"""Generated SQLite and simulated-host controls. Never access production."""
import contextlib
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

spec=importlib.util.spec_from_file_location('release_verification',Path(__file__).with_name('release_verification.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
NEW='b'*40

class VerificationTests(unittest.TestCase):
    def doc(self):
        return {'approval_confirmed':True,'old':m.OLD,'release':NEW,'policy':dict(m.POLICY),'review_id':'test-only-not-production',
            'application_ci_run':1,'controls_ci_run':2,'expires_at':time.time()+3500,
            'helper_sha256':m.sha(Path(__file__).with_name('deploy.py')),
            'smoke_sha256':m.sha(Path(__file__).with_name('smoke.py')),'verifier_sha256':m.sha(m.__file__)}
    def evidence(self):
        return {'protected':['hash',0o600,0],'status':'PASS','review':self.doc(),'identity':{'inode':1},'finished_at':time.time(),
            'checks':[{'check':n,'status':'PASS'} for n in ('quick_check','foreign_key_check')]}
    def validate(self,e):
        m.validate_evidence(e,NEW,m.OLD,self.doc()['helper_sha256'],{'inode':1},time.time())
    def test_evidence_requires_complete_checks_exact_identity_release_hash_and_time(self):
        self.validate(self.evidence())
        mutations=[lambda e:e['review'].update(approval_confirmed=False),lambda e:e.update(status='STOP'),lambda e:e.update(identity={'inode':2}),
            lambda e:e.update(finished_at=time.time()-301),lambda e:e.update(finished_at=time.time()+1),
            lambda e:e['checks'].pop(),lambda e:e['checks'][1].update(status='STOP'),
            lambda e:e['review'].update(release='c'*40),lambda e:e['review'].update(old='a'*40),
            lambda e:e['review'].update(verifier_sha256='wrong'),lambda e:e['review'].update(helper_sha256='wrong'),
            lambda e:e['review']['policy'].update(work_seconds=1801),
            lambda e:e['review'].update(review_id=''),lambda e:e['review'].update(expires_at=time.time()-1),
            lambda e:e['review'].update(application_ci_run=0)]
        for mutation in mutations:
            e=self.evidence();mutation(e)
            with self.subTest(mutation=mutation),self.assertRaises(m.Stop):self.validate(e)
    def fixture(self,path,broken=False):
        db=sqlite3.connect(path);db.execute('PRAGMA journal_mode=WAL')
        db.executescript('CREATE TABLE parent(id INTEGER PRIMARY KEY); CREATE TABLE child(id REFERENCES parent(id));')
        if broken:db.execute('INSERT INTO child VALUES(99)');db.commit()
        db.close()
    def test_real_complete_verification_and_foreign_key_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'generated.db';self.fixture(p)
            original=p.read_bytes();result=m.check_database(p,3)
            self.assertEqual([c['check'] for c in result['checks']],['quick_check','foreign_key_check'])
            self.assertEqual(p.read_bytes(),original)
            replacement=Path(folder)/'other.db';self.fixture(replacement)
            self.assertNotEqual(m.identity(p)['inode'],m.identity(replacement)['inode'])
            link=Path(folder)/'alias';link.symlink_to(p)
            with self.assertRaises(m.Stop):m.identity(link)
            broken=Path(folder)/'broken.db';self.fixture(broken,True)
            with self.assertRaisesRegex(m.Stop,'foreign_key_check'):m.check_database(broken,3)
            with self.assertRaises(m.Stop):m.check_database(p,0)
    def test_persistence_probe_stays_bounded_and_requires_current_market(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'generated.db'
            with sqlite3.connect(p) as db:
                db.executescript('CREATE TABLE stream_events(source,received_at); CREATE TABLE observations(market_id,kind,received_at);')
                db.execute("INSERT INTO stream_events VALUES('coinbase','now')")
                db.execute("INSERT INTO observations VALUES('current','stream_book','old')")
                db.executemany("INSERT INTO observations VALUES('ended','stream_book','newer')",[()]*130)
            with self.assertRaises(m.Stop):m.persistence(p,'current')
            with sqlite3.connect(p) as db:db.execute("INSERT INTO observations VALUES('current','stream_book','latest')")
            self.assertEqual(m.persistence(p,'current'),{'coinbase_persisted':'now','polymarket_persisted':'latest'})

    def test_schema_mutation_invalidates_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'generated.db';self.fixture(p);before=m.identity(p)
            with sqlite3.connect(p) as db:db.execute('CREATE TABLE extra(id)')
            self.assertNotEqual(m.identity(p),before)
    def test_private_documents_refuse_symlinks_world_readability_and_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'review';m.immutable_write(p,{'a':1})
            with self.assertRaises(FileExistsError):m.immutable_write(p,{})
            with patch.object(m.os,'fstat',return_value=SimpleNamespace(st_uid=0,st_mode=0o100600)):
                self.assertEqual(m.private_read(p),{'a':1})
            p.chmod(0o644)
            with patch.object(m.os,'fstat',return_value=SimpleNamespace(st_uid=0,st_mode=0o100644)),self.assertRaises(m.Stop):m.private_read(p)
            link=Path(folder)/'link';link.symlink_to(p)
            with self.assertRaises(OSError):m.private_read(link)
    def test_source_pin_prevents_general_integrity_bypass(self):
        def git(*args):
            if args==('rev-parse','HEAD'):return m.OLD
            if args[:2]==('bundle','list-heads'):return NEW+' refs/heads/codex/lightsail-deployment'
            if args==('rev-parse','FETCH_HEAD'):return NEW
            if args[:2]==('diff','--name-only'):return '\n'.join(m.APP_FILES)
            if args[0]=='rev-parse':return m.APP_BLOBS[args[1].split(':',1)[1]]
            return ''
        cd=SimpleNamespace(git=Mock(side_effect=git),BRANCH='refs/heads/codex/lightsail-deployment')
        self.assertEqual(m.source(cd,NEW,Path('bundle')),m.OLD)
        cd.git=Mock(side_effect=lambda *args:'wrong' if args[0]=='rev-parse' and ':' in args[-1] else git(*args))
        with self.assertRaises(m.Stop):m.source(cd,NEW,Path('bundle'))
    def test_whole_probe_and_metadata_process_timeouts(self):
        with patch.object(m,'owned_process',side_effect=subprocess.TimeoutExpired('child',2)) as run:
            with self.assertRaises(subprocess.TimeoutExpired):m.fetch('/health')
            self.assertEqual(run.call_args.kwargs['timeout'],2)
            with self.assertRaises(subprocess.TimeoutExpired):m.identity(Path('db'))
            self.assertEqual(run.call_args.kwargs['timeout'],3)
    def test_owned_process_timeout_kills_only_its_private_process_group(self):
        child=Mock(pid=123);child.communicate.side_effect=[subprocess.TimeoutExpired('child',1),
            subprocess.TimeoutExpired('child',2),('','')]
        with patch.object(m.subprocess,'Popen',return_value=child),patch.object(m.os,'killpg') as kill:
            with self.assertRaises(subprocess.TimeoutExpired):m.owned_process(['test'],1)
            self.assertEqual([c.args for c in kill.call_args_list],[(123,m.signal.SIGTERM),(123,m.signal.SIGKILL)])
        child.communicate.side_effect=subprocess.TimeoutExpired('child',1)
        with patch.object(m.subprocess,'Popen',return_value=child),patch.object(m.os,'killpg'):
            with self.assertRaisesRegex(m.Stop,'unreaped'):m.owned_process(['test'],1)

    def test_child_termination_escalates_and_reports_unreaped(self):
        child=Mock();child.wait.side_effect=[subprocess.TimeoutExpired('child',2),0]
        m.reap(child,10);child.terminate.assert_called_once();child.kill.assert_called_once()
        child.wait.side_effect=subprocess.TimeoutExpired('child',2)
        with self.assertRaisesRegex(m.Stop,'unreaped'):m.reap(child,10)
    def test_collection_does_not_substitute_replayed_receipts_for_source_time(self):
        now=datetime.now(timezone.utc);stamp=now.isoformat()
        value={'market':{'id':'new','slug':'new','start':(now-timedelta(seconds=1)).isoformat(),'end':(now+timedelta(seconds=100)).isoformat()},
            'coinbase':{'source_time':stamp,'received_at':stamp},'polymarket':{'slug':'new','source_time':stamp,'received_at':stamp}}
        m.collection_state(value,now)
        value['polymarket']['source_time']=(now-timedelta(seconds=31)).isoformat()
        with self.assertRaises(m.Stop):m.collection_state(value,now)
        value['polymarket']['source_time']=stamp;value['polymarket']['slug']='old'
        with self.assertRaises(m.Stop):m.collection_state(value,now)
    def test_recovery_gets_own_deadline_and_legacy_commands_are_restored(self):
        original=Mock(return_value='ok');cd=SimpleNamespace(run=original)
        with m.commands(cd,600) as (recover,remaining):
            cd.run('systemctl','restart','tradebot-api');self.assertLessEqual(original.call_args.kwargs['timeout'],90)
            recover();self.assertLessEqual(remaining(),180)
        self.assertIs(cd.run,original)
    def simulated_host(self,folder):
        states={'tradebot-api':{'MainPID':'10','NRestarts':'0'},'tradebot-ensemble':{'MainPID':'20','NRestarts':'0'}}
        cd=SimpleNamespace(__file__=str(Path(__file__).with_name('deploy.py')),ROOT=Path(folder),
            HELPERS=Path(folder),runtime_preflight=Mock(return_value=states),protected=Mock(return_value=('hash',0o600,0)),
            git=Mock(),run=Mock(return_value='{}'),services=Mock(return_value=states))
        return cd
    def test_verified_deploy_consumes_evidence_and_only_restarts_api(self):
        for failure in (None,subprocess.TimeoutExpired('restart',90),KeyboardInterrupt()):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as folder,contextlib.ExitStack() as stack:
                p=Path(folder)/'evidence';p.write_text('{}');cd=self.simulated_host(folder);e=self.evidence();e['services']=deepcopy(cd.runtime_preflight.return_value)
                stack.enter_context(patch.object(m,'EVIDENCE',p));stack.enter_context(patch.object(m.os,'geteuid',return_value=0))
                stack.enter_context(patch.object(m,'private_read',return_value=e));stack.enter_context(patch.object(m,'identity',return_value={'inode':1}))
                stack.enter_context(patch.object(m,'source',return_value=m.OLD));stack.enter_context(patch.object(m,'fetch',return_value={}))
                stack.enter_context(patch.object(m.time,'sleep'))
                stack.enter_context(patch.object(m,'probe',return_value=({'a':1},{'status':'degraded','diagnostic_reasons':['feature_snapshot_missing']})))
                selected=[m.OLD]
                def git(*args):
                    if args[0]=='checkout':selected[0]=args[-1]
                    if args==('rev-parse','HEAD'):return selected[0]
                    return ''
                cd.git.side_effect=git
                if not failure:
                    after=deepcopy(cd.runtime_preflight.return_value);after['tradebot-api']['MainPID']='11'
                    cd.runtime_preflight.side_effect=[cd.runtime_preflight.return_value,after]
                if failure:cd.run.side_effect=[failure,'ok']
                if failure:
                    with self.assertRaises(type(failure)):m.reviewed_deploy(cd,NEW,Path('bundle'))
                    self.assertIn(('checkout','--detach',m.OLD),[c.args for c in cd.git.call_args_list])
                else:m.reviewed_deploy(cd,NEW,Path('bundle'))
                self.assertFalse(p.exists());self.assertTrue(p.with_suffix('.consumed.json').exists())
                self.assertTrue(all(c.args[:3]==('systemctl','restart','tradebot-api') for c in cd.run.call_args_list if c.args[0]=='systemctl'))
                self.assertTrue(all(c.args[0] in ('systemctl',sys.executable) for c in cd.run.call_args_list))
                report=json.loads(next((Path(folder)/'data/deployments').iterdir()).read_text())
                self.assertEqual(report['status'],'STOP' if failure else 'deployed_pending_acceptance')
                with self.assertRaises(FileNotFoundError):p.open()
    def test_verification_failure_never_publishes_evidence_or_checks_out(self):
        with tempfile.TemporaryDirectory() as folder,contextlib.ExitStack() as stack:
            cd=self.simulated_host(folder);auth=Path(folder)/'review';auth.write_text('{}');evidence=Path(folder)/'evidence'
            stack.enter_context(patch.object(m,'AUTH',auth));stack.enter_context(patch.object(m,'EVIDENCE',evidence))
            stack.enter_context(patch.object(m.os,'geteuid',return_value=0));stack.enter_context(patch.object(m,'source',return_value=m.OLD))
            stack.enter_context(patch.object(m,'private_read',return_value=self.doc()));stack.enter_context(patch.object(m,'identity',return_value={'inode':1}))
            stack.enter_context(patch.object(m,'probe',return_value=({'a':1},{})))
            child=Mock();child.returncode=0;child.communicate.return_value=(json.dumps({'status':'PASS','identity':{'inode':1},'checks':[{'check':'quick_check','status':'PASS'}]}),'');child.poll.return_value=0
            stack.enter_context(patch.object(m.subprocess,'Popen',return_value=child))
            with self.assertRaises(m.Stop):m.verify(cd,NEW,Path('bundle'))
            self.assertFalse(evidence.exists());self.assertFalse(auth.exists());cd.git.assert_not_called()

    def test_absent_review_never_launches_heavy_child(self):
        with tempfile.TemporaryDirectory() as folder,contextlib.ExitStack() as stack:
            cd=self.simulated_host(folder)
            stack.enter_context(patch.object(m,'AUTH',Path(folder)/'absent'))
            stack.enter_context(patch.object(m,'EVIDENCE',Path(folder)/'absent-evidence'))
            stack.enter_context(patch.object(m.os,'geteuid',return_value=0))
            stack.enter_context(patch.object(m,'source',return_value=m.OLD))
            child=stack.enter_context(patch.object(m.subprocess,'Popen'))
            with self.assertRaises(FileNotFoundError):m.verify(cd,NEW,Path('bundle'))
            child.assert_not_called();cd.runtime_preflight.assert_not_called()

    def test_full_verification_publishes_only_on_success_and_reaps_on_health_failure(self):
        for healthy in (True,False):
            with self.subTest(healthy=healthy),tempfile.TemporaryDirectory() as folder,contextlib.ExitStack() as stack:
                cd=self.simulated_host(folder);auth=Path(folder)/'review';auth.write_text('{}');ep=Path(folder)/'evidence'
                stack.enter_context(patch.object(m,'AUTH',auth));stack.enter_context(patch.object(m,'EVIDENCE',ep))
                stack.enter_context(patch.object(m.os,'geteuid',return_value=0))
                stack.enter_context(patch.object(m,'private_read',return_value=self.doc()))
                stack.enter_context(patch.object(m,'identity',return_value={'inode':1}))
                stack.enter_context(patch.object(m,'source',return_value=m.OLD))
                stack.enter_context(patch.object(m,'probe',side_effect=[({'a':1},{}),({'a':2},{})] if healthy else [({'a':1},{}),m.Stop('collection interrupted')]))
                child=Mock();child.returncode=0;child.poll.return_value=0 if healthy else None
                result=self.evidence();result.pop('review');result.pop('finished_at')
                if healthy:child.communicate.return_value=(json.dumps(result),'')
                else:child.communicate.side_effect=subprocess.TimeoutExpired('verification',5)
                stack.enter_context(patch.object(m.subprocess,'Popen',return_value=child))
                reaper=stack.enter_context(patch.object(m,'reap'))
                if healthy:
                    m.verify(cd,NEW,Path('bundle'));self.validate(json.loads(ep.read_text()))
                    reaper.assert_not_called()
                else:
                    with self.assertRaises(m.Stop):m.verify(cd,NEW,Path('bundle'))
                    self.assertFalse(ep.exists());reaper.assert_called_once()
                cd.git.assert_not_called();cd.run.assert_not_called()

    @unittest.skipUnless(sys.platform=='linux','actual bounded Linux verification child')
    def test_actual_linux_child_and_expired_work_budget(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'generated.db';self.fixture(p)
            command=[sys.executable,m.__file__,'--child',str(p),'--seconds','3']
            result=subprocess.run(command,capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(len(json.loads(result.stdout)['checks']),2)
            command[-1]='0.000000001'
            stopped=subprocess.run(command,capture_output=True,text=True,timeout=5)
            self.assertNotEqual(stopped.returncode,0)
            self.assertEqual(json.loads(stopped.stdout)['status'],'STOP')

    def test_full_smoke_preserves_checks_but_allows_only_feature_unavailability(self):
        smoke_spec=importlib.util.spec_from_file_location('reviewed_smoke',Path(__file__).with_name('smoke.py'))
        smoke=importlib.util.module_from_spec(smoke_spec);smoke_spec.loader.exec_module(smoke)
        now=datetime.now(timezone.utc);stamp=now.isoformat()
        feed={'status':'live','last_data_at':stamp}
        health={'status':'degraded','diagnostic_reasons':['feature_snapshot_missing'],
            'collector':{'running':True,'error':None},'feeds':{n:dict(feed) for n in ('coinbase_stream','polymarket_stream')}}
        state={'market':{'id':'new','slug':'new','start':(now-timedelta(seconds=10)).isoformat(),'end':(now+timedelta(minutes=10)).isoformat()},
            'coinbase':{'source_time':stamp,'received_at':stamp},'polymarket':{'slug':'new','source_time':stamp,'received_at':stamp}}
        values={p:{} for p in smoke.CORE+smoke.PHASE}
        values.update({'/health':health,'/state/current':state,'/events':{'coinbase':{'price':1}},
            '/system/status':{'collector':{'running':True},'openai_enabled':False,'retention_enabled':False,'sqlite':{'size_bytes':1},'feeds':{'coinbase':{'status':'live','age_seconds':0}}},
            '/system/history':{'items':[]},'/models/current':{'models':{'ensemble_v1':{}}}})
        with patch.object(smoke,'get',side_effect=lambda p:values[p]):
            result=smoke.check(rollover_release=True)
            self.assertEqual(set(result['endpoints']),set(smoke.CORE+smoke.PHASE+('/events',)))
            self.assertEqual(result['live_health'],'degraded')
            with self.assertRaises(AssertionError):smoke.check()
            health['diagnostic_reasons']=['market_expired']
            with self.assertRaises(AssertionError):smoke.check(rollover_release=True)
            health['diagnostic_reasons']=['feature_snapshot_missing']
            state['polymarket']['source_time']=(now-timedelta(seconds=31)).isoformat()
            with self.assertRaises(Exception):smoke.check(rollover_release=True)

    def test_workflow_remains_manual_phase_specific_and_old_dispatch_cannot_bypass(self):
        root=Path(__file__).resolve().parents[2]
        workflow=(root/'.github/workflows/deploy-tradebot.yml').read_text()
        self.assertIn('options: [verify, deploy-verified]',workflow)
        self.assertIn('timeout-minutes: 35',workflow);self.assertIn('timeout-minutes: 15',workflow)
        self.assertEqual(workflow.count("if: github.event_name == 'workflow_dispatch'"),2)
        env=dict(os.environ,GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REF='refs/heads/codex/lightsail-deployment',RELEASE_OPERATION='deploy',APPROVED_REVISION=NEW,GITHUB_SHA=NEW)
        result=subprocess.run(['bash',str(root/'deploy/lightsail/dispatch.sh')],env=env,capture_output=True,timeout=2)
        self.assertNotEqual(result.returncode,0)

if __name__=='__main__':unittest.main()
