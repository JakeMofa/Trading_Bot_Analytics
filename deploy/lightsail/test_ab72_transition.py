"""Existing controller + actual generated adapter; no production enablement."""
import importlib.util,sys,tempfile,unittest
from contextlib import closing
from pathlib import Path
from datetime import timedelta
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE));sys.path.insert(0,str(ROOT/'backend/tests'))
import maintenance_controller as controller
import release_verification as verifier
from ab72_metadata import verification_binding
from test_ab_application import legacy,T,iso
from application_store import ApplicationStore
import collector

class GeneratedHost:
    def __init__(self,root,fail=None):
        self.generated_root=Path(root);self.fail=fail;self.actions=[];self.t=0;self.store=None
        self.path=self.generated_root/'generated-legacy.db';legacy(self.path)
    def action(self,name):
        self.actions.append(name);self.t+=.01
        if name==self.fail:raise RuntimeError('injected '+name)
    def utcnow(self):return iso(T)
    def preflight(self):self.action('preflight');return dict.fromkeys(controller.WRITERS,'active'),'legacy'
    def pause_monitor(self,b):self.action('pause');return 'paused'
    def stop(self,u,b):
        self.action('stop:'+u)
        if self.store:self.store.close();self.store=None
    def start(self,u,b):self.action('start:'+u)
    def require_quiescence(self,b):self.action('quiescence')
    def allocation(self,b):return {'headroom_mib':512}
    def identity(self,b):return verification_binding(self.path)
    def verify(self,reap,b):
        self.action('verify')
        return verifier.check_database(self.path,min(b,10))
    def checkout_release(self,b):
        self.action('transition')
        self.store=ApplicationStore(self.generated_root,self.path,routing=True)
        db=self.store.connection()
        try:collector.save_observation(db,'m',iso(T+timedelta(seconds=3)),'book',{'exact':'0.00000000000001'},iso(T))
        finally:db.close()
        # A failure here is ambiguous to the controller but the row is durable.
        self.action('after_commit')
        self.store.close();self.store=None
        for path in [self.generated_root/'core.db',*self.generated_root.glob('raw-*.db')]:
            verifier.check_database(path,min(b,10))
    def checkout_old(self,*a):raise AssertionError('legacy rollback must never occur')
    def restore_monitor(self,s,b):self.action('monitor')
    def smoke(self,b):self.action('smoke');return {'status':'PASS'}
    def reap_owned_child(self,b):self.action('reap')
    def save(self,r):self.report=r

class Tests(unittest.TestCase):
    def test_selected_recovery_fresh_b_forward_control_path(self):
        from test_recovery_bootstrap import Tests as RecoveryFixture
        from allocation_measurement import measure
        class RecoveryHost(GeneratedHost):
            def __init__(self,root,fail):
                self.generated_root=Path(root);self.fail=fail;self.actions=[];self.t=0;self.store=None
                self.path,self.capsule,_,_,_=RecoveryFixture().fixture(self.generated_root,live_name='generated-legacy.db')
                self.work=self.generated_root/'generated-ab-core';self.work.mkdir(mode=0o700)
            def checkout_release(self,b):
                self.action('transition')
                self.store=ApplicationStore(self.work,self.path,routing=True,fresh_b=True,recovery=self.capsule)
                with closing(self.store.connection()) as db:
                    self.ack=db.save_observation('m',iso(T+timedelta(seconds=3)),'book',{'exact':'0.00000000000001'},iso(T))
                self.store.close();self.store=None
                self.action('after_commit')
            def smoke(self,b):
                self.action('smoke')
                store=ApplicationStore(self.work,self.path,routing=True,fresh_b=True,recovery=self.capsule)
                try:
                    with closing(store.worker_connection('history')) as db:
                        if db.execute('SELECT count(*) FROM predictions').fetchone()[0]!=1:raise RuntimeError('history discontinuity')
                    if store.protocol.active()['slot']!='B':raise RuntimeError('wrong active buffer')
                finally:store.close()
                return {'status':'PASS','scope':'generated functional checks; no real venue/boundary'}
        for fail in (None,'after_commit','smoke'):
            with self.subTest(fail=fail),tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
                host=RecoveryHost(root,fail);binding=host.identity(1)
                report=controller.run(host,lambda:host.t,generated_transition=True)
                self.assertEqual(report['status'],'GENERATED_TRANSITION_SMOKE_TESTED' if fail is None else 'STOP',report)
                self.assertEqual(host.identity(1),binding)
                store=ApplicationStore(host.work,host.path,routing=True,fresh_b=True,recovery=host.capsule)
                try:
                    self.assertEqual(store.protocol.core.native.execute("SELECT count(*) FROM ab_events WHERE id=? AND status='committed'",(host.ack,)).fetchone()[0],1)
                    self.assertFalse(store.retirement_enabled)
                finally:store.close()
                self.assertGreater(measure(root)['sampled_total_bytes'],0)
                if fail:self.assertFalse(any(a.startswith('start:') for a in host.actions[host.actions.index('reap'):]))

    def test_actual_adapter_transition_and_forward_failure_preserve_commits(self):
        for fail in (None,'after_commit','smoke'):
            with self.subTest(fail=fail),tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
                host=GeneratedHost(root,fail);before=host.identity(1)
                report=controller.run(host,lambda:host.t,generated_transition=True)
                self.assertEqual(report['status'],'GENERATED_TRANSITION_SMOKE_TESTED' if fail is None else 'STOP')
                self.assertEqual(host.identity(1),before)
                if fail:
                    recovery=host.actions[host.actions.index('reap'):]
                    self.assertFalse(any(a.startswith('start:') for a in recovery))
                    self.assertTrue(report['recovery_action'].startswith('PRESERVE_'))
                if host.store:host.store.close()
                store=ApplicationStore(root,host.path,routing=True)
                try:
                    self.assertEqual(store.protocol.core.native.execute("SELECT count(*) FROM ab_events WHERE status='committed'").fetchone()[0],1)
                    self.assertEqual(store.protocol.core.native.execute('PRAGMA foreign_key_check').fetchall(),[])
                finally:store.close()
                self.assertTrue(report['forward_recovery_required'])
    def test_pre_transition_failure_keeps_original_services_stopped(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            host=GeneratedHost(root,'verify');report=controller.run(host,lambda:host.t,generated_transition=True)
            self.assertEqual(report['status'],'STOP');self.assertNotIn('transition',host.actions)
            self.assertFalse(any(a.startswith('start:') for a in host.actions))
    def test_generated_mode_does_not_inherit_128_mib_exception(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            host=GeneratedHost(root);host.allocation=lambda b:{'headroom_mib':511}
            report=controller.run(host,lambda:host.t,generated_transition=True)
            self.assertEqual(report['status'],'STOP');self.assertNotIn('transition',host.actions)
    def test_production_path_rejected_before_preflight(self):
        class Forbidden:
            generated_root=Path('/opt/tradebot')
            def save(self,r):self.report=r
        host=Forbidden();self.assertEqual(controller.run(host,generated_transition=True)['status'],'STOP')
    def test_preflight_time_counts_against_original_absolute_envelope(self):
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            host=GeneratedHost(root);original=host.preflight
            def slow():host.t+=601;return original()
            host.preflight=slow;report=controller.run(host,lambda:host.t,generated_transition=True)
            self.assertEqual(report['status'],'STOP');self.assertNotIn('transition',host.actions)
            self.assertGreater(report['other_seconds'],600)

    def test_same_schema_data_change_invalidates_verification_binding(self):
        import sqlite3
        with tempfile.TemporaryDirectory(prefix='generated-ab-') as root:
            host=GeneratedHost(root);original=host.verify
            def changed(reap,b):
                result=original(reap,b)
                db=sqlite3.connect(host.path)
                try:
                    db.execute("UPDATE observations SET payload='changed' WHERE id=90");db.commit()
                finally:db.close()
                return result
            host.verify=changed
            report=controller.run(host,lambda:host.t,generated_transition=True)
            self.assertEqual(report['status'],'STOP')
            self.assertEqual(report['reason'],'verification binding changed')
            self.assertNotIn('transition',host.actions)
