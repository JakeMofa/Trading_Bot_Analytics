"""Linux generated-only integration. Never connects to PP/prod or cloud."""
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import time
import foundation as f

REPO=Path(__file__).resolve().parents[2]
REDACTIONS=[]
DEADLINE=0
PHASE="initialization"


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
    if os.environ.get('GITHUB_ACTIONS')!='true' or os.geteuid()!=0 or f.MARKER.exists():
        raise RuntimeError('only isolated root Linux CI is allowed')
    DEADLINE=time.monotonic()+600
    f.DEADLINE=DEADLINE
    started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='tradebot-pg-qualified-') as folder:
        root=Path(folder)
        runtime_env=None
        try:
            PHASE="foundation"
            f.start(root)
            baseline=f.verify(root)
            PHASE="isolated_role_provisioning"
            cid=f.compose(['ps','-q','postgres'],root)
            info=json.loads(f.run(['docker','inspect','--format','{{json .NetworkSettings.Networks}}',cid]))
            address=next(iter(info.values()))['IPAddress']
            passwords={name:(root/name).read_text().strip() for name in f.ROLES}
            passwords['lifecycle']=secrets.token_hex(32)
            REDACTIONS.extend(passwords.values())
            f.compose(['exec','-T','postgres','sh','-ec','umask 077; cat > /tmp/generated-lifecycle-password; chown postgres:postgres /tmp/generated-lifecycle-password'],root,input=passwords['lifecycle'])
            f.sql("CREATE ROLE tradebot_lifecycle LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION; DO $$ BEGIN EXECUTE format('ALTER ROLE tradebot_lifecycle PASSWORD %L',pg_read_file('/tmp/generated-lifecycle-password')); END $$; GRANT CONNECT ON DATABASE tradebot_pp TO tradebot_lifecycle;",root)
            f.compose(['exec','-T','postgres','rm','/tmp/generated-lifecycle-password'],root)
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
            runtime_env={**os.environ,'PP_SECRET_DIR':str(root),'PP_RUNTIME_SECRET_DIR':str(root),'PP_APP_IMAGE':'tradebot-pg-test'}
            for name,role in [('app_dsn','application'),('lifecycle_dsn','lifecycle'),('migrator_dsn','migrator')]:
                path=root/name;path.write_text(dsns[role].replace('@'+address+':','@postgres:'));path.chmod(0o400);os.chown(path,10001,10001)
            (root/'lifecycle').write_text(passwords['lifecycle']);(root/'lifecycle').chmod(0o400);os.chown(root/'lifecycle',999,999)
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
            PHASE='resource_accounting'
            sizes=json.loads(f.sql("SELECT json_build_object('database_bytes',pg_database_size(current_database()),'generated_relation_bytes',(SELECT coalesce(sum(pg_total_relation_size(c.oid)),0) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('raw','core','ops','archive') AND c.relkind IN ('r','p')),'wal_bytes',(SELECT sum(size) FROM pg_ls_waldir()));",root))
            if sizes['generated_relation_bytes']>64*1024**2:raise RuntimeError('generated 64 MiB allowance exceeded')
            print(json.dumps({'result':'PASS_GENERATED_POSTGRES_INTEGRATION','elapsed_seconds':round(time.monotonic()-started,3),'baseline':baseline,'sizes':sizes,'runtime':acceptance,'production_access':False,'cloud_writes':False,'representative_capacity':'NOT_PERFORMED'},sort_keys=True))
        finally:
            f.DEADLINE=time.monotonic()+90
            if runtime_env:
                runtime(['down','--volumes','--remove-orphans'],runtime_env,recovery=True)
            else:f.compose(['down','--volumes'],root,timeout=90)

def runtime(args,env,recovery=False):
    cmd=['docker','compose','--env-file','/dev/null','--project-directory',str(f.HERE),'-f',str(f.HERE/'compose.yaml'),'-f',str(f.HERE/'runtime.compose.yaml'),*args]
    if recovery:return f.run(cmd,env=env,timeout=90)
    return command(cmd,env,timeout=90)

if __name__=='__main__':
    try:main()
    except (RuntimeError,subprocess.TimeoutExpired):
        print(json.dumps({'result':'FAIL','phase':PHASE,'scope':'isolated_generated_ci','production_access':False}))
        raise SystemExit('generated PostgreSQL qualification FAIL; see sanitized phase output') from None
