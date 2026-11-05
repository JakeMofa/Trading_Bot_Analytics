"""Selected recovery preserves exact legacy values; production paths stay held."""
from contextlib import closing
import hashlib,json,sqlite3,sys,tempfile,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_ab_application import legacy
from selected_recovery import verify,stage,RecoveryHold

class Tests(unittest.TestCase):
    def fixture(self,root):
        source=root/'generated-legacy-source.db';legacy(source)
        with closing(sqlite3.connect(source)) as db:
            sid,version,market,at,ev,vs=db.execute('SELECT id,version,market_id,as_of,evidence_json,values_json FROM feature_snapshots').fetchone()
            e=json.loads(ev);v=json.loads(vs);price=e['price']
        refs={'format':'AB72_SELECTED_DEPENDENCIES_V1','missing_observations':[41],'missing_stream_events':['7'],
              'snapshots':[[sid,version,market,at,41,e['metadata_received_at'],v['target_usd'],'7',price['source_time'],v['reference_price_usd']]],'predictions':[[1,sid,market]],'legacy_binding':{'generated':True}}
        path=root/'dependencies.json';path.write_text(json.dumps(refs))
        return source,path
    def verified(self,source,refs):
        return verify(source,refs,hashlib.sha256(source.read_bytes()).hexdigest(),hashlib.sha256(refs.read_bytes()).hexdigest(),time.monotonic()+10)
    def test_exact_stage_retry_and_conflict_hold(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-recovery-') as folder:
            root=Path(folder);s,r=self.fixture(root);v=self.verified(s,r)
            first=stage(root,v,time.monotonic()+10);self.assertGreater(first['changed_rows'],0)
            self.assertEqual(stage(root,v,time.monotonic()+10)['changed_rows'],0)
            with closing(sqlite3.connect(root/'staged-core.db')) as db:
                db.execute("UPDATE observations SET payload='{}' WHERE id=41");db.commit()
            with self.assertRaisesRegex(RecoveryHold,'conflict'):stage(root,v,time.monotonic()+10)
            self.assertTrue((root/'staged-core.db').exists())
    def test_crash_boundary_rolls_back_all_selected_rows(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-recovery-') as folder:
            root=Path(folder);s,r=self.fixture(root);v=self.verified(s,r)
            def crash(i):raise RuntimeError('injected crash before commit')
            with self.assertRaisesRegex(RuntimeError,'injected'):stage(root,v,time.monotonic()+10,crash)
            with closing(sqlite3.connect(root/'staged-core.db')) as db:self.assertEqual(db.execute('SELECT count(*) FROM recovery_records').fetchone()[0],0)
            self.assertEqual(stage(root,v,time.monotonic()+10)['records'],2)
    def test_missing_malformed_conflicting_and_duplicate_dependencies(self):
        for fault in ('missing','timestamp','price','prediction','duplicate','unsupported'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory(prefix='generated-ab-recovery-') as folder:
                root=Path(folder);s,r=self.fixture(root);d=json.loads(r.read_text())
                if fault=='missing':
                    with closing(sqlite3.connect(s)) as db,db:db.execute('DELETE FROM observations WHERE id=41')
                elif fault=='timestamp':d['snapshots'][0][5]='2026-01-01'
                elif fault=='price':d['snapshots'][0][9]='0.000000000000001'
                elif fault=='prediction':d['predictions'][0][2]='different-market'
                elif fault=='duplicate':d['missing_observations'].append(41)
                else:d['snapshots'][0][1]=99
                r.write_text(json.dumps(d))
                with self.assertRaises((RecoveryHold,ValueError)):self.verified(s,r)
    def test_hash_source_schema_and_production_path_holds(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-recovery-') as folder:
            root=Path(folder);s,r=self.fixture(root)
            with self.assertRaisesRegex(RecoveryHold,'hash mismatch'):verify(s,r,'0'*64,'0'*64,time.monotonic()+10)
            v=self.verified(s,r)
            with self.assertRaisesRegex(RecoveryHold,'isolated'):stage('/opt/tradebot',v,time.monotonic()+10)
            v[1][('observations','41')]['payload']='{}'
            with self.assertRaisesRegex(RecoveryHold,'selection changed'):stage(root,v,time.monotonic()+10)
            with closing(sqlite3.connect(s)) as db,db:db.execute('PRAGMA user_version=99')
            with self.assertRaisesRegex(ValueError,'user_version'):self.verified(s,r)

    def test_committed_stage_survives_post_commit_crash_and_open_reader(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-recovery-') as folder:
            root=Path(folder);s,r=self.fixture(root);v=self.verified(s,r)
            def after(phase):
                if phase=='after_commit':raise RuntimeError('post commit crash')
            with self.assertRaisesRegex(RuntimeError,'post commit'):stage(root,v,time.monotonic()+10,after)
            with closing(sqlite3.connect(root/'staged-core.db')) as reader:
                reader.execute('BEGIN');self.assertEqual(reader.execute('SELECT count(*) FROM recovery_records').fetchone()[0],2)
                self.assertEqual(stage(root,v,time.monotonic()+10)['changed_rows'],0)
                reader.rollback()
    def test_resource_deadline_and_extra_identity_hold_preserve_files(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-recovery-') as folder:
            root=Path(folder);s,r=self.fixture(root);v=self.verified(s,r)
            def disk():raise sqlite3.OperationalError('database or disk is full')
            with self.assertRaisesRegex(sqlite3.OperationalError,'disk is full'):stage(root,v,time.monotonic()+10,guard=disk)
            with self.assertRaises(TimeoutError):stage(root,v,time.monotonic()-1)
            self.assertEqual(stage(root,v,time.monotonic()+10)['records'],2)
            with closing(sqlite3.connect(root/'staged-core.db')) as db,db:
                db.execute("INSERT INTO recovery_records VALUES('observations','999','{}','invalid')")
            with self.assertRaisesRegex(RecoveryHold,'membership'):stage(root,v,time.monotonic()+10)
            self.assertTrue(s.exists());self.assertTrue((root/'staged-core.db').exists())
    def test_invalid_source_foreign_keys_and_changed_dependency_hash(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-recovery-') as folder:
            root=Path(folder);s,r=self.fixture(root)
            with self.assertRaisesRegex(RecoveryHold,'dependency manifest hash'):
                verify(s,r,hashlib.sha256(s.read_bytes()).hexdigest(),'0'*64,time.monotonic()+10)
            with closing(sqlite3.connect(s)) as db,db:db.execute('DELETE FROM observations WHERE id=90')
            with self.assertRaisesRegex(RecoveryHold,'foreign key'):self.verified(s,r)

    def test_export_launcher_cannot_import_checkout(self):
        import shutil,subprocess,os
        with tempfile.TemporaryDirectory(prefix='generated-ab-recovery-') as folder,tempfile.TemporaryDirectory() as empty:
            root=Path(folder);s,r=self.fixture(root);bundle=root/'export';prototype=bundle/'backend/prototype';prototype.mkdir(parents=True)
            backend=Path(__file__).resolve().parents[1]
            for name in ('run_selected_recovery','selected_recovery','raw_generations','application_validation','run_application_qualification'):
                shutil.copyfile(backend/'prototype'/(name+'.py'),prototype/(name+'.py'))
            app=bundle/'backend/app';app.mkdir()
            for module in (backend/'app').glob('*.py'):shutil.copyfile(module,app/module.name)
            shutil.copyfile(backend/'build_ab_candidate.py',bundle/'backend/build_ab_candidate.py')
            manifest={'source_sha':'0'*40,'files':{}}
            for f in bundle.rglob('*.py'):
                manifest['files'][str(f.relative_to(bundle))]={'mode':'100644','bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}
            (bundle/'AB_CANDIDATE_MANIFEST.json').write_text(json.dumps(manifest))
            stage_root=root/'generated-ab-recovery-isolated';stage_root.mkdir(mode=0o700)
            report=stage_root/'qualification-report.json'
            args=[sys.executable,str(prototype/'run_selected_recovery.py'),'--source',str(s),'--dependencies',str(r),'--source-hash',hashlib.sha256(s.read_bytes()).hexdigest(),'--dependency-hash',hashlib.sha256(r.read_bytes()).hexdigest(),'--root',str(stage_root),'--report',str(report),'--sha','0'*40]
            env=dict(os.environ,PYTHONPATH='',PYTHONDONTWRITEBYTECODE='1')
            result=subprocess.run(args,cwd=empty,env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(json.loads(report.read_text())['retry_stage']['changed_rows'],0)
