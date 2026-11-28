"""PostgreSQL lease ownership and independent source supervision for the sustained watch."""

import asyncio
import unittest
import uuid
from unittest.mock import patch

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
        self.addCleanup(self.cleanup_origin, DISPLAY_ORIGIN, [self.anchor])
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
