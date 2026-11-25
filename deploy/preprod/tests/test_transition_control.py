"""Generated tests for the root live gate; no PP host access."""
from datetime import datetime, timedelta, timezone
import json
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import transition_control as gate
from controller import DeploymentHold, _secure_file


class TransitionGateTests(unittest.TestCase):
    def test_failed_generated_readiness_keeps_leaving_journal_until_recovery(self):
        digest=hashlib.sha256(b'controller').hexdigest()
        request=gate.TransitionRequest('leave','a'*40,'b'*64,digest,'sha256:'+'c'*64)
        active={**request.bindings(),'version':1,'nonce':str(uuid.uuid4()),'state':'ready_off'}
        calls=[]
        class Transition:
            def __init__(self,*_):pass
            def leave(self):
                calls.append('leave')
                if len(calls)==1:
                    raise DeploymentHold('generated_api_readiness_timeout')
                return {'gate':'PP_GENERATED_RESTORED','collector_enabled':False}
        def write(_path,data,**_):
            active.clear();active.update(data)
        with patch.object(gate.HostBinding,'from_marker',return_value=SimpleNamespace(hostname='tradebot-preprod-01', validate=lambda:None)), \
             patch.object(gate,'_secure_file',return_value=(b'controller',None)), \
             patch.object(gate,'_candidate',return_value=SimpleNamespace(image=request.image_id)), \
             patch.object(gate,'_image_binding',return_value=object()), \
             patch.object(gate,'_owned_runtime'), \
             patch.object(gate,'_atomic_json',side_effect=write), \
             patch.object(gate,'_read_active',side_effect=lambda:dict(active)), \
             patch('live_transition.LiveTransition',Transition):
            with self.assertRaisesRegex(DeploymentHold,'generated_api_readiness_timeout'):
                gate.transition(request,Path('/trusted/controller.pyz'))
            self.assertEqual(active['state'],'leaving')
            self.assertEqual(gate.transition(request,Path('/trusted/controller.pyz'))['gate'],
                             'PP_GENERATED_RESTORED')
        self.assertEqual(active['state'],'generated_restored')
        self.assertEqual(calls,['leave','leave'])

    def test_failed_off_retains_journal_for_permit_free_leave(self):
        digest = hashlib.sha256(b'controller').hexdigest()
        enter = gate.TransitionRequest('enter', 'a'*40, 'b'*64, digest, 'sha256:'+'c'*64)
        leave = gate.TransitionRequest('leave', 'a'*40, 'b'*64, digest, 'sha256:'+'c'*64)
        active = {}
        recovery_calls = []
        class Transition:
            def __init__(self, *_):
                pass
            def enter(self):
                self.mutation_started=True
                raise DeploymentHold('simulated_partial_live_start')
            def leave(self):
                recovery_calls.append('leave')
                if len(recovery_calls) == 1:
                    raise DeploymentHold('simulated_off_unproven')
                return {'gate':'PP_GENERATED_RESTORED', 'collector_enabled':False}
        def write(_path, data, **_):
            active.clear()
            active.update(data)
        context = SimpleNamespace(request=SimpleNamespace(source_sha='a'*40), image='sha256:'+'c'*64)
        with patch.object(gate.HostBinding, 'from_marker', return_value=SimpleNamespace(hostname='tradebot-preprod-01', validate=lambda:None)), \
             patch.object(gate, '_secure_file', return_value=(b'controller', None)), \
             patch.object(gate, '_candidate', return_value=context), \
             patch.object(gate, '_image_binding', return_value=object()), \
             patch.object(gate, '_owned_runtime'), \
             patch.object(gate, '_consume', return_value=str(uuid.uuid4())) as consume, \
             patch.object(gate, '_atomic_json', side_effect=write), \
             patch.object(gate, '_read_active', side_effect=lambda:dict(active)), \
             patch.object(gate, 'ACTIVE', Path('/nonexistent-tradebot-transition-journal')), \
             patch('live_transition.LiveTransition', Transition):
            blocked=gate.transition(enter, Path('/trusted/controller.pyz'))
            self.assertEqual(blocked['reason'],'pp_live_entry_recovery_unproven')
            self.assertEqual(active['state'], 'recovery_unproven')
            self.assertEqual(gate.transition(leave, Path('/trusted/controller.pyz'))['gate'],
                             'PP_GENERATED_RESTORED')
        self.assertEqual(active['state'], 'generated_restored')
        self.assertEqual(recovery_calls, ['leave', 'leave'])
        consume.assert_called_once()

    def test_transition_command_has_exact_host_source_artifact_controller_and_image(self):
        command = 'transition-v1 preprod tradebot-preprod-01 enter ' + 'a'*40 + ' ' + 'b'*64 + ' ' + 'c'*64 + ' sha256:' + 'd'*64
        request = gate.TransitionRequest.parse(command)
        self.assertEqual(request.operation, 'enter')
        self.assertEqual(request.image_id, 'sha256:' + 'd'*64)
        for changed in (command.replace('preprod', 'production', 1),
                        command.replace(' enter ', ' enable '),
                        command.replace('sha256:' + 'd'*64, 'latest')):
            with self.assertRaises(DeploymentHold):
                gate.TransitionRequest.parse(changed)

    def test_cycle_anchor_is_bound_and_off_needs_no_cycle_argument(self):
        anchor = str(uuid.uuid4())
        command = ('transition-v1 preprod tradebot-preprod-01 enter ' + 'a'*40 + ' ' +
                   'b'*64 + ' ' + 'c'*64 + ' sha256:' + 'd'*64)
        parsed = gate.TransitionRequest.parse(f'{command} {anchor}')
        self.assertEqual(parsed.bindings()['initial_a'], anchor)
        with self.assertRaises(DeploymentHold):
            gate.TransitionRequest.parse(f'{command.replace(" enter ", " leave ")} {anchor}')
        with self.assertRaises(DeploymentHold):
            gate.TransitionRequest.parse(f'{command} {anchor.upper()}')
        with patch.object(gate.HostBinding,'from_marker',return_value=gate.HostBinding('tradebot-preprod-01','preprod','Tradebot',False,False,False)), \
             patch.object(gate, '_read_active', return_value={'instance': 'tradebot-preprod-01', 'initial_a': anchor}), \
             patch.object(gate, '_secure_file') as controller:
            for invalid in ('session-v1 on 6600', f'session-v1 on 4560 {anchor}',
                            f'session-v1 on 6601 {anchor}',
                            f'session-v1 on 6600 {uuid.uuid4()}'):
                with self.subTest(invalid=invalid), self.assertRaises(DeploymentHold):
                    gate.session(invalid, Path('/trusted/controller.pyz'))
            controller.assert_not_called()

    def test_scope_permit_is_one_use_and_cannot_authorize_other_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'live-enter.json'
            now = datetime.now(timezone.utc)
            expected = {'scope': 'pp_live_ready_off', 'operation': 'enter', 'image_id': 'sha256:'+'a'*64}
            permit = {**expected, 'version': 1, 'nonce': str(uuid.uuid4()),
                'issued_at': now.isoformat(), 'expires_at': (now + timedelta(minutes=10)).isoformat(),
                'paid_ai_enabled': False, 'cloud_enabled': False,
                'retirement_enabled': False, 'production_data_mounted': False}
            path.write_text(json.dumps(permit))
            path.chmod(0o600)
            with patch.object(gate, '_secure_file', side_effect=lambda p: _secure_file(p, expected_uid=os.getuid())):
                with self.assertRaises(DeploymentHold):
                    gate._consume(path, {**expected, 'image_id': 'sha256:'+'b'*64})
                gate._consume(path, expected)
                with self.assertRaises((DeploymentHold, OSError)):
                    gate._consume(path, expected)
            self.assertFalse(path.exists())
            self.assertEqual(len(list(root.glob('consumed-live-enter-*.json'))), 1)

    def test_expired_permit_does_not_mutate_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'live-on.json'
            now = datetime.now(timezone.utc)
            expected = {'scope': 'pp_live_session_on', 'max_seconds': 900}
            permit = {**expected, 'version': 1, 'nonce': str(uuid.uuid4()),
                'issued_at': (now-timedelta(minutes=31)).isoformat(),
                'expires_at': (now-timedelta(minutes=1)).isoformat(),
                'paid_ai_enabled': False, 'cloud_enabled': False,
                'retirement_enabled': False, 'production_data_mounted': False}
            path.write_text(json.dumps(permit))
            path.chmod(0o600)
            with patch.object(gate, '_secure_file', side_effect=lambda p: _secure_file(p, expected_uid=os.getuid())):
                with self.assertRaisesRegex(DeploymentHold, 'expired'):
                    gate._consume(path, expected)
            self.assertTrue(path.exists())


if __name__ == '__main__':
    unittest.main()
