"""Offline PP feed translation; no network or database credentials."""
import sys
import json
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.live_contract import coinbase_ticker, polymarket_bbo, polymarket_market


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
        self.assertEqual(json.loads(event['raw_payload']), raw)
        self.assertEqual(coinbase_ticker(raw, NOW, raw_wire=' {"original":true} ')['raw_payload'],
                         ' {"original":true} ')
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
        self.assertEqual(json.loads(event['raw_payload']), raw)
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

    def test_bbo_exact_quote_prices_are_not_probabilities(self):
        market = {'market_id': 'market-42', 'payload': {'slug': 'btc-up-down-15m'}}
        raw = {'marketData': {'marketSlug': 'btc-up-down-15m',
                             'lastPriceSample': {'ts': '2026-11-13T12:00:00.123456789Z'},
                             'bestBid': {'currency': 'USD', 'value': '0.510000000000000001'},
                             'bestAsk': {'currency': 'USD', 'value': '0.530000000000000001'},
                             'longQuote': {'currency': 'USD', 'value': '0.52'},
                             'shortQuote': {'currency': 'USD', 'value': '0.48'}}}
        event = polymarket_bbo(raw, market, NOW)
        self.assertEqual(event['payload']['best_bid'], '0.510000000000000001')
        self.assertIsNone(event['payload']['up_probability'])
        self.assertEqual(event['source_time'], '2026-11-13T12:00:00.123456789Z')
        self.assertEqual(json.loads(event['raw_payload']), raw)
        self.assertEqual(event['provenance']['source_time_role'], 'last_price_sample_not_book_update')
        with self.assertRaisesRegex(ValueError, 'market identity'):
            polymarket_bbo({'marketData': {**raw['marketData'], 'marketSlug': 'other'}}, market, NOW)
        with self.assertRaisesRegex(ValueError, 'unit interval'):
            polymarket_bbo({'marketData': {**raw['marketData'],
                                            'bestBid': {'value': '1.01'}}}, market, NOW)


if __name__ == '__main__':
    unittest.main()
