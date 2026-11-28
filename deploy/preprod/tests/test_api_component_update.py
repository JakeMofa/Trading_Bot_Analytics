import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller import DeploymentHold
from api_component_update import compatible_build, switch, write_json


class APIComponentDelivery(unittest.TestCase):
    def test_compares_all_migrations_and_build_inputs(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        bases = [root / 'current', root / 'candidate']
        for base in bases:
            (base / 'backend/postgres/migrations').mkdir(parents=True)
            (base / 'backend/postgres/migrations/0001_base.sql').write_text('SELECT 1;')
            (base / 'backend/requirements.txt').write_text('psycopg==3.2.1')
            (base / 'deploy/preprod').mkdir(parents=True)
            (base / 'deploy/preprod/Dockerfile').write_text('FROM pinned')
            for name in ('runtime.compose.yaml','runtime.live.compose.yaml','runtime.live-boundary.compose.yaml',
                         'runtime.quote-display.compose.yaml'):
                (base/'deploy/preprod'/name).write_text('services: {}')
        self.assertEqual(len(compatible_build(*bases)), 64)
        for rel in (
            'backend/postgres/migrations/0001_base.sql',
            'backend/requirements.txt',
            'deploy/preprod/Dockerfile',
            'deploy/preprod/runtime.quote-display.compose.yaml',
        ):
            with self.subTest(rel=rel):
                target = bases[1] / rel
                initial = target.read_bytes()
                target.write_bytes(initial + b'drift')
                with self.assertRaises(DeploymentHold):
                    compatible_build(*bases)
                target.write_bytes(initial)

    def test_failure_after_healthy_HTTP_rolls_back_only_api_and_receipt(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        ctx = SimpleNamespace(staging=directory, image='collector')
        active = {'initial_a': 'initial'}
        previous = {'api_image': 'previous-api'}
        target = {'api_image': 'new-api'}
        marker = directory / 'benchmark-api-component.json'
        write_json(marker, previous)
        actions = Mock()
        actions._runtime.side_effect = DeploymentHold('invalid_api_mount')
        calls = []

        def api(_ctx, _active, _actions, _budget, image):
            calls.append(image)

        with self.assertRaisesRegex(DeploymentHold, 'invalid_api_mount'):
            switch(ctx, active, actions, Mock(), target, previous, probe=api)
        self.assertEqual(json.loads(marker.read_bytes()), previous)
        self.assertEqual(calls, ['new-api', 'previous-api'])
        actions._fence.assert_not_called()
        actions._oneoff.assert_not_called()

    def test_failed_first_deploy_restores_baseline_image_and_recovers_marker(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        ctx = SimpleNamespace(staging=directory, image='base')
        active = {'initial_a': 'initial'}
        calls = []

        def api(_ctx, _active, _actions, _budget, image):
            calls.append(image)
            if image == 'broken-api':
                raise DeploymentHold('api_sse_unhealthy')

        with self.assertRaisesRegex(DeploymentHold, 'api_sse_unhealthy'):
            switch(ctx, active, Mock(), Mock(), {'api_image': 'broken-api'}, None, probe=api)
        self.assertFalse((directory / 'benchmark-api-component.json').exists())
        self.assertEqual(calls, ['broken-api', 'base'])

    def test_independent_renewals_span_failed_switch_and_full_rollback(self):
        from threading import Condition
        from api_component_update import continued_renewal

        changed = Condition()
        current, expires, pulses = 0, 85, 0

        def renew():
            nonlocal expires, pulses
            with changed:
                self.assertLess(current, expires)
                expires = current + 120
                pulses += 1
                changed.notify_all()
            return True

        with continued_renewal(renew, needed=True, interval=0.001):
            # Advance a controlled database clock through an exchange that takes
            # all 55 seconds, a 40-second rollback, and its final checks.
            for second in (12, 24, 36, 48, 55, 67, 79, 91, 95, 107, 119, 120):
                with changed:
                    current = second
                    prior = pulses
                    self.assertTrue(changed.wait_for(lambda: pulses > prior, 1))
                    self.assertLess(current, expires)
        self.assertGreaterEqual(pulses, 13)

    def test_explicit_off_before_or_during_recovery_does_not_start_writer(self):
        from unittest.mock import patch
        from api_component_update import continued_renewal, renew_existing

        document = json.dumps({'state': 'armed', 'binding': {'nonce': 'same'}}).encode()
        with (
            patch('api_component_update.INTENT') as intent,
            patch('api_component_update._secure_file', return_value=(document, None)),
            patch('api_component_update.binding', return_value={'nonce': 'same'}),
            patch('api_component_update.token', return_value='test'),
            patch('api_component_update._operator') as operator,
            patch('api_component_update.recurring_control') as worker,
        ):
            intent.exists.return_value = True
            operator.return_value = {
                'origin_id': 'pp-live-pp-benchmark-watch',
                'watch_explicit_off': True,
                'collector_enabled': False,
                'process_running': False,
            }
            with continued_renewal(lambda: renew_existing({'source_sha': 'shared'}), needed=False):
                pass
            operator.assert_called_once_with('test', '/collector/status')
            worker.assert_not_called()

        from threading import Event

        stopped = Event()
        seen = []

        def receive():
            seen.append('existing')
            if len(seen) > 1:
                stopped.set()
                return False
            return True

        with continued_renewal(receive, needed=True, interval=0.001):
            self.assertTrue(stopped.wait(1))
        self.assertEqual(seen, ['existing', 'existing'])
