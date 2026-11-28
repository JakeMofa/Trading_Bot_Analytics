"""Serial physical reader reuse, fresh ownership, priority, cancellation and cleanup on PG17."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import os
from pathlib import Path
import sys
from threading import Event
from time import monotonic, sleep
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import patch

import psycopg
from psycopg.pq import TransactionStatus

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / 'tests'))
import test_postgres_trial07_permit as fixture
from postgres.feed_controls import desired_feeds
from postgres.lifecycle import LifecycleRepository
from postgres.ownership_probe import OwnershipProbe, is_ownership_check
from postgres.shared_read_connection import SharedReadConnection
from postgres.watch_connections import LocalAdmissionBusy, SessionBudget


class NativeSharedReader(unittest.TestCase):
    require_migration_ledger = True
    native = fixture.Trial07Permit
    setUpClass = native.__dict__['setUpClass']
    tearDownClass = native.__dict__['tearDownClass']
    admin = native.__dict__['admin']

    def setUp(self):
        dsn = (os.environ['TRADEBOT_TEST_READER_DSN'] if self.external
               else f'host={self.socket} user=tradebot_reader dbname=tradebot_pp')
        self.physical = SessionBudget(dsn, 'tradebot_reader', 1)
        self.reader = SharedReadConnection(self.physical)
        self.addCleanup(self.reader.close)

    def backend_pid(self):
        with self.reader.open(readonly=True) as db:
            row = db.execute("""SELECT pg_backend_pid() AS pid,current_user AS login,
                current_setting('transaction_read_only') AS mode""").fetchone()
            self.assertEqual((row['login'], row['mode']), ('tradebot_reader', 'on'))
            return row['pid']

    @contextmanager
    def seeded_writer(self):
        origin = 'pp-live-generated-reader-' + uuid.uuid4().hex[:12]
        gen, session = str(uuid.uuid4()), str(uuid.uuid4())
        with self.admin() as db:
            db.execute("""INSERT INTO archive.generations(origin_id,generation_id,slot,state,
                partition_name,created_at,started_at) VALUES (%s,%s,'A','collecting',%s,now(),now())""",
                (origin, gen, 'events_g_' + gen.replace('-', '')))
            db.execute("""INSERT INTO ops.writer_state(origin_id,generation_id,epoch,updated_at,collector_enabled,
                collector_session_id,collector_lease_expires_at) VALUES(%s,%s,1,now(),TRUE,%s,now()+interval '1 hour')""",
                (origin, gen, session))
        try:
            yield origin, gen, session
        finally:
            with self.admin() as db:
                db.execute('DELETE FROM ops.writer_state WHERE origin_id=%s', (origin,))
                db.execute('DELETE FROM archive.generations WHERE origin_id=%s', (origin,))

    def test_same_pid_reads_new_uuid_expiry_and_off_and_ends_idle(self):
        pid = self.backend_pid()
        repository = LifecycleRepository(lambda: self.reader.open(readonly=True))
        with self.seeded_writer() as (origin, _, session):
            stale = str(uuid.uuid4())
            self.assertFalse(repository.owns_collector(origin, stale))
            self.assertTrue(repository.owns_collector(origin, session))
            with self.admin() as db:
                db.execute('UPDATE ops.writer_state SET collector_session_id=%s WHERE origin_id=%s', (stale, origin))
            self.assertFalse(repository.owns_collector(origin, session))
            self.assertTrue(repository.owns_collector(origin, stale))
            with self.admin() as db:
                db.execute("UPDATE ops.writer_state SET collector_lease_expires_at=now()-interval '1s' WHERE origin_id=%s", (origin,))
            self.assertFalse(repository.owns_collector(origin, stale))
            with self.admin() as db:
                db.execute("""UPDATE ops.writer_state SET collector_enabled=FALSE,collector_session_id=NULL,
                    collector_lease_expires_at=NULL WHERE origin_id=%s""", (origin,))
            self.assertFalse(repository.collector_state(origin)['collector_enabled'])
            self.assertFalse(repository.owns_collector(origin, stale))
        self.assertEqual(self.backend_pid(), pid)
        self.assertEqual(self.reader._db.info.transaction_status, TransactionStatus.IDLE)
        with self.assertRaises(LocalAdmissionBusy):
            self.physical.open(readonly=True, wait=0)

    def test_real_preferences_and_status_yield_next_transaction_to_waiting_owner(self):
        with self.seeded_writer() as (origin, _, session), patch('postgres.feed_controls.ORIGIN', origin):
            store = SimpleNamespace(origin=origin, settings=SimpleNamespace(environment='preprod',data_mode='pp_live'),
                                    connection=lambda _readonly: self.reader.open(readonly=True))
            order = []
            def open_reader():
                handle = self.reader.open(readonly=True)
                order.append('owner' if is_ownership_check() else 'optional')
                return handle
            repository = LifecycleRepository(open_reader)
            def prefs():
                selected = desired_feeds(store)
                order.append('preferences')
                return selected
            with ThreadPoolExecutor(max_workers=4) as threads:
                with self.reader.open(readonly=True) as hold:
                    self.assertEqual(hold.execute('SELECT 1 AS n').fetchone()['n'], 1)
                    status = threads.submit(repository.collector_state, origin)
                    preferences = threads.submit(prefs)
                    probe = OwnershipProbe()
                    owner = threads.submit(probe.worker, lambda: repository.owns_collector(origin,session), probe.submitted())
                    until = monotonic() + .15
                    while monotonic() < until:
                        with self.reader._condition:
                            if self.reader._waiting == {True:1,False:2}:
                                break
                        sleep(.001)
                    self.assertEqual(self.reader._waiting, {True:1,False:2})
                    with self.assertRaises(LocalAdmissionBusy):
                        self.reader.open(readonly=True,wait=0)
                self.assertTrue(owner.result(2))
                self.assertTrue(status.result(2)['collector_enabled'])
                self.assertTrue(all(preferences.result(2).values()))
            self.assertEqual(order[0], 'owner')

    def test_error_server_timeout_and_lost_session_return_fresh_physical_pid(self):
        pid = self.backend_pid()
        with self.assertRaises(psycopg.errors.DivisionByZero):
            with self.reader.open(readonly=True) as db:
                db.execute('SELECT 1/0')
        new = self.backend_pid()
        self.assertNotEqual(pid, new)
        with self.assertRaises(psycopg.errors.QueryCanceled):
            with self.reader.open(readonly=True) as db:
                db.execute('SELECT pg_sleep(1)')
        after_cancel = self.backend_pid()
        self.assertNotEqual(new, after_cancel)
        # Simulate observed native connection loss between transactions.
        self.reader._db.close()
        self.assertNotEqual(self.backend_pid(), after_cancel)

    def test_server_terminated_idle_pid_is_replaced_before_application_sql(self):
        pid = self.backend_pid()
        # PostgreSQL permits a role to signal its own backends; no production
        # privileges or superuser-only fixture are needed. This separate
        # test-only control connection is closed before opening the next borrow.
        dsn = (os.environ['TRADEBOT_TEST_READER_DSN'] if self.external
               else f'host={self.socket} user=tradebot_reader dbname=tradebot_pp')
        with psycopg.connect(dsn) as signaler:
            self.assertTrue(signaler.execute('SELECT pg_terminate_backend(%s,1000)',(pid,)).fetchone()[0])
        with patch.object(self.physical, 'open', wraps=self.physical.open) as connections:
            new = self.backend_pid()
        self.assertEqual(connections.call_count, 1)
        self.assertNotEqual(pid, new)
        self.assertEqual(self.backend_pid(), new)

    def test_connection_loss_during_caller_sql_does_not_replay(self):
        pid = self.backend_pid()
        with patch.object(self.physical, 'open', wraps=self.physical.open) as connections:
            with self.assertRaises(psycopg.OperationalError):
                with self.reader.open(readonly=True) as db:
                    # Server disconnect during caller SQL, with a cached PID.
                    db.execute('SELECT pg_terminate_backend(pg_backend_pid())')
        self.assertEqual(connections.call_count, 0)
        self.assertIsNone(self.reader._db)
        self.assertNotEqual(self.backend_pid(), pid)

    def test_abandoned_handle_ends_idle_and_server_ends_idle_in_transaction(self):
        pid = self.backend_pid()
        unused = self.reader.open(readonly=True)
        unused.close()
        self.assertEqual(self.backend_pid(), pid)
        with self.assertRaises(psycopg.errors.TransactionTimeout):
            with self.reader.open(readonly=True) as held:
                held.execute('SELECT 1')
                sleep(.6)
                held.execute('SELECT 2')
        self.assertNotEqual(self.backend_pid(), pid)

    def test_read_bounds_and_no_cursor_or_handle_escape(self):
        with self.reader.open(readonly=True) as db:
            cursor = db.execute("""SELECT current_setting('statement_timeout') AS statement,
                current_setting('lock_timeout') AS lock,current_setting('transaction_timeout') AS duration""")
            self.assertEqual(cursor.fetchone(),dict(statement='200ms',lock='75ms',duration='500ms'))
            with ThreadPoolExecutor(max_workers=1) as threads:
                with self.assertRaises(RuntimeError):
                    threads.submit(db.execute,'SELECT 1').result(1)
        with self.assertRaises(RuntimeError):
            cursor.fetchall()
        with self.assertRaises(RuntimeError):
            db.execute('SELECT 1')
        with self.assertRaises(ValueError):
            self.reader.open(readonly=False)
        with patch('postgres.shared_read_connection.os.getpid',return_value=self.reader._pid+1):
            with self.assertRaises(RuntimeError):
                self.reader.open(readonly=True)
            with self.assertRaises(RuntimeError):
                self.reader.close()

    def test_async_cancel_and_shutdown_cannot_return_native_ticket_early(self):
        started, proceed, done = Event(), Event(), Event()
        def native():
            try:
                with self.reader.open(readonly=True) as db:
                    db.execute('SELECT 1')
                    started.set()
                    if not proceed.wait(2):
                        raise AssertionError('cancel fixture stalled')
            finally:
                done.set()
        async def exercise():
            task=asyncio.create_task(asyncio.to_thread(native))
            self.assertTrue(await asyncio.to_thread(started.wait, 2))
            try:
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                self.reader.close()
                self.assertFalse(done.is_set())
                with self.assertRaises(psycopg.OperationalError):
                    self.reader.open(readonly=True)
                with self.assertRaises(LocalAdmissionBusy):
                    self.physical.open(readonly=True,wait=0)
            finally:
                proceed.set()
            self.assertTrue(await asyncio.to_thread(done.wait,2))
        asyncio.run(exercise())
        with self.physical.open(readonly=True,wait=0) as db:
            self.assertTrue(db.read_only)

    def test_close_failure_quarantines_socket_until_verified_close(self):
        self.backend_pid()
        physical_conn = self.reader._db
        with patch.object(physical_conn,'close',side_effect=psycopg.OperationalError('generated close failure')):
            with self.assertRaises(psycopg.OperationalError):
                self.reader.close()
            with self.assertRaises(psycopg.OperationalError):
                self.reader.open(readonly=True)
            with self.assertRaises(LocalAdmissionBusy):
                self.physical.open(readonly=True,wait=0)
        self.reader.close()
        self.assertTrue(physical_conn.closed)
        with self.physical.open(readonly=True,wait=0) as db:
            self.assertTrue(db.read_only)
