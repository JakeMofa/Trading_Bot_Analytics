"""Rejected indexed NOT IN candidate versus current merge; generated fixtures only.

This standalone diagnostic accepts no existing database path, creates no indexes
on application databases and removes its fixture. Timing is local/warm-cache,
not a qualification PASS. Defaults reproduce the October31 failed-candidate scale.
"""
import sqlite3,time,json,tempfile,os,argparse
from datetime import datetime,timedelta,timezone
from pathlib import Path
parser=argparse.ArgumentParser(description='Compare timestamp guards on generated data only; not Linux retention qualification.')
parser.add_argument('--observations',type=int,default=654328)
parser.add_argument('--stream-events',type=int,default=1896953)
args=parser.parse_args()
profile={'observations':args.observations,'stream_events':args.stream_events}
if min(profile.values())<100 or max(profile.values())>3000000:parser.error('row counts must be100..3000000')
with tempfile.TemporaryDirectory(prefix='generated-timestamp-plan-') as folder:
 os.environ['SQLITE_TMPDIR']=folder
 db=sqlite3.connect(str(Path(folder)/'generated.db'))
 db.executescript('CREATE TABLE observations(id INTEGER PRIMARY KEY,market_id TEXT,kind TEXT,received_at TEXT,payload TEXT); CREATE INDEX observations_market_kind_received ON observations(market_id,kind,received_at); CREATE TABLE stream_events(source TEXT,event_id TEXT,received_at TEXT,payload TEXT,PRIMARY KEY(source,event_id)); CREATE INDEX stream_cursor ON stream_events(received_at,source,event_id); CREATE TEMP TABLE retention_valid_times(value TEXT PRIMARY KEY) WITHOUT ROWID;')
 base=datetime(2026,10,1,tzinfo=timezone.utc)
 for table,n in profile.items():
  old_count=min(40031 if table=='observations' else 196509,n-1)
  recent=base+timedelta(days=3)
  for lo in range(0,n,2000):
   stamps=[((base if i<old_count else recent)+timedelta(microseconds=i+1)).isoformat(timespec='microseconds') for i in range(lo,min(lo+2000,n))]
   if table=='observations':db.executemany('INSERT INTO observations VALUES(?,?,?,?,?)',[(lo+j+1,str((lo+j)%97),str((lo+j)%3),v,'{}') for j,v in enumerate(stamps)])
   else:db.executemany('INSERT INTO stream_events VALUES(?,?,?,?)',[('coinbase',str(lo+j),v,'{}') for j,v in enumerate(stamps)])
   db.executemany('INSERT OR IGNORE INTO retention_valid_times VALUES(?)',[(s,) for s in stamps])
 db.commit();results=[]
 for variant in ('old_merge','candidate','cached_candidate'):
  cache_kib=131072 if variant=='cached_candidate' else 2000
  db.execute(f'PRAGMA temp.cache_size=-{cache_kib}')
  for table in ('observations','stream_events'):
   query=(f'SELECT received_at COLLATE BINARY FROM {table} EXCEPT SELECT value COLLATE BINARY FROM temp.retention_valid_times ORDER BY 1' if variant=='old_merge' or table=='stream_events' else 'SELECT DISTINCT received_at COLLATE BINARY FROM observations INDEXED BY observations_market_kind_received WHERE received_at IS NULL OR received_at COLLATE BINARY NOT IN (SELECT value FROM temp.retention_valid_times)')
   plan=list(db.execute('EXPLAIN QUERY PLAN '+query));times=[]
   for _ in range(3):
    start=time.monotonic();rows=list(db.execute(query));times.append(time.monotonic()-start)
   results.append({'variant':variant,'temp_cache_kib':cache_kib,'table':table,'seconds':times,'unknown_count':len(rows),'plan':plan})
 value={'generated_only':True,'local_warm_cache_not_qualification':True,'rows':profile,'results':results}
 print(json.dumps(value))
 db.close()
