"""Fourth exact trial policy proof in an owned socket-only PG17 cluster."""
from hashlib import sha256
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'deploy/preprod'))
import psycopg
from psycopg import sql
from bind_trial_cloud_policy import render as first_render
from bind_second_trial_cloud_policy import render as second_render
from bind_third_trial_cloud_policy import render as third_render
from bind_fourth_trial_cloud_policy import render
from bind_fifth_trial_cloud_policy import render as fifth_render

FIRST='pp-live-pp-trial-20261119-01'
RETAINED_SECOND='pp-live-pp-trial-20261119-02'
THIRD='pp-live-pp-trial-20261119-03'
FOURTH='pp-live-pp-trial-20261119-04'
WRITER='tradebot_pp_trial_20261119_04_writer'
READER='tradebot_pp_trial_20261119_04_reader'
GEN='00000000-0000-4000-8000-000000000001'
UIDS=['00000000-0000-4000-8000-0000000000'+suffix for suffix in ('bb','cc','dd','ee','ff','11','22','33')]
CATALOG="SELECT policyname,tablename,roles,cmd,qual,with_check FROM pg_policies WHERE schemaname=%s ORDER BY tablename,policyname"
HASH="""SELECT encode(sha256(convert_to(COALESCE(jsonb_agg(to_jsonb(p) ORDER BY p.policyname),'[]'::jsonb)::text,'UTF8')),'hex')
FROM pg_policies p WHERE schemaname='storage' AND tablename='objects'"""


class FourthTrialPolicyPGTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        choices=[os.getenv('TRADEBOT_TEST_PG17_BIN'),'/opt/homebrew/opt/postgresql@17/bin',str(Path(shutil.which('psql') or '/missing').parent)]
        cls.bin=next((Path(p) for p in choices if p and all((Path(p)/n).is_file() for n in ('initdb','pg_ctl','psql'))),None)
        if cls.bin is None:raise unittest.SkipTest('native PG17 unavailable')
        if ' 17.' not in subprocess.run([str(cls.bin/'psql'),'--version'],check=True,capture_output=True,text=True).stdout:
            raise unittest.SkipTest('native PG17 required')
        cls.temp=tempfile.TemporaryDirectory(prefix='fourth-trial-policy-',dir='/tmp');cls.root=Path(cls.temp.name)
        cls.socket=cls.root/'socket';cls.socket.mkdir();cls.env={k:v for k,v in os.environ.items() if not k.startswith('PG')}
        cls.passfile=cls.root/'empty.pgpass';cls.passfile.write_bytes(b'');cls.passfile.chmod(0o600)
        subprocess.run([str(cls.bin/'initdb'),'-D',str(cls.root/'data'),'-U','postgres','--auth-local=trust','--auth-host=reject','--no-locale','-E','UTF8'],env=cls.env,check=True,capture_output=True)
        subprocess.run([str(cls.bin/'pg_ctl'),'-D',str(cls.root/'data'),'-l',str(cls.root/'log'),'-o',shlex.join(['-k',str(cls.socket),'-h','','-p','5432']),'-w','start'],env=cls.env,check=True,capture_output=True)
        try:
            with cls.admin() as db:
                db.execute('CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN; CREATE ROLE service_role NOLOGIN')
                for name in ('20261116050000_history_v2_private.sql','20261118012340_structured_receipts_v2.sql','20261118020000_pp_history_v2_role.sql','20261118031407_pp_structured_receipt_grants.sql','20261119020000_pp_structured_revision_payloads.sql'):
                    db.execute((ROOT/'supabase/migrations'/name).read_text())
                db.execute((ROOT/'supabase/review/pp_trial_20261119_01_structured.sql').read_text())
                db.execute((ROOT/'deploy/preprod/tests/pp_storage_policy_fixture.sql').read_text())
                legacy=(ROOT/'supabase/review/pp_market_raw_storage_policies.sql.in').read_text()
                db.execute(legacy.replace('__PP_STORAGE_AUTH_UID__','00000000-0000-4000-8000-0000000000aa').replace('__PP_STORAGE_AUTH_EMAIL__','pp-storage-archive@example.invalid'))
                for index,(origin,uids) in enumerate(((FIRST,UIDS[:2]),(RETAINED_SECOND,UIDS[2:4]),(THIRD,UIDS[4:6]),(FOURTH,UIDS[6:]))):
                    for uid,kind in zip(uids,('archive','history_reader')):
                        db.execute("INSERT INTO auth.users VALUES(%s,%s,'authenticated',now(),%s::jsonb)",(uid,kind+str(index)+'@example.invalid',json.dumps(dict(tradebot_role='pp_storage_'+kind,tradebot_origin=origin))))
                first=first_render(writer_uid=UIDS[0],writer_email='archive0@example.invalid',reader_uid=UIDS[1],reader_email='history_reader0@example.invalid',policy_sha256=db.execute(HASH).fetchone()[0])
                db.execute(first)
                db.execute((ROOT/'supabase/review/pp_trial_20261119_02_structured.sql').read_text())
                db.execute(second_render(writer_uid=UIDS[2],writer_email='archive1@example.invalid',reader_uid=UIDS[3],reader_email='history_reader1@example.invalid',policy_sha256=db.execute(HASH).fetchone()[0]))
                db.execute((ROOT/'supabase/review/pp_trial_20261119_03_structured.sql').read_text())
                db.execute(third_render(writer_uid=UIDS[4],writer_email='archive2@example.invalid',reader_uid=UIDS[5],reader_email='history_reader2@example.invalid',policy_sha256=db.execute(HASH).fetchone()[0]))
                for origin in (FIRST, RETAINED_SECOND, THIRD, 'pp-live-pp', 'production'):
                    cls.seed(db, origin)
                cls.before={schema:db.execute(CATALOG,(schema,)).fetchall() for schema in ('history_v2','storage')}
                cls.old_roles=db.execute("SELECT rolname,rolcanlogin,rolinherit,rolsuper,rolbypassrls,rolconnlimit FROM pg_roles WHERE rolname ~ '^tradebot_pp_(history$|trial_20261119_0[123]_)' ORDER BY rolname").fetchall()
                cls.old_grants=db.execute("SELECT grantee,table_schema,table_name,privilege_type FROM information_schema.role_table_grants WHERE grantee ~ '^tradebot_pp_(history$|trial_20261119_0[123]_)' ORDER BY 1,2,3,4").fetchall()
                cls.old_auth=db.execute('SELECT * FROM auth.users ORDER BY id').fetchall()
                cls.old_data=db.execute('SELECT * FROM history_v2.generation_checkpoints ORDER BY origin_id').fetchall()
                cls.old_objects=db.execute('SELECT * FROM storage.objects ORDER BY name').fetchall()
                db.execute((ROOT/'supabase/review/pp_trial_20261119_04_structured.sql').read_text())
                cls.bindings=dict(writer_uid=UIDS[6],writer_email='archive3@example.invalid',reader_uid=UIDS[7],reader_email='history_reader3@example.invalid',policy_sha256=db.execute(HASH).fetchone()[0])
                db.execute(render(**cls.bindings))
                cls.seed(db, FOURTH)
        except BaseException:cls.tearDownClass();raise
    @classmethod
    def admin(cls):
        # Never inherit a service, host address, password or options from a
        # developer's libpq environment. This fixture owns only its fresh socket.
        with patch.dict(os.environ,cls.env,clear=True):
            return psycopg.connect(host=str(cls.socket),port=5432,user='postgres',dbname='postgres',
                                   sslmode='disable',passfile=str(cls.passfile),connect_timeout=3)
    @classmethod
    def seed(cls,db,origin):
        db.execute("INSERT INTO history_v2.generation_checkpoints VALUES(%s,%s,'fixture','{}',0,%s,now())",(origin,GEN,'a'*64))
        key='raw-v1/'+sha256(origin.encode()).hexdigest()+'/'+GEN+'/'+'a'*64+'.jsonl.gz'
        db.execute("INSERT INTO storage.objects(bucket_id,name) VALUES('market-raw',%s)",(key,))
    @classmethod
    def tearDownClass(cls):
        subprocess.run([str(cls.bin/'pg_ctl'),'-D',str(cls.root/'data'),'-m','immediate','-w','stop'],env=cls.env,check=True,capture_output=True);cls.temp.cleanup()
    def role(self,db,role):db.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)))
    def request(self,db,uid,operation):
        self.role(db,'authenticated');db.execute("SELECT set_config('request.jwt.claim.sub',%s,true),set_config('storage.operation',%s,true)",(uid,operation))
    def key(self,origin,digest='a'):return 'raw-v1/'+sha256(origin.encode()).hexdigest()+'/'+GEN+'/'+digest*64+'.jsonl.gz'

    def test_display_scope_is_private_and_excludes_existing_origins(self):
        from postgres.cloud_origin_binding import DISPLAY_ORIGIN, DISPLAY_WRITER, DISPLAY_READER
        with self.admin() as db:
            policy=(ROOT/'supabase/review/pp_display_20261127_02_structured.sql').read_text()
            # Exercise the real statements inside the disposable transaction.
            body=policy.split('BEGIN;',1)[1].rsplit('COMMIT;',1)[0]
            db.execute(body)
            self.seed(db,DISPLAY_ORIGIN)
            self.seed(db,'pp-live-pp-display-20261127-01')
            db.execute('CREATE POLICY fixture_public ON history_v2.generation_checkpoints FOR SELECT TO PUBLIC USING(true)')
            for role in (DISPLAY_WRITER,DISPLAY_READER):
                self.role(db,role)
                self.assertEqual(db.execute('SELECT origin_id FROM history_v2.generation_checkpoints').fetchall(),
                                 [(DISPLAY_ORIGIN,)])
                self.assertFalse(db.execute("SELECT has_schema_privilege(current_user,'storage','USAGE')").fetchone()[0])
                self.assertEqual(db.execute("SELECT has_table_privilege(current_user,'history_v2.structured_receipts','INSERT')").fetchone()[0], role==DISPLAY_WRITER)
                db.execute('RESET ROLE')
            db.rollback()

    def test_old_catalog_grants_roles_and_evidence_unchanged(self):
        with self.admin() as db:
            for schema,before in self.before.items():
                after=db.execute(CATALOG,(schema,)).fetchall()
                self.assertEqual([r for r in after if not r[0].startswith('pp_trial_20261119_04_')],before)
            self.assertEqual(db.execute("SELECT rolname,rolcanlogin,rolinherit,rolsuper,rolbypassrls,rolconnlimit FROM pg_roles WHERE rolname ~ '^tradebot_pp_(history$|trial_20261119_0[123]_)' ORDER BY rolname").fetchall(),self.old_roles)
            self.assertEqual(db.execute("SELECT grantee,table_schema,table_name,privilege_type FROM information_schema.role_table_grants WHERE grantee ~ '^tradebot_pp_(history$|trial_20261119_0[123]_)' ORDER BY 1,2,3,4").fetchall(),self.old_grants)
            self.assertEqual(db.execute('SELECT * FROM auth.users ORDER BY id').fetchall(),self.old_auth)
            self.assertEqual(db.execute('SELECT * FROM history_v2.generation_checkpoints WHERE origin_id<>%s ORDER BY origin_id',(FOURTH,)).fetchall(),self.old_data)
            self.assertEqual(db.execute('SELECT * FROM storage.objects WHERE name NOT LIKE %s ORDER BY name',('raw-v1/'+sha256(FOURTH.encode()).hexdigest()+'/%',)).fetchall(),self.old_objects)
            for role,origin in (('tradebot_pp_history','pp-live-pp'),(WRITER,FOURTH),(READER,FOURTH),('tradebot_pp_trial_20261119_03_reader',THIRD),('tradebot_pp_trial_20261119_01_reader',FIRST),('tradebot_pp_trial_20261119_02_reader',RETAINED_SECOND)):
                with db.transaction():
                    self.role(db,role)
                    self.assertEqual(db.execute('SELECT origin_id FROM history_v2.generation_checkpoints').fetchall(),[(origin,)])
                db.execute('RESET ROLE')
            self.assertEqual(db.execute('SELECT count(*) FROM storage.objects').fetchone()[0],6)

    def test_fourth_structured_grants_are_least_privilege_and_fenced(self):
        with self.admin() as db:
            for role,insert,update in ((WRITER,11,3),(READER,0,0)):
                self.assertEqual(db.execute('SELECT rolcanlogin,rolinherit,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication,rolconnlimit FROM pg_roles WHERE rolname=%s',(role,)).fetchone(),(False,False,False,False,False,False,False,2))
                self.assertEqual(db.execute('SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=%s)',(role,)).fetchone()[0],0)
                for privilege,n in (('SELECT',11),('INSERT',insert),('UPDATE',update),('DELETE',0),('TRUNCATE',0)):
                    self.assertEqual(db.execute("SELECT count(*) FROM pg_tables WHERE schemaname='history_v2' AND has_table_privilege(%s,schemaname||'.'||tablename,%s)",(role,privilege)).fetchone()[0],n)
            db.execute('CREATE POLICY fixture_broad ON history_v2.generation_checkpoints FOR SELECT TO PUBLIC USING(true)')
            self.role(db,READER)
            self.assertEqual(db.execute('SELECT origin_id FROM history_v2.generation_checkpoints').fetchall(),[(FOURTH,)])
            db.rollback()
        for role,statement in ((READER,'UPDATE history_v2.generation_checkpoints SET row_count=1'),(WRITER,'DELETE FROM history_v2.generation_checkpoints'),(WRITER,"UPDATE history_v2.generation_checkpoints SET origin_id='pp-live-pp-trial-20261119-01'")):
            with self.admin() as db:
                self.role(db,role)
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):db.execute(statement)
        for role in ('tradebot_pp_history',*(f'tradebot_pp_trial_20261119_0{i}_writer' for i in (1,2,3))):
            with self.admin() as db:
                self.role(db,role)
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    db.execute("INSERT INTO history_v2.generation_checkpoints VALUES(%s,%s,'foreign-write','{}',0,%s,now())",(FOURTH,GEN,'b'*64))

    def test_storage_fourth_and_prior_identities_cannot_cross_prefixes(self):
        for uid,origin in (('00000000-0000-4000-8000-0000000000aa','pp-live-pp'),(UIDS[0],FIRST),(UIDS[1],FIRST),(UIDS[2],RETAINED_SECOND),(UIDS[3],RETAINED_SECOND),(UIDS[4],THIRD),(UIDS[5],THIRD),(UIDS[6],FOURTH),(UIDS[7],FOURTH)):
            with self.admin() as db:
                self.request(db,uid,'storage.object.get_authenticated')
                self.assertEqual(db.execute('SELECT name FROM storage.objects').fetchall(),[(self.key(origin),)])
        for uid,origin,operation in ((UIDS[7],FOURTH,'storage.object.upload'),(UIDS[6],FIRST,'storage.object.upload'),(UIDS[6],RETAINED_SECOND,'storage.object.upload'),(UIDS[6],THIRD,'storage.object.upload'),(UIDS[0],FOURTH,'storage.object.upload'),(UIDS[2],FOURTH,'storage.object.upload'),(UIDS[4],FOURTH,'storage.object.upload'),(UIDS[6],FOURTH,'storage.object.copy')):
            with self.admin() as db:
                self.request(db,uid,operation)
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):db.execute("INSERT INTO storage.objects(bucket_id,name) VALUES('market-raw',%s)",(self.key(origin,'b'),))
        with self.admin() as db:
            self.request(db,UIDS[6],'storage.object.upload')
            db.execute("INSERT INTO storage.objects(bucket_id,name) VALUES('market-raw',%s)",(self.key(FOURTH,'c'),));db.rollback()
        for operation in ('storage.object.list','storage.object.get_public','storage.object.get_signed'):
            with self.admin() as db:
                self.request(db,UIDS[7],operation)
                self.assertEqual(db.execute('SELECT count(*) FROM storage.objects').fetchone()[0],0)
        for statement in ('UPDATE storage.objects SET owner_id=\'changed\'','DELETE FROM storage.objects'):
            with self.admin() as db:
                self.request(db,UIDS[6],'storage.object.upload_update')
                self.assertEqual(db.execute(statement).rowcount,0)
        with self.admin() as db:
            db.execute('CREATE POLICY broad_read ON storage.objects FOR SELECT TO authenticated USING(true)')
            self.request(db,UIDS[7],'storage.object.get_authenticated')
            self.assertEqual(db.execute('SELECT name FROM storage.objects').fetchall(),[(self.key(FOURTH),)])
            db.rollback()

    def test_fresh_identity_guard_rejects_existing_policy_authority(self):
        with self.admin() as db:
            bindings=dict(self.bindings,policy_sha256=db.execute(HASH).fetchone()[0])
            with self.assertRaisesRegex(psycopg.errors.RaiseException,'fresh identities'):
                db.execute(render(**bindings))

    def test_catalog_drift_or_policy_reuse_stops_create_only_templates(self):
        with self.admin() as db:
            with self.assertRaises(psycopg.errors.RaiseException):db.execute(render(**self.bindings))
        with self.admin() as db:
            with self.assertRaises(psycopg.errors.RaiseException):db.execute((ROOT/'supabase/review/pp_trial_20261119_04_structured.sql').read_text())

    def test_fifth_reader_and_writer_are_isolated_from_fourth(self):
        fifth='pp-live-pp-trial-20261119-05'
        writer='00000000-0000-4000-8000-000000000044'
        reader='00000000-0000-4000-8000-000000000055'
        # The reviewed scripts include COMMIT. Run them in the isolated fixture
        # after stripping their outer transaction to roll back this test only.
        def body(script):
            self.assertIn('\nBEGIN;\n',script);self.assertTrue(script.rstrip().endswith('COMMIT;'))
            return script.replace('\nBEGIN;\n','\n',1).rsplit('COMMIT;',1)[0]
        with self.admin() as db:
            for uid,kind in ((writer,'archive'),(reader,'history_reader')):
                db.execute("INSERT INTO auth.users VALUES(%s,%s,'authenticated',now(),%s::jsonb)",
                           (uid,kind+'05@example.invalid',
                            json.dumps(dict(tradebot_role='pp_storage_'+kind,tradebot_origin=fifth))))
            db.execute(body((ROOT/'supabase/review/pp_trial_20261119_05_structured.sql').read_text()))
            db.execute(body(fifth_render(writer_uid=writer,writer_email='archive05@example.invalid',
                       reader_uid=reader,reader_email='history_reader05@example.invalid',
                       policy_sha256=db.execute(HASH).fetchone()[0])))
            self.seed(db,fifth)
            for role,origin in ((READER,FOURTH),('tradebot_pp_trial_20261119_05_reader',fifth),
                                ('tradebot_pp_trial_20261119_05_writer',fifth)):
                self.role(db,role)
                self.assertEqual(db.execute('SELECT origin_id FROM history_v2.generation_checkpoints').fetchall(),[(origin,)])
                db.execute('RESET ROLE')
            for uid,origin in ((UIDS[7],FOURTH),(reader,fifth),(writer,fifth)):
                self.request(db,uid,'storage.object.get_authenticated')
                self.assertEqual(db.execute('SELECT name FROM storage.objects').fetchall(),[(self.key(origin),)])
                db.execute('RESET ROLE')
            self.request(db,writer,'storage.object.upload')
            with self.assertRaises(psycopg.errors.InsufficientPrivilege), db.transaction():
                db.execute("INSERT INTO storage.objects(bucket_id,name) VALUES('market-raw',%s)",(self.key(FOURTH,'b'),))
            db.rollback()


if __name__=='__main__':unittest.main()
