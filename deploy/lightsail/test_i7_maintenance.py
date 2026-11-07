"""Maintenance failure/recovery invariants; no production, network or service calls."""
import importlib.util
import ast
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('i7_maintenance', Path(__file__).with_name('i7_maintenance.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class FakeHost:
    def __init__(self, fail=None):
        self.fail = fail
        self.events = []
        self.records = []

    def event(self, name, *args):
        self.events.append((name,) + args)
        if self.fail == name:
            self.fail = None
            raise RuntimeError('simulated failure')

    def validate(self, bundle, budget): self.event('validate')
    def save(self, report): self.records.append(json.loads(json.dumps(report)))
    def stop(self, units, budget, recovery=False): self.event('stop', tuple(units), recovery)
    def responsive_window(self, budget): self.event('responsive_window')
    def quiescent(self): self.event('quiescent')
    def recovery_copy(self, budget): self.event('copy'); return Path('verified-copy.db')
    def source_unchanged(self): self.event('source_unchanged')
    def check(self, copy, name, budget):
        self.event(name)
        return {'check': name, 'result': 'PASS'}
    def checkout(self, revision, budget, recovery=False): self.event('checkout_' + revision, recovery)
    def start(self, units, budget, recovery=False): self.event('start', tuple(units), recovery)
    def smoke(self, budget): self.event('smoke')
    def final_checks(self, budget): self.event('final_checks')
    def restore(self, stopped, budget): self.event('restore', tuple(sorted(stopped)))
    def recovery_status(self, budget): self.event('recovery_status'); return {'status': 'services_restored', 'api_health': 'not_certified'}


class MaintenanceTests(unittest.TestCase):
    def run_release(self, host):
        return m.run_release(host, Path('input.bundle'), m.RELEASE, 41138048640)

    def test_success_requires_both_full_checks_and_source_recheck_before_checkout(self):
        host = FakeHost()
        result = self.run_release(host)
        events = [e[0] for e in host.events]
        self.assertEqual(result['status'], 'deployed_pending_I7_validation')
        self.assertLess(events.index('quick_check'), events.index('foreign_key_check'))
        self.assertLess(events.index('foreign_key_check'), events.index('source_unchanged'))
        self.assertLess(events.index('source_unchanged'), events.index('checkout_' + m.RELEASE))
        self.assertNotIn('restore', events)
        self.assertEqual(host.events[1], ('stop', m.MONITOR, False))
        self.assertEqual([e for e in host.events if e[0] == 'stop'][1][1], (m.APPS[0],))

    def test_wrong_ci_cannot_stop_services(self):
        host = FakeHost()
        result = m.run_release(host, Path('input.bundle'), '0' * 40, 1)
        self.assertEqual(result['status'], 'STOP')
        self.assertEqual(host.events, [])

    def test_invalid_bundle_or_runtime_never_enters_maintenance(self):
        host = FakeHost('validate')
        result = self.run_release(host)
        self.assertEqual(result['recovery']['status'], 'not_needed_no_service_stop')
        self.assertFalse(any(e[0] in ('stop', 'checkout_' + m.RELEASE) for e in host.events))

    def test_no_responsive_window_restores_monitor_only(self):
        host = FakeHost('responsive_window')
        result = self.run_release(host)
        restored = next(e[1] for e in host.events if e[0] == 'restore')
        self.assertEqual(set(restored), set(m.MONITOR))
        self.assertEqual(result['phase'], 'responsive_window')

    def test_failed_or_timed_out_checks_cannot_checkout(self):
        for check in ('quick_check', 'foreign_key_check'):
            with self.subTest(check=check):
                host = FakeHost(check)
                result = self.run_release(host)
                self.assertEqual(result['status'], 'STOP')
                self.assertFalse(any(e[0].startswith('checkout_') for e in host.events))
                self.assertTrue(any(e[0] == 'restore' for e in host.events))

    def test_unexpected_owner_or_source_change_prevents_checkout(self):
        for failure in ('quiescent', 'source_unchanged', 'copy'):
            with self.subTest(failure=failure):
                host = FakeHost(failure)
                self.run_release(host)
                self.assertFalse(any(e[0].startswith('checkout_') for e in host.events))

    def test_partial_stop_failure_still_attempts_restoration(self):
        host = FakeHost('stop')
        result = self.run_release(host)
        self.assertEqual(result['status'], 'STOP')
        self.assertTrue(any(e[0] == 'restore' for e in host.events))

    def test_smoke_failure_stops_new_processes_and_restores_old_code(self):
        host = FakeHost('smoke')
        result = self.run_release(host)
        self.assertEqual(result['status'], 'STOP')
        events = [e[0] for e in host.events]
        self.assertIn('checkout_' + m.OLD, events)
        self.assertLess(events.index('checkout_' + m.OLD), events.index('restore'))
        stops = [e for e in host.events if e[0] == 'stop']
        self.assertEqual(stops[-1], ('stop', m.MONITOR + m.APPS, True))
        self.assertEqual(result['recovery']['api_health'], 'not_certified')

    def test_partial_checkout_failure_also_restores_old_code(self):
        host = FakeHost('checkout_' + m.RELEASE)
        self.run_release(host)
        self.assertTrue(any(e[0] == 'checkout_' + m.OLD for e in host.events))

    def test_recovery_failure_is_manual_action_not_success(self):
        class RecoveryFailure(FakeHost):
            def restore(self, stopped, budget): raise RuntimeError('recovery failure')
        result = self.run_release(RecoveryFailure('quick_check'))
        self.assertEqual(result['recovery']['status'], 'MANUAL_ACTION_REQUIRED')

    def test_interrupt_after_stop_uses_recovery_path(self):
        class Interrupted(FakeHost):
            def quiescent(self): raise KeyboardInterrupt()
        host = Interrupted()
        result = self.run_release(host)
        self.assertEqual(result['error_type'], 'KeyboardInterrupt')
        self.assertTrue(any(e[0] == 'restore' for e in host.events))

    def test_recovery_reserve_cannot_be_used_by_normal_work(self):
        now = [0]
        budget = m.Budget(clock=lambda: now[0])
        now[0] = 1201
        with self.assertRaises(m.GateError): budget.seconds(30)
        self.assertEqual(budget.seconds(420, recovery=True), 299)
        now[0] = 1501
        with self.assertRaises(m.GateError): budget.seconds(30, recovery=True)

    def test_default_cli_is_plan_only(self):
        output = subprocess.check_output([sys.executable, str(Path(m.__file__))], text=True)
        self.assertEqual(json.loads(output)['mode'], 'PLAN_ONLY')

    def test_sqlite_copy_checks_reject_real_foreign_key_violations(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'copy.db'
            with sqlite3.connect(path) as db:
                db.executescript('CREATE TABLE parent(id INTEGER PRIMARY KEY); CREATE TABLE child(parent_id REFERENCES parent(id)); INSERT INTO child VALUES(42);')
            before = path.read_bytes()
            self.assertEqual(m.verify_copy(path, 'quick_check', 5)['result'], 'PASS')
            with self.assertRaises(m.GateError): m.verify_copy(path, 'foreign_key_check', 5)
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(Path(str(path) + '-wal').exists())

    def test_corrupt_copy_is_not_a_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'copy.db'
            path.write_bytes(b'not a SQLite database' * 100)
            with self.assertRaises(sqlite3.DatabaseError): m.verify_copy(path, 'quick_check', 5)

    def test_read_only_valid_copy_passes_both_checks_without_sidecars(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'copy.db'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE evidence(id INTEGER PRIMARY KEY, value TEXT)')
                db.execute('INSERT INTO evidence VALUES(1,?)', ('exact: 101.250000',))
            before = path.read_bytes()
            for name in ('quick_check', 'foreign_key_check'):
                self.assertEqual(m.verify_copy(path, name, 5)['result'], 'PASS')
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(sorted(p.name for p in path.parent.iterdir()), ['copy.db'])

    def test_command_deadline_kills_and_reaps_its_child(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(m, 'ROOT', Path(folder)):
            marker = Path(folder) / 'child-pid'
            program = 'import os,time; from pathlib import Path; Path(' + repr(str(marker)) + ').write_text(str(os.getpid())); time.sleep(10)'
            with self.assertRaises(subprocess.TimeoutExpired):
                m.Host(1).command([sys.executable, '-c', program], m.Budget(), cap=0.3)
            self.assertTrue(marker.exists())
            pid = int(marker.read_text())
            with self.assertRaises(ProcessLookupError): os.kill(pid, 0)

    def test_restart_config_cannot_be_masked_by_inherited_operator_values(self):
        repo = Path(__file__).resolve().parents[2]
        source = (repo / 'backend/app/run_api.py').read_text()
        loader = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == 'load_local_env')
        loader_source = 'import os\nfrom pathlib import Path\n' + ast.get_source_segment(source, loader)
        settings = {'ENABLE_OPENAI_ANALYST': 'false', 'ENABLE_LOCAL_RETENTION': 'false',
                    'ENABLE_SUPABASE_SYNC': 'true', 'ENABLE_CLOUD_LIFECYCLE': 'true',
                    'FASTAPI_HOST': '127.0.0.1', 'FASTAPI_PORT': '8000', 'FASTAPI_RELOAD': 'false',
                    'SQLITE_DB_PATH': 'data/btc_intelligence.db', 'MAX_LOCAL_STORAGE_MB': '4096',
                    'SUPABASE_URL': 'fixture-url', 'SUPABASE_SECRET_KEY': 'fixture-only',
                    'POLYMARKET_KEY_ID': 'fixture-id', 'POLYMARKET_SECRET_KEY': 'fixture-only'}
        class LocalHost(m.Host):
            def command(self, args, budget, cap=30, recovery=False, user=False):
                return super().command(args, budget, cap, recovery, user=False)
        with tempfile.TemporaryDirectory() as folder, patch.object(m, 'ROOT', Path(folder)):
            root = Path(folder)
            for directory in ('backend/app', 'deploy/lightsail', '.venv/bin', 'data'):
                (root / directory).mkdir(parents=True)
            (root / 'backend/app/run_api.py').write_text(loader_source)
            (root / 'deploy/lightsail/preflight.py').write_text((repo / 'deploy/lightsail/preflight.py').read_text())
            (root / '.venv/bin/python').symlink_to(sys.executable)
            (root / 'data/btc_intelligence.db').touch()
            def write(values):
                (root / '.env').write_text(''.join(k + '=' + v + '\n' for k, v in values.items()))
            write(settings)
            LocalHost(1).check_config(m.Budget())
            write(dict(settings, MAX_LOCAL_STORAGE_MB='2048'))
            with patch.dict(os.environ, {'MAX_LOCAL_STORAGE_MB': '4096'}), self.assertRaises(subprocess.CalledProcessError):
                LocalHost(1).check_config(m.Budget())
            write(dict(settings, OPENAI_API_KEY='fixture-not-a-real-key'))
            with self.assertRaises(subprocess.CalledProcessError):
                LocalHost(1).check_config(m.Budget())

    def test_owner_check_detects_an_alias_to_the_same_inode(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            db = root / 'source.db'
            db.touch()
            alias = root / 'same-db-another-name'
            os.link(db, alias)
            descriptor = root / 'proc/123/fd/4'
            descriptor.parent.mkdir(parents=True)
            descriptor.symlink_to(alias)
            with self.assertRaisesRegex(m.GateError, 'remaining SQLite owner'):
                m.assert_quiescent(db, root / 'proc')
            descriptor.unlink()
            m.assert_quiescent(db, root / 'proc')

    def test_quiescence_refuses_wal_without_modifying_it(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            db = root / 'source.db'
            db.touch()
            wal = Path(str(db) + '-wal')
            wal.write_bytes(b'preserved WAL evidence')
            (root / 'proc').mkdir()
            with self.assertRaisesRegex(m.GateError, 'WAL remains'):
                m.assert_quiescent(db, root / 'proc')
            self.assertEqual(wal.read_bytes(), b'preserved WAL evidence')


if __name__ == '__main__':
    unittest.main()
