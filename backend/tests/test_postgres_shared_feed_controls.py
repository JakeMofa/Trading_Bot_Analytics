"""A preference timeout retries only its own read-only PostgreSQL transaction."""
from contextlib import contextmanager
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from psycopg import errors
from psycopg.types.json import Jsonb

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / 'tests'))
import test_postgres_shared_read_connection as reader_fixture
from postgres import feed_controls
from postgres.lifecycle import LifecycleRepository


class NativePreferenceRetries(unittest.TestCase):
    require_migration_ledger = True
    setUpClass = reader_fixture.fixture.Trial07Permit.__dict__['setUpClass']
    tearDownClass = reader_fixture.fixture.Trial07Permit.__dict__['tearDownClass']
    admin = reader_fixture.fixture.Trial07Permit.__dict__['admin']
    setUp = reader_fixture.NativeSharedReader.setUp
    seeded_writer = reader_fixture.NativeSharedReader.seeded_writer

    @contextmanager
    def store_with_writer(self):
        with self.seeded_writer() as (origin, _, session), patch.object(feed_controls, 'ORIGIN', origin):
            store = SimpleNamespace(origin=origin, read_login='tradebot_reader',
                                    settings=SimpleNamespace(environment='preprod', data_mode='pp_live'),
                                    connection=lambda readonly: self.reader.open(readonly=readonly))
            try:
                yield store, session
            finally:
                with self.admin() as db:
                    db.execute('DELETE FROM ops.worker_checkpoints WHERE origin_id=%s', (origin,))

    def test_timed_out_query_releases_reader_and_retry_sees_changed_preference_and_off(self):
        with self.store_with_writer() as (store, session):
            repository = LifecycleRepository(lambda: self.reader.open(readonly=True))
            self.assertTrue(repository.owns_collector(store.origin, session))
            actual_rows = feed_controls._rows
            pids, delays = [], []

            def read(db):
                pids.append(db.execute('SELECT pg_backend_pid() AS pid').fetchone()['pid'])
                if len(pids) == 1:
                    db.execute('SELECT pg_sleep(1)')  # Exceeds the ordinary 200ms statement deadline.
                return actual_rows(db)

            def during_backoff(delay):
                delays.append(delay)
                with self.admin() as db:
                    db.execute("""INSERT INTO ops.worker_checkpoints(origin_id,worker,cursor,updated_at)
                        VALUES (%s,'feed_desired:coinbase',%s,clock_timestamp())""",
                        (store.origin, Jsonb({'revision': 1, 'enabled': False})))
                    db.execute("""UPDATE ops.writer_state SET collector_enabled=FALSE,collector_session_id=NULL,
                        collector_lease_expires_at=NULL WHERE origin_id=%s""", (store.origin,))
                self.assertFalse(repository.owns_collector(store.origin, session))

            with patch.object(feed_controls, '_rows', read), patch.object(
                    feed_controls, 'time', SimpleNamespace(sleep=during_backoff)):
                self.assertEqual(feed_controls.desired_feeds(store),
                                 {'polymarket': True, 'robinhood': True, 'coinbase': False})
            self.assertEqual(delays, [.1])
            self.assertEqual(len(set(pids)), 2)

    def test_transaction_timeout_at_commit_discards_already_read_value(self):
        with self.store_with_writer() as (store, _):
            actual_rows = feed_controls._rows
            pids, delays = [], []

            def read(db):
                pids.append(db.execute('SELECT pg_backend_pid() AS pid').fetchone()['pid'])
                rows = actual_rows(db)
                if len(pids) == 1:
                    # Let PostgreSQL terminate this transaction after the
                    # SELECT and before psycopg commits on context exit.
                    time.sleep(.65)
                return rows

            def during_backoff(delay):
                delays.append(delay)
                with self.admin() as db:
                    db.execute("""INSERT INTO ops.worker_checkpoints(origin_id,worker,cursor,updated_at)
                        VALUES (%s,'feed_desired:robinhood',%s,clock_timestamp())""",
                        (store.origin, Jsonb({'revision': 1, 'enabled': False})))

            with patch.object(feed_controls, '_rows', read), patch.object(
                    feed_controls, 'time', SimpleNamespace(sleep=during_backoff)):
                self.assertFalse(feed_controls.desired_feeds(store)['robinhood'])
            self.assertEqual(delays, [.1])
            self.assertEqual(len(set(pids)), 2)

    def test_persistent_query_timeout_fails_on_third_transaction(self):
        with self.store_with_writer() as (store, _):
            delays, pids = [], []

            def timeout(db):
                pids.append(db.execute('SELECT pg_backend_pid() AS pid').fetchone()['pid'])
                db.execute('SELECT pg_sleep(1)')

            with patch.object(feed_controls, '_rows', timeout), patch.object(
                    feed_controls, 'time', SimpleNamespace(sleep=delays.append)):
                with self.assertRaises(errors.QueryCanceled) as failure:
                    feed_controls.desired_feeds(store)
            self.assertEqual(failure.exception.sqlstate, '57014')
            self.assertEqual(delays, [.1, .3])
            self.assertEqual(len(pids), 3)
            self.assertEqual(len(set(pids)), 3)

    def test_other_failures_and_operator_status_do_not_retry(self):
        with self.store_with_writer() as (store, _):
            for failure in (errors.InsufficientPrivilege(), errors.InvalidPassword(), errors.TooManyConnections(),
                            ValueError('invalid durable feed preference')):
                with self.subTest(failure=type(failure).__name__), patch.object(
                        feed_controls, '_rows', side_effect=failure) as read:
                    with self.assertRaises(type(failure)):
                        feed_controls.desired_feeds(store)
                    read.assert_called_once()
            with patch.object(feed_controls, '_rows', side_effect=errors.QueryCanceled()) as read:
                with self.assertRaises(errors.QueryCanceled):
                    feed_controls.read_controls(store)
                read.assert_called_once()
