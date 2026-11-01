"""Explicit supervised read-only integrity gate; never called by startup/CD.

Default CLI is plan-only. Execute only after exact-commit CI and retention
qualification are independently verified by the trusted operator. No copies,
manual WAL operations, configuration writes, checkout or database restoration.
"""
from contextlib import closing
from datetime import datetime, timezone
import argparse
import json
import hashlib
import os
import shutil
import subprocess
import signal
from pathlib import Path
import sqlite3
import time

WRITERS=('tradebot-api','tradebot-ensemble','tradebot-lifecycle')
WORK_SECONDS=1800
RECOVERY_SECONDS=180


class IntegrityStop(RuntimeError):pass


def check_database(path,check,seconds):
    if check not in ('quick_check','foreign_key_check'):raise IntegrityStop('unsupported integrity check')
    path=Path(path).resolve(strict=True)
    started=time.monotonic()
    db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.1)
    try:
        db.execute('PRAGMA query_only=ON')
        db.set_progress_handler(lambda:int(time.monotonic()-started>=seconds),1000)
        cursor=db.execute('PRAGMA '+check)
        first=cursor.fetchone()
        passed=(first==('ok',) and cursor.fetchone() is None) if check=='quick_check' else first is None
        if not passed:raise IntegrityStop('database integrity check failed')
        return {'check':check,'status':'PASS','seconds':time.monotonic()-started}
    finally:db.close()


def run_gate(host,clock=time.monotonic):
    """Host performs bounded effects; any audit failure stays failed after recovery."""
    started=clock();report={'status':'STOP','checks':[], 'stopped_units':[],
                            'started_at':datetime.now(timezone.utc).isoformat()}
    previous=None;paused=False;recovery_deadline=None;pause_started=None
    def remaining(recovery=False):
        limit=WORK_SECONDS+(RECOVERY_SECONDS if recovery else 0)
        end=min(started+limit,recovery_deadline) if recovery and recovery_deadline is not None else started+limit
        value=end-clock()
        if value<=0:raise IntegrityStop('integrity gate deadline')
        return value
    try:
        # Includes clean exact revision, private bind, flags, storage, sole owner,
        # expected source hashes and three completed qualification trials.
        previous=host.preflight(min(30,remaining()))
        if set(previous)!=set(WRITERS) or any(value!='active' for value in previous.values()):
            raise IntegrityStop('expected active writer services')
        for unit in WRITERS:
            # Record intent BEFORE stop: a timed-out command may have stopped it.
            if pause_started is None:
                pause_started=clock();report['collection_pause_requested_at']=datetime.now(timezone.utc).isoformat()
            paused=True;report['stopped_units'].append(unit);host.save(report)
            host.stop(unit,min(30,remaining()))
        host.require_no_database_owners(min(10,remaining()))
        for check in ('quick_check','foreign_key_check'):
            report['checks'].append(host.check(check,remaining()))
            host.save(report)
        report['integrity_passed']=True
    except BaseException as error:
        report['failure_type']=type(error).__name__
    finally:
        if paused:
            recovery_deadline=min(started+WORK_SECONDS+RECOVERY_SECONDS,clock()+RECOVERY_SECONDS)
            failures=[]
            for unit in reversed(report['stopped_units']):
                try:host.start(unit,min(30,remaining(True)))
                except BaseException as error:failures.append({'unit':unit,'error_type':type(error).__name__})
            try:
                report['recovery']=host.verify_recovery(remaining(True))
                report['collection_recovered_at']=datetime.now(timezone.utc).isoformat()
                report['collection_interruption_upper_seconds']=clock()-pause_started
                if report['recovery'].get('status')!='PASS':raise IntegrityStop('collection recovery not verified')
            except BaseException as error:
                report['recovery_failure_type']=type(error).__name__
            if failures:
                report['recovery_start_failures']=failures
                report['recovery_failure_type']='ServiceRecoveryFailed'
        if report.get('integrity_passed') and not report.get('failure_type') and not report.get('recovery_failure_type'):
            report['status']='PASS'
        report['elapsed_seconds']=clock()-started
        host.save(report)
    return report


def bounded_child(command,seconds):
    """Terminate/reap the read-only child group on deadline OR parent signal."""
    child=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           text=True,start_new_session=True)
    try:
        out,err=child.communicate(timeout=seconds)
        return child.returncode,out,err,False
    except BaseException as error:
        try:os.killpg(child.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        try:out,err=child.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            try:out,err=child.communicate(timeout=1)
            except subprocess.TimeoutExpired:raise IntegrityStop('integrity child unreaped; manual recovery required') from None
        if isinstance(error,subprocess.TimeoutExpired):return child.returncode,out,err,True
        raise


class LinuxHost:
    """Pinned operator adapter: credential-free reports, read-only SQLite child."""
    ROOT=Path('/opt/tradebot')
    REVISION='d56b4a73ad6f1a10ba2bac928087cd5d85c6a42a'
    def __init__(self,qualification,report):
        import i7_capacity_bridge
        self.bridge=i7_capacity_bridge.Host()
        self.bounded_process=bounded_child
        self.qualification=qualification;self.report=Path(report)
        self.before=None;self.config=None;self.raw_baseline={}
    class Budget:
        def __init__(self,seconds):self.end=time.monotonic()+seconds
        def seconds(self,cap):
            left=self.end-time.monotonic()
            if left<=0:raise IntegrityStop('operator step deadline')
            return min(cap,left)
    def command(self,args,seconds):
        return subprocess.run(args,cwd=self.ROOT,capture_output=True,text=True,
                              timeout=seconds,check=True).stdout.strip()
    def preflight(self,seconds):
        budget=self.Budget(seconds)
        st=self.report.parent.stat()
        if self.report.parent.is_symlink() or st.st_uid!=0 or st.st_mode&0o022:
            raise IntegrityStop('private root-owned report directory required')
        if self.report.exists() and (self.report.is_symlink() or self.report.stat().st_uid!=0):
            raise IntegrityStop('unsafe report path')
        q=self.qualification
        if q.get('candidate_commit')!='e0d311edcceb4be15811c55f6f8650484d107930' or q.get('ci_run')!=41283537103:
            raise IntegrityStop('unexpected qualification revision/CI')
        if q.get('format')!=1 or len(q.get('trials',[]))!=3:raise IntegrityStop('three full qualification trials required')
        if len({v.get('started_at') for v in q['trials']})!=3:raise IntegrityStop('distinct qualification trials required')
        for trial in q['trials']:
            actor=trial.get('collector',{})
            if (trial.get('status')!='PASS' or trial.get('generated_only') is not True
                or trial.get('trade_id_base')!=1000000000 or trial.get('supervised_elapsed_seconds',181)>180
                or trial.get('max_write_lock_seconds',1)>.5 or trial.get('production_guard_errors')!=[]
                or actor.get('errors')!=[] or actor.get('saves',0)<=0 or actor.get('saves')!=actor.get('ram_updates')
                or actor.get('save_max_seconds',1)>=1 or actor.get('heartbeat_max_seconds',1)>=1):
                raise IntegrityStop('qualification evidence failed')
            for dataset,minimum in (('observations',40030),('stream_events',196509)):
                if trial.get('apply',{}).get('datasets',{}).get(dataset,{}).get('deleted_rows',0)<minimum:
                    raise IntegrityStop('incomplete qualification workload')
        revision=self.command(['sudo','-u','tradebot','git','rev-parse','HEAD'],budget.seconds(5))
        if revision!=self.REVISION or self.command(['sudo','-u','tradebot','git','status','--porcelain','--untracked-files=no'],budget.seconds(5)):
            raise IntegrityStop('unexpected runtime revision/checkout')
        config=self.ROOT/'.env';st=config.stat()
        if config.is_symlink() or st.st_mode&0o777!=0o600:raise IntegrityStop('protected configuration permissions')
        self.config=(hashlib.sha256(config.read_bytes()).hexdigest(),st.st_uid,st.st_gid,st.st_mode)
        db=self.ROOT/'data/btc_intelligence.db'
        if db.is_symlink() or not db.is_file():raise IntegrityStop('unexpected database')
        size=sum(p.stat().st_size for p in (db,Path(str(db)+'-wal')) if p.exists())
        if 5120*1024**2-size<512*1024**2 or shutil.disk_usage(self.ROOT).free<10*1024**3:
            raise IntegrityStop('storage headroom')
        if datetime.now(timezone.utc)>=datetime(2026,11,2,1,56,47,671426,tzinfo=timezone.utc):
            raise IntegrityStop('capacity bridge review overdue')
        self.bridge.config_check(budget,5120);self.bridge.verify(budget,5120)
        self.before=self.bridge.states(budget)
        with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True,timeout=.1)) as connection:
            for dataset in ('observations','stream_events'):
                last=connection.execute('SELECT rowid,received_at FROM '+dataset+' ORDER BY rowid DESC LIMIT 1').fetchone()
                upper=last[0] if last else 0
                self.raw_baseline[dataset]=last
                if any(trial['rows'][dataset]<upper for trial in q['trials']):raise IntegrityStop('unqualified current cardinality')
        actual=hashlib.sha256((self.ROOT/'backend/app/streaming.py').read_bytes()).hexdigest()
        if any(trial.get('deployed_save_sha256')!=actual for trial in q['trials']):raise IntegrityStop('collector source differs')
        health=self.bridge.probe('/health')
        if not health.get('collector_running') or health.get('guard_status')!='watching':raise IntegrityStop('collector not running')
        now=datetime.now(timezone.utc)
        if any(health['feeds'][key]['status']!='live' or not 0<=(now-datetime.fromisoformat(health['feeds'][key]['last_data_at'])).total_seconds()<30 for key in ('coinbase_stream','polymarket_stream')):
            raise IntegrityStop('feed not live before maintenance')
        return {unit:self.before[unit]['ActiveState'] for unit in WRITERS}
    def stop(self,unit,seconds):
        self.command(['systemctl','stop',unit],seconds)
    def start(self,unit,seconds):
        self.command(['systemctl','start',unit],seconds)
    def require_no_database_owners(self,seconds):
        end=time.monotonic()+seconds
        db=self.ROOT/'data/btc_intelligence.db'
        identities=set()
        for path in (db,Path(str(db)+'-wal'),Path(str(db)+'-shm')):
            if path.exists():st=path.stat();identities.add((st.st_dev,st.st_ino))
        for process in Path('/proc').iterdir():
            if time.monotonic()>end:raise IntegrityStop('owner scan deadline')
            if not process.name.isdigit():continue
            try:
                for fd in (process/'fd').iterdir():
                    try:
                        st=fd.stat()
                        if (st.st_dev,st.st_ino) in identities:raise IntegrityStop('unexpected remaining database owner')
                    except FileNotFoundError:pass
            except FileNotFoundError:pass
    def check(self,check,seconds):
        # Reserve two seconds INSIDE the work budget for terminate/kill/reap.
        if seconds<=2:raise IntegrityStop("insufficient child recovery reserve")
        work=seconds-2
        args=['sudo','-u','tradebot',str(self.ROOT/'.venv/bin/python'),'-B',str(Path(__file__).resolve()),
              '--check',check,'--database',str(self.ROOT/'data/btc_intelligence.db'),'--seconds',str(work)]
        code,out,err,timed_out=self.bounded_process(args,work)
        if code or timed_out:raise IntegrityStop('bounded integrity child failed')
        return json.loads(out)
    def verify_recovery(self,seconds):
        budget=self.Budget(seconds);first=None
        while True:
            health=self.bridge.probe('/health');good=health.get('collector_running') and health.get('guard_status')=='watching'
            stamps={key:health.get('feeds',{}).get(key,{}).get('last_data_at') for key in ('coinbase_stream','polymarket_stream')}
            now=datetime.now(timezone.utc)
            try:good=good and all(health['feeds'][key]['status']=='live' and 0<=(now-datetime.fromisoformat(value)).total_seconds()<30 for key,value in stamps.items())
            except (ValueError,TypeError,KeyError):good=False
            if good:
                if first is not None and all(stamps[key]>first[key] for key in stamps):break
                first=stamps
            time.sleep(budget.seconds(5))
        self.bridge.verify(budget,5120)
        after=self.bridge.states(budget)
        if after['tradebot-soak.timer']['MainPID']!=self.before['tradebot-soak.timer']['MainPID']:
            raise IntegrityStop('monitor changed')
        p=self.ROOT/'.env';st=p.stat()
        if self.config!=(hashlib.sha256(p.read_bytes()).hexdigest(),st.st_uid,st.st_gid,st.st_mode):
            raise IntegrityStop('protected configuration changed')
        gaps={}
        db=self.ROOT/'data/btc_intelligence.db'
        with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True,timeout=.1)) as connection:
            for dataset,last in self.raw_baseline.items():
                if last is None:raise IntegrityStop('missing persistence baseline')
                row=connection.execute('SELECT received_at FROM '+dataset+' WHERE rowid>? ORDER BY rowid LIMIT 1',(last[0],)).fetchone()
                if row is None:raise IntegrityStop('persisted collection not advanced')
                gaps[dataset]=(datetime.fromisoformat(row[0])-datetime.fromisoformat(last[1])).total_seconds()
        return {'status':'PASS','feeds_advancing':True,'retention_off':True,'paid_ai_off':True,
                'raw_received_gap_seconds':gaps}
    def save(self,report):
        temporary=self.report.with_suffix('.pending')
        descriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
        os.fchmod(descriptor,0o600)
        with os.fdopen(descriptor,'w') as stream:json.dump(report,stream)
        temporary.replace(self.report)
        print(json.dumps(report),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--preflight-only',action='store_true')
    parser.add_argument('--qualification',type=Path)
    parser.add_argument('--report',type=Path)
    parser.add_argument('--check',choices=('quick_check','foreign_key_check'))
    parser.add_argument('--database',type=Path)
    parser.add_argument('--seconds',type=float,default=WORK_SECONDS)
    args=parser.parse_args()
    if args.execute or args.preflight_only:
        if args.check is not None or args.qualification is None or args.report is None:parser.error('explicit qualification and private report required')
        if os.geteuid()!=0:parser.error('operator root required')
        qualification=json.loads(args.qualification.read_text())
        host=LinuxHost(qualification,args.report)
        if args.preflight_only:
            try:
                host.preflight(30);result={'status':'PASS','mode':'preflight_only','services_untouched':True}
            except BaseException as error:result={'status':'STOP','mode':'preflight_only','failure_type':type(error).__name__}
            host.save(result)
        else:
            def interrupted(signum,frame):raise TimeoutError('operator interrupted')
            previous={sig:signal.signal(sig,interrupted) for sig in (signal.SIGTERM,signal.SIGINT)}
            try:result=run_gate(host)
            finally:
                for sig,handler in previous.items():signal.signal(sig,handler)
        raise SystemExit(0 if result['status']=='PASS' else 1)
    if args.check is None:
        print(json.dumps({'mode':'plan_only','work_seconds':WORK_SECONDS,
                          'recovery_seconds':RECOVERY_SECONDS,'services':WRITERS,
                          'production_operator_host':'explicit execute only'}));return
    if args.database is None or not 0<args.seconds<=WORK_SECONDS:parser.error('bounded explicit database check required')
    print(json.dumps(check_database(args.database,args.check,args.seconds)))


if __name__=='__main__':main()
