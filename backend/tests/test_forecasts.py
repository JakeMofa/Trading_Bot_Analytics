import json
from datetime import timedelta
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from collector import connect, timestamp
from forecasts import MODEL, baseline, evaluate, forecast_snapshot, initialize


class ForecastTests(unittest.TestCase):
    def setUp(self):
        self.db = connect(':memory:')
        initialize(self.db)
        self.values = {'target_usd':'100.00','reference_price_usd':'101.00',
                       'seconds_remaining':300,'realized_volatility_15m':'0.002'}
        self.quality = {'price':{'status':'fresh'},'candle_status':'fresh'}

    def tearDown(self): self.db.close()

    def add_market(self, market_id='m', start='2026-09-30T01:00:00Z',
                   end='2026-09-30T01:15:00Z', result=None, status='MARKET_STATUS_OPEN'):
        self.db.execute('''INSERT INTO markets(id,slug,duration,start,end,target,final,result,status,
          first_seen,last_seen,raw_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
          (market_id,market_id,900,start,end,'100','101' if result else None,result,
           status,start,start,'{}'))

    def add_snapshot(self, market_id='m', as_of='2026-09-30T01:10:00Z',
                     values=None, quality=None):
        self.db.execute('''INSERT INTO feature_snapshots(market_id,as_of,version,
          values_json,quality_json,evidence_json) VALUES(?,?,?,?,?,?)''',
          (market_id,as_of,1,json.dumps(values or self.values),
           json.dumps(quality or self.quality),'{}'))
        return self.db.execute('SELECT last_insert_rowid()').fetchone()[0]

    def test_baseline_direction_and_abstention(self):
        p, reason = baseline(self.values,self.quality)
        self.assertIsNone(reason)
        self.assertGreater(p,.5)
        equal = dict(self.values,reference_price_usd='100.00')
        self.assertEqual(baseline(equal,self.quality)[0],.5)
        stale = {'price':{'status':'stale'},'candle_status':'fresh'}
        self.assertEqual(baseline(self.values,stale)[1],'reference_price_not_fresh')
        self.assertIsNone(baseline(dict(self.values,realized_volatility_15m=None),self.quality)[0])

    def test_live_forecast_linked_and_no_retroactive_issuance(self):
        self.add_market()
        sid=self.add_snapshot()
        now=timestamp('2026-09-30T01:10:10Z')
        result=forecast_snapshot(self.db,sid,now)
        self.assertIsNotNone(result['probability_up'])
        self.assertEqual(forecast_snapshot(self.db,sid,now),result)
        row=self.db.execute('SELECT snapshot_id,model_version,created_at FROM predictions').fetchone()
        self.assertEqual(row,(sid,MODEL,now.isoformat()))
        self.assertEqual(self.db.execute('SELECT count(*) FROM predictions').fetchone()[0],1)
        sid2=self.add_snapshot(as_of='2026-09-30T01:11:00Z')
        self.assertIsNone(forecast_snapshot(self.db,sid2,timestamp('2026-09-30T01:15:01Z')))

    def test_abstention_is_saved(self):
        self.add_market()
        sid=self.add_snapshot(quality={'price':{'status':'stale'},'candle_status':'fresh'})
        result=forecast_snapshot(self.db,sid,timestamp('2026-09-30T01:10:10Z'))
        self.assertIsNone(result['probability_up'])
        self.assertEqual(self.db.execute('SELECT abstain_reason FROM predictions').fetchone()[0],
                         'reference_price_not_fresh')

    def test_evaluation_groups_by_market_and_uses_confirmed_only(self):
        self.add_market(result='UP',status='MARKET_STATUS_RESOLVED')
        self.add_market('pending',result=None)
        self.add_market('late',result='DOWN',status='MARKET_STATUS_RESOLVED')
        for market_id,p,as_of,created in (
            ('m','.8','2026-09-30T01:10:00Z','2026-09-30T01:10:02Z'),
            ('m','.9','2026-09-30T01:10:20Z','2026-09-30T01:10:22Z'),
            ('pending','.1','2026-09-30T01:10:00Z','2026-09-30T01:10:02Z'),
            ('late','.9','2026-09-30T01:10:00Z','2026-09-30T01:16:00Z')):
            sid=self.add_snapshot(market_id,as_of)
            self.db.execute('''INSERT INTO predictions(snapshot_id,market_id,model_version,as_of,
              created_at,seconds_remaining,probability_up,probability_down,assumptions_json)
              VALUES(?,?,?,?,?,?,?,?,?)''',
              (sid,market_id,MODEL,as_of,created,
               (timestamp('2026-09-30T01:15:00Z')-timestamp(as_of)).total_seconds(),
               p,str(1-float(p)),'{}'))
        report=evaluate(self.db)
        five=report['checkpoints']['T-5m']
        self.assertEqual(report['total_confirmed_markets'],2)
        self.assertEqual(five['eligible_markets'],1)
        self.assertAlmostEqual(five['model']['brier'],.04)
        self.assertEqual(five['fifty_fifty']['brier'],.25)
        self.assertIsNone(five['fifty_fifty']['directional_accuracy'])
        self.assertIsNone(five['chronological_splits'])

    def test_empty_report_is_honest(self):
        report=evaluate(self.db)
        self.assertEqual(report['status'],'no_confirmed_checkpoint_forecasts')
        self.assertIsNone(report['checkpoints']['T-10m']['model'])

    def test_chronological_splits_use_distinct_markets(self):
        first=timestamp('2026-09-30T01:00:00Z')
        for i in range(30):
            start=first+timedelta(minutes=15*i)
            end=start+timedelta(minutes=15)
            at=end-timedelta(minutes=5)
            market_id=f'm{i}'
            self.add_market(market_id,start.isoformat(),end.isoformat(),
                            'UP' if i%2 else 'DOWN','MARKET_STATUS_RESOLVED')
            sid=self.add_snapshot(market_id,at.isoformat())
            self.db.execute('''INSERT INTO predictions(snapshot_id,market_id,model_version,as_of,
              created_at,seconds_remaining,probability_up,probability_down,assumptions_json)
              VALUES(?,?,?,?,?,?,?,?,?)''',
              (sid,market_id,MODEL,at.isoformat(),(at+timedelta(seconds=2)).isoformat(),
               300,'.6','.4','{}'))
        report=evaluate(self.db)['checkpoints']['T-5m']
        self.assertEqual(report['eligible_markets'],30)
        self.assertEqual([report['chronological_splits'][part]['model']['markets']
                          for part in ('earliest_60pct','next_20pct','latest_20pct')],
                         [18,6,6])


if __name__=='__main__': unittest.main()
