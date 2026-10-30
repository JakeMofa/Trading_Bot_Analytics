import asyncio
import base64
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from collector import connect, get_json
from streaming import initialize, save_coinbase, save_polymarket, health, auth_headers, reconnect_delay, coinbase_stream, polymarket_stream, polymarket_credentials, subscription, storage_bytes, storage_guard_loop, sync_live_market, hydrate_live_state
from live_state import LiveState
from features import initialize as initialize_features
from forecasts import initialize as initialize_forecasts

class StreamTests(unittest.TestCase):
    def setUp(self):
        self.db=connect(':memory:'); initialize(self.db)
    def tearDown(self): self.db.close()
    def test_trade_deduplication_and_source_time(self):
        msg={'type':'ticker','product_id':'BTC-USD','trade_id':7,'price':'100.12',
             'last_size':'0.1','time':'2026-09-30T02:00:00Z','side':'buy'}
        self.assertTrue(save_coinbase(self.db,msg))
        self.assertFalse(save_coinbase(self.db,msg))
        self.assertEqual(self.db.execute('SELECT price,source_time FROM stream_events').fetchone(),('100.12',msg['time']))
        self.assertFalse(save_coinbase(self.db,{'type':'heartbeat'}))
    def test_health_preserves_last_data_and_counts_reconnects(self):
        state=LiveState()
        health(self.db,'feed','live',data=True,live_state=state)
        before=self.db.execute('SELECT last_data_at FROM feed_health').fetchone()[0]
        health(self.db,'feed','disconnected','timeout',reconnect=True,live_state=state)
        self.assertEqual(self.db.execute('SELECT last_data_at,reconnects FROM feed_health').fetchone(),(before,1))
        live=state.snapshot()['feeds']['feed']
        self.assertEqual(live['status'],'disconnected')
        self.assertEqual(live['reconnects'],1)
        self.assertIsNotNone(live['last_data_at'])
    def test_storage_cap_stops_without_deleting_database(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'evidence.db'
            path.write_bytes(b'x' * 900000)
            wal = Path(str(path) + '-wal')
            wal.write_bytes(b'y' * 200000)
            self.assertEqual(storage_bytes(path), 1100000)
            stop = asyncio.Event()
            with patch('builtins.print'):
                asyncio.run(storage_guard_loop(path, self.db, stop, 1))
            self.assertTrue(stop.is_set())
            self.assertEqual(self.db.execute("SELECT status FROM feed_health WHERE source='storage_guard'").fetchone()[0],
                             'limit_reached')
            self.assertEqual(path.stat().st_size, 900000)
            self.assertEqual(wal.stat().st_size, 200000)
    def test_sync_live_market_populates_ram_state(self):
        self.db.execute('''INSERT INTO markets(id,slug,duration,start,end,target,status,
          first_seen,last_seen,raw_json) VALUES(?,?,?,?,?,?,?,?,?,?)''',
          ('m','btc-market',900,'2026-10-21T04:00:00+00:00','2999-10-21T04:15:00+00:00',
           '100','MARKET_STATUS_OPEN','2026-10-21T04:00:00+00:00',
           '2026-10-21T04:00:00+00:00','{}'))
        state=LiveState()
        row=sync_live_market(self.db,state)
        self.assertIsNotNone(row)
        self.assertEqual(state.market_identity(),('m','btc-market'))

    def test_hydrate_live_state_restores_mid_interval_evidence(self):
        initialize_features(self.db)
        initialize_forecasts(self.db)
        now=datetime(2026,10,21,4,10,0,tzinfo=timezone.utc)
        self.db.execute('''INSERT INTO markets(id,slug,duration,start,end,target,status,
          first_seen,last_seen,raw_json) VALUES(?,?,?,?,?,?,?,?,?,?)''',
          ('m2','btc-live',900,'2026-10-21T04:00:00+00:00',
           '2026-10-21T04:15:00+00:00','100','MARKET_STATUS_OPEN',
           '2026-10-21T04:00:00+00:00','2026-10-21T04:00:00+00:00','{}'))
        ticker={'type':'ticker','product_id':'BTC-USD','trade_id':55,'price':'101',
                'last_size':'0.2','time':'2026-10-21T04:09:59+00:00','side':'buy'}
        self.db.execute('''INSERT INTO stream_events(source,event_id,received_at,
          source_time,price,size,side,payload) VALUES(?,?,?,?,?,?,?,?)''',
          ('coinbase','55','2026-10-21T04:09:59.100000+00:00',
           ticker['time'],'101','0.2','buy',json.dumps(ticker)))
        self.db.execute('''INSERT INTO feature_snapshots(
          market_id,as_of,version,values_json,quality_json,evidence_json)
          VALUES(?,?,?,?,?,?)''',
          ('m2','2026-10-21T04:09:30+00:00',1,
           json.dumps({'target_usd':'100','reference_price_usd':'100.5',
                       'seconds_remaining':330,'realized_volatility_15m':'0.002'}),
           json.dumps({'price':{'status':'fresh'},'candle_status':'fresh',
                       'candle_age_seconds':20,'late_join':False}),'{}'))
        self.db.execute('''INSERT INTO observations(market_id,received_at,kind,payload)
          VALUES(?,?,?,?)''',
          ('m2','2026-10-21T04:09:58+00:00','bbo',
           json.dumps({'marketData':{'marketSlug':'btc-live',
             'longQuote':{'value':'0.57'},'shortQuote':{'value':'0.43'}}})))
        self.db.commit()

        state=LiveState()
        snap=hydrate_live_state(self.db,state,now)
        self.assertEqual(snap['market']['id'],'m2')
        self.assertEqual(snap['coinbase']['price_usd'],101.0)
        self.assertEqual(snap['feature_snapshot']['market_id'],'m2')
        self.assertEqual(snap['polymarket']['up_probability'],0.57)
        self.assertIsNotNone(snap['forecast'])
        self.assertEqual(set(snap['missing_data']),{'trade_flow','btc_order_book'})

    def test_signed_headers(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        seed=bytes(range(32))
        headers=auth_headers('id',base64.b64encode(seed).decode(),12345)
        Ed25519PrivateKey.from_private_bytes(seed).public_key().verify(
            base64.b64decode(headers['X-PM-Signature']),b'12345GET/v1/ws/markets')
        self.assertEqual(headers['X-PM-Access-Key'],'id')
    def test_local_market_credentials_do_not_override_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            env = Path(folder) / '.env'
            env.write_text('POLYMARKET_KEY_ID="saved-id"\nPOLYMARKET_SECRET_KEY=saved-secret\nIGNORED=value\n')
            with patch.dict('os.environ', {'POLYMARKET_KEY_ID':'', 'POLYMARKET_SECRET_KEY':''}):
                self.assertEqual(polymarket_credentials(env), ('saved-id','saved-secret'))
            with patch.dict('os.environ', {'POLYMARKET_KEY_ID':'shell-id', 'POLYMARKET_SECRET_KEY':'shell-secret'}):
                self.assertEqual(polymarket_credentials(env), ('shell-id','shell-secret'))
        self.assertNotIn('responsesDebounced', subscription('btc-market')['subscribe'])
    def test_unknown_market_not_attached(self):
        self.assertFalse(save_polymarket(self.db,{'marketData':{'marketSlug':'unknown'}}))
    def test_backoff_cap(self):
        self.assertEqual([reconnect_delay(x) for x in [0,1,2,9]],[1,2,4,30])
    def test_rest_rate_limit_retry(self):
        error=HTTPError('url',429,'limited',{'Retry-After':'2'},None)
        class Response:
            def __enter__(self): return self
            def __exit__(self,*a): pass
            def read(self): return b'{"ok":true}'
        with patch('collector.urlopen',side_effect=[error,Response()]),patch('collector.time.sleep') as sleep:
            self.assertEqual(get_json('https://example.com','/test'),{'ok':True})
            sleep.assert_called_once_with(2.0)
    def test_missing_keys_disable_without_connecting(self):
        async def check():
            stop=asyncio.Event()
            def forbidden(*a,**kw): raise AssertionError('Should not connect')
            await polymarket_stream(self.db,stop,None,None,forbidden)
        asyncio.run(check())
        self.assertEqual(self.db.execute("SELECT status FROM feed_health WHERE source='polymarket_stream'").fetchone()[0],'disabled')
    def test_disconnect_reconnect_resubscribe(self):
        async def check():
            stop=asyncio.Event(); calls=[]; sends=[]
            class Socket:
                def __init__(self,n): self.n=n
                async def __aenter__(self): return self
                async def __aexit__(self,*a): pass
                async def send(self,msg): sends.append(json.loads(msg))
                async def recv(self):
                    if self.n==1: raise ConnectionError('disconnect')
                    stop.set()
                    return json.dumps({'type':'ticker','product_id':'BTC-USD','trade_id':9,'price':'101','time':'2026-09-30T02:00:00Z'})
            def connector(*a,**kw):
                calls.append(a); return Socket(len(calls))
            async def immediate(*a): pass
            with patch('streaming.pause',side_effect=immediate):
                await coinbase_stream(self.db,stop,connector)
            self.assertEqual(len(calls),2)
            self.assertEqual(sends[0],sends[1])
        asyncio.run(check())
        self.assertEqual(self.db.execute('SELECT count(*) FROM stream_events').fetchone()[0],1)
        self.assertEqual(self.db.execute("SELECT reconnects FROM feed_health WHERE source='coinbase_stream'").fetchone()[0],1)


class FeatureWorkerTests(unittest.TestCase):
    def test_feature_worker_keeps_event_loop_and_real_collector_save_live(self):
        import threading
        from streaming import rest_loop
        entered, release = threading.Event(), threading.Event()
        owner = threading.get_ident()
        worker_threads = []
        def slow_capture(db):
            worker_threads.append(threading.get_ident())
            self.assertEqual(db.execute('PRAGMA busy_timeout').fetchone()[0], 5000)
            self.assertEqual(db.execute('PRAGMA foreign_keys').fetchone()[0], 1)
            # Hold an actual WAL read snapshot while the collector writes.
            db.execute('BEGIN')
            db.execute('SELECT COUNT(*) FROM stream_events').fetchone()
            entered.set()
            if not release.wait(5):
                raise AssertionError('event loop did not release the worker')
            db.rollback()
            return None
        async def exercise(path, db):
            stop = asyncio.Event()
            async def finish_cycle(*args): stop.set()
            with patch('streaming.rest_cycle', return_value=[]), \
                 patch('streaming.capture_features', side_effect=slow_capture) as capture, \
                 patch('streaming.pause', side_effect=finish_cycle), patch('builtins.print'):
                task = asyncio.create_task(rest_loop(path, db, stop, 0))
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                    self.assertFalse(task.done())
                    # This runs on the same event loop as API handlers/feed callbacks.
                    state = LiveState()
                    msg = {'type':'ticker','product_id':'BTC-USD','trade_id':77,
                           'price':'101.25','time':'2026-10-30T18:00:00Z'}
                    self.assertTrue(save_coinbase(db, msg))
                    state.update_coinbase_ticker(msg)
                    self.assertEqual(state.snapshot()['coinbase']['price_usd'],101.25)
                    self.assertEqual(db.execute('PRAGMA busy_timeout').fetchone()[0],5000)
                    for _ in range(3): await asyncio.sleep(0)
                    self.assertEqual(capture.call_count,1)
                finally:
                    release.set()
                    await asyncio.wait_for(task,2)
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder)/'worker.db')
            db = connect(path); initialize(db); initialize_features(db)
            try: asyncio.run(exercise(path,db))
            finally: db.close()
        self.assertNotEqual(worker_threads,[owner])

    def test_feature_worker_closes_connection_after_error(self):
        import sqlite3
        from streaming import feature_cycle
        closed = []
        class TrackingConnection(sqlite3.Connection):
            def close(self):
                closed.append(True)
                super().close()
        factory = sqlite3.connect
        with tempfile.TemporaryDirectory() as folder, \
             patch('streaming.sqlite3.connect', side_effect=lambda *a,**kw: factory(*a,**kw,factory=TrackingConnection)), \
             patch('streaming.capture_features',side_effect=RuntimeError('calculation failed')):
            with self.assertRaisesRegex(RuntimeError,'calculation failed'):
                feature_cycle(str(Path(folder)/'worker.db'))
        self.assertEqual(closed,[True])


if __name__=='__main__': unittest.main()
