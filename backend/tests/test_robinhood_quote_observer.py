"""Official Robinhood v2 BTC/USD reader contract, entirely offline."""
import asyncio
import base64
import json
from pathlib import Path
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class RobinhoodQuoteTests(unittest.TestCase):
    def setUp(self):
        from postgres import robinhood_quote_observer as observer
        self.reader = observer
        self.seed = bytes(range(32))
        self.env = {'ROBINHOOD_API_KEY': 'generated-test-api-key',
                    'ROBINHOOD_PRIVATE_KEY': base64.b64encode(self.seed).decode()}
        self.keys = observer.signing_material(self.env)

    def test_exact_signed_read_and_decimal_midpoint(self):
        import httpx
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        def transport(request):
            self.assertEqual(str(request.url), 'https://trading.robinhood.com/api/v2/crypto/marketdata/best_bid_ask/?symbol=BTC-USD')
            self.assertEqual(request.method, 'GET')
            self.assertEqual(request.content, b'')
            stamp = request.headers['x-timestamp']
            self.assertLess(abs(int(stamp) - time.time()), 5)
            self.assertEqual(request.headers['x-api-key'], self.env['ROBINHOOD_API_KEY'])
            signed = 'generated-test-api-key' + stamp + '/api/v2/crypto/marketdata/best_bid_ask/?symbol=BTC-USDGET'
            Ed25519PrivateKey.from_private_bytes(self.seed).public_key().verify(
                base64.b64decode(request.headers['x-signature']), signed.encode('ascii'))
            return httpx.Response(200, content=b'{"results":[{"symbol":"BTC-USD","bid":90000.00000000000000001,"ask":"90000.00000000000000002"}]}')

        rows = []
        asyncio.run(self.reader.observe(self.keys, .05, 2, emit=rows.append, transport=httpx.MockTransport(transport)))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['midpoint'], '90000.000000000000000015')
        self.assertIsNone(row['source_time'])
        self.assertLessEqual(row['requested_at'], row['received_at'])
        self.assertGreaterEqual(row['http_round_trip_ms'], 0)
        self.assertGreaterEqual(row['receipt_age_ms_at_sample'], 0)
        self.assertNotIn(self.env['ROBINHOOD_API_KEY'], json.dumps(rows))

    def test_errors_rate_limit_and_redirect_cannot_expand_scope(self):
        import httpx
        for status in (401, 403, 429, 302):
            with self.subTest(status=status):
                requests, rows = [], []
                def transport(request):
                    requests.append(request)
                    return httpx.Response(status, headers={'retry-after':'60', 'location':'https://elsewhere.invalid/'},
                                          content=b'private-error-message')
                asyncio.run(self.reader.observe(self.keys, .04, 2, emit=rows.append, transport=httpx.MockTransport(transport)))
                self.assertEqual(len(requests), 1)
                self.assertEqual(rows[0]['http_status'], status)
                self.assertNotIn('private-error-message', json.dumps(rows))

    def test_missing_malformed_or_crossed_books_and_invalid_keys(self):
        for row in ([], [{'symbol':'BTC-USD','bid':'1'}], [{'symbol':'BTC-USD','bid':'2','ask':'1'}],
                    [{'symbol':'ETH-USD','bid':1,'ask':2}], [{'symbol':'BTC-USD','bid':'NaN','ask':2}]):
            with self.assertRaises((ValueError, KeyError)):
                self.reader.book(json.dumps({'results':row}))
        for changes in [{'ROBINHOOD_PRIVATE_KEY':base64.b64encode(b'x'*64).decode()},
                        {'ROBINHOOD_PRIVATE_KEY':'@@'}, {'ROBINHOOD_API_KEY':'bad\nheader'},
                        {'ROBINHOOD_API_KEY':self.env['ROBINHOOD_PRIVATE_KEY']},
                        {'ROBINHOOD_API_KEY':base64.b64encode(
                            self.keys[1].public_key().public_bytes_raw()).decode()}]:
            with self.assertRaises(ValueError):
                self.reader.signing_material(self.env | changes)
