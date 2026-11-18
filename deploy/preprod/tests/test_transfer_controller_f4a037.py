"""Offline checks for the exact f4a037 PP controller transfer; no VM contact."""

import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).parents[1]
REPO = Path(__file__).parents[3]
SPEC = importlib.util.spec_from_file_location('transfer_controller_f4a037',
                                               HERE / 'transfer_controller_f4a037.py')
transfer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(transfer)


class SuccessorTransferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        bundle_spec = importlib.util.spec_from_file_location('controller_bundle_f4a037',
                                                            HERE / 'controller_bundle.py')
        builder = importlib.util.module_from_spec(bundle_spec)
        bundle_spec.loader.exec_module(builder)
        cls.bundle = Path(cls.folder.name) / 'controller.pyz'
        cls.result = builder.build(cls.bundle)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def payload(self):
        return transfer.payload_for(self.bundle, REPO)

    def test_exact_source_bundle_and_members(self):
        self.assertEqual(transfer.SOURCE, 'f4a03703cc8552917b752ab0cacd6e1e7c5233ea')
        self.assertEqual(transfer.OLD, 'c3fac37cb56945ad74d41188b8e22013a199fe8d656b87be4f4154676d3c9479')
        self.assertEqual(self.result['sha256'], transfer.NEW)
        payload = self.payload()
        contents = transfer.decode_payload(io.BytesIO(payload))
        self.assertEqual(contents['controller.pyz'], self.bundle.read_bytes())
        self.assertEqual(set(contents), set(transfer.ORDER))
        self.assertLessEqual(len(payload), transfer.MAX_TOTAL + len(transfer.MAGIC) + 4 * len(transfer.ORDER))

    def test_wrong_bundle_and_changed_source_stop_before_transfer(self):
        with tempfile.TemporaryDirectory() as folder:
            wrong = Path(folder) / 'wrong.pyz'
            wrong.write_bytes(self.bundle.read_bytes() + b'changed')
            with self.assertRaisesRegex(transfer.TransferStop, 'local_source_mismatch'):
                transfer.payload_for(wrong, REPO)
            repo = Path(folder)
            source = repo / 'deploy' / 'preprod'
            source.mkdir(parents=True)
            for name in transfer.FILES:
                (source / name).write_bytes((HERE / name).read_bytes())
            (source / 'linux_actions.py').write_bytes(b'changed')
            with self.assertRaisesRegex(transfer.TransferStop, 'local_source_mismatch'):
                transfer.payload_for(self.bundle, repo)

    def test_wrong_wire_digest_stops_before_host_checks(self):
        damaged = bytearray(self.payload())
        damaged[-1] ^= 1
        with patch.object(transfer.os, 'geteuid', return_value=0), \
             patch.object(transfer, 'checked_host') as host:
            with self.assertRaisesRegex(transfer.TransferStop, 'transfer_digest_mismatch'):
                transfer.receive_and_install(io.BytesIO(damaged))
            host.assert_not_called()

    def test_wrong_host_and_existing_authority_stop_before_stage(self):
        payload = self.payload()
        with patch.object(transfer.os, 'geteuid', return_value=0), \
             patch.object(transfer, 'checked_host', side_effect=transfer.TransferStop('wrong_host_binding')), \
             patch.object(transfer.os, 'mkdir') as mkdir:
            with self.assertRaisesRegex(transfer.TransferStop, 'wrong_host_binding'):
                transfer.receive_and_install(io.BytesIO(payload))
            mkdir.assert_not_called()
        with tempfile.TemporaryDirectory() as folder:
            stage_parent = Path(folder)
            real_digest = transfer.digest
            def digest(data):
                return transfer.OLD if data == b'old' else real_digest(data)
            for name in ('authorization.json', 'live-enter.json', 'live-on.json',
                         'structured-probe.json', 'raw-archive-probe.json'):
                authority = stage_parent / name
                authority.write_text('{}')
                with self.subTest(authority=name), \
                     patch.object(transfer.os, 'geteuid', return_value=0), \
                     patch.object(transfer, 'checked_host'), \
                     patch.object(transfer, 'root_directory'), \
                     patch.object(transfer, 'root_file', return_value=b'old'), \
                     patch.object(transfer, 'digest', side_effect=digest), \
                     patch.object(transfer.os, 'mkdir') as mkdir:
                    with self.assertRaisesRegex(transfer.TransferStop, 'unused_authority_present'):
                        transfer.receive_and_install(io.BytesIO(payload), stage_parent=stage_parent)
                    mkdir.assert_not_called()
                authority.unlink()

    def test_active_live_transition_and_old_controller_mismatch_stop(self):
        payload = self.payload()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            active = root / 'active-live-transition.json'
            active.write_text(json.dumps({'state': 'ready_off'}))
            real_digest = transfer.digest

            def digest(data):
                return transfer.OLD if data == b'old' else real_digest(data)

            with patch.object(transfer.os, 'geteuid', return_value=0), \
                 patch.object(transfer, 'checked_host'), \
                 patch.object(transfer, 'root_directory'), \
                 patch.object(transfer, 'root_file', side_effect=lambda path, **_: b'old' if path == transfer.CURRENT else path.read_bytes()), \
                 patch.object(transfer, 'digest', side_effect=digest), \
                 patch.object(transfer, 'ACTIVE', active), \
                 patch.object(transfer.os, 'mkdir') as mkdir:
                with self.assertRaisesRegex(transfer.TransferStop, 'active_live_transition'):
                    transfer.receive_and_install(io.BytesIO(payload), stage_parent=root)
                mkdir.assert_not_called()
            with patch.object(transfer.os, 'geteuid', return_value=0), \
                 patch.object(transfer, 'checked_host'), \
                 patch.object(transfer, 'root_directory'), \
                 patch.object(transfer, 'root_file', return_value=b'wrong-old-code'), \
                 patch.object(transfer.os, 'mkdir') as mkdir:
                with self.assertRaisesRegex(transfer.TransferStop, 'unexpected_installed_controller'):
                    transfer.receive_and_install(io.BytesIO(payload), stage_parent=root)
                mkdir.assert_not_called()

    def test_installer_result_retains_exact_old_code_and_creates_no_authority(self):
        payload = self.payload()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stage_parent = root / 'run'
            stage_parent.mkdir()
            stage = stage_parent / 'stage'
            current = root / 'controller.pyz'
            prior = root / 'prior.pyz'
            current.write_bytes(b'old')

            def installer(command, **kwargs):
                self.assertEqual(command[1], '-BEs')
                self.assertEqual((stage / 'controller.pyz').read_bytes(), self.bundle.read_bytes())
                self.assertTrue((stage / 'deploy-key.pub').read_bytes().startswith(b'ssh-ed25519 '))
                prior.write_bytes(current.read_bytes())
                current.write_bytes((stage / 'controller.pyz').read_bytes())
                return SimpleNamespace(returncode=0)

            real_digest = transfer.digest

            def digest(data):
                return transfer.OLD if data == b'old' else real_digest(data)

            with patch.object(transfer.os, 'geteuid', return_value=0), \
                 patch.object(transfer, 'checked_host'), \
                 patch.object(transfer, 'root_directory'), \
                 patch.object(transfer, 'root_file', side_effect=lambda path, **_: path.read_bytes()), \
                 patch.object(transfer, 'public_key', return_value=b'ssh-ed25519 test-key\n'), \
                 patch.object(transfer, 'stage_is_safe', return_value=True), \
                 patch.object(transfer, 'ACTIVE', root / 'no-active.json'), \
                 patch.object(transfer, 'digest', side_effect=digest):
                result = transfer.receive_and_install(io.BytesIO(payload), stage_parent=stage_parent,
                                                      stage=stage, current=current, old_saved=prior,
                                                      invoke=installer)
            self.assertEqual(result, {'gate': 'CONTROLLER_INSTALLED_NOT_AUTHORIZED',
                                      'source_sha': transfer.SOURCE, 'previous_sha256': transfer.OLD,
                                      'controller_sha256': transfer.NEW, 'database_changed': False,
                                      'authority_created': False})
            self.assertEqual(current.read_bytes(), self.bundle.read_bytes())
            self.assertEqual(prior.read_bytes(), b'old')
            self.assertFalse(stage.exists())


if __name__ == '__main__':
    unittest.main()
