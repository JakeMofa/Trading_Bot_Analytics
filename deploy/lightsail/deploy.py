#!/usr/bin/python3
"""Root-owned forced SSH command. Receives a tracked-only bundle; preserves runtime data."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = Path('/opt/tradebot')
HELPERS = Path('/usr/local/lib/tradebot-cd')
BRANCH = 'refs/heads/codex/lightsail-deployment'
SERVICES = ('tradebot-api', 'tradebot-ensemble', 'tradebot-lifecycle', 'tradebot-soak.timer')


def run(*args, user=False, **kwargs):
    command = (['sudo', '-u', 'tradebot', '--'] if user else []) + list(args)
    return subprocess.run(command, cwd=ROOT, check=True, text=True, capture_output=True, **kwargs).stdout.strip()


def git(*args):
    return run('git', *args, user=True)


def services():
    states = {}
    for name in SERVICES:
        properties = dict(line.split('=', 1) for line in run('systemctl', 'show', name, '-p', 'ActiveState', '-p', 'NRestarts', '-p', 'MainPID', '-p', 'UnitFileState').splitlines())
        assert properties['ActiveState'] == 'active', name + ' inactive'
        assert properties['UnitFileState'] == 'enabled', name + ' disabled'
        states[name] = properties
    processes = run('ps', '-u', 'tradebot', '-o', 'args=').splitlines()
    assert sum('backend/app/run_api.py' in line for line in processes) == 1, 'API collector ownership is not singular'
    assert not any(re.search(r'backend/app/(streaming|run_collector|dashboard)\.py', line) for line in processes), 'competing collector/dashboard process'
    listeners = run('ss', '-ltnH').splitlines()
    assert all(line.split()[3] == '127.0.0.1:8000' for line in listeners if line.split()[3].endswith(':8000')), 'API publicly bound'
    return states


def protected():
    return (hashlib.sha256((ROOT / '.env').read_bytes()).hexdigest(),
            (ROOT / '.env').stat().st_mode & 0o777, (ROOT / '.env').stat().st_uid)


def preflight():
    # Use the same environment systemd actually supplied; never source or print .env.
    pid = run('systemctl', 'show', 'tradebot-api', '-p', 'MainPID', '--value')
    env = dict(item.split('=', 1) for item in Path('/proc/' + pid + '/environ').read_text().split('\0') if '=' in item)
    assert env.get('ENABLE_OPENAI_ANALYST') == 'false' and env.get('ENABLE_LOCAL_RETENTION') == 'false', 'unsafe process flags'
    run(str(ROOT / '.venv/bin/python'), '-c', "import sys,runpy; sys.path.insert(0,'backend/app'); from run_api import load_local_env; load_local_env(); runpy.run_path('deploy/lightsail/preflight.py',run_name='__main__')", user=True)
    assert not git('diff', '--name-only', 'HEAD'), 'tracked production changes'
    assert not git('diff', '--cached', '--name-only'), 'staged production changes'
    assert protected()[1] == 0o600, 'protected .env permissions'
    assert shutil.disk_usage(ROOT).free > 2 * 1024**3, 'less than 2 GiB free disk'
    db = ROOT / 'data/btc_intelligence.db'
    assert db.is_file(), 'database missing'
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=10) as connection:
        assert connection.execute('PRAGMA quick_check').fetchall() == [('ok',)], 'SQLite quick_check failed'
        assert connection.execute('PRAGMA foreign_key_check').fetchone() is None, 'SQLite foreign-key check failed'
    return services()


def smoke(legacy=False, attempts=24):
    args = ['python3', str(HELPERS / 'smoke.py'), '--attempts', str(attempts)]
    if legacy:
        args.append('--legacy')
    value = json.loads(run(*args, user=True))
    print(json.dumps(value), flush=True)
    return value


def deploy(revision, bundle):
    before = preflight()
    old = git('rev-parse', 'HEAD')
    env_before = protected()
    legacy = not bool(git('ls-tree', '--name-only', old, 'backend/app/system_monitoring.py'))
    smoke(legacy, attempts=1)
    refs = git('bundle', 'list-heads', str(bundle)).splitlines()
    assert refs == [revision + ' ' + BRANCH], 'bundle must contain exactly the approved branch head'
    git('bundle', 'verify', str(bundle))
    git('fetch', str(bundle), BRANCH)
    assert git('rev-parse', 'FETCH_HEAD') == revision, 'revision mismatch'
    git('merge-base', '--is-ancestor', old, revision)
    changes = git('diff', '--name-only', old, revision).splitlines()
    assert all(not path.startswith(('data/', '.env')) for path in changes), 'protected path in deployment'
    # Requirements and service/security changes need a separate reviewed provisioning operation.
    guarded = {'backend/requirements.txt'} | {str(p.relative_to(ROOT)) for p in (ROOT / 'deploy/lightsail').glob('*.service')} | {'deploy/lightsail/install-services.sh', 'deploy/lightsail/preflight.py'}
    assert not guarded.intersection(changes), 'dependency or service provisioning change requires operator review'
    restart = any(path.startswith('backend/app/') for path in changes)
    evidence_dir = ROOT / 'data/deployments'
    evidence_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    evidence = {'OLD_REVISION': old, 'NEW_REVISION': revision, 'status': 'prepared', 'services_restarted': []}
    record = evidence_dir / (str(time.time_ns()) + '.json')
    def save():
        record.write_text(json.dumps(evidence, indent=2) + '\n')
        record.chmod(0o600)
        print(json.dumps(evidence), flush=True)
    save()
    changed = False
    try:
        git('checkout', '--detach', revision)
        changed = True
        if restart:
            run('systemctl', 'restart', 'tradebot-api')
            evidence['services_restarted'] = ['tradebot-api']
        smoke(attempts=24)
        first = services()
        time.sleep(12)
        after = services()
        assert all(first[name]['NRestarts'] == after[name]['NRestarts'] and first[name]['MainPID'] == after[name]['MainPID'] for name in SERVICES), 'service restart loop'
        assert all(before[name]['MainPID'] == after[name]['MainPID'] for name in SERVICES if name != 'tradebot-api'), 'unaffected service restarted'
        assert protected() == env_before, 'protected environment changed'
        evidence['status'] = 'success'
        evidence['services'] = after
        save()
    except Exception as error:
        evidence['status'] = 'failed'
        evidence['error_type'] = type(error).__name__
        if changed:
            # Only failures after checkout can be caused by the deployment. Never repair data.
            try:
                git('checkout', '--detach', old)
                if restart:
                    run('systemctl', 'restart', 'tradebot-api')
                smoke(legacy, attempts=24)
                services()
                assert protected() == env_before, 'protected environment changed'
                evidence['rollback'] = {'revision': old, 'health': 'PASS'}
            except Exception as rollback_error:
                evidence['rollback'] = {'revision': old, 'health': 'FAIL', 'error_type': type(rollback_error).__name__}
        save()
        raise SystemExit(1)


def main():
    # SSH_ORIGINAL_COMMAND is passed as one argument by the forced command entry.
    command = sys.argv[1] if len(sys.argv) == 2 else ''
    match = re.fullmatch(r'deploy ([0-9a-f]{40})', command)
    if not match:
        raise SystemExit('Only deploy <full SHA> is allowed')
    with open('/run/lock/tradebot-deploy.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with tempfile.TemporaryDirectory(prefix='tradebot-deploy-') as directory:
            path = Path(directory)
            path.chmod(0o755)
            bundle = path / 'source.bundle'
            with bundle.open('wb') as output:
                count = 0
                while chunk := sys.stdin.buffer.read(1024 * 1024):
                    count += len(chunk)
                    if count > 100 * 1024 * 1024:
                        raise SystemExit('bundle exceeds 100 MiB')
                    output.write(chunk)
            bundle.chmod(0o644)
            deploy(match[1], bundle)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'deployment': 'FAIL', 'error_type': type(error).__name__,
                          'check': str(error) if isinstance(error, AssertionError) else 'preflight/command failed'}))
        raise SystemExit(1)
