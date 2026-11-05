"""Linux permission fence and forward recovery using actual generated legacy."""
import hashlib
import json
import os
from pathlib import Path
import pwd
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_ab_application import legacy
TESTS=str(Path(__file__).resolve().parent)

CHILD = '''
import sys,os,json,sqlite3
sys.path.insert(0,sys.argv[1])
from test_ab_application import ApplicationStore,collector,iso,T,timedelta
root,legacy,mode=sys.argv[2:5]
if mode=='legacy':
    db=collector.connect(legacy)
    try:
        collector.save_observation(db,'m',iso(T+timedelta(seconds=10)),'book',{'old':True},iso(T))
        print('legacy-write',flush=True)
    finally:db.close()
    raise SystemExit(0)
if mode=='before':
    def fault(at):
        if at=='migration_before_commit':raise RuntimeError('before first acknowledgement')
    try:ApplicationStore(root,legacy,routing=True,fault=fault)
    except RuntimeError as error:
        assert str(error)=='before first acknowledgement',str(error)
        print('before-ack-hold',flush=True)
        raise SystemExit(71)
    raise AssertionError('injected migration failure missed')
s=ApplicationStore(root,legacy,routing=True)
db=s.connection()
if mode=='after':
    first=db.save_observation('m',iso(T+timedelta(seconds=2)),'book',{'new':1},iso(T))
    print(json.dumps({'acknowledged':first}),flush=True)
    s.protocol.fault=lambda at:os._exit(72) if at=='raw_committed' else None
    db.save_observation('m',iso(T+timedelta(seconds=3)),'book',{'new':2},iso(T))
else:
    assert len(db.execute('SELECT id FROM observations WHERE id>90').fetchall())==2
    assert db.execute("SELECT COUNT(*) FROM ab_events WHERE status='pending'").fetchone()[0]==0
    assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
    assert db.execute('SELECT outcome_observation_id FROM prediction_context_links').fetchone()[0]==90
    print('forward-recovered',flush=True)
    db.close();s.close()
'''


@unittest.skipUnless(sys.platform=='linux' and os.geteuid()==0,'Linux root UID fence')
class CutoverTests(unittest.TestCase):
    def test_before_and_after_acknowledgement_recovery(self):
        account=pwd.getpwnam('nobody')
        def demote():
            os.setgroups([])
            os.setgid(account.pw_gid)
            os.setuid(account.pw_uid)
        for mode in ('before','after'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory(prefix='generated-ab-cutover-') as folder:
                parent=Path(folder);parent.chmod(0o1777)
                # The exact export is private to the CI runner. Stage source
                # modules only so the unprivileged fixture UID can import them.
                source=parent/'source'
                backend=Path(__file__).resolve().parents[1]
                for group in ('app','prototype'):
                    target=source/'backend'/group
                    target.mkdir(parents=True,mode=0o755)
                    for module in (backend/group).glob('*.py'):
                        shutil.copyfile(module,target/module.name)
                tests=source/'backend/tests'
                tests.mkdir(parents=True)
                shutil.copyfile(Path(__file__).with_name('test_ab_application.py'),tests/'test_ab_application.py')
                child_tests=str(tests)
                path=parent/'generated-legacy.db';legacy(path)
                # Root-owned sticky parent prevents replacement by the old UID.
                # Root-owned read-only main prevents that UID opening a writer.
                path.chmod(0o444)
                root=parent/'generated-ab-new';root.mkdir(mode=0o700)
                before=hashlib.sha256(path.read_bytes()).hexdigest()
                denied=subprocess.run([sys.executable,'-c',CHILD,child_tests,str(root),str(path),'legacy'],
                                      preexec_fn=demote,capture_output=True,text=True,timeout=10)
                self.assertNotEqual(denied.returncode,0)
                self.assertIn('readonly',denied.stderr.lower())
                # Ordinary last-close cleanup after the failed old-UID reader;
                # no checkpoint pragma or sidecar removal. Refuse changed data.
                ordinary=sqlite3.connect(path)
                ordinary.execute('SELECT count(*) FROM sqlite_master').fetchone()
                ordinary.close()
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)
                started=time.monotonic()
                result=subprocess.run([sys.executable,'-c',CHILD,child_tests,str(root),str(path),mode],
                                      capture_output=True,text=True,timeout=15)
                self.assertEqual(result.returncode,71 if mode=='before' else 72,result.stdout+result.stderr)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)
                if mode=='before':
                    db=sqlite3.connect(root/'core.db')
                    try:
                        self.assertEqual(db.execute('SELECT count(*) FROM ab_events').fetchone()[0],0)
                        self.assertFalse(db.execute("SELECT 1 FROM ab_migration_state WHERE status='complete'").fetchone())
                    finally:db.close()
                    # Generated operator permission restoration is permitted only
                    # before new acknowledgements. No database contents restored.
                    for suffix in ('','-wal','-shm'):
                        component=Path(str(path)+suffix)
                        if component.exists():
                            os.chown(component,account.pw_uid,account.pw_gid)
                            component.chmod(0o600)
                    legacy_result=subprocess.run([sys.executable,'-c',CHILD,child_tests,str(root),str(path),'legacy'],
                                                 preexec_fn=demote,capture_output=True,text=True,timeout=10)
                    self.assertEqual(legacy_result.returncode,0,legacy_result.stderr)
                else:
                    self.assertIn('acknowledged',result.stdout)
                    recovered=subprocess.run([sys.executable,'-c',CHILD,child_tests,str(root),str(path),'recover'],
                                             capture_output=True,text=True,timeout=15)
                    self.assertEqual(recovered.returncode,0,recovered.stdout+recovered.stderr)
                    self.assertIn('forward-recovered',recovered.stdout)
                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)
                check_started=time.monotonic()
                with sqlite3.connect(root/'core.db') as audit:
                    self.assertEqual(audit.execute('PRAGMA quick_check').fetchall(),[('ok',)])
                    self.assertEqual(audit.execute('PRAGMA foreign_key_check').fetchall(),[])
                print(json.dumps({'generated_cutover':mode,'fence_through_recovery_seconds':time.monotonic()-started,
                                  'core_quick_and_fk_seconds':time.monotonic()-check_started,
                                  'scale':'small generated legacy; not production budget'}))
