from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))

from live_state import LiveState


class LiveStateTests(unittest.TestCase):
    def setUp(self):
        self.state = LiveState()
        self.state.set_market({
            'id': 'm1',
            'slug': 'btc-up-down-15m',
            'start': '2026-10-21T04:00:00Z',
            'end': '2026-10-21T04:15:00Z',
            'target_usd': '100',
            'status': 'MARKET_STATUS_OPEN',
        })

    def ticker(self, at, price, trade_id):
        return {
            'type': 'ticker',
            'product_id': 'BTC-USD',
            'time': at,
            'price': str(price),
            'trade_id': trade_id,
            'last_size': '0.1',
            'side': 'buy',
        }

    def test_tick_history_builds_live_returns(self):
        self.state.update_coinbase_ticker(
            self.ticker('2026-10-21T04:09:00Z', 100, 1),
            '2026-10-21T04:09:00.100000Z')
        self.state.update_coinbase_ticker(
            self.ticker('2026-10-21T04:10:00Z', 102, 2),
            '2026-10-21T04:10:00.100000Z')
        snap = self.state.snapshot(datetime(2026,10,21,4,10,1,tzinfo=timezone.utc))
        self.assertEqual(snap['coinbase']['price_usd'], 102.0)
        self.assertAlmostEqual(snap['coinbase']['returns']['1m'], 0.02)
        self.assertEqual(snap['market']['seconds_remaining'], 299)

    def test_polymarket_quote_is_market_scoped(self):
        self.assertFalse(self.state.update_polymarket({
            'marketData': {'marketSlug': 'other',
                           'stats': {'lastPriceSample': {'longPx': {'value': '0.9'}}}}
        }, '2026-10-21T04:10:00Z'))
        self.assertTrue(self.state.update_polymarket({
            'marketData': {
                'marketSlug': 'btc-up-down-15m',
                'bids': [{'px': {'value': '0.54'}}],
                'offers': [{'px': {'value': '0.56'}}],
                'stats': {'lastPriceSample': {
                    'longPx': {'value': '0.55'},
                    'shortPx': {'value': '0.45'},
                    'ts': '2026-10-21T04:10:00Z'}},
            }
        }, '2026-10-21T04:10:00.100000Z'))
        quote = self.state.snapshot(
            datetime(2026,10,21,4,10,1,tzinfo=timezone.utc))['polymarket']
        self.assertEqual(quote['best_bid'], 0.54)
        self.assertEqual(quote['best_ask'], 0.56)
        self.assertEqual(quote['up_probability'], 0.55)

    def test_baseline_can_run_from_ram_without_database(self):
        self.state.update_coinbase_ticker(
            self.ticker('2026-10-21T04:10:00Z', 101, 3),
            '2026-10-21T04:10:00.100000Z')
        self.state.set_feature_snapshot(
            'm1', '2026-10-21T04:10:00Z',
            {
                'target_usd': '100',
                'reference_price_usd': '100.5',
                'realized_volatility_15m': '0.002',
                'seconds_remaining': 300,
            },
            {
                'price': {'status': 'fresh'},
                'candle_status': 'fresh',
                'candle_age_seconds': 20,
                'late_join': False,
            },
            snapshot_id=7)
        result = self.state.baseline_forecast(
            datetime(2026,10,21,4,10,1,tzinfo=timezone.utc))
        self.assertEqual(result['source'], 'live_state_ram')
        self.assertGreater(result['probability_up'], 0.5)

    def test_rollover_clears_market_scoped_state_but_keeps_ticks(self):
        self.state.update_coinbase_ticker(
            self.ticker('2026-10-21T04:10:00Z', 101, 3),
            '2026-10-21T04:10:00.100000Z')
        self.state.set_feature_snapshot('m1', '2026-10-21T04:10:00Z',
                                        {'realized_volatility_15m': '0.002'},
                                        {'candle_status': 'fresh'})
        self.state.set_forecast('test', 0.7, as_of='2026-10-21T04:10:00Z')
        self.state.set_market({
            'id': 'm2',
            'slug': 'btc-next',
            'start': '2026-10-21T04:15:00Z',
            'end': '2026-10-21T04:30:00Z',
            'target_usd': '101',
            'status': 'MARKET_STATUS_OPEN',
        })
        snap = self.state.snapshot(
            datetime(2026,10,21,4,15,1,tzinfo=timezone.utc))
        self.assertIsNone(snap['feature_snapshot'])
        self.assertIsNone(snap['forecast'])
        self.assertEqual(snap['coinbase']['price_usd'], 101.0)

    def test_specialist_slots_are_explicitly_missing_until_populated(self):
        snap = self.state.snapshot(
            datetime(2026,10,21,4,10,1,tzinfo=timezone.utc))
        self.assertIn('trade_flow', snap['missing_data'])
        self.assertIn('btc_order_book', snap['missing_data'])
        self.state.set_trade_flow({'signed_volume_delta': 1.2},
                                  '2026-10-21T04:10:00Z')
        self.state.set_order_book({'depth_imbalance': 0.25},
                                  '2026-10-21T04:10:00Z')
        snap = self.state.snapshot(
            datetime(2026,10,21,4,10,1,tzinfo=timezone.utc))
        self.assertEqual(snap['trade_flow']['values']['signed_volume_delta'], 1.2)
        self.assertEqual(snap['order_book']['values']['depth_imbalance'], 0.25)
        self.assertNotIn('trade_flow', snap['missing_data'])
        self.assertNotIn('btc_order_book', snap['missing_data'])

    def test_feed_health_is_memory_resident(self):
        self.state.update_feed_health(
            'coinbase_stream', 'live',
            updated_at='2026-10-21T04:10:01Z',
            last_data_at='2026-10-21T04:10:00Z',
            reconnects=2)
        feed = self.state.snapshot(
            datetime(2026,10,21,4,10,2,tzinfo=timezone.utc))['feeds']['coinbase_stream']
        self.assertEqual(feed['status'], 'live')
        self.assertEqual(feed['reconnects'], 2)


if __name__ == '__main__':
    unittest.main()
