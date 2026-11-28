"""Exercise authenticated local roles and the real public API on disposable PostgreSQL."""

import asyncio
from contextlib import ExitStack
from threading import Event
from unittest.mock import patch
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_postgres_trial07_permit as fixture
from postgres.config import Settings
from postgres.connection import EnvironmentMismatch, connect
from postgres.dashboard_reader import WatchDashboardStore
from postgres.feed_controls import ORIGIN
from postgres.history import HistoryError


class WatchDashboardReader(unittest.TestCase):
    require_migration_ledger = True
    setup = fixture.Trial07Permit
    setUpClass = setup.__dict__['setUpClass']
    tearDownClass = setup.__dict__['tearDownClass']
    admin = setup.__dict__['admin']

    def setUp(self):
        dsn = (os.environ['TRADEBOT_TEST_READER_DSN'] if self.external
               else f'host={self.socket} user=tradebot_reader dbname=tradebot_pp')
        self.settings = Settings(data_mode='pp_live', origin_id=ORIGIN, dsn=dsn)

    def test_real_roles_limit_two_restart_transactions_and_release_on_error(self):
        import psycopg
        store = WatchDashboardStore(self.settings)
        store.verify()
        with store.connection(True) as one, store.connection(True) as two:
            # The first SQL statement may choose the snapshot used across A/B.
            two.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            self.assertEqual(two.execute(
                "SELECT session_user AS login, current_setting('transaction_read_only') AS mode"
            ).fetchone(), {'login':'tradebot_reader', 'mode':'on'})
            with self.assertRaises(HistoryError) as error:
                with store.connection(True):
                    self.fail('third DB session admitted')
            self.assertEqual(error.exception.code,'history_busy')
            with self.assertRaises(psycopg.errors.ReadOnlySqlTransaction):
                one.execute("DELETE FROM ops.writer_state WHERE false")
        with connect(self.settings.dsn, readonly=False) as db:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                db.execute('DELETE FROM ops.writer_state WHERE false')
        with self.assertRaises(EnvironmentMismatch):
            with store.connection(False):
                self.fail('writable connection admitted')
        wrong_login = WatchDashboardStore(replace(self.settings, dsn=self.app_dsn))
        for _ in range(3):
            with self.assertRaisesRegex(EnvironmentMismatch, 'database login'):
                with wrong_login.connection(True):
                    self.fail('writer login admitted')

    def test_history_admission_is_bounded_while_in_memory_view_remains_responsive(self):
        from fastapi.testclient import TestClient
        from postgres.api import create_app
        store = WatchDashboardStore(self.settings)
        with TestClient(create_app(settings=self.settings, store=store, refresh=False)) as client:
            now = datetime.now(timezone.utc)
            window = dict(market_id='reader-load', start=(now-timedelta(minutes=5)).isoformat(),
                          end=now.isoformat(), as_of=now.isoformat(), limit=500)
            with store.connection(True), store.connection(True):
                response = client.get('/history/market-events',params=window)
                self.assertEqual(response.status_code,429,response.text)
                self.assertEqual(response.json()['detail']['code'],'history_busy')
                self.assertEqual(client.get('/state/current').status_code,200)
                with connect(self.app_dsn) as app:
                    self.assertEqual(app.execute('SELECT session_user AS login').fetchone()['login'],
                                     'tradebot_app')
            self.assertEqual(client.get('/history/market-events',params=window).status_code,200)

    def test_process_budgets_hold_until_physical_close_and_leave_ownership_capacity(self):
        from postgres.feed_writer import _Session
        from postgres.operator_runtime import _owner_reader
        from postgres.watch_connections import LocalAdmissionBusy, SessionBudget, WatchCalculationStore, WatchOperatorStore

        settings = replace(self.settings,dsn=self.app_dsn)
        writes = SessionBudget(self.app_dsn, 'tradebot_app', 6)
        private = SessionBudget(self.settings.dsn, 'tradebot_reader', 1)
        operator = WatchOperatorStore(settings,writes,private)
        source = operator.for_producer('fenced-test-owner')
        calculation = WatchCalculationStore(settings)
        api = WatchDashboardStore(self.settings)
        with ExitStack() as stack:
            pids = set()
            for _ in range(4):
                feed = _Session(source)
                stack.callback(feed.close)
                with feed.transaction() as db:
                    pids.add(db.info.backend_pid)
            for store in (operator,source,calculation,calculation):
                pids.add(stack.enter_context(store.connection()).info.backend_pid)
            self.assertEqual(len(pids),8)
            with self.assertRaises(LocalAdmissionBusy):
                writes.open(readonly=False,wait=0)
            with self.assertRaises(LocalAdmissionBusy):
                calculation._slots.open(readonly=True,wait=0)
            for _ in range(2):
                stack.enter_context(api.connection(True))
            with connect(self.settings.dsn, readonly=True) as diagnostic:
                self.assertEqual(diagnostic.info.user,'tradebot_reader')
                self.assertEqual(diagnostic.execute('SHOW max_connections').fetchone()['max_connections'],'20')
                self.assertEqual(diagnostic.execute('SHOW superuser_reserved_connections').fetchone()['superuser_reserved_connections'],'3')
                self.assertFalse(_owner_reader(None, reader=private).collector_state(ORIGIN)['collector_enabled'])
                with operator.connection(True) as check:
                    self.assertEqual(check.info.user,'tradebot_reader')
                    with self.assertRaises(LocalAdmissionBusy):
                        private.open(readonly=True,wait=0)
        with source.connection() as db:
            self.assertEqual(db.info.user,'tradebot_app')

    def test_reader_timeout_cancel_and_failed_commit_release_only_after_close(self):
        from postgres.watch_connections import LocalAdmissionBusy, SessionBudget
        import psycopg

        budget = SessionBudget(self.settings.dsn,'tradebot_reader',1)
        entered, finish, exited = Event(), Event(), Event()
        def blocking():
            try:
                with budget.open(readonly=True) as db:
                    db.execute('SELECT 1')
                    entered.set()
                    if not finish.wait(5):
                        raise TimeoutError('fixture stalled')
            finally:
                exited.set()
        async def cancel():
            task = asyncio.create_task(asyncio.to_thread(blocking))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait,3))
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                with self.assertRaises(LocalAdmissionBusy):
                    budget.open(readonly=True,wait=0)
            finally:
                finish.set()
                await asyncio.to_thread(exited.wait,3)
        asyncio.run(cancel())
        db = budget.open(readonly=True)
        with patch.object(type(db),'commit',side_effect=psycopg.OperationalError('fixture commit failure')):
            with self.assertRaises(psycopg.OperationalError):
                with db:
                    db.execute('SELECT 1')
        self.assertTrue(db.closed)
        db.close()
        with budget.open(readonly=True,wait=0):
            with self.assertRaises(LocalAdmissionBusy):
                budget.open(readonly=True,wait=0)

    def test_public_history_and_chart_while_application_login_is_at_capacity(self):
        import psycopg
        from fastapi.testclient import TestClient
        from postgres.api import create_app
        # Exclusively owned PG17 instance can exhaust the role. CI's shared
        # generated project runs other application-role services alongside us.
        with ExitStack() as held:
            if not self.external:
                for _ in range(8):
                    held.enter_context(connect(self.app_dsn, readonly=True))
                with self.assertRaises(psycopg.OperationalError):
                    connect(self.app_dsn, readonly=True)
            with TestClient(create_app(settings=self.settings, refresh=False)) as client:
                now = datetime.now(timezone.utc)
                window = dict(market_id='reader-fixture', start=(now-timedelta(minutes=5)).isoformat(),
                              end=now.isoformat(), as_of=now.isoformat(), limit=500)
                for name in ('market-events','market-predictions'):
                    response = client.get('/history/'+name, params=window)
                    self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(client.get('/history/predictions').status_code,200)
                self.assertEqual(client.get('/history/coinbase-chart').status_code,200)
