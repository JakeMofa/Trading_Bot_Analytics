import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from collector import connect
from dashboard import status
from features import initialize as initialize_features
from forecasts import MODEL, initialize as initialize_forecasts
from news import initialize as initialize_news
from streaming import initialize as initialize_stream


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.db = connect(':memory:')
        initialize_features(self.db)
        initialize_forecasts(self.db)
        initialize_news(self.db)
        initialize_stream(self.db)
        self.now = datetime(2026, 10, 1, 2, 10, tzinfo=timezone.utc)

    def tearDown(self):
        self.db.close()

    def test_empty_database_is_honest(self):
        report = status(self.db, self.now)
        self.assertIsNone(report['market'])
        self.assertIsNone(report['forecast'])
        self.assertEqual(report['evaluation']['distinct_confirmed_markets_by_checkpoint']['T-5m'], 0)

    def test_current_market_forecast_and_stale_feed_are_read_only(self):
        start, end = '2026-10-01T02:00:00Z', '2026-10-01T02:15:00Z'
        self.db.execute('''INSERT INTO markets(id,slug,duration,start,end,target,status,
          first_seen,last_seen,raw_json) VALUES(?,?,?,?,?,?,?,?,?,?)''',
          ('m','btc-market',900,start,end,'100','MARKET_STATUS_OPEN',start,start,'{}'))
        self.db.execute('''INSERT INTO feature_snapshots(market_id,as_of,version,
          values_json,quality_json,evidence_json) VALUES(?,?,?,?,?,?)''',
          ('m','2026-10-01T02:09:00Z',1,
           json.dumps({'reference_price_usd':'101','distance_usd':'1','distance_pct':'1'}),
           json.dumps({'price':{'status':'fresh'},'candle_status':'fresh','missing_features':[]}), '{}'))
        sid = self.db.execute('SELECT last_insert_rowid()').fetchone()[0]
        self.db.execute('''INSERT INTO predictions(snapshot_id,market_id,model_version,as_of,
          created_at,seconds_remaining,probability_up,probability_down,assumptions_json)
          VALUES(?,?,?,?,?,?,?,?,?)''',
          (sid,'m',MODEL,'2026-10-01T02:09:00Z','2026-10-01T02:09:02Z',360,'.7','.3','{}'))
        self.db.execute('''INSERT INTO feed_health(source,status,updated_at,last_data_at,
          reconnects,detail) VALUES(?,?,?,?,?,?)''',
          ('coinbase_stream','live','2026-10-01T02:07:00Z',
           '2026-10-01T02:07:00Z',1,'test'))
        self.db.execute('''INSERT INTO news_events(source,source_guid,url,title,
          published_at,first_seen,last_seen,categories_json,asset_tag)
          VALUES(?,?,?,?,?,?,?,?,?)''',
          ('test','one','https://example.com','Bitcoin headline',
           '2026-10-01T02:05:00Z','2026-10-01T02:06:00Z',
           '2026-10-01T02:06:00Z','[]','BTC'))
        self.db.commit()
        self.db.execute('PRAGMA query_only=ON')
        before = self.db.total_changes
        report = status(self.db, self.now)
        self.assertEqual(self.db.total_changes, before)
        self.assertEqual(report['market']['seconds_remaining'], 300)
        self.assertEqual(report['snapshot']['reference_price_usd'], '101')
        self.assertTrue(report['forecast']['current'])
        self.assertEqual(report['forecast']['probability_up'], '.7')
        self.assertEqual(report['feeds'][0]['effective_status'], 'stale')
        self.assertEqual(report['news'][0]['title'], 'Bitcoin headline')

    def test_old_snapshot_is_marked_stale(self):
        self.db.execute('''INSERT INTO markets(id,slug,duration,start,end,target,status,
          first_seen,last_seen,raw_json) VALUES(?,?,?,?,?,?,?,?,?,?)''',
          ('m','btc-market',900,'2026-10-01T02:00:00Z','2026-10-01T02:15:00Z',
           '100','MARKET_STATUS_OPEN','2026-10-01T02:00:00Z','2026-10-01T02:00:00Z','{}'))
        self.db.execute('''INSERT INTO feature_snapshots(market_id,as_of,version,
          values_json,quality_json,evidence_json) VALUES(?,?,?,?,?,?)''',
          ('m','2026-10-01T02:05:00Z',1,'{}','{}','{}'))
        self.assertFalse(status(self.db, self.now)['snapshot']['current'])


if __name__ == '__main__':
    unittest.main()
