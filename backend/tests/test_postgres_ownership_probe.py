"""Native phase attribution and sanitized diagnostics, never a live host."""
import asyncio
import json
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_postgres_trial07_permit as fixture
from psycopg.errors import QueryCanceled
from postgres.connection import connect
from postgres.ownership_probe import OwnershipProbe, phase, submit_ownership
from postgres.watch_connections import SessionBudget


class OwnershipDiagnostics(unittest.TestCase):
    def test_fixed_diagnostic_fields_do_not_copy_callback_exception_text(self):
        private = 'Bearer-private-fixture-not-for-logging'
        probe = OwnershipProbe()
        async def fail():
            try:
                await submit_ownership(lambda: (_ for _ in ()).throw(ValueError(private)), probe)
            except ValueError:
                probe.report('error')
        with self.assertLogs('postgres.ownership_probe', 'WARNING') as logs:
            asyncio.run(fail())
        self.assertNotIn(private, '\n'.join(logs.output))
        record = json.loads(logs.output[-1].split('pp_ownership_check ', 1)[1])
        self.assertEqual(record['outcome'], 'error')
        self.assertTrue(record['worker_finished'])
        self.assertLess(len(json.dumps(record)), 1024)
        with self.assertRaises(ValueError):
            probe.mark(private)
        with self.assertRaises(ValueError):
            probe.report(private)


class NativeOwnershipPhases(unittest.TestCase):
    require_migration_ledger = True
    setup = fixture.Trial07Permit
    setUpClass = setup.__dict__['setUpClass']
    tearDownClass = setup.__dict__['tearDownClass']
    admin = setup.__dict__['admin']

    def setUp(self):
        dsn = (os.environ['TRADEBOT_TEST_READER_DSN'] if self.external
               else f'host={self.socket} user=tradebot_reader dbname=tradebot_pp')
        self.budget = SessionBudget(dsn, 'tradebot_reader', 1)

    def test_connect_environment_query_and_close_are_measured_independently(self):
        from postgres import connection
        original_validate = connection.validate_environment
        probe = OwnershipProbe()
        def delayed_connect(*args, **kwargs):
            phase('connect')
            time.sleep(.03)
            return connect(*args, **kwargs)
        def delayed_environment(*args, **kwargs):
            time.sleep(.03)
            return original_validate(*args, **kwargs)
        def check():
            with self.budget.open(readonly=True) as db:
                phase('query')
                row = db.execute('SELECT pg_sleep(0.03), current_setting(\'transaction_read_only\') AS mode').fetchone()
                return row['mode'] == 'on'
        async def run():
            self.assertIs(await submit_ownership(check, probe), True)
        with patch('postgres.watch_connections.connect', delayed_connect), \
             patch('postgres.connection.validate_environment', delayed_environment):
            asyncio.run(run())
        self.assertGreaterEqual(probe.times['connect'], .025)
        self.assertGreaterEqual(probe.times['environment'], .025)
        self.assertGreaterEqual(probe.times['query'], .025)
        self.assertIn('close', probe.times)
        # The single physical reader is returned after close, including success.
        with self.budget.open(readonly=True, wait=0) as db:
            self.assertTrue(db.read_only)

    def test_native_statement_cancellation_has_separate_outcome_and_releases_reader(self):
        probe = OwnershipProbe()
        def slow_sql():
            with self.budget.open(readonly=True) as db:
                db.execute("SET LOCAL statement_timeout='25ms'")
                phase('query')
                db.execute('SELECT pg_sleep(1)')
        async def run():
            with self.assertRaises(QueryCanceled):
                await submit_ownership(slow_sql, probe)
            probe.report('sql_cancelled')
        with self.assertLogs('postgres.ownership_probe', 'WARNING') as logs:
            asyncio.run(run())
        record = json.loads(logs.output[-1].split('pp_ownership_check ', 1)[1])
        self.assertEqual(record['outcome'], 'sql_cancelled')
        self.assertGreaterEqual(record['phase_ms']['query'], 20)
        with self.budget.open(readonly=True, wait=0) as db:
            self.assertEqual(db.execute('SELECT 1 AS n').fetchone()['n'], 1)
