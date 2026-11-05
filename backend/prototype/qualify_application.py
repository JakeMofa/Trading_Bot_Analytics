"""Single exported-candidate ApplicationStore workload; generated fixtures ONLY.

4000 records, fixed simulated72h boundary, original170s work/180s total,
512MiB Linux AS and2GiB whole workspace. No production operation or retry matrix.
"""
import time
BOOT=float(__import__('os').environ.get('AB_PROFILE_STARTED',time.monotonic()))
import argparse,json,os,resource,signal,sys,tempfile
from pathlib import Path

def validate_workspace(workspace,report):
    workspace=Path(workspace);report=Path(report)
    if workspace.is_symlink() or not workspace.is_dir():raise ValueError('existing private qualification workspace required')
    root=workspace.resolve()
    if (not root.name.startswith(('ab-integration-','generated-ab-')) or root.stat().st_mode&0o077
        or root==Path('/opt/tradebot') or Path('/opt/tradebot') in root.parents):raise ValueError('generated workspace allowlist required')
    if report.is_symlink() or report.exists() or report.parent.resolve()!=root:raise ValueError('fresh report inside qualification workspace required')
    return root

def workspace_bytes(root):
    total=0
    for p in Path(root).rglob('*'):
        try:
            if p.is_file():total+=p.stat().st_size
        except FileNotFoundError:pass
    # SQLite TEMP may be unlinked while still allocated.
    if Path('/proc/self/fd').exists():
        pending=[os.getpid()];visited=set();seen=set();prefix=str(Path(root).resolve())+os.sep
        while pending:
            pid=pending.pop()
            if pid in visited:continue
            visited.add(pid)
            if len(visited)>32:raise RuntimeError('qualification process-family bound exceeded')
            try:
                descendants=Path(f'/proc/{pid}/task/{pid}/children').read_text().split()
                pending.extend(int(value) for value in descendants)
                for fd in Path(f'/proc/{pid}/fd').iterdir():
                    try:
                        target=os.readlink(fd)
                        if target.startswith(prefix) and target.endswith(' (deleted)'):
                            st=fd.stat();key=(st.st_dev,st.st_ino)
                            if key not in seen:total+=st.st_size;seen.add(key)
                    except FileNotFoundError:pass
            except FileNotFoundError:pass # Exited/reaped child has no allocated open file.
            except PermissionError:raise RuntimeError('process-family TEMP visibility incomplete') from None
    return total

def lifecycle_process(root,deadline,start,finish,report):
    # Fresh spawn: no inherited SQLite connections, collector lock or threads.
    from application_store import ApplicationWorker
    from generated_cloud import GeneratedRemote
    from cloud_lifecycle import LifecycleWorker,LifecycleConfig
    from retention import RetentionConfig
    result={'status':'FAIL','cycles':[]}
    worker=None
    try:
        if not start.wait(max(0,deadline-time.monotonic())):raise TimeoutError('lifecycle start deadline')
        worker=ApplicationWorker(root,Path(root)/'generated-legacy.db',routing=True,role='lifecycle')
        remote=GeneratedRemote(Path(root)/'cloud-fixture')
        lifecycle=LifecycleWorker('unused',LifecycleConfig(raw_batch_size=1000),RetentionConfig(),lambda:remote.client(deadline),connection_factory=worker.connection)
        result['cycles'].append(lifecycle.run_cycle(force=True))
        if not finish.wait(max(0,deadline-time.monotonic())):raise TimeoutError('lifecycle finish deadline')
        result['cycles'].append(lifecycle.run_cycle(force=True))
        if any(c['status']!='ok' for c in result['cycles']):raise RuntimeError('lifecycle stage failed')
        result['status']='PASS'
    except BaseException as error:result['error_type']=type(error).__name__
    finally:
        if worker:worker.close()
        Path(report).write_text(json.dumps(result));

def profile(candidate,sha,workspace):
    from build_ab_candidate import verify_export
    from application_store import ApplicationStore,ApplicationWorker
    from generated_cloud import GeneratedRemote
    from raw_generations import Stop,Unproven,iso
    from qualify_ab import event_at
    import asyncio,multiprocessing
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime,timedelta,timezone
    from unittest.mock import patch
    sys.path.insert(0,str(Path(candidate)/'backend/tests'))
    from test_ab_application import legacy,market,T
    import collector,streaming,features,forecasts,dashboard,ensemble
    from live_state import LiveState
    verify_export(candidate,sha,repo=os.environ.get('AB_SOURCE_REPOSITORY'))
    fresh_b=os.environ.get('AB_QUALIFICATION_MODE')=='fresh-b'
    root=Path(tempfile.mkdtemp(prefix='generated-ab-',dir=workspace));os.environ['SQLITE_TMPDIR']=str(root)
    deadline=BOOT+170;result={'status':'NOT_PROVEN','source_sha':sha,'generated_only':True,
        'path':'ApplicationStore + real collector/feature/forecast/history/ensemble + separate LifecycleWorker + SupabaseHTTP MockTransport',
        'workload':'4000 fixed saturation records,512-byte padding,simulated72h boundary; not real venue/network cadence',
        'root':str(root),'errors':[],'rows_requested':4000,'save_max_seconds':None,'heartbeat_max_seconds':None,
        'feature_max_seconds':None,'history_max_seconds':None,'published_age_max_simulated_seconds':None,
        'input_age_max_simulated_seconds':None,'feature_cycles':0,'published_cycles':0,'rejected_publications':0,'published_by_market':{},'rejected_contexts':[],
        'max_outstanding_features':1,'max_ingestion_backlog':0,'TEMP_accounting':'named files plus unique unlinked inodes across Linux process family','workspace_peak_bytes':workspace_bytes(workspace)}
    def maximum(key,value):result[key]=max(value,result[key]) if result[key] is not None else value
    def guard():
        result['workspace_peak_bytes']=max(result['workspace_peak_bytes'],workspace_bytes(workspace))
        if result['workspace_peak_bytes']>2*1024**3:raise Stop('whole exported workspace2GiB gate')
        if time.monotonic()>=deadline:raise TimeoutError('original work deadline exhausted')
    s=None;db=None;life=None;pool=None;finish=None
    try:
        legacy(root/'generated-legacy.db');s=ApplicationStore(root,root/'generated-legacy.db',routing=True,retirement=False,fresh_b=fresh_b)
        result['startup_mode']='fresh-b' if fresh_b else 'full-import'
        result['legacy_retirement']='HELD'
        # Count exported source and reports against the original workspace budget.
        source_bytes=workspace_bytes(candidate);s.protocol.ceiling=2*1024**3-source_bytes-1024**2
        db=s.connection();state=LiveState()
        with db:
            wanted=int((T+timedelta(hours=72)).timestamp())//60*60-60
            for k in range(18):
                at=wanted-k*60;p=str(12300+(k%3)*10)
                db.execute('INSERT OR IGNORE INTO candles VALUES(?,?,?,?,?,?,?,?,?,?)',('coinbase','BTC-USD',60,at,p,p,p,p,'1.00000001',iso(datetime.fromtimestamp(at+60,timezone.utc))))
        result['preparation_seconds']=time.monotonic()-BOOT
        ctx=multiprocessing.get_context('spawn');start=ctx.Event();finish=ctx.Event();life_report=root/'lifecycle-result.json'
        life=ctx.Process(target=lifecycle_process,args=(str(root),deadline,start,finish,str(life_report)));life.start()
        pool=ThreadPoolExecutor(max_workers=1);future=None;asof=None;current=None;stop=False
        def feature_job(at):
            before=time.monotonic()
            with patch.object(features,'utcnow',return_value=at),patch.object(forecasts,'utcnow',return_value=at),patch.object(ensemble,'utcnow',return_value=at):
                value=streaming.feature_cycle('unused',lambda:s.worker_connection('feature'))
            reader=s.worker_connection('history')
            try:
                begin=time.monotonic();chart=dashboard.chart_data(reader,at);query_duration=time.monotonic()-begin
                if not chart['market'] or not chart['points']:raise Stop('actual history unavailable')
            finally:reader.close()
            worker=s.worker_connection('feature')
            try:
                if value:ensemble.compute_ensemble_for_snapshot(worker,value[1])
            finally:worker.close()
            return value,time.monotonic()-before,query_duration
        async def run():
            nonlocal future,asof,current,stop
            async def heartbeat():
                prior=time.monotonic()
                while not stop:
                    await asyncio.sleep(.05);now=time.monotonic();maximum('heartbeat_max_seconds',now-prior);prior=now;guard()
            def completed(value,now):
                cycle,duration,history=value
                if not cycle:raise Stop('actual feature cycle unavailable')
                maximum('feature_max_seconds',duration);maximum('history_max_seconds',history);result['feature_cycles']+=1
                age=cycle[0][2]['price']['age_seconds']
                if age is None or age>30 or duration>30:raise Stop('feature input/completion gate')
                maximum('input_age_max_simulated_seconds',age)
                with patch('live_state.utcnow',return_value=now):published=streaming.publish_feature_cycle(cycle,state,now=now)
                if published:
                    result['published_cycles']+=1;market_id=cycle[0][0];result['published_by_market'][market_id]=result['published_by_market'].get(market_id,0)+1;maximum('published_age_max_simulated_seconds',(now-datetime.fromisoformat(cycle[2])).total_seconds())
                else:
                    result['rejected_publications']+=1
                    if len(result['rejected_contexts'])<20:result['rejected_contexts'].append({'snapshot_market':cycle[0][0],'current_market':(state.snapshot(now).get('market') or {}).get('id'),'age_seconds':(now-datetime.fromisoformat(cycle[2])).total_seconds()})
            beat=asyncio.create_task(heartbeat())
            try:
                for i in range(4000):
                    at=event_at(i,4000);asof=at;before=time.monotonic()
                    if i in (0,1,2000):
                        label='seed' if i==0 else 'before' if i==1 else 'after'
                        begun=T if i==0 else T+timedelta(hours=71,minutes=45) if i==1 else T+timedelta(hours=72)
                        current=market(begun,label);collector.save_market(db,current,iso(at));streaming.sync_live_market(db,state,at)
                    elif i%3==0:
                        msg={'marketData':{'marketSlug':current['slug'],'transactTime':iso(at),'stats':{'lastPriceSample':{'longPx':{'value':'0.51'},'shortPx':{'value':'0.49'}}}},'padding':'x'*512}
                        with patch.object(streaming,'utcnow',return_value=at):
                            if not streaming.save_polymarket(db,msg):raise Stop('book not committed')
                        state.update_polymarket(msg,iso(at))
                    else:
                        msg=dict(type='ticker',product_id='BTC-USD',trade_id=10000+i,time=iso(at),price='12345.1234567890123456789',last_size='0.00000001',side='buy',padding='x'*512)
                        with patch.object(streaming,'utcnow',return_value=at):
                            if not streaming.save_coinbase(db,msg):raise Stop('ticker not committed')
                        state.update_coinbase_ticker(msg,iso(at))
                    duration=time.monotonic()-before;maximum('save_max_seconds',duration)
                    if duration>=1:raise Stop('collector save gate; no retry')
                    if future and future.done():completed(future.result(),at);future=None
                    if i%200==2 and future is None:future=pool.submit(feature_job,at)
                    if i==2000:start.set()
                    guard();await asyncio.sleep(0)
                if future:completed(await asyncio.wrap_future(future),asof)
                finish.set()
                while life.is_alive():guard();await asyncio.sleep(.05)
                life.join()
            finally:stop=True;await beat
        asyncio.run(run());pool.shutdown(wait=True);pool=None
        if result['heartbeat_max_seconds'] is None or result['heartbeat_max_seconds']>=1:raise Stop('heartbeat gate')
        if result['feature_cycles']<3 or result['published_cycles']<3:raise Stop('insufficient real feature/publication cycles')
        if any(result['published_by_market'].get(m,0)<1 for m in ('before','after')):raise Stop('publication not proven in both boundary markets')
        if (state.market_identity() or (None,))[0]!='after':raise Stop('discovery did not retain current market identity')
        result['final_market_identity']=list(state.market_identity())
        if result['published_age_max_simulated_seconds']>30:raise Stop('stale publication')
        result['lifecycle']=json.loads(life_report.read_text())
        if result['lifecycle']['status']!='PASS':raise Stop('separate lifecycle incomplete')
        result['committed_rows']=db.execute("SELECT COUNT(*) FROM ab_events WHERE status='committed'").fetchone()[0]
        result['pending_rows']=db.execute("SELECT COUNT(*) FROM ab_events WHERE status='pending'").fetchone()[0]
        result['archived_rows']=sum(d['archived'] for c in result['lifecycle']['cycles'] for d in c['archive'].values())
        if result['committed_rows']!=4000 or result['pending_rows'] or result['archived_rows']!=(4000 if fresh_b else 4002):raise Stop('workload identity/completion mismatch')
        result['sqlite_runtime']=list(db.execute('SELECT sqlite_version(),sqlite_source_id()').fetchone())
        result['allocation_before_retirement']=s.protocol.allocation();result['wal_peak_bytes']=dict(s.protocol.wal_peaks)
        result['generation_files']={r['slot']:{'id':r['id'],'state':r['state']} for r in s.protocol.core.execute("SELECT * FROM generations WHERE state!='retired'")}
        if set(result['generation_files'])!={'A','B'}:raise Stop('both generations not exercised')
        result['rotation_seconds']=s.protocol.last_rotation_seconds
        # No app handle may remain when retirement starts; production gate stays off.
        db.close();db=None
        old=next(g['id'] for g in result['generation_files'].values() if g['state']=='sealed');cloud=GeneratedRemote(root/'cloud-fixture').client(deadline)
        begin=time.monotonic()
        try:
            # Explicit generated qualification only; never toggles production flags.
            s.protocol.retire(old,cloud,T+timedelta(hours=145));result['retirement']='PASS'
        except Unproven as error:result['retirement']='NOT_PROVEN';result['retirement_limitation']=str(error)
        finally:cloud.close()
        result['retirement_seconds']=time.monotonic()-begin
        db=s.connection()
        if db.execute('PRAGMA foreign_key_check').fetchall():raise Stop('reference integrity failed')
        for (evidence,) in db.execute('SELECT evidence_json FROM feature_snapshots').fetchall():
            mid=json.loads(evidence)['metadata_observation_id']
            if not db.execute('SELECT 1 FROM main.observations WHERE id=?',(mid,)).fetchone():raise Stop('protected metadata lost')
        result['legacy_outcome_reference']=db.execute('SELECT outcome_observation_id FROM prediction_context_links WHERE id=1').fetchone()[0]
        if result['legacy_outcome_reference']!=90:raise Stop('legacy outcome identity changed')
        guard();result['workload_complete']=True
        result['status']='PASS_SCALED_INTEGRATED' if result['retirement']=='PASS' else 'NOT_PROVEN'
    except BaseException as error:
        result['status']='FAIL';result['errors'].append(type(error).__name__+':'+str(error))
    finally:
        if finish:finish.set()
        if life and life.is_alive():life.kill();life.join()
        if pool:pool.shutdown(wait=True)
        if db:db.close()
        if s:s.close()
        result['elapsed_seconds']=time.monotonic()-BOOT
        rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss;result['rss_bytes']=rss if sys.platform=='darwin' else rss*1024
        result['workspace_peak_bytes']=max(result['workspace_peak_bytes'],workspace_bytes(workspace))
        if result['elapsed_seconds']>180 or result['rss_bytes']>512*1024**2 or result['workspace_peak_bytes']>2*1024**3:
            result['status']='FAIL';result['errors'].append('existing overall resource gate')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sha',required=True);parser.add_argument('--workspace',required=True);parser.add_argument('--report',required=True)
    args=parser.parse_args();validate_workspace(args.workspace,args.report)
    import math
    if not math.isfinite(BOOT) or BOOT>time.monotonic() or time.monotonic()-BOOT>=170:parser.error('original work budget already expired')
    if sys.platform=='linux':resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))
    signal.signal(signal.SIGALRM,lambda *a:(_ for _ in ()).throw(TimeoutError('original170s work deadline')));signal.alarm(max(1,int(170-(time.monotonic()-BOOT))))
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    r=profile(Path(__file__).resolve().parents[2],args.sha,Path(args.workspace));signal.alarm(0)
    r['workspace_peak_bytes']+=len(json.dumps(r).encode())+4096
    if r['workspace_peak_bytes']>2*1024**3:r['status']='FAIL';r['errors'].append('report-inclusive workspace gate')
    Path(args.report).write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:r.get(k) for k in ('status','committed_rows','archived_rows','save_max_seconds','heartbeat_max_seconds','feature_cycles','elapsed_seconds','errors')}),flush=True)
    raise SystemExit(0 if r['status']=='PASS_SCALED_INTEGRATED' else 1)
