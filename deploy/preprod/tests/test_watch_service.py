"""A systemd tick maintains only a previously armed, release-bound Benchmark intent."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import watch_service as watch


class WatchHeartbeats(unittest.TestCase):
    def setUp(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.intent = root / 'intent'
        self.boot = root / 'boot'
        self.boot.write_text('boot-id')
        self.bound = dict(source_sha='a' * 40, initial_a='anchor')
        self.status = dict(
            origin_id=watch.DISPLAY_ORIGIN,
            collector_enabled=False,
            process_running=False,
            initialized=True,
            lease_expired=False,
        )
        self.enterContext(
            patch.multiple(watch, INTENT=self.intent, BOOT=self.boot, ON_AUTHORITY=root / 'unused')
        )
        self.enterContext(patch.object(watch, '_secure_file', side_effect=lambda p: (p.read_bytes(), None)))
        self.enterContext(
            patch.object(watch, '_atomic_json', side_effect=lambda p, v, **_: p.write_text(json.dumps(v)))
        )
        self.enterContext(patch.object(watch, 'binding', return_value=self.bound))
        self.enterContext(patch.object(watch, 'token', return_value='private-generated-test'))
        self.worker = self.enterContext(
            patch.object(
                watch, 'recurring_control', return_value={'status': 'running', 'source_sha': 'a' * 40}
            )
        )

        def operator(_token, path):
            if path == '/collector/status':
                return self.status
            if path == '/collector/watch/arm':
                return {'watch_explicit_off': False}
            self.assertEqual(path, '/collector/watch/renew')
            return {'origin_id': watch.DISPLAY_ORIGIN, 'epoch': 2}

        self.enterContext(patch.object(watch, '_operator', side_effect=operator))

    def test_armed_only_renewal_and_durable_explicit_off(self):
        self.assertEqual(watch.tick(), {'state': 'off'})
        watch.arm(self.bound['source_sha'], self.bound['initial_a'])
        with (
            patch('install_controller.authorize_live_on') as mint,
            patch.object(watch, 'session', return_value={'gate': 'PP_LIVE_ON'}) as session,
        ):
            self.assertEqual(watch.tick()['state'], 'running')
            self.status.update(collector_enabled=True, process_running=True)
            self.assertEqual(watch.tick()['epoch'], 2)
            mint.assert_called_once_with(watch.WATCH_LEASE_SECONDS)
            session.assert_called_once()
        self.status.update(watch_explicit_off=True)
        self.assertEqual(watch.tick(), {'state': 'off'})
        self.assertFalse(self.intent.exists())

    def test_no_admission_without_qualified_archive_worker(self):
        watch.arm(self.bound['source_sha'], self.bound['initial_a'])
        self.worker.return_value = {'status': 'off'}
        with patch('install_controller.authorize_live_on') as mint:
            with self.assertRaisesRegex(watch.DeploymentHold, 'watch_archive_worker_unavailable'):
                watch.tick()
            mint.assert_not_called()
