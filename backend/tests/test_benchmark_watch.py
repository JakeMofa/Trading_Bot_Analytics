"""PostgreSQL lease ownership and independent source supervision for the sustained watch."""

import asyncio
from pathlib import Path
import unittest
import uuid
from unittest.mock import patch

import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import test_postgres_trial07_permit as fixture
from postgres.cloud_origin_binding import DISPLAY_ORIGIN
from postgres.connection import connect
from postgres.lifecycle import LifecycleHold, LifecycleRepository
from postgres.rehearsal_profile import WATCH_LEASE_SECONDS
from postgres.watch_lease import WatchLease
from postgres.watch_sources import run_watch_sources


class BenchmarkLease(unittest.TestCase):
    setup = fixture.Trial07Permit
    setUpClass = setup.__dict__['setUpClass']
    tearDownClass = setup.__dict__['tearDownClass']
    admin = setup.__dict__['admin']
    cleanup_origin = setup.cleanup_origin

    def setUp(self):
        self.repo = LifecycleRepository(lambda: connect(self.lifecycle_dsn))
        with self.admin() as db:
            self.assertIsNone(
                db.execute(
                    'SELECT FROM archive.generations WHERE origin_id=%s', (DISPLAY_ORIGIN,)
                ).fetchone()
            )
        self.anchor = str(self.repo.bootstrap(DISPLAY_ORIGIN)['generation_id'])
        self.generations = [self.anchor]
        self.addCleanup(self.cleanup_origin, DISPLAY_ORIGIN, self.generations)
        self.watch = WatchLease(self.repo, self.anchor)
        self.sample = self.enterContext(
            patch('postgres.pp_space.sample', return_value={'space_hold': None})
        )

    def enable(self):
        active = self.watch.admit(WATCH_LEASE_SECONDS)
        session = str(uuid.uuid4())
        self.repo.enable_collector(
            DISPLAY_ORIGIN,
            session_id=session,
            expected_generation_id=active,
            max_seconds=WATCH_LEASE_SECONDS,
        )
        self.watch.session_id = session
        return session

    def test_inflight_owner_finishes_before_transfer_stale_owner_rejected_afterwards(self):
        from concurrent.futures import ThreadPoolExecutor
        from datetime import datetime, timezone
        from threading import Event
        from postgres.config import Settings
        from postgres.feed_controls import record_effective
        from postgres.live_contract import coinbase_ticker
        from postgres.store import Store, StorageHold

        def cleanup_rows():
            with self.admin() as db:
                for table in ('ops.outbox', 'core.current_prices', 'ops.worker_checkpoints'):
                    db.execute('DELETE FROM ' + table + ' WHERE origin_id=%s', (DISPLAY_ORIGIN,))

        self.addCleanup(cleanup_rows)
        settings = Settings(data_mode='pp_live', origin_id=DISPLAY_ORIGIN, dsn=self.app_dsn)

        def tick():
            at = datetime.now(timezone.utc).isoformat()
            return coinbase_ticker(
                {
                    'type': 'ticker',
                    'product_id': 'BTC-USD',
                    'time': at,
                    'price': '100000.25',
                    'trade_id': uuid.uuid4().hex,
                },
                at,
            )

        first = self.enable()
        old = Store(settings, producer_session_id=first)
        acquired, proceed = Event(), Event()
        real_lock = old._locked_writer

        def arm_barrier(db):
            row = real_lock(db)
            acquired.set()
            if not proceed.wait(3):
                raise RuntimeError('owner transfer barrier expired')
            return row

        with (
            ThreadPoolExecutor(max_workers=2) as pool,
            patch.object(old, '_locked_writer', side_effect=arm_barrier),
        ):
            inflight = pool.submit(old.ingest, tick())
            self.assertTrue(acquired.wait(2))
            release_started = Event()

            def release_owner():
                release_started.set()
                self.watch.release(first)

            releasing = pool.submit(release_owner)
            self.assertTrue(release_started.wait(2))
            try:
                with self.assertRaises(TimeoutError):
                    releasing.result(timeout=0.08)
            finally:
                proceed.set()
            self.assertEqual(str(inflight.result(2)['generation_id']), self.anchor)
            releasing.result(2)
        second = self.enable()
        with self.assertRaisesRegex(StorageHold, 'session no longer owns'):
            old.ingest(tick())
        with self.assertRaisesRegex(StorageHold, 'session no longer owns'):
            Store(settings).ingest(tick())
        current = Store(settings, producer_session_id=second)
        record_effective(current, 'coinbase_stream', 'running', session_id=second)
        record_effective(old, 'coinbase_stream', 'paused', session_id=first)
        with self.admin() as db:
            actual = db.execute(
                "SELECT cursor FROM ops.worker_checkpoints WHERE origin_id=%s AND worker='feed_actual:coinbase_stream'",
                (DISPLAY_ORIGIN,),
            ).fetchone()['cursor']
            self.assertEqual(actual['state'], 'running')
            db.execute(
                "UPDATE archive.generations SET started_at=clock_timestamp()-interval '73 hours' WHERE generation_id=%s",
                (self.anchor,),
            )
        self.assertEqual(
            self.repo.switch_if_due(DISPLAY_ORIGIN, require_live_lease=True)['status'], 'switched'
        )
        successor = str(self.repo.collector_state(DISPLAY_ORIGIN)['generation_id'])
        self.generations.append(successor)
        self.assertNotEqual(successor, self.anchor)
        self.assertTrue(self.repo.owns_collector(DISPLAY_ORIGIN, second))
        self.assertEqual(str(current.ingest(tick())['generation_id']), successor)
        self.watch.release(second)

    def test_renewal_expiry_reentry_and_operator_off(self):
        first = self.enable()
        before = self.repo.collector_state(DISPLAY_ORIGIN)
        self.assertEqual(self.watch.renew()['epoch'], before['epoch'])
        self.assertGreater(
            self.repo.collector_state(DISPLAY_ORIGIN)['collector_lease_expires_at'],
            before['collector_lease_expires_at'],
        )
        self.watch.set_explicit_off(True)
        with self.assertRaisesRegex(LifecycleHold, 'operator requested OFF'):
            self.watch.renew()
        self.watch.release(first)
        with self.assertRaisesRegex(LifecycleHold, 'operator requested OFF'):
            self.watch.admit(WATCH_LEASE_SECONDS)
        self.watch.set_explicit_off(False)
        second = self.enable()
        self.watch.release(first)
        self.assertTrue(self.repo.owns_collector(DISPLAY_ORIGIN, second))
        with self.repo.transaction() as db:
            db.execute(
                "UPDATE ops.writer_state SET collector_lease_expires_at=now()-interval '1s' WHERE origin_id=%s",
                (DISPLAY_ORIGIN,),
            )
        with self.assertRaisesRegex(LifecycleHold, 'expired'):
            self.watch.renew()
        self.watch.release(second)
        self.sample.return_value = {'space_hold': 'pp_filesystem_reserve'}
        with self.assertRaisesRegex(LifecycleHold, 'reserve'):
            self.watch.admit(WATCH_LEASE_SECONDS)


class FeedIsolation(unittest.IsolatedAsyncioTestCase):
    async def test_provider_error_and_early_return_retry_only_one_source(self):
        from postgres.live_diagnostics import LiveDiagnostic

        stop = asyncio.Event()
        attempts = {'coinbase': 0, 'polymarket': 0, 'robinhood': 0}

        async def run(name, signal):
            attempts[name] += 1
            if name == 'coinbase':
                if attempts[name] == 1:
                    raise LiveDiagnostic('coinbase_stream', 'transport')
                if attempts[name] == 2:
                    return
                stop.set()
            await signal.wait()

        feeds = {name: (name, lambda signal, n=name: run(n, signal)) for name in attempts}
        actual = []
        await asyncio.wait_for(
            run_watch_sources(
                None,
                stop,
                feeds,
                lambda _: {n: True for n in attempts},
                lambda _, n, s: actual.append((n, s)),
                interval=0.01,
                retry_min=0.01,
            ),
            2,
        )
        self.assertEqual(attempts, {'coinbase': 3, 'polymarket': 1, 'robinhood': 1})
        self.assertEqual(actual.count(('coinbase', 'retrying')), 2)

    async def test_optional_fault_pause_resume_and_other_sources(self):
        desired = dict(polymarket=True, robinhood=True, coinbase=True)
        reports = []
        counts = dict(polymarket=0, coinbase=0, robinhood=0)

        async def run(name, stop):
            counts[name] += 1
            if name == 'coinbase' and counts[name] == 1:
                raise RuntimeError('candle write failed')
            await stop.wait()

        readers = {name: (name, lambda signal, n=name: run(n, signal)) for name in counts}
        stop = asyncio.Event()
        owner = asyncio.create_task(
            run_watch_sources(
                None,
                stop,
                readers,
                lambda _: desired.copy(),
                lambda _, name, state: reports.append((name, state)),
                interval=0.01,
            )
        )

        async def await_report(name, state):
            async with asyncio.timeout(2):
                while (name, state) not in reports:
                    await asyncio.sleep(0.01)

        try:
            await await_report('coinbase', 'held')
            desired['coinbase'] = False
            await await_report('coinbase', 'paused')
            desired['coinbase'] = True
            async with asyncio.timeout(2):
                while counts['coinbase'] < 2:
                    await asyncio.sleep(0.01)
            self.assertEqual(counts, dict(polymarket=1, coinbase=2, robinhood=1))
        finally:
            stop.set()
            await asyncio.wait_for(owner, 2)
