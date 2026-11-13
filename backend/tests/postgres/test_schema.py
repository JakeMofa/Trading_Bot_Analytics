"""CP2 generated schema tests. Integration requires isolated CI DSN files.

Never target a live database. Root creates the generated foundation fixture.
Tests perform reversible mutation inside rollback transactions only.
"""
from decimal import Decimal
import os
from pathlib import Path
import tempfile
from contextlib import contextmanager
import unittest

from postgres.contract import source_timestamp, exact_decimal, canonical_json, content_hash, partition_name
from postgres.connection import EnvironmentMismatch, connect, connect_migrator, validate_environment
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

    def test_migrator_activation_is_explicit_and_rejects_runtime_login(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import patch
        class Cursor:
            def __init__(self,row): self.row=row
            def fetchone(self): return self.row
            def fetchall(self): return self.row
        class Connection:
            def __init__(self,login):
                self.login=login; self.owner=False; self.closed=False; self.statements=[]
            def execute(self,sql):
                self.statements.append(sql)
                if sql=='SELECT session_user AS login': return Cursor({'login':self.login})
                if sql=='SET ROLE tradebot_owner': self.owner=True; return Cursor(None)
                if sql=='SELECT current_database() AS database_name': return Cursor({'database_name':'tradebot_pp'})
                if 'FROM ops.environment_identity' in sql:
                    if self.login=='tradebot_migrator' and not self.owner: raise PermissionError('NOINHERIT')
                    return Cursor([dict(singleton=True,environment='preprod',database_name='tradebot_pp',foundation_version=1)])
                raise AssertionError(sql)
            def commit(self): pass
            def close(self): self.closed=True
        def run(login,helper,environment='preprod'):
            db=Connection(login)
            modules={'psycopg':SimpleNamespace(connect=lambda *a,**k:db),
                     'psycopg.rows':SimpleNamespace(dict_row=object())}
            with patch.dict(sys.modules,modules):
                try: helper('generated fixture',environment)
                except Exception:
                    self.assertTrue(db.closed)
                    raise
            return db
        migrated=run('tradebot_migrator',connect_migrator)
        self.assertTrue(migrated.owner)
        runtime=run('tradebot_app',connect)
        self.assertFalse(runtime.owner)
        with self.assertRaises(EnvironmentMismatch): run('tradebot_app',connect_migrator)
        with self.assertRaises(EnvironmentMismatch): run('tradebot_migrator',connect_migrator,'production')
        with self.assertRaises(PermissionError): run('tradebot_migrator',connect)

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
        cls.db=connect_migrator(Path(_MIGRATOR_FILE).read_text().strip(),'preprod')
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

    def test_explicit_upgrade_and_applied_file_mutation(self):
        with self.generated_transaction(),tempfile.TemporaryDirectory() as directory:
            for migration in load_migrations():
                Path(directory,migration.name).write_text(migration.sql)
            upgrade=Path(directory,'0002_generated_upgrade.sql')
            upgrade.write_text('CREATE TABLE ops.generated_upgrade_probe(id integer PRIMARY KEY);')
            self.assertEqual(apply_migrations(self.db,directory=directory),[2])
            self.assertEqual(apply_migrations(self.db,directory=directory),[])
            self.assertEqual(validate_schema(self.db,migrations=load_migrations(directory)),2)
            original=Path(directory,load_migrations()[0].name)
            original.write_text(original.read_text()+'\n-- forbidden applied-file mutation\n')
            with self.assertRaises(SchemaDrift):
                apply_migrations(self.db,directory=directory)

    def test_migrator_role_explicit_and_identity_checked(self):
        row=self.db.execute('SELECT session_user AS login,current_user AS effective').fetchone()
        self.assertEqual(row,dict(login='tradebot_migrator',effective='tradebot_owner'))
        self.db.rollback()
        with self.assertRaises(EnvironmentMismatch):
            connect_migrator(Path(_MIGRATOR_FILE).read_text().strip(),'production')

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

    @contextmanager
    def generated_transaction(self):
        class RollbackFixture(Exception): pass
        try:
            with self.db.transaction():
                self.db.execute('SET LOCAL ROLE tradebot_owner')
                yield
                raise RollbackFixture()
        except RollbackFixture:
            pass
        finally:
            self.db.rollback()

    def seed_market(self, market='market-1', origin='generated-cp2-schema'):
        self.db.execute("""INSERT INTO core.markets(origin_id,market_id,source,slug,duration,
            start_time,end_time,start_epoch,end_epoch,status,first_seen,last_seen,payload,content_hash)
            VALUES(%s,%s,'polymarket_us',%s,900,'2026-11-12T00:00:00Z','2026-11-12T00:15:00Z',
            core.source_epoch('2026-11-12T00:00:00Z'),core.source_epoch('2026-11-12T00:15:00Z'),
            'MARKET_STATUS_OPEN','2026-11-12T00:00:00Z','2026-11-12T00:00:00Z','{}',%s)""",
            (origin,market,market,'1'*64))

    def seed_generation(self):
        generation='00000000-0000-4000-8000-000000000001'
        name=partition_name(generation)
        self.db.execute("""INSERT INTO archive.generations(origin_id,generation_id,slot,state,
            partition_name,created_at) VALUES('generated-cp2-schema',%s,'A','prepared',%s,now())""",
            (generation,name))
        self.db.execute("SELECT archive.create_generation_partition('generated-cp2-schema',%s)",(generation,))
        return generation,name

    def test_origin_reference_integrity_and_raw_independence(self):
        with self.generated_transaction():
            self.seed_market()
            self.seed_market('market-2')
            self.seed_market(origin='generated-other-origin')
            generation,name=self.seed_generation()
            self.db.execute("""INSERT INTO raw.events(generation_id,origin_id,source,event_id,kind,
                market_id,source_time,source_epoch,received_at,available_at,price,payload,content_hash)
                VALUES(%s,'generated-cp2-schema','polymarket_us','event-1','metadata','market-1',
                '2026-11-12T00:00:00.123456789Z',core.source_epoch('2026-11-12T00:00:00.123456789Z'),
                '2026-11-12T00:00:01Z','2026-11-12T00:00:01Z',91234.12345678901234567890,'{}',%s)""",
                (generation,'2'*64))
            self.db.execute("""INSERT INTO core.protected_evidence(origin_id,evidence_id,generation_id,
                source,event_id,kind,market_id,source_time,source_epoch,received_at,available_at,payload,content_hash)
                SELECT origin_id,'evidence-1',generation_id,source,event_id,kind,market_id,source_time,
                source_epoch,received_at,available_at,payload,content_hash FROM raw.events WHERE generation_id=%s""",(generation,))
            self.db.execute("""INSERT INTO core.feature_snapshots VALUES('generated-cp2-schema','snapshot-1',
                'market-1','2026-11-12T00:00:02Z',1,'{}','{}','{}',%s)""",('3'*64,))
            self.db.execute("INSERT INTO core.snapshot_evidence VALUES('generated-cp2-schema','snapshot-1','evidence-1')")
            with self.assertRaises(Exception),self.db.transaction():
                self.db.execute("INSERT INTO core.snapshot_evidence VALUES('generated-cp2-schema','snapshot-1','missing')")
            with self.assertRaises(Exception),self.db.transaction():
                self.db.execute("""INSERT INTO core.outcomes(origin_id,outcome_id,market_id,evidence_id,result,
                    confirmed_at,available_at,payload,content_hash) VALUES('generated-cp2-schema','o1',
                    'market-2','evidence-1','UP',now(),now(),'{}',%s)""",('4'*64,))
            with self.assertRaises(Exception),self.db.transaction():
                self.db.execute("""INSERT INTO core.predictions(origin_id,prediction_id,snapshot_id,market_id,
                    model_version,as_of,created_at,seconds_remaining,probability_up,probability_down,
                    assumptions_json,payload,content_hash) VALUES('generated-cp2-schema','p1','snapshot-1',
                    'market-1','test','2026-11-12T00:00:03Z','2026-11-12T00:00:03Z',897,0.5,0.5,'{}','{}',%s)""",('5'*64,))
            # Generated-only owner drop demonstrates references have no raw FK dependency;
            # actual authoritative retirement gates are covered separately by CP4 tests.
            from psycopg import sql
            self.db.execute(sql.SQL('DROP TABLE raw.{}').format(sql.Identifier(name)))
            self.assertEqual(self.db.execute("SELECT count(*) AS n FROM core.protected_evidence WHERE origin_id='generated-cp2-schema'").fetchone()['n'],1)
            self.assertEqual(self.db.execute("SELECT count(*) AS n FROM core.snapshot_evidence WHERE origin_id='generated-cp2-schema'").fetchone()['n'],1)

    def test_dynamic_partition_shape_and_grants(self):
        with self.generated_transaction():
            _,name=self.seed_generation()
            second='00000000-0000-4000-8000-000000000002'
            self.db.execute("""INSERT INTO archive.generations(origin_id,generation_id,slot,state,partition_name,created_at)
                VALUES('generated-cp2-schema',%s,'B','prepared',%s,now())""",(second,partition_name(second)))
            third='00000000-0000-4000-8000-000000000003'
            with self.assertRaises(Exception),self.db.transaction():
                self.db.execute("""INSERT INTO archive.generations(origin_id,generation_id,slot,state,partition_name,created_at)
                    VALUES('generated-cp2-schema',%s,'A','prepared',%s,now())""",(third,partition_name(third)))
            self.assertEqual(validate_schema(self.db),1)
            from psycopg import sql
            for statement in [sql.SQL('ALTER TABLE raw.{} ADD CONSTRAINT extra CHECK(length(event_id)>0)').format(sql.Identifier(name)),
                              sql.SQL('CREATE INDEX extra ON raw.{}(source)').format(sql.Identifier(name)),
                              sql.SQL('GRANT DELETE ON raw.{} TO tradebot_app').format(sql.Identifier(name))]:
                class RevertMutation(Exception): pass
                with self.assertRaises(RevertMutation):
                    with self.db.transaction():
                        self.db.execute(statement)
                        with self.assertRaises(SchemaDrift): validate_schema(self.db)
                        raise RevertMutation()
                self.assertEqual(validate_schema(self.db),1)

    @unittest.skipUnless(_APP_FILE,'application DSN fixture not configured')
    def test_app_no_ddl_owner_or_ledger_mutation(self):
        app_dsn=Path(_APP_FILE).read_text().strip()
        with self.assertRaises(EnvironmentMismatch):
            connect_migrator(app_dsn,'preprod')
        with connect(app_dsn,'preprod') as app:
            self.assertEqual(app.execute('SELECT current_user AS role').fetchone()['role'],'tradebot_app')
            self.assertEqual(validate_schema(app),1)
            app.rollback()
            for sql in ['CREATE TABLE core.unreviewed(id int)','SET ROLE tradebot_owner',
                        'DELETE FROM ops.schema_migrations','DELETE FROM core.protected_evidence']:
                with self.subTest(sql=sql),self.assertRaises(Exception),app.transaction(): app.execute(sql)
                app.rollback()


if __name__=='__main__': unittest.main()
