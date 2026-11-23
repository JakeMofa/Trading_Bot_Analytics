"""Exercise a Redis FDW cache beside the local archive lab, using generated data."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import time

import psycopg
from psycopg import sql

PROJECT = 'tradebot-archive-lab'
DB = 'supabase_db_' + PROJECT
REDIS = PROJECT + '-redis'
NETWORK = REDIS + '-internal'
CONFIG = Path.home() / '.local/share/tradebot-archive-lab/redis-lab.conf'
HASH = 'tradebot:lab:pages'
PAGE = 'generated:A:1-500'
DSN = 'host=127.0.0.1 port=57322 dbname=postgres user=postgres password=postgres connect_timeout=3'


def docker(*args, data=None):
    return subprocess.check_output(['docker', *args], input=data, stderr=subprocess.DEVNULL)


def inspect(kind, name):
    proc = subprocess.run(['docker', kind, 'inspect', name], capture_output=True)
    return json.loads(proc.stdout)[0] if proc.returncode == 0 else None


def setup_redis():
    local = inspect('container', DB)
    if (not local or local['Config']['Labels'].get('com.supabase.cli.project') != PROJECT
            or local['NetworkSettings']['Ports']['5432/tcp'] != [{'HostIp':'127.0.0.1','HostPort':'57322'}]):
        raise RuntimeError('Expected the loopback-only workstation archive database')
    if not CONFIG.exists():
        with os.fdopen(os.open(CONFIG, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), 'w') as cfg:
            cfg.write('bind 0.0.0.0\nport 6379\nsave ""\nappendonly no\nmaxmemory 16mb\nmaxmemory-policy allkeys-lru\nuser default off\n')
            for user, commands in [('labreader', '+hgetall +hkeys +hget +hscan +type +exists'),
                                   ('labwriter', '+hset +hdel +expire')]:
                cfg.write(f'user {user} on >{secrets.token_urlsafe(24)} ~{HASH} {commands} +ping +select\n')
    if CONFIG.stat().st_mode & 0o077:
        raise RuntimeError('The local Redis configuration must be owner-only')
    passwords = {line.split()[1]: line.split()[3][1:] for line in CONFIG.read_text().splitlines()
                 if line.startswith(('user labreader ', 'user labwriter '))}
    if inspect('network', NETWORK) is None:
        docker('network','create','--internal',NETWORK)
    if not inspect('network', NETWORK)['Internal']:
        raise RuntimeError('Expected an internal network')
    if NETWORK not in local['NetworkSettings']['Networks']:
        docker('network','connect',NETWORK,DB)
    current = inspect('container', REDIS)
    if current is None:
        docker('run','-d','--name',REDIS,'--network',NETWORK,'--label',f'tradebot.fixture={REDIS}',
               '--restart','unless-stopped','--user',f'{os.getuid()}:{os.getgid()}',
               '--mount',f'type=bind,source={CONFIG},target=/usr/local/etc/redis/redis.conf,readonly',
               '--tmpfs','/data','redis:7','redis-server','/usr/local/etc/redis/redis.conf')
    elif current['Config']['Labels'].get('tradebot.fixture') != REDIS:
        raise RuntimeError('Redis container identity differs from fixture')
    else:
        docker('start', REDIS)
    actual = inspect('container',REDIS)
    if actual['HostConfig']['PortBindings'] or set(actual['NetworkSettings']['Networks']) != {NETWORK}:
        raise RuntimeError('Expected Redis on its private network without published ports')
    return passwords


def redis(user, password, *command):
    shell = 'IFS= read -r REDISCLI_AUTH; export REDISCLI_AUTH; exec redis-cli -e --user "$@"'
    return docker('exec','-i',REDIS,'sh','-ec',shell,'sh',user,*command,
                  data=(password+'\n').encode())


def ready(password):
    for _ in range(20):
        try:
            redis('labreader', password, 'PING')
            return
        except subprocess.CalledProcessError:
            time.sleep(0.3)
    raise RuntimeError('Local Redis did not become ready')


def setup_db(password):
    with psycopg.connect(DSN) as db:
        db.execute('CREATE EXTENSION IF NOT EXISTS wrappers WITH SCHEMA extensions')
        db.execute('CREATE SCHEMA IF NOT EXISTS archive_cache_lab')
        db.execute('REVOKE ALL ON SCHEMA archive_cache_lab FROM PUBLIC, anon, authenticated')
        if not db.execute("SELECT 1 FROM pg_foreign_data_wrapper WHERE fdwname='archive_cache_redis'").fetchone():
            db.execute('CREATE FOREIGN DATA WRAPPER archive_cache_redis HANDLER extensions.redis_fdw_handler VALIDATOR extensions.redis_fdw_validator')
        if not db.execute("SELECT 1 FROM pg_foreign_server WHERE srvname='archive_cache_redis_local'").fetchone():
            url = f'redis://labreader:{password}@{REDIS}:6379/0'
            secret = db.execute('SELECT vault.create_secret(%s,%s,%s)',
                                (url,'archive_cache_lab_redis','Local generated archive-cache reader')).fetchone()[0]
            db.execute(sql.SQL('CREATE SERVER archive_cache_redis_local FOREIGN DATA WRAPPER archive_cache_redis OPTIONS (conn_url_id {})').format(sql.Literal(str(secret))))
        db.execute("""CREATE FOREIGN TABLE IF NOT EXISTS archive_cache_lab.hot_pages (key text, value text)
                     SERVER archive_cache_redis_local OPTIONS(src_type 'hash',src_key 'tradebot:lab:pages')""")
        db.execute("""CREATE TABLE IF NOT EXISTS archive_cache_lab.page_manifest (
                    page text PRIMARY KEY, owner_id uuid NOT NULL, digest text NOT NULL)""")
        fixture = json.loads(CONFIG.with_name('archive-fixture.json').read_text())
        owner = db.execute('SELECT id FROM auth.users WHERE email=%s',
                           (fixture['accounts'][0]['email'],)).fetchone()[0]
        body = canonical_page(db, owner)
        digest = hashlib.sha256(body.encode()).hexdigest()
        db.execute('INSERT INTO archive_cache_lab.page_manifest VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
                   (PAGE,owner,digest))
        saved = db.execute('SELECT owner_id,digest FROM archive_cache_lab.page_manifest WHERE page=%s',
                           (PAGE,)).fetchone()
        if saved != (owner,digest):
            raise RuntimeError('Synthetic page differs from the retained fixture manifest')
        for role in ('anon','authenticated'):
            assert not db.execute("SELECT has_schema_privilege(%s,'archive_cache_lab','USAGE')",(role,)).fetchone()[0]
        return body


def canonical_page(db, owner):
    rows = db.execute("""SELECT generation,outbox_id,decimal_text FROM public.lab_archive_rows
        WHERE owner_id=%s ORDER BY outbox_id LIMIT 500""",(owner,)).fetchall()
    assert len(rows) == 500 and rows[0][1] == 1 and rows[-1][1] == 500
    return json.dumps([dict(generation=g,outbox_id=i,decimal_text=d) for g,i,d in rows],
                      separators=(',',':'), sort_keys=True)


def read_page():
    with psycopg.connect(DSN,autocommit=True) as db:
        db.execute("SET statement_timeout='3s'")
        owner, digest = db.execute(
            'SELECT owner_id,digest FROM archive_cache_lab.page_manifest WHERE page=%s',(PAGE,)).fetchone()
        code = None
        try:
            cached = db.execute('SELECT value FROM archive_cache_lab.hot_pages WHERE key=%s',(PAGE,)).fetchone()
        except psycopg.Error as exc:
            if not (exc.sqlstate or '').startswith(('HV','08')):
                raise
            reason,code = 'unavailable',exc.sqlstate
        else:
            if cached and hashlib.sha256(cached[0].encode()).hexdigest() == digest:
                return 'hit',cached[0],None
            reason = 'mismatch' if cached else 'miss'
        body = canonical_page(db,owner)
        if hashlib.sha256(body.encode()).hexdigest() != digest:
            raise RuntimeError('Authoritative fixture page does not match the saved manifest')
        return reason,body,code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--test-outage',action='store_true',help='Briefly stop only the disposable Redis cache')
    mode.add_argument('--read',action='store_true',help='Read the existing page and print its source and digest')
    args = parser.parse_args()
    if args.read:
        source, body, code = read_page()
        print(json.dumps(dict(cache=source,sqlstate=code,rows=len(json.loads(body)),
                              canonical_bytes=len(body.encode()),sha256=hashlib.sha256(body.encode()).hexdigest())))
        return
    creds = setup_redis()
    ready(creds['labreader'])
    body = setup_db(creds['labreader'])
    def write(*args):
        redis('labwriter',creds['labwriter'],*args)
    results = {}
    try:
        redis('labreader',creds['labreader'],'HSET',HASH,'denied-write','example')
    except subprocess.CalledProcessError:
        results['reader_write_denied'] = True
    else:
        write('HDEL',HASH,'denied-write')
        raise RuntimeError('Redis reader could write')
    try:
        for label,cmd in [('miss',('HDEL',HASH,PAGE)),('mismatch',('HSET',HASH,PAGE,'obsolete')),
                          ('hit',('HSET',HASH,PAGE,body))]:
            write(*cmd)
            actual, page, _ = read_page()
            assert (actual,page)==(label,body)
            results[label]=True
        if args.test_outage:
            docker('stop','--time','2',REDIS)
            try:
                state,page,code=read_page()
                assert (state,page)==('unavailable',body)
                results['unavailable_sqlstate']=code
            finally:
                docker('start',REDIS)
                ready(creds['labreader'])
    finally:
        write('HSET',HASH,PAGE,body)
        write('EXPIRE',HASH,'3600')
    assert read_page()[:2] == ('hit',body)
    print(json.dumps(dict(results,restored_hit=True,redis_host_ports=0,rows=500,canonical_bytes=len(body.encode()))))


if __name__ == '__main__':
    main()
