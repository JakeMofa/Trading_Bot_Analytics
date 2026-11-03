"""One bounded generated A/B/core workload. No production reads or mutations."""
import asyncio,json,os,resource,signal,sqlite3,sys,tempfile,time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from raw_generations import Store,FileArchive,Stop,Unproven,iso


def event_at(i,rows):
    T=datetime(2026,1,1,tzinfo=timezone.utc)
    if i==0:return T
    return T+timedelta(hours=71,minutes=59,seconds=i*.01) if i<rows//2 else T+timedelta(hours=72,seconds=(i-rows//2)*.01)

def profile(rows=4000,parent=None):
    if rows!=4000:raise ValueError('one fixed generated workload, not a matrix')
    started=time.monotonic();root=Path(tempfile.mkdtemp(prefix='generated-ab-',dir=parent))
    result={'status':'NOT_PROVEN','generated_only':True,'root':str(root),'rows':rows,'platform':sys.platform,
            'workload':'fixed saturation burst across simulated72h boundary; not live REST cadence',
            'feature_scope':'indexed input projection only; real features.calculate NOT QUALIFIED',
            'errors':[],'save_max_seconds':0.,'heartbeat_max_seconds':0.,'input_query_max_seconds':0.,
            'sampled_input_age_simulated_seconds':0.,'max_outstanding_features':1,'max_ingestion_backlog':0}
    s=Store(root);cloud=FileArchive(root/'archive-fixtures');T=datetime(2026,1,1,tzinfo=timezone.utc)
    metrics_lock=None;stop=False;query_tasks=[];pool=ThreadPoolExecutor(max_workers=1)
    try:
        async def run():
            nonlocal stop
            async def heartbeat():
                prev=time.monotonic()
                while not stop:
                    await asyncio.sleep(.05);now=time.monotonic();result['heartbeat_max_seconds']=max(result['heartbeat_max_seconds'],now-prev);prev=now
            beat=asyncio.create_task(heartbeat());archive_seconds=0.;archive_rows=0
            try:
                for i in range(rows):
                    at=event_at(i,rows)
                    payload='{"venue":"generated","price":12345.1234567890123456789,"padding":"'+('x'*512)+'"}'
                    dataset='observations' if i%3==0 else 'stream_events'
                    row=({'market_id':'before' if i<rows//2 else 'after','received_at':iso(at),'source_time':iso(at),'kind':'book','payload':payload} if dataset=='observations' else
                         {'source':'coinbase','event_id':str(i),'received_at':iso(at),'source_time':iso(at),'price':'12345.1234567890123456789','size':'0.00000001','side':'buy','payload':payload})
                    begin=time.monotonic();s.save(dataset,('obs:'+str(i)) if dataset=='observations' else ('coinbase:'+str(i)),row);duration=time.monotonic()-begin
                    result['save_max_seconds']=max(duration,result['save_max_seconds'])
                    if duration>=1:raise Stop('save gate failed; no retry')
                    if dataset=='stream_events' and i%200==1:
                        if query_tasks:await query_tasks.pop()
                        async def query(asof=at):
                            before=time.monotonic();value=await asyncio.get_running_loop().run_in_executor(pool,s.inputs,asof-timedelta(minutes=5),asof)
                            result['input_query_max_seconds']=max(result['input_query_max_seconds'],time.monotonic()-before)
                            if value['mean']!='12345.1234567890123456789':raise Stop('input equivalence failed')
                            age=(asof-datetime.fromisoformat(value['latest_source'])).total_seconds()
                            result['sampled_input_age_simulated_seconds']=max(age,result['sampled_input_age_simulated_seconds'])
                            if age>30:raise Stop('simulated input freshness gate failed')
                        query_tasks.append(asyncio.create_task(query()))
                    if i==rows//2:
                        before=time.monotonic();archive_rows+=s.archive_hour(cloud,at+timedelta(seconds=1));archive_seconds+=time.monotonic()-before
                    await asyncio.sleep(0)
                for task in query_tasks:await task
                # Incremental fixed1000-row batches, not an end-only upload policy.
                # Complete residual fixture backlog at a simulated next hourly tick.
                while True:
                    before=time.monotonic();count=s.archive_hour(cloud,T+timedelta(hours=74));archive_seconds+=time.monotonic()-before;archive_rows+=count
                    if not count:break
                    if time.monotonic()-started>160:raise Stop('archive workload deadline')
                result['archive_rows']=archive_rows;result['archive_seconds']=archive_seconds
            finally:stop=True;await beat
        asyncio.run(run())
        if result['heartbeat_max_seconds']>=1 or result['input_query_max_seconds']>30:raise Stop('latency gate failed')
        result['rotation_seconds']=s.last_rotation_seconds
        if s.last_rotation_seconds>=1:raise Stop('rotation interference gate failed')
        result['allocation_before_retirement']=s.allocation();result['wal_peak_bytes']=dict(s.wal_peaks)
        result['generation_files']={r['slot']:{'id':r['id'],'path':str(s.path(r['id'])),'state':r['state']} for r in s.core.execute("SELECT * FROM generations WHERE state!='retired'")}
        result['page_allocation']={}
        for file in [root/'core.db',*root.glob('raw-*.db')]:
            db=sqlite3.connect(file)
            try:result['page_allocation'][file.name]={'pages':db.execute('PRAGMA page_count').fetchone()[0],
                    'indexes':dict(db.execute("SELECT name,SUM(pgsize) FROM dbstat WHERE name IN (SELECT name FROM sqlite_schema WHERE type='index') GROUP BY name")),
                    'synchronous':db.execute('PRAGMA synchronous').fetchone()[0]}
            finally:db.close()
        if set(result['generation_files'])!={'A','B'}:raise Stop('profile did not exercise both roles')
        old=s.core.execute("SELECT id FROM generations WHERE state='sealed'").fetchone()[0]
        begin=time.monotonic()
        try:s.retire(old,cloud,T+timedelta(hours=145));result['retirement']='PASS'
        except Unproven as error:result['retirement']='NOT_PROVEN';result['retirement_limitation']=str(error)
        result['retirement_seconds']=time.monotonic()-begin
        result['allocation_after']=s.allocation();result['status']='PASS_SCALED' if result['retirement']=='PASS' else 'NOT_PROVEN'
        result['workload_complete']=result['archive_rows']==rows
        if not result['workload_complete']:raise Stop('archive workload incomplete')
        result['archive_rows_per_second']=rows/result['archive_seconds']
    except BaseException as e:result['status']='FAIL';result['errors'].append(type(e).__name__+':'+str(e))
    finally:
        pool.shutdown(wait=True);s.close();result['elapsed_seconds']=time.monotonic()-started
        rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss;result['rss_bytes']=rss if sys.platform=='darwin' else rss*1024
        if result['elapsed_seconds']>180 or result['rss_bytes']>512*1024**2:result['status']='FAIL';result['errors'].append('existing resource gate')
    return result

if __name__=='__main__':
    if sys.platform=='linux':resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))
    signal.signal(signal.SIGALRM,lambda *args:(_ for _ in ()).throw(TimeoutError('170s work deadline')));signal.alarm(170)
    r=profile();signal.alarm(0);print(json.dumps(r),flush=True)
    raise SystemExit(1 if r['status']=='FAIL' else 0)
