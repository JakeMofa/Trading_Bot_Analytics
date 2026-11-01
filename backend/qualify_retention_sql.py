"""Generated-data retention qualification. Never accepts a production DB path.

Actual deployed save/RAM code is imported read-only; writes target only a newly
generated fixture. Synthetic manifest claims test compute, not Supabase safety.
Each trial reserves ten of its180 seconds for cleanup. Stop after any failed gate.
"""
import argparse
import asyncio
from datetime import datetime,timedelta,timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import re
import signal
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request


def deployed(path):
    sys.path.insert(0,str(path))
    import streaming,collector,live_state
    return streaming,collector,live_state


def validate_fixture_path(path):
    parent=path.parent
    if (path.name!='fixture.db' or not parent.name.startswith('generated-retention-')
            or path.is_symlink() or parent.is_symlink()
            or parent.stat().st_uid!=os.getuid() or parent.stat().st_mode&0o077
            or Path('/opt/tradebot') in path.resolve().parents):
        raise ValueError('collector actor accepts only its private generated fixture')



def configure_fixture_checkpoint(db,path,pages):
    """Authorized generated-only automatic threshold; never manual checkpoint."""
    if pages not in (0,256):raise ValueError('only the authorized fixture threshold is allowed')
    if not pages:return
    validate_fixture_path(path)
    main=next(row[2] for row in db.execute('PRAGMA database_list') if row[1]=='main')
    if not main or Path(main).resolve()!=path.resolve() or db.in_transaction:
        raise ValueError('private generated main connection required')
    if db.execute('PRAGMA synchronous').fetchone()[0]!=2:
        raise ValueError('FULL durability must remain enabled')
    db.execute('PRAGMA wal_autocheckpoint=256')
    if db.execute('PRAGMA wal_autocheckpoint').fetchone()[0]!=256 or db.execute('PRAGMA synchronous').fetchone()[0]!=2:
        raise ValueError('fixture automatic threshold or durability mismatch')


def actor(args):
    validate_fixture_path(args.collector)
    resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))
    stream,collector,live=deployed(args.deployed_app)
    db=sqlite3.connect(args.collector,timeout=5);db.execute('PRAGMA foreign_keys=ON')
    state=live.LiveState();result={'saves':0,'ram_updates':0,'save_max_seconds':0,'heartbeat_max_seconds':0,'errors':[]}
    stop=args.collector.with_suffix('.stop');ready=args.collector.with_suffix('.ready')
    async def run():
        async def heartbeat():
            previous=time.monotonic()
            while not stop.exists():
                await asyncio.sleep(.05);now=time.monotonic()
                result['heartbeat_max_seconds']=max(result['heartbeat_max_seconds'],now-previous)
                previous=now
        beat=asyncio.create_task(heartbeat())
        i=0
        try:
            while not stop.exists():
                msg={'type':'ticker','product_id':'BTC-USD','trade_id':9000000000+i,
                     'price':'100.000001','last_size':'0.10','side':'buy',
                     'time':datetime.now(timezone.utc).isoformat()}
                started=time.monotonic()
                try:
                    saved=stream.save_coinbase(db,msg)
                    elapsed=time.monotonic()-started
                    result['save_max_seconds']=max(result['save_max_seconds'],elapsed)
                    if saved:
                        result['saves']+=1
                        state.update_coinbase_ticker(msg);result['ram_updates']+=1
                    if elapsed>=1:raise TimeoutError('collector save exceeded1s')
                    if not ready.exists():ready.write_text('ready')
                except Exception as error:
                    result['errors'].append(type(error).__name__);stop.touch();break
                i+=1
                await asyncio.sleep(max(0,.15-(time.monotonic()-started)))
        finally:
            stop.touch();await beat
    try:asyncio.run(run())
    finally:
        db.close();args.collector_report.write_text(json.dumps(result))


def manifest(dataset,lo,hi,start,end,trade_id_base=0):
    return {'source':'polymarket' if dataset=='observations' else 'coinbase',
            'bucket':'market-raw','object_path':'synthetic-only/'+dataset,
            'sha256':'a'*64,'event_count':hi-lo+1,'compressed_bytes':1,
            'first_source_id':lo,'last_source_id':hi,
            'started_at':start,'ended_at':end,'verified_at':end,
            'metadata':{'dataset':dataset,'verification':'authenticated_readback_sha256',
                        'first_source_key':json.dumps(['coinbase',str(trade_id_base+lo)]),
                        'last_source_key':json.dumps(['coinbase',str(trade_id_base+hi)])}}


class ProductionGuardStop(RuntimeError):
    def __init__(self,reason,projection):
        super().__init__(reason)
        self.reason,self.projection=reason,projection


def require_production_health(health,now=None):
    """Keep only typed safe diagnostics; never log arbitrary HTTP response bodies."""
    now=now or datetime.now(timezone.utc)
    projection={'collector_running':health.get('collector',{}).get('running') is True,'feeds':{}}
    bad=[]
    for name in ('coinbase_stream','polymarket_stream'):
        feed=health.get('feeds',{}).get(name,{})
        status=feed.get('status')
        if status not in ('live','running','stale','disconnected','connecting','stopped','awaiting_data','disabled'):
            status='unknown'
        try:
            stamp=datetime.fromisoformat(feed['last_data_at'].replace('Z','+00:00'))
            age=(now-stamp).total_seconds();at=stamp.isoformat()
        except (KeyError,TypeError,ValueError,AttributeError):age=None;at=None
        projection['feeds'][name]={'status':status,'last_data_at':at,'age_seconds':age}
        if status!='live' or age is None or not 0<=age<30:bad.append(name)
    if not projection['collector_running']:raise ProductionGuardStop('production_collector_stopped',projection)
    if bad:raise ProductionGuardStop('production_feed_not_fresh_live:'+','.join(bad),projection)
    return projection


def write_progress_report(path, result, failure, started):
    """Atomic provisional STOP survives child termination, never certifies a pass."""
    if path is None:return
    pending=dict(result)
    pending.update(status='STOP', incomplete=True,
                   production_guard_errors=list(failure),
                   elapsed_seconds=time.monotonic()-started)
    temporary=path.with_suffix('.pending')
    temporary.write_text(json.dumps(pending))
    temporary.replace(path)


def trial(args,number):
    start=time.monotonic();result={'trial':number,'started_at':datetime.now(timezone.utc).isoformat(),'status':'STOP','generated_only':True,
                                 'synthetic_archive_claims_not_cloud_verification':True,
                                 'trade_id_base':args.trade_id_base,'batch_size':getattr(args,'batch_size',1000)}
    worker=None;db=None;monitor_stop=threading.Event();failure=[]
    def checkpoint(stage, dataset=None, partial=None):
        result['stage']=stage
        if dataset is not None:result['active_dataset']=dataset
        if partial is not None:result['partial_apply']=partial
        if stage in ('before_batch','committed_batch'):
            wal=Path(str(path)+'-wal')
            samples=result.setdefault('commit_storage_samples',[])
            samples.append({'stage':stage,'dataset':dataset,'wal_bytes':wal.stat().st_size if wal.exists() else 0})
            del samples[:-16]
        write_progress_report(args.trial_report,result,failure,start)
    checkpoint('starting')
    def deadline(signum,frame):raise TimeoutError('trial work deadline/resource/production guard')
    previous={sig:signal.signal(sig,deadline) for sig in (signal.SIGALRM,signal.SIGUSR1)}
    signal.alarm(170)
    with tempfile.TemporaryDirectory(prefix='generated-retention-',dir=args.work_dir) as folder:
        folder=Path(folder);path=folder/'fixture.db';os.environ['SQLITE_TMPDIR']=str(folder)
        stop=path.with_suffix('.stop');ready=path.with_suffix('.ready');report=folder/'collector.json'
        def disk_bytes():
            identities={}
            for file in folder.iterdir():
                if file.is_file():
                    s=file.stat();identities[(s.st_dev,s.st_ino)]=s.st_size
            # SQLite may unlink TEMP files while their descriptors remain open.
            for file in Path('/proc/self/fd').iterdir():
                try:
                    if os.readlink(file).startswith(str(folder)):
                        s=file.stat();identities[(s.st_dev,s.st_ino)]=s.st_size
                except FileNotFoundError:pass
            return sum(identities.values())
        def monitor():
            next_probe=0.0
            while not monitor_stop.wait(.25):
                context={'reason':'fixture_disk_check'}
                try:
                    size=disk_bytes();result['peak_fixture_disk_bytes']=max(size,result.get('peak_fixture_disk_bytes',0))
                    if size>2*1024**3-4*1024**2:raise ProductionGuardStop('fixture_disk_limit',{'bytes':size})
                    if args.check_production and time.monotonic()>=next_probe:
                        context={'reason':'production_health_request_failed'}
                        with urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2) as response:
                            health=json.load(response)
                        require_production_health(health)
                        next_probe=time.monotonic()+5
                except Exception as error:
                    detail={'error_type':type(error).__name__,**context,'at':datetime.now(timezone.utc).isoformat()}
                    if isinstance(error,ProductionGuardStop):
                        detail.update(reason=error.reason,projection=error.projection)
                    failure.append(detail);os.kill(os.getpid(),signal.SIGUSR1);return
        watcher=threading.Thread(target=monitor,daemon=True);watcher.start()
        try:
            checkpoint('load_candidate')
            actual_sha=hashlib.sha256((args.deployed_app/'streaming.py').read_bytes()).hexdigest()
            if args.expected_save_sha256 and actual_sha!=args.expected_save_sha256:
                raise RuntimeError('deployed collector helper differs from qualified target')
            stream,collector,live=deployed(args.deployed_app)
            spec=importlib.util.spec_from_file_location('retention_candidate',args.candidate)
            sys.path.insert(0,str(args.candidate.parent))
            module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
            db=collector.connect(str(path));stream.initialize(db)
            result['sqlite_settings']={key:db.execute('PRAGMA '+key).fetchone()[0]
                for key in ('journal_mode','synchronous','wal_autocheckpoint','page_size')}
            native=module._load_native_time_validator(db)
            result['timestamp_engine']='native_strict_v1' if native else 'portable_merge'
            if args.require_native and not native:raise RuntimeError('reviewed native timestamp artifact required')
            db.execute('CREATE INDEX IF NOT EXISTS stream_events_archive_cursor ON stream_events(received_at,source,event_id)')
            now=datetime.now(timezone.utc);old=now-timedelta(days=3);recent=now-timedelta(hours=47)
            raw={'id':'fixture','slug':'fixture','status':'MARKET_STATUS_OPEN',
                 'assetPriceTerms':{'asset':{'symbol':'btc'},'horizon':'15m',
                 'marketType':'ASSET_PRICE_MARKET_TYPE_UP_DOWN',
                 'windowStart':(old-timedelta(minutes=15)).isoformat(),'windowEnd':old.isoformat(),
                 'priceToBeat':{'value':'100'}}}
            # Multiple market/kind groups prevent the observation covering index
            # from accidentally supplying global timestamp order in this fixture.
            for market in range(97):
                raw['id']=raw['slug']='fixture-'+str(market)
                collector.save_market(db,collector.normalize(raw),old.isoformat())
            db.execute('DELETE FROM observations');db.commit()
            counts={'observations':args.observations,'stream_events':args.stream_events}
            eligible={'observations':min(40031,args.observations-1),'stream_events':min(196509,args.stream_events-1)}
            evidence=[]
            for dataset,count in counts.items():
                checkpoint('generate_'+dataset)
                old_count=eligible[dataset]
                def received(i):
                    base,rank,count,span=(old,i-1,old_count,12*3600) if i<=old_count else (recent,i-old_count-1,counts[dataset]-old_count,46*3600)
                    return (base+timedelta(microseconds=rank*span*1000000//count)).isoformat(timespec='microseconds')
                for lo in range(1,count+1,20000):
                    rows=[]
                    for i in range(lo,min(lo+20000,count+1)):
                        at=received(i)
                        rows.append((i,'fixture-'+str(i%97),at,None,('book','bbo','stream_book')[i%3],'{}') if dataset=='observations' else
                                    ('coinbase',str(args.trade_id_base+i),at,at,'100.000001','0.10','buy','{}'))
                    marks='(?,?,?,?,?,?)' if dataset=='observations' else '(?,?,?,?,?,?,?,?)'
                    db.executemany('INSERT INTO '+dataset+' VALUES'+marks,rows);db.commit()
                    result['generated_rows_in_stage']=min(lo+19999,count)
                    checkpoint('generate_'+dataset)
                evidence.append(manifest(dataset,1,old_count,
                    received(1),received(old_count),args.trade_id_base))
            db.execute('CREATE TABLE prediction_context_links(outcome_observation_id INTEGER REFERENCES observations(id))')
            db.execute('INSERT INTO prediction_context_links VALUES(1)');db.commit()
            result.update(rows=counts,eligible_before_protection=eligible,
                          deployed_save_sha256=hashlib.sha256((args.deployed_app/'streaming.py').read_bytes()).hexdigest())
            if args.require_indexed:
                checkpoint('build_timestamp_guards')
                built=time.monotonic();db.execute('BEGIN IMMEDIATE')
                module.timestamp_guards.create_indexes(db);db.commit()
                result['guard_build_seconds']=time.monotonic()-built
                if any(module.timestamp_guards.invalid_exists(db,t) for t in module.SPECS):
                    raise RuntimeError('invalid fixture timestamp in indexed guard')
                result['timestamp_engine']='indexed_invalid_v1'
            result['sqlite_settings_before_experiment']=dict(result['sqlite_settings'])
            configure_fixture_checkpoint(db,path,getattr(args,'fixture_autocheckpoint_pages',0))
            result['sqlite_settings']={key:db.execute('PRAGMA '+key).fetchone()[0]
                for key in ('journal_mode','synchronous','wal_autocheckpoint','page_size')}
            config=module.RetentionConfig(True,48,getattr(args,'batch_size',1000))
            checkpoint('plan_retention')
            plan=module.plan_retention(db,evidence,config,now)
            expected={'observations':eligible['observations']-1,'stream_events':eligible['stream_events']}
            if any(plan['datasets'][key]['eligible_rows']!=value for key,value in expected.items()):
                raise RuntimeError('generated eligibility differs from required full workload')
            result['expected_eligible_rows']=expected
            result['preparation_seconds']=time.monotonic()-start
            worker=subprocess.Popen([sys.executable,__file__,'--collector',str(path),
                                     '--collector-report',str(report),'--deployed-app',str(args.deployed_app)],
                                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            wait_until=time.monotonic()+5
            while not ready.exists():
                if worker.poll() is not None or time.monotonic()>=wait_until:raise RuntimeError('collector fixture startup')
                time.sleep(.01)
            try:
                checkpoint('retention_apply')
                result['apply']=module.apply_retention(db,plan,config,confirm=True,progress=checkpoint)
                result['max_write_lock_seconds']=max(d['max_write_lock_seconds'] for d in result['apply']['datasets'].values())
            except module.RetentionBudgetError as error:
                result.update(error_type=type(error).__name__,phase=error.phase,
                              lock_seconds=error.seconds,committed_rows=error.committed_rows,
                              phase_seconds=error.phase_seconds)
                raise
            if any(result['apply']['datasets'][key]['deleted_rows']!=value for key,value in expected.items()):
                raise RuntimeError('incomplete generated retention workload')
            if db.execute('SELECT 1 FROM observations WHERE id=1').fetchone() is None:raise RuntimeError('protected reference lost')
            if db.execute('PRAGMA foreign_key_check').fetchone() is not None:raise RuntimeError('fixture foreign key violation')
            result['status']='PASS'
        except BaseException as error:
            result.update(status='STOP',error_type=type(error).__name__)
            if hasattr(error,'retention_progress'):result['partial_apply']=error.retention_progress
            if hasattr(error,'retention_failed_operation'):
                result['failed_operation']=error.retention_failed_operation
                result['failed_write_seconds']=error.retention_failed_write_seconds
        finally:
            result['cleanup_pending']=True
            write_progress_report(args.trial_report,result,failure,start)
            signal.signal(signal.SIGUSR1,signal.SIG_IGN);signal.alarm(0)
            monitor_stop.set();watcher.join(3)
            stop.touch()
            if worker is not None:
                try:worker.wait(timeout=5)
                except subprocess.TimeoutExpired:worker.kill();worker.wait();result['status']='STOP';result['actor_cleanup']='killed_fixture_actor'
            if report.exists():
                result['collector']=json.loads(report.read_text())
                actor_result=result['collector']
                if (actor_result['errors'] or actor_result['save_max_seconds']>=1 or actor_result['heartbeat_max_seconds']>=1
                        or actor_result['saves']==0 or actor_result['saves']!=actor_result['ram_updates']):result['status']='STOP'
            elif worker is not None:result['status']='STOP';result['actor_report']='missing'
            # A last-connection automatic close/checkpoint can itself be slow.
            # Save a provisional STOP before it; the parent enforces the TOTAL
            # deadline and reaps the whole fixture process group if needed.
            if args.trial_report:
                pending=dict(result);pending['status']='STOP';pending['cleanup_pending']=True
                pending['production_guard_errors']=list(failure)
                args.trial_report.write_text(json.dumps(pending))
            if db is not None:db.close()
            result.pop('cleanup_pending',None)
            result['production_guard_errors']=failure
            result['elapsed_seconds']=time.monotonic()-start
            result['max_rss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            if failure or result['elapsed_seconds']>180:result['status']='STOP'
            for sig,handler in previous.items():signal.signal(sig,handler)
    return result


class FixtureReapError(RuntimeError):
    def __init__(self,pid):self.pid=pid


def bounded_process(command, work_seconds=177):
    """Only a newly created fixture process group is signalled and reaped."""
    child=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           text=True,start_new_session=True)
    timed_out=False
    try:
        stdout,stderr=child.communicate(timeout=work_seconds)
    except subprocess.TimeoutExpired:
        timed_out=True
        try:os.killpg(child.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        try:stdout,stderr=child.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            try:stdout,stderr=child.communicate(timeout=1)
            except subprocess.TimeoutExpired:raise FixtureReapError(child.pid) from None
    return child.returncode,stdout,stderr,timed_out


def supervised_trial(args,number):
    started=time.monotonic()
    folder=Path(tempfile.mkdtemp(prefix='bounded-retention-',dir=args.work_dir))
    report=folder/'trial.json';reaped=True
    try:
        command=[sys.executable,__file__,'--candidate',str(args.candidate),
                 '--deployed-app',str(args.deployed_app),'--work-dir',str(folder),
                 '--observations',str(args.observations),'--stream-events',str(args.stream_events),
                 '--trial-child',str(number),'--trial-report',str(report),
                 '--trade-id-base',str(getattr(args,'trade_id_base',0)),
                 '--batch-size',str(getattr(args,'batch_size',1000)),
                 '--fixture-autocheckpoint-pages',str(getattr(args,'fixture_autocheckpoint_pages',0))]
        if args.expected_save_sha256:command+=['--expected-save-sha256',args.expected_save_sha256]
        if args.check_production:command+=['--check-production']
        if args.require_native:command+=['--require-native']
        if args.require_indexed:command+=['--require-indexed']
        try:
            code,stdout,stderr,timed_out=bounded_process(command)
            try:result=json.loads(report.read_text())
            except (OSError,ValueError):
                result={'trial':number,'status':'STOP','error_type':'MissingOrIncompleteFixtureReport'}
            if code or timed_out:
                result['status']='STOP';result['supervisor_timeout']=timed_out
                result['fixture_exit_code']=code
        except FixtureReapError as error:
            reaped=False
            result={'trial':number,'status':'STOP','error_type':'FixtureReapError',
                    'fixture_pid':error.pid,'retained_generated_container':str(folder)}
    finally:
        # Never unlink an active fixture underneath an unreaped process.
        if reaped:shutil.rmtree(folder)
    result['supervised_elapsed_seconds']=time.monotonic()-started
    if result['supervised_elapsed_seconds']>180:result['status']='STOP'
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path,default=Path(__file__).parent/'app/retention.py')
    parser.add_argument('--deployed-app',type=Path,default=Path('/opt/tradebot/backend/app'))
    parser.add_argument('--work-dir',type=Path)
    parser.add_argument('--observations',type=int,default=578343)
    parser.add_argument('--stream-events',type=int,default=1684881)
    parser.add_argument('--trade-id-base',type=int,choices=(0,1000000000),default=0,
                        help='Synthetic string IDs: adversarial variable widths (0) or observed ten-digit Coinbase shape')
    parser.add_argument('--check-production',action='store_true')
    parser.add_argument('--require-native',action='store_true',help='Fail closed unless reviewed native artifact is loaded')
    parser.add_argument('--require-indexed',action='store_true',help='Qualify explicit invalid-timestamp guard indexes, without native artifact')
    parser.add_argument('--trials',type=int,choices=(1,2,3),default=3,
                        help='Bound a diagnostic run; qualification still requires three full passes')
    parser.add_argument('--batch-size',type=int,choices=(250,500,1000),default=1000,
                        help='Generated trial batch ceiling; never raises the qualified1000-row maximum')
    parser.add_argument('--fixture-autocheckpoint-pages',type=int,choices=(0,256),default=0,
                        help='Explicit generated-only256-page automatic threshold experiment;0 preserves defaults')
    parser.add_argument('--expected-save-sha256')
    parser.add_argument('--trial-child',type=int,choices=(1,2,3),help=argparse.SUPPRESS)
    parser.add_argument('--trial-report',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--collector',type=Path)
    parser.add_argument('--collector-report',type=Path)
    args=parser.parse_args()
    if sys.platform!='linux':parser.error('qualification requires Linux; use unit tests on other hosts')
    if args.collector:return actor(args)
    if args.require_native and args.require_indexed:parser.error('choose one qualification strategy')
    if args.check_production and (args.deployed_app.resolve()!=Path('/opt/tradebot/backend/app')
                                  or not re.fullmatch('[0-9a-f]{64}',args.expected_save_sha256 or '')):
        parser.error('production guard requires actual deployed app and expected helper SHA256')
    if min(args.observations,args.stream_events)<100 or max(args.observations,args.stream_events)>10000000:
        parser.error('generated row counts must be100..10000000')
    resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))
    if args.trial_child:
        if args.trial_report is None:parser.error('trial child requires report path')
        result=trial(args,args.trial_child)
        args.trial_report.write_text(json.dumps(result))
        return
    for number in range(1,args.trials+1):
        result=supervised_trial(args,number);print(json.dumps(result),flush=True)
        if result['status']!='PASS':raise SystemExit(1)


if __name__=='__main__':main()
