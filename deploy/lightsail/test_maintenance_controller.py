import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('maintenance',Path(__file__).with_name('maintenance_controller.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Host:
    def __init__(self,fail=None):self.fail=fail;self.actions=[];self.t=0
    def action(self,name):
        self.actions.append(name);self.t+=1
        if name==self.fail:raise RuntimeError('simulated')
    def preflight(self):self.action('preflight');return dict.fromkeys(m.WRITERS,'active'),'old'
    def utcnow(self):return 'test'
    def pause_monitor(self,b):self.action('pause');return 'active'
    def stop(self,u,b):self.action('stop:'+u)
    def start(self,u,b):self.action('start:'+u)
    def require_quiescence(self,b):self.action('quiescence')
    def allocation(self,b):self.action('allocation');return {'headroom_mib':600}
    def identity(self,b):self.action('identity');return 'binding'
    def verify(self,reap,b):self.action('verify');return {'status':'PASS'}
    def checkout_release(self,b):self.action('checkout')
    def checkout_old(self,old,b):self.action('rollback')
    def restore_monitor(self,state,b):self.action('monitor')
    def smoke(self,b):self.action('smoke');return {'status':'PASS'}
    def reap_owned_child(self,b):self.action('reap')
    def save(self,r):self.report=r

class Tests(unittest.TestCase):
    def test_success_and_failure_recovery(self):
        for failure in (None,'preflight','stop:tradebot-api','verify','checkout','smoke'):
            with self.subTest(failure=failure):
                h=Host(failure);r=m.run(h,lambda:h.t)
                self.assertEqual(r['status'],'DEPLOYED_SMOKE_TESTED' if failure is None else 'STOP')
                if failure in ('checkout','smoke'):self.assertIn('rollback',h.actions)
                if failure and failure!='preflight':
                    for unit in m.WRITERS:self.assertIn('start:'+unit,h.actions)
                self.assertEqual(r['boundary_acceptance'],'NOT_PERFORMED')
    def test_insufficient_capacity_restores_without_checkout(self):
        h=Host();h.allocation=lambda b:{'headroom_mib':511}
        self.assertEqual(m.run(h,lambda:h.t)['status'],'STOP');self.assertNotIn('checkout',h.actions)
    def test_failed_recovery_does_not_skip_other_services(self):
        h=Host('verify');original=h.start
        def start(u,b):
            if u=='tradebot-api':raise RuntimeError('failure')
            original(u,b)
        h.start=start;r=m.run(h,lambda:h.t)
        self.assertEqual(r['status'],'MANUAL_ACTION_REQUIRED')
        self.assertIn('start:tradebot-lifecycle',h.actions)
    def test_timeout_and_absolute_deadline(self):
        h=Host();h.verify=lambda reap,b:(setattr(h,'t',h.t+b+1) or {'status':'PASS'})
        r=m.run(h,lambda:h.t);self.assertNotEqual(r['status'],'DEPLOYED_SMOKE_TESTED')
        self.assertNotIn('checkout',h.actions)
