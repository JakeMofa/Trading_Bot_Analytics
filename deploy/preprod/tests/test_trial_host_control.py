"""Exact trial host control contracts; no Docker/host/cloud operations."""
from copy import deepcopy
import json
import hashlib
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from controller import DeploymentHold
import linux_actions as actions
from live_profile import validate_live_profile
from live_transition import LiveTransition
import transition_control as gate
from test_linux_actions import configuration,IMAGE
from test_live_transition import Actions,Budget

A=str(uuid.uuid4());TRIAL=actions.TRIAL_ORIGIN

class TrialHostTests(unittest.TestCase):
    def test_previous_display_terminal_journal_and_inventory(self):
        old=actions.PREVIOUS_DISPLAY_ORIGIN
        journal=dict(version=1,environment='preprod',instance=gate.BENCHMARK_INSTANCE,
                     state='generated_restored',nonce=A,initial_a=A,source_sha='a'*40,
                     artifact_sha256='b'*64,controller_sha256='c'*64,image_id=IMAGE,
                     trial_origin=old,profile=actions.BOUNDARY_POLICY)
        def read(**changes):
            payload=json.dumps({**journal,**changes}).encode()
            with patch.object(gate,'_secure_file',return_value=(payload,None)):
                return gate._read_active()
        self.assertEqual(read()['trial_origin'],old)
        self.assertIn(old,actions.OUTBOX_ORIGINS)
        for changes in ({'state':'ready_off'},{'initial_a':None},{'profile':'wrong'},
                        {'instance':'tradebot-preprod-01'}):
            with self.assertRaises(DeploymentHold):
                read(**changes)
        with self.assertRaises(DeploymentHold):
            actions.live_origin(old)

    def test_exact_origin_anchor_and_full_profile_binding(self):
        source=Path('/reviewed/source');base=configuration(source);live=deepcopy(base)
        for name in ('api','calculation','lifecycle','operator'):
            live['services'][name]['environment']=actions.expected_environment(name,live=True,initial_a=A,trial_origin=TRIAL)
        live['services']['operator']['secrets'].append({'source':'app_dsn','target':'app_dsn'})
        self.assertIs(validate_live_profile(base,live,source,IMAGE,initial_a=A,trial_origin=TRIAL),live)
        for name in ('api','calculation','lifecycle','operator'):
            bad=deepcopy(live);bad['services'][name]['environment']['TRADEBOT_ORIGIN_ID']='pp-live-pp'
            with self.assertRaises(DeploymentHold):validate_live_profile(base,bad,source,IMAGE,initial_a=A,trial_origin=TRIAL)
        for name in ('lifecycle','operator'):
            bad=deepcopy(live);bad['services'][name]['environment']['TRADEBOT_PP_ELAPSED_CYCLE_SECONDS']='1'
            with self.assertRaises(DeploymentHold):validate_live_profile(base,bad,source,IMAGE,initial_a=A,trial_origin=TRIAL)
        for origin,anchor in ((TRIAL+'-other',A),(TRIAL,None)):
            with self.assertRaises(DeploymentHold):actions.cycle_environment(anchor,origin)
        with self.assertRaises(DeploymentHold):validate_live_profile(base,live,source,IMAGE,initial_a=A,trial_origin=TRIAL,reader=True)
        self.assertFalse(any('history' in secret['source'] for secret in live['services']['api']['secrets']))

    def test_fresh_permits_bind_profile_and_elapsed_window_and_retained_sixth_cannot_enter(self):
        request=gate.TransitionRequest('enter','a'*40,'b'*64,'c'*64,IMAGE,initial_a=A,trial_origin=TRIAL)
        request.validate()
        self.assertEqual((request.bindings()['profile'],request.bindings()['window_seconds']),
                         ('elapsed-30m-cycle',1800))
        old='pp-live-pp-trial-20261119-06'
        self.assertEqual(actions.cycle_environment(A,old)['TRADEBOT_PP_WINDOW_POLICY'],
                         'two-official-markets-cycle')
        with self.assertRaisesRegex(DeploymentHold,'retained_trial_is_read_only'):
            gate.TransitionRequest('enter','a'*40,'b'*64,'c'*64,IMAGE,initial_a=A,trial_origin=old).validate()

    def test_timing_is_exact_active_trial_operator_only_and_cannot_be_removed(self):
        source=Path('/reviewed/source');base=configuration(source)
        for origin in (None,*actions.RETAINED_TRIAL_ORIGINS):
            self.assertNotIn('TRADEBOT_PP_COINBASE_TIMING',actions.expected_environment('operator',live=True,
                initial_a=A if origin else None,trial_origin=origin))
        live=deepcopy(base)
        for name in ('api','calculation','lifecycle','operator'):
            live['services'][name]['environment']=actions.expected_environment(name,live=True,initial_a=A,trial_origin=TRIAL)
            self.assertEqual(live['services'][name]['environment'].get('TRADEBOT_PP_COINBASE_TIMING'),
                             'true' if name=='operator' else None)
        live['services']['operator']['secrets'].append({'source':'app_dsn','target':'app_dsn'})
        validate_live_profile(base,live,source,IMAGE,initial_a=A,trial_origin=TRIAL)
        for service in ('api','operator'):
            bad=deepcopy(live)
            if service=='operator':del bad['services'][service]['environment']['TRADEBOT_PP_COINBASE_TIMING']
            else:bad['services'][service]['environment']['TRADEBOT_PP_COINBASE_TIMING']='true'
            with self.assertRaises(DeploymentHold):validate_live_profile(base,bad,source,IMAGE,initial_a=A,trial_origin=TRIAL)

    def test_command_and_active_binding_reject_wrong_or_missing_trial_origin(self):
        base='transition-v1 preprod tradebot-preprod-01 enter '+'a'*40+' '+'b'*64+' '+'c'*64+' sha256:'+'d'*64
        request=gate.TransitionRequest.parse(base+' '+A+' '+TRIAL)
        self.assertEqual(request.bindings()['trial_origin'],TRIAL)
        for origin in ('pp-live-pp','pp-live-pp-trial-20261119-01','pp-live-pp-trial-20261119-02','pp-live-pp-trial-20261119-03',TRIAL+'-other'):
            with self.assertRaises(DeploymentHold):gate.TransitionRequest.parse(base+' '+A+' '+origin)
        active={'instance':'tradebot-preprod-01','initial_a':A,'trial_origin':TRIAL}
        with patch.object(gate.HostBinding,'from_marker',return_value=gate.HostBinding('tradebot-preprod-01','preprod','Tradebot',False,False,False)),patch.object(gate,'_read_active',return_value=active),patch.object(gate,'_secure_file') as secret:
            for command in ('session-v1 on 6600 '+A,'session-v1 on 6600 '+A+' '+TRIAL+'-other'):
                with self.assertRaises(DeploymentHold):gate.session(command,Path('/trusted/controller'))
            secret.assert_not_called()
        self.assertEqual(gate._cycle_args(active),{'initial_a':A,'trial_origin':TRIAL})

    def test_retained_first_trial_journal_remains_valid_for_off_but_never_new_enter(self):
        retained='pp-live-pp-trial-20261119-01'
        self.assertEqual(actions.live_origin(retained),retained)
        owned=Actions();context=SimpleNamespace(source=Path('/reviewed/source'),image=IMAGE)
        base=Budget(owned)
        class RetainedBudget:
            def timeout(self,*args):return base.timeout(*args)
            def run(self,args,**kwargs):
                raw=base.run(args,**kwargs)
                return raw.replace(b'pp-live-pp',retained.encode()) if args[-1] in ('--stop-collector','--collector-status') else raw
        transition=LiveTransition(owned,context,RetainedBudget(),initial_a=A,trial_origin=retained)
        with self.assertRaisesRegex(DeploymentHold,'retained_trial_is_read_only'):transition.enter()
        self.assertEqual(owned.calls,[])
        with patch('live_transition.validate_live_profile'):
            transition.leave()
        commands=[c[1] for c in owned.calls if isinstance(c,tuple) and c[0]=='live']
        self.assertTrue(any(any('runtime.retained-trial-01.compose.yaml' in value for value in command) for command in commands))
        self.assertFalse(any('postgres.pp_trial_prepare' in command for command in commands))

    def test_retained_second_trial_journal_remains_valid_for_off_but_never_new_enter(self):
        retained='pp-live-pp-trial-20261119-02'
        self.assertEqual(actions.live_origin(retained),retained)
        owned=Actions();context=SimpleNamespace(source=Path('/reviewed/source'),image=IMAGE)
        base=Budget(owned)
        class RetainedBudget:
            def timeout(self,*args):return base.timeout(*args)
            def run(self,args,**kwargs):
                raw=base.run(args,**kwargs)
                return raw.replace(b'pp-live-pp',retained.encode()) if args[-1] in ('--stop-collector','--collector-status') else raw
        transition=LiveTransition(owned,context,RetainedBudget(),initial_a=A,trial_origin=retained)
        with self.assertRaisesRegex(DeploymentHold,'retained_trial_is_read_only'):transition.enter()
        self.assertEqual(owned.calls,[])
        with patch('live_transition.validate_live_profile'):
            transition.leave()
        commands=[c[1] for c in owned.calls if isinstance(c,tuple) and c[0]=='live']
        self.assertTrue(any(any('runtime.retained-trial-02.compose.yaml' in value for value in command) for command in commands))
        self.assertFalse(any('postgres.pp_trial_prepare' in command for command in commands))

    def test_retained_third_trial_journal_remains_valid_for_off_but_never_new_enter(self):
        retained='pp-live-pp-trial-20261119-03'
        self.assertEqual(actions.live_origin(retained),retained)
        owned=Actions();context=SimpleNamespace(source=Path('/reviewed/source'),image=IMAGE)
        base=Budget(owned)
        class RetainedBudget:
            def timeout(self,*args):return base.timeout(*args)
            def run(self,args,**kwargs):
                raw=base.run(args,**kwargs)
                return raw.replace(b'pp-live-pp',retained.encode()) if args[-1] in ('--stop-collector','--collector-status') else raw
        transition=LiveTransition(owned,context,RetainedBudget(),initial_a=A,trial_origin=retained)
        with self.assertRaisesRegex(DeploymentHold,'retained_trial_is_read_only'):transition.enter()
        self.assertEqual(owned.calls,[])
        with patch('live_transition.validate_live_profile'):
            transition.leave()
        commands=[c[1] for c in owned.calls if isinstance(c,tuple) and c[0]=='live']
        self.assertTrue(any(any('runtime.retained-trial-03.compose.yaml' in value for value in command) for command in commands))
        self.assertFalse(any('postgres.pp_trial_prepare' in command for command in commands))

    def test_retained_fifth_on_rejects_before_secrets_authority_or_network(self):
        retained='pp-live-pp-trial-20261119-05'
        with patch.object(gate.HostBinding,'from_marker',return_value=gate.HostBinding('tradebot-preprod-01','preprod','Tradebot',False,False,False)),patch.object(gate,'_read_active',return_value={
            'instance':'tradebot-preprod-01',                'state':'ready_off','initial_a':A,'trial_origin':retained}), \
             patch.object(gate,'_secure_file') as secret,patch.object(gate,'_consume') as consume, \
             patch.object(gate,'_operator') as operator:
            with self.assertRaisesRegex(DeploymentHold,'retained_trial_is_read_only'):
                gate.session('session-v1 on 6600 '+A+' '+retained,Path('/trusted/controller'))
            secret.assert_not_called();consume.assert_not_called();operator.assert_not_called()
        import install_controller as install
        with patch.object(install.HostBinding,'from_marker',return_value=install.HostBinding('tradebot-preprod-01','preprod','Tradebot',False,False,False)),patch.object(install,'_read_active',return_value={
            'instance':'tradebot-preprod-01',                'state':'ready_off','initial_a':A,'trial_origin':retained}), \
             patch.object(install,'_scope_permit') as permit,patch('trial_cloud_control.require_ready') as ready:
            with self.assertRaisesRegex(DeploymentHold,'retained_trial_is_read_only'):
                install.authorize_live_on(6600)
            permit.assert_not_called();ready.assert_not_called()

    def test_trial_on_is_held_before_consuming_authority_until_cloud_readiness(self):
        digest=hashlib.sha256(b'controller').hexdigest()
        active=dict(instance='tradebot-preprod-01',state='ready_off',initial_a=A,trial_origin=TRIAL,source_sha='a'*40,
            artifact_sha256='b'*64,controller_sha256=digest,image_id=IMAGE)
        with patch.object(gate.HostBinding,'from_marker',return_value=gate.HostBinding('tradebot-preprod-01','preprod','Tradebot',False,False,False)),patch.object(gate,'_read_active',return_value=active), \
             patch.object(gate,'_secure_file',return_value=(b'controller',None)),patch.object(gate,'_candidate'), \
             patch.object(gate,'_image_binding'),patch.object(gate,'_owned_runtime'),patch.object(gate,'_consume') as consume, \
             patch('trial_cloud_control.require_ready',side_effect=DeploymentHold('archive_readiness_unqualified')):
            with self.assertRaisesRegex(DeploymentHold,'archive_readiness_unqualified'):
                gate.session('session-v1 on 6600 '+A+' '+TRIAL,Path('/trusted/controller'))
            consume.assert_not_called()
        import install_controller as install
        with patch.object(install.HostBinding,'from_marker',return_value=install.HostBinding('tradebot-preprod-01','preprod','Tradebot',False,False,False)),patch.object(install,'_read_active',return_value=active), \
             patch.object(install,'_scope_permit') as scope,patch.object(install,'_candidate'), \
             patch('trial_cloud_control.require_ready',side_effect=DeploymentHold('archive_readiness_unqualified')):
            with self.assertRaisesRegex(DeploymentHold,'archive_readiness_unqualified'):
                install.authorize_live_on(6600)
            scope.assert_not_called()

    def test_prepare_runs_only_after_stop_and_never_on_leave(self):
        class TrialActions(Actions):
            def _runtime(self,*_,live=False,**kwargs):
                if live:self.asserted_scope=kwargs
                super()._runtime(live=live)
            def _host_api(self,*,live=False,**_):super()._host_api(live=live)
            def _host_operator(self,*,live=False,**_):super()._host_operator(live=live)
        owned=TrialActions();base=Budget(owned)
        class TrialBudget:
            def timeout(self,*args):return base.timeout(*args)
            def run(self,args,**kwargs):
                if 'postgres.pp_trial_prepare' in args:
                    owned.calls.append(('prepare',tuple(args)))
                    return json.dumps(dict(status='trial_ready_off',origin_id=TRIAL,generation_id=A,collector_enabled=False) | actions.cycle_profile_binding(TRIAL)).encode()
                result=base.run(args,**kwargs)
                return result.replace(b'pp-live-pp',TRIAL.encode()) if args[-1] in ('--stop-collector','--collector-status') else result
        context=SimpleNamespace(source=Path('/reviewed/source'),image=IMAGE,request=SimpleNamespace(source_sha='a'*40))
        transition=LiveTransition(owned,context,TrialBudget(),initial_a=A,trial_origin=TRIAL)
        with patch('live_transition.validate_live_profile'),patch('live_transition.history_reader_enabled',side_effect=AssertionError('legacy reader inspected')):
            result=transition.enter()
            self.assertEqual((result['origin_id'],result['initial_a']),(TRIAL,A))
            stop=next(i for i,c in enumerate(owned.calls) if isinstance(c,tuple) and c[0]=='base' and c[1][0]=='stop')
            prepare=next(i for i,c in enumerate(owned.calls) if isinstance(c,tuple) and c[0]=='prepare')
            up=next(i for i,c in enumerate(owned.calls) if isinstance(c,tuple) and c[0]=='live' and 'up' in c[1])
            self.assertLess(stop,prepare);self.assertLess(prepare,up)
            transition.leave()
        self.assertEqual(len([c for c in owned.calls if isinstance(c,tuple) and c[0]=='prepare']),1)
        self.assertEqual(owned.asserted_scope,dict(initial_a=A,trial_origin=TRIAL))
