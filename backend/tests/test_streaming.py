import asyncio
import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from collector import connect, get_json
from streaming import initialize, save_coinbase, save_polymarket, health, auth_headers, reconnect_delay, coinbase_stream, polymarket_stream, polymarket_credentials, subscription

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
        health(self.db,'feed','live',data=True)
        before=self.db.execute('SELECT last_data_at FROM feed_health').fetchone()[0]
        health(self.db,'feed','disconnected','timeout',reconnect=True)
        self.assertEqual(self.db.execute('SELECT last_data_at,reconnects FROM feed_health').fetchone(),(before,1))
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

if __name__=='__main__': unittest.main()
