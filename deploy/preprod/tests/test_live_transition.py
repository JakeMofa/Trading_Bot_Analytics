"""Generated host command tests; no PP host or cloud operations."""
from pathlib import Path
import json
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from controller import DeploymentHold
from live_transition import LiveTransition


class Actions:
    def _live_filesystem(self,context,budget):self.calls.append('bound_filesystem')
    def __init__(self):
        self.calls=[]
        self.fail_live=False
    def _host(self):self.calls.append('host')
    def _postgres(self,*_):self.calls.append('postgres')
    def _runtime(self,*_,live=False):self.calls.append('runtime_live' if live else 'runtime_generated')
    def _host_api(self,*,live=False):self.calls.append('api_live' if live else 'api_generated')
    def _host_operator(self,*,live=False):self.calls.append('operator_live' if live else 'operator_generated')
    def _compose(self,_context,_budget,args,**_):
        self.calls.append(('base',tuple(args)))
        return b'{}' if args[0]=='config' else b''
    def _environment(self,_image):return {'PATH':'/usr/bin'}
    def _json(self,raw):return json.loads(raw)
    def _oneoff(self,_context,_budget,_service,args,timeout,*,compose):
        return compose(['run','--rm','--no-deps','lifecycle',*args],timeout)


class Budget:
    def __init__(self,actions):self.actions=actions
    def timeout(self,maximum=None):return 180 if maximum is None else min(180,maximum)
    def run(self,args,**_):
        args=tuple(args)
        self.actions.calls.append(('live',args))
        if args[-3:]==('python','-m','postgres.lifecycle_worker'):
            raise AssertionError('missing recovery operation')
        if args[-1]=='--stop-collector':
            return b'{"environment":"preprod","origin_id":"pp-live-pp","collector_enabled":false}'
        if args[-1]=='--collector-status':
            return b'{"environment":"preprod","origin_id":"pp-live-pp","collector_enabled":false}'
        if args[-2:]==('config','--format'):
            raise AssertionError('malformed config command')
        if args[-1]=='json':return b'{}'
        if 'up' in args and self.actions.fail_live:
            raise DeploymentHold('simulated_live_start_failure')
        return b''


class LiveTransitionTests(unittest.TestCase):
    def setUp(self):
        self.actions=Actions()
        self.context=SimpleNamespace(source=Path('/reviewed/source'),image='sha256:'+'a'*64)
        self.transition=LiveTransition(self.actions,self.context,Budget(self.actions))
        self.profile=patch('live_transition.validate_live_profile')
        self.profile.start();self.addCleanup(self.profile.stop)

    def test_enter_only_exposes_off_control_then_leave_stops_before_restore(self):
        ready=self.transition.enter()
        self.assertEqual(ready['gate'],'PP_LIVE_READY_OFF')
        self.assertFalse(ready['collector_enabled'])
        self.assertIn('runtime_live',self.actions.calls)
        self.assertFalse(any('/collector/on' in str(call) for call in self.actions.calls))
        restored=self.transition.leave()
        self.assertEqual(restored['gate'],'PP_GENERATED_RESTORED')
        commands=[(index,call) for index,call in enumerate(self.actions.calls) if isinstance(call,tuple)]
        off=next(index for index,call in commands if '--stop-collector' in call[1])
        base_up=next(index for index,call in commands if call[0]=='base' and 'up' in call[1])
        self.assertLess(off,base_up)
        self.assertEqual(self.actions.calls[-1],'operator_generated')

    def test_failed_live_start_recovers_generated_only_after_durable_off(self):
        self.actions.fail_live=True
        with self.assertRaisesRegex(DeploymentHold,'transition_failed_recovered'):
            self.transition.enter()
        self.assertEqual(self.actions.calls[-1],'operator_generated')

    def test_unproven_off_blocks_generated_restore(self):
        budget=self.transition.budget
        original=budget.run
        def failed_off(args,**kwargs):
            if '--stop-collector' in args:
                raise DeploymentHold('simulated_off_failure')
            return original(args,**kwargs)
        budget.run=failed_off
        with self.assertRaises(DeploymentHold):
            self.transition.leave()
        self.assertFalse(any(call[0]=='base' and 'up' in call[1]
                             for call in self.actions.calls if isinstance(call,tuple)))

    def test_invalid_profile_stops_before_service_mutation(self):
        with patch('live_transition.validate_live_profile',side_effect=DeploymentHold('profile_changed')):
            with self.assertRaisesRegex(DeploymentHold,'profile_changed'):
                self.transition.enter()
        self.assertFalse(any('stop' in call[1] or 'up' in call[1]
                             for call in self.actions.calls if isinstance(call,tuple)))

    def test_generated_restore_waits_for_delayed_api_and_operator_binding(self):
        clock=[0.0]
        api,operator=self.actions._host_api,self.actions._host_operator
        attempts={'api':0,'operator':0}
        def delayed_api(*,live=False):
            attempts['api']+=1
            if attempts['api']<=2:raise DeploymentHold('host_api_loopback_unavailable')
            return api(live=live)
        def delayed_operator(*,live=False):
            attempts['operator']+=1
            if attempts['operator']<=2:raise DeploymentHold('host_operator_loopback_unavailable')
            return operator(live=live)
        self.actions._host_api=delayed_api
        self.actions._host_operator=delayed_operator
        with patch('live_transition.time.monotonic',side_effect=lambda:clock[0]), \
             patch('live_transition.time.sleep',side_effect=lambda seconds:clock.__setitem__(0,clock[0]+seconds)):
            result=self.transition.leave()
        self.assertEqual(result['gate'],'PP_GENERATED_RESTORED')
        self.assertEqual(attempts,{'api':5,'operator':3})
        self.assertLess(clock[0],10)
        self.assertEqual(self.actions.calls[-1],'operator_generated')
        self.assertTrue(any('--stop-collector' in call[1] for call in self.actions.calls if isinstance(call,tuple)))

    def test_generated_restore_times_out_on_persistent_unavailability(self):
        clock=[0.0]
        def unavailable(*,live=False):
            self.actions.calls.append('api_unavailable')
            raise DeploymentHold('host_api_loopback_unavailable')
        self.actions._host_api=unavailable
        with patch('live_transition.time.monotonic',side_effect=lambda:clock[0]), \
             patch('live_transition.time.sleep',side_effect=lambda seconds:clock.__setitem__(0,clock[0]+seconds)):
            with self.assertRaisesRegex(DeploymentHold,'generated_api_readiness_timeout'):
                self.transition.leave()
        self.assertLessEqual(clock[0],10)
        self.assertNotIn('operator_generated',self.actions.calls)

    def test_generated_restore_rejects_reachable_wrong_state_immediately(self):
        attempts=[]
        def wrong_state(*,live=False):
            attempts.append('api')
            raise DeploymentHold('host_api_wrong_state')
        self.actions._host_api=wrong_state
        with patch('live_transition.time.sleep') as sleep:
            with self.assertRaisesRegex(DeploymentHold,'generated_api_state_check_failed'):
                self.transition.leave()
        self.assertEqual(attempts,['api'])
        sleep.assert_not_called()

    def test_generated_restore_reports_runtime_phase_without_host_retry(self):
        def invalid_runtime(*_,live=False):
            self.actions.calls.append('runtime_invalid')
            raise DeploymentHold('private_binding_changed')
        self.actions._runtime=invalid_runtime
        with patch('live_transition.time.sleep') as sleep:
            with self.assertRaisesRegex(DeploymentHold,'generated_runtime_check_failed'):
                self.transition.leave()
        self.assertNotIn('api_generated',self.actions.calls)
        sleep.assert_not_called()

    def test_generated_restore_rejects_operator_auth_mismatch_immediately(self):
        def wrong_auth(*,live=False):
            self.actions.calls.append('operator_wrong_auth')
            raise DeploymentHold('host_operator_unauthenticated_control_allowed')
        self.actions._host_operator=wrong_auth
        with patch('live_transition.time.sleep') as sleep:
            with self.assertRaisesRegex(DeploymentHold,'generated_operator_state_check_failed'):
                self.transition.leave()
        self.assertEqual(self.actions.calls[-1],'operator_wrong_auth')
        sleep.assert_not_called()
