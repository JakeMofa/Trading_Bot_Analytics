"""Generated concurrent PP collector tests. No real source or live activation."""
import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from postgres.live_ingest import polymarket_cycle
from postgres.live_supervisor import CollectorHold, run_bounded
from postgres.live_diagnostics import LiveDiagnostic, SourceHTTPFailure


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
    async def test_rollover_waits_for_book_while_coinbase_continues(self):
        store = Store()
        stop = asyncio.Event()
        saved, requests = [], []
        observed_empty = asyncio.Event()
        coinbase_during_gap = asyncio.Event()
        market = {'market_id': 'new', 'kind': 'market', 'payload': {'slug': 'new'}}
        store.ingest = saved.append
        async def discover(_client, _now):
            return market
        def reply(request):
            requests.append(request.url.path)
            if len(requests) <= 2:
                return httpx.Response(404)
            data = {'marketSlug': 'new', 'state': 'MARKET_STATE_OPEN'}
            if len(requests) == 4:
                raise httpx.ReadTimeout('private raw response', request=request)
            if len(requests) == 5:
                return httpx.Response(429)
            if len(requests) == 6:
                return httpx.Response(503)
            if len(requests) == 7:
                raise httpx.ConnectError('private transport details', request=request)
            if len(requests) > 7:
                data['bestAsk'] = {'value': '0.5300'}
            return httpx.Response(200, json={'marketData': data})
        async def cycle(s, client, st, **kw):
            result = await polymarket_cycle(s, client, st, discover=discover, **kw)
            if result is None:
                observed_empty.set()
            else:
                self.assertTrue(coinbase_during_gap.is_set())
                st.set()
        async def cb(s, st):
            await observed_empty.wait()
            await asyncio.to_thread(s.ingest, {'kind': 'price', 'source': 'coinbase'})
            coinbase_during_gap.set()
            await st.wait()
        async def candle(*_a, **_kw):
            await stop.wait()
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
            await run_bounded(store, client, stop, owner_check=lambda: True,
                              disable_collector=store.disable, max_seconds=12,
                              market_interval=1, market=cycle, coinbase=cb, candles=candle)
        self.assertEqual([e['kind'] for e in saved], ['market', 'price'] + ['market'] * 6 + ['quote'])
        self.assertEqual(saved[-1]['market_id'], 'new')
        self.assertEqual(saved[-1]['payload']['best_ask'], '0.5300')
        self.assertEqual(store.stops, 1)

    async def test_fence_failure_opens_no_source(self):
        store = Store()
        async def source(*_args, **_kwargs):
            self.fail('source must remain closed')
        with self.assertRaisesRegex(LiveDiagnostic, 'ownership.lease_lost'):
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
        with self.assertRaisesRegex(LiveDiagnostic, 'coinbase_stream.ended'):
            await run_bounded(store, None, asyncio.Event(), owner_check=lambda: True,
                              disable_collector=store.disable, max_seconds=1,
                              coinbase=ended, market=idle, candles=idle)
        store.enabled = True
        with self.assertRaisesRegex(LiveDiagnostic, 'session.deadline_reached'):
            await run_bounded(store, None, asyncio.Event(), owner_check=lambda: True,
                              disable_collector=store.disable, max_seconds=.02,
                              coinbase=idle, market=idle, candles=idle)

    async def test_unqualified_cadence_and_mode_rejected(self):
        store = Store()
        for options in ({'market_interval': 11}, {'candle_interval': 5},
                        {'max_seconds': 4561}):
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
        with self.assertRaisesRegex(LiveDiagnostic, 'session.durable_off_unproven'):
            await run_bounded(store, None, stop, owner_check=lambda: True,
                              disable_collector=broken_stop, max_seconds=1)

    async def test_supervisor_preserves_bounded_source_operation(self):
        store = Store()
        async def idle(*_args, **_kwargs):
            await asyncio.Event().wait()
        async def bad_market(*_args, **_kwargs):
            raise SourceHTTPFailure(429, 'secret=never-display')
        with self.assertRaises(LiveDiagnostic) as caught:
            await run_bounded(store, None, asyncio.Event(), owner_check=lambda: True,
                              disable_collector=store.disable, max_seconds=1,
                              coinbase=idle, market=bad_market, candles=idle)
        self.assertEqual(caught.exception.code, 'polymarket_loop.http_429')
        self.assertNotIn('secret', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
