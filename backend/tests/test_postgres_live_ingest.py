"""Network-free PP live bridge tests; no test enables the real collector."""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.live_ingest import coinbase_candle_cycle, coinbase_session, polymarket_cycle
from postgres.live_diagnostics import LiveDiagnostic, SourceHTTPFailure
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

    async def test_discovery_http_status_and_missing_market_are_distinct(self):
        store = FakeStore()
        async def missing(*_):
            return None
        self.assertIsNone(await polymarket_cycle(store, None, asyncio.Event(), discover=missing))
        async def rejected(*_):
            raise SourceHTTPFailure(503, 'private-response-body')
        with self.assertRaises(LiveDiagnostic) as caught:
            await polymarket_cycle(store, None, asyncio.Event(), discover=rejected)
        self.assertEqual(caught.exception.code, 'polymarket_discovery.http_5xx')
        self.assertNotIn('private', str(caught.exception))

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
