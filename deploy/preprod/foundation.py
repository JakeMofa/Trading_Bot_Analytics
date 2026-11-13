#!/usr/bin/env python3
"""Bounded PP-only PostgreSQL foundation. No application, collector or cloud access."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import stat
import sys
import subprocess
import tempfile
import time

HERE = Path(__file__).resolve().parent
SECRET_DIR = Path('/etc/tradebot/pp-postgres')
MARKER = Path('/etc/tradebot/preprod-host.json')
IMAGE = 'postgres:17.12-bookworm@sha256:40865bc877a289da75963d97d72b59633f639fc5af7a4e856bfa3714cae5b536'
ROLES = {'admin': 'postgres', 'migrator': 'tradebot_migrator', 'application': 'tradebot_app', 'reader': 'tradebot_reader'}
GIB = 1024 ** 3
DEADLINE = None


def run(args, *, input=None, timeout=30, env=None):
    # Never include child output, environment or argv in errors: some commands
    # consume credentials. Failure evidence is operation + exit code only.
    remaining = timeout if DEADLINE is None else min(timeout, DEADLINE - time.monotonic())
    if remaining <= 0:
        raise RuntimeError('overall work deadline exceeded')
    process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, env=env, start_new_session=True)
    try:
        stdout, _ = process.communicate(input, timeout=remaining)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
        raise RuntimeError('child deadline exceeded; process group terminated and reaped') from None
    if process.returncode:
        raise RuntimeError(f'operation failed (exit {process.returncode})')
    return stdout.strip()


def validate_host(hostname, marker, disk_free, available_memory, os_id, version):
    if hostname != 'tradebot-preprod-01' or marker.get('environment') != 'preprod' or marker.get('project') != 'Tradebot':
        raise RuntimeError('refusing non-PP host')
    for key in ('live_collector_authorized', 'paid_ai_authorized', 'production_data_copied', 'application_installed'):
        if marker.get(key) is not False:
            raise RuntimeError(f'foundation requires {key}=false')
    if os_id != 'ubuntu' or version != '24.04':
        raise RuntimeError('only qualified Ubuntu 24.04 is supported')
    if disk_free < 10 * GIB or available_memory < GIB:
        raise RuntimeError('requires 10 GiB free disk and 1 GiB available RAM')


def preflight():
    if os.geteuid() != 0:
        raise RuntimeError('run through the existing sudo operator route')
    info = MARKER.stat()
    if MARKER.is_symlink() or info.st_uid != 0 or info.st_mode & 0o022:
        raise RuntimeError('unsafe host identity marker')
    marker = json.loads(MARKER.read_text())
    release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    available = int(memory['MemAvailable'].split()[0]) * 1024
    free = shutil.disk_usage('/').free
    validate_host(socket.gethostname(), marker, free, available,
                  release.get('ID', '').strip('"'), release.get('VERSION_ID', '').strip('"'))
    for unit in ('tradebot-api', 'tradebot-ensemble', 'tradebot-lifecycle'):
        state = run(['systemctl', 'show', unit, '--property=LoadState', '--value'])
        if state != 'not-found':
            raise RuntimeError('existing application service needs separate runtime qualification')
    return {'host': socket.gethostname(), 'disk_free_bytes': free, 'available_memory_bytes': available}


def compose(args, secret_dir, *, timeout=60, input=None):
    env = {**os.environ, 'PP_SECRET_DIR': str(secret_dir)}
    # Explicit file and project directory: no implicit overrides or .env secrets.
    return run(['docker', 'compose', '--env-file', '/dev/null', '--project-directory', str(HERE),
                '-f', str(HERE / 'compose.yaml'), *args], timeout=timeout, env=env, input=input)


def prepare_secrets(secret_dir):
    if secret_dir.is_symlink():
        raise RuntimeError('secret directory must not be a symlink')
    secret_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if secret_dir.stat().st_uid != os.geteuid() or stat.S_IMODE(secret_dir.stat().st_mode) != 0o700:
        raise RuntimeError('unsafe secret directory owner or mode')
    for name in ROLES:
        path = secret_dir / name
        if not path.exists() and not path.is_symlink():
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o400)
            with os.fdopen(fd, 'w') as stream:
                stream.write(secrets.token_hex(32) + '\n')
            os.chown(path, 999, 999)  # verified official Debian image postgres UID
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 999 or stat.S_IMODE(info.st_mode) != 0o400:
            raise RuntimeError('unsafe secret file owner/type/mode')
        if len(path.read_text().strip()) != 64:
            raise RuntimeError('unexpected foundation credential format')


def sql(query, secret_dir, role='admin', *, timeout=20):
    if role not in ROLES:
        raise ValueError('unknown role')
    # Password is read inside the container, not exposed in host process argv.
    script = 'export PGPASSWORD="$(cat /run/secrets/' + role + ')"; exec psql -X -qAt --set ON_ERROR_STOP=1 -h 127.0.0.1 -U ' + ROLES[role] + ' -d tradebot_pp'
    return compose(['exec', '-T', 'postgres', 'sh', '-ec', script], secret_dir, input=query, timeout=timeout)


def verify_configuration(secret_dir):
    config = json.loads(compose(['config', '--format', 'json'], secret_dir))
    service = config['services']['postgres']
    if set(config['services']) != {'postgres'} or service.get('ports') or service['image'] != IMAGE:
        raise RuntimeError('unexpected service, exposed port or image')
    if int(service['mem_limit']) != 512 * 1024 ** 2 or int(service['memswap_limit']) != int(service['mem_limit']):
        raise RuntimeError('memory limit mismatch')
    if not config['networks']['database'].get('internal'):
        raise RuntimeError('database network must be isolated')
    return config


def start(secret_dir):
    verify_configuration(secret_dir)
    print('foundation: image pull', file=sys.stderr)
    compose(['pull', 'postgres'], secret_dir, timeout=240)
    uid = run(['docker', 'run', '--rm', '--network', 'none', '--entrypoint', 'id', IMAGE, '-u', 'postgres'])
    if uid != '999':
        raise RuntimeError('image postgres UID does not match secret ownership')
    print('foundation: secret preparation', file=sys.stderr)
    prepare_secrets(secret_dir)
    try:
        compose(['up', '-d', '--wait', '--wait-timeout', '90', 'postgres'], secret_dir, timeout=110)
        identity = sql('SELECT environment, database_name, foundation_version FROM ops.environment_identity;', secret_dir)
        if identity != 'preprod|tradebot_pp|1':
            raise RuntimeError('database environment/version mismatch')
    except RuntimeError:
        # Preserve volume and credentials, stop only this PP foundation service.
        compose(['stop', 'postgres'], secret_dir, timeout=65)
        raise


def verify(secret_dir):
    print('foundation: verify identity/settings', file=sys.stderr)
    started = time.monotonic()
    verify_configuration(secret_dir)
    identity = sql('SELECT environment, database_name, foundation_version FROM ops.environment_identity;', secret_dir)
    if identity != 'preprod|tradebot_pp|1':
        raise RuntimeError('database environment/version mismatch')
    settings = json.loads(sql("SELECT json_build_object('version',current_setting('server_version'),'fsync',current_setting('fsync'),'synchronous_commit',current_setting('synchronous_commit'),'full_page_writes',current_setting('full_page_writes'),'autovacuum',current_setting('autovacuum'),'shared_buffers',current_setting('shared_buffers'),'max_connections',current_setting('max_connections'),'data_checksums',current_setting('data_checksums'));", secret_dir))
    if any(settings[key] != 'on' for key in ('fsync', 'synchronous_commit', 'full_page_writes', 'autovacuum', 'data_checksums')) or settings['shared_buffers'] != '128MB' or settings['max_connections'] != '20':
        raise RuntimeError('durability/resource settings mismatch')
    if not settings['version'].startswith('17.12 '):
        raise RuntimeError('unexpected PostgreSQL version')
    print('foundation: generated data and roles', file=sys.stderr)
    # Deliberately small, repeatable generated data; business migrations are CP2.
    sql("SET ROLE tradebot_owner; CREATE TABLE IF NOT EXISTS ops.foundation_smoke(id integer PRIMARY KEY CHECK(id BETWEEN 1 AND 32), amount numeric(30,18) NOT NULL, source_time text NOT NULL, payload text NOT NULL CHECK(length(payload)=128)); GRANT SELECT,INSERT ON ops.foundation_smoke TO tradebot_app; GRANT SELECT ON ops.foundation_smoke TO tradebot_reader;", secret_dir, 'migrator')
    sql("INSERT INTO ops.foundation_smoke SELECT n, 12345.123456789012345678::numeric, '2026-11-12T00:00:00.123456789Z', repeat('g',128) FROM generate_series(1,32) AS n ON CONFLICT DO NOTHING;", secret_dir, 'application')
    check = "SELECT count(*),bool_and(amount=12345.123456789012345678::numeric AND source_time='2026-11-12T00:00:00.123456789Z' AND payload=repeat('g',128)) FROM ops.foundation_smoke;"
    before = sql(check, secret_dir, 'reader')
    if before != '32|t':
        raise RuntimeError('generated values mismatch')
    # Reader cannot write even if it overrides the read-only default; no grants.
    denied = [
        ('reader', "SET default_transaction_read_only=off; UPDATE ops.foundation_smoke SET amount=0 WHERE id=1;"),
        ('application', 'CREATE TABLE core.must_not_exist(id int);'),
        ('application', "UPDATE ops.environment_identity SET foundation_version=2;"),
        ('application', 'SET ROLE tradebot_owner;'),
    ]
    for role, query in denied:
        try:
            sql(query, secret_dir, role)
        except RuntimeError as error:
            if 'exit 3' not in str(error):
                raise
        else:
            raise RuntimeError('restricted role unexpectedly permitted operation')
    print('foundation: container recreation', file=sys.stderr)
    container_before = compose(['ps', '-q', 'postgres'], secret_dir)
    volume_before = json.loads(run(['docker', 'inspect', '--format', '{{json .Mounts}}', container_before]))
    pg_volume = next(m['Name'] for m in volume_before if m['Destination'] == '/var/lib/postgresql/data')
    compose(['up', '-d', '--force-recreate', '--wait', '--wait-timeout', '60', 'postgres'], secret_dir, timeout=85)
    container_after = compose(['ps', '-q', 'postgres'], secret_dir)
    if container_after == container_before or sql(check, secret_dir, 'reader') != before:
        raise RuntimeError('container recreation/persistence proof failed')
    inspected = json.loads(run(['docker', 'inspect', '--format', '{{json .}}', container_after]))
    # Do not emit the inspect payload; environment can contain secret paths.
    if inspected['HostConfig']['PortBindings'] or inspected['HostConfig']['Memory'] != 512 * 1024 ** 2 or inspected['State'].get('OOMKilled'):
        raise RuntimeError('runtime port, memory or OOM check failed')
    if not any(m.get('Name') == pg_volume for m in inspected['Mounts']):
        raise RuntimeError('persistent volume changed')
    smoke_bytes = int(sql("SELECT pg_total_relation_size('ops.foundation_smoke');", secret_dir))
    if smoke_bytes > 64 * 1024 ** 2:
        raise RuntimeError('generated smoke allowance exceeded')
    usage = json.loads(sql("SELECT json_build_object('database_bytes',pg_database_size(current_database()),'wal_bytes',(SELECT coalesce(sum(size),0) FROM pg_ls_waldir()),'temporary_bytes',(SELECT temp_bytes FROM pg_stat_database WHERE datname=current_database()));", secret_dir))
    allocated = int(compose(['exec', '-T', 'postgres', 'du', '-s', '-B1', '/var/lib/postgresql/data'], secret_dir).split()[0])
    stats = json.loads(run(['docker', 'stats', '--no-stream', '--format', '{{json .}}', container_after]))
    return {'result': 'PASS_FOUNDATION_ONLY', 'settings': settings, 'generated_rows': 32,
            'generated_relation_bytes': smoke_bytes, 'usage': usage, 'pgdata_allocated_bytes': allocated,
            'container_memory': stats['MemUsage'], 'recreated': True, 'volume': pg_volume,
            'published_ports': [], 'restricted_role_checks': len(denied), 'image': IMAGE,
            'elapsed_seconds': round(time.monotonic() - started, 3),
            'collector': 'NOT_INSTALLED', 'application': 'NOT_INSTALLED', 'cd': 'NOT_QUALIFIED'}


def main():
    global DEADLINE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['preflight', 'install-docker', 'up', 'verify', 'status', 'stop', 'ci'])
    args = parser.parse_args()
    DEADLINE = time.monotonic() + (600 if args.operation in ('ci', 'install-docker') else 360 if args.operation == 'up' else 180)
    if args.operation == 'ci':
        if os.environ.get('GITHUB_ACTIONS') != 'true' or os.geteuid() != 0 or MARKER.exists():
            raise RuntimeError('ci command requires the root isolated GitHub runner')
        with tempfile.TemporaryDirectory(prefix='tradebot-pp-secrets-') as folder:
            directory = Path(folder)
            try:
                start(directory)
                print(json.dumps(verify(directory), sort_keys=True))
            finally:
                # Only generated CI's named project; never used by operator mode.
                DEADLINE = time.monotonic() + 90
                compose(['down', '--volumes'], directory, timeout=90)
        return
    evidence = preflight()
    if args.operation == 'install-docker':
        run(['bash', str(HERE / 'install-docker.sh')], timeout=600)
        evidence['docker'] = run(['docker', '--version'])
        evidence['compose'] = run(['docker', 'compose', 'version'])
    elif args.operation == 'up':
        start(SECRET_DIR)
        evidence['result'] = 'STARTED'
    elif args.operation == 'verify':
        evidence.update(verify(SECRET_DIR))
    elif args.operation == 'stop':
        compose(['stop', 'postgres'], SECRET_DIR, timeout=80)
        evidence['result'] = 'STOPPED_VOLUME_PRESERVED'
    elif args.operation == 'status':
        evidence['postgres'] = json.loads(compose(['ps', '--format', 'json'], SECRET_DIR))
    print(json.dumps(evidence, sort_keys=True))

if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError) as error:
        raise SystemExit(f'FOUNDATION STOP: {error}') from None
