"""Execute unchanged schema files against disposable, network-isolated Postgres.

Only Docker exec is used: no connection URL, production credential or host port.
The storage.buckets table and Supabase roles are minimal explicit fixtures, not
an installed Supabase Storage/Auth/PostgREST stack.
"""
import hashlib
import os
from pathlib import Path
import subprocess
import time
import unittest
import uuid
from run_tests import write_evidence
import container_ownership

IMAGE = 'postgres:17.6@sha256:00bc86618629af00d2937fdc5a5d63db3ff8450acf52f0636ec813c7f4902929'
SCHEMAS = [Path('supabase/schema') / name for name in
           ('cloud_memory_v1.sql', 'raw_archive_source_ids_v1.sql', 'storage_buckets_v1.sql')]


class SchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        name = os.environ.get('CI_POSTGRES_CONTAINER', 'tradebot-schema-' + uuid.uuid4().hex)
        cls.receipt = Path(os.environ['CI_EVIDENCE_DIR']) / 'postgres-container-receipt.json'
        cls.addClassCleanup(container_ownership.cleanup, cls.receipt)
        cls.container = container_ownership.create(IMAGE, name, cls.receipt)
        subprocess.run(['docker', 'start', cls.container], check=True, capture_output=True, timeout=20)
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            ready = subprocess.run(['docker', 'exec', cls.container, 'pg_isready', '-h', '127.0.0.1', '-U', 'postgres'],
                                   capture_output=True, timeout=5)
            if ready.returncode == 0:
                cls.sql('CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;')
                return
            time.sleep(.25)
        raise RuntimeError('generated Postgres readiness deadline')

    @classmethod
    def sql(cls, text, database='postgres', fail=False):
        result = subprocess.run(['docker', 'exec', '-i', cls.container, 'psql', '-X',
                                 '-U', 'postgres', '-d', database, '-v', 'ON_ERROR_STOP=1', '-Atq'],
                                input=text, text=True, capture_output=True, timeout=15)
        if fail:
            if result.returncode == 0:
                raise AssertionError('expected generated SQL rejection')
            return result.stderr
        if result.returncode:
            raise AssertionError(result.stderr)
        return result.stdout.strip()

    def setUp(self):
        self.db = 'generated_' + uuid.uuid4().hex
        self.sql('CREATE DATABASE ' + self.db)
        self.addCleanup(self.sql, 'DROP DATABASE ' + self.db)
        self.query('CREATE SCHEMA storage; CREATE TABLE storage.buckets '
                   '(id text primary key, name text not null, public boolean not null);')

    def query(self, text, fail=False):
        return self.sql(text, self.db, fail)

    def apply(self, paths=SCHEMAS):
        for path in paths:
            self.query(path.read_text())

    def market(self):
        self.query('''SET ROLE service_role;
            INSERT INTO public.markets(id,slug,duration,start,"end",target,first_seen,last_seen)
            VALUES ('m','m',15,'2026-01-01T00:00:00Z','2026-01-01 00:15Z',
                    12345.1234567890123456789,'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z');''')

    def test_clean_install_repeat_preserves_exact_values_and_private_buckets(self):
        self.apply()
        self.market()
        self.apply()
        self.assertEqual(self.query("SELECT target::text FROM markets WHERE id='m'"),
                         '12345.1234567890123456789')
        self.assertEqual(self.query('SELECT count(*) FROM storage.buckets WHERE NOT public'), '3')
        self.assertEqual(self.query("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                                    "WHERE n.nspname='public' AND c.relkind='r' AND c.relrowsecurity"), '10')

    def test_legacy_manifest_migration_and_checkpoint_identity(self):
        self.apply(SCHEMAS[:1])
        self.query("""INSERT INTO raw_archives(source,started_at,ended_at,bucket,object_path,compression,
            content_type,sha256,event_count,uncompressed_bytes,compressed_bytes)
            VALUES ('generated','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z','market-raw','legacy','gzip',
                    'application/json','fixture-sha',1,10,5);
            INSERT INTO sync_checkpoints(dataset,last_source_id,last_source_key,rows_synced)
            VALUES ('archive:observations',90,'90',1);""")
        self.apply(SCHEMAS[1:])
        self.apply(SCHEMAS[1:])
        self.assertEqual(self.query("SELECT sha256 || ':' || (first_source_id IS NULL)::text FROM raw_archives"),
                         'fixture-sha:true')
        self.assertEqual(self.query("SELECT last_source_id::text || ':' || last_source_key FROM sync_checkpoints"), '90:90')
        self.query("UPDATE raw_archives SET first_source_id=90,last_source_id=90 WHERE object_path='legacy'")
        self.assertEqual(self.query('SELECT first_source_id::text FROM raw_archives'), '90')

    def test_reference_and_duplicate_constraints_and_transaction_failure(self):
        self.apply()
        self.market()
        error = self.query("INSERT INTO feature_snapshots VALUES (1,'missing','2026-01-01T00:00:00Z',1,'{}','{}','{}',now())", fail=True)
        self.assertIn('foreign key', error)
        self.query("INSERT INTO feature_snapshots VALUES (1,'m','2026-01-01T00:00:00Z',1,'{}','{}','{}',now())")
        self.assertIn('duplicate key', self.query("INSERT INTO feature_snapshots VALUES (1,'m','2026-01-01T00:00:00Z',2,'{}','{}','{}',now())", fail=True))
        self.query("BEGIN; UPDATE markets SET target=999 WHERE id='m'; SELECT 1/0; COMMIT;", fail=True)
        self.assertEqual(self.query("SELECT target::text FROM markets WHERE id='m'"), '12345.1234567890123456789')
        self.assertEqual(self.query('SELECT count(*) FROM feature_snapshots'), '1')

    def test_anonymous_access_denied_service_role_is_mutable_not_immutable(self):
        self.apply()
        self.market()
        for role in ('anon', 'authenticated'):
            self.assertIn('permission denied', self.query('SET ROLE ' + role + '; SELECT * FROM markets', fail=True))
        self.query("SET ROLE service_role; UPDATE markets SET target=2 WHERE id='m'; DELETE FROM markets WHERE id='m';")
        self.assertEqual(self.query('SELECT count(*) FROM markets'), '0')
        # Existing DDL grants CRUD to a BYPASSRLS service fixture: this is NOT a retirement fence.
        self.assertEqual(self.query("SELECT has_table_privilege('service_role','raw_archives','UPDATE')"), 't')

    def test_failed_schema_transaction_rolls_back_then_reviewed_sql_restarts(self):
        text = SCHEMAS[0].read_text()
        self.query(text.replace('commit;', 'SELECT 1/0; commit;'), fail=True)
        self.assertEqual(self.query("SELECT to_regclass('public.markets') IS NULL"), 't')
        self.apply(SCHEMAS[:1])
        # Fault after the non-transactional ALTER committed, before index creation.
        self.query(SCHEMAS[1].read_text().replace('create index if not exists', 'create invalid index'), fail=True)
        self.apply(SCHEMAS[1:])
        self.assertEqual(self.query("SELECT count(*) FROM information_schema.columns WHERE table_name='raw_archives' "
                                    "AND column_name IN ('first_source_id','last_source_id')"), '2')


if __name__ == '__main__':
    started = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SchemaTests))
    passed = result.wasSuccessful() and result.testsRun == 5 and not result.skipped
    write_evidence('postgres', {'gate': 'PASS' if passed else 'FAIL', 'tests': result.testsRun,
                   'skips': len(result.skipped), 'failures': len(result.failures), 'errors': len(result.errors),
                   'image': IMAGE, 'schema_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in SCHEMAS},
                   'limits': {'container_memory_mib': 512, 'data_tmpfs_mib': 256, 'cpus': 1, 'pids': 128},
                   'scope': 'isolated PostgreSQL SQL engine; minimal roles/storage fixture; no live Supabase stack'}, started)
    raise SystemExit(not passed)
