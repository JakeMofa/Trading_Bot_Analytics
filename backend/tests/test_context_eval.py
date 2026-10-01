import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from collector import connect, normalize, save_market
from context_eval import evaluate_context
from features import initialize as initialize_features
from forecasts import MODEL, initialize as initialize_forecasts
from news import initialize as initialize_news

VALUES = {'distance_pct': '0.02', 'realized_volatility_15m': '0.001',
          'return_5m': '0.002', 'seconds_remaining': 300}
QUALITY = {'price': {'status': 'fresh'}, 'candle_status': 'fresh'}
BASE = datetime(2026, 9, 30, tzinfo=timezone.utc)


def stamp(minutes):
    return (BASE + timedelta(minutes=minutes)).isoformat()


def raw(market_id, start, end, status, final=None):
    return {'id': market_id, 'slug': market_id, 'status': status,
            'assetPriceTerms': {'asset': {'symbol': 'btc'},
              'marketType': 'ASSET_PRICE_MARKET_TYPE_UP_DOWN', 'horizon': '15m',
              'windowStart': stamp(start), 'windowEnd': stamp(end),
              'priceToBeat': {'value': '100'},
              'settlementPrice': {'value': final} if final else None}}


class ContextEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.db = connect(':memory:')
        initialize_features(self.db)
        initialize_forecasts(self.db)
        initialize_news(self.db)

    def tearDown(self):
        self.db.close()

    def market(self, name, start, resolved_seen, final='101', prediction=False):
        end = start + 15
        save_market(self.db, normalize(raw(name, start, end, 'MARKET_STATUS_OPEN')),
                    stamp(start + 1))
        at = start + 10
        self.db.execute('''INSERT INTO feature_snapshots
          (market_id,as_of,version,values_json,quality_json,evidence_json)
          VALUES(?,?,?,?,?,?)''', (name, stamp(at), 1, json.dumps(VALUES),
                                   json.dumps(QUALITY), '{}'))
        sid = self.db.execute('SELECT last_insert_rowid()').fetchone()[0]
        if prediction:
            self.db.execute('''INSERT INTO predictions
              (snapshot_id,market_id,model_version,as_of,created_at,
               seconds_remaining,probability_up,probability_down,assumptions_json)
              VALUES(?,?,?,?,?,?,?,?,?)''',
              (sid, name, MODEL, stamp(at), stamp(at+1/60), 300, '.8', '.2', '{}'))
        save_market(self.db, normalize(raw(name, start, end,
                    'MARKET_STATUS_RESOLVED', final)), stamp(resolved_seen))
        return sid

    def test_only_prior_known_cases_and_prior_seen_news_are_counted(self):
        for i in range(5):
            self.market(f'prior{i}', i*15, i*15+20,
                        final='101' if i < 4 else '99')
        # Ended before target, but its result arrived after target forecast.
        self.market('late', 75, 110, final='99')
        self.market('target', 90, 120, final='101', prediction=True)
        self.db.execute('''INSERT INTO news_events
          (source,source_guid,url,title,published_at,first_seen,last_seen,
           categories_json,asset_tag) VALUES(?,?,?,?,?,?,?,?,?)''',
          ('test','a','https://example.com/a','Bitcoin',stamp(95),stamp(99),stamp(99),'[]','BTC'))
        self.db.execute('''INSERT INTO news_events
          (source,source_guid,url,title,published_at,first_seen,last_seen,
           categories_json,asset_tag) VALUES(?,?,?,?,?,?,?,?,?)''',
          ('test','b','https://example.com/b','Bitcoin',stamp(95),stamp(101),stamp(101),'[]','BTC'))
        report = evaluate_context(self.db)['checkpoints']['T-5m']
        self.assertEqual(report['saved_forecasts'], 1)
        self.assertEqual(report['case_count_min'], 5)
        self.assertEqual(report['markets_with_prior_seen_btc_news'], 1)
        self.assertEqual(report['paired_markets_with_at_least_5_cases'], 1)
        self.assertAlmostEqual(report['case_proxy']['brier'], (1-5/7)**2)
        self.assertAlmostEqual(report['saved_baseline_on_same_markets']['brier'], .04)
        self.assertEqual(report['status'], 'insufficient_30_distinct_markets')

    def test_no_prior_cases_does_not_create_proxy_score(self):
        self.market('target', 90, 120, prediction=True)
        report = evaluate_context(self.db)['checkpoints']['T-5m']
        self.assertEqual(report['paired_markets_with_at_least_5_cases'], 0)
        self.assertIsNone(report['case_proxy'])


if __name__ == '__main__':
    unittest.main()
