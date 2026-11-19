"""Generated wire tests for default-off read-only PP source clients."""
import asyncio
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import sys
import unittest

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.live_sources import (coinbase_once, discover_polymarket_15m,
                                   fetch_coinbase_closed_candles, fetch_polymarket_bbo)
from postgres.live_diagnostics import SourceHTTPFailure, SourceTransportFailure


NOW = datetime(2026, 11, 15, 12, 5, tzinfo=timezone.utc)


def market(market_id='one'):
    return {'id': market_id, 'slug': 'btc-up-down-' + market_id,
            'status': 'MARKET_STATUS_OPEN',
            'assetPriceTerms': {'asset': {'symbol': 'btc'},
                                'marketType': 'ASSET_PRICE_MARKET_TYPE_UP_DOWN',
                                'horizon': '15m',
                                'windowStart': '2026-11-15T12:00:00Z',
                                'windowEnd': '2026-11-15T12:15:00Z',
                                'priceToBeat': {'value': '100000.1234567890123456789'}}}


class FakeWebsocket:
    def __init__(self, frames):
        self.frames = iter(frames)
        self.sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def send(self, value):
        self.sent.append(json.loads(value))

    async def recv(self):
        return next(self.frames)


class SourceClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_bounded_closed_candles_keep_exact_values_and_missing_intervals(self):
        calls = []
        def handler(request):
            calls.append(request)
            # The current/open bucket and a pre-range bucket are excluded.
            return httpx.Response(200, json=[
                [1763208300, '100.01', '101.09', '100.10', '100.99', '0.1234567890123456789'],
                [1763208240, '99', '101', '100', '100.5', '0.2'],
                [1763208300 - 18 * 60, '90', '91', '90', '91', '1'],
            ])
        at = datetime.fromtimestamp(1763208300, timezone.utc)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            events = await fetch_coinbase_closed_candles(client, at)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].url.params['granularity'], '60')
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event['payload']['close'], '100.5')
        self.assertEqual(event['provenance']['source_time_role'], 'bucket_start_not_last_trade')
        self.assertEqual(event['provenance']['price_role'], 'reference_not_settlement')

    async def test_candle_corruption_and_response_bounds_fail_closed(self):
        at = datetime.fromtimestamp(1763208300, timezone.utc)
        for rows in ([[1763208240, '100', '101', '102', '100', '1']],
                     [[1763208240, '100', '101', '100', '100', '1']] * 2,
                     [[1763208240, '100', '101', '100', '100', '1']] * 26):
            with self.subTest(rows=len(rows)):
                async with httpx.AsyncClient(transport=httpx.MockTransport(
                        lambda _request: httpx.Response(200, json=rows))) as client:
                    with self.assertRaises(ValueError):
                        await fetch_coinbase_closed_candles(client, at)
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, content=b'x' * (1024 * 1024 + 1)))) as client:
            with self.assertRaisesRegex(ValueError, 'exceeds bound'):
                await fetch_coinbase_closed_candles(client, at)

    async def test_coinbase_subscription_preserves_exact_price_and_provenance(self):
        ws = FakeWebsocket([json.dumps({'type': 'ticker', 'product_id': 'BTC-USD',
                                        'trade_id': 42, 'time': '2026-11-15T12:05:00.123456789Z',
                                        'price': '100000.1234567890123456789', 'last_size': '0.00001'})])
        def connect(url, **options):
            self.assertEqual(url, 'wss://ws-feed.exchange.coinbase.com')
            self.assertEqual(options['max_size'], 1024 * 1024)
            return ws
        source = coinbase_once(asyncio.Event(), connector=connect)
        event = await anext(source)
        await source.aclose()
        self.assertEqual(event['price'], '100000.1234567890123456789')
        self.assertEqual(event['source_time'], '2026-11-15T12:05:00.123456789Z')
        self.assertEqual(event['provenance']['price_role'], 'reference_not_settlement')
        self.assertEqual(ws.sent[0]['channels'], ['ticker', 'heartbeat'])

    async def test_discovery_selects_current_15m_and_rejects_ambiguity(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={'markets': [market()]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            event = await discover_polymarket_15m(client, NOW)
        self.assertEqual(event['market_id'], 'one')
        self.assertEqual(event['payload']['target_usd'], '100000.1234567890123456789')
        self.assertEqual(requests[0].url.path, '/v1/markets')
        def ambiguous(_request):
            return httpx.Response(200, json={'markets': [market(), market('two')]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(ambiguous)) as client:
            with self.assertRaisesRegex(ValueError, 'ambiguous'):
                await discover_polymarket_15m(client, NOW)

    async def test_discovery_bounds_and_errors_fail_closed(self):
        for response in (httpx.Response(503), httpx.Response(200, content=b'x' * (1024 * 1024 + 1)),
                         httpx.Response(200, json={'markets': [market()] * 101})):
            with self.subTest(status=response.status_code, length=len(response.content)):
                async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: response)) as client:
                    with self.assertRaises(ValueError):
                        await discover_polymarket_15m(client, NOW)
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, json={'markets': [market()] * 100}))) as client:
            with self.assertRaisesRegex(ValueError, 'pagination limit'):
                await discover_polymarket_15m(client, NOW, max_pages=1)

    async def test_source_status_and_timeout_are_classified_without_response_text(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda _request: httpx.Response(429, text='secret-provider-body'))) as client:
            with self.assertRaises(SourceHTTPFailure) as caught:
                await discover_polymarket_15m(client, NOW)
        self.assertEqual(caught.exception.category, 'http_429')
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda _request: httpx.Response(503, text='secret-provider-body'))) as client:
            with self.assertRaises(SourceHTTPFailure) as caught:
                await fetch_coinbase_closed_candles(client, NOW)
        self.assertEqual(caught.exception.category, 'http_5xx')
        event = {'market_id': 'one', 'payload': {'slug': 'btc-up-down-one'}}
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda _request: httpx.Response(404, text='secret-provider-body'))) as client:
            with self.assertRaises(SourceHTTPFailure) as caught:
                await fetch_polymarket_bbo(client, event)
        self.assertEqual(caught.exception.category, 'http_404')
        def timed_out(_request):
            raise httpx.ReadTimeout('private-url-and-query')
        async with httpx.AsyncClient(transport=httpx.MockTransport(timed_out)) as client:
            with self.assertRaises(SourceTransportFailure) as caught:
                await discover_polymarket_15m(client, NOW)
        self.assertEqual(caught.exception.category, 'timeout')

    async def test_compressed_json_is_decoded_then_bounded(self):
        def compressed(payload):
            return httpx.Response(200, content=gzip.compress(json.dumps(payload).encode()),
                                  headers={'content-encoding': 'gzip'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda _request: compressed({'markets': [market()]}))) as client:
            self.assertEqual((await discover_polymarket_15m(client, NOW))['market_id'], 'one')
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda _request: compressed({'markets': [], 'padding': 'x' * (1024 * 1024 + 1)}))) as client:
            with self.assertRaisesRegex(ValueError, 'exceeds bound'):
                await discover_polymarket_15m(client, NOW)

    async def test_coinbase_error_frame_and_missing_trade_identity_fail_closed(self):
        for frame in ({'type': 'error', 'message': 'untrusted'},
                      {'type': 'ticker', 'product_id': 'BTC-USD',
                       'time': '2026-11-15T12:05:00Z', 'price': '100000'}):
            with self.subTest(frame=frame['type']):
                ws = FakeWebsocket([json.dumps(frame)])
                source = coinbase_once(asyncio.Event(), connector=lambda *_args, **_kw: ws)
                with self.assertRaises(ValueError):
                    await anext(source)
                await source.aclose()

    async def test_real_depth_shape_preserves_best_prices_time_and_raw_payload(self):
        event = {'market_id': 'one', 'payload': {'slug': 'example'}}
        market_data = {'marketSlug': 'example', 'state': 'MARKET_STATE_OPEN',
                       'bids': [{'px': {'value': '0.4600'}}, {'px': {'value': '0.4700'}}],
                       'offers': [{'px': {'value': '0.5100'}}, {'px': {'value': '0.4800'}}],
                       'transactTime': '2026-11-19T07:18:09.966255984Z'}
        def reply(request):
            return (httpx.Response(404) if request.url.path.endswith('/bbo') else
                    httpx.Response(200, json={'marketData': market_data}))
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
            result = await fetch_polymarket_bbo(client, event)
            self.assertEqual(result['payload']['best_bid'], '0.4700')
            self.assertEqual(result['payload']['best_ask'], '0.4800')
            self.assertEqual(result['source_time'], market_data['transactTime'])
            self.assertEqual(result['provenance']['source_time_role'], 'order_book_transaction_time')
            self.assertEqual(json.loads(result['raw_payload']), {'marketData': market_data})
            market_data['bids'] = []
            market_data['offers'] = []
            self.assertIsNone(await fetch_polymarket_bbo(client, event))
            market_data['bids'] = [{'px': {'value': '1.51'}}]
            with self.assertRaisesRegex(ValueError, 'unit interval'):
                await fetch_polymarket_bbo(client, event)
            market_data['bids'] = []
            market_data['transactTime'] = 'not-a-timestamp'
            with self.assertRaisesRegex(ValueError, 'timestamp'):
                await fetch_polymarket_bbo(client, event)

    async def test_bbo_404_fallback_and_wrong_market_hold(self):
        event = {'market_id': 'one', 'payload': {'slug': 'btc-up-down-one'}}
        calls = []
        body = {'marketData': {'marketSlug': 'btc-up-down-one',
                               'lastPriceSample': {'ts': '2026-11-15T12:05:00Z'},
                               'bestBid': {'value': '0.50'}, 'bestAsk': {'value': '0.51'}}}
        def handler(request):
            calls.append(request.url.path)
            if request.url.path.endswith('/bbo'):
                return httpx.Response(404)
            return httpx.Response(200, json=body)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            quote = await fetch_polymarket_bbo(client, event)
        self.assertEqual(quote['payload']['best_ask'], '0.51')
        self.assertEqual([path.rsplit('/', 1)[-1] for path in calls], ['bbo', 'book'])
        body['marketData']['marketSlug'] = 'wrong'
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaisesRegex(ValueError, 'market identity'):
                await fetch_polymarket_bbo(client, event)


if __name__ == '__main__':
    unittest.main()
