"""Isolated Linux-root proof of the operator UID to root secret boundary."""
from __future__ import annotations

import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import install_storage_auth as target


@unittest.skipUnless(sys.platform == 'linux' and os.geteuid() == 0,
                     'requires isolated Linux root fixture')
class RootStorageAuthInstall(unittest.TestCase):
    def test_operator_stage_becomes_root_only_without_touching_history(self):
        with tempfile.TemporaryDirectory(prefix='tradebot-pp-auth-install-') as folder:
            base = Path(folder)
            stage = base / 'stage'
            cloud = base / 'cloud'
            lockdir = base / 'run'
            for directory in (stage, cloud, lockdir):
                directory.mkdir(mode=0o700)
            os.chown(stage, 10001, 10001)
            lock = lockdir / 'controller.lock'
            lock.write_bytes(b'')
            lock.chmod(0o600)
            uid = str(uuid.uuid4())
            values = {
                'pp_storage_api_key': b'sb_publishable_' + b'p' * 32 + b'\n',
                'supabase_auth_email': b'archive-pp@example.invalid\n',
                'supabase_auth_password': b'a' * 64 + b'\n',
                'supabase_auth_uid': uid.encode() + b'\n',
            }
            for name, content in values.items():
                path = stage / name
                path.write_bytes(content)
                os.chown(path, 10001, 10001)
                path.chmod(0o400)
            status = stage / 'status'
            status.write_bytes(b'CREATED_VERIFIED_RESPONSE\n')
            os.chown(status, 10001, 10001)
            status.chmod(0o400)
            for name, mode in (('pp_history_dsn', 0o600),
                               ('pp_history_ca', 0o644)):
                path = cloud / name
                path.write_bytes(b'generated-history-file')
                path.chmod(mode)
            original = {(cloud / name).name: (cloud / name).stat().st_ino
                        for name in ('pp_history_dsn', 'pp_history_ca')}
            result = target.install(uid, stage=stage, cloud=cloud, lock=lock,
                                    stage_uid=10001, check_host=False)
            self.assertEqual(result['cloud_calls'], 0)
            self.assertFalse(stage.exists())
            for name, content in values.items():
                path = cloud / name
                self.assertEqual(path.read_bytes(), content)
                self.assertEqual(path.stat().st_uid, 0)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            for name, inode in original.items():
                self.assertEqual((cloud / name).stat().st_ino, inode)


if __name__ == '__main__':
    unittest.main()
