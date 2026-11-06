"""Reviewed, one-use full-verification route. No production authority ships in code.

Root must install an exact-release review document AFTER procedure approval.
Legacy deployment retains its complete inline checks. This module never copies a
DB, stops writers, checkpoints WAL, migrates schema, or weakens durability.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.request

AUTH = Path('/run/tradebot-release-review.json')
EVIDENCE = Path('/run/tradebot-release-verification.json')
POLICY = {'work_seconds':1800, 'reap_seconds':10, 'recovery_seconds':180,
          'freshness_seconds':300, 'deploy_seconds':600,
          'storage_ceiling_mb':5120,'storage_reserve_mb':512}
APP_FILES = {'backend/app/api.py','backend/app/streaming.py','backend/app/live_health.py'}
OLD = 'd56b4a73ad6f1a10ba2bac928087cd5d85c6a42a'
APP_BLOBS = {'backend/app/api.py':'ab3a2d3747d3551b18d3f21db813e025b2221393',
 'backend/app/streaming.py':'7b38f893e25e2e0b3421b0c083a112dd55edba02',
 'backend/app/live_health.py':'1d1c173ebd3eef082c22676ce7b936cdbcb70ed6'}
FEATURE_REASONS = {'feature_snapshot_missing','feature_as_of_stale'}


class Stop(RuntimeError):pass


class NotReady(Stop):pass


def require(condition, reason):
    if not condition:raise Stop(reason)


def owned_process(command, timeout, cwd=None):
    """A timed-out child must be reaped within a separate bounded grace."""
    child=subprocess.Popen(command,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        text=True,start_new_session=True)
    try:
        stdout,stderr=child.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:os.killpg(child.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        try:child.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            try:child.communicate(timeout=POLICY['reap_seconds']-2)
            except subprocess.TimeoutExpired:
                raise Stop('owned child unreaped; manual action required: '+str(child.pid)) from None
        raise subprocess.TimeoutExpired(command,timeout) from None
    return subprocess.CompletedProcess(command,child.returncode,stdout,stderr)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def private_read(path):
    # O_NOFOLLOW + fstat avoids a symlink replacement race during open.
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        st=os.fstat(stream.fileno())
        require(st.st_uid==0 and st.st_mode & 0o777==0o600,'unsafe review/evidence permissions')
        return json.load(stream)


def immutable_write(path, value):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as stream:
        json.dump(value,stream);stream.write('\n');stream.flush();os.fsync(stream.fileno())


def review(doc, revision, old, helper_hash, now):
    require(old==OLD,'review route supports only the existing rollout baseline')
    require(doc.get('approval_confirmed') is True,'production procedure not approved')
    require(doc.get('release')==revision and doc.get('old')==old,'review revision mismatch')
    require(re.fullmatch('[0-9a-f]{40}',revision) is not None,'full release SHA required')
    require(doc.get('policy')==POLICY,'unreviewed policy values')
    require(doc.get('helper_sha256')==helper_hash and doc.get('verifier_sha256')==sha(__file__),'review helper mismatch')
    require(doc.get('smoke_sha256')==sha(Path(__file__).with_name('smoke.py')),'review smoke mismatch')
    require(isinstance(doc.get('review_id'),str) and bool(doc['review_id'].strip()),'review acknowledgment missing')
    for name in ('application_ci_run','controls_ci_run'):
        require(type(doc.get(name)) is int and doc[name]>0,'exact CI acknowledgment missing')
    require(type(doc.get('expires_at')) in (int,float) and 0<doc['expires_at']-now<=3600,'review expired or too long')


def _identity(path):
    path=Path(path)
    require(not path.is_symlink(),'database symlink forbidden')
    before=path.stat()
    db=sqlite3.connect(path.resolve(strict=True).as_uri()+'?mode=ro',uri=True,timeout=.1)
    try:
        db.execute('PRAGMA query_only=ON');deadline=time.monotonic()+2
        db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
        version=db.execute('PRAGMA schema_version').fetchone()[0]
        catalog=db.execute('SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name').fetchall()
        require(db.execute('PRAGMA journal_mode').fetchone()[0]=='wal','expected WAL database')
    finally:db.close()
    after=path.stat()
    require((before.st_dev,before.st_ino)==(after.st_dev,after.st_ino),'database replaced during identity read')
    return {'path':str(path.resolve()),'device':after.st_dev,'inode':after.st_ino,
            'schema_version':version,'schema_sha256':hashlib.sha256(json.dumps(catalog).encode()).hexdigest()}


def identity(path):
    result=owned_process([sys.executable,__file__,'--identity',str(path)],timeout=3)
    require(result.returncode==0,'database identity read failed')
    return json.loads(result.stdout)


def persistence(path, market):
    db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=.1)
    try:
        db.execute('PRAGMA query_only=ON');deadline=time.monotonic()+1
        db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
        stream=db.execute("SELECT received_at FROM (SELECT rowid,source,received_at FROM stream_events ORDER BY rowid DESC LIMIT 256) WHERE source='coinbase' ORDER BY rowid DESC LIMIT 1").fetchone()
        book=db.execute("SELECT received_at FROM (SELECT rowid,market_id,kind,received_at FROM observations ORDER BY rowid DESC LIMIT 128) WHERE market_id=? AND kind='stream_book' ORDER BY rowid DESC LIMIT 1",(market,)).fetchone()
        require(stream is not None and book is not None,'recent persisted collection missing')
        return {'coinbase_persisted':stream[0],'polymarket_persisted':book[0]}
    finally:db.close()


def write_verification_progress(path, value):
    """Bounded private atomic diagnostics; never authority or integrity proof."""
    if path is None:return
    path=Path(path);parent=path.parent;st=parent.stat()
    require(not parent.is_symlink() and st.st_uid==os.geteuid() and not st.st_mode&0o077,'unsafe progress directory')
    data=json.dumps(value,separators=(',',':')).encode()
    require(len(data)<=8192,'verification diagnostic too large')
    if path.exists():
        st=path.lstat();require(not path.is_symlink() and st.st_uid==os.geteuid() and st.st_mode&0o777==0o600,'unsafe progress target')
    pending=path.with_name(path.name+'.pending-'+str(os.getpid()))
    fd=os.open(pending,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(pending,path)
    finally:
        if pending.exists():pending.unlink()


def read_verification_progress(path,pid):
    """Missing/truncated/stale diagnostics never count as verification success."""
    try:
        path=Path(path);st=path.lstat()
        require(not path.is_symlink() and st.st_uid==os.geteuid() and st.st_mode&0o777==0o600 and st.st_size<=8192,'unsafe partial report')
        value=json.loads(path.read_text())
        require(value.get('format')==1 and value.get('pid')==pid,'stale partial report')
        require(value.get('active_check') in (None,'identity','quick_check','foreign_key_check','final_identity'),'invalid partial phase')
        checks=value.get('checks');require(isinstance(checks,list) and len(checks)<=2 and all(isinstance(c,dict) for c in checks),'invalid partial checks')
        require([c.get('check') for c in checks] in ([],['quick_check'],['quick_check','foreign_key_check']),'invalid partial order')
        require(all(c.get('status')=='PASS' and type(c.get('seconds')) in (int,float) for c in checks),'invalid partial result')
        require(value.get('status') in ('RUNNING','STOP','PASS'),'invalid diagnostic state')
        require(type(value.get('elapsed_seconds')) in (int,float),'invalid diagnostic time')
        # Return only bounded metadata; arbitrary JSON fields are never logged.
        out={k:value[k] for k in ('format','pid','status','active_check','elapsed_seconds') if k in value}
        out['checks']=[{k:c[k] for k in ('check','status','seconds')} for c in checks]
        table=value.get('active_table')
        if table is None or (isinstance(table,str) and re.fullmatch('[A-Za-z_][A-Za-z_0-9]{0,127}',table)):out['active_table']=table
        count=value.get('foreign_key_tables_completed')
        if type(count) is int and 0<=count<=256:out['foreign_key_tables_completed']=count
        error=value.get('error_type')
        if isinstance(error,str) and re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,63}',error):out['error_type']=error
        return out
    except (OSError,ValueError,TypeError,KeyError,Stop):return {'status':'UNAVAILABLE','active_check':None,'checks':[]}


def check_database(path, seconds, progress=None):
    """Complete checks in one read transaction, with durable phase boundaries."""
    started=time.monotonic();path=Path(path);checks=[];db=None
    state={'format':1,'pid':os.getpid(),'status':'RUNNING','active_check':'identity','checks':checks,
           'started_at':datetime.now(timezone.utc).isoformat()}
    def publish():
        state['elapsed_seconds']=time.monotonic()-started
        write_verification_progress(progress,state)
    try:
        publish();require(seconds>0,'verification deadline');before=_identity(path)
        db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=.1)
        db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        require(db.execute('PRAGMA schema_version').fetchone()[0]==before['schema_version'],'schema changed before checks')
        db.set_progress_handler(lambda:int(time.monotonic()-started>=seconds),1000)
        for name in ('quick_check','foreign_key_check'):
            state['active_check']=name;publish()
            require(time.monotonic()-started<seconds,'verification deadline')
            at=time.monotonic()
            if name=='quick_check':
                cursor=db.execute('PRAGMA quick_check');first=cursor.fetchone()
                require(first==('ok',) and cursor.fetchone() is None,'quick_check failed')
            else:
                # Same complete FK scope, with a durable boundary per declaring
                # table. Never substitute sampled rows or table-local integrity.
                tables=db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name LIMIT 257").fetchall()
                require(len(tables)<=256,'foreign key schema bound')
                state['foreign_key_tables_completed']=0
                for (table,) in tables:
                    require(re.fullmatch('[A-Za-z_][A-Za-z_0-9]{0,127}',table),'unsupported table identity')
                    if not db.execute('PRAGMA foreign_key_list("'+table+'")').fetchone():continue
                    state['active_table']=table;publish()
                    require(time.monotonic()-started<seconds,'verification deadline')
                    require(db.execute('PRAGMA foreign_key_check("'+table+'")').fetchone() is None,'foreign_key_check failed')
                    state['foreign_key_tables_completed']+=1;publish()
                state['active_table']=None
            checks.append({'check':name,'status':'PASS','seconds':time.monotonic()-at})
            state['active_check']=None;publish()
        require(time.monotonic()-started<seconds,'verification deadline')
        db.rollback() # End read snapshot only, never restore database contents.
        db.close();db=None
        state['active_check']='final_identity';publish()
        require(_identity(path)==before,'database/schema identity changed during verification')
        state.update(status='PASS',active_check=None);publish()
        return {'status':'PASS','identity':before,'checks':checks,'seconds':time.monotonic()-started}
    except BaseException as error:
        error.verification_phase=state['active_check'];error.completed_checks=list(checks)
        state.update(status='STOP',error_type=type(error).__name__);publish()
        raise
    finally:
        if db is not None:db.close()


def validate_evidence(evidence, revision, old, helper_hash, current_identity, now):
    doc=evidence['review']
    # Policy/CI/hash binding still applies after verification; original review expiry
    # is NOT renewed. Completion TTL and original authorization both must hold.
    review(doc,revision,old,helper_hash,now)
    require(evidence.get('status')=='PASS','verification incomplete')
    require(evidence.get('identity')==current_identity,'verification database identity mismatch')
    checks=evidence.get('checks',[])
    require([c.get('check') for c in checks]==['quick_check','foreign_key_check'] and
            all(c.get('status')=='PASS' for c in checks),'full verification evidence missing')
    age=now-evidence.get('finished_at',0)
    require(0<=age<=POLICY['freshness_seconds'],'verification expired or future')


@contextmanager
def commands(cd, seconds):
    """Bound subprocesses and termination; parent lock covers both routes."""
    original=cd.run;start=time.monotonic();state={'recovery':False,'recovery_at':None}
    def recovery():
        if not state['recovery']:
            state.update(recovery=True,recovery_at=time.monotonic())
            for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):signal.signal(sig,signal.SIG_IGN)
    def remaining():
        end=(state['recovery_at']+POLICY['recovery_seconds']) if state['recovery'] else start+seconds
        value=end-time.monotonic();require(value>0,'release phase deadline');return value
    def bounded(*args,**kwargs):
        cap=kwargs.pop('timeout',None)
        if cap is None:cap=90 if args[:2]==('systemctl','restart') else 30
        kwargs['timeout']=min(cap,remaining())
        return getattr(cd,'reviewed_run',original)(*args,**kwargs)
    previous={}
    def interrupted(signum, frame):raise Stop('release interrupted')
    cd.run=bounded
    try:
        for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):previous[sig]=signal.signal(sig,interrupted)
        yield recovery,remaining
    finally:
        cd.run=original
        for sig,handler in previous.items():signal.signal(sig,handler)


def source(cd, revision, bundle):
    old=cd.git('rev-parse','HEAD')
    require(cd.git('bundle','list-heads',str(bundle)).splitlines()==[revision+' '+cd.BRANCH],'wrong bundle ref')
    cd.git('bundle','verify',str(bundle));cd.git('fetch',str(bundle),cd.BRANCH)
    require(cd.git('rev-parse','FETCH_HEAD')==revision,'bundle revision mismatch')
    cd.git('merge-base','--is-ancestor',old,revision)
    paths=cd.git('diff','--name-only',old,revision).splitlines()
    require({p for p in paths if p.startswith('backend/app/')}==APP_FILES,'not the reviewed rollover application scope')
    require(all(p.startswith(('backend/app/','backend/tests/','docs/PLAN/','deploy/lightsail/','.github/workflows/')) for p in paths),'unexpected release path')
    guarded={'backend/requirements.txt','deploy/lightsail/preflight.py','deploy/lightsail/install-services.sh'}
    require(not any(p in guarded or p.endswith(('.service','.timer')) for p in paths),'provisioning change forbidden')
    require(old==OLD,'unexpected runtime revision')
    for path,blob in APP_BLOBS.items():
        require(cd.git('rev-parse',revision+':'+path)==blob,'application differs from qualified rollover candidate')
    return old


def stamp(value):
    require(isinstance(value,str),'source timestamp missing')
    try:
        at=datetime.fromisoformat(value.replace('Z','+00:00'))
        require(at.tzinfo is not None,'naive source timestamp')
        return at
    except (ValueError,TypeError):raise Stop('invalid source timestamp') from None


def collection_state(value, now=None, allow_features=False):
    now=now or datetime.now(timezone.utc)
    market=value.get('market') or {};require(market.get('id') and market.get('slug'),'market identity missing')
    require(stamp(market.get('start'))<=now<stamp(market.get('end')),'market not current')
    quote=value.get('polymarket') or {}
    require(quote.get('slug')==market['slug'],'quote identity mismatch')
    for name in ('coinbase','polymarket'):
        age=(now-stamp((value.get(name) or {}).get('source_time'))).total_seconds()
        require(-5<=age<=30,'source not current: '+name)
    return {name:(value.get(name) or {}).get('received_at') for name in ('coinbase','polymarket')}


def probe(cd, before=None):
    # Network calls are separately timeout-bounded; no source/private payload output.
    def get(route):return fetch(route)
    health=get('/health');require(health.get('collector',{}).get('running') is True,'collector not running')
    require(health['collector'].get('error') is None,'collector error')
    state=get('/state/current');progress=collection_state(state)
    for name in ('coinbase_stream','polymarket_stream'):
        require(health.get('feeds',{}).get(name,{}).get('status')=='live','feed not live')
    persisted=owned_process([sys.executable,__file__,'--persistence',str(cd.ROOT/'data/btc_intelligence.db'),
        '--market',str(state['market']['id'])],timeout=2)
    require(persisted.returncode==0,'persistence probe failed')
    progress.update(json.loads(persisted.stdout))
    now=datetime.now(timezone.utc)
    require(all(-5<=(now-stamp(v)).total_seconds()<=30 for v in progress.values()),'receipt/persistence stale')
    if before:
        require(all(progress[k]!=before[k] for k in progress),'feed receipt progress stopped')
    db=cd.ROOT/'data/btc_intelligence.db';physical=sum(p.stat().st_size for p in (db,Path(str(db)+'-wal')) if p.exists())
    require(physical < (POLICY['storage_ceiling_mb']-POLICY['storage_reserve_mb'])*1024**2,'storage reserve exhausted')
    return progress,health


def reap(child, seconds):
    child.terminate()
    try:child.wait(timeout=min(2,seconds))
    except subprocess.TimeoutExpired:
        child.kill()
        try:child.wait(timeout=max(.1,seconds-2))
        except subprocess.TimeoutExpired:raise Stop('verification child unreaped; manual action required') from None


def verify(cd, revision, bundle):
    require(os.geteuid()==0,'root review authority required')
    require(not EVIDENCE.exists(),'prior verification evidence must be reviewed, not overwritten')
    with commands(cd,POLICY['work_seconds']) as (recover,remaining):
        old=source(cd,revision,bundle);doc=private_read(AUTH)
        review(doc,revision,old,sha(cd.__file__),time.time())
        before_services=cd.runtime_preflight();protected=cd.protected()
        before_identity=identity(cd.ROOT/'data/btc_intelligence.db')
        before,_=probe(cd)
        # Consume the reviewed scan authority before launching a heavy child.
        claimed=AUTH.with_suffix('.claimed.json');require(not claimed.exists(),'review already claimed')
        AUTH.rename(claimed)
        child=None
        try:
            child=subprocess.Popen([sys.executable,__file__,'--child',str(cd.ROOT/'data/btc_intelligence.db'),
                '--seconds',str(max(.1,remaining()-10))],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            while True:
                try:
                    stdout,stderr=child.communicate(timeout=min(5,remaining()));break
                except subprocess.TimeoutExpired:
                    current,_=probe(cd,before);before=current
            result=json.loads(stdout)
            if child.returncode!=0:
                print(json.dumps({'verification':'STOP','phase':result.get('phase'),'checks':result.get('checks',[]),'error_type':result.get('error_type')}),flush=True)
                raise Stop('full verification child failed')
            require(result.get('status')=='PASS' and result['identity']==before_identity,'verification identity/result mismatch')
            require(identity(cd.ROOT/'data/btc_intelligence.db')==before_identity,'identity changed after verification')
            probe(cd);after_services=cd.runtime_preflight()
            require(after_services==before_services,'service identity changed during verification')
            require(cd.protected()==protected,'configuration changed during verification')
            result.update(review=doc,finished_at=time.time(),protected=list(protected),services=after_services)
            remaining()
            validate_evidence(result,revision,old,sha(cd.__file__),before_identity,time.time())
            immutable_write(EVIDENCE,result)
            print(json.dumps({'verification':'PASS','release':revision,'checks':result['checks']}),flush=True)
        finally:
            if child is not None and child.poll() is None:
                recover();reap(child,min(POLICY['reap_seconds'],remaining()))


def reviewed_deploy(cd, revision, bundle):
    require(os.geteuid()==0,'root review authority required')
    with commands(cd,POLICY['deploy_seconds']) as (recover,remaining):
        old=source(cd,revision,bundle);evidence=private_read(EVIDENCE)
        db=cd.ROOT/'data/btc_intelligence.db'
        validate_evidence(evidence,revision,old,sha(cd.__file__),identity(db),time.time())
        before=cd.runtime_preflight();protected=cd.protected()
        require(evidence.get('services')==before,'services changed since verification')
        require(evidence.get('protected')==list(protected),'configuration changed since verification')
        probe(cd)
        # Final freshness/identity check immediately before one-use consumption.
        validate_evidence(evidence,revision,old,sha(cd.__file__),identity(db),time.time())
        consumed=EVIDENCE.with_suffix('.consumed.json');require(not consumed.exists(),'verification already consumed')
        EVIDENCE.rename(consumed)
        record=cd.ROOT/'data/deployments'/('reviewed-'+str(time.time_ns())+'.json')
        record.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        result={'old':old,'release':revision,'status':'STOP','review_id':evidence['review']['review_id']}
        changed=False
        try:
            changed=True # A partial checkout is also rolled back.
            cd.git('checkout','--detach',revision)
            cd.run('systemctl','restart','tradebot-api',timeout=90)
            result['api_readiness']=wait_for_api(min(180,remaining()))
            # Keep aggregate feature unavailability visible; never require false ok.
            progress,health=probe(cd)
            reasons=set(health.get('diagnostic_reasons',[]))
            require(health.get('status') in ('ok','degraded') and reasons<=FEATURE_REASONS,'unexpected degraded health')
            require(health.get('status')!='degraded' or bool(reasons),'degraded without reasons')
            smoke=json.loads(cd.run(sys.executable,str(cd.HELPERS/'smoke.py'),
                '--rollover-release','--attempts','1',timeout=min(180,remaining())))
            result['smoke']=smoke
            time.sleep(min(5,remaining()))
            probe(cd,progress);after=cd.runtime_preflight()
            require(cd.git('rev-parse','HEAD')==revision,'checkout did not select release')
            require(after['tradebot-api']['MainPID']!=before['tradebot-api']['MainPID'],'API restart not observed')
            require(all(before[n]['MainPID']==after[n]['MainPID'] and before[n]['NRestarts']==after[n]['NRestarts']
                        for n in before if n!='tradebot-api'),'unrelated service changed')
            require(before['tradebot-api']['NRestarts']==after['tradebot-api']['NRestarts'],'automatic API restart')
            require(cd.protected()==protected,'protected environment changed')
            remaining()
            result.update(status='deployed_pending_acceptance',services_restarted=['tradebot-api'],diagnostic_reasons=sorted(reasons))
        except BaseException as error:
            result['failure_type']=type(error).__name__
            if changed:
                recover()
                try:
                    cd.git('checkout','--detach',old);cd.run('systemctl','restart','tradebot-api',timeout=90)
                    restored=cd.runtime_preflight();require(cd.git('rev-parse','HEAD')==old,'rollback code not restored')
                    require(cd.protected()==protected,'rollback configuration changed')
                    require(all(restored[n]['MainPID']==before[n]['MainPID'] for n in before if n!='tradebot-api'),'rollback changed unrelated service')
                    result['rollback']='code_restored_collection_health_unqualified'
                except BaseException as recovery_error:
                    result.update(rollback='MANUAL_ACTION_REQUIRED',recovery_failure_type=type(recovery_error).__name__)
            raise
        finally:
            immutable_write(record,result)


def wait_for_api(seconds):
    """Startup transport readiness only. Never retry unhealthy source evidence."""
    start=time.monotonic();failures=0
    while time.monotonic()-start<seconds:
        try:
            fetch('/health')
            elapsed=time.monotonic()-start
            require(elapsed<=seconds,'API startup readiness deadline')
            return {'seconds':elapsed,'transport_failures':failures}
        except (NotReady,subprocess.TimeoutExpired):
            failures+=1
            left=seconds-(time.monotonic()-start)
            if left>0:time.sleep(min(1,left))
    raise Stop('API startup readiness deadline')


def fetch(route):
    require(route in ('/health','/state/current','/dashboard','/events'),'unsupported probe route')
    child=owned_process([sys.executable,__file__,'--http',route],timeout=2)
    if child.returncode:
        failure=json.loads(child.stdout)
        if failure.get('error_type') in ('URLError','TimeoutError','ConnectionRefusedError','ConnectionResetError'):
            raise NotReady('API transport not ready')
        raise Stop('API probe failed')
    return json.loads(child.stdout)


def http_child(route):
    with urllib.request.urlopen('http://127.0.0.1:8000'+route,timeout=2) as response:
        if route=='/events':
            require(response.headers.get('Content-Type','').startswith('text/event-stream'),'SSE content type')
            require(response.readline(2*1024*1024).startswith(b'data: '),'SSE data missing')
            return {'status':'PASS'}
        if route=='/dashboard':
            require(b'<html' in response.read(2*1024*1024).lower(),'dashboard unavailable')
            return {'status':'PASS'}
        value=json.load(response)
        if route=='/health':return {k:value.get(k) for k in ('collector','feeds','status','diagnostic_reasons')}
        return {k:value.get(k) for k in ('market','coinbase','polymarket')}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--child',type=Path);parser.add_argument('--seconds',type=float)
    parser.add_argument('--progress',type=Path)
    parser.add_argument('--identity',type=Path);parser.add_argument('--persistence',type=Path);parser.add_argument('--market')
    parser.add_argument('--http',choices=('/health','/state/current','/dashboard','/events'))
    args=parser.parse_args()
    try:
        if args.identity:result=_identity(args.identity)
        elif args.persistence:result=persistence(args.persistence,args.market)
        elif args.http:result=http_child(args.http)
        else:
            require(args.child is not None and args.seconds is not None and 0<args.seconds<=POLICY['work_seconds'],'invalid child request')
            require(sys.platform=='linux','bounded verification child requires Linux')
            resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))
            result=check_database(args.child,args.seconds,args.progress)
        print(json.dumps(result),flush=True)
    except BaseException as error:
        print(json.dumps({'status':'STOP','error_type':type(error).__name__,
            'phase':getattr(error,'verification_phase',None),'checks':getattr(error,'completed_checks',[])}),flush=True);raise SystemExit(1)
