"""Linux harness self-test uses tiny generated data, not a production R5 pass."""
import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import unittest
import tempfile


class QualificationHarnessTests(unittest.TestCase):
    def test_checkpoint_experiment_is_private_generated_only_and_keeps_full_durability(self):
        import sqlite3
        from contextlib import closing
        backend=Path(__file__).resolve().parents[1]
        spec=importlib.util.spec_from_file_location('qualification_checkpoint',backend/'qualify_retention_sql.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(prefix='generated-retention-') as folder:
            path=Path(folder)/'fixture.db'
            with closing(sqlite3.connect(path)) as db:
                db.execute('PRAGMA journal_mode=WAL')
                self.assertEqual(db.execute('PRAGMA synchronous').fetchone()[0],2)
                module.configure_fixture_checkpoint(db,path,256)
                self.assertEqual(db.execute('PRAGMA wal_autocheckpoint').fetchone()[0],256)
                self.assertEqual(db.execute('PRAGMA synchronous').fetchone()[0],2)
                with self.assertRaises(ValueError):module.configure_fixture_checkpoint(db,Path('/opt/tradebot/data/btc_intelligence.db'),256)
                with self.assertRaises(ValueError):module.configure_fixture_checkpoint(db,path,512)
                db.execute('BEGIN')
                with self.assertRaises(ValueError):module.configure_fixture_checkpoint(db,path,256)
                db.rollback()
                db.execute('PRAGMA synchronous=NORMAL')
                with self.assertRaises(ValueError):module.configure_fixture_checkpoint(db,path,256)
            with closing(sqlite3.connect(':memory:')) as other:
                with self.assertRaises(ValueError):module.configure_fixture_checkpoint(other,path,256)

    def test_production_guard_identifies_feed_or_collector_without_raw_body(self):
        from datetime import datetime,timezone
        backend=Path(__file__).resolve().parents[1]
        spec=importlib.util.spec_from_file_location('qualification_projection',backend/'qualify_retention_sql.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        now=datetime(2026,10,31,tzinfo=timezone.utc)
        health={'collector':{'running':True},'feeds':{name:{'status':'live','last_data_at':now.isoformat()}
                for name in ('coinbase_stream','polymarket_stream')},'private_fixture':'must not escape'}
        self.assertTrue(module.require_production_health(health,now)['collector_running'])
        health['feeds']['polymarket_stream']['status']='stale'
        with self.assertRaises(module.ProductionGuardStop) as caught:
            module.require_production_health(health,now)
        self.assertEqual(caught.exception.reason,'production_feed_not_fresh_live:polymarket_stream')
        self.assertNotIn('private_fixture',caught.exception.projection)
        health['collector']['running']=False
        with self.assertRaises(module.ProductionGuardStop) as caught:
            module.require_production_health(health,now)
        self.assertEqual(caught.exception.reason,'production_collector_stopped')

    def test_provisional_progress_is_atomic_and_never_reports_pass(self):
        import time
        backend=Path(__file__).resolve().parents[1]
        spec=importlib.util.spec_from_file_location('qualification_progress',backend/'qualify_retention_sql.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'trial.json'
            original={'status':'PASS','stage':'committed_batch','partial_apply':{'committed':1000}}
            module.write_progress_report(path,original,[],time.monotonic())
            saved=json.loads(path.read_text())
            self.assertEqual(saved['status'],'STOP');self.assertTrue(saved['incomplete'])
            self.assertEqual(saved['partial_apply']['committed'],1000)
            self.assertEqual(original['status'],'PASS')
            self.assertFalse(path.with_suffix('.pending').exists())

    def test_actor_rejects_existing_production_paths_and_symlinks(self):
        backend=Path(__file__).resolve().parents[1]
        spec=importlib.util.spec_from_file_location('qualification_guard',backend/'qualify_retention_sql.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(prefix='generated-retention-') as folder:
            path=Path(folder)/'fixture.db';path.touch()
            module.validate_fixture_path(path)
            with self.assertRaises(ValueError):module.validate_fixture_path(Path('/opt/tradebot/data/btc_intelligence.db'))
            with self.assertRaises(ValueError):module.validate_fixture_path(Path(folder)/'other.db')
            path.unlink();path.symlink_to('/opt/tradebot/data/btc_intelligence.db')
            with self.assertRaises(ValueError):module.validate_fixture_path(path)

    def test_unreaped_fixture_is_reported_and_not_unlinked(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        backend=Path(__file__).resolve().parents[1]
        spec=importlib.util.spec_from_file_location('qualification_reap_failure',backend/'qualify_retention_sql.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            args=SimpleNamespace(work_dir=Path(folder),candidate=backend/'app/retention.py',
                deployed_app=backend/'app',observations=100,stream_events=100,
                expected_save_sha256=None,check_production=False,require_native=False,require_indexed=False,batch_size=500,fixture_autocheckpoint_pages=256)
            with patch.object(module,'bounded_process',side_effect=module.FixtureReapError(12345)) as process:
                result=module.supervised_trial(args,1)
            command=process.call_args.args[0]
            self.assertEqual(command[command.index('--batch-size')+1],'500')
            self.assertEqual(command[command.index('--fixture-autocheckpoint-pages')+1],'256')
            self.assertEqual(result['status'],'STOP');self.assertEqual(result['fixture_pid'],12345)
            retained=Path(result['retained_generated_container'])
            self.assertEqual(retained.parent,Path(folder));self.assertTrue(retained.is_dir())

    @unittest.skipUnless(sys.platform=='linux','Linux process-group supervisor')
    def test_supervisor_terminates_and_reaps_ignoring_child(self):
        backend=Path(__file__).resolve().parents[1]
        spec=importlib.util.spec_from_file_location('qualification_supervisor',backend/'qualify_retention_sql.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        import time
        started=time.monotonic()
        code,stdout,stderr,timed_out=module.bounded_process([sys.executable,'-c',
            'import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);print("ready",flush=True);time.sleep(60)'],work_seconds=1.0)
        self.assertTrue(timed_out);self.assertLess(code,0)
        self.assertIn('ready',stdout);self.assertLess(time.monotonic()-started,3)

    @unittest.skipUnless(sys.platform=='linux','Linux qualification harness')
    def test_three_tiny_complete_trials_and_actual_save_ordering(self):
        backend=Path(__file__).resolve().parents[1]
        result=subprocess.run([sys.executable,str(backend/'qualify_retention_sql.py'),
            '--deployed-app',str(backend/'app'),'--candidate',str(backend/'app/retention.py'),
            '--observations','100','--stream-events','100'],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        rows=[json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(rows),3)
        one=subprocess.run([sys.executable,str(backend/'qualify_retention_sql.py'),
            '--deployed-app',str(backend/'app'),'--candidate',str(backend/'app/retention.py'),
            '--observations','100','--stream-events','100','--trials','1','--require-indexed',
            '--trade-id-base','1000000000','--batch-size','500','--fixture-autocheckpoint-pages','256'],capture_output=True,text=True,timeout=10)
        self.assertEqual(one.returncode,0,one.stdout+one.stderr)
        self.assertEqual(len(one.stdout.splitlines()),1)
        indexed=json.loads(one.stdout);self.assertEqual(indexed['timestamp_engine'],'indexed_invalid_v1')
        self.assertEqual(indexed['trade_id_base'],1000000000)
        self.assertEqual(indexed['batch_size'],500)
        self.assertEqual(indexed['sqlite_settings']['wal_autocheckpoint'],256)
        self.assertEqual(indexed['sqlite_settings']['synchronous'],2)
        self.assertEqual(indexed['sqlite_settings_before_experiment']['wal_autocheckpoint'],1000)
        self.assertEqual(indexed['apply']['datasets']['stream_events']['deleted_rows'],99)
        for row in rows:
            self.assertEqual(row['status'],'PASS',row)
            self.assertEqual(row['collector']['saves'],row['collector']['ram_updates'])
            self.assertLess(row['max_write_lock_seconds'],.5)


if __name__=='__main__':unittest.main()
