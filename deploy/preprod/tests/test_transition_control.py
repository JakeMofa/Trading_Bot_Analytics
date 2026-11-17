"""Generated tests for the root live gate; no PP host access."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import transition_control as gate
from controller import DeploymentHold, _secure_file


class TransitionGateTests(unittest.TestCase):
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
