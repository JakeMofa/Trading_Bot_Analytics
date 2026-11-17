"""Generated concurrent PP collector tests. No real source or live activation."""
import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.live_supervisor import CollectorHold, run_bounded


class Store:
    def __init__(self):
        self.settings = SimpleNamespace(environment='preprod', data_mode='pp_live',
                                        origin_id='pp-live-fixture')
        self.enabled = True
        self.calls = 0
        self.stops = 0

    def collector_enabled(self):
        self.calls += 1
        return self.enabled

    def disable(self):
        self.stops += 1
        self.enabled = False
        return {'collector_enabled': False}


class SupervisorTests(unittest.IsolatedAsyncioTestCase):
    async def test_fence_failure_opens_no_source(self):
        store = Store()
        async def source(*_args, **_kwargs):
            self.fail('source must remain closed')
        with self.assertRaises(CollectorHold):
            await run_bounded(store, None, asyncio.Event(), owner_check=lambda: False,
                              disable_collector=store.disable, max_seconds=1,
                              coinbase=source, market=source, candles=source)
        self.assertEqual(store.calls, 0)
        self.assertEqual(store.stops, 1)
        with self.assertRaises(CollectorHold):
            await run_bounded(store, None, asyncio.Event(), owner_check=lambda: True,
                              disable_collector=store.disable, max_seconds=1,
                              coinbase=source, market=source, candles=source)

    async def test_market_and_candles_advance_while_coinbase_waits(self):
        store, stop = Store(), asyncio.Event()
        calls = []
        async def coinbase(_store, _stop):
            await asyncio.Event().wait()
        async def market(_store, _client, _stop, *, now):
            calls.append('market')
            if 'candle' in calls:
                stop.set()
        async def candles(_store, _client, _stop, *, now):
            calls.append('candle')
            if 'market' in calls:
                stop.set()
        result = await run_bounded(store, None, stop, owner_check=lambda: True,
                                   disable_collector=store.disable, max_seconds=1, coinbase=coinbase, market=market,
                                   candles=candles)
        self.assertEqual(result, 'stopped')
        self.assertIn('market', calls)
        self.assertIn('candle', calls)
        self.assertFalse(store.enabled)

    async def test_lost_durable_flag_cancels_waiting_feed(self):
        store, stop = Store(), asyncio.Event()
        cancelled = asyncio.Event()
        async def coinbase(_store, _stop):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        async def idle(*_args, **_kwargs):
            await asyncio.Event().wait()
        async def revoke():
            await asyncio.sleep(.02)
            store.enabled = False
        revoker = asyncio.create_task(revoke())
        with self.assertRaises(CollectorHold):
            await run_bounded(store, None, stop, owner_check=lambda: True,
                              disable_collector=store.disable, max_seconds=2,
                              coinbase=coinbase, market=idle, candles=idle)
        await revoker
        self.assertTrue(cancelled.is_set())

    async def test_unexpected_source_end_and_deadline_are_reported(self):
        store = Store()
        async def ended(_store, _stop):
            return None
        async def idle(*_args, **_kwargs):
            await asyncio.Event().wait()
        with self.assertRaisesRegex(CollectorHold, 'stream ended'):
            await run_bounded(store, None, asyncio.Event(), owner_check=lambda: True,
                              disable_collector=store.disable, max_seconds=1,
                              coinbase=ended, market=idle, candles=idle)
        store.enabled = True
        with self.assertRaisesRegex(CollectorHold, 'deadline'):
            await run_bounded(store, None, asyncio.Event(), owner_check=lambda: True,
                              disable_collector=store.disable, max_seconds=.02,
                              coinbase=idle, market=idle, candles=idle)

    async def test_unqualified_cadence_and_mode_rejected(self):
        store = Store()
        for options in ({'market_interval': 11}, {'candle_interval': 5},
                        {'max_seconds': 1801}):
            with self.assertRaises(ValueError):
                await run_bounded(store, None, asyncio.Event(), owner_check=lambda: True,
                                  disable_collector=store.disable,
                                  max_seconds=options.get('max_seconds', 1),
                                  market_interval=options.get('market_interval', 5),
                                  candle_interval=options.get('candle_interval', 60))
        store.settings.data_mode = 'generated'
        with self.assertRaises(ValueError):
            await run_bounded(store, None, asyncio.Event(), owner_check=lambda: True,
                              disable_collector=store.disable, max_seconds=1)

    async def test_failed_durable_stop_cannot_report_success(self):
        store, stop = Store(), asyncio.Event()
        stop.set()
        def broken_stop():
            raise RuntimeError('sensitive database error')
        with self.assertRaisesRegex(CollectorHold, 'durable PP collector stop unproven'):
            await run_bounded(store, None, stop, owner_check=lambda: True,
                              disable_collector=broken_stop, max_seconds=1)


if __name__ == '__main__':
    unittest.main()
