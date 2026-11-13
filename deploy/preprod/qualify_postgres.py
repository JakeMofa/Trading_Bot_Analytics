"""Linux generated-only integration. Never connects to PP/prod or cloud."""
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import time
import foundation as f

REPO=Path(__file__).resolve().parents[2]
REDACTIONS=[]
DEADLINE=0


def command(args,env=None,timeout=120):
    remaining=min(timeout,DEADLINE-time.monotonic())
    if remaining<=0:raise RuntimeError('qualification deadline exceeded')
    result=subprocess.run(args,env=env,cwd=REPO,capture_output=True,text=True,timeout=remaining)
    output=result.stdout+'\n'+result.stderr
    for secret in sorted(REDACTIONS,key=len,reverse=True):output=output.replace(secret,'[REDACTED]')
    output=re.sub(r'postgres(?:ql)?://[^\s\x22\x27]+','[REDACTED_DSN]',output)
    print(output[-50000:],file=sys.stderr)
    if result.returncode:raise RuntimeError('generated integration subprocess failed: '+str(result.returncode))
    return result.stdout


def main():
    global DEADLINE
    if os.environ.get('GITHUB_ACTIONS')!='true' or os.geteuid()!=0 or f.MARKER.exists():
        raise RuntimeError('only isolated root Linux CI is allowed')
    DEADLINE=time.monotonic()+600
    f.DEADLINE=DEADLINE
    started=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='tradebot-pg-qualified-') as folder:
        root=Path(folder)
        try:
            f.start(root)
            baseline=f.verify(root)
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
            # Schema suite performs actual foundation migration and repeat/upgrade tests.
            command([sys.executable,'-m','unittest','discover','-s','backend/tests/postgres','-v'],env)
            command([sys.executable,'-m','unittest','discover','-s','backend/tests','-p','test_postgres*.py','-v'],env)
            sizes=json.loads(f.sql("SELECT json_build_object('database_bytes',pg_database_size(current_database()),'generated_relation_bytes',(SELECT coalesce(sum(pg_total_relation_size(c.oid)),0) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('raw','core','ops','archive') AND c.relkind IN ('r','p')),'wal_bytes',(SELECT sum(size) FROM pg_ls_waldir()));",root))
            if sizes['generated_relation_bytes']>64*1024**2:raise RuntimeError('generated 64 MiB allowance exceeded')
            print(json.dumps({'result':'PASS_GENERATED_POSTGRES_INTEGRATION','elapsed_seconds':round(time.monotonic()-started,3),'baseline':baseline,'sizes':sizes,'production_access':False,'cloud_writes':False,'representative_capacity':'NOT_PERFORMED'},sort_keys=True))
        finally:
            f.DEADLINE=time.monotonic()+90
            f.compose(['down','--volumes'],root,timeout=90)

if __name__=='__main__':
    try:main()
    except (RuntimeError,subprocess.TimeoutExpired):raise SystemExit('generated PostgreSQL qualification FAIL; see sanitized phase output') from None
