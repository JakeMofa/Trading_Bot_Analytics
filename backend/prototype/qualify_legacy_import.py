"""Generated known-structured-cardinality import; NOT full legacy-volume proof.

Original 2GiB workspace, 512MiB/process (Linux), 170s work/180s total.
An outer supervisor includes fixture preparation, verification and cleanup.
"""
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import sqlite3
import sys
import tempfile
import time

BOOT=float(os.environ.get('AB_PROFILE_STARTED',time.monotonic()))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from test_ab_application import legacy,T,iso
from application_store import ApplicationStore
from migration_budget import MigrationBudget
from datetime import timedelta

TABLES={'markets':1826,'feature_snapshots':18289,'predictions':27743,'prediction_context_links':20,'news_events':28}


def digest_table(db,table):
    checksum=hashlib.sha256()
    for row in db.execute('SELECT * FROM "'+table+'" ORDER BY rowid'):
        body=json.dumps(tuple(row),ensure_ascii=True,separators=(',',':')).encode()
        checksum.update(len(body).to_bytes(8,'big'));checksum.update(body)
    return checksum.hexdigest()


def qualify():
    if sys.platform=='linux':resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))
    root=Path(tempfile.mkdtemp(prefix='generated-ab-import-',dir=os.environ.get('AB_IMPORT_WORKSPACE')))
    result={'status':'FAIL','scope':'known structured counts only; raw volume and embedded-reference distribution NOT PROVEN',
            'limits':{'workspace_bytes':2*1024**3,'audit_bytes':128*1024**2,'rows':60000,
                      'work_seconds':170,'total_seconds':180,'linux_address_space_bytes':512*1024**2},
            'source_sha':os.environ.get('AB_IMPORT_SOURCE_SHA'),'counts':TABLES}
    owner=None
    def guard():
        if time.monotonic()-BOOT>=170:raise TimeoutError('original generated work deadline')
        files=list(root.rglob('*'))
        source_bytes=int(os.environ.get('AB_IMPORT_SOURCE_BYTES','0'))
        logical=source_bytes+sum(p.stat().st_size for p in files if p.is_file())
        allocated=source_bytes+sum(p.stat().st_blocks*512 for p in files if p.is_file())
        result['sampled_logical_peak_bytes']=max(logical,result.get('sampled_logical_peak_bytes',0))
        result['sampled_allocated_peak_bytes']=max(allocated,result.get('sampled_allocated_peak_bytes',0))
        if max(logical,allocated)>2*1024**3:raise RuntimeError('original workspace budget')
    try:
        path=root/'generated-legacy.db';legacy(path)
        db=sqlite3.connect(path)
        try:
            def columns(table):return [r[1] for r in db.execute('PRAGMA table_info('+table+')')]
            with db:
                cols=columns('markets');seed=dict(zip(cols,db.execute('SELECT * FROM markets').fetchone()))
                for i in range(1,TABLES['markets']):
                    row={**seed,'id':'fixture-market-'+str(i),'slug':'fixture-market-'+str(i)}
                    db.execute('INSERT INTO markets VALUES('+','.join('?' for _ in cols)+')',[row[c] for c in cols])
                cols=columns('feature_snapshots');seed=dict(zip(cols,db.execute('SELECT * FROM feature_snapshots').fetchone()))
                for i in range(2,TABLES['feature_snapshots']+1):
                    row={**seed,'id':i,'as_of':iso(T+timedelta(microseconds=i))}
                    db.execute('INSERT INTO feature_snapshots VALUES('+','.join('?' for _ in cols)+')',[row[c] for c in cols])
                    if i%1000==0:guard()
                cols=columns('predictions');seed=dict(zip(cols,db.execute('SELECT * FROM predictions').fetchone()))
                for i in range(2,TABLES['predictions']+1):
                    row={**seed,'id':i,'snapshot_id':(i-1)%TABLES['feature_snapshots']+1,
                         'model_version':'generated-'+str((i-1)//TABLES['feature_snapshots'])}
                    db.execute('INSERT INTO predictions VALUES('+','.join('?' for _ in cols)+')',[row[c] for c in cols])
                    if i%1000==0:guard()
                for i in range(1,29):
                    db.execute('INSERT INTO news_events VALUES(?,?,?,?,?,?,?,?,?,?)',
                        (i,'generated-only',str(i),'https://fixture.invalid/'+str(i),
                         'Generated Bitcoin '+str(i),iso(T),iso(T),iso(T),'[]','BTC'))
                for i in range(91,98):
                    db.execute('INSERT INTO observations VALUES(?,?,?,?,?,?)',(i,'m',iso(T),iso(T),'resolution','{}'))
                cols=columns('prediction_context_links');seed=dict(zip(cols,db.execute('SELECT * FROM prediction_context_links').fetchone()))
                for i in range(2,21):
                    row={**seed,'id':i,'prediction_id':i,'outcome_observation_id':90+(i-1)%8}
                    db.execute('INSERT INTO prediction_context_links VALUES('+','.join('?' for _ in cols)+')',[row[c] for c in cols])
            selfcheck=db.execute('PRAGMA foreign_key_check').fetchall()
            if selfcheck:raise RuntimeError('generated source FK')
            expected={table:digest_table(db,table) for table in TABLES}
        finally:db.close()
        guard();result['preparation_seconds']=time.monotonic()-BOOT
        # Default still rejects this count. Explicit generated scope changes rows
        # only; original byte, RAM, workspace and whole-operation limits remain.
        begin=time.monotonic()
        owner=ApplicationStore(root,path,routing=True,
            migration_budget=MigrationBudget(row_limit=60000,deadline=BOOT+170))
        result['constructor_seconds']=time.monotonic()-begin
        result['import_metrics']=owner.import_metrics
        # Count/sample while the core WAL is still allocated, before last close.
        guard();result['protocol_peak_bytes']=owner.protocol.peak
        core=owner.protocol.core.native
        checks=time.monotonic()
        quick=[tuple(row) for row in core.execute('PRAGMA quick_check')]
        result['core_quick_check']=quick
        if quick!=[('ok',)]:raise RuntimeError('core quick_check: '+repr(quick[:3]))
        if core.execute('PRAGMA foreign_key_check').fetchall():raise RuntimeError('core FK')
        for table,count in TABLES.items():
            if core.execute('SELECT count(*) FROM '+table).fetchone()[0]!=count:raise RuntimeError('count '+table)
            if digest_table(core,table)!=expected[table]:raise RuntimeError('exact structured identity '+table)
        if core.execute("SELECT count(*) FROM news_events_fts WHERE news_events_fts MATCH 'Generated'").fetchone()[0]!=28:
            raise RuntimeError('news FTS rebuild')
        if core.execute('SELECT count(DISTINCT outcome_observation_id) FROM prediction_context_links').fetchone()[0]!=8:
            raise RuntimeError('eight protected outcome references')
        if core.execute('SELECT count(*) FROM observations WHERE id BETWEEN 90 AND 97').fetchone()[0]!=8:
            raise RuntimeError('protected outcome body preservation')
        reader=owner.reader_connection()
        try:
            if reader.execute('SELECT count(*) FROM predictions').fetchone()[0]!=27743:raise RuntimeError('application history routing')
        finally:reader.close()
        result['quick_fk_and_exact_structured_verification_seconds']=time.monotonic()-checks
        guard();owner.close();owner=None
        restart=time.monotonic()
        owner=ApplicationStore(root,path,routing=True,
            migration_budget=MigrationBudget(row_limit=60000,deadline=BOOT+170))
        result['restart_audit_seconds']=time.monotonic()-restart
        guard();result['status']='PASS_KNOWN_STRUCTURED_COUNTS_ONLY'
    except Exception as error:
        result.update(error_type=type(error).__name__,error=str(error))
    finally:
        if owner:owner.close()
        shutil.rmtree(root)
        result['elapsed_including_cleanup_seconds']=time.monotonic()-BOOT
        rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        result['rss_bytes']=rss if sys.platform=='darwin' else rss*1024
        if result['elapsed_including_cleanup_seconds']>180:result['status']='FAIL'
    return result

if __name__=='__main__':
    result=qualify()
    if len(sys.argv)==3 and sys.argv[1]=='--report':
        with open(sys.argv[2],'x') as report:json.dump(result,report,sort_keys=True)
    print(json.dumps(result,sort_keys=True),flush=True)
    raise SystemExit(0 if result['status']=='PASS_KNOWN_STRUCTURED_COUNTS_ONLY' else 1)
