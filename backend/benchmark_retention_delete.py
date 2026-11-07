"""Compare exact stream deletes on generated data; rollback each timed trial.

Never accepts an existing database path and never copies a database. Keeps the
same rows for both algorithms by rolling back generated-only test deletions.
"""
import argparse
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import sys
sys.path.insert(0,str(Path(__file__).parent/'app'))
import retention_timestamp_guards as guards

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--rows',type=int,default=1922598)
args=parser.parse_args()
if not 2000<=args.rows<=3000000:parser.error('rows must be2000..3000000')
with tempfile.TemporaryDirectory(prefix='generated-retention-delete-') as folder:
    db=sqlite3.connect(str(Path(folder)/'fixture.db'))
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('CREATE TABLE observations(received_at TEXT); CREATE TABLE stream_events(source TEXT,event_id TEXT,received_at TEXT,source_time TEXT,price TEXT,size TEXT,side TEXT,payload TEXT,PRIMARY KEY(source,event_id)); CREATE INDEX cursor ON stream_events(received_at,source,event_id); CREATE TEMP TABLE batch(source TEXT,event_id TEXT,received_at TEXT,PRIMARY KEY(received_at,source,event_id)) WITHOUT ROWID;')
    base=datetime(2026,10,1,tzinfo=timezone.utc)
    for lo in range(1,args.rows+1,20000):
        rows=[]
        for i in range(lo,min(lo+20000,args.rows+1)):
            at=(base+timedelta(microseconds=i*100000)).isoformat(timespec='microseconds')
            rows.append(('coinbase',str(i),at,at,'100.000001','0.1','buy','{}'))
        db.executemany('INSERT INTO stream_events VALUES(?,?,?,?,?,?,?,?)',rows);db.commit()
    db.execute('BEGIN IMMEDIATE');guards.create_indexes(db);db.commit()
    selected=[('coinbase',str(i),(base+timedelta(microseconds=i*100000)).isoformat(timespec='microseconds')) for i in range(1001,2001)]
    results=[]
    queries={
        'per_row':'DELETE FROM stream_events WHERE source=? AND event_id=? AND received_at=?',
        'cursor_row':'DELETE FROM stream_events INDEXED BY cursor WHERE source=? AND event_id=? AND received_at=?',
        'cached_cursor_row':'DELETE FROM stream_events INDEXED BY cursor WHERE source=? AND event_id=? AND received_at=?',
        'tuple_batch':'DELETE FROM stream_events WHERE (received_at,source,event_id) IN (SELECT received_at,source,event_id FROM temp.batch)',
        'rowid_join':'DELETE FROM stream_events WHERE rowid IN (SELECT raw.rowid FROM temp.batch AS b CROSS JOIN stream_events AS raw ON raw.source=b.source AND raw.event_id=b.event_id AND raw.received_at=b.received_at)'}
    for name,query in queries.items():
        db.execute("PRAGMA main.cache_size="+("-16384" if name=="cached_cursor_row" else "-2000"))
        times=[]
        for _ in range(3):
            db.execute('BEGIN IMMEDIATE');start=time.monotonic()
            if name in ('per_row','cursor_row','cached_cursor_row'):changed=db.executemany(query,selected).rowcount
            else:
                db.executemany('INSERT INTO temp.batch VALUES(?,?,?)',selected)
                changed=db.execute(query).rowcount
            times.append(time.monotonic()-start)
            assert changed==1000,(name,changed)
            db.rollback()
        plan=list(db.execute('EXPLAIN QUERY PLAN '+query,selected[0] if name in ('per_row','cursor_row','cached_cursor_row') else ()))
        results.append({'method':name,'seconds':times,'plan':plan})
    import retention
    bound=min(args.rows,196509)
    lo=((base+timedelta(microseconds=100000)).isoformat(timespec='microseconds'),'coinbase','1')
    hi=((base+timedelta(microseconds=bound*100000)).isoformat(timespec='microseconds'),'coinbase',str(bound))
    marker=retention._validated_timestamp_cache(db);db.execute('BEGIN IMMEDIATE')
    retention._validate_current_timestamps(db,marker);range_results=[]
    for method in ('original','split_boundaries'):
        times=[]
        for _ in range(3):
            start=time.monotonic()
            if method=='original':
                where,params=retention._between(retention.SPECS['stream_events'],lo,hi)
                count=retention._count(db,retention.SPECS['stream_events'],where,params)
            else:count=retention._stream_range_count_validated(db,lo,hi)
            times.append(time.monotonic()-start);assert count==bound
        range_results.append({'method':method,'count':count,'seconds':times})
    db.rollback()
    print(json.dumps({'range_counts':range_results,'generated_only' :True,'local_not_qualification':True,'journal_mode':db.execute('PRAGMA journal_mode').fetchone()[0],'rows':args.rows,'delete_batch':1000,'results':results}))
    db.close()
