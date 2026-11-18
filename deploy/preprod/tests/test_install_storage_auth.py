"""Offline PP Storage Auth installation safety tests; all values are synthetic."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import install_storage_auth as target


class StorageAuthInstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.stage = self.base / 'stage'
        self.cloud = self.base / 'cloud'
        self.lockdir = self.base / 'run'
        for folder in (self.stage, self.cloud, self.lockdir):
            folder.mkdir(mode=0o700)
        self.lock = self.lockdir / 'controller.lock'
        self.lock.write_bytes(b'')
        self.lock.chmod(0o600)
        self.uid = str(uuid.uuid4())
        self.values = {
            'pp_storage_api_key': b'sb_publishable_' + b'p' * 32 + b'\n',
            'supabase_auth_email': b'archive-pp@example.invalid\n',
            'supabase_auth_password': b'a' * 64 + b'\n',
            'supabase_auth_uid': self.uid.encode() + b'\n',
        }
        for name, value in self.values.items():
            path = self.stage / name
            path.write_bytes(value)
            path.chmod(0o400)
        (self.stage / 'status').write_bytes(b'CREATED_VERIFIED_RESPONSE\n')
        (self.stage / 'status').chmod(0o400)
        (self.cloud / 'pp_history_dsn').write_bytes(b'postgresql://fake\n')
        (self.cloud / 'pp_history_dsn').chmod(0o600)
        (self.cloud / 'pp_history_ca').write_bytes(b'FAKE CERTIFICATE\n')
        (self.cloud / 'pp_history_ca').chmod(0o644)
        self.history = {
            name: (self.cloud / name).read_bytes()
            for name in ('pp_history_dsn', 'pp_history_ca')
        }

    def run_install(self):
        return target.install(self.uid, stage=self.stage, cloud=self.cloud,
                              lock=self.lock, stage_uid=os.geteuid(),
                              root_uid=os.geteuid(), check_host=False)

    def assert_history(self):
        for name, content in self.history.items():
            self.assertEqual((self.cloud / name).read_bytes(), content)

    def test_success_installs_only_four_files_without_a_cloud_call(self):
        result = self.run_install()
        self.assertEqual(result['result'], 'PP_STORAGE_AUTH_INSTALLED')
        self.assertEqual(result['cloud_calls'], 0)
        self.assertEqual(result['retirement'], 'off')
        self.assertFalse(self.stage.exists())
        for name, value in self.values.items():
            path = self.cloud / name
            self.assertEqual(path.read_bytes(), value)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(value.decode().strip(), repr(result))
        self.assert_history()
        with self.assertRaises(target.InstallStop):
            self.run_install()

    def test_wrong_uid_and_unsafe_stage_leave_destinations_absent(self):
        with self.assertRaises(target.InstallStop):
            target.install(str(uuid.uuid4()), stage=self.stage, cloud=self.cloud,
                           lock=self.lock, stage_uid=os.geteuid(),
                           root_uid=os.geteuid(), check_host=False)
        (self.stage / 'supabase_auth_password').chmod(0o644)
        with self.assertRaises(target.InstallStop):
            self.run_install()
        for name in self.values:
            self.assertFalse((self.cloud / name).exists())
        self.assert_history()

    def test_unconfirmed_creation_stops_before_install(self):
        (self.stage / 'status').chmod(0o600)
        with self.assertRaises(target.InstallStop):
            self.run_install()
        (self.stage / 'status').chmod(0o600)
        (self.stage / 'status').write_bytes(b'UNCONFIRMED_CREATE\n')
        (self.stage / 'status').chmod(0o400)
        with self.assertRaises(target.InstallStop):
            self.run_install()
        for name in self.values:
            self.assertFalse((self.cloud / name).exists())

    def test_symlink_alias_and_existing_partial_install_stop(self):
        (self.stage / 'supabase_auth_uid').unlink()
        (self.stage / 'supabase_auth_uid').symlink_to(
            self.stage / 'supabase_auth_password')
        with self.assertRaises(target.InstallStop):
            self.run_install()
        (self.stage / 'supabase_auth_uid').unlink()
        (self.stage / 'supabase_auth_uid').write_bytes(self.values['supabase_auth_uid'])
        (self.stage / 'supabase_auth_uid').chmod(0o400)
        (self.cloud / 'pp_storage_api_key').write_bytes(b'partial')
        (self.cloud / 'pp_storage_api_key').chmod(0o600)
        with self.assertRaises(target.InstallStop):
            self.run_install()
        self.assertEqual((self.cloud / 'pp_storage_api_key').read_bytes(), b'partial')
        self.assert_history()

    def test_interrupted_write_keeps_stage_and_blocks_retry(self):
        with mock.patch.object(target.os, 'fsync', side_effect=OSError('synthetic')):
            with self.assertRaises(OSError):
                self.run_install()
        self.assertTrue(self.stage.exists())
        self.assertTrue((self.cloud / 'pp_storage_api_key').exists())
        with self.assertRaises(target.InstallStop):
            self.run_install()
        self.assert_history()


if __name__ == '__main__':
    unittest.main()
