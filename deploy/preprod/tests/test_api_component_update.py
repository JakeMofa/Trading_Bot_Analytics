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
        self.assertEqual(len(compatible_build(*bases)), 64)
        for rel in (
            'backend/postgres/migrations/0001_base.sql',
            'backend/requirements.txt',
            'deploy/preprod/Dockerfile',
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
