"""Linux generated-only integration. Never connects to PP/prod or cloud."""
from datetime import datetime,timedelta,timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import tarfile
import time
from unittest.mock import patch
import uuid
import foundation as f

REPO=Path(__file__).resolve().parents[2]
REDACTIONS=[]
DEADLINE=0
PHASE="initialization"
CI_FOUNDATION_SECRETS=Path('/etc/tradebot/pp-postgres')
CI_RUNTIME_SECRETS=Path('/etc/tradebot/pp-runtime')


def claim_ci_directory(path,owned):
    """Only a fresh generated fixture may claim these fixed Linux adapter paths."""
    if path.exists() or path.is_symlink():
        raise RuntimeError('fixed controller fixture path already exists; refusing reuse')
    path.mkdir(mode=0o700)
    info=path.lstat()
    owned.append((path,info.st_dev,info.st_ino))


def cleanup_ci_directories(owned):
    for path,device,inode in reversed(owned):
        info=path.lstat()
        if path.is_symlink() or (info.st_dev,info.st_ino)!=(device,inode) or info.st_uid!=0:
            raise RuntimeError('owned fixture path changed; preserving it for inspection')
        shutil.rmtree(path)


def qualify_controller(root):
    """Real core/Actions with only PP hostname identity substituted on CI Linux."""
    from controller import Budget,Context,Controller,HostBinding,Request,RootAuthorization
    from controller_bundle import build
    from linux_actions import LinuxActions
    source_sha=command(['git','rev-parse','HEAD']).strip()
    if not re.fullmatch('[0-9a-f]{40}',source_sha):raise RuntimeError('full CI source identity required')
    artifact=root/'controller-source.tar.gz'
    command(['git','archive','--format=tar.gz','--output='+str(artifact),source_sha],timeout=30)
    if artifact.stat().st_size>16*1024**2:raise RuntimeError('controller source archive bound exceeded')
    blob=artifact.read_bytes()
    # CI must execute the exact controller/adapter code bound by the source archive.
    with tarfile.open(fileobj=io.BytesIO(blob),mode='r:gz') as archive:
        for name in ('controller.py','linux_actions.py'):
            with archive.extractfile('deploy/preprod/'+name) as source:
                if source.read()!=(f.HERE/name).read_bytes():
                    raise RuntimeError('controller working source differs from exact archive')
    controller_path=root/'controller.pyz'
    packaged=build(controller_path)
    request=Request(source_sha,hashlib.sha256(blob).hexdigest(),packaged['sha256'])
    now=datetime.now(timezone.utc)
    authorization=root/'authorization.json'
    authorization.write_text(json.dumps({**request.bindings(),'version':1,'nonce':str(uuid.uuid4()),
        'issued_at':now.isoformat(),'expires_at':(now+timedelta(minutes=20)).isoformat(),
        'data_mode':'generated','allow_migration':True,'live_collector_enabled':False,
        'paid_ai_enabled':False,'retention_enabled':False,'production_data_mounted':False}))
    authorization.chmod(0o600)
    staging=root/'controller-staging';staging.mkdir(mode=0o700)
    binding=HostBinding('tradebot-preprod-01','preprod','Tradebot',False,False,False)
    actions=LinuxActions()
    remaining=DEADLINE-time.monotonic()
    if remaining<=180:raise RuntimeError('insufficient controller recovery reserve')
    controller=Controller(binding,RootAuthorization(authorization),controller_path,staging,work_seconds=min(600,remaining-180))
    # This is the sole substitution: OS, headroom, root credentials, Docker,
    # mounts, schema, actions, API, source freshness and recovery remain real.
    with patch.object(HostBinding,'from_marker',return_value=binding):
        result=controller.deploy(request,io.BytesIO(blob),actions)
    if result.get('gate')!='PASS' or result.get('acceptance_scope')!='generated_only':
        print(json.dumps({'controller':result,'qualification_scope':'generated_ci_host_identity_substituted'},sort_keys=True),file=sys.stderr)
        raise RuntimeError('real Linux controller generated acceptance failed')
    if authorization.exists() or len(list(root.glob('consumed-*.json')))!=1:
        raise RuntimeError('controller one-use authority consumption not proven')
    replay=controller.deploy(request,io.BytesIO(blob),LinuxActions())
    if replay.get('gate')!='BLOCKED':raise RuntimeError('consumed controller authority accepted twice')
    # Exercise concrete forward-preserving failure recovery as well as the API
    # restart/readback already required by LinuxActions.smoke(). No DB restore.
    candidates=list(staging.glob('candidate-*'))
    if len(candidates)!=1:raise RuntimeError('controller retained staging is ambiguous')
    candidate=candidates[0]
    journal=json.loads((candidate/'controller-journal.json').read_text())
    context=Context(request,candidate/'source',candidate,journal['image'],failed_stage='smoke',migration_started=True)
    remaining=DEADLINE-time.monotonic()
    if remaining<=0:raise RuntimeError('no remaining generated recovery budget')
    recovery=actions.recover(context,Budget(min(180,remaining)))
    if recovery!={'strategy':'stop_candidate_keep_database','database_preserved':True,
                  'new_acknowledgements_preserved':True,'database_restored':False}:
        raise RuntimeError('real Linux forward-preserving recovery incomplete')
    return {'result':result,'qualification_scope':'generated_ci_host_identity_substituted',
            'actual_pp_host_binding':'UNQUALIFIED','controller_bundle_sha256':packaged['sha256'],
            'one_use_replay_rejected':True,'api_restart_persisted_acknowledgement':True,'recovery':recovery}


def command(args,env=None,timeout=120):
    remaining=min(timeout,DEADLINE-time.monotonic())
    if remaining<=0:raise RuntimeError('qualification deadline exceeded')
    process=subprocess.Popen(args,env=env,cwd=REPO,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
    try:
        stdout,stderr=process.communicate(timeout=remaining)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGTERM)
        try:process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);process.communicate()
        raise RuntimeError('qualification child deadline; terminated and reaped') from None
    output=stdout+'\n'+stderr
    for secret in sorted(REDACTIONS,key=len,reverse=True):output=output.replace(secret,'[REDACTED]')
    output=re.sub(r'postgres(?:ql)?://[^\s\x22\x27]+','[REDACTED_DSN]',output)
    print(output[-50000:],file=sys.stderr)
    if process.returncode:raise RuntimeError('generated integration subprocess failed: '+str(process.returncode))
    return stdout


def main():
    global DEADLINE, PHASE
    if os.environ.get('GITHUB_ACTIONS')!='true' or os.geteuid()!=0 or f.MARKER.exists() or f.MARKER.is_symlink():
        raise RuntimeError('only isolated root Linux CI is allowed')
    if any(path.exists() or path.is_symlink() for path in (CI_FOUNDATION_SECRETS,CI_RUNTIME_SECRETS)):
        raise RuntimeError('fixed controller fixture secret paths already exist; refusing any runtime mutation')
    DEADLINE=time.monotonic()+600
    f.DEADLINE=DEADLINE
    started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='tradebot-pg-qualified-') as folder:
        root=Path(folder)
        runtime_env=None
        owned=[]
        foundation_attempted=False
        secret_parent=CI_FOUNDATION_SECRETS.parent
        created_parent=False
        try:
            if secret_parent.is_symlink():raise RuntimeError('unsafe fixed secret parent')
            if not secret_parent.exists():
                secret_parent.mkdir(mode=0o700);created_parent=True
            parent_info=secret_parent.stat()
            if parent_info.st_uid!=0 or parent_info.st_mode & 0o022:raise RuntimeError('unsafe fixed secret parent')
            claim_ci_directory(CI_FOUNDATION_SECRETS,owned)
            claim_ci_directory(CI_RUNTIME_SECRETS,owned)
            PHASE="foundation"
            # Never let generated cleanup adopt an existing named project/volume.
            if (f.run(['docker','ps','-a','--filter','label=com.docker.compose.project=tradebot-pp-foundation','--format','{{.ID}}'])
                    or f.run(['docker','volume','ls','--filter','name=^tradebot_pp_pgdata$','--format','{{.Name}}'])):
                raise RuntimeError('generated CI project or volume already exists; refusing reuse')
            foundation_attempted=True
            f.start(CI_FOUNDATION_SECRETS)
            baseline=f.verify(CI_FOUNDATION_SECRETS)
            PHASE="isolated_role_provisioning"
            cid=f.compose(['ps','-q','postgres'],CI_FOUNDATION_SECRETS)
            info=json.loads(f.run(['docker','inspect','--format','{{json .NetworkSettings.Networks}}',cid]))
            address=next(iter(info.values()))['IPAddress']
            passwords={name:(CI_FOUNDATION_SECRETS/name).read_text().strip() for name in f.ROLES}
            passwords['lifecycle']=secrets.token_hex(32)
            REDACTIONS.extend(passwords.values())
            f.compose(['exec','-T','postgres','sh','-ec','umask 077; cat > /tmp/generated-lifecycle-password; chown postgres:postgres /tmp/generated-lifecycle-password'],CI_FOUNDATION_SECRETS,input=passwords['lifecycle'])
            f.sql("CREATE ROLE tradebot_lifecycle LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION; DO $$ BEGIN EXECUTE format('ALTER ROLE tradebot_lifecycle PASSWORD %L',pg_read_file('/tmp/generated-lifecycle-password')); END $$; GRANT CONNECT ON DATABASE tradebot_pp TO tradebot_lifecycle;",CI_FOUNDATION_SECRETS)
            f.compose(['exec','-T','postgres','rm','/tmp/generated-lifecycle-password'],CI_FOUNDATION_SECRETS)
            dsns={name:'postgresql://'+role+':'+passwords[name]+'@'+address+':5432/tradebot_pp' for name,role in {**f.ROLES,'lifecycle':'tradebot_lifecycle'}.items()}
            REDACTIONS.extend(dsns.values())
            env={**os.environ,'PYTHONPATH':str(REPO/'backend'),'TRADEBOT_ENVIRONMENT':'preprod','TRADEBOT_DATA_MODE':'generated','TRADEBOT_ORIGIN_ID':'generated-ci','TRADEBOT_COLLECTOR_ENABLED':'false'}
            names={'migrator':'TRADEBOT_TEST_MIGRATOR_DSN','application':'TRADEBOT_TEST_APP_DSN','reader':'TRADEBOT_TEST_READER_DSN','lifecycle':'TRADEBOT_TEST_LIFECYCLE_DSN'}
            for name,key in names.items():
                p=root/(name+'-dsn');p.write_text(dsns[name]);p.chmod(0o600)
                env[key]=dsns[name];env[key+'_FILE']=str(p)
            env['TRADEBOT_TEST_DSN']=dsns['application']
            env['TRADEBOT_TEST_DSN_FILE']=env['TRADEBOT_TEST_APP_DSN_FILE']
            # A skipped DB case is not a passing qualification.
            for phase,directory,pattern in [('schema','backend/tests/postgres','test*.py'),('application_lifecycle','backend/tests','test_postgres*.py')]:
                PHASE=phase
                code=("import unittest; s=unittest.defaultTestLoader.discover("+repr(directory)+",pattern="+repr(pattern)+"); r=unittest.TextTestRunner(verbosity=2).run(s); raise SystemExit(0 if r.wasSuccessful() and not r.skipped and r.testsRun else 1)")
                command([sys.executable,'-c',code],env,timeout=180)
            PHASE='runtime_image'
            command(['docker','build','-f','deploy/preprod/Dockerfile','-t','tradebot-pg-test','.'],timeout=200)
            runtime_env={**os.environ,'PP_SECRET_DIR':str(CI_FOUNDATION_SECRETS),'PP_RUNTIME_SECRET_DIR':str(CI_RUNTIME_SECRETS),'PP_APP_IMAGE':'tradebot-pg-test'}
            for name,role in [('app_dsn','application'),('lifecycle_dsn','lifecycle'),('migrator_dsn','migrator')]:
                path=CI_RUNTIME_SECRETS/name;path.write_text(dsns[role].replace('@'+address+':','@postgres:'));path.chmod(0o400);os.chown(path,10001,10001)
            (CI_FOUNDATION_SECRETS/'lifecycle').write_text(passwords['lifecycle']);(CI_FOUNDATION_SECRETS/'lifecycle').chmod(0o400);os.chown(CI_FOUNDATION_SECRETS/'lifecycle',999,999)
            PHASE='ci_only_postgres_secret_mount_recreation'
            runtime(['up','-d','--force-recreate','--wait','--wait-timeout','60','postgres'],runtime_env)
            PHASE='runtime_explicit_migration'
            runtime(['run','--rm','--no-deps','migrate'],runtime_env)
            PHASE='runtime_generated_bootstrap'
            runtime(['run','--rm','--no-deps','lifecycle','python','-m','postgres.lifecycle_worker','--once','--bootstrap'],runtime_env)
            PHASE='runtime_services'
            runtime(['up','-d','--no-deps','--wait','--wait-timeout','40','api','calculation','lifecycle'],runtime_env)
            PHASE='runtime_api_sse_acceptance'
            acceptance=json.loads(runtime(['exec','-T','api','python','-m','postgres.acceptance','--base-url','http://api:8000'],runtime_env))
            if acceptance.get('status')!='pass' or acceptance.get('collector_enabled') is not False:
                raise RuntimeError('runtime acceptance incomplete')
            PHASE='real_linux_controller'
            controller_proof=qualify_controller(root)
            PHASE='resource_accounting'
            sizes=json.loads(f.sql("SELECT json_build_object('database_bytes',pg_database_size(current_database()),'generated_relation_bytes',(SELECT coalesce(sum(pg_total_relation_size(c.oid)),0) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('raw','core','ops','archive') AND c.relkind IN ('r','p')),'wal_bytes',(SELECT sum(size) FROM pg_ls_waldir()));",CI_FOUNDATION_SECRETS))
            if sizes['generated_relation_bytes']>64*1024**2:raise RuntimeError('generated 64 MiB allowance exceeded')
            print(json.dumps({'result':'PASS_GENERATED_POSTGRES_INTEGRATION','elapsed_seconds':round(time.monotonic()-started,3),'baseline':baseline,'sizes':sizes,'runtime':acceptance,'controller':controller_proof,'production_access':False,'cloud_writes':False,'representative_capacity':'NOT_PERFORMED'},sort_keys=True))
        finally:
            f.DEADLINE=time.monotonic()+90
            try:
                if runtime_env:
                    runtime(['down','--volumes','--remove-orphans'],runtime_env,recovery=True)
                elif foundation_attempted:
                    f.compose(['down','--volumes'],CI_FOUNDATION_SECRETS,timeout=90)
            finally:
                cleanup_ci_directories(owned)
                if created_parent:
                    try:secret_parent.rmdir()
                    except OSError:pass

def runtime(args,env,recovery=False):
    cmd=['docker','compose','--env-file','/dev/null','--project-directory',str(f.HERE),'-f',str(f.HERE/'compose.yaml'),'-f',str(f.HERE/'runtime.compose.yaml'),*args]
    if recovery:return f.run(cmd,env=env,timeout=90)
    return command(cmd,env,timeout=90)

if __name__=='__main__':
    try:main()
    except (RuntimeError,subprocess.TimeoutExpired):
        print(json.dumps({'result':'FAIL','phase':PHASE,'scope':'isolated_generated_ci','production_access':False}))
        raise SystemExit('generated PostgreSQL qualification FAIL; see sanitized phase output') from None
