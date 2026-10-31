"""Prepared, operator-only I7 maintenance release; default invocation is plan-only.

This is NOT installed as a forced SSH command and is NOT called by normal CD.
Execution requires a separately approved collection gap and fresh exact-SHA CI
verification by the trusted operator. It never restores a database on rollback.
"""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time

OLD = 'a7c098900f8310367fc262a1b837c369bb63dc56'
RELEASE = 'd56b4a73ad6f1a10ba2bac928087cd5d85c6a42a'
BRANCH = 'refs/heads/codex/lightsail-deployment'
ROOT = Path('/opt/tradebot')
APPS = ('tradebot-api', 'tradebot-lifecycle', 'tradebot-ensemble')
MONITOR = ('tradebot-soak.timer', 'tradebot-soak.service')
ALLOWED = {'backend/app/streaming.py', 'backend/tests/test_features.py',
           'backend/tests/test_streaming.py', 'docs/PLAN/I7_FEATURE_STALL_2026-10-30.md',
           'docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md', 'deploy/lightsail/README.md'}


class GateError(RuntimeError):
    pass


class Budget:
    """25-minute operation, reserving the final five minutes for recovery."""
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.started = clock()

    def seconds(self, cap, recovery=False):
        remaining = (1500 if recovery else 1200) - (self.clock() - self.started)
        if remaining <= 0:
            raise GateError('maintenance budget exhausted')
        return min(cap, remaining)


def verify_copy(path, check, seconds):
    """Immutable copy only; caller additionally enforces a child-process deadline."""
    if check not in ('quick_check', 'foreign_key_check'):
        raise GateError('unsupported check')
    path = Path(path).resolve(strict=True)
    started = time.monotonic()
    with contextlib.closing(sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True, timeout=1)) as db:
        db.execute('PRAGMA query_only=ON')
        db.set_progress_handler(lambda: int(time.monotonic() - started >= seconds), 1000)
        try:
            cursor = db.execute('PRAGMA ' + check)
            row = cursor.fetchone()
            passed = row == ('ok',) and cursor.fetchone() is None if check == 'quick_check' else row is None
            if not passed:
                raise GateError('SQLite verification failed')
        finally:
            db.set_progress_handler(None, 0)
    return {'check': check, 'result': 'PASS', 'seconds': round(time.monotonic() - started, 3)}


def assert_quiescent(db, proc_root=Path('/proc')):
    targets = (db, Path(str(db) + '-wal'), Path(str(db) + '-shm'))
    identities = set()
    for target in targets:
        try:
            stat = target.stat()
            identities.add((stat.st_dev, stat.st_ino))
        except FileNotFoundError:
            pass
    for process in proc_root.iterdir():
        if not process.name.isdigit():
            continue
        try:
            for descriptor in (process / 'fd').iterdir():
                try:
                    stat = descriptor.stat()
                    if (stat.st_dev, stat.st_ino) in identities:
                        raise GateError('unexpected remaining SQLite owner')
                except FileNotFoundError:
                    pass
        except FileNotFoundError:
            pass
    wal = Path(str(db) + '-wal')
    if wal.exists() and wal.stat().st_size:
        raise GateError('WAL remains; no manual manipulation permitted')


def run_release(host, bundle, ci_sha, ci_run_id, budget=None):
    """Testable orchestration. All machine effects go through the host interface."""
    budget = budget or Budget()
    report = {'old_revision': OLD, 'candidate_revision': RELEASE, 'ci_run_id': ci_run_id,
              'status': 'preparing', 'phase': 'validate', 'collection_gap_authorized': True}
    stopped = set()
    changed = False
    def phase(name):
        report['phase'] = name
        report['stopped_units'] = sorted(stopped)
        host.save(report)
    try:
        if ci_sha != RELEASE or ci_run_id <= 0:
            raise GateError('exact-SHA CI acknowledgment missing')
        host.validate(bundle, budget)
        host.save(report)
        # Suspend the timer and any in-flight read-only sample before quiescence.
        stopped.update(MONITOR)
        phase('stop_monitor')
        host.stop(MONITOR, budget)
        phase('responsive_window')
        host.responsive_window(budget)
        # Stop the API immediately after an observed responsive window, before
        # waiting for background workers. Existing systemd stop policies apply.
        stopped.add(APPS[0])
        phase('stop_api')
        host.stop((APPS[0],), budget)
        stopped.update(APPS[1:])
        phase('stop_workers')
        host.stop(APPS[1:], budget)
        phase('quiescence')
        host.quiescent()
        phase('recovery_copy')
        copy = host.recovery_copy(budget)
        phase('verify_copy')
        report['checks'] = [host.check(copy, name, budget) for name in ('quick_check', 'foreign_key_check')]
        # No writers may have returned or changed the source during verification.
        host.quiescent()
        host.source_unchanged()
        phase('checkout')
        changed = True  # Partial checkout failures must also restore old code.
        host.checkout(RELEASE, budget)
        phase('start_and_validate')
        host.start(APPS, budget)
        host.smoke(budget)
        host.start((MONITOR[0],), budget)
        host.final_checks(budget)
        report['status'] = 'deployed_pending_I7_validation'
        report['phase'] = 'complete'
        host.save(report)
        return report
    except BaseException as error:
        report.update(status='STOP', error_type=type(error).__name__)
        if stopped:
            try:
                if changed:
                    host.stop(MONITOR + APPS, budget, recovery=True)
                    host.checkout(OLD, budget, recovery=True)
                host.restore(stopped, budget)
                report['recovery'] = host.recovery_status(budget)
            except BaseException as recovery_error:
                report['recovery'] = {'status': 'MANUAL_ACTION_REQUIRED', 'error_type': type(recovery_error).__name__}
        else:
            report['recovery'] = {'status': 'not_needed_no_service_stop'}
        host.save(report)
        return report


class Host:
    def __init__(self, ci_run_id):
        self.directory = None
        self.ci_run_id = ci_run_id
        self.original = None
        self.config = None

    def command(self, args, budget, cap=30, recovery=False, user=False):
        if user:
            args = ['sudo', '-u', 'tradebot', '--'] + list(args)
        return subprocess.run(args, cwd=ROOT, text=True, capture_output=True,
                              check=True, timeout=budget.seconds(cap, recovery)).stdout.strip()

    def git(self, args, budget, recovery=False):
        return self.command(['git'] + list(args), budget, recovery=recovery, user=True)

    @staticmethod
    def properties(unit):
        raw = subprocess.run(['systemctl', 'show', unit, '-p', 'ActiveState', '-p', 'SubState',
                              '-p', 'MainPID', '-p', 'NRestarts', '-p', 'Result', '-p', 'UnitFileState'],
                             text=True, capture_output=True, check=True, timeout=5).stdout
        return dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)

    @staticmethod
    def protected():
        p = ROOT / '.env'
        return (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mode & 0o777, p.stat().st_uid)

    @staticmethod
    def flags(pid, guard=False):
        environment = dict(item.split('=', 1) for item in Path('/proc', pid, 'environ').read_text().split('\0') if '=' in item)
        if any(environment.get(k) for k in ('OPENAI_API_KEY', 'OPENAPIKEY', 'OPENAI_KEY')):
            raise GateError('OpenAI credentials present')
        expected = {'ENABLE_OPENAI_ANALYST': 'false', 'ENABLE_LOCAL_RETENTION': 'false',
                    'ENABLE_SUPABASE_SYNC': 'true',
                    'ENABLE_CLOUD_LIFECYCLE': 'true'}
        if guard:
            expected['MAX_LOCAL_STORAGE_MB'] = '4096'
        if any(environment.get(k) != v for k, v in expected.items()):
            raise GateError('runtime flags changed')

    def validate(self, bundle, budget):
        import shutil
        if self.git(['rev-parse', 'HEAD'], budget) != OLD:
            raise GateError('production revision changed')
        if self.git(['status', '--porcelain', '--untracked-files=no'], budget):
            raise GateError('tracked production checkout not clean')
        self.original = {unit: self.properties(unit) for unit in APPS + MONITOR}
        for unit in APPS + (MONITOR[0],):
            if self.original[unit]['ActiveState'] != 'active' or self.original[unit]['UnitFileState'] != 'enabled':
                raise GateError('required unit not active/enabled')
        for unit in APPS:
            self.flags(self.original[unit]['MainPID'], guard=unit == APPS[0])
        self.config = self.protected()
        if self.config[1] != 0o600:
            raise GateError('configuration mode changed')
        self.check_config(budget)
        db = ROOT / 'data/btc_intelligence.db'
        if not db.is_file() or db.is_symlink():
            raise GateError('unexpected database path')
        if shutil.disk_usage(db.parent).free < 2 * db.stat().st_size + 2 * 1024**3:
            raise GateError('insufficient copy and recovery reserve')
        if self.git(['bundle', 'list-heads', str(bundle)], budget) != RELEASE + ' ' + BRANCH:
            raise GateError('unexpected bundle ref')
        self.git(['bundle', 'verify', str(bundle)], budget)
        self.git(['fetch', str(bundle), BRANCH], budget)
        if self.git(['rev-parse', 'FETCH_HEAD'], budget) != RELEASE:
            raise GateError('bundle revision mismatch')
        self.git(['merge-base', '--is-ancestor', OLD, RELEASE], budget)
        changes = set(self.git(['diff', '--name-only', OLD, RELEASE], budget).splitlines())
        if not changes or not changes <= ALLOWED or 'backend/app/streaming.py' not in changes:
            raise GateError('release scope changed')
        self.private_binding(budget)
        self.sole_collector(budget)

    def check_config(self, budget):
        # Validate the literal file that systemd will use at restart, not just
        # the old process environment. Inherited operator variables must not
        # mask an unsafe/missing file setting. No credential values are logged.
        program = ("import os,runpy,sys; sys.dont_write_bytecode=True; "
                   "sys.path.insert(0,'backend/app'); from run_api import load_local_env; "
                   "os.environ.clear(); load_local_env(); "
                   "assert os.environ.get('MAX_LOCAL_STORAGE_MB')=='4096'; "
                   "runpy.run_path('deploy/lightsail/preflight.py',run_name='__main__')")
        self.command([str(ROOT / '.venv/bin/python'), '-c', program], budget, cap=15, user=True)

    def sole_collector(self, budget, recovery=False):
        processes = self.command(['ps', '-u', 'tradebot', '-o', 'args='], budget, recovery=recovery).splitlines()
        if sum('backend/app/run_api.py' in line for line in processes) != 1:
            raise GateError('collector ownership is not singular')
        if any(any('backend/app/' + name in line for name in ('streaming.py', 'run_collector.py', 'dashboard.py')) for line in processes):
            raise GateError('competing collector/dashboard process')

    def private_binding(self, budget, recovery=False):
        lines = self.command(['ss', '-ltnH'], budget, recovery=recovery).splitlines()
        addresses = [line.split()[3] for line in lines if line.split()[3].endswith(':8000')]
        if addresses != ['127.0.0.1:8000']:
            raise GateError('API binding unavailable or not private')

    def save(self, report):
        from datetime import datetime, timezone
        if self.directory is None:
            self.directory = ROOT / 'data/deployments' / ('i7-maintenance-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
            self.directory.mkdir(mode=0o700)
        report['recorded_at'] = datetime.now(timezone.utc).isoformat()
        path = self.directory / 'report.json'
        path.write_text(json.dumps(report, indent=2) + '\n')
        path.chmod(0o600)
        events = self.directory / 'events.jsonl'
        with events.open('a') as output:
            events.chmod(0o600)
            output.write(json.dumps(report) + '\n')
        print(json.dumps(report), flush=True)

    def stop(self, units, budget, recovery=False):
        self.command(['systemctl', 'stop'] + list(units), budget, cap=150, recovery=recovery)
        for unit in units:
            state = self.properties(unit)
            if state['ActiveState'] != 'inactive' or int(state.get('MainPID', '0')):
                raise GateError('unit did not stop')
            if state.get('Result') not in (None, '', 'success'):
                raise GateError('unit shutdown was not clean')

    def responsive_window(self, budget):
        import urllib.request
        deadline = time.monotonic() + budget.seconds(180)
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2) as response:
                    payload = json.load(response)
                if payload.get('status') == 'ok' and payload.get('collector', {}).get('running'):
                    return
            except Exception:
                pass
            time.sleep(min(2, max(0, deadline - time.monotonic())))
        raise GateError('no responsive API stop window')

    def quiescent(self):
        assert_quiescent(ROOT / 'data/btc_intelligence.db')

    @staticmethod
    def identity(path):
        s = path.stat()
        return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)

    def recovery_copy(self, budget):
        source = ROOT / 'data/btc_intelligence.db'
        self.source_identity = self.identity(source)
        copy = self.directory / 'recovery.db'
        deadline = time.monotonic() + budget.seconds(120)
        digest = hashlib.sha256()
        with source.open('rb') as inp, copy.open('xb') as out:
            copy.chmod(0o600)
            while block := inp.read(1024 * 1024):
                if time.monotonic() >= deadline:
                    raise GateError('recovery copy deadline')
                digest.update(block)
                out.write(block)
            out.flush()
            os.fsync(out.fileno())
        deadline = time.monotonic() + budget.seconds(120)
        verified = hashlib.sha256()
        with copy.open('rb') as inp:
            while block := inp.read(1024 * 1024):
                if time.monotonic() >= deadline:
                    raise GateError('copy readback deadline')
                verified.update(block)
        self.source_unchanged()
        if digest.digest() != verified.digest() or source.stat().st_size != copy.stat().st_size:
            raise GateError('copy identity mismatch')
        (self.directory / 'recovery-sha256.txt').write_text(verified.hexdigest() + '\n')
        return copy

    def source_unchanged(self):
        if self.identity(ROOT / 'data/btc_intelligence.db') != self.source_identity:
            raise GateError('quiesced source changed')

    def check(self, copy, name, budget):
        seconds = max(1, int(budget.seconds(420)) - 3)
        # Child reads only the immutable copy. subprocess.run kills/reaps it on
        # timeout, so cancellation cannot leave an unbounded SQLite reader.
        output = self.command([sys.executable, str(Path(__file__).resolve()), '--check-copy', str(copy),
                               '--check', name, '--seconds', str(seconds)], budget, cap=seconds + 2)
        return json.loads(output)

    def checkout(self, revision, budget, recovery=False):
        self.git(['checkout', '--detach', revision], budget, recovery=recovery)

    def start(self, units, budget, recovery=False):
        for unit in units:
            self.command(['systemctl', 'start', unit], budget, cap=45, recovery=recovery)

    def smoke(self, budget):
        self.command(['python3', '/usr/local/lib/tradebot-cd/smoke.py', '--attempts', '24'], budget, cap=180, user=True)

    def final_checks(self, budget):
        if self.protected() != self.config:
            raise GateError('protected configuration changed')
        self.private_binding(budget)
        self.sole_collector(budget)
        first = {unit: self.properties(unit) for unit in APPS}
        for unit, state in first.items():
            if state['ActiveState'] != 'active' or state['UnitFileState'] != 'enabled':
                raise GateError('service not active')
            self.flags(state['MainPID'], guard=unit == APPS[0])
        time.sleep(min(5, budget.seconds(5)))
        if any(self.properties(unit)['MainPID'] != state['MainPID'] or self.properties(unit)['NRestarts'] != state['NRestarts'] for unit, state in first.items()):
            raise GateError('unstable service process')
        if self.properties(MONITOR[0])['ActiveState'] != 'active':
            raise GateError('monitor timer not restored')

    def restore(self, stopped, budget):
        for unit in APPS + (MONITOR[0],):
            if unit in stopped and self.original[unit]['ActiveState'] == 'active':
                self.start((unit,), budget, recovery=True)

    def recovery_status(self, budget):
        states = {unit: self.properties(unit) for unit in APPS + (MONITOR[0],)}
        if any(state['ActiveState'] != 'active' for state in states.values()):
            raise GateError('service restoration incomplete')
        if self.protected() != self.config:
            raise GateError('configuration changed during recovery')
        self.private_binding(budget, recovery=True)
        self.sole_collector(budget, recovery=True)
        for unit in APPS:
            self.flags(states[unit]['MainPID'], guard=unit == APPS[0])
        return {'status': 'services_restored', 'api_health': 'not_certified_original_stall_unresolved',
                'revision': self.git(['rev-parse', 'HEAD'], budget, recovery=True)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--execute', action='store_true')
    parser.add_argument('--confirm-collection-gap', action='store_true')
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--ci-verified-sha')
    parser.add_argument('--ci-run-id', type=int, default=0)
    mode.add_argument('--check-copy', type=Path)
    parser.add_argument('--check', choices=('quick_check', 'foreign_key_check'))
    parser.add_argument('--seconds', type=int, default=420)
    args = parser.parse_args()
    if args.execute:
        parser.error('WITHDRAWN: database-copy maintenance is not authorized; use the exact-release I7 procedure')
    if args.check_copy:
        if not args.check or not 1 <= args.seconds <= 420:
            parser.error('bounded check required')
        print(json.dumps(verify_copy(args.check_copy, args.check, args.seconds)))
        return
    if not args.execute:
        print(json.dumps({'mode': 'PLAN_ONLY', 'candidate': RELEASE, 'expected_old': OLD,
                          'maximum_minutes': 25, 'recovery_reserve_minutes': 5,
                          'requires': 'separate maintenance approval and fresh trusted-operator exact-SHA CI verification'}))
        return
    if os.geteuid() != 0 or not args.confirm_collection_gap or not args.bundle:
        parser.error('root operator, approved collection gap and verified bundle required')
    def interrupted(signum, frame):
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(sig, signal.SIG_IGN)
        raise GateError('operator interrupted maintenance')
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, interrupted)
    with open('/run/lock/tradebot-deploy.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        report = run_release(Host(args.ci_run_id), args.bundle.resolve(), args.ci_verified_sha, args.ci_run_id)
    raise SystemExit(0 if report['status'] == 'deployed_pending_I7_validation' else 1)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'status': 'STOP', 'error_type': type(error).__name__}), flush=True)
        raise SystemExit(1)
