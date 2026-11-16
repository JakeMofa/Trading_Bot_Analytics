"""Generated wire tests for default-off read-only PP source clients."""
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.live_sources import coinbase_once, discover_polymarket_15m


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


if __name__ == '__main__':
    unittest.main()
