"""One-setting capacity bridge; no production configuration/service access."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


def load():
    spec=importlib.util.spec_from_file_location('bridge',Path(__file__).with_name('i7_capacity_bridge.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class FakeHost:
    def __init__(self,fail=None):self.fail=fail;self.calls=[];self.reports=[]
    def validate(self,budget):
        self.calls.append('validate')
        if self.fail=='validate':raise ValueError('preflight')
    def save(self,report):self.reports.append(dict(report))
    def set_guard(self,old,new):
        self.calls.append(('guard',old,new))
        if self.fail=='write':raise OSError('atomic write failure')
    def restore_guard(self):
        self.calls.append('restore')
        if self.fail=='recovery':raise OSError('external edit')
    def restart(self,budget):
        self.calls.append(('restart',budget.recovery))
        if self.fail=='restart' and not budget.recovery:raise TimeoutError('restart')
    def observe(self,budget):
        self.calls.append('observe')
        if self.fail in ('observe','recovery'):raise ValueError('verification')
        return {'continuous_seconds':300}
    def verify(self,budget,guard):self.calls.append(('verify',guard))


class BridgeTests(unittest.TestCase):
    def test_replacement_changes_exactly_one_guard_and_preserves_other_bytes(self):
        module=load()
        for guard in ('4096','"4096"',"'4096'"):
            text='OTHER_SETTING=fixture\r\n  MAX_LOCAL_STORAGE_MB = '+guard+' \r\n# note\r\n'
            updated=module.replace_guard(text,4096,5120)
            self.assertEqual(updated,text.replace('4096','5120'))
            self.assertEqual(module.replace_guard(updated,5120,4096),text)
        for text in ('MAX_LOCAL_STORAGE_MB=8192\n','MAX_LOCAL_STORAGE_MB=4096\nMAX_LOCAL_STORAGE_MB=5120\n','MISSING=1\n','MAX_LOCAL_STORAGE_MB=4096 # ambiguous\n'):
            with self.subTest(text=text),self.assertRaises(ValueError):module.replace_guard(text,4096,5120)

    def test_success_changes_guard_and_restarts_only_api_through_host_interface(self):
        module=load();host=FakeHost()
        result=module.apply_bridge(host,'a'*40,1)
        self.assertEqual(result['status'],'BRIDGE_ACTIVE')
        self.assertEqual(host.calls,['validate',('guard',4096,5120),('restart',False),'observe',('verify',5120)])
        from datetime import datetime
        self.assertEqual((datetime.fromisoformat(result['review_due_at'])-datetime.fromisoformat(result['applied_at'])).total_seconds(),86400)
        self.assertFalse(result['permanent'])

    def test_bad_ci_or_preflight_never_changes_setting_or_restarts(self):
        module=load()
        host=FakeHost();result=module.apply_bridge(host,'short',0)
        self.assertEqual(result['status'],'STOP');self.assertFalse(host.calls)
        host=FakeHost('validate');result=module.apply_bridge(host,'a'*40,1)
        self.assertEqual(host.calls,['validate'])

    def test_atomic_write_failure_restores_setting_without_unneeded_restart(self):
        module=load();host=FakeHost('write');result=module.apply_bridge(host,'a'*40,1)
        self.assertEqual(result['status'],'STOP')
        self.assertIn('restore',host.calls)
        self.assertFalse(any(isinstance(c,tuple) and c[0]=='restart' for c in host.calls))

    def test_restart_and_observation_failure_use_one_recovery_restart(self):
        module=load()
        for failure in ('restart','observe'):
            with self.subTest(failure=failure):
                host=FakeHost(failure);result=module.apply_bridge(host,'a'*40,1)
                self.assertEqual(result['status'],'STOP')
                self.assertEqual([c for c in host.calls if isinstance(c,tuple) and c[0]=='restart'],[('restart',False),('restart',True)])
                self.assertIn(('verify',4096),host.calls)

    def test_failed_recovery_is_manual_action_not_success(self):
        module=load();host=FakeHost('recovery');result=module.apply_bridge(host,'a'*40,1)
        self.assertEqual(result['recovery'],'MANUAL_ACTION_REQUIRED')

    def test_real_atomic_file_update_preserves_mode_owner_and_no_evidence_copy(self):
        module=load()
        with tempfile.TemporaryDirectory() as folder,patch.object(module,'ROOT',Path(folder)):
            path=Path(folder)/'.env';path.write_text('MAX_LOCAL_STORAGE_MB=4096\nOTHER=fixture\n');path.chmod(0o600)
            host=module.Host();host.settings=path.read_bytes();host.owner=(path.stat().st_uid,path.stat().st_gid)
            host.set_guard(4096,5120)
            self.assertEqual(path.read_text(),'MAX_LOCAL_STORAGE_MB=5120\nOTHER=fixture\n')
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertEqual(list(Path(folder).iterdir()),[path])
            host.restore_guard();self.assertEqual(path.read_bytes(),host.settings)
            path.write_text('MAX_LOCAL_STORAGE_MB=4096\nOTHER=external\n')
            with self.assertRaises(ValueError):host.set_guard(4096,5120)

    def test_recovery_reserve_is_bounded(self):
        module=load()
        with patch.object(module.time,'monotonic',return_value=0):budget=module.Budget()
        with patch.object(module.time,'monotonic',return_value=601):
            with self.assertRaises(TimeoutError):budget.seconds(5)
            budget.recovery=True;self.assertEqual(budget.seconds(500),179)
        with patch.object(module.time,'monotonic',return_value=781):
            with self.assertRaises(TimeoutError):budget.seconds(5)

    def observation(self,mode='healthy'):
        from datetime import datetime,timedelta,timezone
        module=load();clock=[0.0];base=datetime(2026,10,31,tzinfo=timezone.utc)
        class FakeDate(datetime):
            @classmethod
            def now(cls,tz=None):return base+timedelta(seconds=clock[0])
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return b'<html>fixture</html>'
            def readline(self,*args):return b'data: {}\n'
        def probe(route):
            if mode=='startup' or (mode=='timeout' and clock[0]>=5):return {'route':route,'error_type':'TimeoutError'}
            if route=='/health':return {'route':route,'collector_running':True,'guard_status':'watching',
               'feeds':{k:{'status':'live','last_data_at':FakeDate.now().isoformat()} for k in ('coinbase_stream','polymarket_stream')}}
            return {'route':route,'market':{'start':(base-timedelta(seconds=60)).isoformat(),'end':(base+timedelta(hours=1)).isoformat()}}
        with patch.object(module.time,'monotonic',side_effect=lambda:clock[0]),patch.object(module.time,'sleep',side_effect=lambda seconds:clock.__setitem__(0,clock[0]+seconds)),patch.object(module,'datetime',FakeDate),patch.object(module.urllib.request,'urlopen',return_value=Response()):
            host=module.Host()
            with patch.object(host,'probe',side_effect=probe),patch.object(host,'save_sample') as samples,patch.object(host,'verify') as verify:
                result=host.observe(module.Budget())
                return result,samples.call_count,verify.call_args

    def test_observation_requires_five_continuous_minutes_and_actual_guard_check(self):
        result,count,verify=self.observation()
        self.assertGreaterEqual(result['continuous_seconds'],300)
        self.assertGreaterEqual(count,61)
        self.assertEqual(verify.args[1],5120)

    def test_startup_and_post_readiness_timeouts_cannot_be_hidden(self):
        with self.assertRaises(TimeoutError):self.observation('startup')
        with self.assertRaises(ValueError):self.observation('timeout')


if __name__=='__main__':unittest.main()
