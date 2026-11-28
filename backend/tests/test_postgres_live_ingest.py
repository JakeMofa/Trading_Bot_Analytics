"""Network-free PP live bridge tests; no test enables the real collector."""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.live_ingest import coinbase_candle_cycle, coinbase_session, polymarket_cycle
from postgres.live_diagnostics import LiveDiagnostic, SourceHTTPFailure, SourceTransportFailure
from postgres.store import StorageHold


class FakeStore:
    def __init__(self, mode='pp_live', origin='pp-live-fixture'):
        self.settings = SimpleNamespace(environment='preprod', data_mode=mode, origin_id=origin)
        self.events = []
        self.fail = False

    def ingest(self, event):
        if self.fail:
            raise RuntimeError('durable collector hold')
        self.events.append(event)
        return {'event_id': event['event_id']}


class LiveIngestTests(unittest.IsolatedAsyncioTestCase):
    async def test_off_or_wrong_origin_cannot_use_bridge(self):
        async def discover(*_):
            self.fail('network client must not be called')
        for mode, origin in [('generated', 'pp-live-fixture'), ('pp_live', 'generated-pp'),
                             ('pp_live', 'pp-live-')]:
            with self.subTest(mode=mode, origin=origin):
                with self.assertRaises(ValueError):
                    await polymarket_cycle(FakeStore(mode, origin), None, asyncio.Event(), discover=discover)

    async def test_market_discovery_and_quote_are_ordered_and_independent(self):
        store = FakeStore()
        market = {'market_id': 'm2', 'event_id': 'market-m2'}
        quote = {'market_id': 'm2', 'event_id': 'quote-m2'}
        async def discover(_client, now):
            self.assertIsInstance(now, datetime)
            return market
        async def fetch(_client, selected):
            self.assertIs(selected, market)
            self.assertEqual([e['event_id'] for e in store.events], ['market-m2'])
            return quote
        result = await polymarket_cycle(store, None, asyncio.Event(),
                                        now=datetime(2026, 11, 16, tzinfo=timezone.utc),
                                        discover=discover, fetch=fetch)
        self.assertEqual(result, 'm2')
        self.assertEqual([e['event_id'] for e in store.events], ['market-m2', 'quote-m2'])

    async def test_no_old_market_fallback_and_stop_prevents_later_write(self):
        store, stop = FakeStore(), asyncio.Event()
        async def no_market(*_):
            return None
        self.assertIsNone(await polymarket_cycle(store, None, stop, discover=no_market))
        self.assertEqual(store.events, [])
        async def market_then_stop(*_):
            stop.set()
            return {'market_id': 'old', 'event_id': 'old'}
        self.assertIsNone(await polymarket_cycle(store, None, stop, discover=market_then_stop))
        self.assertEqual(store.events, [])

    async def test_durable_hold_propagates_without_quote_or_retry(self):
        store = FakeStore()
        store.fail = True
        async def discover(*_):
            return {'market_id': 'm', 'event_id': 'market'}
        async def fetch(*_):
            self.fail('quote cannot run after failed market acknowledgement')
        with self.assertRaisesRegex(LiveDiagnostic, 'polymarket_market_write.unexpected'):
            await polymarket_cycle(store, None, asyncio.Event(), discover=discover, fetch=fetch)
        self.assertEqual(store.events, [])

    async def test_durable_store_hold_is_classified_without_database_text(self):
        class HeldStore(FakeStore):
            def ingest(self, _event):
                raise StorageHold('private-database-details')
        async def discover(*_):
            return {'market_id': 'm', 'event_id': 'market'}
        with self.assertRaises(LiveDiagnostic) as caught:
            await polymarket_cycle(HeldStore(), None, asyncio.Event(), discover=discover)
        self.assertEqual(caught.exception.code, 'polymarket_market_write.write_rejected')
        self.assertNotIn('private', str(caught.exception))

    async def test_rejected_quote_credentials_stop_collection(self):
        store = FakeStore()
        async def market(*_):
            return {'market_id': 'current', 'event_id': 'current-market'}
        for status in (401, 403):
            async def denied(*_):
                raise SourceHTTPFailure(status, 'private credentials')
            with self.assertRaisesRegex(LiveDiagnostic, 'polymarket_bbo.http_4xx'):
                await polymarket_cycle(store, None, asyncio.Event(), discover=market, fetch=denied)
        self.assertEqual([e['event_id'] for e in store.events], ['current-market'] * 2)

    async def test_mismatched_quote_is_not_persisted(self):
        store = FakeStore()
        async def discover(*_):
            return {'market_id': 'current', 'event_id': 'market'}
        async def fetch(*_):
            return {'market_id': 'ended', 'event_id': 'quote'}
        with self.assertRaisesRegex(LiveDiagnostic, 'polymarket_bbo.identity_mismatch'):
            await polymarket_cycle(store, None, asyncio.Event(), discover=discover, fetch=fetch)
        self.assertEqual([e['event_id'] for e in store.events], ['market'])

    async def test_transient_discovery_waits_for_next_cycle_without_writes(self):
        store = FakeStore()
        for error in [SourceHTTPFailure(status, 'private-response')
                      for status in (404, 429, 500, 503)] + [
                SourceTransportFailure(timeout=timeout, message='private-transport')
                for timeout in (True, False)]:
            async def unavailable(*_):
                raise error
            async def fetch(*_):
                self.fail('no quote fetch without a discovered current market')
            with self.subTest(error=error.category), self.assertLogs('postgres.live_ingest') as logs:
                self.assertIsNone(await polymarket_cycle(store, None, asyncio.Event(),
                                                        discover=unavailable, fetch=fetch))
            self.assertNotIn('private', str(logs.output))
            self.assertEqual(store.events, [])

    async def test_discovery_auth_and_invalid_data_remain_fatal(self):
        for error in (SourceHTTPFailure(401, 'private'), SourceHTTPFailure(403, 'private'),
                      ValueError('ambiguous active market'), ValueError('pagination limit')):
            store = FakeStore()
            async def rejected(*_):
                raise error
            with self.subTest(error=type(error)), self.assertRaises(LiveDiagnostic) as caught:
                await polymarket_cycle(store, None, asyncio.Event(), discover=rejected)
            self.assertTrue(caught.exception.code.startswith('polymarket_discovery.'))
            self.assertNotIn('private', str(caught.exception))
            self.assertEqual(store.events, [])

    async def test_coinbase_backpressure_and_stop(self):
        store, stop = FakeStore(), asyncio.Event()
        async def source(_stop):
            for i in range(3):
                if i == 0:
                    stop.set()
                yield {'event_id': str(i)}
        await coinbase_session(store, stop, source=source)
        self.assertEqual(store.events, [])
        stop.clear()
        async def two(_stop):
            yield {'event_id': '1'}
            yield {'event_id': '2'}
        await coinbase_session(store, stop, source=two)
        self.assertEqual([e['event_id'] for e in store.events], ['1', '2'])

    async def test_bounded_read_ahead_drains_each_accepted_tick_on_orderly_stop(self):
        from threading import Event
        stop = asyncio.Event()
        full = asyncio.Event()
        beyond_capacity = asyncio.Event()
        release = Event()
        store = FakeStore()
        original = store.ingest
        def slow_writer(event):
            if not release.wait(3):
                raise RuntimeError('fixture writer timed out')
            return original(event)
        store.ingest = slow_writer
        produced = []
        async def source(_):
            for i in range(100):
                produced.append(i)
                if i == 33:  # One saving, 32 enqueued, one waiting to enqueue.
                    full.set()
                if i > 33:
                    beyond_capacity.set()
                yield {'event_id':str(i)}
        task = asyncio.create_task(coinbase_session(store,stop,source=source))
        try:
            await asyncio.wait_for(full.wait(), 2)
            with self.assertRaises(TimeoutError):
                await asyncio.wait_for(beyond_capacity.wait(), .025)
            stop.set()
        finally:
            release.set()
            await asyncio.wait_for(task, 2)
        self.assertEqual([int(e['event_id']) for e in store.events], produced)
        self.assertEqual(len(produced), 34)

    async def test_closed_candle_cycle_preserves_gaps_and_stop(self):
        store, stop = FakeStore(), asyncio.Event()
        async def fetch(_client, _now):
            return [{'event_id': 'minute-1'}, {'event_id': 'minute-3'}]
        self.assertEqual(await coinbase_candle_cycle(store, None, stop, fetch=fetch), 2)
        self.assertEqual([e['event_id'] for e in store.events], ['minute-1', 'minute-3'])
        stop.set()
        self.assertEqual(await coinbase_candle_cycle(store, None, stop, fetch=fetch), 0)

    async def test_candle_failure_keeps_operation_without_source_body(self):
        async def failed(_client, _now):
            raise SourceHTTPFailure(429, 'private-url-and-response')
        with self.assertRaises(LiveDiagnostic) as caught:
            await coinbase_candle_cycle(FakeStore(), None, asyncio.Event(), fetch=failed)
        self.assertEqual(caught.exception.code, 'coinbase_candles.http_429')
        self.assertNotIn('private', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
