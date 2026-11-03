"""Tiny phase/resource checks; the full4000 profile runs once after exact CI."""
import json,multiprocessing,sys,tempfile,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'prototype'))
from qualify_application import lifecycle_process,workspace_bytes
from raw_generations import iso
from test_ab_application import legacy,ApplicationStore,T
from datetime import timedelta
class Tests(unittest.TestCase):
    def test_fresh_spawn_lifecycle_preparation_and_finish_use_one_deadline(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as f:
            p=Path(f);legacy(p/'generated-legacy.db');s=ApplicationStore(p,p/'generated-legacy.db',routing=True);db=s.connection()
            try:db.save_observation('m',iso(T+timedelta(seconds=2)),'book',{'exact':'0.00000001'},iso(T))
            finally:db.close()
            ctx=multiprocessing.get_context('spawn');start=ctx.Event();finish=ctx.Event();start.set();finish.set()
            child=ctx.Process(target=lifecycle_process,args=(f,time.monotonic()+8,start,finish,str(p/'report.json')))
            try:
                child.start();child.join(9)
                if child.is_alive():child.kill();child.join();self.fail('tiny lifecycle child exceeded original deadline')
                self.assertEqual(child.exitcode,0)
                result=json.loads((p/'report.json').read_text());self.assertEqual(result['status'],'PASS',result)
                self.assertEqual(len(result['cycles']),2);self.assertGreater(workspace_bytes(p),0)
            finally:s.close()
    def test_export_source_is_in_whole_workspace_accounting(self):
        with tempfile.TemporaryDirectory() as f:
            p=Path(f);(p/'candidate').mkdir();(p/'candidate/source.py').write_bytes(b'x'*1024)
            (p/'generated-ab-fixture').mkdir();(p/'generated-ab-fixture/state').write_bytes(b'y'*2048)
            self.assertEqual(workspace_bytes(p),3072)
    def test_absolute_supervisor_kills_and_reaps_ignoring_child(self):
        from run_application_qualification import supervise
        import os
        with tempfile.TemporaryDirectory() as f:
            report=Path(f)/'report.json';pidfile=Path(f)/'pid'
            code="import os,time,signal,pathlib;signal.signal(signal.SIGTERM,signal.SIG_IGN);pathlib.Path("+repr(str(pidfile))+").write_text(str(os.getpid()));time.sleep(10)"
            start=time.monotonic();result=supervise([sys.executable,'-c',code],report,.15)
            self.assertEqual(result,1);self.assertLess(time.monotonic()-start,1)
            with self.assertRaises(ProcessLookupError):os.kill(int(pidfile.read_text()),0)
            self.assertEqual(json.loads(report.read_text())['status'],'FAIL')
    def test_preparation_budget_is_not_reset_before_child_launch(self):
        from run_application_qualification import supervise
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as f,patch.dict('os.environ',{'AB_PROFILE_STARTED':str(time.monotonic()-200)}),patch('run_application_qualification.subprocess.Popen') as launch:
            report=Path(f)/'report.json';self.assertEqual(supervise(['never-run'],report),1);launch.assert_not_called()
            self.assertEqual(json.loads(report.read_text())['error'],'original budget expired before launch')
    def test_workspace_report_and_production_paths_fail_closed(self):
        from qualify_application import validate_workspace
        with tempfile.TemporaryDirectory(prefix='ab-integration-') as f:
            root=Path(f);self.assertEqual(validate_workspace(root,root/'new-report.json'),root.resolve())
            with self.assertRaises(ValueError):validate_workspace(root,root.parent/'outside-report.json')
            (root/'existing').write_text('retained')
            with self.assertRaises(ValueError):validate_workspace(root,root/'existing')
        with self.assertRaises(ValueError):validate_workspace('/opt/tradebot','/opt/tradebot/report')
    @unittest.skipUnless(Path('/proc/self/fd').exists(),'Linux process-family unlinked TEMP descriptor accounting')
    def test_unlinked_non_database_temp_in_child_counts_toward_workspace(self):
        import subprocess
        with tempfile.TemporaryDirectory() as f:
            code="import tempfile,time; f=tempfile.TemporaryFile(dir="+repr(f)+"); f.write(b'x'*65536); f.flush(); print('ready',flush=True); time.sleep(10)"
            child=subprocess.Popen([sys.executable,'-c',code],stdout=subprocess.PIPE,text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(),'ready')
                self.assertGreaterEqual(workspace_bytes(f),65536)
            finally:child.kill();child.wait();child.stdout.close()
