import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))

from collector import connect, timestamp
from decision import decide_action
from ensemble import (
    MODEL as ENSEMBLE_MODEL,
    compute_ensemble_for_snapshot,
    implied_from_market,
    news_probability,
    research_signal,
)
from forecasts import MODEL as BASELINE_MODEL, forecast_snapshot, initialize as initialize_forecasts
from news import initialize as initialize_news


class EnsemblePhase0Tests(unittest.TestCase):
    def setUp(self):
        self.db = connect(':memory:')
        initialize_forecasts(self.db)
        initialize_news(self.db)
        self.values = {
            'target_usd': '100.00',
            'reference_price_usd': '101.00',
            'seconds_remaining': 300,
            'realized_volatility_15m': '0.002',
            'distance_pct': '1.0',
            'return_5m': '0.001',
        }
        self.quality = {'price': {'status': 'fresh'}, 'candle_status': 'fresh'}
        self.add_market()
        self.snapshot_id = self.add_snapshot()
        forecast_snapshot(self.db, self.snapshot_id, timestamp('2026-09-30T01:10:05Z'))

    def tearDown(self):
        self.db.close()

    def add_market(self, market_id='m', start='2026-09-30T01:00:00Z',
                   end='2026-09-30T01:15:00Z'):
        self.db.execute('''INSERT INTO markets(
          id,slug,duration,start,end,target,status,first_seen,last_seen,raw_json)
          VALUES(?,?,?,?,?,?,?,?,?,?)''',
          (market_id, market_id, 900, start, end, '100', 'MARKET_STATUS_OPEN',
           start, start, '{}'))

    def add_snapshot(self, market_id='m', as_of='2026-09-30T01:10:00Z'):
        self.db.execute('''INSERT INTO feature_snapshots(
          market_id,as_of,version,values_json,quality_json,evidence_json)
          VALUES(?,?,?,?,?,?)''',
          (market_id, as_of, 1, json.dumps(self.values),
           json.dumps(self.quality), '{}'))
        return self.db.execute('SELECT last_insert_rowid()').fetchone()[0]

    def test_missing_components_are_excluded_and_baseline_row_is_preserved(self):
        baseline = self.db.execute('''SELECT id,probability_up,model_version
          FROM predictions WHERE snapshot_id=? AND model_version=?''',
          (self.snapshot_id, BASELINE_MODEL)).fetchone()
        self.assertIsNotNone(baseline)

        result = compute_ensemble_for_snapshot(self.db, self.snapshot_id)
        self.assertAlmostEqual(result['ensemble_up'], float(baseline[1]), places=12)
        self.assertEqual(result['components'], {'baseline': float(baseline[1])})

        rows = self.db.execute('''SELECT model_version,probability_up
          FROM predictions WHERE snapshot_id=? ORDER BY model_version''',
          (self.snapshot_id,)).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual({row[0] for row in rows}, {BASELINE_MODEL, ENSEMBLE_MODEL})
        preserved = self.db.execute('SELECT model_version FROM predictions WHERE id=?',
                                    (baseline[0],)).fetchone()[0]
        self.assertEqual(preserved, BASELINE_MODEL)

    def test_market_probability_uses_saved_real_kinds_and_is_timestamp_safe(self):
        self.db.execute('''INSERT INTO observations(market_id,received_at,kind,payload)
          VALUES(?,?,?,?)''',
          ('m', '2026-09-30T01:09:00Z', 'bbo',
           json.dumps({'marketData': {
               'longQuote': {'value': '0.60'},
               'shortQuote': {'value': '0.40'}}})))
        self.db.execute('''INSERT INTO observations(market_id,received_at,kind,payload)
          VALUES(?,?,?,?)''',
          ('m', '2026-09-30T01:11:00Z', 'stream_book',
           json.dumps({'marketData': {'stats': {'lastPriceSample': {
               'longPx': {'value': '0.90'},
               'shortPx': {'value': '0.10'}}}}})))

        self.assertAlmostEqual(
            implied_from_market(self.db, 'm', '2026-09-30T01:10:00Z'), 0.60)
        self.assertAlmostEqual(
            implied_from_market(self.db, 'm', '2026-09-30T01:12:00Z'), 0.90)

    def test_news_uses_news_events_and_excludes_future_information(self):
        rows = [
            ('past', 'Bitcoin rally continues',
             '2026-09-30T01:05:00Z', '2026-09-30T01:06:00Z'),
            ('future-seen', 'Bitcoin plunge',
             '2026-09-30T01:05:00Z', '2026-09-30T01:11:00Z'),
            ('future-published', 'Bitcoin plunge again',
             '2026-09-30T01:11:00Z', '2026-09-30T01:09:00Z'),
        ]
        for guid, title, published, seen in rows:
            self.db.execute('''INSERT INTO news_events(
              source,source_guid,url,title,published_at,first_seen,last_seen,
              categories_json,asset_tag) VALUES(?,?,?,?,?,?,?,?,?)''',
              ('test', guid, f'https://example.com/{guid}', title, published,
               seen, seen, '[]', 'BTC'))

        self.assertAlmostEqual(
            news_probability(self.db, '2026-09-30T01:10:00Z'), 0.55)

    def test_no_edge_band_does_not_force_direction(self):
        self.assertEqual(research_signal(0.50), 'NO_EDGE')
        self.assertEqual(research_signal(0.53), 'NO_EDGE')
        self.assertEqual(research_signal(0.56), 'BUY_UP')
        self.assertEqual(research_signal(0.44), 'BUY_DOWN')

    def test_decision_logic_does_not_infer_position_from_previous_suggestion(self):
        self.db.execute('''UPDATE predictions SET decision_action='BUY_UP'
          WHERE snapshot_id=? AND model_version=?''',
          (self.snapshot_id, BASELINE_MODEL))
        action, confidence, summary, _hold = decide_action(
            self.db, 'm', {'baseline': 0.10}, 0.10, {'baseline': 1.0})
        self.assertEqual(action, 'BUY_DOWN')
        self.assertNotIn('SELL', action)
        self.assertGreaterEqual(confidence, 0.5)
        self.assertIn(summary, ('BUY', 'BUY_MORE'))


if __name__ == '__main__':
    unittest.main()
