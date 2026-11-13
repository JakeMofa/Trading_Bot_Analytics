"""CP2 generated schema tests. Integration requires isolated CI DSN files.

Never target a live database. Root creates the generated foundation fixture.
Tests perform reversible mutation inside rollback transactions only.
"""
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import tempfile
import unittest

from postgres.contract import source_timestamp, exact_decimal, canonical_json, content_hash, partition_name
from postgres.connection import EnvironmentMismatch, connect, validate_environment
from postgres.migrate import load_migrations, validate_ledger, apply_migrations, validate_schema, SchemaDrift


class ContractTests(unittest.TestCase):
    def test_timestamp_exact_sort_and_original(self):
        a = '2026-11-12T01:02:03.123456789123456789123456789Z'
        b = '2026-11-11T19:02:03.123456789123456789123456790-06:00'
        original, epoch = source_timestamp(a)
        self.assertEqual(original,a)
        self.assertEqual(str(epoch),'1794445323.123456789123456789123456789')
        self.assertGreater(source_timestamp(b)[1],epoch)
        self.assertEqual(source_timestamp('1969-12-31T23:59:59.999999999Z')[1],Decimal('-0.000000001'))

    def test_timestamp_rejects_malformed_and_unknown(self):
        for value in ['2026-11-12T00:00:00','2026-02-30T00:00:00Z','2026-11-12T00:00:60Z',
                      '2026-11-12T00:00:00-00:00','2026-11-12T00:00:00+24:00',None,12]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                source_timestamp(value)

    def test_exact_decimal_json(self):
        value=Decimal('91234.123456789012345678901234567890')
        self.assertEqual(exact_decimal(str(value)),value)
        self.assertEqual(canonical_json({'value':value}),'{"value":"91234.123456789012345678901234567890"}')
        for bad in [0.1,True,'NaN','Infinity',None,{}]:
            with self.subTest(value=bad), self.assertRaises(ValueError):
                exact_decimal(bad)
        self.assertIsNone(exact_decimal(None,nullable=True))
        with self.assertRaises(ValueError):
            canonical_json({'bad':float('nan')})

    def test_uuid_partition_name_injection(self):
        self.assertEqual(partition_name('00000000-0000-4000-8000-000000000001'),'events_g_00000000000040008000000000000001')
        for bad in ['A','bad;DROP SCHEMA core','00000000000040008000000000000001']:
            with self.assertRaises(ValueError): partition_name(bad)

    def test_checksum_mutation_missing_and_gaps(self):
        migrations=load_migrations()
        m=migrations[0]
        row=dict(version=1,name=m.name,checksum=m.checksum,catalog={},catalog_hash=content_hash({}))
        validate_ledger([row],migrations)
        for change in [dict(checksum='0'*64),dict(version=2),dict(name='renamed.sql'),dict(catalog={'drift':True})]:
            with self.subTest(change=change),self.assertRaises(SchemaDrift):
                validate_ledger([row|change],migrations)
        with tempfile.TemporaryDirectory() as directory:
            Path(directory,'0002_gap.sql').write_text('SELECT 1;')
            with self.assertRaises(SchemaDrift): load_migrations(directory)

    def test_migration_cloud_separation_and_no_cascade(self):
        sql='\n'.join(m.sql for m in load_migrations())
        self.assertNotIn('history_v2',sql)
        self.assertNotIn('ON DELETE CASCADE',sql)
        self.assertNotIn('double precision',sql)
        self.assertNotIn('GRANT tradebot_owner',sql)
        cloud=(Path(__file__).parents[2]/'postgres/history_v2_contract.sql').read_text()
        self.assertIn('REVOKE ALL ON SCHEMA history_v2 FROM PUBLIC,anon,authenticated',cloud)
        self.assertNotIn('CREATE TABLE public.',cloud)


_MIGRATOR_FILE = os.environ.get('TRADEBOT_TEST_MIGRATOR_DSN_FILE')
_APP_FILE = os.environ.get('TRADEBOT_TEST_APP_DSN_FILE')


@unittest.skipUnless(_MIGRATOR_FILE,'isolated generated PostgreSQL fixture not configured')
class PostgreSQLSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=connect(Path(_MIGRATOR_FILE).read_text().strip(),'preprod')
        cls.first_apply=apply_migrations(cls.db,'preprod')
        cls.db.commit()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_empty_or_foundation_install_and_repeat(self):
        self.assertIn(self.first_apply,([1],[]))
        self.assertEqual(apply_migrations(self.db),[])
        self.assertEqual(validate_schema(self.db),1)
        self.db.rollback()

    def test_wrong_environment(self):
        with self.assertRaises(EnvironmentMismatch): validate_environment(self.db,'production')
        self.db.rollback()

    def test_exact_decimal_and_timestamp_database(self):
        value='91234.123456789012345678901234567890'
        stamp='2026-11-12T01:02:03.123456789123456789123456789Z'
        row=self.db.execute('SELECT %s::core.exact_numeric AS n,core.source_epoch(%s) AS t',(value,stamp)).fetchone()
        self.assertEqual(row['n'],Decimal(value))
        self.assertEqual(row['t'],source_timestamp(stamp)[1])
        self.db.rollback()
        for bad in ['NaN','Infinity','-Infinity']:
            with self.assertRaises(Exception),self.db.transaction():
                self.db.execute('SELECT %s::core.exact_numeric',(bad,))
        self.db.rollback()

    def test_schema_constraint_index_grant_mutations_rejected(self):
        mutations=[
            'ALTER TABLE core.markets ADD COLUMN unreviewed text',
            'ALTER TABLE core.markets ADD CONSTRAINT unreviewed CHECK (length(slug)>0)',
            'CREATE INDEX unreviewed ON core.markets(slug)',
            'GRANT DELETE ON core.markets TO tradebot_app',
            'ALTER TABLE core.markets ALTER COLUMN status SET DEFAULT \'unreviewed\'',
            "UPDATE ops.schema_migrations SET checksum=repeat('0',64)",
            "UPDATE ops.environment_identity SET foundation_version=2",
        ]
        for sql in mutations:
            with self.subTest(sql=sql):
                class ExpectedRollback(Exception): pass
                with self.assertRaises(ExpectedRollback):
                    with self.db.transaction():
                        self.db.execute('SET LOCAL ROLE tradebot_owner')
                        try:
                            self.db.execute(sql)
                        except Exception:
                            # A restrictive foundation check may reject mutation directly.
                            raise ExpectedRollback()
                        with self.assertRaises(SchemaDrift): validate_schema(self.db)
                        raise ExpectedRollback()
                self.db.rollback()
                self.assertEqual(validate_schema(self.db),1)
                self.db.rollback()

    @unittest.skipUnless(_APP_FILE,'application DSN fixture not configured')
    def test_app_no_ddl_owner_or_ledger_mutation(self):
        with connect(Path(_APP_FILE).read_text().strip(),'preprod') as app:
            self.assertEqual(validate_schema(app),1)
            app.rollback()
            for sql in ['CREATE TABLE core.unreviewed(id int)','SET ROLE tradebot_owner',
                        'DELETE FROM ops.schema_migrations','DELETE FROM core.protected_evidence']:
                with self.subTest(sql=sql),self.assertRaises(Exception),app.transaction(): app.execute(sql)
                app.rollback()


if __name__=='__main__': unittest.main()
