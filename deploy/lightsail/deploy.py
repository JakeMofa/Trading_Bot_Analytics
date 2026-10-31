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
import signal
from datetime import datetime, timezone

ROOT = Path('/opt/tradebot')
HELPERS = Path('/usr/local/lib/tradebot-cd')
BRANCH = 'refs/heads/codex/lightsail-deployment'
SERVICES = ('tradebot-api', 'tradebot-ensemble', 'tradebot-lifecycle', 'tradebot-soak.timer')
I7_OLD = 'a7c098900f8310367fc262a1b837c369bb63dc56'
I7_RELEASE = 'd56b4a73ad6f1a10ba2bac928087cd5d85c6a42a'
I7_AUTH = Path('/run/tradebot-i7-authorization.json')
I7_FILES = {'backend/app/streaming.py', 'backend/tests/test_features.py',
            'backend/tests/test_streaming.py', 'deploy/lightsail/README.md',
            'docs/PLAN/I7_FEATURE_STALL_2026-10-30.md', 'docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md'}
I7_SCHEMA_PROGRAM = '''import json,sqlite3,sys
from pathlib import Path
expected={
'markets': {'id','start','end','duration','status','first_seen'},
'stream_events': {'source','event_id','received_at','source_time','price'},
'reference_prices': {'id','source','received_at','source_time','price'},
'observations': {'id','market_id','received_at','kind','payload'},
'candles': {'source','symbol','granularity','time','close','volume','first_seen'},
'feature_snapshots': {'id','market_id','as_of','version','values_json','quality_json','evidence_json'},
'predictions': {'id','market_id','as_of','model_version','probability_up'},
'feed_health': {'source','status','last_data_at'}}
p=Path(sys.argv[1]).resolve(strict=True)
db=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True,timeout=0.1)
try:
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
    assert expected.keys() <= tables, 'required tables missing'
    for name, columns in expected.items():
        assert columns <= {r[1] for r in db.execute('PRAGMA table_info('+name+')')}, 'required columns missing'
    print(json.dumps({'schema_readiness':'PASS','integrity':'NOT_PERFORMED_SCOPED_I7_EXCEPTION'}))
finally:
    db.close()
'''


class I7Budget:
    def __init__(self):
        self.started = time.monotonic()
        self.recovery = False

    def command(self, *args, cap=30, user=False):
        remaining = (780 if self.recovery else 600) - (time.monotonic() - self.started)
        if remaining <= 0:
            raise TimeoutError('I7 release budget exhausted')
        return run(*args, user=user, timeout=min(cap, remaining))


def i7_authorization():
    stat = I7_AUTH.stat()
    assert stat.st_uid == 0 and stat.st_mode & 0o777 == 0o600 and not I7_AUTH.is_symlink(), 'invalid I7 authorization permissions'
    authorization = json.loads(I7_AUTH.read_text())
    assert authorization['old'] == I7_OLD and authorization['release'] == I7_RELEASE, 'wrong authorized revision'
    assert authorization['application_ci_run'] > 0 and authorization['helper_ci_run'] > 0, 'exact CI acknowledgment missing'
    assert authorization['helper_sha256'] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'helper differs from CI-verified export'
    assert 0 < authorization['expires_at'] - time.time() <= 3600, 'I7 authorization expired or too long'
    return authorization


def i7_runtime_flags(states):
    for unit in SERVICES[:3]:
        env = dict(x.split('=',1) for x in Path('/proc', states[unit]['MainPID'], 'environ').read_text().split('\0') if '=' in x)
        assert env.get('ENABLE_OPENAI_ANALYST') == 'false' and env.get('ENABLE_LOCAL_RETENTION') == 'false', 'unsafe process flags'
        assert not any(env.get(k) for k in ('OPENAI_API_KEY','OPENAPIKEY','OPENAI_KEY')), 'paid AI credentials present'
        if unit == 'tradebot-api':
            assert env.get('MAX_LOCAL_STORAGE_MB') == '4096', 'guard changed'


def i7_release(revision, bundle):
    """One-use exact-SHA exception; no full scans, DB copies or DB rollback."""
    budget = I7Budget()
    command = budget.command
    def source(*args):
        return command('git', *args, user=True)
    assert revision == I7_RELEASE, 'wrong I7 candidate'
    old = source('rev-parse', 'HEAD')
    assert old == I7_OLD, 'I7 runtime changed'
    assert source('bundle', 'list-heads', str(bundle)).splitlines() == [revision + ' ' + BRANCH], 'wrong bundle ref'
    source('bundle', 'verify', str(bundle))
    source('fetch', str(bundle), BRANCH)
    assert source('rev-parse', 'FETCH_HEAD') == revision, 'bundle SHA mismatch'
    source('merge-base', '--is-ancestor', old, revision)
    assert set(source('diff', '--name-only', old, revision).splitlines()) == I7_FILES, 'I7 release scope changed'
    authorization = i7_authorization()  # Operator checks CI; workflow independently checks application CI.
    assert not source('status', '--porcelain', '--untracked-files=no'), 'production checkout changed'
    env_before = protected()
    assert env_before[1] == 0o600, 'unsafe configuration permissions'
    db = ROOT / 'data/btc_intelligence.db'
    assert db.is_file() and not db.is_symlink(), 'database missing or unexpected'
    assert shutil.disk_usage(ROOT).free > 2 * 1024**3, 'less than 2 GiB free'
    assert sum(p.stat().st_size for p in (db, Path(str(db)+'-wal')) if p.exists()) < 4096 * 1024**2, 'storage guard reached'
    before = services(command)
    i7_runtime_flags(before)
    program = ("import os,runpy,sys; sys.dont_write_bytecode=True; sys.path.insert(0,'backend/app'); "
               "from run_api import load_local_env; os.environ.clear(); load_local_env(); "
               "assert os.environ.get('MAX_LOCAL_STORAGE_MB')=='4096'; "
               "runpy.run_path('deploy/lightsail/preflight.py',run_name='__main__')")
    command(str(ROOT/'.venv/bin/python'), '-c', program, user=True, cap=15)
    schema = json.loads(command(sys.executable, '-c', I7_SCHEMA_PROGRAM, str(db), user=True, cap=5))
    directory = ROOT/'data/deployments'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    record = directory/(str(time.time_ns())+'-i7.json')
    evidence = {'OLD_REVISION':old, 'NEW_REVISION':revision, 'status':'prepared',
                'services_restarted':[], 'checks':schema, 'application_ci_run':authorization['application_ci_run'],
                'helper_ci_run':authorization['helper_ci_run'], 'events':[]}
    def save(phase):
        evidence['events'].append({'phase':phase,'at':datetime.now(timezone.utc).isoformat()})
        record.write_text(json.dumps(evidence,indent=2)+'\n')
        record.chmod(0o600)
        print(json.dumps(evidence),flush=True)
    # Baseline unresponsiveness is evidence, not a veto for this known stall fix.
    baseline = "import json,time,urllib.request; t=time.monotonic();\ntry:\n r=urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2); p=json.load(r); print(json.dumps({'responded':True,'seconds':time.monotonic()-t,'status':p.get('status'),'collector_running':p.get('collector',{}).get('running')}))\nexcept Exception as e:\n print(json.dumps({'responded':False,'error_type':type(e).__name__,'seconds':time.monotonic()-t}))"
    evidence['baseline'] = json.loads(command(sys.executable,'-c',baseline,cap=5))
    assert evidence['baseline'].get('collector_running') is not False, 'collector stopped before release'
    save('preflight_passed')
    I7_AUTH.unlink()  # Consume before any checkout; no automatic second attempt.
    changed = False
    previous = {}
    def interrupted(signum, frame):
        for sig in previous:
            signal.signal(sig, signal.SIG_IGN)
        raise TimeoutError('I7 release interrupted')
    try:
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            previous[sig] = signal.signal(sig, interrupted)
        changed = True  # A partial checkout must also roll back.
        save('checkout_started')
        source('checkout','--detach',revision)
        save('api_restart_requested')
        command('systemctl','restart','tradebot-api',cap=90)
        evidence['services_restarted'] = ['tradebot-api']
        save('api_restart_returned')
        result = command(sys.executable,str(HELPERS/'smoke.py'),'--attempts','24',user=True,cap=180)
        evidence['smoke'] = json.loads(result)
        first = services(command)
        time.sleep(12)
        after = services(command)
        i7_runtime_flags(after)
        assert all(first[n]['MainPID']==after[n]['MainPID'] and first[n]['NRestarts']==after[n]['NRestarts'] for n in SERVICES), 'service restart loop'
        assert all(before[n]['MainPID']==after[n]['MainPID'] and before[n]['NRestarts']==after[n]['NRestarts'] for n in SERVICES if n!='tradebot-api'), 'unaffected service changed'
        assert source('rev-parse','HEAD') == revision, 'runtime revision mismatch'
        assert protected() == env_before, 'protected config changed'
        evidence.update(status='success_pending_I7_validation',services=after)
        save('release_complete')
    except BaseException as error:
        evidence.update(status='failed',error_type=type(error).__name__)
        # Reserve recovery even after a deadline/interruption; never restore DB data.
        budget.recovery = True
        for sig in previous:
            signal.signal(sig, signal.SIG_IGN)
        if changed:
            try:
                save('rollback_started')
                source('checkout','--detach',old)
                command('systemctl','restart','tradebot-api',cap=90)
                restored = services(command)
                i7_runtime_flags(restored)
                assert source('rev-parse','HEAD') == old and protected() == env_before, 'rollback state mismatch'
                assert all(restored[n]['MainPID']==before[n]['MainPID'] for n in SERVICES if n!='tradebot-api'), 'unaffected service changed'
                evidence['rollback']={'revision':old,'services':'restored','health':'NOT_CERTIFIED_ORIGINAL_STALL'}
            except BaseException as rollback_error:
                evidence['rollback']={'status':'MANUAL_ACTION_REQUIRED','error_type':type(rollback_error).__name__}
        save('release_failed')
        raise SystemExit(1)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def run(*args, user=False, **kwargs):
    command = (['sudo', '-u', 'tradebot', '--'] if user else []) + list(args)
    return subprocess.run(command, cwd=ROOT, check=True, text=True, capture_output=True, **kwargs).stdout.strip()


def git(*args):
    return run('git', *args, user=True)


def services(runner=None):
    execute = runner or run
    states = {}
    for name in SERVICES:
        properties = dict(line.split('=', 1) for line in execute('systemctl', 'show', name, '-p', 'ActiveState', '-p', 'NRestarts', '-p', 'MainPID', '-p', 'UnitFileState').splitlines())
        assert properties['ActiveState'] == 'active', name + ' inactive'
        assert properties['UnitFileState'] == 'enabled', name + ' disabled'
        properties.setdefault('NRestarts', '0')  # Timers have no process/restart fields.
        properties.setdefault('MainPID', '0')
        states[name] = properties
    processes = execute('ps', '-u', 'tradebot', '-o', 'args=').splitlines()
    assert sum('backend/app/run_api.py' in line for line in processes) == 1, 'API collector ownership is not singular'
    assert not any(re.search(r'backend/app/(streaming|run_collector|dashboard)\.py', line) for line in processes), 'competing collector/dashboard process'
    listeners = execute('ss', '-ltnH').splitlines()
    assert [line.split()[3] for line in listeners if line.split()[3].endswith(':8000')] == ['127.0.0.1:8000'], 'API binding unavailable or not private'
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
    try:
        value = json.loads(run(*args, user=True))
    except subprocess.CalledProcessError as error:
        try:
            failure = json.loads(error.stdout.strip().splitlines()[-1])
            reason = failure.get('check', 'smoke request failed')
        except (ValueError, IndexError, AttributeError):
            reason = 'smoke command failed'
        raise AssertionError(reason) from None
    print(json.dumps(value), flush=True)
    return value


def deploy(revision, bundle):
    if revision == I7_RELEASE:
        return i7_release(revision, bundle)
    before = preflight()
    old = git('rev-parse', 'HEAD')
    env_before = protected()
    legacy = not bool(git('ls-tree', '--name-only', old, 'backend/app/system_monitoring.py'))
    smoke(legacy, attempts=6)
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
        evidence['reason'] = str(error) if isinstance(error, AssertionError) else 'command/verification error'
        if changed and isinstance(error, (AssertionError, subprocess.CalledProcessError)):
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
        if changed and not isinstance(error, (AssertionError, subprocess.CalledProcessError)):
            evidence['verification'] = 'manual verification required; no material application failure established'
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
