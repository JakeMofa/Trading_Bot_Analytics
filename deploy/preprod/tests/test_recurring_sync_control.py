import contextlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import structured_probe_control as sync
from controller import DeploymentHold


class RecurringControlTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        state = patch.object(sync, 'SYNC_STATE', Path(tmp.name)/'owner.json')
        state.start()
        self.addCleanup(state.stop)
        read = patch.object(sync, '_secure_file', side_effect=lambda path: (path.read_bytes(), None))
        read.start()
        self.addCleanup(read.stop)
        self.actions = MagicMock()
        self.actions.attempt_id = 'a'*32
        self.ctx = MagicMock()
        self.ctx.image = 'sha256:'+'d'*64
        self.ctx.request.source_sha = 'c'*40
        self.ctx.request.controller_sha256 = 'b'*64
        self.owner = dict(attempt_id=self.actions.attempt_id, image=self.ctx.image,
                          source_sha=self.ctx.request.source_sha)

    def test_forced_off_frees_one_owned_worker_and_reproves(self):
        from transition_control import _prove_off
        transition = MagicMock()
        transition._live_off.side_effect = [DeploymentHold('off_unproven'), None]
        budget = MagicMock()
        with patch.object(sync, 'recurring_control', side_effect=[
                {'status':'running', 'source_sha':'a'*40}, {'status':'off'}]) as control:
            _prove_off(transition, 'a'*40, budget)
        self.assertEqual(transition._live_off.call_count, 2)
        self.assertEqual([call.args[0] for call in control.call_args_list], ['status','stop'])
        self.assertTrue(all(call.args[1] is budget for call in control.call_args_list))

    def test_forced_off_preserves_other_release_and_propagates_failure(self):
        from transition_control import _prove_off
        transition = MagicMock()
        transition._live_off.side_effect = DeploymentHold('off_unproven')
        with patch.object(sync, 'recurring_control', return_value={
                'status':'running','source_sha':'c'*40}) as control:
            with self.assertRaisesRegex(DeploymentHold, 'source_mismatch'):
                _prove_off(transition, 'b'*40, MagicMock())
        self.assertEqual(control.call_count, 1)
        self.assertEqual(transition._live_off.call_count, 1)

    def test_start_proves_readiness_then_fences_deploy_until_stop(self):
        row = dict(Id='f'*64, State=dict(Running=True))
        with patch.object(sync, 'preflight', return_value=(self.ctx, self.actions, 'b'*64)), \
             patch.object(sync, '_stage_local_secret', return_value=contextlib.nullcontext()), \
             patch.object(sync, '_compose') as compose, \
             patch.object(sync, '_sync_container', return_value=row), \
             patch.object(sync.Budget, 'run', return_value=b'{"status": "structured_worker_ready"}\n'):
            self.assertEqual(sync.recurring_start(Path('bundle'))['status'], 'started')
        self.assertIn('TRADEBOT_PP_STRUCTURED_RECURRING=true', compose.call_args.args[-2])
        self.assertEqual(json.loads(sync.SYNC_STATE.read_text()), self.owner)
        with self.assertRaises(DeploymentHold):
            sync.fence_recurring_sync()
        with patch.object(sync, '_sync_container', side_effect=[row, None, None]):
            self.assertEqual(sync.recurring_control('stop', MagicMock())['status'], 'off')
        sync.fence_recurring_sync()

    def test_archive_and_sync_have_independent_owners_and_one_release_fence(self):
        from raw_archive_probe_control import recurring_start
        archive_state = sync.SYNC_STATE.with_name('archive.json')
        marker = b'{"status": "sealed_archive_worker_ready"}'
        row = dict(Id='f'*64, State=dict(Running=True))
        self.actions._json.return_value = {}
        with patch.object(sync, 'ARCHIVE_STATE', archive_state), \
             patch('raw_archive_probe_control.preflight', return_value=(self.ctx,self.actions,'b'*64)), \
             patch('raw_archive_probe_control._stage_local_secret', return_value=contextlib.nullcontext()), \
             patch('raw_archive_probe_control._compose') as compose, \
             patch('raw_archive_probe_profile.validate_recurring_profile'), \
             patch.object(sync, '_sync_container', return_value=row), \
             patch.object(sync.Budget, 'run', return_value=marker):
            sync._write_sync_owner(self.owner)
            self.assertEqual(recurring_start(Path('bundle'))['status'],'started')
            self.assertIn('sealed_archive', compose.call_args.args[-2])
            with self.assertRaises(DeploymentHold):
                sync.fence_recurring_sync()
            with patch.object(sync, '_sync_container', side_effect=[row,None,None]):
                sync.recurring_control('stop',MagicMock(),archive=True)
            self.assertFalse(archive_state.exists())
            self.assertTrue(sync.SYNC_STATE.exists())
            with self.assertRaises(DeploymentHold):
                sync.fence_recurring_sync()

    def test_foreign_or_unconfirmed_worker_keeps_fence(self):
        sync._write_sync_owner(self.owner)
        with patch.object(sync, '_sync_container', side_effect=DeploymentHold('mismatch')):
            with self.assertRaises(DeploymentHold):
                sync.recurring_control('stop', MagicMock())
        with self.assertRaises(DeploymentHold):
            sync.fence_recurring_sync()

    def test_controller_hash_mismatch_prevents_start(self):
        with patch.object(sync, 'preflight', return_value=(self.ctx,self.actions,'e'*64)), \
             patch.object(sync, '_compose') as compose:
            with self.assertRaises(DeploymentHold):
                sync.recurring_start(Path('bundle'))
        compose.assert_not_called()
        self.assertFalse(sync.SYNC_STATE.exists())


    def test_packaged_entry_reports_worker_fence_for_deploy_and_transition(self):
        import io
        import stat
        from types import SimpleNamespace
        import zipfile
        import controller_bundle

        bundle = sync.SYNC_STATE.parent / 'controller.pyz'
        controller_bundle.build(bundle)
        with zipfile.ZipFile(bundle) as archive:
            entry = compile(archive.read('__main__.py'), '__main__.py', 'exec')
        sync._write_sync_owner(self.owner)
        for command in ('transition-v1 leave', 'deploy-v1 preprod tradebot-preprod-01 '
                        + 'c'*40 + ' ' + 'd'*64 + ' ' + 'a'*64):
            out = io.StringIO()
            with self.subTest(command=command.split()[0]), contextlib.ExitStack() as ctx:
                for target, value in (
                    ('sys.argv', [str(bundle), command]), ('sys.stdout', out),
                ):
                    ctx.enter_context(patch(target, value))
                for target, value in (
                    ('os.geteuid', 0), ('controller.HostBinding.from_marker', object()),
                    ('os.open', 23), ('fcntl.flock', None), ('signal.signal', None),
                    ('os.fstat', SimpleNamespace(st_uid=0,st_mode=stat.S_IFREG | 0o600))
                ):
                    ctx.enter_context(patch(target, return_value=value))
                with self.assertRaises(SystemExit) as result:
                    exec(entry, {'__name__': '__main__'})
                self.assertEqual(result.exception.code, 1)
                self.assertEqual(json.loads(out.getvalue())['reason'],
                                 'stop_recurring_structured_sync_first')
