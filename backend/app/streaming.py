"""Read-only streaming supervisor: Coinbase public feed; optional Polymarket keys."""
import argparse
import asyncio
import base64
import json
import os
import signal
import time
import uuid
from pathlib import Path
from websockets.asyncio.client import connect as ws_connect
from collector import connect, collect_once, amount, utcnow, timestamp, save_observation, refresh_recent_candles, record
from features import initialize as initialize_features, capture as capture_features

COINBASE_WS = 'wss://ws-feed.exchange.coinbase.com'
POLYMARKET_WS = 'wss://api.polymarket.us/v1/ws/markets'


def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS stream_events (
      source TEXT NOT NULL, event_id TEXT NOT NULL, received_at TEXT NOT NULL,
      source_time TEXT NOT NULL, price TEXT NOT NULL, size TEXT, side TEXT,
      payload TEXT NOT NULL, PRIMARY KEY(source,event_id));
    CREATE TABLE IF NOT EXISTS feed_health (
      source TEXT PRIMARY KEY, status TEXT NOT NULL, updated_at TEXT NOT NULL,
      last_data_at TEXT, reconnects INTEGER NOT NULL DEFAULT 0, detail TEXT);
    ''')


def health(db, source, status, detail=None, data=False, reconnect=False):
    now=utcnow().isoformat()
    with db:
        db.execute('''INSERT INTO feed_health VALUES(?,?,?,?,?,?)
        ON CONFLICT(source) DO UPDATE SET status=excluded.status,
        updated_at=excluded.updated_at,
        last_data_at=COALESCE(excluded.last_data_at,feed_health.last_data_at),
        reconnects=feed_health.reconnects+excluded.reconnects,detail=excluded.detail''',
        (source,status,now,now if data else None,int(reconnect),detail))


def save_coinbase(db, msg):
    if msg.get('type') != 'ticker' or msg.get('product_id') != 'BTC-USD':
        return False
    price=amount(msg.get('price'))
    if price is None or 'trade_id' not in msg or not msg.get('time'):
        raise ValueError('Incomplete Coinbase ticker')
    timestamp(msg['time'])
    with db:
        inserted=db.execute('INSERT OR IGNORE INTO stream_events VALUES(?,?,?,?,?,?,?,?)',
          ('coinbase',str(msg['trade_id']),utcnow().isoformat(),msg['time'],price,
           amount(msg.get('last_size')),msg.get('side'),json.dumps(msg))).rowcount
    return bool(inserted)


def auth_headers(key_id, secret, milliseconds=None):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    millis=str(milliseconds if milliseconds is not None else int(time.time()*1000))
    key=Ed25519PrivateKey.from_private_bytes(base64.b64decode(secret,validate=True)[:32])
    signature=base64.b64encode(key.sign((millis+'GET/v1/ws/markets').encode())).decode()
    return {'X-PM-Access-Key':key_id,'X-PM-Timestamp':millis,'X-PM-Signature':signature}


def subscription(slug):
    return {'subscribe':{'requestId':str(uuid.uuid4()),
        'subscriptionType':'SUBSCRIPTION_TYPE_MARKET_DATA','marketSlugs':[slug],
        'responsesDebounced':True}}


def current_market(db):
    now=utcnow().isoformat()
    return db.execute("SELECT id,slug FROM markets WHERE duration=900 AND start<=? AND end>? AND status='MARKET_STATUS_OPEN' ORDER BY start DESC LIMIT 1",(now,now)).fetchone()


def save_polymarket(db, msg):
    payload=msg.get('marketData') or msg.get('market_data')
    if not payload:
        return False
    slug=payload.get('marketSlug') or payload.get('market_slug')
    row=db.execute('SELECT id FROM markets WHERE slug=?',(slug,)).fetchone()
    if not row:
        return False
    with db:
        save_observation(db,row[0],utcnow().isoformat(),'stream_book',msg,
                         payload.get('transactTime') or payload.get('transact_time'))
    return True


def reconnect_delay(attempt):
    return min(30,2**min(attempt,5))


async def pause(stop, seconds):
    try:
        await asyncio.wait_for(stop.wait(),seconds)
    except asyncio.TimeoutError:
        pass


async def coinbase_stream(db, stop, connector=ws_connect):
    attempt=0
    while not stop.is_set():
        health(db,'coinbase_stream','connecting')
        try:
            async with connector(COINBASE_WS,ping_interval=20,ping_timeout=20,open_timeout=15,max_queue=128) as ws:
                await ws.send(json.dumps({'type':'subscribe','product_ids':['BTC-USD'],
                                          'channels':['ticker','heartbeat']}))
                health(db,'coinbase_stream','awaiting_data')
                last_data=None
                while not stop.is_set():
                    msg=json.loads(await asyncio.wait_for(ws.recv(),10))
                    if msg.get('type')=='error':
                        raise ValueError('Coinbase subscription error')
                    if msg.get('type')=='ticker':
                        save_coinbase(db,msg)
                        last_data=time.monotonic()
                        age=(utcnow()-timestamp(msg['time'])).total_seconds()
                        health(db,'coinbase_stream','live' if -5 <= age <= 30 else 'stale',data=True)
                        attempt=0
                    elif last_data is not None and time.monotonic()-last_data>15:
                        health(db,'coinbase_stream','stale','No ticker for 15 seconds')
        except Exception as exc:
            # Deliberately omit raw exception text: handshake errors may contain headers.
            health(db,'coinbase_stream','disconnected',type(exc).__name__,reconnect=True)
            await pause(stop,reconnect_delay(attempt)); attempt+=1
    health(db,'coinbase_stream','stopped')


async def polymarket_stream(db, stop, key_id, secret, connector=ws_connect):
    if not key_id or not secret:
        health(db,'polymarket_stream','disabled','Credentials absent; public REST remains active')
        return
    attempt=0
    while not stop.is_set():
        market=current_market(db)
        if not market:
            health(db,'polymarket_stream','awaiting_market')
            await pause(stop,2)
            continue
        try:
            headers=auth_headers(key_id,secret)  # fresh signature on every reconnect
            health(db,'polymarket_stream','connecting')
            async with connector(POLYMARKET_WS,additional_headers=headers,
                    ping_interval=20,ping_timeout=20,open_timeout=15,max_queue=128) as ws:
                await ws.send(json.dumps(subscription(market[1])))
                health(db,'polymarket_stream','awaiting_data')
                last_message=time.monotonic()
                last_data=None
                while not stop.is_set():
                    # Restart connection/subscription when the discovered market changes.
                    if current_market(db)!=market:
                        break
                    try:
                        raw=await asyncio.wait_for(ws.recv(),2)
                    except asyncio.TimeoutError:
                        if last_data is not None and time.monotonic()-last_data>15:
                            health(db,'polymarket_stream','stale','No book update for 15 seconds')
                        if time.monotonic()-last_message>30:
                            raise TimeoutError('Feed silent')
                        continue
                    last_message=time.monotonic()
                    msg=json.loads(raw)
                    if 'error' in msg:
                        raise ValueError('Polymarket subscription error')
                    if save_polymarket(db,msg):
                        last_data=time.monotonic()
                        health(db,'polymarket_stream','live',data=True); attempt=0
        except Exception as exc:
            health(db,'polymarket_stream','disconnected',type(exc).__name__,reconnect=True)
            await pause(stop,reconnect_delay(attempt)); attempt+=1
    health(db,'polymarket_stream','stopped')


def rest_cycle(path, refresh_candles=False):
    db=connect(path)
    try:
        messages = collect_once(db)
        if refresh_candles:
            try:
                coverage = refresh_recent_candles(db)
                record(db, 'coinbase_candle_refresh', True, coverage)
                messages.append(f'Candle refresh: {coverage}')
            except Exception as exc:
                record(db, 'coinbase_candle_refresh', False, exc)
                messages.append(f'Candle refresh failed: {exc}')
        return messages
    finally:
        db.close()


async def rest_loop(path, db, stop, interval):
    last_candle_refresh = None
    while not stop.is_set():
        try:
            refresh = last_candle_refresh is None or time.monotonic()-last_candle_refresh >= 60
            messages=await asyncio.to_thread(rest_cycle,path,refresh)
            if refresh:
                last_candle_refresh = time.monotonic()
            print('\n'.join(messages),flush=True)
            snapshot = capture_features(db)
            if snapshot:
                market_id, values, quality = snapshot
                print(f"15m features: market={market_id} remaining={values['seconds_remaining']:.0f}s price={quality['price']['status']} missing={len(quality['missing_features'])}", flush=True)
            # collect_once logs per-source failures; don't declare the feeds healthy here.
            health(db,'rest_supervisor','running','See runs for individual source errors')
        except Exception as exc:
            health(db,'rest_supervisor','error',type(exc).__name__)
        await pause(stop,interval)
    health(db,'rest_supervisor','stopped')


async def run(path, seconds, interval):
    db=connect(path); initialize(db); initialize_features(db)
    stop=asyncio.Event()
    loop=asyncio.get_running_loop()
    for sig in (signal.SIGINT,signal.SIGTERM):
        loop.add_signal_handler(sig,stop.set)
    timer=loop.call_later(seconds,stop.set) if seconds else None
    tasks=[asyncio.create_task(rest_loop(path,db,stop,interval)),
           asyncio.create_task(coinbase_stream(db,stop)),
           asyncio.create_task(polymarket_stream(db,stop,
              os.environ.get('POLYMARKET_KEY_ID'),os.environ.get('POLYMARKET_SECRET_KEY')))]
    try:
        await asyncio.gather(*tasks)
        summary=db.execute('SELECT source,status,reconnects FROM feed_health').fetchall()
        print('Feed status:',summary,flush=True)
    finally:
        stop.set()
        if timer: timer.cancel()
        for task in tasks:
            if not task.done(): task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        db.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',default='data/btc_intelligence.db')
    p.add_argument('--seconds',type=int,default=60,help='Bounded runtime; 0 runs until Ctrl+C')
    p.add_argument('--rest-interval',type=int,default=30)
    a=p.parse_args()
    if a.seconds<0 or a.rest_interval<15:
        p.error('seconds >=0; rest interval >=15 required')
    asyncio.run(run(a.db,a.seconds,a.rest_interval))


if __name__=='__main__': main()
