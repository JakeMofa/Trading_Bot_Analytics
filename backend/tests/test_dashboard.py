import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from collector import connect
from dashboard import LiveQuoteRelay, chart_data, compact_live_quote, latest_tick_event, status
from features import initialize as initialize_features
from forecasts import MODEL, initialize as initialize_forecasts
from knowledge import initialize as initialize_knowledge
from news import initialize as initialize_news
from streaming import initialize as initialize_stream


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.db = connect(':memory:')
        initialize_features(self.db)
        initialize_forecasts(self.db)
        initialize_news(self.db)
        initialize_stream(self.db)
        initialize_knowledge(self.db)
        self.now = datetime(2026, 10, 1, 2, 10, tzinfo=timezone.utc)

    def tearDown(self):
        self.db.close()

    def test_empty_database_is_honest(self):
        report = status(self.db, self.now)
        self.assertIsNone(report['market'])
        self.assertIsNone(report['forecast'])
        self.assertIsNone(report['latest_coinbase_tick'])
        self.assertIsNone(report['evidence'])
        self.assertEqual(report['evaluation']['distinct_confirmed_markets_by_checkpoint']['T-5m'], 0)
        self.assertEqual(chart_data(self.db, self.now)['points'], [])

    def test_direct_quote_relay_keeps_last_sample_without_exposing_book(self):
        relay = LiveQuoteRelay()
        first = compact_live_quote({'marketData': {
            'marketSlug': 'btc-market', 'bids': [{'px': {'value': '0.51'}, 'qty': '8'}],
            'offers': [{'px': {'value': '0.53'}, 'qty': '10'}],
            'stats': {'lastPriceSample': {'longPx': {'value': '0.52'},
                                         'shortPx': {'value': '0.48'},
                                         'ts': '2026-10-01T02:09:00Z'}}}},
            'm', 'btc-market', '2026-10-01T02:09:01Z')
        relay.publish(first)
        second = compact_live_quote({'marketData': {
            'marketSlug': 'btc-market', 'bids': [{'px': {'value': '0.54'}}],
            'offers': [{'px': {'value': '0.55'}}]}},
            'm', 'btc-market', '2026-10-01T02:09:02Z')
        relay.publish(second)
        latest = relay.latest()
        self.assertEqual(latest['sequence'], 2)
        self.assertEqual(latest['best_bid'], '0.54')
        self.assertEqual(latest['up_quote'], '0.52')
        self.assertEqual(latest['sample_time'], '2026-10-01T02:09:00Z')
        self.assertNotIn('bids', latest)
        self.assertIsNone(compact_live_quote({'marketData': {'marketSlug': 'other'}},
                                              'm', 'btc-market', '2026-10-01T02:09:02Z'))

    def test_chart_uses_only_saved_ticks_from_current_market(self):
        self.db.execute('''INSERT INTO markets(id,slug,duration,start,end,target,status,
          first_seen,last_seen,raw_json) VALUES(?,?,?,?,?,?,?,?,?,?)''',
          ('m','btc-market',900,'2026-10-01T02:00:00Z','2026-10-01T02:15:00Z',
           '100','MARKET_STATUS_OPEN','2026-10-01T02:00:00Z',
           '2026-10-01T02:00:00Z','{}'))
        for event_id, source_time, received_at, price in (
            ('old','2026-10-01T01:59:59Z','2026-10-01T01:59:59Z','50'),
            ('a','2026-10-01T02:00:01Z','2026-10-01T02:00:01Z','100'),
            ('b','2026-10-01T02:00:03Z','2026-10-01T02:00:03Z','101'),
            ('c','2026-10-01T02:00:06Z','2026-10-01T02:00:06Z','102'),
            ('future','2026-10-01T02:11:00Z','2026-10-01T02:11:00Z','150')):
            self.db.execute('''INSERT INTO stream_events(source,event_id,received_at,
              source_time,price,payload) VALUES(?,?,?,?,?,?)''',
              ('coinbase',event_id,received_at,source_time,price,'{}'))
        self.db.commit()
        self.db.execute('PRAGMA query_only=ON')
        before = self.db.total_changes
        report = chart_data(self.db, self.now)
        self.assertEqual(self.db.total_changes, before)
        self.assertEqual(report['market']['target_usd'], '100')
        self.assertEqual([p['price_usd'] for p in report['points']], ['101','102'])
        self.assertFalse(report['sample_limited'])
        self.assertEqual(latest_tick_event(self.db)['price_usd'], '150')
        self.assertEqual(latest_tick_event(self.db)['source_time'], '2026-10-01T02:11:00Z')

    def test_current_market_forecast_and_stale_feed_are_read_only(self):
        start, end = '2026-10-01T02:00:00Z', '2026-10-01T02:15:00Z'
        self.db.execute('''INSERT INTO markets(id,slug,duration,start,end,target,status,
          first_seen,last_seen,raw_json) VALUES(?,?,?,?,?,?,?,?,?,?)''',
          ('m','btc-market',900,start,end,'100','MARKET_STATUS_OPEN',start,start,'{}'))
        self.db.execute('''INSERT INTO feature_snapshots(market_id,as_of,version,
          values_json,quality_json,evidence_json) VALUES(?,?,?,?,?,?)''',
          ('m','2026-10-01T02:09:00Z',1,
           json.dumps({'reference_price_usd':'101','distance_usd':'1','distance_pct':'1'}),
           json.dumps({'price':{'status':'fresh','source':'coinbase_stream'},
                       'candle_status':'lagging','candle_age_seconds':65,
                       'missing_features':[]}), '{}'))
        sid = self.db.execute('SELECT last_insert_rowid()').fetchone()[0]
        self.db.execute('''INSERT INTO predictions(snapshot_id,market_id,model_version,as_of,
          created_at,seconds_remaining,probability_up,probability_down,assumptions_json)
          VALUES(?,?,?,?,?,?,?,?,?)''',
          (sid,'m',MODEL,'2026-10-01T02:09:00Z','2026-10-01T02:09:02Z',360,'.7','.3','{}'))
        self.db.execute('''INSERT INTO feed_health(source,status,updated_at,last_data_at,
          reconnects,detail) VALUES(?,?,?,?,?,?)''',
          ('coinbase_stream','live','2026-10-01T02:07:00Z',
           '2026-10-01T02:07:00Z',1,'test'))
        self.db.execute('''INSERT INTO observations(market_id,received_at,kind,payload)
          VALUES(?,?,?,?)''',('m','2026-10-01T02:09:30Z','bbo',
                             json.dumps({'marketData':{'longQuote':{'value':'0.57'},
                                                       'shortQuote':{'value':'0.45'}}})))
        self.db.execute('''INSERT INTO stream_events(source,event_id,received_at,
          source_time,price,payload) VALUES(?,?,?,?,?,?)''',
          ('coinbase','trade-1','2026-10-01T02:09:59Z',
           '2026-10-01T02:09:58Z','103','{}'))
        self.db.execute('''INSERT INTO news_events(source,source_guid,url,title,
          published_at,first_seen,last_seen,categories_json,asset_tag)
          VALUES(?,?,?,?,?,?,?,?,?)''',
          ('test','one','https://example.com','Bitcoin headline',
           '2026-10-01T02:05:00Z','2026-10-01T02:06:00Z',
           '2026-10-01T02:06:00Z','[]','BTC'))
        event_id = self.db.execute('SELECT last_insert_rowid()').fetchone()[0]
        prediction_id = self.db.execute('SELECT id FROM predictions').fetchone()[0]
        self.db.execute('''INSERT INTO prediction_context_links
          (prediction_id,kind,news_event_id,method,linked_at)
          VALUES(?,'news',?,'test',?)''',
          (prediction_id,event_id,'2026-10-01T02:09:30Z'))
        self.db.execute('''INSERT INTO markets(id,slug,duration,start,end,target,final,
          result,status,first_seen,last_seen,raw_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
          ('old','old-market',900,'2026-10-01T01:45:00Z','2026-10-01T02:00:00Z',
           '99','100','UP','MARKET_STATUS_RESOLVED',
           '2026-10-01T01:45:00Z','2026-10-01T02:03:00Z','{}'))
        self.db.commit()
        self.db.execute('PRAGMA query_only=ON')
        before = self.db.total_changes
        report = status(self.db, self.now)
        self.assertEqual(self.db.total_changes, before)
        self.assertEqual(report['market']['seconds_remaining'], 300)
        self.assertEqual(report['snapshot']['reference_price_usd'], '101')
        self.assertEqual(report['latest_coinbase_tick']['price_usd'], '103')
        self.assertEqual(report['latest_coinbase_tick']['age_seconds'], 1)
        self.assertEqual(report['snapshot']['candle_age_seconds'], 65)
        self.assertEqual(report['snapshot']['reference_source'], 'coinbase_stream')
        self.assertEqual(report['market_quote']['age_seconds'], 30)
        self.assertEqual(report['market_quote']['up_quote'], '0.57')
        self.assertEqual(report['market_quote']['down_quote'], '0.45')
        self.assertTrue(report['forecast']['current'])
        self.assertEqual(report['forecast']['probability_up'], '.7')
        self.assertEqual(report['feeds'][0]['effective_status'], 'stale')
        self.assertEqual(report['news'][0]['title'], 'Bitcoin headline')
        self.assertEqual(report['outcomes'][0]['result'], 'UP')
        self.assertIsNone(report['outcomes'][0]['t5_forecast_probability_up'])
        self.assertEqual(report['evidence']['news'][0]['title'], 'Bitcoin headline')
        self.assertIn('not used by forecast model', report['evidence']['semantics'])

    def test_old_snapshot_is_marked_stale(self):
        self.db.execute('''INSERT INTO markets(id,slug,duration,start,end,target,status,
          first_seen,last_seen,raw_json) VALUES(?,?,?,?,?,?,?,?,?,?)''',
          ('m','btc-market',900,'2026-10-01T02:00:00Z','2026-10-01T02:15:00Z',
           '100','MARKET_STATUS_OPEN','2026-10-01T02:00:00Z','2026-10-01T02:00:00Z','{}'))
        self.db.execute('''INSERT INTO feature_snapshots(market_id,as_of,version,
          values_json,quality_json,evidence_json) VALUES(?,?,?,?,?,?)''',
          ('m','2026-10-01T02:05:00Z',1,'{}','{}','{}'))
        self.assertFalse(status(self.db, self.now)['snapshot']['current'])

    def test_live_book_exposes_bid_ask_and_timed_price_sample(self):
        start, end = '2026-10-01T02:00:00Z', '2026-10-01T02:15:00Z'
        self.db.execute('''INSERT INTO markets(id,slug,duration,start,end,target,status,
          first_seen,last_seen,raw_json) VALUES(?,?,?,?,?,?,?,?,?,?)''',
          ('m','btc-market',900,start,end,'100','MARKET_STATUS_OPEN',start,start,'{}'))
        payload = {'marketData': {'marketSlug':'btc-market',
            'bids':[{'px':{'value':'0.74'}}], 'offers':[{'px':{'value':'0.75'}}],
            'stats':{'lastPriceSample':{'longPx':{'value':'0.75'},
                                        'shortPx':{'value':'0.25'},
                                        'ts':'2026-10-01T02:09:58Z'}},
            'transactTime':'2026-10-01T02:09:59Z'}}
        self.db.execute('''INSERT INTO observations(market_id,received_at,source_time,kind,payload)
          VALUES(?,?,?,?,?)''', ('m','2026-10-01T02:09:59Z',
            '2026-10-01T02:09:59Z','stream_book',json.dumps(payload)))
        self.db.commit()
        self.db.execute('PRAGMA query_only=ON')
        quote = status(self.db,self.now)['market_quote']
        self.assertEqual(quote['kind'],'stream_book')
        self.assertEqual((quote['best_bid'],quote['best_ask']),('0.74','0.75'))
        self.assertEqual((quote['up_quote'],quote['down_quote']),('0.75','0.25'))
        self.assertEqual(quote['sample_time'],'2026-10-01T02:09:58Z')


if __name__ == '__main__':
    unittest.main()
