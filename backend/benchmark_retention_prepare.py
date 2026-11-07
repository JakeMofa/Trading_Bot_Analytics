"""Compare immutable approved-identity TEMP preparation on generated data only."""
from datetime import datetime,timedelta,timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).parent/'app'))
import retention

base=datetime(2026,10,1,tzinfo=timezone.utc)
identities={('coinbase',str(i),(base+timedelta(microseconds=i*100000)).isoformat(timespec='microseconds')) for i in range(196509)}
with tempfile.TemporaryDirectory(prefix='generated-retention-prepare-') as folder:
    os.environ['SQLITE_TMPDIR']=folder
    db=sqlite3.connect(str(Path(folder)/'fixture.db'));results=[]
    for method in ('unordered_uncached','ordered_bounded_cache'):
        db.execute('PRAGMA temp.cache_size='+('0' if method=='unordered_uncached' else '-16384'))
        started=time.monotonic()
        if method=='unordered_uncached':
            db.execute('DROP TABLE IF EXISTS temp.retention_pending_stream_events')
            db.execute('CREATE TEMP TABLE retention_pending_stream_events(stamp TEXT,source TEXT,event_id TEXT,received_at TEXT,PRIMARY KEY(stamp,source,event_id,received_at)) WITHOUT ROWID')
            db.executemany('INSERT INTO temp.retention_pending_stream_events VALUES(?,?,?,?)',
                ((retention.canonical_time(k[2]),k[0],k[1],k[2]) for k in identities));db.commit()
        else:retention._prepare_pending(db,'stream_events',identities)
        seconds=time.monotonic()-started
        count=db.execute('SELECT COUNT(*) FROM temp.retention_pending_stream_events').fetchone()[0]
        assert count==len(identities)
        results.append({'method':method,'seconds':seconds,'rows':count})
    print(json.dumps({'generated_only':True,'local_not_qualification':True,'results':results}))
    db.close()
