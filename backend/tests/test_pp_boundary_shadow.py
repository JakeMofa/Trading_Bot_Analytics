"""Offline evidence-path regressions. No PP connection, secret, or durable database."""
import asyncio
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres import boundary_shadow as shadow
from postgres.boundary_report import summary
from postgres.live_contract import QuoteContractError

START = 1800000000


def market(slug, start=START):
    return {'id': slug + '-id', 'slug': slug, 'status': 'MARKET_STATUS_OPEN', 'assetPriceTerms': {
        'asset': {'symbol': 'BTC'}, 'marketType': 'ASSET_PRICE_MARKET_TYPE_UP_DOWN',
        'horizon': '15m', 'windowStart': shadow.utc(start), 'windowEnd': shadow.utc(start + 900)}}


def observed(offset=0):
    return {'ts_utc': shadow.utc(START + offset), 'mono_ns': int((1000 + offset) * 1e9)}


class ShadowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.trace = shadow.Boundary(START, self.output)
        self.trace.market = shadow.polymarket_market(market('next'), shadow.utc(START))

    def rows(self):
        return [json.loads(line) for line in self.output.getvalue().splitlines()]

    async def test_socket_preflight_uses_mounted_credentials_and_reports_only_status(self):
        with patch.dict(shadow.os.environ, {}, clear=True), patch.object(shadow, 'connect') as connect:
            self.assertEqual(await shadow.check_market_socket(), {'status': 'pp_key_files_unbound'})
            connect.assert_not_called()

        files = {'POLYMARKET_KEY_ID_FILE': '/mounted/id',
                 'POLYMARKET_SECRET_KEY_FILE': '/mounted/key'}
        with patch.dict(shadow.os.environ, files, clear=True), \
                patch.object(shadow, 'signing_key', side_effect=OSError('private failure')):
            self.assertEqual(await shadow.check_market_socket(), {'status': 'pp_key_files_unusable'})
        with patch.dict(shadow.os.environ, files, clear=True), \
                patch.object(shadow, 'signing_key', return_value=object()), \
                patch.object(shadow, 'headers', return_value={'X-PM-Access-Key': 'test-value'}), \
                patch.object(shadow, 'connect') as connect:
            self.assertEqual(await shadow.check_market_socket(),
                             {'status': 'pp_market_socket_authenticated'})
            self.assertEqual(connect.call_args.args, (shadow.WS_URL,))
            self.assertIsNone(connect.call_args.kwargs['proxy'])
            connect.return_value.__aenter__.return_value.send.assert_not_called()

    async def test_future_catalog_uses_typed_identity_without_assuming_listing(self):
        def route(request):
            self.assertNotIn('active', request.url.params)
            return httpx.Response(200, json={'markets': [market('current', START - 900),
                market('next'), market('unrelated', START + 900)]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(route)) as client:
            found = await shadow.catalog(client, self.trace)
        self.assertEqual(set(found), {START - 900, START})
        self.assertEqual(found[START]['market_id'], 'next-id')
        for rows, ambiguous in [([market('one'), market('two')], True), ([], False)]:
            async with httpx.AsyncClient(transport=httpx.MockTransport(
                    lambda _: httpx.Response(200, json={'markets': rows}))) as client:
                if ambiguous:
                    with self.assertRaisesRegex(ValueError, 'ambiguous'):
                        await shadow.catalog(client, self.trace)
                else:
                    self.assertEqual({}, await shadow.catalog(client, self.trace))

    async def test_rest_404_fallback_empty_one_sided_wrong_slug_and_429(self):
        raw = {'marketData': {'marketSlug': 'next', 'bids': [{'px': {'value': '0.333333333333333333'}}],
                              'offers': [], 'transactTime': shadow.utc(START)}}
        def route(request):
            if request.url.path.endswith('/bbo'):
                return httpx.Response(404)
            return httpx.Response(200, json=raw)
        async with httpx.AsyncClient(transport=httpx.MockTransport(route)) as client:
            await shadow.rest_once(client, self.trace)
            last = self.rows()[-1]
            self.assertEqual(('quote', 'one', '0.333333333333333333', 'order_book_transaction_time'),
                             (last['stage'], last['sides'], last['best_bid'], last['source_time_role']))
            raw['marketData']['bids'] = []
            await shadow.rest_once(client, self.trace)
            self.assertEqual(self.rows()[-1]['stage'], 'empty')
            raw['marketData']['marketSlug'] = 'previous'
            with self.assertRaises(QuoteContractError):
                await shadow.rest_once(client, self.trace)
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(429))) as client:
            with self.assertRaises(shadow.HttpStatus):
                await shadow.rest_once(client, self.trace)
            self.assertEqual(self.rows()[-1]['status'], 429)

    async def test_stream_preserves_one_sided_two_sided_and_both_sides_of_boundary(self):
        # Stream sampling must preserve the earliest usable received book even at
        # a boundary with unchanged prices, and the first confirmed in-window book.
        fields = {'sides': 'one', 'best_bid': '.4', 'best_ask': None, 'source_time': shadow.utc(START - 10)}
        for offset in (-1, 1, 1.2):
            self.trace.ws_sample('quote', fields, observed(offset))
        self.trace.ws_sample('quote', {**fields, 'source_time': shadow.utc(START)}, observed(1.3))
        self.trace.ws_sample('quote', {**fields, 'sides': 'two', 'best_ask': '.5'}, observed(1.4))
        self.assertEqual([row['ts_utc'] for row in self.rows()],
                         [shadow.utc(START + i) for i in (-1, 1, 1.3, 1.4)])

    async def test_ws_reconnect_resubscribes_after_server_disconnect(self):
        class Socket:
            def __init__(self, attempt):
                self.attempt = attempt
            async def __aenter__(self):
                return self
            async def __aexit__(self, *_):
                pass
            async def send(self, wire):
                requests.append(json.loads(wire)['subscribe'])
            async def recv(self):
                if self.attempt == 1:
                    raise OSError('closed')
                if self.attempt == 2:
                    self.attempt = 3
                    return json.dumps({'marketData': {'marketSlug':'next','bids':[],
                                                      'offers':[{'px':{'value':'.75'}}]}})
                raise asyncio.CancelledError
        requests = []
        sockets = iter([Socket(1), Socket(2)])
        with patch.object(shadow, 'headers', return_value={}), patch.object(shadow, 'connect',
                side_effect=lambda *a, **kw: next(sockets)), patch('asyncio.sleep'):
            with self.assertRaises(asyncio.CancelledError):
                await shadow.websocket(self.trace, {START: self.trace.market}, ('unused', None))
        self.assertEqual(len(requests), 2)
        self.assertNotEqual(requests[0]['requestId'], requests[1]['requestId'])
        self.assertEqual(requests[1]['marketSlugs'], ['next'])
        self.assertIn('reconnect', [r['stage'] for r in self.rows()])
        self.assertEqual(self.rows()[-1]['best_ask'], '.75')

    async def test_report_requires_same_displayed_quote_and_market(self):
        def row(reader, stage, offset, **fields):
            return {**observed(offset), 'reader':reader, 'stage':stage, 'window_start':shadow.utc(START),
                    'market_id':'next-id', 'slug':'next', **fields}
        prices = {'best_bid':'0.41', 'best_ask':None, 'received_at':shadow.utc(START + 4)}
        canonical = [row('canonical_rest', 'bbo_received', 4.1, **prices, event_id='a'),
                     row('canonical_rest', 'commit_ack', 4.5, **prices, event_id='a')]
        early = [row('early_rest','quote',-2, best_bid='0.38'),
                 row('early_rest','quote',2, best_bid='0.39'),
                 row('websocket','quote',1.1, best_bid='0.40', source_time=shadow.utc(START - 8),
                     source_time_role='order_book_transaction_time'),
                 row('dashboard_api','quote',5, **prices), row('observer','window_end',300)]
        result = list(summary(START,canonical,early))
        self.assertEqual(len(result),4)
        self.assertTrue(result[0]['three_reader_match'])
        self.assertEqual(result[0]['canonical_minus_early_rest_ms'],2000)
        self.assertEqual(result[0]['displayed_receive_to_api_ms'],1000)
        self.assertTrue(result[0]['displayed_within_5s'])
        self.assertIsNone(result[0]['ws_first_in_window_exchange_book_utc'])
        self.assertIsNone(result[1]['websocket_first_utc'])
        early[3]['received_at'] = shadow.utc(START + 4.2)
        self.assertIsNone(list(summary(START,canonical,early))[0]['displayed_within_5s'])
        early[1]['market_id'] = 'different'
        self.assertFalse(list(summary(START,canonical,early))[0]['three_reader_match'])


if __name__ == '__main__':
    unittest.main()
