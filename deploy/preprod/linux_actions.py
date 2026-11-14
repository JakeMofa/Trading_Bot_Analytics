"""Concrete generated-only PP Actions; no provisioning, live feeds or cloud calls.

Only stdlib and the bundled controller are imported. Fixed root secrets and an
already-running qualified PostgreSQL foundation are prerequisites. Every child
runs through the controller's bounded Budget. Recovery stops candidate writers
and preserves the database; it never starts an earlier application or restores
a volume. Tests use command doubles; actual Linux execution remains a separate
qualification gate.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import stat
import urllib.parse
import urllib.request
import uuid

from controller import CHECKS, DeploymentHold, HostBinding, require

PROJECT='tradebot-pp-foundation'
PG_VOLUME='tradebot_pp_pgdata'
NETWORK=PROJECT+'_database'
API_NETWORK=PROJECT+'_api_loopback'
SECRETS=Path('/etc/tradebot/pp-postgres')
RUNTIME_SECRETS=Path('/etc/tradebot/pp-runtime')
PG_IMAGE='postgres:17.12-bookworm@sha256:40865bc877a289da75963d97d72b59633f639fc5af7a4e856bfa3714cae5b536'
PYTHON_IMAGE='python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df'
SERVICES=('api','calculation','lifecycle')
MEMORY={'postgres':512,'api':192,'calculation':192,'lifecycle':128,'migrate':192}
CPUS={'postgres':1.0,'api':0.5,'calculation':0.5,'lifecycle':0.25}
PG_ENV={'POSTGRES_DB':'tradebot_pp','POSTGRES_USER':'postgres','POSTGRES_PASSWORD_FILE':'/run/secrets/admin',
        'POSTGRES_INITDB_ARGS':'--auth-host=scram-sha-256 --data-checksums'}
PG_COMMAND=['postgres',*sum((['-c',value] for value in (
    'shared_buffers=128MB','max_connections=20','work_mem=2MB','maintenance_work_mem=32MB','temp_file_limit=64MB',
    'statement_timeout=15s','lock_timeout=2s','idle_in_transaction_session_timeout=15s','fsync=on',
    'synchronous_commit=on','full_page_writes=on','autovacuum=on','max_wal_size=256MB','min_wal_size=80MB')),[])]
PG_SECRET_MAPPINGS={name:name for name in ('admin','migrator','application','reader')}
PG_SECRET_MAPPINGS['lifecycle_password']='lifecycle'
ATTEMPT_LABEL='tradebot.deployment_attempt'
SOURCE_LABEL='tradebot.deployment_source'
COMMANDS={'api':['python','-m','uvicorn','postgres.api:app','--host','0.0.0.0','--port','8000'],
          'calculation':['python','-m','postgres.worker'],
          'lifecycle':['python','-m','postgres.lifecycle_worker'],
          'migrate':['python','-m','postgres.migrate','--environment','preprod','--dsn-file','/run/secrets/migrator_dsn']}
ROLE_SECRET={'api':'app_dsn','calculation':'app_dsn','lifecycle':'lifecycle_dsn','migrate':'migrator_dsn'}
BASE_ENV={'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':'/app/backend','TRADEBOT_ENVIRONMENT':'preprod',
          'TRADEBOT_DATA_MODE':'generated','TRADEBOT_ORIGIN_ID':'generated-pp','TRADEBOT_COLLECTOR_ENABLED':'false',
          'ENABLE_OPENAI_ANALYST':'false','ENABLE_SUPABASE_SYNC':'false','ENABLE_LOCAL_RETENTION':'false'}
OPTIONAL_DISABLED={'TRADEBOT_CLOUD_ENABLED','TRADEBOT_RETIREMENT_ENABLED'}


def memory_bytes(value):
    if isinstance(value,int):return value
    match=re.fullmatch(r'(\d+)([kmg]?)b?',str(value).lower())
    require(match is not None,'invalid_memory_limit')
    return int(match[1])*{'':1,'k':1024,'m':1024**2,'g':1024**3}[match[2]]


def expected_environment(service):
    return {**BASE_ENV,'TRADEBOT_DATABASE_DSN_FILE':'/run/secrets/'+ROLE_SECRET[service]}


def reviewed_secret_mapping(mapping,source,target):
    """Compose may expand short syntax to its exact /run/secrets destination.

    Accept only the two equivalent literal spellings. Do not normalize arbitrary
    paths or accept uid/gid/mode overrides: file ownership and 0400 permissions
    are checked independently on the fixed root-provisioned secret files.
    """
    return (isinstance(mapping,dict) and set(mapping)=={'source','target'}
            and mapping['source']==source and mapping['target'] in (target,'/run/secrets/'+target))


def validate_config(config,source,image):
    """Validate normalized Compose, including hostile overrides in approved source."""
    require(config.get('name')==PROJECT and set(config.get('services',{}))==set(MEMORY),'unexpected_compose_project_or_services')
    require(set(config.get('networks',{}))=={'database','api_loopback'} and config['networks']['database'].get('internal') is True
            and config['networks']['database'].get('name')==NETWORK and not config['networks']['database'].get('external')
            and config['networks']['database'].get('driver','bridge')=='bridge','unsafe_database_network')
    frontend=config['networks']['api_loopback']
    require(frontend.get('name')==API_NETWORK and frontend.get('driver','bridge')=='bridge'
            and frontend.get('internal',False) is False and not frontend.get('external')
            and frontend.get('driver_opts')=={'com.docker.network.bridge.host_binding_ipv4':'127.0.0.1'},
            'unsafe_api_loopback_network')
    require(set(config.get('volumes',{}))=={'pp_pgdata'} and config['volumes']['pp_pgdata'].get('name')==PG_VOLUME
            and config['volumes']['pp_pgdata'].get('external',False) is False
            and config['volumes']['pp_pgdata'].get('driver','local')=='local'
            and not config['volumes']['pp_pgdata'].get('driver_opts'),'unsafe_database_volume')
    expected_secrets={name:str(SECRETS/name) for name in ('admin','migrator','application','reader')}
    expected_secrets.update(lifecycle_password=str(SECRETS/'lifecycle'))
    expected_secrets.update({name:str(RUNTIME_SECRETS/name) for name in ROLE_SECRET.values()})
    require(set(config.get('secrets',{}))==set(expected_secrets),'unexpected_secret')
    require(all(config['secrets'][name].get('file')==path and not config['secrets'][name].get('external')
                for name,path in expected_secrets.items()),'unsafe_secret_path')
    for name,service in config['services'].items():
        require(service.get('image')==(PG_IMAGE if name=='postgres' else image),'unbound_service_image')
        require(memory_bytes(service.get('mem_limit'))==MEMORY[name]*1024**2
                and memory_bytes(service.get('memswap_limit'))==MEMORY[name]*1024**2,'resource_limit_mismatch')
        if name in CPUS:require(float(service.get('cpus',0))==CPUS[name],'cpu_limit_mismatch')
        require(service.get('privileged',False) is False and not service.get('devices') and not service.get('cap_add')
                and not service.get('pid') and not service.get('ipc') and not service.get('network_mode')
                and not service.get('extra_hosts') and not service.get('entrypoint') and not service.get('build')
                and not service.get('configs') and not service.get('runtime')
                and not service.get('use_api_socket') and not service.get('post_start') and not service.get('pre_stop')
                and not service.get('volumes_from'), 'unsafe_service_override')
        require(set(service.get('networks',{}))==({'database','api_loopback'} if name=='api' else {'database'}),
                'unexpected_service_network')
        log=service.get('logging',{})
        require(log.get('driver')=='json-file' and log.get('options')=={'max-size':'5m','max-file':'2'},'unbounded_container_logs')
        require('no-new-privileges:true' in service.get('security_opt',[]),'missing_security_option')
        ports=service.get('ports',[])
        if name=='api':
            require(len(ports)==1 and ports[0].get('host_ip')=='127.0.0.1' and int(ports[0].get('target',0))==8000
                    and str(ports[0].get('published'))=='8000' and ports[0].get('protocol','tcp')=='tcp','unsafe_api_port')
        else:require(not ports,'unexpected_published_port')
        if name=='postgres':
            require(service.get('environment',{})==PG_ENV,'wrong_postgres_environment')
            require(service.get('command')==PG_COMMAND,'unreviewed_postgres_command')
            mappings=service.get('secrets',[])
            require(len(mappings)==len(PG_SECRET_MAPPINGS)
                    and all(isinstance(item,dict) and item.get('source') in PG_SECRET_MAPPINGS for item in mappings)
                    and {item['source'] for item in mappings}==set(PG_SECRET_MAPPINGS)
                    and all(reviewed_secret_mapping(item,item['source'],PG_SECRET_MAPPINGS[item['source']]) for item in mappings),
                    'unexpected_postgres_secret_mapping')
            mounts=service.get('volumes',[])
            require(len(mounts)==2,'unexpected_postgres_mount')
            data=next((m for m in mounts if m.get('target')=='/var/lib/postgresql/data'),{})
            init=next((m for m in mounts if m.get('target')=='/docker-entrypoint-initdb.d/10-foundation.sh'),{})
            require(data.get('type')=='volume' and data.get('source')=='pp_pgdata'
                    and init.get('type')=='bind' and init.get('read_only') is True
                    and init.get('source')==str(source/'deploy/preprod/init.sh'),'unsafe_postgres_mount')
        else:
            require(service.get('command')==COMMANDS[name] and service.get('user')=='10001:10001'
                    and service.get('read_only') is True and service.get('cap_drop')==['ALL']
                    and service.get('pids_limit')==64 and not service.get('volumes'),'unsafe_application_runtime')
            require(service.get('pull_policy')=='never','runtime_pull_not_allowed')
            tmpfs=service.get('tmpfs',[])
            require(len(tmpfs)==1 and tmpfs[0].startswith('/tmp:') and 'mode=1777' in tmpfs[0]
                    and re.search(r'(?:^|,)size=(?:16m|16777216)(?:,|$)',tmpfs[0].split(':',1)[1]),'unbounded_application_tmpfs')
            require(service.get('restart')==('no' if name=='migrate' else 'unless-stopped'),'unexpected_restart_policy')
            env=service.get('environment',{})
            require(all(env.get(key)==value for key,value in expected_environment(name).items()),'unsafe_application_environment')
            require(set(env)<=set(expected_environment(name))|OPTIONAL_DISABLED
                    and all(env.get(key,'false')=='false' for key in OPTIONAL_DISABLED),'unexpected_application_environment')
            secrets=service.get('secrets',[])
            require(len(secrets)==1 and reviewed_secret_mapping(secrets[0],ROLE_SECRET[name],ROLE_SECRET[name]),
                    'unexpected_application_secret')
    return config


PROBE=r'''
import json,os,sys
from datetime import datetime,timezone
import urllib.request
from postgres.config import Settings
from postgres.domain import timestamp
from postgres.store import Store
import time
expected=json.load(sys.stdin)
def check():
    with urllib.request.urlopen('http://127.0.0.1:8000/state/current',timeout=2) as response:
        raw=response.read(65537)
    assert len(raw)<=65536
    state=json.loads(raw)
    now=datetime.now(timezone.utc)
    market=state['market']; feature=state['feature_snapshot']; price=state['coinbase']; quote=state['polymarket']
    assert state['environment']=='preprod' and state['data_mode']=='generated' and state['origin_id']=='generated-pp'
    assert state['collector']['enabled'] is False and state['collector']['running'] is False
    assert timestamp(market['start'])<=now<timestamp(market['end'])
    assert feature['market_id']==market['id'] and quote['market_id']==market['id']
    assert 0<market['seconds_remaining']<=900
    for instant in (price['source_time'],quote['source_time'],feature['as_of']):
        assert 0<=(now-timestamp(instant)).total_seconds()<=30
    assert feature['quality']['price']['input_id']==price['event_id']
    assert state['feeds']['coinbase_stream']['status']=='fresh' and state['feeds']['polymarket_stream']['status']=='fresh'
    store=Store(Settings.from_env());store.verify()
    with store.connection(True) as db:
        assert db.execute('SELECT count(*) AS n FROM ops.writer_state WHERE collector_enabled').fetchone()['n']==0
        row=db.execute("SELECT event_id,price,content_hash FROM core.current_prices WHERE origin_id=%s AND source='coinbase' AND symbol='BTC-USD'",('generated-pp',)).fetchone()
        assert row['event_id']==price['event_id'] and str(row['price'])==price['price_usd']
        prediction=db.execute('SELECT prediction_id,content_hash FROM core.predictions WHERE origin_id=%s AND snapshot_id=%s',('generated-pp',feature['snapshot_id'])).fetchone()
        assert prediction is not None
        if expected:
            prior=db.execute('SELECT content_hash FROM core.predictions WHERE origin_id=%s AND prediction_id=%s',('generated-pp',expected['prediction_id'])).fetchone()
            assert prior and prior['content_hash']==expected['prediction_hash']
            assert row['event_id']==expected['price_event_id'] and row['content_hash']==expected['price_hash']
    return {'fresh':True,'market_identity':True,'collector_disabled':True,'schema_verified':True,
     'prediction_id':prediction['prediction_id'],'prediction_hash':prediction['content_hash'],
     'price_event_id':row['event_id'],'price_hash':row['content_hash'],'prior_acknowledgement_preserved':bool(expected)}
deadline=time.monotonic()+8
while True:
    try:
        print(json.dumps(check()))
        break
    except (AssertionError,KeyError,TypeError):
        if time.monotonic()>=deadline:raise
        time.sleep(.2)
'''


class LinuxActions:
    def __init__(self):
        self.config=None
        self.pg_id=None
        self.pg_volume=None
        self.migrated=False
        self.anchor=None
        self.before_migration=None
        self.attempt_id=uuid.uuid4().hex
        self.oneoffs={}
        self.oneoff_sequence=0

    @staticmethod
    def _environment(image):
        return {'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C.UTF-8','DOCKER_HOST':'unix:///var/run/docker.sock',
                'PP_SECRET_DIR':str(SECRETS),'PP_RUNTIME_SECRET_DIR':str(RUNTIME_SECRETS),'PP_APP_IMAGE':image}

    def _compose(self,context,budget,args,*,timeout=90,input=None,image=None):
        selected=image or context.image or 'sha256:'+'0'*64
        folder=context.source/'deploy/preprod'
        # Compose v5 omits inactive profile services from rendered config. Inspect
        # the explicit migration service too, without enabling it for normal up.
        profiles=['--profile','migration'] if args and args[0]=='config' else []
        return budget.run(['docker','compose','--env-file','/dev/null','--project-name',PROJECT,
            '--project-directory',str(folder),'-f',str(folder/'compose.yaml'),'-f',str(folder/'runtime.compose.yaml'),*profiles,*args],
            cwd=context.source,env=self._environment(selected),timeout=timeout,input=input)

    def _json(self,raw):
        try:return json.loads(raw)
        except (ValueError,UnicodeError):raise DeploymentHold('invalid_runtime_evidence') from None

    def _ids(self,context,budget,services,all=False):
        args=['ps']+(['-a'] if all else [])+['-q',*services]
        result=self._compose(context,budget,args).decode().split()
        require(all_id(result),'invalid_container_identity')
        return result

    def _inspect(self,budget,ids):
        require(ids and all_id(ids),'invalid_container_identity')
        result=self._json(budget.run(['docker','inspect',*ids],env=self._environment('unused'),timeout=15))
        require(isinstance(result,list) and len(result)==len(ids),'missing_container_inspection')
        return result

    def _owned_oneoff(self,context,budget,name,service):
        """Read only exact-attempt containers; never adopt another deployment."""
        output=budget.run(['docker','ps','-a','--no-trunc','--filter','label=com.docker.compose.project='+PROJECT,
            '--filter','label='+ATTEMPT_LABEL+'='+self.attempt_id,'--filter','name='+name,'--format','{{.ID}}'],
            env=self._environment(context.image or 'unused'),timeout=10).decode().split()
        require(all_id(output) and len(output)<=1,'ambiguous_deployment_oneoff')
        if not output:return []
        rows=self._inspect(budget,output)
        for row in rows:
            labels=row.get('Config',{}).get('Labels',{})
            require(row.get('Name')=='/'+name and labels.get('com.docker.compose.project')==PROJECT
                    and labels.get('com.docker.compose.service')==service
                    and labels.get(ATTEMPT_LABEL)==self.attempt_id and labels.get(SOURCE_LABEL)==context.request.source_sha,
                    'oneoff_ownership_mismatch')
            require(row.get('HostConfig',{}).get('RestartPolicy',{}).get('Name') in ('no',''),
                    'oneoff_restart_not_fenced')
        return rows

    def _cleanup_oneoffs(self,context,budget):
        for name,service in list(self.oneoffs.items()):
            rows=self._owned_oneoff(context,budget,name,service)
            if rows and rows[0]['State'].get('Running'):
                try:
                    budget.run(['docker','stop','--time','5',rows[0]['Id']],
                               env=self._environment(context.image or 'unused'),timeout=10)
                except DeploymentHold:
                    pass  # CLI timeout is not proof of container exit; inspect again.
                rows=self._owned_oneoff(context,budget,name,service)
                if rows and rows[0]['State'].get('Running'):
                    try:
                        budget.run(['docker','kill',rows[0]['Id']],env=self._environment(context.image or 'unused'),timeout=10)
                    except DeploymentHold:
                        pass
                    rows=self._owned_oneoff(context,budget,name,service)
            require(not rows or not rows[0]['State'].get('Running'),'deployment_oneoff_still_running')
            if rows:
                try:
                    budget.run(['docker','rm',rows[0]['Id']],env=self._environment(context.image or 'unused'),timeout=10)
                except DeploymentHold:
                    pass  # --rm may already have removed the stopped container.
            require(not self._owned_oneoff(context,budget,name,service),'deployment_oneoff_not_removed')
            del self.oneoffs[name]

    def _oneoff(self,context,budget,service,args=(),timeout=90):
        require(service in ('migrate','lifecycle'),'unsupported_deployment_oneoff')
        self.oneoff_sequence+=1
        name='tradebot-pp-deploy-'+self.attempt_id+'-'+str(self.oneoff_sequence)
        self.oneoffs[name]=service  # Record before daemon-side creation can occur.
        output=self._compose(context,budget,['run','--rm','--no-deps','--name',name,
            '--label',ATTEMPT_LABEL+'='+self.attempt_id,'--label',SOURCE_LABEL+'='+context.request.source_sha,
            service,*args],timeout=timeout)
        # On timeout the exception leaves ownership registered for fresh recovery
        # budget. Success also requires daemon-side exit/removal, not CLI exit alone.
        self._cleanup_oneoffs(context,budget)
        return output

    def _sql(self,budget,query):
        require(self.pg_id is not None,'postgres_identity_not_verified')
        script='export PGPASSWORD="$(cat /run/secrets/application)"; exec psql -X -qAt --set ON_ERROR_STOP=1 -h 127.0.0.1 -U tradebot_app -d tradebot_pp'
        return budget.run(['docker','exec','-i',self.pg_id,'sh','-ec',script],input=('BEGIN READ ONLY; '+query+'; COMMIT;').encode(),
                          env=self._environment('unused'),timeout=20).decode().strip()

    @staticmethod
    def _host():
        HostBinding.from_marker().validate()
        release=dict(line.split('=',1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
        require(release.get('ID','').strip('"')=='ubuntu' and release.get('VERSION_ID','').strip('"')=='24.04','unqualified_host_os')
        memory=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
        require(shutil.disk_usage('/').free>=10*1024**3 and int(memory['MemAvailable'].split()[0])*1024>=1024**3,
                'insufficient_host_headroom')
        for directory in (SECRETS,RUNTIME_SECRETS):
            info=directory.lstat()
            require(stat.S_ISDIR(info.st_mode) and info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o700,'unsafe_secret_directory')
        for name in ('admin','migrator','application','reader','lifecycle'):
            path=SECRETS/name;info=path.lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_uid==999 and stat.S_IMODE(info.st_mode)==0o400,'unprepared_foundation_secret')
        for name,role in [('app_dsn','tradebot_app'),('lifecycle_dsn','tradebot_lifecycle'),('migrator_dsn','tradebot_migrator')]:
            path=RUNTIME_SECRETS/name;info=path.lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_uid==10001 and stat.S_IMODE(info.st_mode)==0o400 and info.st_size<4096,
                    'unprepared_runtime_secret')
            parsed=urllib.parse.urlsplit(path.read_text().strip())
            require(parsed.scheme=='postgresql' and parsed.hostname=='postgres' and parsed.port==5432
                    and parsed.path=='/tradebot_pp' and parsed.username==role and not parsed.query and not parsed.fragment
                    and bool(re.fullmatch('[0-9a-f]{64}',urllib.parse.unquote(parsed.password or ''))),'runtime_secret_binding_mismatch')

    def _postgres(self,context,budget):
        ids=self._ids(context,budget,['postgres'])
        require(len(ids)==1,'existing_postgres_required')
        row=self._inspect(budget,ids)[0]
        require(row['State'].get('Running') is True and row['State'].get('OOMKilled') is False
                and row['Config'].get('Image')==PG_IMAGE and not row['HostConfig'].get('PortBindings'), 'unsafe_postgres_runtime')
        require(row['HostConfig'].get('Memory')==512*1024**2 and row['HostConfig'].get('MemorySwap')==512*1024**2,'postgres_resource_mismatch')
        require(row['Config'].get('Labels',{}).get('com.docker.compose.project')==PROJECT,'wrong_postgres_project')
        require(set(row['NetworkSettings']['Networks'])=={NETWORK},'wrong_postgres_network')
        volumes=[mount for mount in row['Mounts'] if mount['Destination']=='/var/lib/postgresql/data']
        require(len(volumes)==1 and volumes[0].get('Type')=='volume' and volumes[0].get('Name')==PG_VOLUME,'wrong_postgres_volume')
        allowed={'/var/lib/postgresql/data','/docker-entrypoint-initdb.d/10-foundation.sh'}|{'/run/secrets/'+name for name in ('admin','migrator','application','reader','lifecycle')}
        require({mount['Destination'] for mount in row['Mounts']}==allowed,'unprepared_or_unexpected_postgres_mount')
        for mount in row['Mounts']:
            if mount['Destination'].startswith('/run/secrets/'):
                require(mount.get('Source')==str(SECRETS/Path(mount['Destination']).name) and mount.get('RW') is False,'unsafe_postgres_secret_mount')
        network=self._json(budget.run(['docker','network','inspect',NETWORK],timeout=10,env=self._environment('unused')))
        require(len(network)==1 and network[0].get('Internal') is True,'database_network_not_internal')
        self.pg_id=ids[0]
        volume=volumes[0]['Name']
        if self.pg_volume is not None:require(volume==self.pg_volume,'database_volume_changed')
        self.pg_volume=volume
        identity=self._json(self._sql(budget,"SELECT json_build_object('database',current_database(),'environment',(SELECT environment FROM ops.environment_identity),'foundation_version',(SELECT foundation_version FROM ops.environment_identity),'version',current_setting('server_version'),'fsync',current_setting('fsync'),'synchronous_commit',current_setting('synchronous_commit'),'full_page_writes',current_setting('full_page_writes'),'autovacuum',current_setting('autovacuum'),'data_checksums',current_setting('data_checksums'))"))
        require(identity.get('database')=='tradebot_pp' and identity.get('environment')=='preprod' and identity.get('foundation_version')==1
                and identity.get('version','').startswith('17.12 '),'postgres_identity_mismatch')
        require(all(identity.get(key)=='on' for key in ('fsync','synchronous_commit','full_page_writes','autovacuum','data_checksums')),'postgres_durability_disabled')

    def preflight(self,context,budget):
        self._host()
        dockerfile=(context.source/'deploy/preprod/Dockerfile').read_text()
        require(re.findall(r'^FROM (.+)$',dockerfile,re.M)==[PYTHON_IMAGE],'unqualified_python_base')
        self.config=validate_config(self._json(self._compose(context,budget,['config','--format','json'])),context.source,'sha256:'+'0'*64)
        self._postgres(context,budget)
        pending=budget.run(['docker','ps','-a','--filter','label=com.docker.compose.project='+PROJECT,
            '--filter','label=com.docker.compose.oneoff=True','--format','{{.ID}}'],
            env=self._environment('unused'),timeout=10).strip()
        require(not pending,'prior_oneoff_requires_operator_inspection')

    def build(self,context,budget):
        require(self.config is not None,'preflight_required')
        destination=context.staging/'image-id'
        budget.run(['docker','build','--quiet','--iidfile',str(destination),'--label','tradebot.source_sha='+context.request.source_sha,
                    '-f',str(context.source/'deploy/preprod/Dockerfile'),str(context.source)],
                   env=self._environment('unused'),timeout=240)
        image=destination.read_text().strip()
        require(bool(re.fullmatch('sha256:[0-9a-f]{64}',image)),'invalid_built_image_id')
        info=self._json(budget.run(['docker','image','inspect',image],env=self._environment(image),timeout=10))
        require(len(info)==1 and info[0].get('Id')==image and info[0]['Config'].get('User')=='10001:10001'
                and info[0]['Config'].get('Labels',{}).get('tradebot.source_sha')==context.request.source_sha,'built_image_binding_mismatch')
        validate_config(self._json(self._compose(context,budget,['config','--format','json'],image=image)),context.source,image)
        return image

    def _fence(self,context,budget):
        ids=self._ids(context,budget,SERVICES,all=True)
        if ids:
            # Compose ps may include run/one-off containers for a service. Those
            # are handled only by exact-attempt cleanup, never a service-wide fence.
            prior=self._inspect(budget,ids)
            require(all(row.get('Config',{}).get('Labels',{}).get('com.docker.compose.project')==PROJECT
                        and row['Config']['Labels'].get('com.docker.compose.service') in SERVICES
                        and row['Config']['Labels'].get('com.docker.compose.oneoff','False')=='False'
                        for row in prior),'unowned_container_blocks_runtime_fence')
            budget.run(['docker','update','--restart=no',*ids],env=self._environment(context.image or 'unused'),timeout=20)
            self._compose(context,budget,['stop','--timeout','20',*SERVICES],timeout=30)
            require(all(not row['State'].get('Running') and row['HostConfig']['RestartPolicy']['Name']=='no'
                        for row in self._inspect(budget,ids)),'candidate_writer_fence_failed')

    def _inventory(self,budget):
        # Bounded generated-only evidence, not a production-scale checksum claim.
        result={}
        identities={'core.markets':'origin_id,market_id,content_hash','core.candles':'origin_id,source,symbol,granularity,time,content_hash',
                    'core.current_prices':'origin_id,source,symbol,content_hash','core.protected_evidence':'origin_id,evidence_id,content_hash',
                    'core.feature_snapshots':'origin_id,snapshot_id,content_hash','core.predictions':'origin_id,prediction_id,content_hash',
                    'core.outcomes':'origin_id,outcome_id,content_hash','raw.events':'generation_id,origin_id,source,event_id,content_hash',
                    'core.snapshot_evidence':'origin_id,snapshot_id,evidence_id',
                    'ops.outbox':'id,origin_id,entity_type,entity_id,content_hash'}
        for table,identity in identities.items():
            exists=self._sql(budget,"SELECT to_regclass('"+table+"') IS NOT NULL")
            if exists=='f':result[table]=None;continue
            require(exists=='t','invalid_inventory_evidence')
            row=self._json(self._sql(budget,"SELECT json_build_object('count',count(*),'digest',md5(coalesce(string_agg(fingerprint,',' ORDER BY fingerprint),''))) FROM (SELECT jsonb_build_array("+identity+")::text AS fingerprint FROM "+table+" LIMIT 10001) bounded"))
            require(0<=row.get('count',10001)<=10000 and bool(re.fullmatch('[0-9a-f]{32}',row.get('digest',''))),'inventory_exceeds_generated_bound')
            result[table]=row
        return result

    def migrate(self,context,budget):
        self._fence(context,budget)
        self.before_migration=self._inventory(budget)
        evidence=self._json(self._oneoff(context,budget,'migrate',timeout=90))
        require(evidence.get('environment')=='preprod' and evidence.get('operation')=='migrate'
                and isinstance(evidence.get('result'),list),'explicit_migration_not_proven')
        after=self._inventory(budget)
        require(all(value is None or after.get(table)==value for table,value in self.before_migration.items()),'migration_changed_existing_evidence')
        self.migrated=True

    def start(self,context,budget):
        require(self.migrated,'explicit_migration_required')
        evidence=self._json(self._oneoff(context,budget,'lifecycle',['python','-m','postgres.lifecycle_worker','--once','--bootstrap']))
        require(evidence.get('retirement')=='off' and evidence.get('archive')=='held_no_qualified_transport','generated_bootstrap_not_proven')
        self._compose(context,budget,['up','-d','--no-deps','--force-recreate','--wait','--wait-timeout','40',*SERVICES],timeout=60)

    def _runtime(self,context,budget):
        for service in SERVICES:
            ids=self._ids(context,budget,[service])
            require(len(ids)==1,'missing_runtime_service')
            row=self._inspect(budget,ids)[0]
            host=row['HostConfig']; config=row['Config']
            require(row['State'].get('Running') is True and row['State'].get('OOMKilled') is False and row.get('Image')==context.image,
                    'runtime_image_or_process_mismatch')
            require(config.get('Cmd')==COMMANDS[service] and config.get('User')=='10001:10001'
                    and config.get('Labels',{}).get('com.docker.compose.project')==PROJECT,'runtime_command_or_project_mismatch')
            require(host.get('Memory')==MEMORY[service]*1024**2 and host.get('MemorySwap')==MEMORY[service]*1024**2
                    and host.get('PidsLimit')==64 and host.get('ReadonlyRootfs') is True and host.get('Privileged') is False
                    and host.get('CapDrop')==['ALL'] and host.get('NanoCpus')==int(CPUS[service]*1_000_000_000)
                    and host.get('RestartPolicy',{}).get('Name')=='unless-stopped','runtime_resource_or_privilege_mismatch')
            env=dict(item.split('=',1) for item in config.get('Env',[]) if '=' in item)
            require(all(env.get(key)==value for key,value in expected_environment(service).items())
                    and all(env.get(key,'false')=='false' for key in OPTIONAL_DISABLED)
                    and not env.get('TRADEBOT_DATABASE_DSN'),'runtime_flag_mismatch')
            network_settings=row['NetworkSettings']
            require(set(network_settings['Networks'])==({NETWORK,API_NETWORK} if service=='api' else {NETWORK}),
                    'runtime_network_mismatch')
            mounts=row.get('Mounts',[])
            secret=[item for item in mounts if item.get('Destination')=='/run/secrets/'+ROLE_SECRET[service]]
            require(len(secret)==1 and secret[0].get('Source')==str(RUNTIME_SECRETS/ROLE_SECRET[service])
                    and secret[0].get('RW') is False and all(item.get('Destination') in ('/tmp','/run/secrets/'+ROLE_SECRET[service])
                        for item in mounts),'runtime_unexpected_data_mount')
            ports=host.get('PortBindings') or {}
            require(ports==({'8000/tcp':[{'HostIp':'127.0.0.1','HostPort':'8000'}]} if service=='api' else {}),'runtime_public_port')
            if service=='api':
                require(network_settings.get('Ports',{}).get('8000/tcp')==ports['8000/tcp'],
                        'api_loopback_port_not_published')
                require(row['State'].get('Health',{}).get('Status')=='healthy','api_not_healthy')

    @staticmethod
    def _host_api():
        """Test the real host listener; container-local HTTP is insufficient."""
        try:
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open('http://127.0.0.1:8000/state/current',timeout=2) as response:
                raw=response.read(65537)
            require(len(raw)<=65536,'host_api_response_too_large')
            state=json.loads(raw)
            require(state.get('environment')=='preprod' and state.get('data_mode')=='generated'
                    and state.get('collector',{}).get('enabled') is False,'host_api_wrong_state')
        except (OSError,ValueError,KeyError) as error:
            raise DeploymentHold('host_api_loopback_unavailable') from None

    def _probe(self,context,budget,expected=None):
        return self._json(self._compose(context,budget,['exec','-T','api','python','-c',PROBE],input=json.dumps(expected or {}).encode(),timeout=20))

    def smoke(self,context,budget):
        require(self.migrated,'explicit_migration_required')
        schema=self._json(self._oneoff(context,budget,'migrate',['python','-m','postgres.migrate',
            '--environment','preprod','--dsn-file','/run/secrets/migrator_dsn','--check']))
        require(schema.get('environment')=='preprod' and schema.get('operation')=='check' and isinstance(schema.get('result'),int)
                and schema['result']>0,'schema_check_not_proven')
        self._runtime(context,budget)
        self._host_api()
        accepted=self._json(self._compose(context,budget,['exec','-T','api','python','-m','postgres.acceptance','--base-url','http://api:8000'],timeout=45))
        require(accepted.get('status')=='pass' and accepted.get('scope')=='generated_local_api'
                and accepted.get('origin_id')=='generated-pp' and accepted.get('collector_enabled') is False
                and accepted.get('sse_connections')==2 and accepted.get('acknowledged_events',0)>=20
                and 0<=accepted.get('api_max_seconds',999)<2
                and all(accepted.get(key) is True for key in ('conflict_detected','exact_decimal_roundtrip','api_ram_after_commit',
                    'dashboard_contract','bounded_chart','prediction_history')),'generated_acceptance_incomplete')
        self.anchor=self._probe(context,budget)
        require(all(self.anchor.get(key) is True for key in ('fresh','market_identity','collector_disabled','schema_verified')),'freshness_or_market_not_proven')
        pg_before=self.pg_id
        self._compose(context,budget,['restart','--timeout','10','api'],timeout=20)
        # Health waits only for API; worker and database are not recreated or restored.
        self._compose(context,budget,['up','-d','--no-deps','--wait','--wait-timeout','15','api'],timeout=20)
        after=self._probe(context,budget,self.anchor)
        require(after.get('prior_acknowledgement_preserved') is True and all(after.get(key) is True for key in
                ('fresh','market_identity','collector_disabled','schema_verified')),'restart_persistence_not_proven')
        self._postgres(context,budget)
        require(self.pg_id==pg_before,'postgres_restarted_during_api_recovery')
        self._runtime(context,budget)
        self._host_api()
        return {'checks':dict.fromkeys(CHECKS,'PASS'),'acceptance_scope':'generated_only','live_collector_enabled':False,
                'paid_ai_enabled':False,'retention_enabled':False,'production_data_mounted':False}

    def recover(self,context,budget):
        if not context.migration_started:
            require(not self.oneoffs,'unexpected_pre_migration_oneoff')
            return {'strategy':'prior_runtime_unchanged','database_preserved':True,
                    'new_acknowledgements_preserved':True,'database_restored':False}
        self._cleanup_oneoffs(context,budget)
        self._fence(context,budget)
        self._postgres(context,budget)
        before=self._inventory(budget)
        if context.failed_stage=='migrate' and self.before_migration is not None:
            require(all(value is None or before.get(table)==value for table,value in self.before_migration.items()),
                    'migration_recovery_evidence_changed')
        if self.anchor:
            identity=self.anchor.get('prediction_id','');digest=self.anchor.get('prediction_hash','')
            require(bool(re.fullmatch('[0-9a-f]{64}',identity)) and bool(re.fullmatch('[0-9a-f]{64}',digest)),'invalid_recovery_anchor')
            actual=self._sql(budget,"SELECT content_hash FROM core.predictions WHERE origin_id='generated-pp' AND prediction_id='"+identity+"'")
            require(actual==digest,'acknowledged_prediction_not_preserved')
        require(self._inventory(budget)==before,'database_changed_after_writer_fence')
        return {'strategy':'stop_candidate_keep_database','database_preserved':True,
                'new_acknowledgements_preserved':True,'database_restored':False}


def all_id(values):
    return all(isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) for value in values)
