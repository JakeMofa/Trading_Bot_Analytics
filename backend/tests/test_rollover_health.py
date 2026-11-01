import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from live_health import degradation_reasons
from live_state import LiveState
from collector import connect
from streaming import initialize, rest_loop, feature_loop, polymarket_stream, publish_feature_cycle

class TruthfulHealthTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,1,16,15,tzinfo=timezone.utc)
        at=self.now.isoformat()
        self.snapshot={'market':{'id':'new','slug':'new','start':at,'end':(self.now+timedelta(minutes=15)).isoformat()},
            'coinbase':{'source_time':at},'polymarket':{'slug':'new','source_time':at},
            'feature_snapshot':{'market_id':'new','as_of':at},'feeds':{},'missing_data':[]}
    def reasons(self,s=None):return degradation_reasons(s or self.snapshot,{'enabled':True,'running':True},self.now)
    def test_source_time_boundaries_replay_and_genuine_recovery(self):
        self.assertEqual(self.reasons(),[])
        for source in ('coinbase','polymarket'):
            for value,expected in [(None,'missing'),('bad','malformed'),('2026-11-01T16:15:00','malformed'),
                    ((self.now-timedelta(seconds=31)).isoformat(),'stale'),
                    ((self.now+timedelta(seconds=6)).isoformat(),'future')]:
                s=deepcopy(self.snapshot);s[source]['source_time']=value
                # Fresh receipts of an old event must not mask source age.
                s[source]['received_at']=self.now.isoformat()
                self.assertIn(source+'_source_time_'+expected,self.reasons(s))
                s[source]['source_time']=self.now.isoformat();self.assertEqual(self.reasons(s),[])
            for age in (-5,30):
                s=deepcopy(self.snapshot);s[source]['source_time']=(self.now-timedelta(seconds=age)).isoformat()
                self.assertEqual(self.reasons(s),[])
    def test_expired_missing_and_mismatched_identity_and_features(self):
        s=deepcopy(self.snapshot);s['market']['end']=self.now.isoformat()
        self.assertIn('market_expired',self.reasons(s))
        s=deepcopy(self.snapshot);s['polymarket']['slug']='old'
        self.assertIn('polymarket_market_mismatch',self.reasons(s))
        s=deepcopy(self.snapshot);s['market'].pop('id')
        self.assertIn('market_identity_missing',self.reasons(s))
        s=deepcopy(self.snapshot);s['feature_snapshot']=None
        self.assertIn('feature_snapshot_missing',self.reasons(s))
        s=deepcopy(self.snapshot);s['feature_snapshot']['market_id']='old'
        self.assertIn('feature_market_mismatch',self.reasons(s))
        s=deepcopy(self.snapshot);s['feature_snapshot']['as_of']=(self.now-timedelta(seconds=31)).isoformat()
        self.assertIn('feature_as_of_stale',self.reasons(s))

class BoundarySchedulingTests(unittest.TestCase):
    def test_186_second_job_does_not_hold_discovery_or_subscription_rollover(self):
        entered,release=threading.Event(),threading.Event();calls=[]
        before=datetime(2026,11,1,16,14,59,tzinfo=timezone.utc)
        clock=[before];state=LiveState();subscriptions=[]
        old_subscribed=asyncio.Event();new_subscribed=asyncio.Event()
        def market(name,start):return {'id':name,'slug':name,'start':start.isoformat(),'end':(start+timedelta(minutes=15)).isoformat(),'target_usd':'100'}
        state.set_market(market('old',before-timedelta(minutes=14,seconds=59)))
        def slow(path):
            calls.append(threading.get_ident());entered.set()
            if not release.wait(5):raise AssertionError('worker not released')
            return (('old',{},{}),1,before.isoformat(),None)
        class WS:
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            async def send(self,raw):
                self.slug=json.loads(raw)['subscribe']['marketSlugs'][0];subscriptions.append(self.slug)
                (new_subscribed if self.slug=='new' else old_subscribed).set()
            async def recv(self):
                await asyncio.sleep(0)
                return json.dumps({'marketData':{'marketSlug':self.slug,'transactTime':clock[0].isoformat()}})
        async def exercise(db):
            stop=asyncio.Event()
            def discover(db,live):
                clock[0]=before+timedelta(seconds=186)
                live.set_market(market('new',datetime(2026,11,1,16,15,tzinfo=timezone.utc)))
            async def pause(stop,seconds):await asyncio.sleep(.001)
            with patch('streaming.feature_cycle',side_effect=slow),patch('streaming.utcnow',side_effect=lambda:clock[0]),patch('streaming.rest_cycle',return_value=[]),patch('streaming.sync_live_market',side_effect=discover),patch('streaming.pause',side_effect=pause),patch('streaming.auth_headers',return_value={}),patch('streaming.save_polymarket',return_value=True),patch('builtins.print'):
                feature=asyncio.create_task(feature_loop('unused',db,stop,state))
                book=asyncio.create_task(polymarket_stream(db,stop,'test','test',connector=lambda *a,**k:WS(),live_state=state))
                rest=None
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait,1))
                    await asyncio.wait_for(old_subscribed.wait(),1)
                    rest=asyncio.create_task(rest_loop('unused',db,stop,30,state))
                    await asyncio.wait_for(new_subscribed.wait(),2)
                    self.assertIn('new',subscriptions)
                    self.assertFalse(feature.done());self.assertEqual(len(calls),1)
                    self.assertIsNone(state.snapshot(clock[0])['feature_snapshot'])
                    stop.set();release.set()
                finally:
                    stop.set();release.set()
                    await asyncio.wait_for(asyncio.gather(feature,book,*([rest] if rest else [])),2)
                self.assertIsNone(state.snapshot(clock[0])['feature_snapshot'])
        db=connect(':memory:');initialize(db)
        try:asyncio.run(exercise(db))
        finally:db.close()
