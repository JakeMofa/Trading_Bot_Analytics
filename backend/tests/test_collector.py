import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from datetime import timedelta
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from collector import normalize, session_state, timestamp, connect, save_market, save_candles, collect_once, discover

class CollectorTests(unittest.TestCase):
    def market(self):
        return {'id':'1','slug':'test','status':'MARKET_STATUS_OPEN','assetPriceTerms':{
          'asset':{'symbol':'btc'},'marketType':'ASSET_PRICE_MARKET_TYPE_UP_DOWN',
          'horizon':'15m','windowStart':'2026-09-30T01:00:00Z','windowEnd':'2026-09-30T01:15:00Z',
          'priceToBeat':{'value':'100.00'},'settlementPrice':None}}

    def test_actual_window_not_administrative_end(self):
        raw=self.market(); raw['endDate']='2026-09-30T01:45:00Z'
        m=normalize(raw)
        self.assertEqual(session_state(m,timestamp('2026-09-30T01:10:00Z')),'active')
        self.assertEqual(session_state(m,timestamp('2026-09-30T01:15:00Z')),'pending_result')

    def test_missing_target_and_confirmed_equality(self):
        raw=self.market(); raw['assetPriceTerms']['priceToBeat']=None
        self.assertEqual(session_state(normalize(raw),timestamp('2026-09-30T01:10:00Z')),'awaiting_target')
        raw=self.market(); raw['assetPriceTerms']['settlementPrice']={'value':'100.00'}
        self.assertIsNone(normalize(raw)['result'])
        raw['status']='MARKET_STATUS_RESOLVED'
        self.assertEqual(normalize(raw)['result'],'UP')
        raw['assetPriceTerms']['settlementPrice']={'value':'99.99'}
        self.assertEqual(normalize(raw)['result'],'DOWN')

    def test_reject_other_contracts(self):
        raw=self.market(); raw['assetPriceTerms']['asset']['symbol']='eth'
        self.assertIsNone(normalize(raw))
        raw=self.market(); raw['assetPriceTerms']['windowEnd']='2026-09-30T02:00:00Z'
        with self.assertRaises(ValueError): normalize(raw)

    def test_restart_deduplication_and_bounded_candles(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'db.sqlite'; db=connect(p)
            m=normalize(self.market())
            with db:
                save_market(db,m,'2026-09-30T01:05:00+00:00')
                save_candles(db,[[60,1,2,1,2,3],[120,1,2,1,2,3]],60,120)
            db.close(); db=connect(p)
            with db: save_market(db,m,'2026-09-30T01:06:00+00:00')
            self.assertEqual(db.execute('SELECT count(*) FROM markets').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM candles').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT first_seen FROM markets').fetchone()[0],'2026-09-30T01:05:00+00:00')
            db.close()

    def test_discovery_filters_old_and_future(self):
        old=self.market()
        future=self.market(); future['id']='2'
        future['assetPriceTerms']['windowStart']='2026-09-30T01:15:00Z'
        future['assetPriceTerms']['windowEnd']='2026-09-30T01:30:00Z'
        with patch('collector.get_json',return_value={'markets':[old,future]}):
            found=discover(timestamp('2026-09-30T01:15:00Z'))
        self.assertEqual(found[900]['id'],'2')

    def test_book_fallback_and_delayed_resolution_do_not_block_collection(self):
        db=connect(':memory:')
        m=normalize(self.market())
        with db: save_market(db,m,'2026-09-30T01:05:00+00:00')
        def response(base,path,params=None):
            if path.endswith('/bbo'): raise HTTPError(path,404,'not found',{},None)
            if path.endswith('/book'): return {'marketData':{'transactTime':'2026-09-30T01:10:00Z'}}
            if '/market/slug/' in path: raise HTTPError(path,503,'pending',{},None)
            if path.endswith('/ticker'): return {'price':'101','time':'2026-09-30T01:10:00Z'}
            raise AssertionError(path)
        with patch('collector.discover',return_value={900:m}), patch('collector.get_json',side_effect=response):
            collect_once(db)
        self.assertEqual(db.execute("SELECT count(*) FROM observations WHERE kind='book'").fetchone()[0],1)
        self.assertEqual(db.execute('SELECT count(*) FROM reference_prices').fetchone()[0],1)
        self.assertIsNone(db.execute('SELECT result FROM markets').fetchone()[0])
        db.close()

    def test_default_collects_and_reconciles_only_15m(self):
        db=connect(':memory:')
        short=normalize(self.market())
        raw=self.market(); raw['id']='hour'; raw['slug']='hour'
        raw['assetPriceTerms']['horizon']='1h'
        raw['assetPriceTerms']['windowEnd']='2026-09-30T02:00:00Z'
        hour=normalize(raw)
        with db: save_market(db,hour,'2026-09-30T01:05:00+00:00')
        paths=[]
        def response(base,path,params=None):
            paths.append(path)
            if path.endswith('/ticker'): return {'price':'101'}
            return {'marketData':{}}
        with patch('collector.discover',return_value={900:short,3600:hour}), patch('collector.get_json',side_effect=response):
            collect_once(db)
        self.assertFalse(any('hour' in path for path in paths))
        self.assertEqual(db.execute("SELECT count(*) FROM markets WHERE id='hour'").fetchone()[0],1)
        self.assertEqual(db.execute("SELECT count(*) FROM observations WHERE market_id='hour'").fetchone()[0],1)
        db.close()

    def test_discovery_15m_default_and_both_option(self):
        raw=self.market(); raw['id']='hour'; raw['slug']='hour'
        raw['assetPriceTerms']['horizon']='1h'
        raw['assetPriceTerms']['windowEnd']='2026-09-30T02:00:00Z'
        with patch('collector.get_json',return_value={'markets':[self.market(),raw]}):
            now=timestamp('2026-09-30T01:10:00Z')
            self.assertEqual(set(discover(now)),{900})
            self.assertEqual(set(discover(now,(900,3600))),{900,3600})

if __name__=='__main__': unittest.main()
