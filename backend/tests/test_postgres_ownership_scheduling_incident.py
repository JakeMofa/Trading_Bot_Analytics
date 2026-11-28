"""Offline scheduling fault reproductions; no vendor, live host or runtime changes.

These prove possible deadline failure modes, not the cause of the 09:51
incident. The native case uses only the disposable generated PG17 fixture.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sys
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import test_postgres_trial07_permit as fixture
from postgres.live_diagnostics import LiveDiagnostic, OwnershipConnectionLimit
from postgres.live_supervisor import run_bounded
from postgres.ownership_probe import OwnershipProbe, phase, submit_ownership
from postgres.watch_connections import LocalAdmissionBusy, SessionBudget


class GeneratedStore:
    def __init__(self):
        self.settings = SimpleNamespace(environment='preprod', data_mode='pp_live',
                                        origin_id='pp-live-offline-owner-scheduling')
        self.enabled = True
        self.stops = 0

    def disable(self):
        self.enabled = False
        self.stops += 1
        return {'collector_enabled': False}


class OwnershipExecutorScheduling(unittest.IsolatedAsyncioTestCase):
    async def test_real_supervisor_deadline_can_expire_before_owner_worker_starts(self):
        loop = asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=1))
        occupied, release = Event(), Event()
        owner_started = Event()

        def unrelated_write_work():
            occupied.set()
            release.wait(10)

        blocker = loop.run_in_executor(None, unrelated_write_work)
        while not occupied.is_set():
            await asyncio.sleep(.001)
        store = GeneratedStore()

        def owner_check():
            owner_started.set()
            return True

        async def forbidden_source(*_args, **_kwargs):
            self.fail('no source may start without the initial ownership proof')

        # Release AFTER the actual two-second fence deadline, so durable OFF
        # can run in the same default pool. No timeout constants are patched.
        timer = loop.call_later(2.15, release.set)

        async def legacy_submission(callback, _probe):
            return await asyncio.to_thread(callback)

        try:
            with (patch('postgres.live_supervisor.submit_ownership', legacy_submission),
                  self.assertRaises(LiveDiagnostic) as caught):
                await run_bounded(store, None, asyncio.Event(), owner_check=owner_check,
                                  disable_collector=store.disable, max_seconds=3,
                                  coinbase=forbidden_source, market=forbidden_source,
                                  candles=forbidden_source)
            self.assertEqual(caught.exception.code, 'ownership.timeout')
            self.assertFalse(owner_started.is_set(), 'SQL was never attempted')
            self.assertEqual((store.enabled, store.stops), (False, 1))
        finally:
            timer.cancel()
            release.set()
            await blocker

    async def test_candidate_owner_executor_is_not_queued_behind_default_source_work(self):
        # Isolation removes this particular queue, not CPU/SQL/admission delay.
        loop = asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=1))
        occupied, release = Event(), Event()

        def unrelated_write_work():
            occupied.set()
            release.wait(10)

        blocker = loop.run_in_executor(None, unrelated_write_work)
        while not occupied.is_set():
            await asyncio.sleep(.001)
        try:
            result = await asyncio.wait_for(submit_ownership(lambda: True, OwnershipProbe()), 2)
            self.assertIs(result, True)
            self.assertFalse(blocker.done())
            # A successful submission does not authorize cached ownership:
            # every subsequent read must evaluate the current authority.
            result = await asyncio.wait_for(submit_ownership(lambda: False, OwnershipProbe()), 2)
            self.assertIs(result, False)
        finally:
            release.set()
            await blocker

    async def test_candidate_supervisor_rejects_fresh_false_while_default_pool_is_busy(self):
        loop = asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=1))
        occupied, release = Event(), Event()
        owner_saw_busy = []

        def unrelated_write_work():
            occupied.set()
            release.wait(10)

        blocker = loop.run_in_executor(None, unrelated_write_work)
        while not occupied.is_set():
            await asyncio.sleep(.001)
        store = GeneratedStore()

        def no_longer_owner():
            owner_saw_busy.append(not release.is_set())
            # Allow the default-pool durable-OFF callback to run. The fresh
            # False must still reject all source startup, never reuse True.
            release.set()
            return False

        async def forbidden_source(*_args, **_kwargs):
            self.fail('lost ownership may not start any source')

        try:
            with self.assertRaises(LiveDiagnostic) as caught:
                await run_bounded(store, None, asyncio.Event(), owner_check=no_longer_owner,
                                  disable_collector=store.disable, max_seconds=3,
                                  coinbase=forbidden_source, market=forbidden_source,
                                  candles=forbidden_source)
            self.assertEqual(caught.exception.code, 'ownership.lease_lost')
            self.assertEqual(owner_saw_busy, [True])
            self.assertEqual((store.enabled, store.stops), (False, 1))
        finally:
            release.set()
            await blocker

    async def test_candidate_supervisor_starts_sources_under_fresh_true_with_default_pool_busy(self):
        loop = asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=1))
        occupied, release = Event(), Event()
        source_saw_busy = []
        owner_checks = []

        def unrelated_write_work():
            occupied.set()
            release.wait(10)

        blocker = loop.run_in_executor(None, unrelated_write_work)
        while not occupied.is_set():
            await asyncio.sleep(.001)
        store, stop = GeneratedStore(), asyncio.Event()

        def current_owner():
            owner_checks.append(True)
            return True

        async def source(*_args, **_kwargs):
            source_saw_busy.append(not release.is_set())
            if len(source_saw_busy) == 3:
                release.set()
                stop.set()
            await stop.wait()

        try:
            result = await run_bounded(store, None, stop, owner_check=current_owner,
                                       disable_collector=store.disable, max_seconds=3,
                                       coinbase=source, market=source, candles=source)
            self.assertEqual(result, 'stopped')
            self.assertEqual(source_saw_busy, [True, True, True])
            self.assertGreaterEqual(len(owner_checks), 1)
            self.assertEqual((store.enabled, store.stops), (False, 1))
        finally:
            release.set()
            await blocker


class OwnershipNativeConnectionCancellation(unittest.TestCase):
    require_migration_ledger = True
    setup = fixture.Trial07Permit
    setUpClass = setup.__dict__['setUpClass']
    tearDownClass = setup.__dict__['tearDownClass']
    admin = setup.__dict__['admin']

    def test_expired_async_wait_does_not_close_physical_reader_or_restore_authority(self):
        dsn = (os.environ['TRADEBOT_TEST_READER_DSN'] if self.external
               else f'host={self.socket} user=tradebot_reader dbname=tradebot_pp')
        budget = SessionBudget(dsn, 'tradebot_reader', 1)
        opened, release, closed = Event(), Event(), Event()
        observed = {}
        store = GeneratedStore()

        def owner_check():
            try:
                with budget.open(readonly=True, wait=.20) as db:
                    phase('query')
                    observed.update(db.execute("SELECT pg_backend_pid() AS pid, "
                        "current_setting('transaction_read_only') AS readonly").fetchone())
                    opened.set()
                    release.wait(10)
                    return True
            finally:
                closed.set()

        async def forbidden_source(*_args, **_kwargs):
            self.fail('a late worker result cannot start source readers')

        async def scenario():
            loop = asyncio.get_running_loop()
            loop.set_default_executor(ThreadPoolExecutor(max_workers=2))
            try:
                with self.assertRaises(LiveDiagnostic) as caught:
                    await run_bounded(store, None, asyncio.Event(), owner_check=owner_check,
                                      disable_collector=store.disable, max_seconds=3,
                                      coinbase=forbidden_source, market=forbidden_source,
                                      candles=forbidden_source)
                self.assertEqual(caught.exception.code, 'ownership.timeout')
                self.assertTrue(opened.is_set())
                self.assertFalse(closed.is_set())
                self.assertEqual(observed['readonly'], 'on')
                self.assertEqual((store.enabled, store.stops), (False, 1))
                # Async cancellation cannot release the process-wide owner
                # ticket while the previous native query/session is alive.
                second_started = Event()
                with self.assertRaises(OwnershipConnectionLimit):
                    await submit_ownership(lambda: second_started.set(), OwnershipProbe())
                self.assertFalse(second_started.is_set())
                with self.assertRaises(LocalAdmissionBusy):
                    budget.open(readonly=True, wait=.01)
                with self.admin() as db:
                    self.assertTrue(db.execute('SELECT EXISTS (SELECT FROM pg_stat_activity '
                        'WHERE pid=%s) AS present', (observed['pid'],)).fetchone()['present'])
            finally:
                release.set()
                for _ in range(200):
                    if closed.is_set():
                        break
                    await asyncio.sleep(.01)
            self.assertTrue(closed.is_set())
            self.assertFalse(store.enabled, 'late True must never undo durable OFF')
            # The native done callback may run just after the worker's own
            # finally block; wait for that genuine completion, not a delay
            # that assumes when it must have occurred.
            for _ in range(200):
                try:
                    self.assertIs(await submit_ownership(lambda: True, OwnershipProbe()), True)
                    break
                except OwnershipConnectionLimit:
                    await asyncio.sleep(.01)
            else:
                self.fail('native completion did not return the ownership ticket')
            with budget.open(readonly=True, wait=.20) as db:
                self.assertNotEqual(db.info.backend_pid, observed['pid'])

        asyncio.run(scenario())
