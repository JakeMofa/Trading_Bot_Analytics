"""Generated SQLite only: durable phase boundaries, timeout and owned reaping."""
import importlib.util,json,os
from pathlib import Path
import signal,sqlite3,subprocess,sys,tempfile,time,unittest
from types import SimpleNamespace
from unittest.mock import patch,Mock
import release_verification as v
import maintenance_host as h

class ProgressTests(unittest.TestCase):
    def fixture(self,folder,broken=False):
        p=Path(folder)/'generated.db'
        with sqlite3.connect(p) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('CREATE TABLE p(id PRIMARY KEY);CREATE TABLE c(id REFERENCES p(id));')
            if broken:db.execute('INSERT INTO c VALUES(7)')
        return p
    def test_success_is_complete_atomic_private_and_read_only(self):
        self.assertEqual(v.POLICY['work_seconds'],1800)
        self.assertEqual(v.POLICY['storage_reserve_mb'],512)
        self.assertEqual(h.POLICY['headroom_mib'],128)
        self.assertEqual(h.controller.INTERRUPTION,2590)
        with tempfile.TemporaryDirectory() as folder:
            p=self.fixture(folder);before=p.read_bytes();report=Path(folder)/'progress.json'
            r=v.check_database(p,3,report);d=v.read_verification_progress(report,os.getpid())
            self.assertEqual(r['status'],'PASS');self.assertEqual(d['status'],'PASS');self.assertIsNone(d['active_check'])
            self.assertEqual([c['check'] for c in d['checks']],['quick_check','foreign_key_check'])
            self.assertEqual(report.stat().st_mode&0o777,0o600);self.assertEqual(p.read_bytes(),before)
            self.assertEqual(list(Path(folder).glob('*.pending-*')),[])
    def test_first_and_second_check_timeout_keep_exact_phase(self):
        for failed,completed in [('quick_check',[]),('foreign_key_check',['quick_check'])]:
            with self.subTest(failed=failed),tempfile.TemporaryDirectory() as folder:
                p=self.fixture(folder);report=Path(folder)/'progress.json';connect=sqlite3.connect
                class Connection:
                    def __init__(self,*a,**kw):self.db=connect(*a,**kw)
                    def __getattr__(self,name):return getattr(self.db,name)
                    def execute(self,sql,*a):
                        if sql=='PRAGMA '+failed:raise TimeoutError('generated-only controlled deadline')
                        return self.db.execute(sql,*a)
                with patch.object(v.sqlite3,'connect',Connection),self.assertRaises(TimeoutError):v.check_database(p,3,report)
                d=v.read_verification_progress(report,os.getpid())
                self.assertEqual(d['active_check'],failed);self.assertEqual([c['check'] for c in d['checks']],completed)
                self.assertEqual(d['status'],'STOP');self.assertGreaterEqual(d['elapsed_seconds'],0)
    def test_invalid_result_and_atomic_partial_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            p=self.fixture(folder,True);report=Path(folder)/'progress.json'
            with self.assertRaises(v.Stop):v.check_database(p,3,report)
            d=v.read_verification_progress(report,os.getpid());self.assertEqual(d['active_check'],'foreign_key_check');self.assertEqual(len(d['checks']),1)
            original=report.read_bytes()
            with patch.object(v.os,'replace',side_effect=OSError('generated-only fault')),self.assertRaises(OSError):v.write_verification_progress(report,{'format':1})
            self.assertEqual(report.read_bytes(),original)
            self.assertEqual(v.read_verification_progress(report,os.getpid()+1)['status'],'UNAVAILABLE')
            report.write_text('truncated');self.assertEqual(v.read_verification_progress(report,os.getpid())['status'],'UNAVAILABLE')
    def test_interruption_preserves_active_check(self):
        with tempfile.TemporaryDirectory() as folder:
            p=self.fixture(folder);report=Path(folder)/'progress.json';connect=sqlite3.connect
            class Connection:
                def __init__(self,*a,**kw):self.db=connect(*a,**kw)
                def __getattr__(self,n):return getattr(self.db,n)
                def execute(self,sql,*a):
                    if sql=='PRAGMA foreign_key_check':raise KeyboardInterrupt()
                    return self.db.execute(sql,*a)
            with patch.object(v.sqlite3,'connect',Connection),self.assertRaises(KeyboardInterrupt):v.check_database(p,3,report)
            d=v.read_verification_progress(report,os.getpid());self.assertEqual(d['error_type'],'KeyboardInterrupt');self.assertEqual(d['active_check'],'foreign_key_check');self.assertEqual(len(d['checks']),1)
    def test_parent_timeout_reaps_and_recovers_persisted_partial(self):
        # Real owned process writes a phase marker, then sleeps. No DB scan.
        with tempfile.TemporaryDirectory() as folder:
            host=h.Host(SimpleNamespace(ROOT=Path(folder)),'b'*40,Path('unused'))
            real_popen=subprocess.Popen
            def launch(command,**kw):
                progress=command[command.index('--progress')+1]
                code="import os,time;import release_verification as v;v.write_verification_progress("+repr(progress)+",{'format':1,'pid':os.getpid(),'status':'RUNNING','active_check':'foreign_key_check','checks':[{'check':'quick_check','status':'PASS','seconds':.01}],'elapsed_seconds':.01});time.sleep(60)"
                return real_popen([sys.executable,'-c',code],env=dict(os.environ,PYTHONPATH=str(Path(v.__file__).parent)),**kw)
            with patch.object(h.subprocess,'Popen',side_effect=launch),self.assertRaises(subprocess.TimeoutExpired):host.verify(1,1.5)
            d=host.verification_diagnostic
            self.assertTrue(d['reaped']);self.assertEqual(d['termination'],'terminated_and_reaped');self.assertIsNotNone(host.child.returncode)
            self.assertEqual(d['partial']['active_check'],'foreign_key_check');self.assertEqual(len(d['partial']['checks']),1)
    def test_parent_interruption_reaps_with_partial_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            host=h.Host(SimpleNamespace(ROOT=Path(folder)),'b'*40,Path('unused'))
            child=Mock();child.pid=123;child.communicate.side_effect=KeyboardInterrupt();child.returncode=-15;child.poll.return_value=-15
            with patch.object(h.subprocess,'Popen',return_value=child),patch.object(host,'reap_owned_child') as reap,self.assertRaises(KeyboardInterrupt):host.verify(1,3)
            reap.assert_called_once_with(1);self.assertTrue(host.verification_diagnostic['reaped']);self.assertEqual(host.verification_diagnostic['partial']['status'],'UNAVAILABLE')

    def test_parent_rejects_incomplete_or_invalid_check_results(self):
        for checks in ([{'check':'quick_check','status':'PASS'}],[{'check':'quick_check','status':'PASS'},{'check':'foreign_key_check','status':'STOP'}]):
            with self.subTest(checks=checks),tempfile.TemporaryDirectory() as folder:
                host=h.Host(SimpleNamespace(ROOT=Path(folder)),'b'*40,Path('unused'))
                child=Mock();child.pid=123;child.returncode=0;child.poll.return_value=0
                child.communicate.return_value=(json.dumps({'status':'PASS','checks':checks}),'')
                with patch.object(h.subprocess,'Popen',return_value=child),self.assertRaises(v.Stop):host.verify(1,3)
                self.assertTrue(host.verification_diagnostic['reaped'])
