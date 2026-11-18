"""Generated transfer and fail-closed staging checks; never contact a VM."""

import importlib.util
import io
from pathlib import Path
import stat
import struct
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import zipfile


SPEC = importlib.util.spec_from_file_location(
    'transfer_controller', Path(__file__).parents[1] / 'transfer_controller.py')
transfer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(transfer)


def wire(contents):
    body = bytearray(transfer.MAGIC)
    for name in transfer.ORDER:
        data = contents[name]
        body.extend(struct.pack('>I', len(data)))
        body.extend(data)
    return bytes(body)


class TransferControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle_folder = tempfile.TemporaryDirectory()
        spec = importlib.util.spec_from_file_location(
            'controller_bundle_for_transfer', Path(__file__).parents[1] / 'controller_bundle.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        bundle_path = Path(cls.bundle_folder.name) / 'controller.pyz'
        builder.build(bundle_path)
        cls.valid_bundle = bundle_path.read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.bundle_folder.cleanup()

    def setUp(self):
        self.contents = {name: bytes.fromhex(transfer.HASHES[name]) for name in transfer.ORDER}
        self.contents['controller.pyz'] = self.valid_bundle
        self.real_digest = transfer.digest
        self.digest_patch = patch.object(transfer, 'digest', side_effect=self._digest)
        self.digest_patch.start()

    def tearDown(self):
        self.digest_patch.stop()

    def _digest(self, data):
        for name, value in self.contents.items():
            if data == value:
                return transfer.HASHES[name]
        return self.real_digest(data)

    def test_exact_bounded_payload_decodes_without_extracting_archive(self):
        self.assertEqual(transfer.decode_payload(io.BytesIO(wire(self.contents))), self.contents)

    def test_corruption_truncation_extra_bytes_and_oversize_stop(self):
        correct = wire(self.contents)
        bad = [correct[:-1], correct + b'!', correct.replace(transfer.MAGIC, b'wrong', 1)]
        offset = len(transfer.MAGIC)
        bad.append(correct[:offset] + struct.pack('>I', transfer.MAX_FILE + 1)
                   + correct[offset + 4:])
        damaged = bytearray(correct)
        damaged[offset + 4] ^= 1
        bad.append(bytes(damaged))
        for payload in bad:
            with self.subTest(size=len(payload)), self.assertRaises(transfer.TransferStop):
                transfer.decode_payload(io.BytesIO(payload))

    def test_wrong_zip_member_set_rejected_before_stage(self):
        bad_zip = io.BytesIO()
        with zipfile.ZipFile(bad_zip, 'w') as archive:
            archive.writestr('unexpected.py', 'pass')
        self.contents['controller.pyz'] = bad_zip.getvalue()
        with self.assertRaises(transfer.TransferStop):
            transfer.decode_payload(io.BytesIO(wire(self.contents)))

    def test_failed_payload_never_reaches_host_install(self):
        with patch.object(transfer.os, 'geteuid', return_value=0), \
             patch.object(transfer, 'root_directory') as directory, \
             patch.object(transfer, 'root_file') as root_file:
            with self.assertRaises(transfer.TransferStop):
                transfer.receive_and_install(io.BytesIO(wire(self.contents)[:-2]))
            directory.assert_not_called()
            root_file.assert_not_called()

    def test_wrong_host_and_old_hash_stop_before_staging(self):
        payload = io.BytesIO(wire(self.contents))
        with patch.object(transfer.os, 'geteuid', return_value=0), \
             patch.object(transfer, 'checked_host', side_effect=transfer.TransferStop('wrong_host')), \
             patch.object(transfer, 'root_directory') as directory:
            with self.assertRaises(transfer.TransferStop):
                transfer.receive_and_install(payload)
            directory.assert_not_called()
        with patch.object(transfer.os, 'geteuid', return_value=0), \
             patch.object(transfer, 'checked_host'), \
             patch.object(transfer, 'root_directory'), \
             patch.object(transfer, 'root_file', return_value=b'unexpected-old-controller'), \
             patch.object(transfer.os, 'mkdir') as mkdir:
            with self.assertRaises(transfer.TransferStop):
                transfer.receive_and_install(io.BytesIO(wire(self.contents)))
            mkdir.assert_not_called()

    def test_host_marker_requires_pp_and_disabled_flags(self):
        safe = {'environment': 'preprod', 'project': 'Tradebot',
                'live_collector_authorized': False, 'paid_ai_authorized': False,
                'production_data_copied': False}
        import json
        with patch.object(transfer, 'root_file', return_value=json.dumps(safe).encode()), \
             patch.object(transfer.socket, 'gethostname', return_value='tradebot-preprod-01'):
            transfer.checked_host()
            for key, value in [('environment', 'production'),
                               ('live_collector_authorized', True),
                               ('production_data_copied', True)]:
                with self.subTest(key=key):
                    changed = dict(safe, **{key: value})
                    with patch.object(transfer, 'root_file', return_value=json.dumps(changed).encode()):
                        with self.assertRaises(transfer.TransferStop):
                            transfer.checked_host()

    def test_success_preserves_old_code_and_removes_only_stage(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stage_parent = root / 'run'
            stage_parent.mkdir()
            stage = stage_parent / 'stage'
            current = root / 'controller.pyz'
            old_saved = root / 'old.pyz'
            current.write_bytes(b'old-code')
            active = root / 'no-active.json'
            key_file = root / 'authorized_keys'
            key_file.write_text('test-public-only')

            def installed(command, **kwargs):
                self.assertEqual(command[1], '-BEs')
                self.assertTrue((stage / 'controller.pyz').is_file())
                self.assertTrue((stage / 'deploy-key.pub').is_file())
                self.assertNotIn(b'PRIVATE', (stage / 'deploy-key.pub').read_bytes())
                old_saved.write_bytes(current.read_bytes())
                current.write_bytes(b'new-code')
                return SimpleNamespace(returncode=0)

            def fake_digest(data):
                if data == b'old-code':
                    return transfer.OLD
                if data == b'new-code':
                    return transfer.NEW
                return self._digest(data)

            with patch.object(transfer.os, 'geteuid', return_value=0), \
                 patch.object(transfer, 'checked_host'), \
                 patch.object(transfer, 'root_directory'), \
                 patch.object(transfer, 'root_file', side_effect=lambda path, **_: path.read_bytes()), \
                 patch.object(transfer, 'public_key', return_value=b'ssh-ed25519 test-public-only\n'), \
                 patch.object(transfer, 'stage_is_safe', return_value=True), \
                 patch.object(transfer, 'ACTIVE', active), \
                 patch.object(transfer, 'digest', side_effect=fake_digest):
                result = transfer.receive_and_install(
                    io.BytesIO(wire(self.contents)), stage_parent=stage_parent,
                    stage=stage, current=current, old_saved=old_saved,
                    key_file=key_file, invoke=installed)
            self.assertEqual(result['gate'], 'CONTROLLER_INSTALLED_NOT_AUTHORIZED')
            self.assertFalse(result['authority_created'])
            self.assertEqual(current.read_bytes(), b'new-code')
            self.assertEqual(old_saved.read_bytes(), b'old-code')
            self.assertFalse(stage.exists())

    def test_installer_timeout_cleans_stage_and_cannot_claim_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stage_parent = root / 'run'
            stage_parent.mkdir()
            stage = stage_parent / 'stage'
            current = root / 'controller.pyz'
            current.write_bytes(b'old-code')
            active = root / 'no-active.json'

            def fake_digest(data):
                return transfer.OLD if data == b'old-code' else self._digest(data)

            def timed_out(*_, **__):
                raise subprocess.TimeoutExpired('installer', 90)

            with patch.object(transfer.os, 'geteuid', return_value=0), \
                 patch.object(transfer, 'checked_host'), \
                 patch.object(transfer, 'root_directory'), \
                 patch.object(transfer, 'root_file', side_effect=lambda path, **_: path.read_bytes()), \
                 patch.object(transfer, 'public_key', return_value=b'ssh-ed25519 test-only\n'), \
                 patch.object(transfer, 'stage_is_safe', return_value=True), \
                 patch.object(transfer, 'ACTIVE', active), \
                 patch.object(transfer, 'digest', side_effect=fake_digest):
                with self.assertRaises(subprocess.TimeoutExpired):
                    transfer.receive_and_install(
                        io.BytesIO(wire(self.contents)), stage_parent=stage_parent,
                        stage=stage, current=current, old_saved=root / 'old.pyz',
                        invoke=timed_out)
            self.assertFalse(stage.exists())
            self.assertEqual(current.read_bytes(), b'old-code')

    def test_unused_authority_blocks_before_staging(self):
        for name in ('authorization.json', 'live-enter.json', 'live-on.json',
                     'structured-probe.json', 'raw-archive-probe.json'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                stage_parent = root / 'run'
                stage_parent.mkdir()
                (stage_parent / name).write_text('{}')

                def fake_digest(data):
                    return transfer.OLD if data == b'old-code' else self._digest(data)

                with patch.object(transfer.os, 'geteuid', return_value=0), \
                     patch.object(transfer, 'checked_host'), \
                     patch.object(transfer, 'root_directory'), \
                     patch.object(transfer, 'root_file', return_value=b'old-code'), \
                     patch.object(transfer, 'digest', side_effect=fake_digest), \
                     patch.object(transfer.os, 'mkdir') as mkdir:
                    with self.assertRaises(transfer.TransferStop):
                        transfer.receive_and_install(io.BytesIO(wire(self.contents)),
                                                     stage_parent=stage_parent)
                    mkdir.assert_not_called()

    def test_root_only_and_exclusive_nofollow_stage_write(self):
        with patch.object(transfer.os, 'geteuid', return_value=1000), \
             patch.object(transfer, 'decode_payload') as decode:
            with self.assertRaises(transfer.TransferStop):
                transfer.receive_and_install(io.BytesIO(b''))
            decode.assert_not_called()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'source.py'
            transfer.write_exclusive(path, b'code only')
            self.assertEqual(path.read_bytes(), b'code only')
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError):
                transfer.write_exclusive(path, b'replaced')
            link = root / 'link.py'
            link.symlink_to(path)
            with self.assertRaises(FileExistsError):
                transfer.write_exclusive(link, b'replaced')
            self.assertEqual(path.read_bytes(), b'code only')

    def test_exact_existing_public_key_only(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'authorized_keys'
            key = 'ssh-ed25519 ' + ('A' * 68)
            with patch.object(transfer, 'root_file', side_effect=lambda _: path.read_bytes()):
                path.write_text(transfer.FORCED_PREFIX + key + '\n')
                self.assertEqual(transfer.public_key(path), (key + '\n').encode())
                path.write_text(transfer.FORCED_PREFIX + key + '\n' + key + '\n')
                with self.assertRaises(transfer.TransferStop):
                    transfer.public_key(path)
                path.write_text(key + '\n')
                with self.assertRaises(transfer.TransferStop):
                    transfer.public_key(path)

    def test_exact_source_and_bundle_constants_are_real(self):
        # Works in shallow CI; pinned digests prevent local edits from shipping.
        repo = Path(__file__).parents[3]
        with tempfile.TemporaryDirectory() as folder:
            bundle = Path(folder) / 'bundle.pyz'
            import sys
            sys.path.insert(0, str(Path(__file__).parents[1]))
            try:
                import controller_bundle
                info = controller_bundle.build(bundle)
            finally:
                sys.path.pop(0)
            self.assertEqual(info['sha256'], transfer.NEW)
            actual = transfer.payload_for(bundle, repo)
            self.assertLess(len(actual), transfer.MAX_TOTAL)
            self.assertEqual(transfer.decode_payload(io.BytesIO(actual))['controller.pyz'],
                             bundle.read_bytes())
            bundle.write_bytes(b'changed')
            with self.assertRaises(transfer.TransferStop):
                transfer.payload_for(bundle, repo)

    def test_changed_checkout_source_cannot_enter_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'deploy' / 'preprod'
            source.mkdir(parents=True)
            real_source = Path(__file__).parents[1]
            for name in transfer.FILES:
                (source / name).write_bytes((real_source / name).read_bytes())
            bundle = root / 'controller.pyz'
            bundle.write_bytes(self.valid_bundle)
            transfer.payload_for(bundle, root)
            (source / 'install_controller.py').write_bytes(b'changed')
            with self.assertRaises(transfer.TransferStop):
                transfer.payload_for(bundle, root)
            (source / 'install_controller.py').unlink()
            (source / 'install_controller.py').symlink_to(real_source / 'install_controller.py')
            with self.assertRaises(transfer.TransferStop):
                transfer.payload_for(bundle, root)


if __name__ == '__main__':
    unittest.main()
