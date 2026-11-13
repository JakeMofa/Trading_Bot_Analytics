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


@unittest.skipUnless(sys.platform=='linux' and os.geteuid()==0,'requires isolated Linux root fixture')
class AuthorizedKeyAccess(unittest.TestCase):
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
