import json
from decimal import Decimal
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from collector import connect, normalize, save_market, timestamp, refresh_recent_candles
from streaming import initialize as initialize_stream
from features import initialize, calculate, capture


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.db = connect(':memory:')
        initialize_stream(self.db)
        initialize(self.db)
        self.raw = {'id': 'm1', 'slug': 'btc-test', 'status': 'MARKET_STATUS_OPEN',
                    'assetPriceTerms': {'asset': {'symbol': 'btc'},
                    'marketType': 'ASSET_PRICE_MARKET_TYPE_UP_DOWN', 'horizon': '15m',
                    'windowStart': '2026-09-30T01:00:00Z',
                    'windowEnd': '2026-09-30T01:15:00Z',
                    'priceToBeat': {'value': '100.00'}}}
        with self.db:
            save_market(self.db, normalize(self.raw), '2026-09-30T01:05:00+00:00')

    def tearDown(self):
        self.db.close()

    def event(self, id, source_time, received_at, price):
        self.db.execute('''INSERT INTO stream_events VALUES(?,?,?,?,?,?,?,?)''',
                        ('coinbase', str(id), received_at, source_time, price,
                         '1', None, '{}'))

    def candles(self, skip=()):
        base = int(timestamp('2026-09-30T00:53:00Z').timestamp())
        for i in range(17):
            if i in skip:
                continue
            self.db.execute('''INSERT INTO candles(source,symbol,granularity,time,low,high,open,close,volume,first_seen)
              VALUES(?,?,?,?,?,?,?,?,?,?)''',
              ('coinbase', 'BTC-USD', 60, base+i*60,
               '99','102','100',str(100+i),'2','2026-09-30T01:10:00Z'))

    def test_exact_distance_time_and_reproducible_snapshot(self):
        self.event(1, '2026-09-30T01:10:20Z', '2026-09-30T01:10:21Z', '101.25')
        at = timestamp('2026-09-30T01:10:25Z')
        market, values, quality = capture(self.db, at)
        self.assertEqual(market, 'm1')
        self.assertEqual(values['distance_usd'], '1.25')
        self.assertEqual(values['distance_pct'], '1.2500')
        self.assertEqual(values['seconds_remaining'], 275)
        self.assertEqual(quality['price']['source'], 'coinbase_stream')
        self.assertTrue(quality['late_join'])
        self.assertEqual(calculate(self.db, market, at)[:2], (values, quality))
        capture(self.db, at)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM feature_snapshots').fetchone()[0],1)

    def test_candles_backfilled_later_do_not_leak_into_old_snapshot(self):
        self.candles()
        self.db.execute("UPDATE candles SET first_seen='2026-09-30T01:11:00Z'")
        values, quality, _ = calculate(self.db,'m1',timestamp('2026-09-30T01:10:30Z'))
        self.assertIsNone(values['return_15m'])
        self.assertEqual(quality['candle_status'],'missing_or_stale')

    def test_stale_and_future_or_late_inputs_are_excluded(self):
        self.event(1, '2026-09-30T01:09:00Z', '2026-09-30T01:09:01Z', '101')
        self.event(2, '2026-09-30T01:10:20Z', '2026-09-30T01:11:00Z', '110')
        self.event(3, '2026-09-30T01:11:00Z', '2026-09-30T01:10:01Z', '120')
        values, quality, _ = calculate(self.db,'m1',timestamp('2026-09-30T01:10:25Z'))
        self.assertIsNone(values['reference_price_usd'])
        self.assertIsNone(values['distance_usd'])
        self.assertEqual(quality['price']['status'],'stale')

    def test_metadata_target_must_be_known_at_snapshot_time(self):
        self.db.execute("DELETE FROM observations WHERE kind='metadata'")
        self.assertIsNone(calculate(self.db,'m1',timestamp('2026-09-30T01:10:00Z')))
        self.db.execute('INSERT INTO observations(market_id,received_at,kind,payload) VALUES(?,?,?,?)',
                        ('m1','2026-09-30T01:11:00Z','metadata',json.dumps(self.raw)))
        self.assertIsNone(calculate(self.db,'m1',timestamp('2026-09-30T01:10:00Z')))

    def test_complete_candles_and_gap_flags(self):
        self.candles()
        values, quality, _ = calculate(self.db,'m1',timestamp('2026-09-30T01:10:30Z'))
        self.assertEqual(values['return_1m'], str(Decimal(116)/Decimal(115)-1))
        self.assertEqual(values['volume_btc_5m'],'10')
        self.assertEqual(values['volume_btc_15m'],'30')
        self.assertIsNotNone(values['realized_volatility_15m'])
        _, _, evidence = calculate(self.db,'m1',timestamp('2026-09-30T01:10:30Z'))
        self.assertEqual(len(evidence['candle_inputs']),17)
        self.db.execute("DELETE FROM candles WHERE time=?", (int(timestamp('2026-09-30T01:07:00Z').timestamp()),))
        values, quality, _ = calculate(self.db,'m1',timestamp('2026-09-30T01:10:30Z'))
        self.assertIsNone(values['return_5m'])
        self.assertIsNone(values['return_15m'])
        self.assertIsNone(values['volume_btc_5m'])
        self.assertIsNone(values['realized_volatility_15m'])
        self.assertIn('return_5m',quality['missing_features'])

    def test_one_minute_candle_lag_is_visible(self):
        self.candles()
        values, quality, _ = calculate(self.db,'m1',timestamp('2026-09-30T01:11:30Z'))
        self.assertEqual(quality['candle_status'],'lagging')
        self.assertEqual(quality['candle_age_seconds'],90)
        self.assertIsNotNone(values['return_15m'])
        values, quality, _ = calculate(self.db,'m1',timestamp('2026-09-30T01:12:01Z'))
        self.assertEqual(quality['candle_status'],'missing_or_stale')
        self.assertIsNone(values['return_15m'])

    def test_recent_candle_refresh_excludes_unfinished_minute(self):
        now = timestamp('2026-09-30T01:10:30Z')
        base = int(timestamp('2026-09-30T00:50:00Z').timestamp())
        rows = [[base+i*60, 99, 101, 100, 100, 2] for i in range(21)]
        with patch('collector.utcnow', return_value=now), patch('collector.get_json', return_value=rows) as fetch:
            coverage = refresh_recent_candles(self.db)
        self.assertEqual(coverage['stored_minutes'],20)
        self.assertEqual(self.db.execute('SELECT MAX(time) FROM candles').fetchone()[0],base+19*60)
        self.assertEqual(fetch.call_args.args[1],'/products/BTC-USD/candles')

    def test_boundary_and_earlier_than_first_seen(self):
        self.assertIsNone(capture(self.db,timestamp('2026-09-30T01:04:00Z')))
        self.assertIsNone(capture(self.db,timestamp('2026-09-30T01:15:00Z')))


if __name__ == '__main__': unittest.main()
