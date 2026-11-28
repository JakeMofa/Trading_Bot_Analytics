"""Owned disposable Unix-socket PG17 role/Storage-policy approximation only.

No external DSN, credential, Supabase, host or cloud runtime is contacted.
"""
import json
from contextlib import contextmanager
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend')); sys.path.insert(0,str(ROOT/'deploy/preprod'))
import psycopg
from psycopg import sql
from postgres.cloud_origin_binding import TRIAL_ORIGIN,TRIAL_WRITER,TRIAL_READER,cloud_binding
from bind_trial_cloud_policy import render

WUID='00000000-0000-4000-8000-0000000000cc'
RUID='00000000-0000-4000-8000-0000000000dd'
OLDUID='00000000-0000-4000-8000-0000000000aa'
GEN='00000000-0000-4000-8000-000000000001'
POLICY_HASH="""SELECT encode(sha256(convert_to(COALESCE(jsonb_agg(to_jsonb(p) ORDER BY p.policyname),'[]'::jsonb)::text,'UTF8')),'hex')
FROM pg_policies p WHERE schemaname='storage' AND tablename='objects'"""


class TrialCloudPolicyPGTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        choices=[os.getenv('TRADEBOT_TEST_PG17_BIN'),'/opt/homebrew/opt/postgresql@17/bin',
                 str(Path(shutil.which('psql') or '/missing').parent)]
        cls.bin=next((Path(path) for path in choices if path and all((Path(path)/n).is_file() for n in ('initdb','pg_ctl','psql'))),None)
        if cls.bin is None: raise unittest.SkipTest('native PostgreSQL17 binaries unavailable')
        if ' 17.' not in subprocess.run([str(cls.bin/'psql'),'--version'],capture_output=True,text=True,check=True).stdout:
            raise unittest.SkipTest('native policy tests require PostgreSQL17')
        cls.temp=tempfile.TemporaryDirectory(prefix='trial-cloud-policy-',dir='/tmp')
        cls.root=Path(cls.temp.name); cls.data=cls.root/'data'; cls.socket=cls.root/'socket'; cls.socket.mkdir()
        cls.env={k:v for k,v in os.environ.items() if not k.startswith('PG')}
        subprocess.run([str(cls.bin/'initdb'),'-D',str(cls.data),'-U','postgres','--auth-local=trust',
            '--auth-host=reject','--no-locale','--encoding=UTF8'],env=cls.env,check=True,capture_output=True)
        subprocess.run([str(cls.bin/'pg_ctl'),'-D',str(cls.data),'-l',str(cls.root/'server.log'),'-o',
            shlex.join(['-k',str(cls.socket),'-h','','-p','5432']),'-w','start'],env=cls.env,check=True,capture_output=True)
        try:
            with cls.admin() as db:
                db.execute('CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN; CREATE ROLE service_role NOLOGIN')
                for filename in ('20261116050000_history_v2_private.sql','20261118012340_structured_receipts_v2.sql',
                    '20261118020000_pp_history_v2_role.sql','20261118031407_pp_structured_receipt_grants.sql',
                    '20261119020000_pp_structured_revision_payloads.sql'):
                    db.execute((ROOT/'supabase/migrations'/filename).read_text())
                cls.old_policies=db.execute("SELECT policyname,tablename,qual,with_check FROM pg_policies WHERE schemaname='history_v2' ORDER BY tablename,policyname").fetchall()
                db.execute((ROOT/'supabase/review/pp_trial_20261119_01_structured.sql').read_text())
                for origin in ('pp-live-pp',TRIAL_ORIGIN,'production','generated-fixture'):
                    db.execute('''INSERT INTO history_v2.generation_checkpoints
                      (origin_id,generation_id,dataset,cursor,row_count,content_hash,acknowledged_at)
                      VALUES(%s,%s,'fixture','{}',0,%s,now())''',(origin,GEN,'a'*64))
                db.execute((ROOT/'deploy/preprod/tests/pp_storage_policy_fixture.sql').read_text())
                base=(ROOT/'supabase/review/pp_market_raw_storage_policies.sql.in').read_text()
                db.execute(base.replace('__PP_STORAGE_AUTH_UID__',OLDUID).replace('__PP_STORAGE_AUTH_EMAIL__','pp-storage-archive@example.invalid'))
                for uid,email,role in ((WUID,'trial-writer@example.invalid','pp_storage_archive'),(RUID,'trial-reader@example.invalid','pp_storage_history_reader')):
                    db.execute('INSERT INTO auth.users VALUES(%s,%s,\'authenticated\',now(),%s::jsonb)',
                        (uid,email,json.dumps(dict(tradebot_role=role,tradebot_origin=TRIAL_ORIGIN))))
                cls.before_storage=db.execute("SELECT policyname,qual,with_check FROM pg_policies WHERE schemaname='storage' ORDER BY policyname").fetchall()
                cls.catalog_hash=db.execute(POLICY_HASH).fetchone()[0]
                db.execute(render(writer_uid=WUID,writer_email='trial-writer@example.invalid',reader_uid=RUID,
                    reader_email='trial-reader@example.invalid',policy_sha256=cls.catalog_hash))
                cls.trial_key=cloud_binding(TRIAL_ORIGIN).raw_prefix+GEN+'/'+'a'*64+'.jsonl.gz'
                cls.old_key=cloud_binding('pp-live-pp').raw_prefix+GEN+'/'+'b'*64+'.jsonl.gz'
                db.execute("INSERT INTO storage.objects(bucket_id,name) VALUES('market-raw',%s),('market-raw',%s)",(cls.trial_key,cls.old_key))
        except Exception:
            cls.tearDownClass(); raise

    @classmethod
    def admin(cls): return psycopg.connect(host=str(cls.socket),user='postgres',dbname='postgres')

    @classmethod
    def tearDownClass(cls):
        subprocess.run([str(cls.bin/'pg_ctl'),'-D',str(cls.data),'-m','immediate','-w','stop'],env=cls.env,check=True,capture_output=True)
        cls.temp.cleanup()

    def set_role(self,db,role): db.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)))
    def storage_request(self,db,uid,operation):
        self.set_role(db,'authenticated')
        db.execute("SELECT set_config('request.jwt.claim.sub',%s,true),set_config('storage.operation',%s,true)",(uid,operation))

    def test_structured_reader_writer_and_legacy_are_origin_isolated(self):
        for role,origin in ((TRIAL_WRITER,TRIAL_ORIGIN),(TRIAL_READER,TRIAL_ORIGIN),('tradebot_pp_history','pp-live-pp')):
            with self.admin() as db:
                self.set_role(db,role)
                self.assertEqual(db.execute('SELECT origin_id FROM history_v2.generation_checkpoints').fetchall(),[(origin,)])
        with self.admin() as db:
            self.set_role(db,TRIAL_WRITER)
            db.execute('UPDATE history_v2.generation_checkpoints SET row_count=1 WHERE origin_id=%s',(TRIAL_ORIGIN,))
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                db.execute('UPDATE history_v2.generation_checkpoints SET origin_id=\'pp-live-pp\'')
        for role,statement in ((TRIAL_READER,'UPDATE history_v2.generation_checkpoints SET row_count=3'),
            (TRIAL_WRITER,'DELETE FROM history_v2.generation_checkpoints'),
            (TRIAL_WRITER,"UPDATE history_v2.predictions SET content_hash=repeat('b',64)"),
            (TRIAL_READER,'SELECT * FROM history_v2.coverage'),
            (TRIAL_READER,"INSERT INTO history_v2.generation_checkpoints(origin_id,generation_id,dataset,cursor,row_count,content_hash,acknowledged_at) VALUES('pp-live-pp-trial-20261119-01','00000000-0000-4000-8000-000000000002','fixture','{}',0,repeat('a',64),now())"),
            (TRIAL_WRITER,"INSERT INTO history_v2.generation_checkpoints(origin_id,generation_id,dataset,cursor,row_count,content_hash,acknowledged_at) VALUES('production','00000000-0000-4000-8000-000000000002','fixture','{}',0,repeat('a',64),now())")):
            with self.admin() as db:
                self.set_role(db,role)
                with self.assertRaises(psycopg.errors.InsufficientPrivilege): db.execute(statement)

    def test_role_attributes_grants_and_old_policies_are_unchanged(self):
        with self.admin() as db:
            for role in (TRIAL_WRITER,TRIAL_READER):
                attrs=db.execute('SELECT rolcanlogin,rolinherit,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication,rolconnlimit FROM pg_roles WHERE rolname=%s',(role,)).fetchone()
                self.assertEqual(attrs,(False,False,False,False,False,False,False,2))
                self.assertEqual(db.execute('SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=%s)',(role,)).fetchone()[0],0)
            unchanged=db.execute("SELECT policyname,tablename,qual,with_check FROM pg_policies WHERE schemaname='history_v2' AND policyname NOT LIKE 'pp_trial_20261119_01_%' ORDER BY tablename,policyname").fetchall()
            self.assertEqual(unchanged,self.old_policies)
            unchanged=db.execute("SELECT policyname,qual,with_check FROM pg_policies WHERE schemaname='storage' AND policyname NOT LIKE 'pp_trial_20261119_01_%' ORDER BY policyname").fetchall()
            self.assertEqual(unchanged,self.before_storage)
            for role,insert,update in ((TRIAL_WRITER,11,3),(TRIAL_READER,0,0)):
                for privilege,expected in (('SELECT',11),('INSERT',insert),('UPDATE',update),('DELETE',0),('TRUNCATE',0)):
                    self.assertEqual(db.execute('''SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                       WHERE n.nspname='history_v2' AND c.relkind='r' AND has_table_privilege(%s,c.oid,%s)''',(role,privilege)).fetchone()[0],expected)

    def test_storage_exact_new_uid_prefix_operations_and_old_reader_isolation(self):
        for uid,key,expected in ((WUID,self.trial_key,1),(RUID,self.trial_key,1),(WUID,self.old_key,0),
                                 (RUID,self.old_key,0),(OLDUID,self.trial_key,0),(OLDUID,self.old_key,1)):
            with self.admin() as db:
                self.storage_request(db,uid,'storage.object.get_authenticated')
                self.assertEqual(db.execute('SELECT count(*) FROM storage.objects WHERE name=%s',(key,)).fetchone()[0],expected)
        for uid,operation,key in ((RUID,'storage.object.upload',self.trial_key.replace('a'*64,'c'*64)),
            (WUID,'storage.object.upload',self.old_key.replace('b'*64,'d'*64)),
            (WUID,'storage.object.copy',self.trial_key.replace('a'*64,'e'*64))):
            with self.admin() as db:
                self.storage_request(db,uid,operation)
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    db.execute("INSERT INTO storage.objects(bucket_id,name) VALUES('market-raw',%s)",(key,))
        for operation in ('storage.object.list','storage.object.get_public','storage.object.get_signed'):
            with self.admin() as db:
                self.storage_request(db,RUID,operation)
                self.assertEqual(db.execute('SELECT count(*) FROM storage.objects').fetchone()[0],0)
        for statement in ('UPDATE storage.objects SET owner_id=\'changed\'','DELETE FROM storage.objects'):
            with self.admin() as db:
                self.storage_request(db,WUID,'storage.object.upload_update')
                self.assertEqual(db.execute(statement).rowcount,0)
        with self.admin() as db:
            self.storage_request(db,WUID,'storage.object.upload')
            key=self.trial_key.replace('a'*64,'f'*64)
            db.execute("INSERT INTO storage.objects(bucket_id,name) VALUES('market-raw',%s)",(key,))
            db.rollback()

    def test_restrictive_fences_survive_unrelated_permissive_grants(self):
        with self.admin() as db:
            db.execute("CREATE POLICY fixture_broad_select ON history_v2.generation_checkpoints FOR SELECT TO PUBLIC USING(true)")
            self.set_role(db,TRIAL_READER)
            self.assertEqual(db.execute('SELECT origin_id FROM history_v2.generation_checkpoints').fetchall(),[(TRIAL_ORIGIN,)])
            db.rollback()
        with self.admin() as db:
            db.execute("CREATE POLICY fixture_broad_storage_select ON storage.objects FOR SELECT TO authenticated USING(true)")
            self.storage_request(db,RUID,'storage.object.get_authenticated')
            self.assertEqual(db.execute('SELECT name FROM storage.objects').fetchall(),[(self.trial_key,)])
            db.rollback()
        with self.admin() as db:
            db.execute("CREATE POLICY fixture_broad_storage_insert ON storage.objects FOR INSERT TO authenticated WITH CHECK(true)")
            self.storage_request(db,RUID,'storage.object.upload')
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                db.execute("INSERT INTO storage.objects(bucket_id,name) VALUES('market-raw',%s)",(self.trial_key.replace('a'*64,'c'*64),))

    @classmethod
    def role_connection(cls, role):
        from psycopg.rows import dict_row
        @contextmanager
        def connect(*,timeout_seconds):
            with psycopg.connect(host=str(cls.socket),user='postgres',dbname='postgres',
                                 autocommit=True,row_factory=dict_row) as db:
                db.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(role)))
                yield db
        return connect

    def test_trial_writer_receipt_envelope_roundtrip_and_readonly_verifier(self):
        from postgres.archive_codec import encoded
        from postgres.history_v2_transport import HistoryV2PostgresTransport
        from postgres.history_v2_envelope import TABLE_KEYS
        payload=dict(origin_id=TRIAL_ORIGIN,source='coinbase',symbol='BTC-USD',event_id='trial-generated',
            generation_id=GEN,source_time='2026-11-19T00:00:00.123456789Z',
            source_epoch='1795046400.123456789',received_at='2026-11-19T00:00:01Z',
            available_at='2026-11-19T00:00:01Z',price='100000.00000000000000001',size=None,
            payload={'generated':True,'missing':None},content_hash='a'*64)
        record=dict(id=1,origin_id=TRIAL_ORIGIN,generation_id=GEN,entity_type='core.current_prices',
            entity_id=encoded([payload[k] for k in TABLE_KEYS['core.current_prices']]).decode(),
            content_hash=payload['content_hash'],payload=payload)
        writer=HistoryV2PostgresTransport(self.role_connection(TRIAL_WRITER),origin_id=TRIAL_ORIGIN,
            generation_id=GEN,expected_database='postgres',expected_role=TRIAL_WRITER,retain_revisions=True)
        writer.put_structured([record],timeout_seconds=4)
        reader=HistoryV2PostgresTransport(self.role_connection(TRIAL_READER),origin_id=TRIAL_ORIGIN,
            generation_id=GEN,expected_database='postgres',expected_role=TRIAL_READER,retain_revisions=True)
        actual=reader.read_structured_authenticated([record],max_bytes=256*1024,timeout_seconds=4)
        self.assertEqual(actual,[record])
        self.assertEqual(reader.read_revisions([1],max_bytes=256*1024,timeout_seconds=4),[record])

    def test_policy_catalog_drift_blocks_review_template(self):
        with self.admin() as db:
            with self.assertRaises(psycopg.errors.RaiseException):
                db.execute(render(writer_uid=WUID,writer_email='trial-writer@example.invalid',reader_uid=RUID,
                    reader_email='trial-reader@example.invalid',policy_sha256=self.catalog_hash))


if __name__=='__main__': unittest.main()
