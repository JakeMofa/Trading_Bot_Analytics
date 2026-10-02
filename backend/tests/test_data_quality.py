import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from collector import connect
from data_quality import report
from history_batch import initialize_batch
from news import initialize as initialize_news


class DataQualityTests(unittest.TestCase):
    def setUp(self):
        self.db = connect(':memory:')
        initialize_batch(self.db)
        initialize_news(self.db)

    def tearDown(self):
        self.db.close()

    def test_separates_before_range_and_unconfirmed_saved_gaps(self):
        self.db.execute('''INSERT INTO markets(id,slug,duration,start,end,target,final,
          result,status,first_seen,last_seen,raw_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
          ('resolved','resolved',900,'2026-10-01T01:00:00Z',
           '2026-10-01T01:15:00Z','100','101','UP','MARKET_STATUS_RESOLVED',
           '2026-10-01T01:15:00Z','2026-10-01T01:20:00Z','{}'))
        self.db.execute('''INSERT INTO markets(id,slug,duration,start,end,target,
          status,first_seen,last_seen,raw_json) VALUES(?,?,?,?,?,?,?,?,?,?)''',
          ('unconfirmed','unconfirmed',900,'2026-10-01T01:15:00Z',
           '2026-10-01T01:30:00Z','100','MARKET_STATUS_OPEN',
           '2026-10-01T01:15:00Z','2026-10-01T01:20:00Z','{}'))
        missing = ['2026-10-01T00:45:00+00:00','2026-10-01T01:15:00+00:00',
                   '2026-10-01T01:30:00+00:00']
        self.db.execute('''INSERT INTO historical_backfill_chunks
          (window_start,window_end,attempted_at,result_json) VALUES(?,?,?,?)''',
          ('2026-10-01T00:00:00Z','2026-10-01T02:00:00Z',
           '2026-10-01T02:01:00Z',json.dumps({'missing_intervals':missing})))
        self.db.execute('''INSERT INTO news_events(source,source_guid,url,title,
          published_at,first_seen,last_seen,categories_json,asset_tag)
          VALUES(?,?,?,?,?,?,?,?,?)''',
          ('test','n','https://example.com/n','BTC',
           '2026-10-01T01:00:00Z','2026-10-01T01:10:00Z',
           '2026-10-01T01:10:00Z','[]','BTC'))
        self.db.execute('''INSERT INTO runs(received_at,source,success,detail)
          VALUES(?,?,?,?)''',('2026-10-01T02:00:00Z','coindesk_rss',1,'{}'))
        result = report(self.db,'2026-10-01T03:00:00Z')
        history = result['historical_15m']
        self.assertEqual(history['missing_before_first_saved_resolved'],1)
        self.assertEqual(history['missing_within_saved_range'],2)
        self.assertEqual(history['within_range_absent_from_saved_markets'],1)
        self.assertEqual(history['within_range_saved_without_confirmed_result'],1)
        self.assertEqual(history['within_range_missing_ranges'][0]['intervals'],2)
        news = result['btc_news']
        self.assertEqual(news['median_publication_to_first_seen_seconds'],600)
        self.assertEqual(news['poll_age_seconds'],3600)

    def test_empty_database_reports_unknown_coverage(self):
        result = report(self.db,'2026-10-01T03:00:00Z')
        self.assertIsNone(result['historical_15m']['earliest_saved_resolved_start'])
        self.assertIsNone(result['btc_news']['median_publication_to_first_seen_seconds'])
        self.assertIsNone(result['btc_news']['poll_age_seconds'])


if __name__ == '__main__':
    unittest.main()
