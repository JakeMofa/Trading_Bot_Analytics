"""Bounded generated A/B input projection; reuses the real feature/baseline code.

No whole-generation materialization. Same price/metadata query semantics as the
existing feature version; matching indexes live only in generated raw/core DBs.
"""
import json,sqlite3,time
from pathlib import Path
from datetime import timedelta
from raw_generations import connect,iso,stamp,Stop,canonical,COLUMNS
import features,forecasts

META_SQL="""SELECT id,market_id,received_at,source_time,kind,payload FROM observations
 WHERE market_id=? AND kind='metadata' AND julianday(received_at)<=julianday(?)
 ORDER BY julianday(received_at) DESC,id DESC LIMIT 1"""

def project(store,market_id,asof):
    cutoff=iso(asof);registry=connect(store.root/'core.db',True);db=sqlite3.connect(':memory:');refs={};stream_rows=[];obs_rows=[]
    try:
        m=registry.execute('SELECT metadata FROM markets WHERE id=?',(market_id,)).fetchone()
        if not m or not json.loads(m[0]):raise Stop('market metadata unavailable')
        market=json.loads(m[0])
        db.executescript('''CREATE TABLE markets(id TEXT,start TEXT,end TEXT,duration INTEGER,first_seen TEXT);
CREATE TABLE observations(id INTEGER PRIMARY KEY,market_id TEXT,received_at TEXT,source_time TEXT,kind TEXT,payload TEXT);
CREATE TABLE stream_events(source TEXT,event_id TEXT,received_at TEXT,source_time TEXT,price TEXT,size TEXT,side TEXT,payload TEXT);
CREATE TABLE reference_prices(id INTEGER,received_at TEXT,source_time TEXT,source TEXT,price TEXT,payload TEXT);
CREATE TABLE candles(source TEXT,symbol TEXT,granularity INTEGER,time INTEGER,low TEXT,high TEXT,open TEXT,close TEXT,volume TEXT,first_seen TEXT);''')
        db.execute('INSERT INTO markets VALUES(?,?,?,?,?)',tuple(market[k] for k in ('id','start','end','duration','first_seen')))
        for gen in registry.execute("SELECT id FROM generations WHERE state IN ('active','sealed','retiring')").fetchall():
            with store.reader(gen['id']) as raw:
                meta=raw.execute(META_SQL,(market_id,cutoff)).fetchone()
                if meta:obs_rows.append(dict(meta));refs[('observations',meta['id'])]=gen['id']
                price=raw.execute(features.price_query('stream_events','event_id'),(cutoff,cutoff)).fetchone()
                if price:
                    full=raw.execute('SELECT '+','.join(COLUMNS['stream_events'])+' FROM stream_events WHERE source=? AND event_id=?',('coinbase',price[0])).fetchone()
                    stream_rows.append(dict(full));refs[('stream_events',price[0])]=gen['id']
        # Metadata required by current markets survives raw retirement in core.
        pin=registry.execute('''SELECT e.record FROM metadata_pins p JOIN evidence e ON e.id=p.event_id
WHERE p.market_id=? AND julianday(p.received_at)<=julianday(?) ORDER BY julianday(p.received_at) DESC,p.event_id DESC LIMIT 1''',(market_id,cutoff)).fetchone()
        if pin:
            record=json.loads(pin[0]);obs_rows.append(record['row']);refs[('observations',record['row']['id'])]=record['generation_id']
        if sum(len(r['payload'].encode()) for r in obs_rows+stream_rows)>64*1024**2:raise Stop('bounded RAM input budget')
        seen={}
        for row in obs_rows:
            if row['id'] in seen and seen[row['id']]!=row:raise Stop('inconsistent metadata identity')
            seen[row['id']]=row
        db.executemany('INSERT INTO observations VALUES(?,?,?,?,?,?)',[tuple(r[k] for k in COLUMNS['observations']) for r in seen.values()])
        db.executemany('INSERT INTO stream_events VALUES(?,?,?,?,?,?,?,?)',[tuple(r[k] for k in COLUMNS['stream_events']) for r in stream_rows])
        price=registry.execute(features.price_query('reference_prices','id'),(cutoff,cutoff)).fetchone()
        if price:
            r=registry.execute('SELECT * FROM reference_prices WHERE id=?',(price[0],)).fetchone();db.execute('INSERT INTO reference_prices VALUES(?,?,?,?,?,?)',tuple(r))
        wanted=int(stamp(asof).timestamp())//60*60-60
        candles=registry.execute("SELECT * FROM candles WHERE source='coinbase' AND symbol='BTC-USD' AND granularity=60 AND time BETWEEN ? AND ? ORDER BY time",(wanted-16*60,wanted)).fetchall()
        db.executemany('INSERT INTO candles VALUES(?,?,?,?,?,?,?,?,?,?)',[tuple(r) for r in candles]);db.commit();db.execute('PRAGMA query_only=ON')
        return db,refs,stream_rows
    except BaseException:db.close();raise
    finally:registry.close()

def cycle(store,market_id,asof):
    before=time.monotonic();db,refs,prices=project(store,market_id,asof)
    try:result=features.calculate(db,market_id,stamp(asof))
    finally:db.close()
    if result is None:raise Stop('feature inputs unavailable/current market invalid')
    values,quality,evidence=result;p,reason=forecasts.baseline(values,quality)
    # Bind copied evidence and durable prediction in one core commit.
    with store.worker_session():
        metadata_id=evidence['metadata_observation_id'];generation_refs={'metadata':{'id':metadata_id,'generation_id':refs[('observations',metadata_id)]}}
        price_info=evidence['price'];price_event=None
        if price_info['source']=='coinbase_stream':
            key=price_info['input_id'];price_event=store.core.execute("SELECT * FROM events WHERE dataset='stream_events' AND event_key=?",('coinbase:'+key,)).fetchone()
            row=next(r for r in prices if r['event_id']==key)
            generation_refs['price']={'source':'coinbase','event_id':key,'generation_id':refs[('stream_events',key)]}
        eid=price_event['id'] if price_event else metadata_id
        with store.core:
            if price_event:store.pin_record(eid,{'generation_id':price_event['gen'],'dataset':'stream_events','row':row})
            enriched={**evidence,'raw_generation_refs':generation_refs}
            store.core.execute('INSERT OR IGNORE INTO feature_snapshots(market_id,as_of,version,values_json,quality_json,evidence_json) VALUES(?,?,?,?,?,?)',(market_id,iso(asof),features.VERSION,canonical(values),canonical(quality),canonical(enriched)))
            snapshot_id=store.core.execute('SELECT id FROM feature_snapshots WHERE market_id=? AND as_of=? AND version=?',(market_id,iso(asof),features.VERSION)).fetchone()[0]
            prediction='baseline:'+market_id+':'+iso(asof)
            store.core.execute('INSERT OR IGNORE INTO predictions VALUES(?,?,?,?,?)',(prediction,market_id,iso(asof),str(p) if p is not None else None,eid))
            store.core.execute('INSERT OR IGNORE INTO prediction_details VALUES(?,?,?,?)',(prediction,snapshot_id,forecasts.MODEL,reason))
    return {'result':result,'prediction':p,'abstain_reason':reason,'duration_seconds':time.monotonic()-before,'cycle':((market_id,values,quality),snapshot_id,iso(asof),(p,reason)),'generation_refs':generation_refs}
