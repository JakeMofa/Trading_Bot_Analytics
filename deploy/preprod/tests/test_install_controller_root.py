"""Required Linux-root fixture: no host users, SSH server or installed paths."""
from pathlib import Path
import os
import stat
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).parents[1]))
import install_controller as installer
import raw_archive_probe_control as raw_probe
import transfer_controller as transfer
import install_storage_auth as storage_installer


@unittest.skipUnless(sys.platform=='linux' and os.geteuid()==0,'requires isolated Linux root fixture')
class AuthorizedKeyAccess(unittest.TestCase):
    def test_pp_storage_auth_operator_stage_becomes_root_only(self):
        import uuid
        with tempfile.TemporaryDirectory(prefix='tradebot-pp-auth-install-') as folder:
            base=Path(folder);stage=base/'stage';cloud=base/'cloud';lockdir=base/'run'
            for directory in (stage,cloud,lockdir):directory.mkdir(mode=0o700)
            os.chown(stage,10001,10001)
            lock=lockdir/'controller.lock';lock.write_bytes(b'');lock.chmod(0o600)
            uid=str(uuid.uuid4())
            values={'pp_storage_api_key':b'sb_publishable_'+b'p'*32+b'\n',
                    'supabase_auth_email':b'archive-pp@example.invalid\n',
                    'supabase_auth_password':b'a'*64+b'\n',
                    'supabase_auth_uid':uid.encode()+b'\n'}
            for name,content in {**values,'status':b'CREATED_VERIFIED_RESPONSE\n'}.items():
                path=stage/name;path.write_bytes(content)
                os.chown(path,10001,10001);path.chmod(0o400)
            for name,mode in (('pp_history_dsn',0o600),('pp_history_ca',0o644)):
                path=cloud/name;path.write_bytes(b'generated-history-file');path.chmod(mode)
            history={name:(cloud/name).stat().st_ino for name in ('pp_history_dsn','pp_history_ca')}
            result=storage_installer.install(uid,stage=stage,cloud=cloud,lock=lock,
                                             stage_uid=10001,check_host=False)
            self.assertEqual(result['cloud_calls'],0)
            self.assertFalse(stage.exists())
            for name,content in values.items():
                path=cloud/name
                self.assertEqual(path.read_bytes(),content)
                self.assertEqual(path.stat().st_uid,0)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
            for name,inode in history.items():
                self.assertEqual((cloud/name).stat().st_ino,inode)

    def test_transfer_stage_is_root_only_and_exclusive(self):
        with tempfile.TemporaryDirectory(prefix='tradebot-pp-transfer-') as folder:
            base=Path(folder);base.chmod(0o700)
            transfer.root_directory(base)
            stage=base/'stage'
            os.mkdir(stage,0o700)
            self.assertTrue(transfer.stage_is_safe(stage))
            target=stage/'controller.pyz'
            transfer.write_exclusive(target,b'generated-controller-code')
            self.assertEqual(target.stat().st_uid,0)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode),0o600)
            with self.assertRaises(FileExistsError):
                transfer.write_exclusive(target,b'other')
            alias=stage/'alias.pyz';alias.symlink_to(target)
            with self.assertRaises(FileExistsError):
                transfer.write_exclusive(alias,b'other')
            self.assertEqual(target.read_bytes(),b'generated-controller-code')

    def test_raw_probe_local_credential_staging_is_root_only_and_short_lived(self):
        with tempfile.TemporaryDirectory(prefix='tradebot-raw-secret-') as folder:
            base=Path(folder);base.chmod(0o700)
            source=base/'lifecycle_dsn'
            staged=base/'probe-local-dsn'
            source.write_bytes(b'generated-pp-local-dsn')
            os.chown(source,10001,10001)
            source.chmod(0o400)
            with raw_probe._stage_local_secret(source,staged):
                self.assertEqual(staged.read_bytes(),b'generated-pp-local-dsn')
                self.assertEqual(staged.stat().st_uid,0)
                self.assertEqual(stat.S_IMODE(staged.stat().st_mode),0o600)
                self.assertEqual(stat.S_IMODE(source.stat().st_mode),0o400)
            self.assertFalse(staged.exists())
            self.assertEqual(source.read_bytes(),b'generated-pp-local-dsn')

    def test_effective_deploy_uid_can_read_but_cannot_modify_authorized_key(self):
        import pwd
        nobody=pwd.getpwnam('nobody')
        with tempfile.TemporaryDirectory(prefix='tradebot-authorized-key-') as folder:
            home=Path(folder);home.chmod(0o755)
            installer.install_authorized_key(home,'ssh-ed25519 '+('A'*68)+' generated-fixture')
            path=home/'.ssh/authorized_keys'
            self.assertEqual(path.stat().st_uid,0)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o644)
            self.assertEqual((home/'.ssh').stat().st_uid,0)
            self.assertEqual(stat.S_IMODE((home/'.ssh').stat().st_mode),0o755)
            def unprivileged():
                os.setgroups([]);os.setgid(nobody.pw_gid);os.setuid(nobody.pw_uid)
            program="""from pathlib import Path
import os,sys
p=Path(sys.argv[1])
assert p.read_text().startswith('restrict,command=')
assert not os.access(p,os.W_OK) and not os.access(p.parent,os.W_OK)
try:
    p.open('a').close()
except PermissionError:
    print('READ_ONLY_KEY_PASS')
else:
    raise SystemExit('deployment UID can modify authorized keys')
"""
            result=subprocess.run([sys.executable,'-I','-c',program,str(path)],
                cwd='/tmp',env={},preexec_fn=unprivileged,capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout.strip(),'READ_ONLY_KEY_PASS')
            self.assertEqual(result.stderr,'')
