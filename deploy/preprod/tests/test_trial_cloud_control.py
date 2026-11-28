"""Exact child cloud scopes, attestation and readiness; generated inputs only."""
from contextlib import nullcontext
from datetime import datetime,timedelta,timezone
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import MagicMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from compose_render import render_config
from controller import DeploymentHold
import trial_cloud_control as c
import trial_cloud_profile as p
import linux_actions as a
from test_linux_actions import configuration,IMAGE

ANCHOR=str(uuid.uuid4());SOURCE='a'*40


def live_config(base):
    live=deepcopy(base)
    for service in a.SERVICES:live['services'][service]['environment']=a.expected_environment(service,live=True,initial_a=ANCHOR,trial_origin=a.TRIAL_ORIGIN)
    live['services']['operator']['secrets'].append({'source':'app_dsn','target':'app_dsn'})
    return live


def child_config(base,live,archive):
    cfg=deepcopy(live);files=p.WRITER_AUTH if archive else p.WRITER_SQL
    for name,path in {**files,'probe_local_dsn':p.LOCAL_STAGED}.items():cfg['secrets'][name]={'name':a.PROJECT+'_'+name,'file':path}
    egress='raw_archive_probe_egress' if archive else 'structured_probe_egress'
    cfg['networks'][egress]={'name':a.PROJECT+'_'+egress,'driver':'bridge','ipam':{}}
    cfg['services'][p.service_name(archive)]=p.child_service(base,ANCHOR,archive=archive)
    return cfg

class ProfileTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('docker'),'Docker Compose unavailable')
    def test_boundary_compose_uses_structured_only_authority(self):
        folder=Path(__file__).resolve().parents[1]
        env={**os.environ,'PP_APP_IMAGE':IMAGE,'PP_SECRET_DIR':str(a.SECRETS),
             'PP_RUNTIME_SECRET_DIR':str(a.RUNTIME_SECRETS),
             **a.cycle_environment(ANCHOR,a.BOUNDARY_ORIGIN)}

        def render(files):
            command=['docker','compose','--env-file','/dev/null','--profile','migration',
                     '--profile','trial_structured','--project-directory',str(folder)]
            for name in files:command+=['-f',str(folder/name)]
            return render_config([*command,'config','--format','json'],env=env,timeout=10)

        basefiles=['compose.yaml','runtime.compose.yaml']
        livefiles=[*basefiles,'runtime.live.compose.yaml','runtime.live-boundary.compose.yaml']
        base,live,child=(render(files) for files in
                         (basefiles,livefiles,[*livefiles,'runtime.boundary-structured.compose.yaml']))
        p.validate_profile(base,live,child,folder.parent.parent,IMAGE,ANCHOR,boundary_origin=p.BOUNDARY_ORIGIN)
        self.assertEqual(live['services']['operator']['environment']['TRADEBOT_PP_BOUNDARY_TRACE'],'1')
        self.assertNotIn('TRADEBOT_PP_CYCLE_INITIAL_A',live['services']['lifecycle']['environment'])
        self.assertNotIn('sealed_archive',child['services'])
        self.assertTrue(a.allowed_session_seconds(4100,scoped=True,origin=a.BOUNDARY_ORIGIN))
        self.assertFalse(a.allowed_session_seconds(6600,scoped=True,origin=a.BOUNDARY_ORIGIN))
        with self.assertRaises(DeploymentHold):
            p.child_service(base,ANCHOR,boundary_origin=p.BOUNDARY_ORIGIN,archive=True)
        env.update(a.cycle_environment(ANCHOR, a.DISPLAY_ORIGIN))
        display_files=[*livefiles, 'runtime.quote-display.compose.yaml']
        display=render(display_files)
        display_child=render([*display_files, 'runtime.display-structured.compose.yaml'])
        p.validate_profile(base,display,display_child,folder.parent.parent,IMAGE,ANCHOR,boundary_origin=a.DISPLAY_ORIGIN)
        self.assertTrue(a.allowed_session_seconds(1320,scoped=True,origin=a.DISPLAY_ORIGIN))
        self.assertFalse(a.allowed_session_seconds(540,scoped=True,origin=a.DISPLAY_ORIGIN))
        self.assertFalse(display['services']['api']['environment'].get('POLYMARKET_SECRET_KEY_FILE'))
        for service in ('operator','api'):
            bad=deepcopy(display)
            bad['services'][service]['volumes'][0]['source']='/etc'
            with self.assertRaises(DeploymentHold):
                p.validate_profile(base,bad,display_child,folder.parent.parent,IMAGE,ANCHOR,boundary_origin=a.DISPLAY_ORIGIN)
        self.assertEqual(display_child['secrets']['pp_boundary_history_writer_dsn']['file'],
                         '/etc/tradebot/cloud/display_20261127_02_history_writer_dsn')
        self.assertNotIn('sealed_archive',display_child['services'])
        with self.assertRaises(DeploymentHold):
            p.child_service(base,ANCHOR,boundary_origin=a.DISPLAY_ORIGIN,archive=True)
        env.update(a.cycle_environment(ANCHOR, a.BOUNDARY_SMOKE_ORIGIN))
        smoke = render(livefiles)
        from live_profile import validate_live_profile
        validate_live_profile(base, smoke, folder.parent.parent, IMAGE, initial_a=ANCHOR,
                              trial_origin=a.BOUNDARY_SMOKE_ORIGIN)
        self.assertNotIn('structured_sync', smoke['services'])
        self.assertNotIn('sealed_archive', smoke['services'])
        self.assertTrue(a.allowed_session_seconds(540, scoped=True, origin=a.BOUNDARY_SMOKE_ORIGIN))
        self.assertFalse(a.allowed_session_seconds(4100, scoped=True, origin=a.BOUNDARY_SMOKE_ORIGIN))

    def test_measured_modes_are_exact_structured_trial_child_only(self):
        base=configuration(Path('/reviewed/source'));live=live_config(base)
        flags=('TRADEBOT_PP_SYNC_BARRIERS','TRADEBOT_PP_REUSE_HISTORY_SESSION')
        for service in (*base['services'].values(),*live['services'].values(),p.child_service(base,ANCHOR,archive=True)):
            for flag in flags:self.assertNotIn(flag,service['environment'])
        actual=child_config(base,live,False)
        for flag in flags:
            self.assertEqual(actual['services']['structured_probe']['environment'][flag],'true')
            for replacement in (None,'false'):
                bad=deepcopy(actual);env=bad['services']['structured_probe']['environment']
                if replacement is None:del env[flag]
                else:env[flag]=replacement
                with self.subTest(flag=flag,replacement=replacement),self.assertRaises(DeploymentHold):
                    p.validate_profile(base,live,bad,Path('/reviewed/source'),IMAGE,ANCHOR)

    def test_exact_profiles_exclude_opposite_and_legacy_credentials(self):
        base=configuration(Path('/reviewed/source'));live=live_config(base)
        for archive in (False,True):
            actual=child_config(base,live,archive)
            p.validate_profile(base,live,actual,Path('/reviewed/source'),IMAGE,ANCHOR,archive=archive)
            service=actual['services'][p.service_name(archive)]
            mounted={item['source'] for item in service['secrets']}
            self.assertEqual(mounted,{'probe_local_dsn',*(p.WRITER_AUTH if archive else p.WRITER_SQL)})
            for mutate in (lambda row:row['environment'].update(TRADEBOT_ORIGIN_ID='pp-live-pp'),
                           lambda row:row['environment'].update(ENABLE_OPENAI_ANALYST='true'),
                           lambda row:row['secrets'].append({'source':'pp_history_dsn','target':'pp_history_dsn'}),
                           lambda row:row.update(user='10001:10001'),
                           lambda row:row['networks'].update(public=None)):
                bad=deepcopy(actual);mutate(bad['services'][p.service_name(archive)])
                with self.assertRaises(DeploymentHold):p.validate_profile(base,live,bad,Path('/reviewed/source'),IMAGE,ANCHOR,archive=archive)

    @unittest.skipUnless(shutil.which('docker'),'Docker Compose unavailable')
    def test_actual_compose_matches_exact_child_service(self):
        root=Path(__file__).resolve().parents[3];folder=root/'deploy/preprod'
        env={**os.environ,'PP_APP_IMAGE':IMAGE,'PP_SECRET_DIR':str(a.SECRETS),'PP_RUNTIME_SECRET_DIR':str(a.RUNTIME_SECRETS),
             **a.cycle_environment(ANCHOR,a.TRIAL_ORIGIN)}
        def render(files,profile=None):
            command=['docker','compose','--env-file','/dev/null','--profile','migration']
            if profile:command+=['--profile',profile]
            command+=['--project-directory',str(folder)]
            for name in files:command+=['-f',str(folder/name)]
            return render_config([*command,'config','--format','json'], env=env, timeout=10)
        basefiles=['compose.yaml','runtime.compose.yaml'];livefiles=[*basefiles,'runtime.live.compose.yaml','runtime.live-cycle.compose.yaml','runtime.live-trial.compose.yaml']
        base=render(basefiles)
        for reader in (False,True):
            selected=livefiles+(['runtime.trial-history-reader.compose.yaml'] if reader else [])
            live=render(selected)
            for archive in (False,True):
                actual=render([*selected,p.overlay(archive)],p.profile_name(archive))
                p.validate_profile(base,live,actual,root,IMAGE,ANCHOR,archive=archive,trial_reader=reader)

class DispatchOrderTests(unittest.TestCase):
    def test_readiness_then_one_use_authority_precedes_mocked_activation(self):
        import transition_control as gate
        digest=hashlib.sha256(b'controller').hexdigest()
        active=dict(environment='preprod',instance='tradebot-preprod-01',state='ready_off',initial_a=ANCHOR,trial_origin=a.TRIAL_ORIGIN,source_sha=SOURCE,
            artifact_sha256='b'*64,controller_sha256=digest,image_id=IMAGE,nonce=str(uuid.uuid4()))
        context=SimpleNamespace(request=SimpleNamespace(source_sha=SOURCE),image=IMAGE)
        calls=[];statuses=[dict(generation_id=ANCHOR,collector_enabled=False),dict(origin_id=a.TRIAL_ORIGIN,
            collector_enabled=True,process_running=True,lease_expires_at=(datetime.now(timezone.utc)+timedelta(seconds=6600)).isoformat())]
        def operator(_token,path,**kwargs):
            calls.append(path)
            return statuses.pop(0) if path=='/collector/status' else dict(accepted=True,origin_id=a.TRIAL_ORIGIN)
        def token_metadata(path):
            if path==gate.RUNTIME_SECRETS/'operator_token':
                return SimpleNamespace(st_mode=stat.S_IFREG|0o400,st_uid=10001)
            raise FileNotFoundError
        with patch.object(gate.HostBinding,'from_marker',return_value=gate.HostBinding('tradebot-preprod-01','preprod','Tradebot',False,False,False)),patch.object(gate,'_read_active',return_value=active), \
             patch.object(gate,'_secure_file',return_value=(b'controller',None)),patch.object(gate,'_candidate',return_value=context), \
             patch.object(gate,'_image_binding'),patch.object(gate,'_owned_runtime'), \
             patch.object(gate,'_consume',side_effect=lambda *_:calls.append('consume')) as consume, \
             patch.object(gate,'_operator',side_effect=operator),patch.object(c,'require_ready',side_effect=lambda *_:calls.append('ready')), \
             patch.object(Path,'lstat',new=token_metadata), \
             patch.object(Path,'read_text',return_value='a'*64):
            result=gate.session('session-v1 on 6600 '+ANCHOR+' '+a.TRIAL_ORIGIN,Path('/trusted/controller'))
        self.assertEqual(result['origin_id'],a.TRIAL_ORIGIN)
        self.assertLess(calls.index('ready'),calls.index('consume'))
        self.assertLess(calls.index('consume'),calls.index('/collector/on'))
        self.assertEqual(consume.call_args.args[1]['trial_origin'],a.TRIAL_ORIGIN)
        self.assertEqual(consume.call_args.args[1]['initial_a'],ANCHOR)

class RecoveryTests(unittest.TestCase):
    def test_permit_free_leave_proves_off_even_when_reader_attestation_is_corrupt(self):
        from live_transition import LiveTransition
        from test_live_transition import Actions,Budget
        owned=Actions();base=Budget(owned)
        class TrialBudget:
            def timeout(self,*args):return base.timeout(*args)
            def run(self,args,**kwargs):
                raw=base.run(args,**kwargs)
                return raw.replace(b'pp-live-pp',a.TRIAL_ORIGIN.encode()) if args[-1] in ('--stop-collector','--collector-status') else raw
        context=SimpleNamespace(source=Path('/reviewed/source'),image=IMAGE)
        transition=LiveTransition(owned,context,TrialBudget(),initial_a=ANCHOR,trial_origin=a.TRIAL_ORIGIN)
        with patch('live_transition.validate_live_profile'),patch('live_transition.history_reader_enabled',side_effect=DeploymentHold('legacy_bad')), \
             patch('trial_history_reader.trial_history_reader_enabled',side_effect=DeploymentHold('trial_bad')):
            self.assertEqual(transition.leave()['gate'],'PP_GENERATED_RESTORED')
        self.assertTrue(any(isinstance(call,tuple) and '--stop-collector' in call[1] for call in owned.calls))

class WriterProofTests(unittest.TestCase):
    def test_scope_hash_identities_and_exact_host_verdicts(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);root.chmod(0o700)
            sql={key:str(root/key) for key in p.WRITER_SQL};auth={key:str(root/key) for key in p.WRITER_AUTH}
            writer,reader=str(uuid.uuid4()),str(uuid.uuid4())
            for name in (*sql,*auth,'supabase_auth_uid','trial_20261119_07_history_reader_uid'):
                path=root/name;path.write_text('fixture')
                path.chmod(0o644 if name=='pp_history_ca' else 0o400 if name=='trial_20261119_07_history_reader_uid' else 0o600)
            (root/'pp_history_ca').write_text('-----BEGIN CERTIFICATE-----\nfixture\n-----END CERTIFICATE-----')
            (root/'trial_archive_uid').write_text(writer);(root/'supabase_auth_uid').write_text(str(uuid.uuid4()))
            (root/'trial_20261119_07_history_reader_uid').chmod(0o600);(root/'trial_20261119_07_history_reader_uid').write_text(reader);(root/'trial_20261119_07_history_reader_uid').chmod(0o400)
            proof=dict(version=1,origin_id=a.TRIAL_ORIGIN,sql_writer_role=c.WRITER_ROLE,sql_reader_role=c.READER_ROLE,
                       archive_writer_uid=writer,archive_reader_uid=reader,**dict.fromkeys(c.VERDICTS,'pass'))
            ctx=SimpleNamespace(request=SimpleNamespace(source_sha=SOURCE),image=IMAGE)
            authority=root/'authority';evidence=root/'proof'
            def save(data,**changed):
                raw=json.dumps(data,sort_keys=True).encode()
                for path,value in ((evidence,raw),(authority,json.dumps(dict(version=1,scope='pp-trial-cloud-writer-v1',origin_id=a.TRIAL_ORIGIN,
                    initial_a=ANCHOR,source_sha=SOURCE,image_id=IMAGE,proof_sha256=hashlib.sha256(raw).hexdigest())|changed).encode())):
                    path.chmod(0o600) if path.exists() else None;path.write_bytes(value);path.chmod(0o400)
            original=Path.lstat
            def ownership(path,*args,**kwargs):
                value=list(original(path,*args,**kwargs));value[4]=10001 if path.name=='trial_20261119_07_history_reader_uid' else 0
                return os.stat_result(value)
            with patch.object(c,'AUTHORITY',authority),patch.object(c,'PROOF',evidence),patch.object(c,'RUNTIME_SECRETS',root),patch('trial_history_reader.RUNTIME_SECRETS',root),patch.object(c,'CLOUD_DIR',root), \
                 patch.object(c,'WRITER_SQL',sql),patch.object(c,'WRITER_AUTH',auth),patch.object(Path,'lstat',ownership), \
                 patch.object(c,'_secure_file',side_effect=lambda path:(path.read_bytes(),None)), \
                 patch('structured_probe_control.CA_SHA256',hashlib.sha256(b'fixture').hexdigest()),patch.object(c.ssl,'PEM_cert_to_DER_cert',return_value=b'fixture'):
                save(proof);self.assertEqual(len(c.writer_proof(ctx,ANCHOR)),64)
                for changed in ({'origin_id':'pp-live-pp'},{'sql_reader_role':c.WRITER_ROLE},{'storage_reader_create_denied':'unqualified'},
                                {'archive_reader_uid':writer},{'trial_03_independent_archive_verified':'not_run'},
                                {'sql_trial_03_denied':'not_run'},{'storage_trial_03_denied':'not_run'}):
                    save(proof|changed)
                    with self.assertRaises(DeploymentHold):c.writer_proof(ctx,ANCHOR)
                for changed in ({'source_sha':'b'*40},{'initial_a':str(uuid.uuid4())},{'image_id':'sha256:'+'b'*64}):
                    save(proof,**changed)
                    with self.assertRaises(DeploymentHold):c.writer_proof(ctx,ANCHOR)
                save(proof);evidence.chmod(0o600)
                with self.assertRaises(DeploymentHold):c.writer_proof(ctx,ANCHOR)

class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.base=configuration(Path('/reviewed/source'))
        self.owner=dict(attempt_id='a'*32,image=IMAGE,source_sha=SOURCE,origin_id=a.TRIAL_ORIGIN,initial_a=ANCHOR,writer_proof_sha256='b'*64)
    def row(self,archive=False):
        expected=p.child_service(self.base,ANCHOR,archive=archive);files=p.WRITER_AUTH if archive else p.WRITER_SQL
        sources={'/run/secrets/'+key:value for key,value in files.items()};sources['/run/secrets/lifecycle_dsn']=p.LOCAL_STAGED
        egress='raw_archive_probe_egress' if archive else 'structured_probe_egress'
        return dict(Id='c'*64,State=dict(Running=True,OOMKilled=False),Config=dict(Cmd=expected['command'],User='0:0',Env=[k+'='+v for k,v in expected['environment'].items()]),
            HostConfig=dict(ReadonlyRootfs=True,Privileged=False,CapDrop=['ALL'],Memory=128*1024**2,MemorySwap=128*1024**2,NanoCpus=250000000,PidsLimit=64),
            Mounts=[dict(Destination=k,Source=v,RW=False) for k,v in sources.items()],NetworkSettings=dict(Networks={a.PROJECT+'_database':{},a.PROJECT+'_'+egress:{}}))
    def test_actual_worker_guard_rejects_wrong_origin_credentials_and_isolation(self):
        for archive in (False,True):
            row=self.row(archive)
            with patch('structured_probe_control._sync_container',return_value=row):c._inspect_worker(self.owner,MagicMock(),self.base,archive=archive)
            for mutate in (lambda r:r['Config']['Env'].append('TRADEBOT_ORIGIN_ID=pp-live-pp'),lambda r:r['HostConfig'].update(Privileged=True),
                           lambda r:r['Mounts'][0].update(Source='/etc/tradebot/cloud/pp_history_dsn'),lambda r:r['State'].update(Running=False)):
                bad=deepcopy(row);mutate(bad)
                with patch('structured_probe_control._sync_container',return_value=bad),self.assertRaises(DeploymentHold):
                    c._inspect_worker(self.owner,MagicMock(),self.base,archive=archive)
    def test_actual_structured_worker_requires_both_measured_modes(self):
        for flag in ('TRADEBOT_PP_SYNC_BARRIERS','TRADEBOT_PP_REUSE_HISTORY_SESSION'):
            for replacement in (None,'false'):
                bad=self.row();env=bad['Config']['Env']
                env.remove(flag+'=true')
                if replacement is not None:env.append(flag+'='+replacement)
                with self.subTest(flag=flag,replacement=replacement), \
                     patch('structured_probe_control._sync_container',return_value=bad),self.assertRaises(DeploymentHold):
                    c._inspect_worker(self.owner,MagicMock(),self.base)
    def test_readiness_requires_both_owned_bound_workers_and_reader_proof(self):
        ctx=SimpleNamespace(request=SimpleNamespace(source_sha=SOURCE),image=IMAGE)
        with patch.object(c,'writer_proof',return_value='b'*64),patch.object(c,'_reader',return_value=True), \
             patch.object(c,'_secure_file',return_value=(json.dumps(self.owner).encode(),None)), \
             patch.object(c,'_inspect_worker') as inspect,patch.object(c.LinuxActions,'_compose',return_value=json.dumps(self.base).encode()):
            self.assertTrue(c.require_ready(ctx,ANCHOR,MagicMock()));self.assertEqual(inspect.call_count,2)
            with patch.object(c,'_secure_file',return_value=(json.dumps(self.owner|{'origin_id':'pp-live-pp'}).encode(),None)),self.assertRaises(DeploymentHold):
                c.require_ready(ctx,ANCHOR,MagicMock())
    def test_start_preserves_ownership_and_stops_failed_owned_worker(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'owner.json';ctx=SimpleNamespace(request=SimpleNamespace(source_sha=SOURCE),image=IMAGE)
            actions=MagicMock();actions.attempt_id='a'*32
            with patch('structured_probe_control.SYNC_STATE',path),patch.object(c,'preflight',return_value=(ctx,actions,ANCHOR,'b'*64,self.base,a.TRIAL_ORIGIN)), \
                 patch('structured_probe_control._stage_local_secret',return_value=nullcontext()),patch.object(c,'_compose') as compose, \
                 patch.object(c,'_inspect_worker',return_value=self.row()),patch.object(c.Budget,'run',return_value=b'{"status": "structured_worker_ready"}\n'):
                self.assertEqual(c.start(Path('bundle'))['origin_id'],a.TRIAL_ORIGIN)
                self.assertEqual(json.loads(path.read_text()),self.owner)
                self.assertIn('--no-deps',compose.call_args.args[-1])
            path.unlink()
            with patch('structured_probe_control.SYNC_STATE',path),patch.object(c,'preflight',return_value=(ctx,actions,ANCHOR,'b'*64,self.base,a.TRIAL_ORIGIN)), \
                 patch('structured_probe_control._stage_local_secret',return_value=nullcontext()),patch.object(c,'_compose',side_effect=DeploymentHold('failed')), \
                 patch('structured_probe_control.recurring_control') as stop:
                with self.assertRaises(DeploymentHold):c.start(Path('bundle'))
                self.assertEqual(stop.call_args.args[0],'stop')
