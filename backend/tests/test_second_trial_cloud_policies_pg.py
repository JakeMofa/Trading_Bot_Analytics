"""Second exact trial policy proof in an owned socket-only PG17 cluster."""
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

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'deploy/preprod'))
import psycopg
from psycopg import sql
from bind_trial_cloud_policy import render as first_render
from bind_second_trial_cloud_policy import render

FIRST='pp-live-pp-trial-20261119-01'
SECOND='pp-live-pp-trial-20261119-02'
WRITER='tradebot_pp_trial_20261119_02_writer'
READER='tradebot_pp_trial_20261119_02_reader'
GEN='00000000-0000-4000-8000-000000000001'
UIDS=['00000000-0000-4000-8000-0000000000'+suffix for suffix in ('bb','cc','dd','ee')]
CATALOG="SELECT policyname,tablename,roles,cmd,qual,with_check FROM pg_policies WHERE schemaname=%s ORDER BY tablename,policyname"
HASH="""SELECT encode(sha256(convert_to(COALESCE(jsonb_agg(to_jsonb(p) ORDER BY p.policyname),'[]'::jsonb)::text,'UTF8')),'hex')
FROM pg_policies p WHERE schemaname='storage' AND tablename='objects'"""


class SecondTrialPolicyPGTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        choices=[os.getenv('TRADEBOT_TEST_PG17_BIN'),'/opt/homebrew/opt/postgresql@17/bin',str(Path(shutil.which('psql') or '/missing').parent)]
        cls.bin=next((Path(p) for p in choices if p and all((Path(p)/n).is_file() for n in ('initdb','pg_ctl','psql'))),None)
        if cls.bin is None:raise unittest.SkipTest('native PG17 unavailable')
        if ' 17.' not in subprocess.run([str(cls.bin/'psql'),'--version'],check=True,capture_output=True,text=True).stdout:
            raise unittest.SkipTest('native PG17 required')
        cls.temp=tempfile.TemporaryDirectory(prefix='second-trial-policy-',dir='/tmp');cls.root=Path(cls.temp.name)
        cls.socket=cls.root/'socket';cls.socket.mkdir();cls.env={k:v for k,v in os.environ.items() if not k.startswith('PG')}
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
                for index,(origin,uids) in enumerate(((FIRST,UIDS[:2]),(SECOND,UIDS[2:]))):
                    for uid,kind in zip(uids,('archive','history_reader')):
                        db.execute("INSERT INTO auth.users VALUES(%s,%s,'authenticated',now(),%s::jsonb)",(uid,kind+str(index)+'@example.invalid',json.dumps(dict(tradebot_role='pp_storage_'+kind,tradebot_origin=origin))))
                first=first_render(writer_uid=UIDS[0],writer_email='archive0@example.invalid',reader_uid=UIDS[1],reader_email='history_reader0@example.invalid',policy_sha256=db.execute(HASH).fetchone()[0])
                db.execute(first)
                cls.before={schema:db.execute(CATALOG,(schema,)).fetchall() for schema in ('history_v2','storage')}
                cls.old_roles=db.execute("SELECT rolname,rolcanlogin,rolinherit,rolsuper,rolbypassrls,rolconnlimit FROM pg_roles WHERE rolname LIKE 'tradebot_pp_trial_20261119_01_%' ORDER BY rolname").fetchall()
                cls.old_grants=db.execute("SELECT grantee,table_schema,table_name,privilege_type FROM information_schema.role_table_grants WHERE grantee LIKE 'tradebot_pp_trial_20261119_01_%' ORDER BY 1,2,3,4").fetchall()
                db.execute((ROOT/'supabase/review/pp_trial_20261119_02_structured.sql').read_text())
                cls.bindings=dict(writer_uid=UIDS[2],writer_email='archive1@example.invalid',reader_uid=UIDS[3],reader_email='history_reader1@example.invalid',policy_sha256=db.execute(HASH).fetchone()[0])
                db.execute(render(**cls.bindings))
                for origin in (FIRST,SECOND,'pp-live-pp','production'):
                    db.execute("INSERT INTO history_v2.generation_checkpoints VALUES(%s,%s,'fixture','{}',0,%s,now())",(origin,GEN,'a'*64))
                    key='raw-v1/'+sha256(origin.encode()).hexdigest()+'/'+GEN+'/'+'a'*64+'.jsonl.gz'
                    db.execute("INSERT INTO storage.objects(bucket_id,name) VALUES('market-raw',%s)",(key,))
        except BaseException:cls.tearDownClass();raise
    @classmethod
    def admin(cls):return psycopg.connect(host=str(cls.socket),user='postgres',dbname='postgres')
    @classmethod
    def tearDownClass(cls):
        subprocess.run([str(cls.bin/'pg_ctl'),'-D',str(cls.root/'data'),'-m','immediate','-w','stop'],env=cls.env,check=True,capture_output=True);cls.temp.cleanup()
    def role(self,db,role):db.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)))
    def request(self,db,uid,operation):
        self.role(db,'authenticated');db.execute("SELECT set_config('request.jwt.claim.sub',%s,true),set_config('storage.operation',%s,true)",(uid,operation))
    def key(self,origin,digest='a'):return 'raw-v1/'+sha256(origin.encode()).hexdigest()+'/'+GEN+'/'+digest*64+'.jsonl.gz'

    def test_old_catalog_grants_roles_and_evidence_unchanged(self):
        with self.admin() as db:
            for schema,before in self.before.items():
                after=db.execute(CATALOG,(schema,)).fetchall()
                self.assertEqual([r for r in after if not r[0].startswith('pp_trial_20261119_02_')],before)
            self.assertEqual(db.execute("SELECT rolname,rolcanlogin,rolinherit,rolsuper,rolbypassrls,rolconnlimit FROM pg_roles WHERE rolname LIKE 'tradebot_pp_trial_20261119_01_%' ORDER BY rolname").fetchall(),self.old_roles)
            self.assertEqual(db.execute("SELECT grantee,table_schema,table_name,privilege_type FROM information_schema.role_table_grants WHERE grantee LIKE 'tradebot_pp_trial_20261119_01_%' ORDER BY 1,2,3,4").fetchall(),self.old_grants)
            for role,origin in ((WRITER,SECOND),(READER,SECOND),('tradebot_pp_trial_20261119_01_reader',FIRST)):
                with db.transaction():
                    self.role(db,role)
                    self.assertEqual(db.execute('SELECT origin_id FROM history_v2.generation_checkpoints').fetchall(),[(origin,)])
                db.execute('RESET ROLE')
            self.assertEqual(db.execute('SELECT count(*) FROM storage.objects').fetchone()[0],4)

    def test_second_structured_grants_are_least_privilege_and_fenced(self):
        with self.admin() as db:
            for role,insert,update in ((WRITER,11,3),(READER,0,0)):
                self.assertEqual(db.execute('SELECT rolcanlogin,rolinherit,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication,rolconnlimit FROM pg_roles WHERE rolname=%s',(role,)).fetchone(),(False,False,False,False,False,False,False,2))
                self.assertEqual(db.execute('SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=%s)',(role,)).fetchone()[0],0)
                for privilege,n in (('SELECT',11),('INSERT',insert),('UPDATE',update),('DELETE',0),('TRUNCATE',0)):
                    self.assertEqual(db.execute("SELECT count(*) FROM pg_tables WHERE schemaname='history_v2' AND has_table_privilege(%s,schemaname||'.'||tablename,%s)",(role,privilege)).fetchone()[0],n)
            db.execute('CREATE POLICY fixture_broad ON history_v2.generation_checkpoints FOR SELECT TO PUBLIC USING(true)')
            self.role(db,READER)
            self.assertEqual(db.execute('SELECT origin_id FROM history_v2.generation_checkpoints').fetchall(),[(SECOND,)])
        for role,statement in ((READER,'UPDATE history_v2.generation_checkpoints SET row_count=1'),(WRITER,'DELETE FROM history_v2.generation_checkpoints'),(WRITER,"UPDATE history_v2.generation_checkpoints SET origin_id='pp-live-pp-trial-20261119-01'")):
            with self.admin() as db:
                self.role(db,role)
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):db.execute(statement)

    def test_storage_second_and_first_identities_cannot_cross_prefixes(self):
        for uid,origin in (('00000000-0000-4000-8000-0000000000aa','pp-live-pp'),(UIDS[0],FIRST),(UIDS[1],FIRST),(UIDS[2],SECOND),(UIDS[3],SECOND)):
            with self.admin() as db:
                self.request(db,uid,'storage.object.get_authenticated')
                self.assertEqual(db.execute('SELECT name FROM storage.objects').fetchall(),[(self.key(origin),)])
        for uid,origin,operation in ((UIDS[3],SECOND,'storage.object.upload'),(UIDS[2],FIRST,'storage.object.upload'),(UIDS[2],SECOND,'storage.object.copy')):
            with self.admin() as db:
                self.request(db,uid,operation)
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):db.execute("INSERT INTO storage.objects(bucket_id,name) VALUES('market-raw',%s)",(self.key(origin,'b'),))
        with self.admin() as db:
            self.request(db,UIDS[2],'storage.object.upload')
            db.execute("INSERT INTO storage.objects(bucket_id,name) VALUES('market-raw',%s)",(self.key(SECOND,'c'),));db.rollback()
        for operation in ('storage.object.list','storage.object.get_public','storage.object.get_signed'):
            with self.admin() as db:
                self.request(db,UIDS[3],operation)
                self.assertEqual(db.execute('SELECT count(*) FROM storage.objects').fetchone()[0],0)
        for statement in ('UPDATE storage.objects SET owner_id=\'changed\'','DELETE FROM storage.objects'):
            with self.admin() as db:
                self.request(db,UIDS[2],'storage.object.upload_update')
                self.assertEqual(db.execute(statement).rowcount,0)
        with self.admin() as db:
            db.execute('CREATE POLICY broad_read ON storage.objects FOR SELECT TO authenticated USING(true)')
            self.request(db,UIDS[3],'storage.object.get_authenticated')
            self.assertEqual(db.execute('SELECT name FROM storage.objects').fetchall(),[(self.key(SECOND),)])

    def test_fresh_identity_guard_rejects_existing_policy_authority(self):
        with self.admin() as db:
            bindings=dict(self.bindings,policy_sha256=db.execute(HASH).fetchone()[0])
            with self.assertRaisesRegex(psycopg.errors.RaiseException,'fresh identities'):
                db.execute(render(**bindings))

    def test_catalog_drift_or_policy_reuse_stops_create_only_templates(self):
        with self.admin() as db:
            with self.assertRaises(psycopg.errors.RaiseException):db.execute(render(**self.bindings))
        with self.admin() as db:
            with self.assertRaises(psycopg.errors.RaiseException):db.execute((ROOT/'supabase/review/pp_trial_20261119_02_structured.sql').read_text())


if __name__=='__main__':unittest.main()
