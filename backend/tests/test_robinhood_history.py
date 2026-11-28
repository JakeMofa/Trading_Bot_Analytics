"""Signed read-only BTC/USD v1, persistence and independent display behavior."""
import asyncio
import base64
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from psycopg import OperationalError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres import robinhood_history as history

PROVIDER_TIME = '2026-11-27T23:02:00.123456789Z'
RESPONSE = {
    'symbol': 'BTC-USD', 'price': '68000.00000000001',
    'bid_inclusive_of_sell_spread': '67900.00', 'ask_inclusive_of_buy_spread': '68100.00',
    'buy_spread': '.001', 'sell_spread': '.001', 'timestamp': PROVIDER_TIME,
}


def fixture_event(requested='2026-11-27T23:02:00.201000Z', received='2026-11-27T23:02:00.230000Z', **changes):
    raw = json.dumps({'results': [{**RESPONSE, **changes}]}).encode()
    return history.price_event({**history.v1_book(raw), 'requested_at': requested, 'received_at': received,
                                'http_round_trip_ms': 29.0})


class RobinhoodReferenceTests(unittest.IsolatedAsyncioTestCase):
    def test_exact_provider_price_timestamp_and_missing_or_crossed_books(self):
        event = fixture_event()
        self.assertEqual(event['price'], RESPONSE['price'])
        self.assertEqual(event['source_time'], PROVIDER_TIME)
        self.assertEqual(event['provenance']['source_time_role'], 'retrieved_by_robinhood')
        self.assertEqual(event['payload']['http_round_trip_ms'], 29)
        self.assertIsNone(fixture_event(price=None)['price'])
        partial = fixture_event(ask_inclusive_of_buy_spread=None, timestamp=None)
        self.assertIsNone(partial['source_time'])
        self.assertEqual(partial['payload']['book_status'], 'partial')
        crossed = fixture_event(bid_inclusive_of_sell_spread='69000')
        self.assertIsNone(crossed['price'])
        self.assertEqual(crossed['payload']['provider_price'], RESPONSE['price'])
        self.assertEqual(json.loads(crossed['raw_payload'])['results'][0]['bid_inclusive_of_sell_spread'], '69000')
        self.assertNotEqual(event['event_id'], fixture_event(requested='2026-11-27T23:02:00.202000Z')['event_id'])
        self.assertEqual(event, fixture_event())

    def test_movement_uses_consecutive_polls_preserving_subcent_changes(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from postgres.quote_session import QuotePipeline
        sender = Mock()
        pipe = QuotePipeline(SimpleNamespace(), sender)
        first = fixture_event()
        pipe.publish_robinhood(first)
        self.assertIsNone(sender.send.call_args.args[0]['reference']['movement'])
        second = fixture_event(requested='2026-11-27T23:02:01.200000Z', received='2026-11-27T23:02:01.230000Z',
                               price='68000.00000000002')
        pipe.publish_robinhood(second)
        movement = sender.send.call_args.args[0]['reference']['movement']
        self.assertEqual(movement['delta_usd'], '0.00000000001')
        self.assertEqual(movement['previous_event_id'], first['event_id'])
        pipe.publish_robinhood(second)
        self.assertEqual(sender.send.call_count, 2)
        previous = pipe.previous_robinhood
        now = {**previous, 'source_time':'2026-11-27T23:02:02Z','received_at':'2026-11-27T23:02:02.1Z'}
        self.assertEqual(history.quote_movement(previous, now)['delta_usd'], '0.00000000000')
        self.assertTrue(history.quote_movement(previous, {**now, 'price_usd':'67000'})['delta_usd'].startswith('-'))
        for invalid in ({'price_usd':None}, {'source_time':None}, {'book_status':'crossed'},
                        {'source_time':'2026-11-27T23:01:59Z'}, {'received_at':'2026-11-27T23:02:20Z'}):
            with self.subTest(change=invalid):
                self.assertIsNone(history.quote_movement(previous, {**now, **invalid}))

    async def test_reuses_client_verifies_v1_signature_obeys_retry_after_and_stops_on_denial(self):
        private = Ed25519PrivateKey.generate()
        key = ('fixture-key', private)
        requests, delays = [], []
        def response(request):
            self.assertEqual(request.method, 'GET')
            self.assertEqual(request.url.raw_path.decode(), history.V1_PATH)
            msg = (key[0] + request.headers['x-timestamp'] + history.V1_PATH + 'GET').encode()
            private.public_key().verify(base64.b64decode(request.headers['x-signature']), msg)
            requests.append(request)
            return httpx.Response(429, headers={'Retry-After':'39'}) if len(requests) == 1 else httpx.Response(403)

        async def capture_delay(stop, delay):
            delays.append(delay)

        stop = asyncio.Event()
        with patch.object(history, 'credentials', return_value=key), patch.object(history, 'pause', capture_delay),                 patch.object(history.httpx, 'AsyncClient', wraps=httpx.AsyncClient) as clients:
            await history.collect(object(), stop, self.fail, transport=httpx.MockTransport(response))
        self.assertEqual(len(requests), 2)
        self.assertEqual(delays, [39])
        self.assertEqual(clients.call_count, 1)
        self.assertFalse(stop.is_set())

    async def test_display_precedes_slow_commit_and_same_event_is_retried(self):
        displayed, ingested = [], []
        writer_waiting, release = threading.Event(), threading.Event()
        stop = asyncio.Event()
        class Store:
            def ingest(self, event):
                ingested.append(event)
                if len(ingested) == 1:
                    writer_waiting.set()
                    if not release.wait(4):
                        raise AssertionError('writer did not resume')
                    raise OperationalError('generated transient failure')
        async def finish(stop, delay):
            stop.set()
        with patch.object(history, 'credentials', return_value=('fixture', Ed25519PrivateKey.generate())),                 patch.object(history, 'pause', finish):
            run = asyncio.create_task(history.collect(Store(), stop, displayed.append, transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={'results':[RESPONSE]}))))
            try:
                self.assertTrue(await asyncio.to_thread(writer_waiting.wait, 2))
                self.assertEqual(len(displayed), 1)
                self.assertFalse(run.done())
            finally:
                release.set()
            await asyncio.wait_for(run, 3)
        self.assertEqual(ingested, [displayed[0], displayed[0]])
