import importlib.util
from pathlib import Path
import sqlite3
import sys
import time
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('lifecycle_integrity',Path(__file__).with_name('lifecycle_integrity.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class Host:
    def __init__(self,fail=None):self.fail=fail;self.calls=[]
    def action(self,name):
        self.calls.append(name)
        if name==self.fail:raise TimeoutError('injected')
    def preflight(self,seconds):self.action('preflight');return dict.fromkeys(module.WRITERS,'active')
    def stop(self,unit,seconds):self.action('stop:'+unit)
    def start(self,unit,seconds):self.action('start:'+unit)
    def require_no_database_owners(self,seconds):self.action('owners')
    def check(self,check,seconds):self.action(check);return {'check':check,'status':'PASS'}
    def verify_recovery(self,seconds):self.action('recovery');return {'status':'PASS'}
    def save(self,report):pass


class IntegrityGateTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform=='linux','Linux process group termination')
    def test_bounded_child_kills_and_reaps_sigterm_ignoring_process(self):
        started=time.monotonic()
        code,out,err,timed_out=module.bounded_child([sys.executable,'-c',
            'import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);print("ready",flush=True);time.sleep(60)'],.5)
        self.assertTrue(timed_out);self.assertLess(code,0);self.assertIn('ready',out)
        self.assertLess(time.monotonic()-started,3)

    @unittest.skipUnless(sys.platform=='linux','Linux parent interruption')
    def test_parent_interruption_reaps_child_before_recovery(self):
        import signal
        from unittest.mock import patch
        children=[];original=module.subprocess.Popen
        def spawn(*args,**kwargs):
            child=original(*args,**kwargs);children.append(child);return child
        def interrupt(signum,frame):raise RuntimeError('interrupted test parent')
        previous=signal.signal(signal.SIGALRM,interrupt)
        try:
            signal.setitimer(signal.ITIMER_REAL,.2)
            with patch.object(module.subprocess,'Popen',side_effect=spawn):
                with self.assertRaises(RuntimeError):
                    module.bounded_child([sys.executable,'-c','import time;time.sleep(60)'],10)
            self.assertIsNotNone(children[0].poll())
        finally:
            signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)

    def test_full_pass_restores_previous_writers(self):
        host=Host();result=module.run_gate(host)
        self.assertEqual(result['status'],'PASS')
        self.assertEqual([x for x in host.calls if x.startswith('start:')],['start:'+u for u in reversed(module.WRITERS)])
    def test_failed_preflight_never_stops_services(self):
        host=Host('preflight');self.assertEqual(module.run_gate(host)['status'],'STOP')
        self.assertEqual(host.calls,['preflight'])
    def test_partial_stop_and_failed_audit_stay_failed_after_recovery(self):
        for failure in ('stop:tradebot-ensemble','owners','quick_check','foreign_key_check'):
            host=Host(failure);result=module.run_gate(host)
            self.assertEqual(result['status'],'STOP')
            self.assertEqual(result['recovery']['status'],'PASS')
            self.assertTrue(any(x.startswith('start:') for x in host.calls))
    def test_recovery_failure_is_explicit(self):
        host=Host('recovery');result=module.run_gate(host)
        self.assertEqual(result['status'],'STOP');self.assertEqual(result['recovery_failure_type'],'TimeoutError')
    def test_restart_failure_still_attempts_other_stopped_services(self):
        host=Host('start:tradebot-lifecycle');result=module.run_gate(host)
        self.assertEqual(result['status'],'STOP')
        self.assertIn('start:tradebot-ensemble',host.calls);self.assertIn('start:tradebot-api',host.calls)
        self.assertEqual(result['recovery_start_failures'][0]['unit'],'tradebot-lifecycle')

    def test_timer_without_mainpid_passes_actual_read_only_recovery(self):
        from datetime import datetime,timedelta,timezone
        from types import SimpleNamespace
        from unittest.mock import patch
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'data').mkdir();config=root/'.env'
            config.write_bytes(b'generated_fixture=true');config.chmod(0o600);st=config.stat()
            db=sqlite3.connect(root/'data/btc_intelligence.db')
            old=datetime(2026,10,1,tzinfo=timezone.utc)
            for table in ('observations','stream_events'):
                db.execute('CREATE TABLE '+table+'(received_at TEXT)')
                db.executemany('INSERT INTO '+table+' VALUES(?)',[(old.isoformat(),),((old+timedelta(seconds=2)).isoformat(),)])
            db.commit();db.close()
            now=datetime.now(timezone.utc);counter=[0]
            def probe(route):
                counter[0]+=1;stamp=(now-timedelta(seconds=2)+timedelta(milliseconds=counter[0]*100)).isoformat()
                return {'collector_running':True,'guard_status':'watching','feeds':{key:{'status':'live','last_data_at':stamp} for key in ('coinbase_stream','polymarket_stream')}}
            timer={'ActiveState':'active','UnitFileState':'enabled'}
            host=object.__new__(module.LinuxHost);host.ROOT=root
            host.before={'tradebot-soak.timer':timer};host.config=(hashlib.sha256(config.read_bytes()).hexdigest(),st.st_uid,st.st_gid,st.st_mode)
            host.raw_baseline={key:(1,old.isoformat()) for key in ('observations','stream_events')}
            host.bridge=SimpleNamespace(probe=probe,verify=lambda *args:None,states=lambda *args:{'tradebot-soak.timer':timer})
            with patch.object(module.time,'sleep',return_value=None):result=host.verify_recovery(5)
            self.assertEqual(result['status'],'PASS')
            self.assertEqual(result['raw_received_gap_seconds'],{'observations':2,'stream_events':2})

    def test_unreaped_child_is_explicit_even_after_services_recover(self):
        host=Host()
        def check(*args):raise module.UnreapedIntegrityChild(12345)
        host.check=check
        result=module.run_gate(host)
        self.assertEqual(result['status'],'STOP');self.assertEqual(result['unreaped_child_pid'],12345)
        self.assertTrue(result['manual_recovery_required']);self.assertEqual(result['recovery']['status'],'PASS')

    def test_checks_are_read_only_and_fk_failure_is_not_hidden(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'generated.db';db=sqlite3.connect(p)
            db.executescript('CREATE TABLE parent(id PRIMARY KEY);CREATE TABLE child(id REFERENCES parent(id));INSERT INTO child VALUES(1);');db.close()
            before=p.read_bytes()
            self.assertEqual(module.check_database(p,'quick_check',1)['status'],'PASS')
            with self.assertRaises(module.IntegrityStop):module.check_database(p,'foreign_key_check',1)
            self.assertEqual(p.read_bytes(),before)


if __name__=='__main__':unittest.main()
