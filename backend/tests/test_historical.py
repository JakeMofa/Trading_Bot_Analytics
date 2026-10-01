from datetime import timedelta
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from collector import connect,timestamp
from historical import backfill_window, discover_past, expected_windows, initialize, save_price_history


class HistoricalTests(unittest.TestCase):
    def setUp(self):
        self.db=connect(':memory:')
        initialize(self.db)
        self.start=timestamp('2026-09-30T01:00:00Z')
        self.end=timestamp('2026-09-30T01:30:00Z')

    def tearDown(self): self.db.close()

    def market(self,id,start,end,target='100',final='101',status='MARKET_STATUS_RESOLVED'):
        return {'id':id,'slug':'cpc-'+str(id),'status':status,
                'assetPriceTerms':{'asset':{'symbol':'btc'},
                 'marketType':'ASSET_PRICE_MARKET_TYPE_UP_DOWN','horizon':'15m',
                 'windowStart':start,'windowEnd':end,
                 'priceToBeat':{'value':target},
                 'settlementPrice':{'value':final} if final else None}}

    def test_retroactive_market_and_display_prices_are_separate(self):
        market=self.market('a','2026-09-30T01:00:00Z','2026-09-30T01:15:00Z')
        def fetch(base,path,params):
            if path=='/v1/markets': return {'markets':[market]}
            self.assertEqual(params['symbol'],'cpc-a')
            return {'history':[{'timestamp':int(self.start.timestamp()),
                                'longPrice':.51,'shortPrice':.53},
                               {'timestamp':int((self.start+timedelta(minutes=15)).timestamp()),
                                'longPrice':.98,'shortPrice':.03}]}
        result=backfill_window(self.db,self.start,self.end,fetch,lambda _:None)
        self.assertEqual(result['expected_complete_intervals'],2)
        self.assertEqual(result['resolved_markets_found'],1)
        self.assertEqual(len(result['missing_intervals']),1)
        self.assertEqual(result['new_display_price_points'],2)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM markets').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM historical_market_prices').fetchone()[0],2)
        self.assertIsNone(self.db.execute("SELECT name FROM sqlite_master WHERE name='predictions'").fetchone())
        again=backfill_window(self.db,self.start,self.end,fetch,lambda _:None)
        self.assertEqual(again['new_display_price_points'],0)

    def test_filters_actual_windows_and_unresolved_markets(self):
        old=self.market('old','2026-09-30T00:45:00Z','2026-09-30T01:00:00Z')
        live=self.market('live','2026-09-30T01:00:00Z','2026-09-30T01:15:00Z',final=None,status='MARKET_STATUS_OPEN')
        good=self.market('good','2026-09-30T01:15:00Z','2026-09-30T01:30:00Z')
        found=discover_past(self.start,self.end,lambda *_:{'markets':[old,live,good]})
        self.assertEqual([m['id'] for m in found],['good'])

    def test_bad_price_and_window_rejected(self):
        raw=self.market('a','2026-09-30T01:00:00Z','2026-09-30T01:15:00Z')
        from collector import normalize, save_market
        market=normalize(raw)
        with self.db: save_market(self.db,market,self.start.isoformat())
        with self.assertRaises(ValueError):
            save_price_history(self.db,market,[{'timestamp':int(self.start.timestamp()),
                                                'longPrice':1.2}],self.end.isoformat())
        self.assertEqual(len(expected_windows(self.start,self.end)),2)
        with self.assertRaises(ValueError):
            backfill_window(self.db,self.end,self.start,lambda *_:None,lambda _:None)


if __name__=='__main__': unittest.main()
