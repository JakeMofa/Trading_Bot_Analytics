"""Command/guard tests only. These do not claim a qualified Linux deployment."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import controller as c
import linux_actions as a

IMAGE='sha256:'+'a'*64
CID='b'*64


def configuration(source,image=IMAGE):
    config={'name':a.PROJECT,'networks':{'database':{'name':a.NETWORK,'internal':True}},
            'volumes':{'pp_pgdata':{'name':a.PG_VOLUME}},'secrets':{},'services':{}}
    for name in ('admin','migrator','application','reader'):
        config['secrets'][name]={'file':str(a.SECRETS/name)}
    config['secrets']['lifecycle_password']={'file':str(a.SECRETS/'lifecycle')}
    for name in a.ROLE_SECRET.values():config['secrets'][name]={'file':str(a.RUNTIME_SECRETS/name)}
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
                secrets=[{'source':a.ROLE_SECRET[name],'target':a.ROLE_SECRET[name]}],tmpfs=['/tmp:size=16m,mode=1777'])
        if name=='api':service['ports']=[{'host_ip':'127.0.0.1','published':'8000','target':8000,'protocol':'tcp'}]
        config['services'][name]=service
    return config


def inspected(service='api',running=True):
    return {'Id':CID,'Image':IMAGE,'State':{'Running':running,'OOMKilled':False,'Health':{'Status':'healthy'}},
        'Config':{'Image':IMAGE,'Cmd':a.COMMANDS[service],'User':'10001:10001','Labels':{
                  'com.docker.compose.project':a.PROJECT,'com.docker.compose.service':service,'com.docker.compose.oneoff':'False'},
                  'Env':[key+'='+value for key,value in a.expected_environment(service).items()]},
        'HostConfig':{'Memory':a.MEMORY[service]*1024**2,'MemorySwap':a.MEMORY[service]*1024**2,'PidsLimit':64,
                      'ReadonlyRootfs':True,'Privileged':False,'CapDrop':['ALL'],
                      'NanoCpus':int(a.CPUS.get(service,0)*1_000_000_000),
                      'RestartPolicy':{'Name':'unless-stopped' if running else 'no'},
                      'PortBindings':{'8000/tcp':[{'HostIp':'127.0.0.1','HostPort':'8000'}]} if service=='api' else {}},
        'Mounts':[{'Destination':'/run/secrets/'+a.ROLE_SECRET[service],'Source':str(a.RUNTIME_SECRETS/a.ROLE_SECRET[service]),'RW':False}],
        'NetworkSettings':{'Networks':{a.NETWORK:{}}}}


class RecordingBudget:
    def __init__(self):self.calls=[];self.responses=[]
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
        self.assertEqual(sum(len(service['secrets']) for service in validated['services'].values()),9)
        # Long syntax can explicitly use the same absolute destination too.
        config['services']['postgres']['secrets'][-1]['target']='/run/secrets/lifecycle'
        a.validate_config(config,source,IMAGE)

    def test_secret_target_aliases_do_not_admit_other_paths_or_ownership_overrides(self):
        source=Path('/private/candidate/source')
        for service in ('api','calculation','lifecycle','migrate','postgres'):
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
        with patch.object(self.actions,'_host'),patch.object(self.actions,'_postgres'):
            self.actions.preflight(self.context,budget)
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
        with patch.object(self.actions,'_fence',side_effect=lambda *_:calls.append('fence')), \
             patch.object(self.actions,'_inventory',side_effect=[original,original]), \
             patch.object(self.actions,'_compose',side_effect=lambda ctx,budget,args,**kw:(calls.append(args) or b'{"environment":"preprod","operation":"migrate","result":[1]}')):
            self.actions.migrate(self.context,self.budget)
        self.assertEqual(calls[0],'fence')
        self.assertEqual(calls[1][:3],['run','--rm','--no-deps'])
        self.assertEqual(calls[1][-1],'migrate')
        self.assertIn(a.ATTEMPT_LABEL+'='+self.actions.attempt_id,calls[1])
        self.assertTrue(self.actions.migrated)

    def test_migration_existing_evidence_change_is_held_without_restore(self):
        with patch.object(self.actions,'_fence'),patch.object(self.actions,'_inventory',side_effect=[{'core.predictions':{'count':1}}, {'core.predictions':{'count':0}}]), \
             patch.object(self.actions,'_compose',return_value=b'{"environment":"preprod","operation":"migrate","result":[1]}'):
            with self.assertRaisesRegex(c.DeploymentHold,'migration_changed_existing_evidence'):
                self.actions.migrate(self.context,self.budget)
        self.assertFalse(self.actions.migrated)

    def test_start_requires_migration_and_never_starts_postgres(self):
        with self.assertRaisesRegex(c.DeploymentHold,'explicit_migration_required'):
            self.actions.start(self.context,self.budget)
        self.actions.migrated=True
        self.budget.responses=[b'{"retirement":"off","archive":"held_no_qualified_transport"}',b'']
        self.actions.start(self.context,self.budget)
        commands=[args for args,_ in self.budget.calls]
        self.assertIn('--bootstrap',commands[0])
        startup=next(args for args in commands if '--force-recreate' in args)
        self.assertEqual(startup[-3:],list(a.SERVICES))
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
        self.assertEqual(stop[-5:],['--timeout','20',*a.SERVICES])
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
        def inventory(_):
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
                         lambda r:r['HostConfig'].update(PortBindings={'8000/tcp':[{'HostIp':'0.0.0.0','HostPort':'8000'}]})):
            row=inspected();mutation(row)
            with patch.object(self.actions,'_ids',return_value=[CID]),patch.object(self.actions,'_inspect',return_value=[row]):
                with self.assertRaises(c.DeploymentHold):self.actions._runtime(self.context,self.budget)

    def test_smoke_does_not_turn_status200_or_partial_acceptance_into_pass(self):
        self.actions.migrated=True
        with patch.object(self.actions,'_runtime'),patch.object(self.actions,'_compose',side_effect=[
             b'{"environment":"preprod","operation":"check","result":1}',b'{"status":"pass"}']):
            with self.assertRaisesRegex(c.DeploymentHold,'generated_acceptance_incomplete'):
                self.actions.smoke(self.context,self.budget)

    def test_smoke_proves_api_only_restart_freshness_and_ack_anchor(self):
        self.actions.migrated=True;self.actions.pg_id=CID
        acceptance={'status':'pass','scope':'generated_local_api','origin_id':'generated-pp','collector_enabled':False,
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
        with patch.object(self.actions,'_runtime'),patch.object(self.actions,'_compose',side_effect=compose), \
             patch.object(self.actions,'_postgres'),patch.object(self.actions,'_probe',side_effect=[anchor,{**anchor,'prior_acknowledgement_preserved':True}]) as probe:
            result=self.actions.smoke(self.context,self.budget)
        self.assertEqual(result['checks'],dict.fromkeys(c.CHECKS,'PASS'))
        self.assertEqual(result['acceptance_scope'],'generated_only')
        self.assertEqual(probe.call_args_list[-1].args[-1],anchor)
        self.assertIn(['restart','--timeout','10','api'],calls)
        self.assertFalse(any('postgres' in args or 'calculation' in args or 'lifecycle' in args for args in calls))


if __name__=='__main__':unittest.main()
