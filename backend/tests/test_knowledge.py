from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from collector import connect, normalize, save_market
from knowledge import initialize, link_eligible_context, trace_prediction


def market(id,start,end,status='MARKET_STATUS_OPEN',final=None):
    return normalize({'id':id,'slug':'cpc-'+id,'status':status,
      'assetPriceTerms':{'asset':{'symbol':'btc'},
        'marketType':'ASSET_PRICE_MARKET_TYPE_UP_DOWN','horizon':'15m',
        'windowStart':start,'windowEnd':end,'priceToBeat':{'value':'100'},
        'settlementPrice':{'value':final} if final else None}})


VALUES={'distance_pct':'0.02','realized_volatility_15m':'0.001',
        'return_5m':'0.002','seconds_remaining':300}
QUALITY={'price':{'status':'fresh'},'candle_status':'fresh'}


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.db=connect(':memory:')
        initialize(self.db)
        with self.db:
            save_market(self.db,market('prior','2026-09-30T01:00:00Z',
              '2026-09-30T01:15:00Z'),'2026-09-30T01:00:10Z')
            save_market(self.db,market('current','2026-09-30T01:30:00Z',
              '2026-09-30T01:45:00Z'),'2026-09-30T01:30:10Z')
            for market_id,as_of in [('prior','2026-09-30T01:05:00Z'),
                                    ('current','2026-09-30T01:35:00Z')]:
                self.db.execute('''INSERT INTO feature_snapshots
                  (market_id,as_of,version,values_json,quality_json,evidence_json)
                  VALUES(?,?,?,?,?,?)''',
                  (market_id,as_of,1,json.dumps(VALUES),json.dumps(QUALITY),'{}'))
            snapshot_id=self.db.execute('''SELECT id FROM feature_snapshots
              WHERE market_id='current' ''').fetchone()[0]
            self.prediction_id=self.db.execute('''INSERT INTO predictions
              (snapshot_id,market_id,model_version,as_of,created_at,
               seconds_remaining,probability_up,probability_down,
               abstain_reason,assumptions_json) VALUES(?,?,?,?,?,?,?,?,?,?)''',
              (snapshot_id,'current','test_v1','2026-09-30T01:35:00Z',
               '2026-09-30T01:35:05Z',300,'0.6','0.4',None,'{}')).lastrowid

    def tearDown(self): self.db.close()

    def add_news(self,guid,seen):
        with self.db:
            self.db.execute('''INSERT INTO news_events
              (source,source_guid,url,title,published_at,first_seen,last_seen,
               categories_json,asset_tag) VALUES(?,?,?,?,?,?,?,?,?)''',
              ('coindesk_rss',guid,'https://www.coindesk.com/'+guid,
               'Bitcoin market update','2026-09-30T01:32:00Z',seen,seen,'[]','BTC'))

    def resolve_prior(self,seen):
        with self.db:
            save_market(self.db,market('prior','2026-09-30T01:00:00Z',
              '2026-09-30T01:15:00Z','MARKET_STATUS_RESOLVED','101'),seen)

    def test_trace_deduplicates_only_context_known_at_forecast_time(self):
        self.add_news('early','2026-09-30T01:34:00Z')
        self.add_news('late','2026-09-30T01:36:00Z')
        self.resolve_prior('2026-09-30T01:20:00Z')
        now=datetime(2026,9,30,1,50,tzinfo=timezone.utc)
        first=link_eligible_context(self.db,self.prediction_id,'bitcoin',now=now)
        second=link_eligible_context(self.db,self.prediction_id,'bitcoin',now=now)
        self.assertEqual((first['new_news_links'],first['new_case_links']),(1,1))
        self.assertEqual((second['new_news_links'],second['new_case_links']),(0,0))
        trace=trace_prediction(self.db,self.prediction_id)
        self.assertEqual(len(trace['news']),1)
        self.assertEqual(trace['news'][0]['first_seen'],'2026-09-30T01:34:00Z')
        self.assertEqual(len(trace['prior_cases']),1)
        self.assertEqual(trace['prior_cases'][0]['observed_outcome'],'UP')
        self.assertIn('not used by forecast model',trace['link_semantics'])
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_later_resolution_and_news_are_not_linked(self):
        self.add_news('late','2026-09-30T01:36:00Z')
        self.resolve_prior('2026-09-30T01:40:00Z')
        result=link_eligible_context(self.db,self.prediction_id,'bitcoin')
        self.assertEqual((result['new_news_links'],result['new_case_links']),(0,0))
        self.assertEqual(trace_prediction(self.db,self.prediction_id)['prior_cases'],[])

    def test_missing_prediction_and_invalid_relation_rejected(self):
        with self.assertRaises(ValueError): link_eligible_context(self.db,999,'bitcoin')
        with self.assertRaises(ValueError):
            link_eligible_context(self.db,self.prediction_id,'bitcoin',
                now=datetime(2026,9,30,1,34,tzinfo=timezone.utc))
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('''INSERT INTO prediction_context_links
              (prediction_id,kind,method,linked_at) VALUES(?,'news','bad',?)''',
              (self.prediction_id,'2026-09-30T01:50:00Z'))

    def test_prediction_snapshot_mismatch_rejected(self):
        self.db.execute('UPDATE predictions SET as_of=? WHERE id=?',
                        ('2026-09-30T01:34:00Z',self.prediction_id))
        with self.assertRaises(ValueError):
            link_eligible_context(self.db,self.prediction_id,'bitcoin')


if __name__=='__main__': unittest.main()
