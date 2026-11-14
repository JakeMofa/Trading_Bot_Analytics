"""Offline PP feed translation; no network or database credentials."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.live_contract import coinbase_ticker, polymarket_market


NOW = '2026-11-13T12:00:01Z'


class LiveContractTests(unittest.TestCase):
    def test_coinbase_exact_price_identity_and_reference_provenance(self):
        raw = {'type': 'ticker', 'product_id': 'BTC-USD', 'trade_id': 42,
               'time': '2026-11-13T12:00:00.123456789Z',
               'price': '100000.1234567890123456789', 'last_size': '0.000000001'}
        event = coinbase_ticker(raw, NOW)
        self.assertEqual(event['price'], raw['price'])
        self.assertEqual(event['source_time'], raw['time'])
        self.assertEqual(event['event_id'], 'exchange-trade-42')
        self.assertEqual(event['provenance']['data_mode'], 'pp_live')
        self.assertEqual(event['provenance']['price_role'], 'reference_not_settlement')
        self.assertEqual(event['raw_payload'], raw)
        self.assertIsNone(coinbase_ticker({'type': 'heartbeat'}, NOW))
        for change in ({'price': 100000.5}, {'price': 'NaN'}, {'last_size': '-1'},
                       {'time': '2026-11-13T12:00:00'}, {'trade_id': None}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                coinbase_ticker({**raw, **change}, NOW)

    def test_market_boundary_identity_and_missing_source_time(self):
        raw = {'id': 'market-42', 'slug': 'btc-up-down-15m', 'status': 'MARKET_STATUS_OPEN',
               'assetPriceTerms': {'asset': {'symbol': 'BTC'},
                   'marketType': 'ASSET_PRICE_MARKET_TYPE_UP_DOWN', 'horizon': '15m',
                   'windowStart': '2026-11-13T12:00:00Z',
                   'windowEnd': '2026-11-13T12:15:00Z',
                   'priceToBeat': {'value': '100000.00000000000001'}}}
        event = polymarket_market(raw, NOW)
        self.assertEqual(event['market_id'], raw['id'])
        self.assertEqual(event['payload']['target_usd'], '100000.00000000000001')
        self.assertIsNone(event['source_time'])
        self.assertFalse(event['provenance']['source_time_present'])
        self.assertEqual(polymarket_market(raw, NOW)['event_id'], event['event_id'])
        self.assertIsNone(polymarket_market({**raw, 'assetPriceTerms':
            {**raw['assetPriceTerms'], 'horizon': '1h'}}, NOW))
        for change in ({'windowEnd': '2026-11-13T12:14:59Z'},
                       {'priceToBeat': {'value': 100000.0}},
                       {'priceToBeat': {'value': '-1'}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                polymarket_market({**raw, 'assetPriceTerms': {**raw['assetPriceTerms'], **change}}, NOW)


if __name__ == '__main__':
    unittest.main()
