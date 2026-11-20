"""Generated no-market Coinbase reference regression: actual API/SSE/dashboard JS."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import Mock,MagicMock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from postgres.api import create_app
from postgres.config import Settings
from postgres.live_state import LiveState
from postgres.store import Store

NOW=datetime(2026,11,19,22,15,5,tzinfo=timezone.utc)
SETTINGS=Settings(data_mode='pp_live',origin_id='pp-live-pp-trial-20261119-01')


def price(event='first',seconds=0,**changes):
    stamp=(NOW+timedelta(seconds=seconds)).isoformat()
    return dict(origin=SETTINGS.origin_id,source='coinbase',event_id=event,
        generation_id='00000000-0000-4000-8000-000000000001',source_time=stamp,
        received_at=stamp,available_at=stamp,price_usd='98765.123456789012345678901',
        size_btc=None,content_hash='a'*64,provenance={'generated':True})|changes


def market():
    return dict(id='next',start='2026-11-19T22:15:00+00:00',end='2026-11-19T22:30:00+00:00',target_usd='98700')


class GapPriceStateTests(unittest.TestCase):
    def test_gap_and_expired_markets_accept_reference_without_forecasts(self):
        current=[NOW];state=LiveState(SETTINGS,clock=lambda:current[0])
        self.assertTrue(state.publish_price(price(seconds=-1)))
        state.discover(dict(market(),id='ended',start='2026-11-19T22:00:00Z',end='2026-11-19T22:15:00Z'))
        self.assertTrue(state.publish_price(price('second',source_time='2026-11-19T22:15:04.999999999Z')))
        result=state.snapshot()
        self.assertEqual(result['coinbase']['event_id'],'second')
        self.assertFalse(result['market']['active'])
        for key in ('polymarket','feature_snapshot','forecast','live_estimate'):self.assertIsNone(result[key])

    def test_old_future_foreign_missing_or_bad_prices_never_replace_latest(self):
        state=LiveState(SETTINGS,clock=lambda:NOW)
        self.assertTrue(state.publish_price(price()))
        for candidate in (None,price('old',seconds=-1),price('future',seconds=1),
            price('received-future',received_at=(NOW+timedelta(seconds=1)).isoformat()),
            price('available-future',available_at=(NOW+timedelta(seconds=1)).isoformat()),
            price('wrong-origin',origin='pp-live-pp'),price('wrong-source',source='polymarket_us'),
            price('nan',price_usd='NaN'),price('missing',available_at=None),price('zero',price_usd='0')):
            self.assertFalse(state.publish_price(candidate))
            self.assertEqual(state.snapshot()['coinbase']['event_id'],'first')
        # Nanosecond ordering/cutoffs cannot be rounded into an equal microsecond.
        state=LiveState(SETTINGS,clock=lambda:NOW)
        self.assertTrue(state.publish_price(price('nano',source_time='2026-11-19T22:15:04.999999999Z')))
        self.assertFalse(state.publish_price(price('older-nano',source_time='2026-11-19T22:15:04.999999998Z')))
        self.assertFalse(state.publish_price(price('future-nano',source_time='2026-11-19T22:15:05.000000001Z')))
        self.assertEqual(state.snapshot()['coinbase']['event_id'],'nano')

    def test_stale_missing_and_active_discovery_race_keep_publication_gates(self):
        clock=[NOW];state=LiveState(SETTINGS,clock=lambda:clock[0])
        self.assertIsNone(state.snapshot()['coinbase'])
        self.assertTrue(state.publish_price(price('stale',seconds=-31)))
        self.assertEqual(state.snapshot()['feeds']['coinbase_stream']['status'],'stale')
        self.assertIn('coinbase_price',state.snapshot()['missing_data'])
        self.assertTrue(state.publish_price(price()))
        gap=state.snapshot()
        self.assertEqual(gap['feeds']['coinbase_stream']['status'],'fresh')
        for key in ('forecast','feature_snapshot','polymarket','live_estimate'):self.assertIsNone(gap[key])
        self.assertIn('active_market',gap['missing_data'])
        state.discover(market())
        self.assertFalse(state.publish_price(price('gap-read-raced-with-discovery')))
        self.assertIsNone(state.snapshot()['forecast'])
        clock[0]=datetime(2026,11,19,22,30,tzinfo=timezone.utc)
        self.assertFalse(state.publish('next',price(),None,None,None))
        self.assertIsNone(state.snapshot()['live_estimate'])
        self.assertTrue(state.publish_price(price('after-expiry',source_time=clock[0].isoformat(),
            received_at=clock[0].isoformat(),available_at=clock[0].isoformat())))
        self.assertIsNone(state.snapshot()['forecast'])

    def test_store_current_price_is_one_scoped_read_without_candles(self):
        store=Store(SETTINGS);connection=MagicMock();store.connection=Mock(return_value=connection)
        query=connection.__enter__.return_value.execute
        query.return_value.fetchone.return_value=None
        self.assertIsNone(store.current_price(NOW))
        store.connection.assert_called_once_with(True);query.assert_called_once()
        statement,args=query.call_args.args
        self.assertIn("source='coinbase' AND symbol='BTC-USD'",statement)
        self.assertIn('origin_id=%s',statement);self.assertIn('received_at<=%s AND available_at<=%s',statement)
        self.assertNotIn('candles',statement)
        self.assertEqual(args[0],SETTINGS.origin_id)
        self.assertEqual(str(args[1]),'1795126505')
        self.assertEqual(args[2:],(NOW,NOW))


class GapPriceHTTPTests(unittest.TestCase):
    def test_actual_http_sse_and_dashboard_follow_coinbase_through_discovery_gap(self):
        import httpx
        import uvicorn
        class StoreFixture:
            selected_market=None;tick=price('first',seconds=-1);gap_reads=0;active_reads=0
            def verify(self):pass
            def active_market(self):return deepcopy(self.selected_market)
            def collector_enabled(self):return True
            def current_price(self):self.gap_reads+=1;return deepcopy(self.tick)
            def hydrate(self,market_id):
                self.active_reads+=1
                return deepcopy(self.tick),None,None,None
        store=StoreFixture();clock=[NOW];state=LiveState(SETTINGS,clock=lambda:clock[0])
        app=create_app(SETTINGS,store,state,refresh=True)
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(app,log_level='critical'))
        thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
        def wait_for(check):
            deadline=time.monotonic()+4
            while time.monotonic()<deadline:
                if check():return
                time.sleep(.02)
            self.fail('generated API hydration condition timed out')
        try:
            wait_for(lambda:server.started)
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=2,trust_env=False) as client:
                wait_for(lambda:(state.snapshot().get('coinbase') or {}).get('event_id')=='first')
                before=client.get('/state/current').json();self.assertEqual(before['coinbase']['event_id'],'first')
                store.tick=price('second')
                wait_for(lambda:(state.snapshot().get('coinbase') or {}).get('event_id')=='second')
                gap=client.get('/state/current').json()
                self.assertIsNone(gap['market']);self.assertEqual(gap['coinbase']['event_id'],'second')
                self.assertEqual(gap['coinbase']['price_usd'],'98765.123456789012345678901')
                self.assertEqual(gap['feeds']['coinbase_stream']['status'],'fresh')
                self.assertEqual(store.active_reads,0);self.assertGreaterEqual(store.gap_reads,2)
                for key in ('feature_snapshot','forecast','live_estimate','polymarket'):self.assertIsNone(gap[key])
                with client.stream('GET','/events') as response:
                    self.assertIn('text/event-stream',response.headers['content-type'])
                    lines=response.iter_lines();self.assertTrue(next(lines).startswith('id: '))
                    streamed=json.loads(next(lines).removeprefix('data: '))
                    self.assertEqual(streamed['coinbase'],gap['coinbase'])
                    self.assertIsNone(streamed['forecast'])
                dashboard=client.get('/dashboard').text
                self.dashboard_reference(dashboard,gap)
                # Active-market hydration remains the only read path on later ticks.
                store.selected_market=market()
                wait_for(lambda:store.active_reads>=1)
                reads=store.gap_reads;active_reads=store.active_reads
                wait_for(lambda:store.active_reads>=active_reads+2)
                self.assertEqual(store.gap_reads,reads)
                self.assertEqual(client.get('/state/current').json()['market']['id'],'next')
        finally:
            server.should_exit=True;thread.join(5);sock.close()
        self.assertFalse(thread.is_alive())

    def dashboard_reference(self,source,state):
        if not shutil.which('node'):self.skipTest('dashboard JS requires Node.js')
        tick=re.search(r'    function tick\(\) \{.*?\n    \}',source,re.S).group()
        accept=re.search(r'    function acceptState\(state\) \{.*?\n    \}',source,re.S).group()
        formatters='\n'.join(re.findall(r'    const (?:money|pct|cents|age) = .*?;',source))
        script='''let latest,serverEpochMs,syncAt,lastError,chartData={};
const savedModels={},savedContext={},out={};
const set=(key,value)=>out[key]=value;
const byId=()=>({className:''});
const serverNowMs=()=>serverEpochMs;
const ageOf=value=>value ? Math.max(0,(serverEpochMs-Date.parse(value))/1000) : null;
const render=()=>{},refreshChart=()=>{},mergeLatestTick=()=>{},scheduleChartDraw=()=>{},updateChartSummary=()=>{};
''' +formatters+'\n'+tick+'\n'+accept+'\nacceptState('+json.dumps(state)+');process.stdout.write(JSON.stringify({out,latest}));'
        result=json.loads(subprocess.run([shutil.which('node'),'-e',script],check=True,capture_output=True,text=True,timeout=10).stdout)
        self.assertEqual(result['latest']['latest_coinbase_tick']['event_id'],'second')
        self.assertEqual(result['out']['live-reference'],'$98,765.12')
        self.assertEqual(result['out']['collection-state'],'Collecting live Coinbase reference ticks')
        self.assertEqual(result['out']['forecast-up'],'—')
        self.assertEqual(result['out']['market-timer'],'—')


if __name__=='__main__':unittest.main()
