"""A systemd tick maintains only a previously armed, release-bound Benchmark intent."""

import json
from pathlib import Path
import tempfile
import unittest
import stat
from types import SimpleNamespace
from urllib.error import HTTPError
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

    def test_historical_failure_requires_confirmed_off_to_rearm_same_origin(self):
        self.status['session_failure_code'] = 'selected_feeds.database_connection_limit'
        for acknowledged in (None, False):
            self.status['session_failure_acknowledged'] = acknowledged
            with self.assertRaisesRegex(watch.DeploymentHold, 'watch_start_state'):
                watch.arm(self.bound['source_sha'], self.bound['initial_a'])
        self.status['session_failure_acknowledged'] = True
        self.status['process_running'] = True
        with self.assertRaisesRegex(watch.DeploymentHold, 'watch_start_state'):
            watch.arm(self.bound['source_sha'], self.bound['initial_a'])
        self.status['process_running'] = False
        self.assertEqual(watch.arm(self.bound['source_sha'], self.bound['initial_a'])['state'], 'armed')
        with patch('install_controller.authorize_live_on'), patch.object(watch, 'session', return_value={'gate':'PP_LIVE_ON'}):
            self.assertEqual(watch.tick()['state'], 'running')

    def test_no_admission_without_qualified_archive_worker(self):
        watch.arm(self.bound['source_sha'], self.bound['initial_a'])
        self.worker.return_value = {'status': 'off'}
        with patch('install_controller.authorize_live_on') as mint:
            with self.assertRaisesRegex(watch.DeploymentHold, 'watch_archive_worker_unavailable'):
                watch.tick()
            mint.assert_not_called()

    def run_tick(self):
        # Exercise run()'s persistent hold policy as well as tick(), without
        # requiring root, an installed controller, Docker or a live database.
        with (
            patch.object(watch, 'LOCK', self.intent.parent / 'lock'),
            patch.object(watch.os, 'geteuid', return_value=0),
            patch.object(watch.HostBinding, 'from_marker', return_value=SimpleNamespace(
                hostname=watch.BENCHMARK_INSTANCE)),
            patch.object(Path, 'lstat', return_value=SimpleNamespace(
                st_mode=stat.S_IFDIR | 0o700, st_uid=0)),
            patch.object(watch.os, 'fstat', return_value=SimpleNamespace(
                st_mode=stat.S_IFREG | 0o600, st_uid=0)),
        ):
            return watch.run('tick')

    def running_intent(self):
        self.intent.write_text(json.dumps(dict(
            version=1, state='armed', binding=self.bound, boot_id='boot-id')))
        self.status.update(collector_enabled=True, process_running=True,
                           watch_explicit_off=False)

    def test_status_503_retries_fresh_proofs_without_changing_owned_session(self):
        self.running_intent()
        owner = 'same-owned-session'
        calls = []

        def operator(_token, path):
            calls.append(path)
            if len(calls) == 1:
                raise HTTPError('private-status', 503, 'unavailable', {}, None)
            if path == '/collector/status':
                return dict(self.status)
            self.assertEqual(path, '/collector/watch/renew')
            return dict(origin_id=watch.DISPLAY_ORIGIN, epoch=6, owner=owner)

        with (patch.object(watch, '_operator', side_effect=operator),
              patch('install_controller.authorize_live_on') as mint,
              patch.object(watch, 'session') as session):
            self.assertEqual(self.run_tick(), dict(
                state='unavailable', reason='watch_status_unavailable'))
            self.assertEqual(json.loads(self.intent.read_text())['state'], 'armed')
            self.worker.assert_not_called()
            result = self.run_tick()
            self.assertEqual((result['owner'], result['epoch']), (owner, 6))
            self.worker.assert_called_once()
            self.assertEqual(calls, ['/collector/status', '/collector/status', '/collector/watch/renew'])
            mint.assert_not_called()
            session.assert_not_called()

    def test_prolonged_503_does_not_extend_or_restart_expired_lease(self):
        self.running_intent()
        with (patch.object(watch, '_operator', side_effect=HTTPError(
                'private-status', 503, 'unavailable', {}, None)) as operator,
              patch('install_controller.authorize_live_on') as mint,
              patch.object(watch, 'session') as session):
            for _ in range(10):
                self.assertEqual(self.run_tick()['state'], 'unavailable')
            self.assertTrue(all(call.args[1] == '/collector/status' for call in operator.call_args_list))
            self.status.update(collector_enabled=False, lease_expired=True)
            operator.side_effect = None
            operator.return_value = self.status
            with self.assertRaisesRegex(watch.DeploymentHold, 'watch_inconsistent_writer'):
                self.run_tick()
            self.assertEqual(json.loads(self.intent.read_text())['state'], 'held')
            mint.assert_not_called()
            session.assert_not_called()

    def test_explicit_off_after_503_disarms_without_renewal(self):
        self.running_intent()
        with patch.object(watch, '_operator', side_effect=HTTPError(
                'private-status', 503, 'unavailable', {}, None)):
            self.run_tick()
        self.status['watch_explicit_off'] = True
        with patch.object(watch, '_operator', return_value=self.status) as operator:
            self.assertEqual(self.run_tick(), {'state': 'off'})
            operator.assert_called_once_with('private-generated-test', '/collector/status')
        self.assertFalse(self.intent.exists())

    def test_auth_and_renew_refusals_remain_terminal(self):
        for stage, code in (('status', 401), ('status', 403), ('status', 409),
                            ('renew', 409), ('renew', 503)):
            with self.subTest(stage=stage, code=code):
                self.running_intent()

                def operator(_token, path):
                    if path == '/collector/status' and stage != 'status':
                        return dict(self.status)
                    raise HTTPError('private-operator', code, 'refused', {}, None)

                with patch.object(watch, '_operator', side_effect=operator):
                    with self.assertRaises(HTTPError):
                        self.run_tick()
                self.assertEqual(json.loads(self.intent.read_text())['state'], 'held')

    def test_transferred_owner_cannot_be_renewed_or_restarted(self):
        self.running_intent()
        with patch.object(watch, '_operator', side_effect=HTTPError(
                'private-status', 503, 'unavailable', {}, None)):
            self.run_tick()
        # A new UUID can own the same generation. Status alone cannot grant
        # the old process authority: renewal still compares its exact UUID.
        self.status['epoch'] = 8

        def operator(_token, path):
            if path == '/collector/status':
                return dict(self.status)
            raise HTTPError('private-renew', 409, 'owner transferred', {}, None)

        with (patch.object(watch, '_operator', side_effect=operator),
              patch('install_controller.authorize_live_on') as mint,
              patch.object(watch, 'session') as session):
            with self.assertRaises(HTTPError):
                self.run_tick()
            mint.assert_not_called()
            session.assert_not_called()
        self.assertEqual(json.loads(self.intent.read_text())['state'], 'held')

    def test_source_worker_and_origin_drift_still_hold_after_transient(self):
        for kind in ('source', 'worker', 'origin'):
            with self.subTest(kind=kind):
                self.running_intent()
                with patch.object(watch, '_operator', side_effect=HTTPError(
                        'private-status', 503, 'unavailable', {}, None)):
                    self.run_tick()
                if kind == 'source':
                    doc = json.loads(self.intent.read_text())
                    doc['binding']['source_sha'] = 'b' * 40
                    self.intent.write_text(json.dumps(doc))
                elif kind == 'worker':
                    self.worker.return_value = dict(status='running', source_sha='b' * 40)
                else:
                    self.status['origin_id'] = 'another-origin'
                with self.assertRaises(watch.DeploymentHold):
                    self.run_tick()
                self.assertEqual(json.loads(self.intent.read_text())['state'], 'held')
                self.worker.return_value = dict(status='running', source_sha='a' * 40)
                self.status['origin_id'] = watch.DISPLAY_ORIGIN
