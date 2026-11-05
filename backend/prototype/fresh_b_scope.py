"""Read-only startup-input census; no raw history scan or production authority."""
from contextlib import closing
from datetime import datetime,timezone
import json,re,sqlite3,time
from pathlib import Path

RAW={'observations','stream_events'}

def inventory(path,seconds=5,row_limit=150000,byte_limit=128*1024**2):
    if not 0<seconds<=5 or not 0<row_limit<=150000 or not 0<byte_limit<=128*1024**2:raise ValueError('bounded inventory required')
    path=Path(path)
    if path.is_symlink() or not path.is_file():raise ValueError('existing nonsymlink legacy required')
    end=time.monotonic()+seconds
    def check():
        if time.monotonic()>=end:raise TimeoutError('whole input inventory deadline')
    def binding():
        result={}
        for suffix in ('','-wal'):
            p=Path(str(path)+suffix)
            if p.is_symlink():raise ValueError('sidecar symlink')
            if p.exists():
                s=p.stat()
                if not suffix or s.st_size:result[suffix or 'main']=[s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns]
        return result
    before=binding();counts={};size=0;total=0;pins=set();stream=set()
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=.1)) as db:
        db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON');db.set_progress_handler(lambda:int(time.monotonic()>=end),1000)
        db.execute('BEGIN')
        # Reject missing protected inputs before spending the bulk inventory budget.
        # Every lookup uses the legacy primary identity; never substitute a nearby row.
        seen=set()
        for snapshot in db.execute('SELECT id,evidence_json FROM feature_snapshots LIMIT 20001'):
            check()
            evidence=json.loads(snapshot['evidence_json']);key=evidence.get('metadata_observation_id')
            if type(key) is not int or key<=0:raise ValueError('missing selected metadata identity at snapshot '+str(snapshot['id']))
            if key not in seen:
                if db.execute('SELECT 1 FROM observations WHERE id=?',(key,)).fetchone() is None:
                    raise ValueError('missing selected metadata '+str(key)+' at snapshot '+str(snapshot['id']))
                seen.add(key)
            if len(seen)>20000:raise ValueError('protected snapshot scope exceeded')
        shadows={r[1] for r in db.execute('PRAGMA table_list') if r[2]=='shadow'}
        tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'") if r[0] not in RAW|shadows|{'news_events_fts'}]
        if len(tables)>64:raise ValueError('table scope exceeded')
        for table in tables:
            if not re.fullmatch('[A-Za-z_][A-Za-z_0-9]*',table):raise ValueError('unknown table identity')
            count=0
            for row in db.execute('SELECT * FROM "'+table+'" LIMIT ?', (row_limit-total+1,)):
                check();total+=1;count+=1
                if total>row_limit:raise ValueError('structured row scope exceeded')
                size+=len(json.dumps(tuple(row),separators=(',',':')).encode())
                if size>byte_limit:raise ValueError('structured byte scope exceeded')
                if table=='feature_snapshots':
                    evidence=json.loads(row['evidence_json']);pins.add(evidence['metadata_observation_id'])
                    price=evidence.get('price') or {}
                    if price.get('source')=='coinbase_stream':stream.add(('coinbase',str(price['input_id'])))
            counts[table]=count
            for fk in db.execute('PRAGMA foreign_key_list("'+table+'")'):
                if fk['table']=='observations':
                    if fk['to']!='id' or not re.fullmatch('[A-Za-z_][A-Za-z_0-9]*',fk['from']):raise ValueError('unsupported protected reference')
                    pins.update(r[0] for r in db.execute('SELECT "'+fk['from']+'" FROM "'+table+'" WHERE "'+fk['from']+'" IS NOT NULL'))
        latest=db.execute("SELECT source,event_id FROM stream_events NOT INDEXED WHERE source='coinbase' ORDER BY rowid DESC LIMIT 1").fetchone()
        if latest:stream.add(tuple(latest))
        now=datetime.now(timezone.utc).isoformat()
        markets=db.execute("SELECT id FROM markets WHERE duration=900 AND status='MARKET_STATUS_OPEN' AND julianday(start)<=julianday(?) AND julianday(end)>julianday(?) LIMIT 33",(now,now)).fetchall()
        if len(markets)>32:raise ValueError('current market scope exceeded')
        for market in markets:
            row=db.execute("SELECT id FROM observations WHERE market_id=? AND kind='metadata' ORDER BY id DESC LIMIT 1",(market[0],)).fetchone()
            if row:pins.add(row[0])
        for table,keys,query in (('observations',pins,'SELECT * FROM observations WHERE id=?'),('stream_events',stream,'SELECT * FROM stream_events WHERE source=? AND event_id=?')):
            for key in keys:
                check();row=db.execute(query,key if isinstance(key,tuple) else (key,)).fetchone()
                if row is None:raise ValueError('missing selected legacy input')
                size+=len(json.dumps(tuple(row),separators=(',',':')).encode());total+=1
                if size>byte_limit or total>row_limit:raise ValueError('selected input scope exceeded')
        check();db.rollback()
    if binding()!=before:raise ValueError('legacy changed during inventory')
    return dict(status='PASS_BOUNDED_INPUT_CENSUS',binding=before,structured_counts=counts,
        selected_observations=len(pins),selected_stream_records=len(stream),rows=total,audit_bytes=size,
        candle_policy='all structured candle history preserved; prediction uses 17 completed BTC-USD 60s candles with first_seen<=as_of',
        raw_history='retained legacy; no raw scan',production_authority=False)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--legacy',required=True);a=p.parse_args()
    print(json.dumps(inventory(a.legacy),sort_keys=True))
