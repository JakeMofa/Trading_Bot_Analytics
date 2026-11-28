"""Command/guard tests only. These do not claim a qualified Linux deployment."""
from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from compose_render import render_config
import controller as c
import linux_actions as a
import live_profile as live_policy

IMAGE='sha256:'+'a'*64
CID='b'*64


def configuration(source,image=IMAGE):
    config={'name':a.PROJECT,'networks':{'database':{'name':a.NETWORK,'internal':True},
            'api_loopback':{'name':a.API_NETWORK,'driver':'bridge','driver_opts':{
                'com.docker.network.bridge.host_binding_ipv4':'127.0.0.1'}}},
            'volumes':{'pp_pgdata':{'name':a.PG_VOLUME}},'secrets':{},'services':{}}
    for name in ('admin','migrator','application','reader'):
        config['secrets'][name]={'file':str(a.SECRETS/name)}
    config['secrets']['lifecycle_password']={'file':str(a.SECRETS/'lifecycle')}
    for name in a.ROLE_SECRET.values():config['secrets'][name]={'file':str(a.RUNTIME_SECRETS/name)}
    config['secrets']['operator_token']={'file':str(a.RUNTIME_SECRETS/'operator_token')}
    for name,memory in a.MEMORY.items():
        service={'image':a.PG_IMAGE if name=='postgres' else image,'mem_limit':str(memory*1024**2),
                 'memswap_limit':memory*1024**2,'networks':{'database':None},'security_opt':['no-new-privileges:true'],
                 'logging':{'driver':'json-file','options':{'max-size':'5m','max-file':'2'}}}
        if name in a.CPUS:service['cpus']=a.CPUS[name]
        if name=='postgres':
            service.update(environment=dict(a.PG_ENV),command=list(a.PG_COMMAND),
                           secrets=[{'source':source,'target':target} for source,target in a.PG_SECRET_MAPPINGS.items()],
                           volumes=[{'type':'volume','source':'pp_pgdata','target':'/var/lib/postgresql/data'},
                                    {'type':'bind','source':str(source/'deploy/preprod/init.sh'),
                                     'target':'/docker-entrypoint-initdb.d/10-foundation.sh','read_only':True}])
        else:
            service.update(command=a.COMMANDS[name],user='10001:10001',read_only=True,cap_drop=['ALL'],pids_limit=64,
                pull_policy='never',restart='no' if name=='migrate' else 'unless-stopped',environment=a.expected_environment(name),
                secrets=[{'source':secret,'target':secret} for secret in a.service_secrets(name)],tmpfs=['/tmp:size=16m,mode=1777'])
        if name in ('api','operator'):
            port=8000 if name=='api' else 8001
            service['ports']=[{'host_ip':'127.0.0.1','published':str(port),'target':port,'protocol':'tcp'}]
            service['networks']['api_loopback']=None
        config['services'][name]=service
    return config


def inspected(service='api',running=True,live=False):
    port=8000 if service=='api' else 8001 if service=='operator' else None
    bindings={f'{port}/tcp':[{'HostIp':'127.0.0.1','HostPort':str(port)}]} if port else {}
    return {'Id':CID,'Image':IMAGE,'State':{'Running':running,'OOMKilled':False,'Health':{'Status':'healthy'}},
        'Config':{'Image':IMAGE,'Cmd':a.COMMANDS[service],'User':'10001:10001','Labels':{
                  'com.docker.compose.project':a.PROJECT,'com.docker.compose.service':service,'com.docker.compose.oneoff':'False'},
                  'Env':[key+'='+value for key,value in a.expected_environment(service,live=live).items()]},
        'HostConfig':{'Memory':a.MEMORY[service]*1024**2,'MemorySwap':a.MEMORY[service]*1024**2,'PidsLimit':64,
                      'ReadonlyRootfs':True,'Privileged':False,'CapDrop':['ALL'],
                      'NanoCpus':int(a.CPUS.get(service,0)*1_000_000_000),
                      'RestartPolicy':{'Name':'unless-stopped' if running else 'no'},
                      'PortBindings':bindings},
        'Mounts':[{'Destination':'/run/secrets/'+secret,'Source':str(a.RUNTIME_SECRETS/secret),'RW':False} for secret in a.service_secrets(service,live=live)],
        'NetworkSettings':{'Networks':{name:{} for name in
            ([a.NETWORK,a.API_NETWORK] if service in ('api','operator') else [a.NETWORK])},
            'Ports':bindings}}


class RecordingBudget:
    def __init__(self):self.calls=[];self.responses=[]
    def timeout(self,maximum=None):return 600 if maximum is None else min(600,maximum)
    def run(self,args,**kwargs):
        self.calls.append((args,kwargs))
        result=self.responses.pop(0) if self.responses else b''
        if isinstance(result,Exception):raise result
        return result


class OneoffBudget(RecordingBudget):
    """Docker daemon keeps running after its CLI times out; stop is ignored."""
    def __init__(self,actions,context):
        super().__init__()
        self.actions,self.context=actions,context
        self.exists=False;self.running=True;self.ignore_kill=False;self.foreign=False;self.name=None
    def run(self,args,**kwargs):
        self.calls.append((args,kwargs))
        if args[:2]==['docker','compose'] and 'run' in args:
            self.name=args[args.index('--name')+1]
            self.exists=True
            raise c.DeploymentHold('child_deadline_exceeded')
        if args[:2]==['docker','ps']:return (CID+'\n').encode() if self.exists else b''
        if args[:2]==['docker','inspect']:
            return json.dumps([{'Id':CID,'Name':'/'+self.name,'State':{'Running':self.running},
                'Config':{'Labels':{'com.docker.compose.project':a.PROJECT,'com.docker.compose.service':'migrate',
                                   a.ATTEMPT_LABEL:'foreign-attempt' if self.foreign else self.actions.attempt_id,
                                   a.SOURCE_LABEL:self.context.request.source_sha}},
                'HostConfig':{'RestartPolicy':{'Name':'no'}}}]).encode()
        if args[:2]==['docker','stop']:return b''
        if args[:2]==['docker','kill']:
            if not self.ignore_kill:self.running=False
            return b''
        if args[:2]==['docker','rm']:
            if self.running:raise AssertionError('cannot remove a running owned container without exit evidence')
            self.exists=False;return b''
        raise AssertionError('unexpected command in owned-oneoff test')


class ConfigTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('docker'), 'Docker Compose unavailable')
    def test_real_compose_live_overlay_matches_reviewed_profile(self):
        source=Path(__file__).resolve().parents[3]
        env={**os.environ,'PP_APP_IMAGE':IMAGE,
             'PP_SECRET_DIR':str(a.SECRETS),'PP_RUNTIME_SECRET_DIR':str(a.RUNTIME_SECRETS)}
        def rendered(*overlays):
            command=['docker','compose','--env-file','/dev/null','--profile','migration',
                     '--project-directory',str(source/'deploy/preprod'),
                     '-f',str(source/'deploy/preprod/compose.yaml'),
                     '-f',str(source/'deploy/preprod/runtime.compose.yaml')]
            for overlay in overlays:
                command.extend(('-f',str(source/'deploy/preprod'/overlay)))
            command.extend(('config','--format','json'))
            return render_config(command, env=env, timeout=10)
        live_policy.validate_live_profile(rendered(),rendered('runtime.live.compose.yaml'),
                                          source,IMAGE)
        cfg = rendered('runtime.live.compose.yaml','runtime.history-reader.compose.yaml')
        live_policy.validate_live_profile(rendered(),cfg,source,IMAGE,reader=True)
        with self.assertRaises(a.DeploymentHold):
            live_policy.validate_live_profile(rendered(),cfg,source,IMAGE)
        cfg['services']['api']['secrets'].append({'source':'lifecycle_dsn','target':'lifecycle_dsn'})
        with self.assertRaises(a.DeploymentHold):
            live_policy.validate_live_profile(rendered(),cfg,source,IMAGE,reader=True)


    def test_explicit_live_overlay_changes_only_reviewed_pp_fields(self):
        source=Path('/private/candidate/source')
        base=configuration(source)
        live=deepcopy(base)
        for name in ('api','calculation','lifecycle'):
            live['services'][name]['environment'].update(
                TRADEBOT_DATA_MODE='pp_live',TRADEBOT_ORIGIN_ID='pp-live-pp')
        live['services']['lifecycle']['environment'].update(
            TRADEBOT_PP_LIVE_LIFECYCLE='true', TRADEBOT_PP_WINDOW_POLICY='two-official-markets',
            TRADEBOT_GENERATED_LOCAL_STORAGE='false')
        live['services']['operator']['environment'].update(
            TRADEBOT_PP_LIVE_CONTROL='true',TRADEBOT_APP_DSN_FILE='/run/secrets/app_dsn')
        live['services']['operator']['secrets'].append({'source':'app_dsn','target':'app_dsn'})
        self.assertIs(live_policy.validate_live_profile(base,live,source,IMAGE),live)
        for mutate in (
            lambda row:row['services']['lifecycle']['environment'].update(TRADEBOT_QUALIFIED_GENERATION_BYTES='1'),
            lambda row:row['services']['api']['environment'].update(ENABLE_OPENAI_ANALYST='true'),
            lambda row:row['services']['lifecycle']['environment'].update(ENABLE_LOCAL_RETENTION='true'),
            lambda row:row['services']['lifecycle']['environment'].update(TRADEBOT_GENERATED_LOCAL_STORAGE='true'),
            lambda row:row['services']['operator']['secrets'].pop(),
            lambda row:row['services']['api']['environment'].update(TRADEBOT_ORIGIN_ID='generated-pp'),
            lambda row:row['services']['operator']['ports'][0].update(host_ip='0.0.0.0'),
            lambda row:row['services']['postgres']['environment'].update(POSTGRES_DB='tradebot_prod'),
        ):
            changed=deepcopy(live)
            mutate(changed)
            with self.assertRaises(c.DeploymentHold):
                live_policy.validate_live_profile(base,changed,source,IMAGE)

    def test_actual_policy_accepts_generated_normalized_shape(self):
        source=Path('/private/candidate/source')
        self.assertEqual(a.validate_config(configuration(source),source,IMAGE)['name'],a.PROJECT)

    def test_compose_v5_short_secret_expansion_and_remaining_normalized_fields(self):
        # Observed from actual `docker compose v5.6.1 ... config --format json`:
        # short secrets expand to absolute destinations; explicit lifecycle target
        # remains relative. Limits are strings, postgres cpus is numeric 1, and
        # the API port includes ingress mode. No credential contents are fixtures.
        source=Path('/private/candidate/source')
        config=configuration(source)
        for service in config['services'].values():
            service['mem_limit']=str(service['mem_limit'])
            service['memswap_limit']=str(service['memswap_limit'])
            for mapping in service.get('secrets',[]):
                if mapping['source']!='lifecycle_password':
                    mapping['target']='/run/secrets/'+mapping['target']
        config['services']['postgres']['cpus']=1
        config['services']['api']['ports'][0]['mode']='ingress'
        validated=a.validate_config(config,source,IMAGE)
        self.assertEqual(set(validated['services']),set(a.MEMORY))
        self.assertEqual(sum(len(service['secrets']) for service in validated['services'].values()),11)
        # Long syntax can explicitly use the same absolute destination too.
        config['services']['postgres']['secrets'][-1]['target']='/run/secrets/lifecycle'
        a.validate_config(config,source,IMAGE)

    def test_secret_target_aliases_do_not_admit_other_paths_or_ownership_overrides(self):
        source=Path('/private/candidate/source')
        for service in ('api','calculation','lifecycle','operator','migrate','postgres'):
            baseline=configuration(source)
            mapping=baseline['services'][service]['secrets'][0]
            for change in ({'target':'/tmp/'+mapping['target']},
                           {'target':'/run/secrets/../'+mapping['target']},
                           {'target':'/run/secrets//'+mapping['target']},
                           {'target':'nested/'+mapping['target']},
                           {'target':'/run/secrets/unreviewed'},
                           {'source':'unreviewed'},{'uid':'0'},{'uid':'10001'},
                           {'gid':'0'},{'mode':0o400},{'mode':0o444}):
                with self.subTest(service=service,field=next(iter(change))):
                    candidate=deepcopy(baseline)
                    candidate['services'][service]['secrets'][0].update(change)
                    with self.assertRaises(c.DeploymentHold):a.validate_config(candidate,source,IMAGE)
        config=configuration(source)
        config['services']['postgres']['secrets'][1]=dict(config['services']['postgres']['secrets'][0])
        with self.assertRaises(c.DeploymentHold):a.validate_config(config,source,IMAGE)

    def test_public_ports_live_flags_external_volume_extra_mount_and_unbounded_resources_hold(self):
        source=Path('/private/candidate/source')
        mutations=[
            lambda c:c['services']['postgres'].update(ports=[{'published':'5432'}]),
            lambda c:c['services']['api']['ports'][0].update(host_ip='0.0.0.0'),
            lambda c:c['services']['operator']['ports'][0].update(host_ip='0.0.0.0'),
            lambda c:c['services']['operator']['environment'].update(TRADEBOT_COLLECTOR_ENABLED='true'),
            lambda c:c['services']['operator']['secrets'].pop(),
            lambda c:c['services']['operator']['networks'].pop('api_loopback'),
            lambda c:c['services']['api']['environment'].update(TRADEBOT_COLLECTOR_ENABLED='true'),
            lambda c:c['services']['lifecycle']['environment'].update(TRADEBOT_RETIREMENT_ENABLED='true'),
            lambda c:c['services']['calculation']['environment'].update(OPENAI_API_KEY='private'),
            lambda c:c['services']['api'].update(volumes=[{'source':'/data/prod','target':'/data'}]),
            lambda c:c['volumes']['pp_pgdata'].update(driver_opts={'device':'/data/prod'}),
            lambda c:c['networks']['database'].update(internal=False),
            lambda c:c['services']['api'].update(mem_limit='2g'),
            lambda c:c['services']['api'].update(tmpfs=['/tmp:mode=1777']),
            lambda c:c['services']['api'].update(entrypoint=['sh']),
            lambda c:c['services']['api'].update(configs=[{'source':'secret'}]),
            lambda c:c['services']['api'].update(command=['python','-m','postgres.migrate']),
            lambda c:c['secrets']['app_dsn'].update(file='/etc/tradebot/prod-runtime/app_dsn'),
            lambda c:c['services']['api'].update(use_api_socket=True),
            lambda c:c['services']['api'].update(post_start=[{'command':'touch /data/unsafe'}]),
            lambda c:c['services']['api'].update(pre_stop=[{'command':'touch /data/unsafe'}]),
            lambda c:c['services']['api'].update(volumes_from=['otherproject']),
            lambda c:c['services']['postgres'].update(command=['postgres','-c','fsync=off']),
            lambda c:c['services']['postgres']['environment'].update(POSTGRES_HOST_AUTH_METHOD='trust'),
            lambda c:c['services']['postgres']['environment'].update(POSTGRES_INITDB_ARGS='--auth-host=trust'),
            lambda c:c['services']['postgres']['secrets'].append({'source':'app_dsn','target':'app_dsn'}),
            lambda c:c['services']['postgres']['secrets'][0].update(target='other'),
        ]
        for index,mutate in enumerate(mutations):
            with self.subTest(case=index):
                config=configuration(source);mutate(config)
                with self.assertRaises(c.DeploymentHold):a.validate_config(config,source,IMAGE)

    def test_memory_normalization_is_bounded_not_eval(self):
        self.assertEqual(a.memory_bytes('192m'),192*1024**2)
        for value in ('192;echo bad','-1','NaN',''):
            with self.assertRaises(c.DeploymentHold):a.memory_bytes(value)


class ActionTests(unittest.TestCase):
    def test_live_filesystem_validates_volume_and_container_bind_before_sampling(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = root/'volumes'/a.PG_VOLUME/'_data'
            data.mkdir(parents=True)
            secret = root/'lifecycle_dsn'
            secret.touch()
            device = str(data.stat().st_dev).encode()
            pg = {'Type':'volume','Source':str(data),'Destination':'/var/lib/postgresql/data','Name':a.PG_VOLUME}
            bind = {'Type':'bind','Source':str(secret),'Destination':'/run/secrets/lifecycle_dsn','RW':False}
            actions = a.LinuxActions()
            budget = Mock()
            def inspect(_budget, ids):
                return [{'Mounts':[pg] if ids==['postgres'] else [bind]}]
            with patch.object(a,'RUNTIME_SECRETS',root), \
                 patch.object(actions,'_ids',side_effect=lambda _c,_b,services:services), \
                 patch.object(actions,'_inspect',side_effect=inspect), \
                 patch.object(a.shutil,'disk_usage',return_value=SimpleNamespace(free=10*1024**3)) as space:
                budget.run.return_value=device
                actions._live_filesystem(None,budget)
                space.assert_called_with(data)
                budget.run.side_effect = [device,b'0']
                with self.assertRaisesRegex(c.DeploymentHold,'device_mismatch'):
                    actions._live_filesystem(None,budget)
                budget.run.side_effect = None
                bind['RW']=True
                with self.assertRaisesRegex(c.DeploymentHold,'runtime_binding'):
                    actions._live_filesystem(None,budget)
                bind['RW']=False
                space.return_value.free-=1
                with self.assertRaisesRegex(c.DeploymentHold,'filesystem_reserve'):
                    actions._live_filesystem(None,budget)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        source=Path(self.temp.name)/'source';source.mkdir()
        folder=source/'deploy/preprod';folder.mkdir(parents=True)
        (folder/'Dockerfile').write_text('FROM '+a.PYTHON_IMAGE+'\n')
        self.context=c.Context(c.Request('a'*40,'b'*64,'c'*64),source,Path(self.temp.name),IMAGE)
        self.budget=RecordingBudget()
        self.actions=a.LinuxActions()
    def tearDown(self):self.temp.cleanup()

    def test_compose_uses_fixed_paths_local_engine_and_no_inherited_credentials(self):
        with patch.dict('os.environ',{'DOCKER_HOST':'tcp://remote:2375','PP_SECRET_DIR':'/production','API_KEY':'secret'}):
            self.actions._compose(self.context,self.budget,['config','--format','json'])
        command,options=self.budget.calls[0]
        self.assertEqual(command[:7],['docker','compose','--env-file','/dev/null','--project-name',a.PROJECT,'--project-directory'])
        self.assertEqual(options['env']['DOCKER_HOST'],'unix:///var/run/docker.sock')
        self.assertEqual(options['env']['PP_SECRET_DIR'],str(a.SECRETS))
        self.assertNotIn('API_KEY',options['env'])
        self.assertNotIn('--privileged',command)

    def test_preflight_checks_config_before_any_database_action(self):
        config=configuration(self.context.source,'sha256:'+'0'*64)
        config['services']['api']['ports'][0]['host_ip']='0.0.0.0'
        with patch.object(self.actions,'_host'),patch.object(self.actions,'_postgres') as postgres:
            self.budget.responses=[json.dumps(config).encode()]
            with self.assertRaises(c.DeploymentHold):self.actions.preflight(self.context,self.budget)
            postgres.assert_not_called()
        self.assertTrue(all('up' not in args and 'run' not in args for args,_ in self.budget.calls))

    def test_profiled_migration_is_inspected_without_enabling_it_for_runtime_start(self):
        budget=self.budget
        def rendered_config(args,**kwargs):
            budget.calls.append((args,kwargs))
            if 'config' in args:
                config=configuration(self.context.source,'sha256:'+'0'*64)
                if '--profile' not in args or args[args.index('--profile')+1]!='migration':
                    del config['services']['migrate']  # Compose v5 inactive-profile behavior.
                return json.dumps(config).encode()
            return b''
        budget.run=rendered_config
        with patch.object(self.actions,'_host'),patch.object(self.actions,'_postgres'), \
             patch.object(self.actions,'_outbox_release_preflight') as outbox,patch.object(self.actions,'_inventory'):
            self.actions.preflight(self.context,budget)
        outbox.assert_called_once_with(budget)
        self.assertEqual(set(self.actions.config['services']),set(a.MEMORY))
        rendered=budget.calls[0][0]
        self.assertLess(rendered.index('--profile'),rendered.index('config'))
        self.actions._compose(self.context,budget,['up','-d','--no-deps','api'])
        self.assertNotIn('--profile',budget.calls[-1][0])
        incomplete=configuration(self.context.source,IMAGE)
        del incomplete['services']['migrate']
        with self.assertRaisesRegex(c.DeploymentHold,'unexpected_compose_project_or_services'):
            a.validate_config(incomplete,self.context.source,IMAGE)

    def test_build_binds_source_label_and_uses_actual_iid_not_mutable_tag(self):
        self.actions.config=configuration(self.context.source)
        budget=self.budget
        original=budget.run
        def run(args,**kwargs):
            if args[:2]==['docker','build']:
                Path(args[args.index('--iidfile')+1]).write_text(IMAGE)
            return original(args,**kwargs)
        budget.run=run
        budget.responses=[b'',json.dumps([{'Id':IMAGE,'Config':{'User':'10001:10001','Labels':{'tradebot.source_sha':'a'*40}}}]).encode(),
                          json.dumps(configuration(self.context.source)).encode()]
        self.assertEqual(self.actions.build(self.context,budget),IMAGE)
        self.assertIn('tradebot.source_sha='+'a'*40,budget.calls[0][0])
        self.assertNotIn('-t',budget.calls[0][0])

    def test_migration_fences_writers_before_explicit_migrate_and_preserves_existing_rows(self):
        calls=[]
        original={'core.predictions':{'count':1,'digest':'a'*32}}
        with patch.object(self.actions,'_capture_prior_runtime'), \
             patch.object(self.actions,'_fence',side_effect=lambda *_:calls.append('fence')), \
             patch.object(self.actions,'_inventory',side_effect=[original,original]), \
             patch.object(self.actions,'_compose',side_effect=lambda ctx,budget,args,**kw:(calls.append(args) or b'{"environment":"preprod","operation":"migrate","result":[1]}')):
            self.actions.migrate(self.context,self.budget)
        self.assertEqual(calls[0],'fence')
        self.assertEqual(calls[1][:3],['run','--rm','--no-deps'])
        self.assertEqual(calls[1][-1],'migrate')
        self.assertIn(a.ATTEMPT_LABEL+'='+self.actions.attempt_id,calls[1])
        self.assertTrue(self.actions.migrated)

    def test_migration_existing_evidence_change_is_held_without_restore(self):
        with patch.object(self.actions,'_capture_prior_runtime'),patch.object(self.actions,'_fence'),patch.object(self.actions,'_inventory',side_effect=[{'core.predictions':{'count':1}}, {'core.predictions':{'count':0}}]), \
             patch.object(self.actions,'_compose',return_value=b'{"environment":"preprod","operation":"migrate","result":[1]}'):
            with self.assertRaisesRegex(c.DeploymentHold,'migration_changed_existing_evidence'):
                self.actions.migrate(self.context,self.budget)
        self.assertFalse(self.actions.migrated)

    def test_generated_storage_inventory_uses_reader_before_and_after_upgrade(self):
        for installed in (False,True):
            with self.subTest(installed=installed):
                def application(_,query):
                    self.assertNotIn('generated_outbox_storage',query)
                    self.assertTrue(query.startswith('SELECT to_regclass('))
                    return 'f'
                def reader(_,query):
                    self.assertIn('archive.generated_outbox_storage',query)
                    self.assertTrue(query.startswith('SELECT to_regclass('))
                    return 't' if installed else 'f'
                def digest(_,table,identity,directory):
                    self.assertEqual(directory, self.context.staging)
                    self.assertEqual(table,'archive.generated_outbox_storage')
                    self.assertEqual(identity,"origin_id,outbox_id,generation_id,envelope_hash,encode(sha256(envelope),'hex'),stored_at")
                    return {'count':2,'digest':'a'*64}
                with patch.object(self.actions,'_sql',side_effect=application), \
                     patch.object(self.actions,'_reader_sql',side_effect=reader) as read, \
                     patch.object(self.actions,'_metadata_digest',side_effect=digest) as hashed:
                    inventory=self.actions._inventory(self.budget,self.context.staging)
                self.assertEqual(inventory['archive.generated_outbox_storage'],
                                 {'count':2,'digest':'a'*64} if installed else None)
                self.assertEqual(read.call_count,1)
                self.assertEqual(hashed.call_count,int(installed))

    def test_generated_migration_inventory_uses_its_controller_staging_before_and_after(self):
        seen=[]
        def inventory(budget,directory):
            self.assertIs(budget,self.budget)
            self.assertEqual(directory,self.context.staging)
            seen.append(directory)
            return {'raw.events':None} if len(seen)==1 else {'raw.events':{'count':0,'digest':'a'*64}}
        with patch.object(self.actions,'_capture_prior_runtime'), patch.object(self.actions,'_fence'), \
             patch.object(self.actions,'_inventory',side_effect=inventory), \
             patch.object(self.actions,'_oneoff',return_value=b'{"environment":"preprod","operation":"migrate","result":[1]}'):
            self.actions.migrate(self.context,self.budget)
        self.assertEqual(seen,[self.context.staging]*2)

    def test_missing_staging_holds_with_an_identifiable_reason(self):
        with self.assertRaisesRegex(c.DeploymentHold,'metadata_scratch_directory'), \
             patch.object(self.actions,'_outbox_channel') as channel:
            self.actions._metadata_digest(self.budget,'core.markets','market_id',self.context.staging/'missing')
        channel.assert_not_called()

    def test_generated_storage_inventory_authenticates_reader_read_only(self):
        self.actions.pg_id=CID
        self.budget.responses=[b't\n']
        self.assertEqual(self.actions._reader_sql(self.budget,'SELECT true'),'t')
        args,kwargs=self.budget.calls[0]
        self.assertEqual(args[:4],['docker','exec','-i',CID])
        self.assertIn('cat /run/secrets/reader',args[-1])
        self.assertIn('-U tradebot_reader',args[-1])
        self.assertEqual(kwargs['input'],b"BEGIN READ ONLY; SET LOCAL statement_timeout='19s'; SELECT true; COMMIT;")
        self.assertEqual(kwargs['timeout'],20)

    def test_outbox_inventory_checks_12779_rows_across_two_origins_after_oneoff(self):
        calls=[]
        def sql(_,query):
            calls.append(query)
            if query.startswith('SELECT to_regclass('):
                return 't' if "'ops.outbox'" in query else 'f'
            if 'SELECT coalesce(json_agg(origin_id' in query:
                return '["generated-pp","pp-live-pp"]'
            raise AssertionError('unexpected inventory query')
        proofs={'generated-pp':{'count':17511,'pending':7511,'digest':'a'*64},
                'pp-live-pp':{'count':5268,'pending':5268,'digest':'b'*64}}
        with patch.object(self.actions,'_sql',side_effect=sql), \
             patch.object(self.actions,'_reader_sql',side_effect=sql), \
             patch.object(self.actions,'_outbox_channel'), \
             patch('linux_actions.outbox_digests',return_value=proofs) as digests:
            original=self.actions._inventory(self.budget)
            self.actions.before_migration=original
            self.actions.fence_started=True
            self.actions.migration_oneoff_attempted=True
            with patch.object(self.actions,'_fence'),patch.object(self.actions,'_postgres'):
                recovery=self.actions.recover(replace(self.context,failed_stage='migrate',migration_started=True),self.budget)
        self.assertEqual(original['ops.outbox'],{
            'generated-pp':{'count':17511,'pending':7511,'digest':'a'*64},
            'pp-live-pp':{'count':5268,'pending':5268,'digest':'b'*64}})
        self.assertEqual(recovery['strategy'],'stop_candidate_keep_database')
        self.assertTrue(recovery['new_acknowledgements_preserved'])
        self.assertEqual(digests.call_count,3)
        self.assertTrue(all(set(proofs).issubset(call.args[1]) for call in digests.call_args_list))
        self.assertFalse(any('FROM ops.outbox LIMIT 10001' in q for q in calls))
        for query in calls:
            self.assertTrue(query.startswith(('SELECT ', 'WITH ranges AS MATERIALIZED')))
            self.assertNotRegex(query.upper(), r'\b(INSERT|UPDATE|DELETE|ALTER|TRUNCATE|DROP|CREATE)\b')

    def test_overbound_outbox_holds_in_read_only_preflight_before_fence(self):
        def sql(_,query):
            if query=="SELECT to_regclass('ops.outbox') IS NOT NULL":return 't'
            if 'SELECT coalesce(json_agg(origin_id' in query:return '["generated-pp"]'
            if "WHERE origin_id='generated-pp'" in query:return '10001'
            raise AssertionError('unexpected preflight query')
        config=json.dumps(configuration(self.context.source,'sha256:'+'0'*64)).encode()
        with patch.object(self.actions,'_host'),patch.object(self.actions,'_postgres'), \
             patch.object(self.actions,'_compose',return_value=config), \
             patch.object(self.actions,'_sql',side_effect=sql), \
             patch.object(self.actions,'_fence') as fence:
            with self.assertRaisesRegex(c.DeploymentHold,'outbox_inventory_exceeds_release_bound'):
                self.actions.preflight(self.context,self.budget)
            fence.assert_not_called()
        self.assertEqual(self.budget.calls,[])

    def test_outbox_release_preflight_accepts_two_bounded_origins(self):
        calls=[]
        def sql(_,query):
            calls.append(query)
            if query=="SELECT to_regclass('ops.outbox') IS NOT NULL":return 't'
            if 'SELECT coalesce(json_agg(origin_id' in query:return '["generated-pp","pp-live-pp"]'
            if "WHERE origin_id='generated-pp'" in query:return '7511'
            if "WHERE origin_id='pp-live-pp'" in query:return '5268'
            raise AssertionError('unexpected preflight query')
        with patch.object(self.actions,'_sql',side_effect=sql):
            self.actions._outbox_release_preflight(self.budget)
        self.assertEqual(len(calls),4)
        self.assertTrue(all(q.startswith('SELECT ') for q in calls))
        self.assertEqual(sum('acknowledged_at IS NULL LIMIT 10001' in q for q in calls),2)

    def test_outbox_inventory_rejects_overbound_or_unknown_origin(self):
        for origins,count in [(['generated-pp'],10001),
                              (['generated-pp','pp-live-pp','unexpected'],7511),
                              (['generated-pp',None],7511),
                              (['unexpected'],7511)]:
            with self.subTest(origins=origins,count=count):
                def sql(_,query):
                    if query.startswith('SELECT to_regclass('):
                        return 't' if "'ops.outbox'" in query else 'f'
                    if 'SELECT coalesce(json_agg(origin_id' in query:
                        return json.dumps(origins)
                    if "WHERE origin_id='generated-pp'" in query:
                        return json.dumps({'count':count,'pending':count,'digest':'a'*64})
                    raise AssertionError('unexpected inventory query')
                from contextlib import nullcontext
                from deploy.preprod.tests.test_outbox_cursor_protocol import ScriptedSnapshot
                header=[[origin,10,count] for origin in origins]
                pages=[[origin,n,n*1024,n*1024+1023,min(1024,count-n*1024)] for origin in origins for n in range(10)]
                hashes=[[desc[-1],desc[-1],'a'*64] for desc in pages]
                snapshot=ScriptedSnapshot(header,pages,hashes)
                with patch.object(self.actions,'_sql',side_effect=sql), \
                     patch.object(self.actions,'_outbox_channel',return_value=nullcontext(snapshot)):
                    with self.assertRaisesRegex(c.DeploymentHold,
                                                'outbox_inventory_invalid|unexpected_outbox_origin'):
                        self.actions._inventory(self.budget)

    def test_outbox_recovery_rejects_changed_origin_fingerprint(self):
        self.actions.before_migration={'ops.outbox':{
            'generated-pp':{'count':7511,'digest':'a'*32},
            'pp-live-pp':{'count':5268,'digest':'b'*32}}}
        current={'ops.outbox':{
            'generated-pp':{'count':7511,'digest':'a'*32},
            'pp-live-pp':{'count':5268,'digest':'c'*32}}}
        self.actions.fence_started=True
        self.actions.migration_oneoff_attempted=True
        with patch.object(self.actions,'_fence'),patch.object(self.actions,'_postgres'), \
             patch.object(self.actions,'_inventory',return_value=current):
            with self.assertRaisesRegex(c.DeploymentHold,'migration_recovery_evidence_changed'):
                self.actions.recover(replace(self.context,failed_stage='migrate',migration_started=True),self.budget)

    def test_start_holds_before_services_without_verified_generated_headroom(self):
        self.actions.migrated=True
        self.budget.responses=[b'{"retirement":"off","archive":"held_no_qualified_transport"}']
        with self.assertRaisesRegex(c.DeploymentHold,'generated_durable_headroom_not_proven'):
            self.actions.start(self.context,self.budget)
        self.assertFalse(any('--force-recreate' in args for args,_ in self.budget.calls))

    def test_start_requires_migration_and_never_starts_postgres(self):
        with self.assertRaisesRegex(c.DeploymentHold,'explicit_migration_required'):
            self.actions.start(self.context,self.budget)
        self.actions.migrated=True
        self.budget.responses=[json.dumps({'retirement':'off','archive':'held_no_qualified_transport','generated_storage':{'scope':'durable_generated_local_storage','headroom':128,'pending':9872,'raw_retirement_authorized':False,'cloud_receipts':False}}).encode(),b'']
        self.actions.start(self.context,self.budget)
        commands=[args for args,_ in self.budget.calls]
        self.assertIn('--bootstrap',commands[0])
        startup=next(args for args in commands if '--force-recreate' in args)
        self.assertEqual(startup[-len(a.SERVICES):],list(a.SERVICES))
        self.assertIn('--no-deps',startup)

    def test_recovery_fences_restart_then_stops_only_application_services(self):
        self.actions.pg_id=CID;self.actions.pg_volume=a.PG_VOLUME
        with patch.object(self.actions,'_ids',return_value=[CID]),patch.object(self.actions,'_inspect',return_value=[inspected(running=False)]), \
             patch.object(self.actions,'_postgres'),patch.object(self.actions,'_inventory',return_value={'core.predictions':{'count':2,'digest':'f'*32}}):
            result=self.actions.recover(replace(self.context,failed_stage='start',migration_started=True),self.budget)
        self.assertTrue(result['database_preserved'])
        self.assertTrue(result['new_acknowledgements_preserved'])
        self.assertFalse(result['database_restored'])
        self.assertEqual(self.budget.calls[0][0],['docker','update','--restart=no',CID])
        stop=self.budget.calls[1][0]
        self.assertEqual(stop[-(len(a.SERVICES)+2):],['--timeout','20',*a.SERVICES])
        self.assertNotIn('postgres',stop)
        self.assertTrue(all('down' not in args and '--volumes' not in args and 'rm' not in args for args,_ in self.budget.calls))

    def test_recovery_failure_never_claims_acknowledgement_preservation(self):
        with patch.object(self.actions,'_fence'),patch.object(self.actions,'_postgres'), \
             patch.object(self.actions,'_inventory',side_effect=[{'core.predictions':{'count':2}}, {'core.predictions':{'count':1}}]):
            with self.assertRaisesRegex(c.DeploymentHold,'database_changed_after_writer_fence'):
                self.actions.recover(replace(self.context,failed_stage='smoke',migration_started=True),self.budget)

    def test_build_failure_keeps_prior_runtime_untouched(self):
        with patch.object(self.actions,'_fence') as fence,patch.object(self.actions,'_inventory') as inventory:
            result=self.actions.recover(replace(self.context,failed_stage='build',migration_started=False),self.budget)
        self.assertEqual(result['strategy'],'prior_runtime_unchanged')
        self.assertTrue(result['database_preserved'])
        self.assertEqual(self.budget.calls,[])
        fence.assert_not_called();inventory.assert_not_called()

    def test_cli_timeout_stubborn_oneoff_is_killed_removed_before_inventory(self):
        budget=OneoffBudget(self.actions,self.context)
        with self.assertRaisesRegex(c.DeploymentHold,'child_deadline_exceeded'):
            self.actions._oneoff(self.context,budget,'migrate')
        self.assertTrue(self.actions.oneoffs)
        self.assertTrue(budget.exists)
        checks=[]
        def inventory(_,directory):
            self.assertEqual(directory,self.context.staging)
            self.assertFalse(budget.exists)
            checks.append(True)
            return {'core.predictions':{'count':1,'digest':'a'*32}}
        with patch.object(self.actions,'_fence'),patch.object(self.actions,'_postgres'),patch.object(self.actions,'_inventory',side_effect=inventory):
            result=self.actions.recover(replace(self.context,failed_stage='migrate',migration_started=True),budget)
        self.assertEqual(result['strategy'],'stop_candidate_keep_database')
        self.assertEqual(len(checks),2)
        operations=[args[:2] for args,_ in budget.calls]
        self.assertIn(['docker','stop'],operations)
        self.assertIn(['docker','kill'],operations)
        self.assertIn(['docker','rm'],operations)
        self.assertFalse(self.actions.oneoffs)
        for args,_ in budget.calls:
            if args[:2] in (['docker','stop'],['docker','kill'],['docker','rm']):
                self.assertEqual(args[-1],CID)
        searches=[args for args,_ in budget.calls if args[:2]==['docker','ps']]
        self.assertTrue(all('label='+a.ATTEMPT_LABEL+'='+self.actions.attempt_id in args for args in searches))
        self.assertTrue(all('label=com.docker.compose.project='+a.PROJECT in args for args in searches))

    def test_unstoppable_oneoff_blocks_inventory_and_preservation_claim(self):
        budget=OneoffBudget(self.actions,self.context);budget.ignore_kill=True
        with self.assertRaises(c.DeploymentHold):self.actions._oneoff(self.context,budget,'migrate')
        with patch.object(self.actions,'_fence'),patch.object(self.actions,'_postgres'),patch.object(self.actions,'_inventory') as inventory:
            with self.assertRaisesRegex(c.DeploymentHold,'deployment_oneoff_still_running'):
                self.actions.recover(replace(self.context,failed_stage='migrate',migration_started=True),budget)
            inventory.assert_not_called()
        self.assertTrue(budget.exists)
        self.assertNotIn(['docker','rm'],[args[:2] for args,_ in budget.calls])

    def test_oneoff_from_other_attempt_is_never_stopped_or_removed(self):
        budget=OneoffBudget(self.actions,self.context)
        with self.assertRaises(c.DeploymentHold):self.actions._oneoff(self.context,budget,'migrate')
        budget.foreign=True
        with self.assertRaisesRegex(c.DeploymentHold,'oneoff_ownership_mismatch'):
            self.actions._cleanup_oneoffs(self.context,budget)
        self.assertFalse(any(args[:2] in (['docker','stop'],['docker','kill'],['docker','rm']) for args,_ in budget.calls))

    def test_service_fence_never_adopts_another_attempt_oneoff(self):
        row=inspected(service='lifecycle',running=False)
        row['Config']['Labels']['com.docker.compose.oneoff']='True'
        with patch.object(self.actions,'_ids',return_value=[CID]),patch.object(self.actions,'_inspect',return_value=[row]):
            with self.assertRaisesRegex(c.DeploymentHold,'unowned_container_blocks_runtime_fence'):
                self.actions._fence(self.context,self.budget)
        self.assertEqual(self.budget.calls,[])

    def test_runtime_inspection_rejects_wrong_image_public_port_and_privilege(self):
        for mutation in (lambda r:r.update(Image='sha256:'+'f'*64),
                         lambda r:r['HostConfig'].update(Privileged=True),
                         lambda r:r['HostConfig'].update(PortBindings={'8000/tcp':[{'HostIp':'0.0.0.0','HostPort':'8000'}]}),
                         lambda r:r['NetworkSettings']['Ports'].update({'8000/tcp':None}),
                         lambda r:r['NetworkSettings']['Networks'].pop(a.API_NETWORK)):
            row=inspected();mutation(row)
            with patch.object(self.actions,'_ids',return_value=[CID]),patch.object(self.actions,'_inspect',return_value=[row]):
                with self.assertRaises(c.DeploymentHold):self.actions._runtime(self.context,self.budget)

    def test_live_runtime_requires_exact_origin_flags_and_app_secret(self):
        ids=lambda _context,_budget,services:[services[0]]
        rows=lambda _budget,items:[inspected(service=items[0],live=True)]
        with patch.object(self.actions,'_ids',side_effect=ids), \
             patch.object(self.actions,'_inspect',side_effect=rows):
            self.actions._runtime(self.context,self.budget,live=True)
        self.assertEqual(a.expected_environment('api',live=True)['TRADEBOT_ORIGIN_ID'],'pp-live-pp')
        self.assertIn('app_dsn',a.service_secrets('operator',live=True))
        self.assertNotIn('app_dsn',a.service_secrets('operator'))
        for mutation in (
            lambda row:row['Config']['Env'].append('ENABLE_SUPABASE_SYNC=true'),
            lambda row:row['Mounts'].pop(),
            lambda row:row['Config']['Env'].append('TRADEBOT_ORIGIN_ID=generated-pp'),
        ):
            def changed(_budget,items):
                row=inspected(service=items[0],live=True)
                if items[0]=='operator':mutation(row)
                return [row]
            with patch.object(self.actions,'_ids',side_effect=ids), \
                 patch.object(self.actions,'_inspect',side_effect=changed), \
                 self.assertRaises(c.DeploymentHold):
                self.actions._runtime(self.context,self.budget,live=True)

    def test_owned_lifecycle_oneoff_uses_only_explicit_live_compose(self):
        commands=[]
        def selected(args,timeout):
            commands.append((args,timeout))
            return b'{"collector_enabled":false}'
        with patch.object(self.actions,'_cleanup_oneoffs') as cleanup, \
             patch.object(self.actions,'_compose') as base:
            result=self.actions._oneoff(self.context,self.budget,'lifecycle',
                ['python','-m','postgres.lifecycle_worker','--stop-collector'],
                timeout=30,compose=selected)
        self.assertEqual(result,b'{"collector_enabled":false}')
        self.assertEqual(len(commands),1)
        self.assertIn(a.ATTEMPT_LABEL+'='+self.actions.attempt_id,commands[0][0])
        self.assertIn(a.SOURCE_LABEL+'='+self.context.request.source_sha,commands[0][0])
        self.assertEqual(commands[0][0][-4:],['python','-m','postgres.lifecycle_worker','--stop-collector'])
        self.assertEqual(commands[0][1],30)
        cleanup.assert_called_once()
        base.assert_not_called()

    def test_host_api_requires_private_generated_state(self):
        class Response:
            def __init__(self,payload):self.payload=payload
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,limit):return json.dumps(self.payload).encode()
        valid={'environment':'preprod','data_mode':'generated','origin_id':'generated-pp',
               'collector':{'enabled':False}}
        for payload in (valid,{**valid,'environment':'production'},
                        {**valid,'collector':{'enabled':True}},
                        {**valid,'data_mode':'production_preview'}):
            with patch.object(a.urllib.request.OpenerDirector,'open',return_value=Response(payload)) as opened:
                if payload is valid:self.actions._host_api()
                else:
                    with self.assertRaises(c.DeploymentHold):self.actions._host_api()
                self.assertEqual(opened.call_args.args[0],'http://127.0.0.1:8000/state/current')

    def test_host_live_api_requires_pp_origin_and_durable_off(self):
        class Response:
            def __init__(self,payload):self.payload=payload
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,_limit):return json.dumps(self.payload).encode()
        valid={'environment':'preprod','data_mode':'pp_live','origin_id':'pp-live-pp',
               'collector':{'enabled':False}}
        for payload in (valid,{**valid,'origin_id':'generated-pp'},
                        {**valid,'collector':{'enabled':None}},
                        {**valid,'collector':{'enabled':True}}):
            with patch.object(a.urllib.request.OpenerDirector,'open',return_value=Response(payload)):
                if payload is valid:self.actions._host_api(live=True)
                else:
                    with self.assertRaises(c.DeploymentHold):self.actions._host_api(live=True)

    def test_host_operator_proves_live_on_route_without_enabling_it(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,_limit):return json.dumps({
                'environment':'preprod','origin_id':'pp-live-pp',
                'collector_enabled':False,'initialized':True,
                'process_running':False,'live_fence_qualified':False}).encode()
        class Opener:
            def __init__(self,on_code):self.on_code=on_code;self.paths=[]
            def open(self,target,timeout):
                path=target if isinstance(target,str) else target.full_url
                self.paths.append(path)
                if len(self.paths)==1:raise HTTPError(path,401,'unauthorized',None,None)
                if len(self.paths)==2:return Response()
                raise HTTPError(path,self.on_code,'route check',None,None)
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'operator_token').write_text('fixture-token')
            for code,passes in ((405,True),(404,False),(200,False)):
                opener=Opener(code)
                with patch.object(a,'RUNTIME_SECRETS',Path(folder)), \
                     patch.object(a.urllib.request,'build_opener',return_value=opener):
                    if passes:self.actions._host_operator(live=True)
                    else:
                        with self.assertRaises(c.DeploymentHold):self.actions._host_operator(live=True)
                self.assertEqual(opener.paths[-1],'http://127.0.0.1:8001/collector/on')

    def test_smoke_does_not_turn_status200_or_partial_acceptance_into_pass(self):
        self.actions.migrated=True
        with patch.object(self.actions,'_runtime'),patch.object(self.actions,'_host_api'),patch.object(self.actions,'_host_operator'),patch.object(self.actions,'_compose',side_effect=[
             b'{"environment":"preprod","operation":"check","result":1}',b'{"status":"pass"}']):
            with self.assertRaisesRegex(c.DeploymentHold,'generated_acceptance_incomplete'):
                self.actions.smoke(self.context,self.budget)

    def test_smoke_proves_api_only_restart_freshness_and_ack_anchor(self):
        self.actions.migrated=True;self.actions.pg_id=CID
        acceptance={'status':'pass','scope':'generated_local_api','generated_headroom_verified':True,'origin_id':'generated-pp','collector_enabled':False,
                    'sse_connections':2,'acknowledged_events':21,'api_max_seconds':.01,
                    **dict.fromkeys(('conflict_detected','exact_decimal_roundtrip','api_ram_after_commit','dashboard_contract','bounded_chart','prediction_history'),True)}
        anchor={'fresh':True,'market_identity':True,'collector_disabled':True,'schema_verified':True,
                'prediction_id':'a'*64,'prediction_hash':'b'*64,'price_event_id':'generated-price','price_hash':'c'*64}
        calls=[]
        def compose(ctx,budget,args,**kwargs):
            calls.append(args)
            if '--check' in args:return b'{"environment":"preprod","operation":"check","result":1}'
            if 'postgres.acceptance' in args:return json.dumps(acceptance).encode()
            return b''
        with patch.object(self.actions,'_runtime'),patch.object(self.actions,'_host_api'),patch.object(self.actions,'_host_operator'),patch.object(self.actions,'_compose',side_effect=compose), \
             patch.object(self.actions,'_postgres'),patch.object(self.actions,'_probe',side_effect=[anchor,{**anchor,'prior_acknowledgement_preserved':True}]) as probe:
            result=self.actions.smoke(self.context,self.budget)
        self.assertEqual(result['checks'],dict.fromkeys(c.CHECKS,'PASS'))
        self.assertEqual(result['acceptance_scope'],'generated_only')
        self.assertEqual(probe.call_args_list[-1].args[-1],anchor)
        self.assertIn(['restart','--timeout','10','api'],calls)
        self.assertFalse(any('postgres' in args or 'calculation' in args or 'lifecycle' in args for args in calls))

    def test_smoke_reseeds_only_expired_generated_market_and_keeps_old_anchor(self):
        self.actions.migrated=True;self.actions.pg_id=CID
        acceptance={'status':'pass','scope':'generated_local_api','generated_headroom_verified':True,'origin_id':'generated-pp','collector_enabled':False,
                    'sse_connections':2,'acknowledged_events':21,'api_max_seconds':.01,
                    **dict.fromkeys(('conflict_detected','exact_decimal_roundtrip','api_ram_after_commit',
                                      'dashboard_contract','bounded_chart','prediction_history'),True)}
        anchor={'fresh':True,'market_identity':True,'collector_disabled':True,'schema_verified':True,
                'prediction_id':'a'*64,'prediction_hash':'b'*64,'price_event_id':'generated-price','price_hash':'c'*64}
        calls=[]
        def compose(ctx,budget,args,**kwargs):
            calls.append(args)
            if '--check' in args:return b'{"environment":"preprod","operation":"check","result":1}'
            if 'postgres.acceptance' in args:return json.dumps(acceptance).encode()
            return b''
        probes=[{'status':'expired_generated_market'},anchor,
                {'status':'expired_generated_market'},{**anchor,'prior_acknowledgement_preserved':True}]
        with patch.object(self.actions,'_runtime'),patch.object(self.actions,'_host_api'),patch.object(self.actions,'_host_operator'),patch.object(self.actions,'_compose',side_effect=compose), \
             patch.object(self.actions,'_postgres'),patch.object(self.actions,'_probe',side_effect=probes) as probe:
            result=self.actions.smoke(self.context,self.budget)
        self.assertEqual(result['checks'],dict.fromkeys(c.CHECKS,'PASS'))
        self.assertEqual(sum('postgres.acceptance' in args for args in calls),4)
        self.assertEqual(probe.call_args_list[-1].args[-1],anchor)
        self.assertEqual(self.actions.smoke_phase,'complete')

    def test_smoke_unknown_probe_failure_is_not_reseeded(self):
        self.actions.migrated=True
        acceptance={'status':'pass','scope':'generated_local_api','generated_headroom_verified':True,'origin_id':'generated-pp','collector_enabled':False,
                    'sse_connections':2,'acknowledged_events':21,'api_max_seconds':.01,
                    **dict.fromkeys(('conflict_detected','exact_decimal_roundtrip','api_ram_after_commit',
                                      'dashboard_contract','bounded_chart','prediction_history'),True)}
        calls=[]
        def compose(ctx,budget,args,**kwargs):
            calls.append(args)
            if '--check' in args:return b'{"environment":"preprod","operation":"check","result":1}'
            if 'postgres.acceptance' in args:return json.dumps(acceptance).encode()
            return b''
        with patch.object(self.actions,'_runtime'),patch.object(self.actions,'_host_api'),patch.object(self.actions,'_host_operator'),patch.object(self.actions,'_compose',side_effect=compose), \
             patch.object(self.actions,'_probe',return_value={'status':'unknown'}):
            with self.assertRaisesRegex(c.DeploymentHold,'freshness_or_market_not_proven'):
                self.actions.smoke(self.context,self.budget)
        self.assertEqual(sum('postgres.acceptance' in args for args in calls),1)



class HostReadinessTests(unittest.TestCase):
    """Exercise actual host HTTP/auth checks with an offline startup listener."""
    class Response:
        def __init__(self,raw):self.raw=raw
        def __enter__(self):return self
        def __exit__(self,*_):return False
        def read(self,_limit):return self.raw

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'operator_token').write_text('offline-token')
        self.actions=a.LinuxActions();self.clock=[0.0];self.paths=[];self.operator_attempts=0
        self.api=dict(environment='preprod',data_mode='generated',origin_id='generated-pp',collector=dict(enabled=False))
        self.operator=dict(environment='preprod',origin_id='pp-live-pp',collector_enabled=False,
                           initialized=False,process_running=None,live_fence_qualified=False)

    def opener(self,*,unavailable=0,operator_payload=None):
        owner=self
        class Opener:
            def open(self,target,timeout):
                path=target if isinstance(target,str) else target.full_url
                owner.paths.append(path)
                if ':8000/' in path:return owner.Response(json.dumps(owner.api).encode())
                if isinstance(target,str) and path.endswith('/collector/status'):
                    owner.operator_attempts+=1
                    if owner.operator_attempts<=unavailable:
                        from urllib.error import URLError
                        raise URLError(ConnectionRefusedError(111,'offline refused'))
                    raise HTTPError(path,401,'unauthorized',{},None)
                if path.endswith('/collector/on'):raise HTTPError(path,404,'absent',{},None)
                return owner.Response(operator_payload if operator_payload is not None else json.dumps(owner.operator).encode())
        return Opener()

    def wait(self,opener,budget=None):
        budget=budget or c.Budget(60,clock=lambda:self.clock[0])
        with patch.object(a,'RUNTIME_SECRETS',self.root), \
             patch.object(a.urllib.request,'build_opener',return_value=opener), \
             patch.object(a.time,'monotonic',side_effect=lambda:self.clock[0]), \
             patch.object(a.time,'sleep',side_effect=lambda seconds:self.clock.__setitem__(0,self.clock[0]+seconds)) as sleep:
            a.wait_generated_host_routes(self.actions,budget)
            return sleep

    def test_delayed_operator_binding_retries_real_auth_and_route_checks(self):
        sleep=self.wait(self.opener(unavailable=2))
        self.assertEqual(self.operator_attempts,3)
        self.assertEqual(sleep.call_count,2)
        self.assertAlmostEqual(self.clock[0],.4)
        self.assertEqual(self.paths[-1],'http://127.0.0.1:8001/collector/on')
        self.assertTrue(all(path.startswith('http://127.0.0.1:') for path in self.paths))

    def test_reachable_wrong_state_and_malformed_json_are_fatal_without_retry(self):
        for payload in (b'{not-json',b'[]',json.dumps({**self.operator,'collector_enabled':True}).encode()):
            with self.subTest(payload=payload):
                self.clock[0]=0;self.operator_attempts=0
                with self.assertRaisesRegex(c.DeploymentHold,'generated_operator_state_check_failed'):
                    self.wait(self.opener(operator_payload=payload))
                self.assertEqual(self.operator_attempts,1);self.assertEqual(self.clock[0],0)

    def test_missing_token_is_fatal_without_connection_retry(self):
        (self.root/'operator_token').unlink()
        with self.assertRaisesRegex(c.DeploymentHold,'generated_operator_state_check_failed'):
            self.wait(self.opener())
        self.assertEqual(self.operator_attempts,1);self.assertEqual(self.clock[0],0)

    def test_persistent_startup_failure_respects_ten_second_and_remaining_budget(self):
        with self.assertRaisesRegex(c.DeploymentHold,'generated_operator_readiness_timeout'):
            self.wait(self.opener(unavailable=1000))
        self.assertLessEqual(self.clock[0],10)
        self.assertGreater(self.operator_attempts,1)
        self.clock[0]=0;self.paths=[]
        with self.assertRaisesRegex(c.DeploymentHold,'generated_api_readiness_timeout'):
            self.wait(self.opener(),c.Budget(1.5,clock=lambda:self.clock[0]))
        self.assertEqual(self.paths,[]);self.assertEqual(self.clock[0],0)

    def test_only_connection_errors_are_retryable(self):
        from urllib.error import URLError
        for error in (ConnectionRefusedError(),TimeoutError(),URLError(ConnectionResetError())):
            self.assertTrue(a._startup_connection_error(error))
        for error in (FileNotFoundError(),ValueError(),URLError('unclassified'),HTTPError('http://127.0.0.1',503,'unavailable',{},None)):
            self.assertFalse(a._startup_connection_error(error))

    def test_smoke_reuses_bounded_poll_before_acceptance(self):
        self.actions.migrated=True
        with patch.object(self.actions,'_oneoff',return_value=b'{"environment":"preprod","operation":"check","result":1}'), \
             patch.object(self.actions,'_runtime'), \
             patch.object(a,'wait_generated_host_routes',side_effect=c.DeploymentHold('generated_operator_readiness_timeout')) as readiness, \
             patch.object(self.actions,'_compose') as acceptance:
            with self.assertRaisesRegex(c.DeploymentHold,'generated_operator_readiness_timeout'):
                self.actions.smoke(None,RecordingBudget())
        readiness.assert_called_once();acceptance.assert_not_called()
        self.assertEqual(self.actions.smoke_phase,'host_routes_readiness')

if __name__=='__main__':unittest.main()
