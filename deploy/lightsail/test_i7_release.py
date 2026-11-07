"""Exact-release exception, real schema reads/deadlines and simulated recovery."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


def load():
    spec = importlib.util.spec_from_file_location('i7_deploy', Path(__file__).with_name('deploy.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReleaseTests(unittest.TestCase):
    def scenario(self, *, stage=None, old=None, files=None, bundle_ref=None, candidate=None):
        cd = load()
        calls = []
        with tempfile.TemporaryDirectory() as temporary, contextlib.ExitStack() as stack:
            root = Path(temporary)
            (root/'data').mkdir()
            (root/'data/btc_intelligence.db').touch()
            auth = root/'authorization.json'
            auth.write_text('{}')
            stack.enter_context(patch.object(cd, 'ROOT', root))
            stack.enter_context(patch.object(cd, 'I7_AUTH', auth))
            stack.enter_context(patch.object(cd, 'i7_authorization', return_value={'application_ci_run':1,'helper_ci_run':2}))
            stack.enter_context(patch.object(cd, 'protected', return_value=('fingerprint',0o600,0)))
            flags = stack.enter_context(patch.object(cd, 'i7_runtime_flags'))
            if stage == 'flags':
                flags.side_effect = AssertionError('unsafe flags')
            states = {n:{'MainPID':'1','NRestarts':'0'} for n in cd.SERVICES}
            stack.enter_context(patch.object(cd, 'services', return_value=states))
            stack.enter_context(patch.object(cd.time, 'sleep'))
            stack.enter_context(patch.object(cd.shutil, 'disk_usage', return_value=type('Disk',(),{'free':10*1024**3})()))
            checked_out = False
            failed_once = False
            def command(*args, **kwargs):
                nonlocal checked_out, failed_once
                calls.append((args,kwargs))
                if args[:3] == ('git','rev-parse','HEAD'):
                    return cd.I7_RELEASE if checked_out else (old or cd.I7_OLD)
                if args[:3] == ('git','bundle','list-heads'):
                    return cd.I7_RELEASE+' '+(bundle_ref or cd.BRANCH)
                if args[:3] == ('git','rev-parse','FETCH_HEAD'):
                    return cd.I7_RELEASE
                if args[:3] == ('git','diff','--name-only'):
                    return '\n'.join(files if files is not None else sorted(cd.I7_FILES))
                if args[:3] == ('git','checkout','--detach'):
                    checked_out = args[3] == cd.I7_RELEASE
                    if stage == 'checkout' and checked_out:
                        raise subprocess.CalledProcessError(1,args)
                    if stage == 'rollback' and not checked_out:
                        raise subprocess.CalledProcessError(1,args)
                if cd.I7_SCHEMA_PROGRAM in args:
                    if stage == 'schema':
                        raise subprocess.TimeoutExpired(args,5)
                    return json.dumps({'schema_readiness':'PASS','integrity':'NOT_PERFORMED_SCOPED_I7_EXCEPTION'})
                if len(args)>1 and str(args[1]).endswith('smoke.py'):
                    if stage in ('smoke','deadline','rollback'):
                        raise (subprocess.TimeoutExpired(args,180) if stage=='deadline' else subprocess.CalledProcessError(1,args))
                    return '{}'
                if args[:3] == ('systemctl','restart','tradebot-api') and stage=='restart' and not failed_once:
                    failed_once = True
                    raise subprocess.CalledProcessError(1,args)
                if '-c' in args and 'responded' in args[2]:
                    return '{"responded":false,"error_type":"TimeoutError"}'
                return ''
            stack.enter_context(patch.object(cd.I7Budget,'command',side_effect=command))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            error = None
            try:
                cd.i7_release(candidate or cd.I7_RELEASE,root/'bundle')
            except (AssertionError,SystemExit,subprocess.TimeoutExpired) as caught:
                error = caught
            records = list((root/'data/deployments').glob('*')) if (root/'data/deployments').exists() else []
            report = json.loads(records[0].read_text()) if records else None
            return cd,calls,report,error,auth.exists()

    def test_exact_release_succeeds_without_baseline_health_or_full_scan(self):
        cd,calls,report,error,auth_exists = self.scenario()
        self.assertIsNone(error)
        self.assertEqual(report['status'],'success_pending_I7_validation')
        self.assertEqual(report['checks']['integrity'],'NOT_PERFORMED_SCOPED_I7_EXCEPTION')
        self.assertFalse(auth_exists)
        self.assertFalse(any('quick_check' in str(args) or 'foreign_key_check' in str(args) for args,_ in calls))
        self.assertEqual([a for a,_ in calls if a[0]=='systemctl'],[('systemctl','restart','tradebot-api')])

    def test_wrong_candidate_runtime_branch_and_changed_scope_never_checkout(self):
        for kwargs in ({'candidate':'b'*40},{'old':'a'*40},{'bundle_ref':'refs/heads/main'},
                       {'files':['backend/app/retention.py']},{'files':['backend/app/collector.py']},
                       {'stage':'flags'},{'stage':'schema'}):
            with self.subTest(kwargs=kwargs):
                _,calls,_,error,exists = self.scenario(**kwargs)
                self.assertIsNotNone(error)
                self.assertFalse(any(a[:2]==('git','checkout') or a[0]=='systemctl' for a,_ in calls))
                self.assertTrue(exists)

    def test_all_postcheckout_failures_restore_old_code_restart_only_api(self):
        for stage in ('checkout','restart','smoke','deadline'):
            with self.subTest(stage=stage):
                cd,calls,report,error,exists = self.scenario(stage=stage)
                self.assertIsInstance(error,SystemExit)
                self.assertEqual(report['status'],'failed')
                self.assertEqual(report['rollback']['revision'],cd.I7_OLD)
                self.assertIn((('git','checkout','--detach',cd.I7_OLD),{'user':True}),calls)
                self.assertTrue(all(a==('systemctl','restart','tradebot-api') for a,_ in calls if a[0]=='systemctl'))
                self.assertFalse(exists)

    def test_failed_rollback_requires_manual_action(self):
        _,_,report,error,_ = self.scenario(stage='rollback')
        self.assertIsInstance(error,SystemExit)
        self.assertEqual(report['rollback']['status'],'MANUAL_ACTION_REQUIRED')

    def test_real_schema_fixture_readiness_is_readonly_and_rejects_missing_schema(self):
        cd=load()
        with tempfile.TemporaryDirectory() as temporary:
            db=Path(temporary)/'fixture.db'
            connection=sqlite3.connect(db)
            # Extract the constant expected mapping without executing any application initializer.
            import ast
            tree=ast.parse(cd.I7_SCHEMA_PROGRAM)
            expected=ast.literal_eval(tree.body[2].value)
            for name,columns in expected.items():
                connection.execute('CREATE TABLE '+name+'('+','.join(c+' TEXT' for c in columns)+')')
            connection.commit()
            connection.close()
            before=db.read_bytes()
            result=subprocess.run([sys.executable,'-c',cd.I7_SCHEMA_PROGRAM,str(db)],capture_output=True,check=True,timeout=5)
            self.assertEqual(json.loads(result.stdout)['schema_readiness'],'PASS')
            self.assertEqual(db.read_bytes(),before)
            with sqlite3.connect(db) as connection:
                connection.execute('DROP TABLE predictions')
            self.assertNotEqual(subprocess.run([sys.executable,'-c',cd.I7_SCHEMA_PROGRAM,str(db)],capture_output=True,timeout=5).returncode,0)

    def test_real_child_deadline_kills_and_reaps_child(self):
        cd=load()
        with tempfile.TemporaryDirectory() as temporary:
            pidfile=Path(temporary)/'pid'
            with patch.object(cd,'ROOT',Path(temporary)):
                with self.assertRaises(subprocess.TimeoutExpired):
                    cd.I7Budget().command(sys.executable,'-c',"import os,time,pathlib,sys; pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(30)",str(pidfile),cap=0.3)
            with self.assertRaises(ProcessLookupError):
                os.kill(int(pidfile.read_text()),0)

    def test_authorization_checks_permissions_hash_expiry_and_exact_ci(self):
        cd=load()
        with tempfile.TemporaryDirectory() as temporary:
            auth=Path(temporary)/'auth'
            valid={'old':cd.I7_OLD,'release':cd.I7_RELEASE,'application_ci_run':1,'helper_ci_run':2,
                   'helper_sha256':cd.hashlib.sha256(Path(cd.__file__).read_bytes()).hexdigest(),'expires_at':time.time()+300}
            with patch.object(cd,'I7_AUTH',auth),patch.object(cd.os,'getuid',return_value=0):
                for field,value in [('old','x'),('release','x'),('application_ci_run',0),('helper_ci_run',0),('helper_sha256','wrong'),('expires_at',0)]:
                    auth.write_text(json.dumps(dict(valid,**{field:value})))
                    auth.chmod(0o600)
                    # Owner assertion is separately checked; local Mac test fixture is non-root.
                    with patch.object(type(auth),'stat',return_value=type('Stat',(),{'st_uid':0,'st_mode':0o100600})()),patch.object(type(auth),'is_symlink',return_value=False):
                        with self.assertRaises(AssertionError):
                            cd.i7_authorization()


if __name__=='__main__':
    unittest.main()
