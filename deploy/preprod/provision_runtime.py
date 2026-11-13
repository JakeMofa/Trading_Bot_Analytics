"""Explicit PP runtime-role provisioning, never an application startup action."""
from pathlib import Path
import json
import os
import secrets
import stat
import urllib.parse
import foundation as f

RUNTIME_SECRETS = Path('/etc/tradebot/pp-runtime')


def provision(directory=RUNTIME_SECRETS):
    f.preflight()
    if directory.is_symlink():
        raise RuntimeError('unsafe runtime secret directory')
    directory.mkdir(mode=0o700, exist_ok=True)
    if directory.stat().st_uid != 0 or stat.S_IMODE(directory.stat().st_mode) != 0o700:
        raise RuntimeError('unsafe runtime secret owner/mode')
    for name, role, password_file in [('app_dsn','tradebot_app','application'),('migrator_dsn','tradebot_migrator','migrator'),('lifecycle_dsn','tradebot_lifecycle',None)]:
        path=directory/name
        if path.is_symlink():raise RuntimeError('unsafe secret symlink')
        if path.exists():
            info=path.stat()
            if info.st_uid!=10001 or stat.S_IMODE(info.st_mode)!=0o400:raise RuntimeError('unsafe existing runtime secret')
            value=path.read_text().strip()
            parsed=urllib.parse.urlsplit(value)
            if parsed.hostname!='postgres' or parsed.path!='/tradebot_pp' or parsed.username!=role:raise RuntimeError('runtime DSN environment mismatch')
            password=urllib.parse.unquote(parsed.password or '')
        else:
            password=(f.SECRET_DIR/password_file).read_text().strip() if password_file else secrets.token_hex(32)
            if len(password)!=64 or not all(c in '0123456789abcdef' for c in password):raise RuntimeError('invalid generated secret format')
            value='postgresql://'+role+':'+password+'@postgres:5432/tradebot_pp'
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o400)
            with os.fdopen(fd,'w') as stream:stream.write(value+'\n')
            os.chown(path,10001,10001)
        if name=='lifecycle_dsn':
            # A separate file mounts into PostgreSQL, so ALTER ROLE never
            # contains a credential literal that could reach error logs.
            if len(password)!=64 or not all(c in '0123456789abcdef' for c in password):raise RuntimeError('invalid lifecycle credential format')
            pg_secret=f.SECRET_DIR/'lifecycle'
            if pg_secret.is_symlink():raise RuntimeError('unsafe PostgreSQL secret')
            if not pg_secret.exists():
                fd=os.open(pg_secret,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o400)
                with os.fdopen(fd,'w') as stream:stream.write(password+'\n')
                os.chown(pg_secret,999,999)
            if pg_secret.read_text().strip()!=password or pg_secret.stat().st_uid!=999 or stat.S_IMODE(pg_secret.stat().st_mode)!=0o400:
                raise RuntimeError('lifecycle secret continuity mismatch')
    return {'result':'RUNTIME_ROLES_PREPARED','environment':'preprod','credential_values_recorded':False}

def activate_role():
    f.preflight()
    f.sql("DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='tradebot_lifecycle') THEN CREATE ROLE tradebot_lifecycle NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION; END IF; END $$;", f.SECRET_DIR)
    flags=f.sql("SELECT rolsuper,rolcreatedb,rolcreaterole,rolinherit,rolreplication,rolbypassrls FROM pg_roles WHERE rolname='tradebot_lifecycle';",f.SECRET_DIR)
    if flags!='f|f|f|f|f|f' or f.sql("SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE r.rolname='tradebot_lifecycle';",f.SECRET_DIR)!='0':
        raise RuntimeError('unexpected lifecycle privilege or membership')
    f.sql("DO $$ BEGIN EXECUTE format('ALTER ROLE tradebot_lifecycle LOGIN CONNECTION LIMIT 3 PASSWORD %L',btrim(pg_read_file('/run/secrets/lifecycle'),E'\\n\\r ')); END $$; GRANT CONNECT ON DATABASE tradebot_pp TO tradebot_lifecycle;",f.SECRET_DIR)
    return {'result':'LIFECYCLE_ROLE_ACTIVATED','environment':'preprod','credential_values_recorded':False}

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('operation',choices=['prepare','activate']);args=parser.parse_args()
    try:print(json.dumps(provision() if args.operation=='prepare' else activate_role(),sort_keys=True))
    except (OSError,ValueError,RuntimeError):raise SystemExit('runtime role provisioning STOP; no credential output')
