import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from audit import audit
from collector import connect
from features import initialize as initialize_features
from forecasts import initialize as initialize_forecasts


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.db=connect(':memory:')
        initialize_features(self.db)
        initialize_forecasts(self.db)
        self.since='2026-10-01T01:00:00Z'
        self.until='2026-10-01T02:00:00Z'

    def tearDown(self): self.db.close()

    def market(self, market_id, start, end, result=None):
        self.db.execute('''INSERT INTO markets(id,slug,duration,start,end,target,final,
          result,status,first_seen,last_seen,raw_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
          (market_id,market_id,900,start,end,'100', '101' if result else None,
           result,'MARKET_STATUS_RESOLVED' if result else 'MARKET_STATUS_OPEN',
           start,start,'{}'))
        self.db.execute('''INSERT INTO observations(market_id,received_at,kind,payload)
          VALUES(?,?,?,?)''',(market_id,start,'metadata','{}'))

    def snapshot(self, market_id, at, quality):
        self.db.execute('''INSERT INTO feature_snapshots(market_id,as_of,version,
          values_json,quality_json,evidence_json) VALUES(?,?,?,?,?,?)''',
          (market_id,at,1,'{}',json.dumps(quality),'{}'))
        return self.db.execute('SELECT last_insert_rowid()').fetchone()[0]

    def test_rollover_coverage_failures_and_abstentions(self):
        self.market('a','2026-10-01T01:00:00Z','2026-10-01T01:15:00Z','UP')
        self.market('b','2026-10-01T01:15:00Z','2026-10-01T01:30:00Z')
        self.market('old','2026-10-01T00:00:00Z','2026-10-01T00:15:00Z','DOWN')
        self.db.execute('''INSERT INTO observations(market_id,received_at,kind,payload)
          VALUES(?,?,?,?)''',('old','2026-10-01T01:20:00Z','metadata','{}'))
        good={'price':{'status':'fresh'},'candle_status':'fresh','missing_features':[]}
        bad={'price':{'status':'stale'},'candle_status':'missing_or_stale',
             'missing_features':['distance_usd','return_15m']}
        first=self.snapshot('a','2026-10-01T01:10:00Z',good)
        second=self.snapshot('b','2026-10-01T01:15:30Z',bad)
        for sid,market,at,p,reason in ((first,'a','2026-10-01T01:10:00Z','.7',None),
                                       (second,'b','2026-10-01T01:15:30Z',None,'stale')):
            self.db.execute('''INSERT INTO predictions(snapshot_id,market_id,model_version,
              as_of,created_at,seconds_remaining,probability_up,abstain_reason,assumptions_json)
              VALUES(?,?,?,?,?,?,?,?,?)''',
              (sid,market,'test',at,at,300,p,reason,'{}'))
        self.db.execute('''INSERT INTO runs(received_at,source,success,detail)
          VALUES(?,?,?,?)''',('2026-10-01T01:20:00Z','coinbase_candle_refresh',0,'timeout'))
        report=audit(self.db,self.since,self.until)
        self.assertEqual(report['markets']['seen'],2)
        self.assertEqual(report['markets']['rollovers_observed'],1)
        self.assertEqual(report['markets']['confirmed'],1)
        self.assertEqual(report['markets']['outcomes'],{'UP':1,'unconfirmed':1})
        self.assertEqual(report['features']['complete_snapshots'],1)
        self.assertEqual(report['features']['missing_feature_counts']['return_15m'],1)
        self.assertEqual(report['features']['gaps_over_90_seconds'],1)
        self.assertEqual(report['forecasts']['abstentions'],1)
        self.assertEqual(report['recorded_failures']['coinbase_candle_refresh'],1)
        self.assertEqual(report['failure_breakdown']['live_request_errors_by_source'],
                         {'coinbase_candle_refresh':1})
        self.db.execute("UPDATE markets SET last_seen='2026-10-01T03:00:00Z' WHERE id='a'")
        historical=audit(self.db,self.since,self.until)
        self.assertEqual(historical['markets']['confirmed'],0)

    def test_empty_window_and_invalid_order(self):
        report=audit(self.db,self.since,self.until)
        self.assertEqual(report['markets']['seen'],0)
        self.assertIsNone(report['features']['largest_snapshot_gap_seconds'])
        with self.assertRaises(ValueError): audit(self.db,self.until,self.since)

    def test_failure_breakdown_keeps_missing_history_separate_from_live_errors(self):
        entries = [
            ('polymarket_history',json.dumps({'missing_intervals':['old-window'],
                                              'price_history_failures':[]})),
            ('polymarket_history',json.dumps({'missing_intervals':['another'],
                                              'price_history_failures':['timeout']})),
            ('polymarket_quotes','market endpoint=book: HTTP Error 404: Not Found'),
            ('polymarket_discovery','timed out')]
        for source,detail in entries:
            self.db.execute('''INSERT INTO runs(received_at,source,success,detail)
              VALUES(?,?,0,?)''',(self.since,source,detail))
        report=audit(self.db,self.since,self.until)
        self.assertEqual(report['recorded_failures'],
                         {'polymarket_history':2,'polymarket_quotes':1,'polymarket_discovery':1})
        breakdown=report['failure_breakdown']
        self.assertEqual(breakdown['history_missing_interval_window_reports'],2)
        self.assertEqual(breakdown['history_price_request_failure_reports'],1)
        self.assertEqual(breakdown['quote_book_404_requests'],1)
        self.assertEqual(breakdown['live_request_errors_by_source'],
                         {'polymarket_discovery':1})


if __name__=='__main__': unittest.main()
