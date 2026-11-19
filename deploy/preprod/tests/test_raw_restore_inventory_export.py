"""Native read-only psql exporter tests in an owned disposable Unix-socket PG17.

No externally supplied DSN, host, credential, cloud or application database used.
Run with a Python containing psycopg; set TRADEBOT_TEST_PG17_BIN only to an
installed PG17 bin directory if it is not in PATH/Homebrew's normal location.
"""
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

try:
    import psycopg
except ImportError:
    psycopg = None

SCRIPT = Path(__file__).resolve().parents[1] / 'export_raw_restore_inventory.sql'
ORIGIN = 'pp-live-pp'
GENERATION = '00000000-0000-4000-8000-000000000001'
SEAL_HASH = 'a' * 64
FIELDS = {'manifest_id', 'format_version', 'object_key', 'sha256',
          'row_count', 'byte_count', 'coverage'}


@unittest.skipUnless(psycopg, 'native exporter tests require psycopg')
class RawRestoreInventoryExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        choices = [os.getenv('TRADEBOT_TEST_PG17_BIN'),
                   '/opt/homebrew/opt/postgresql@17/bin',
                   str(Path(shutil.which('psql') or '/missing').parent)]
        cls.bin = next((Path(p) for p in choices if p and
                        all((Path(p)/n).is_file() for n in ('psql', 'initdb', 'pg_ctl'))), None)
        if cls.bin is None:
            raise unittest.SkipTest('installed PostgreSQL17 binaries unavailable')
        version = subprocess.run([str(cls.bin/'psql'), '--version'], check=True,
                                 capture_output=True, text=True).stdout
        if ' 17.' not in version:
            raise unittest.SkipTest('exporter requires PostgreSQL17 transaction_timeout')
        cls.temp = tempfile.TemporaryDirectory(prefix='tradebot-raw-inventory-', dir='/tmp')
        cls.root = Path(cls.temp.name)
        cls.data, cls.socket = cls.root/'data', cls.root/'socket'
        cls.socket.mkdir()
        cls.env = {k: v for k, v in os.environ.items() if not k.startswith('PG')}
        cls.env.update(PGHOST=str(cls.socket), PGPORT='5432', PGDATABASE='tradebot_pp',
                       PGUSER='tradebot_reader', PGCONNECT_TIMEOUT='2')
        try:
            subprocess.run([str(cls.bin/'initdb'), '-D', str(cls.data), '-U', 'fixture_owner',
                            '--auth-local=trust', '--auth-host=reject', '--no-locale',
                            '--encoding=UTF8'], check=True, capture_output=True, env=cls.env)
            subprocess.run([str(cls.bin/'pg_ctl'), '-D', str(cls.data), '-l', str(cls.root/'server.log'),
                            '-o', shlex.join(['-k', str(cls.socket), '-h', '', '-p', '5432']),
                            '-w', 'start'], check=True, capture_output=True, env=cls.env)
            with psycopg.connect(host=str(cls.socket), user='fixture_owner', dbname='postgres',
                                 autocommit=True) as db:
                db.execute('CREATE DATABASE tradebot_pp')
                db.execute('CREATE ROLE tradebot_reader LOGIN')
            with cls.admin() as db:
                db.execute('CREATE SCHEMA archive')
                db.execute('''CREATE TABLE archive.generations (
                    origin_id text,generation_id text,state text,hold_reason text,
                    seal_count bigint,seal_hash text,sealed_at timestamptz,
                    verified_at timestamptz,retired_at timestamptz,
                    PRIMARY KEY(origin_id,generation_id))''')
                db.execute('''CREATE TABLE archive.manifests (
                    origin_id text,generation_id text,manifest_id text,format_version integer,
                    object_key text,sha256 text,row_count bigint,byte_count bigint,
                    coverage jsonb,verified_at timestamptz,verification jsonb,
                    PRIMARY KEY(origin_id,generation_id,manifest_id))''')
                db.execute('GRANT USAGE ON SCHEMA archive TO tradebot_reader')
                db.execute('GRANT SELECT ON ALL TABLES IN SCHEMA archive TO tradebot_reader')
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def admin(cls):
        return psycopg.connect(host=str(cls.socket), user='fixture_owner', dbname='tradebot_pp')

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'data'):
            subprocess.run([str(cls.bin/'pg_ctl'), '-D', str(cls.data), '-m', 'immediate',
                            '-w', 'stop'], capture_output=True, env=cls.env)
            cls.temp.cleanup()

    def setUp(self):
        self.load()

    def load(self, count=2, *, origin=ORIGIN):
        self.manifests = []
        prior = None
        for index in range(count):
            last = ['coinbase', str(index)]
            checksum = hashlib.sha256(str(index).encode()).hexdigest()
            coverage = dict(format_version=1, dataset='raw.events', origin_id=origin,
                            generation_id=GENERATION, after=prior, first=last, last=last,
                            decoded_bytes=123, decoded_sha256='b'*64, identity_sha256='c'*64)
            self.manifests.append(dict(manifest_id=f'raw.events:{index:012d}', format_version=1,
                object_key=f'raw-v1/{hashlib.sha256(origin.encode()).hexdigest()}/{GENERATION}/{checksum}.jsonl.gz',
                sha256=checksum, row_count=1, byte_count=123, coverage=coverage))
            prior = last
        with self.admin() as db:
            db.execute('TRUNCATE archive.manifests,archive.generations')
            db.execute('INSERT INTO archive.generations VALUES (%s,%s,%s,NULL,%s,%s,now(),now(),NULL)',
                       (origin, GENERATION, 'verified', count, SEAL_HASH))
            for m in reversed(self.manifests):
                db.execute('INSERT INTO archive.manifests VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,now(),%s::jsonb)',
                    (origin, GENERATION, m['manifest_id'], 1, m['object_key'], m['sha256'], 1, 123,
                     json.dumps(m['coverage']), json.dumps({'method': 'fresh_authenticated_readback'})))

    def export(self, *, user='tradebot_reader', **overrides):
        variables = dict(expected_origin=ORIGIN, generation_id=GENERATION,
                         expected_seal_count=str(len(self.manifests)), expected_seal_hash=SEAL_HASH)
        variables.update(overrides)
        command = [str(self.bin/'psql'), '-X', '-w', '-qAt']
        for name, value in variables.items():
            command.extend(['-v', f'{name}={value}'])
        command.extend(['-f', str(SCRIPT)])
        return subprocess.run(command, capture_output=True, text=True,
                              env={**self.env, 'PGUSER': user}, timeout=6)

    def denied(self, **kwargs):
        result = self.export(**kwargs)
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')

    def test_existing_select_only_reader_exports_exact_ordered_contract(self):
        result = self.export()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 1)
        document = json.loads(result.stdout)
        self.assertEqual(set(document), {'generation', 'manifests'})
        self.assertEqual(document['generation'], dict(origin_id=ORIGIN, generation_id=GENERATION,
            seal_count=2, seal_hash=SEAL_HASH))
        self.assertEqual(document['manifests'], self.manifests)
        self.assertTrue(all(set(m) == FIELDS for m in document['manifests']))

    def test_retired_generation_is_supported(self):
        with self.admin() as db:
            db.execute("UPDATE archive.generations SET state='retired',retired_at=now()")
        self.assertEqual(self.export().returncode, 0)

    def test_invalid_or_injected_scope_and_changed_seal_emit_no_payload(self):
        for overrides in (dict(expected_origin='prod-live'), dict(expected_origin="pp-live-pp'; SELECT 9; --"),
                          dict(generation_id='AAAAAAAA-0000-4000-8000-000000000001'),
                          dict(generation_id=GENERATION+"'; SELECT 9; --"),
                          dict(generation_id='not-uuid'), dict(expected_seal_count='1'),
                          dict(expected_seal_count='9223372036854775808'),
                          dict(expected_seal_hash='b'*64), dict(max_manifests='0'),
                          dict(max_manifests='129'), dict(max_manifests="1; SELECT 9; --")):
            with self.subTest(overrides=overrides):
                self.denied(**overrides)

    def test_unqualified_generation_or_manifest_emits_no_payload(self):
        for statement in ("UPDATE archive.generations SET state='sealed'",
                          "UPDATE archive.generations SET hold_reason='held'",
                          "UPDATE archive.generations SET state='retired',retired_at=NULL",
                          'UPDATE archive.generations SET verified_at=NULL',
                          'UPDATE archive.manifests SET verified_at=NULL',
                          "UPDATE archive.manifests SET verification='{}'::jsonb",
                          "UPDATE archive.manifests SET object_key='foreign/key'",
                          'UPDATE archive.manifests SET row_count=2',
                          "UPDATE archive.manifests SET coverage=coverage-'origin_id' WHERE manifest_id='raw.events:000000000001'",
                          "UPDATE archive.manifests SET coverage=jsonb_set(coverage,'{after}','null'::jsonb) WHERE manifest_id='raw.events:000000000001'",
                          "UPDATE archive.manifests SET manifest_id='raw.events:999999999999' WHERE manifest_id='raw.events:000000000001'",
                          "UPDATE archive.manifests SET coverage=jsonb_build_object('large',repeat('x',1048577))"):
            self.load()
            with self.admin() as db:
                db.execute(statement)
            with self.subTest(statement=statement):
                self.denied()

    def test_count_cap_rejects_whole_inventory_instead_of_truncating(self):
        self.denied(max_manifests='1')
        self.load(128)
        self.assertEqual(len(json.loads(self.export().stdout)['manifests']), 128)
        self.load(129)
        self.denied()

    def test_empty_sealed_generation_has_one_verified_empty_manifest(self):
        self.load(1)
        coverage = {**self.manifests[0]['coverage'], 'first': None, 'last': None}
        with self.admin() as db:
            db.execute('UPDATE archive.generations SET seal_count=0')
            db.execute('UPDATE archive.manifests SET row_count=0,coverage=%s::jsonb',
                       (json.dumps(coverage),))
        result = self.export(expected_seal_count='0')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['manifests'][0]['row_count'], 0)

    def test_wrong_login_or_effective_column_write_cannot_export(self):
        self.denied(user='fixture_owner')
        with self.admin() as db:
            db.execute('GRANT UPDATE(object_key) ON archive.manifests TO tradebot_reader')
        try:
            self.denied()
        finally:
            with self.admin() as db:
                db.execute('REVOKE UPDATE(object_key) ON archive.manifests FROM tradebot_reader')

    def test_ddl_lock_timeout_emits_no_payload(self):
        with self.admin() as db:
            db.execute('LOCK TABLE archive.manifests IN ACCESS EXCLUSIVE MODE')
            result = self.export()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')
        self.assertIn('lock timeout', result.stderr)


if __name__ == '__main__':
    unittest.main()
