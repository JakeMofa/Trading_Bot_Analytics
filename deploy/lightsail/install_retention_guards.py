"""Explicit timestamp-guard maintenance, never startup or normal CD.

Requires completed full integrity evidence and independent recovered collection.
No deletion, price indexes, database copies, manual WAL operations or flag changes.
"""
from contextlib import closing
from datetime import datetime,timezone
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import sqlite3
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))
import lifecycle_integrity as maintenance

GUARD_SHA='ceecf07d1685290056fc0cff115407eef6b8c6fd6ffea71729450150bc3ad70c'
CAP_BYTES=5120*1024**2


def load_guards(path):
    path=Path(path)
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=GUARD_SHA:
        raise maintenance.IntegrityStop('unqualified timestamp guard module')
    spec=importlib.util.spec_from_file_location('qualified_timestamp_guards',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def install(path,module_path,seconds):
    guards=load_guards(module_path);path=Path(path).resolve(strict=True)
    started=time.monotonic();deadline=started+seconds;next_stat=[0.0];reason=[None]
    def used():return sum(p.stat().st_size for p in (path,Path(str(path)+'-wal')) if p.exists())
    result={'check':'timestamp_guards','status':'STOP','committed':False,'storage_before':used()}
    db=sqlite3.connect(path,timeout=.1)
    try:
        result['preexisting']={t:guards.available(db,t) for t in guards.TABLES}
        def progress():
            now=time.monotonic()
            if now>=deadline:reason[0]='deadline';return 1
            if now>=next_stat[0]:
                next_stat[0]=now+.05
                size=used();result['peak_db_wal_bytes']=max(size,result.get('peak_db_wal_bytes',0))
                if size>=CAP_BYTES-64*1024**2:reason[0]='storage_reserve';return 1
            return 0
        db.set_progress_handler(progress,1000)
        if progress():raise maintenance.IntegrityStop('guard build budget')
        db.execute('BEGIN IMMEDIATE')
        guards.create_indexes(db)
        if any(guards.invalid_exists(db,t) for t in guards.TABLES):
            reason[0]='invalid_current_raw_timestamp';raise maintenance.IntegrityStop('invalid raw timestamps')
        if progress():raise maintenance.IntegrityStop('guard build budget')
        db.commit();result['committed']=True
        if time.monotonic()>=deadline:
            reason[0]='committed_after_deadline';raise maintenance.IntegrityStop('commit deadline')
        result['status']='PASS'
    except BaseException as error:
        result.update(error_type=type(error).__name__,reason=reason[0] or 'sqlite_or_schema_error')
        db.set_progress_handler(None,0)
        if db.in_transaction:db.rollback()
    finally:
        db.set_progress_handler(None,0);db.close()
    # Always record the actual committed schema, including a late commit.
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.1)) as check:
        result['schema_after']={t:{'present':guards.available(check,t)} for t in guards.TABLES}
        for t,v in result['schema_after'].items():
            if v['present']:v['invalid_present']=guards.invalid_exists(check,t)
    result.update(seconds=time.monotonic()-started,storage_after=used())
    return result


class GuardHost(maintenance.LinuxHost):
    def __init__(self,qualification,report,evidence,module):
        super().__init__(qualification,report);self.evidence=evidence;self.module=Path(module)
    def preflight(self,seconds):
        result=super().preflight(seconds)
        evidence=self.evidence;audit=evidence['integrity'];recovery=evidence['independent_recovery']
        if (audit.get('integrity_passed') is not True or len(audit.get('checks',[]))!=2
            or {v['check'] for v in audit['checks']}!={'quick_check','foreign_key_check'}
            or any(v['status']!='PASS' for v in audit['checks']) or recovery.get('status')!='PASS'):
            raise maintenance.IntegrityStop('full integrity/recovery evidence required')
        if audit.get('failure_type') or audit.get('recovery_start_failures') or audit.get('manual_recovery_required'):
            raise maintenance.IntegrityStop('unresolved maintenance failure')
        if audit.get('recovery_failure_type') not in (None,'KeyError'):
            raise maintenance.IntegrityStop('unresolved recovery failure')
        # The original KeyError attempt remains failed; independent recovery
        # confirms the live prerequisite without repeating successful scans.
        if evidence.get('integrity_helper_commit')!='7e5e7d2bd01626dc20a8d840eeaa59fc9cf4fc39' or evidence.get('integrity_ci_run')!=41284629743:
            raise maintenance.IntegrityStop('unexpected integrity evidence source')
        load_guards(self.module)
        return result
    def check(self,operation,seconds):
        if operation!='timestamp_guards' or seconds<=2:raise maintenance.IntegrityStop('unsupported guard operation/budget')
        args=['sudo','-u','tradebot',str(self.ROOT/'.venv/bin/python'),'-B',str(Path(__file__).resolve()),
              '--build-guards','--module',str(self.module),'--database',str(self.ROOT/'data/btc_intelligence.db'),
              '--seconds',str(seconds-2)]
        code,out,err,timed_out=self.bounded_process(args,seconds-2)
        try:result=json.loads(out)
        except ValueError:result={'status':'STOP','reason':'missing_child_report','timed_out':timed_out}
        if code or timed_out or result.get('status')!='PASS':
            error=maintenance.IntegrityStop('timestamp guard installation stopped');error.operation_result=result;raise error
        return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true');parser.add_argument('--build-guards',action='store_true')
    parser.add_argument('--qualification',type=Path);parser.add_argument('--evidence',type=Path)
    parser.add_argument('--report',type=Path);parser.add_argument('--module',type=Path)
    parser.add_argument('--database',type=Path);parser.add_argument('--seconds',type=float,default=1800)
    args=parser.parse_args()
    if args.build_guards:
        if args.database is None or args.module is None or not 0<args.seconds<=1800:parser.error('bounded explicit guard build required')
        resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))
        result=install(args.database,args.module,args.seconds);print(json.dumps(result),flush=True)
        raise SystemExit(0 if result['status']=='PASS' else 1)
    if not args.execute:
        print(json.dumps({'mode':'plan_only','operation':'explicit_timestamp_guards','price_indexes':False,'deletion':False}));return
    if os.geteuid()!=0 or not all((args.qualification,args.evidence,args.report,args.module)):parser.error('trusted explicit operator inputs required')
    host=GuardHost(json.loads(args.qualification.read_text()),args.report,json.loads(args.evidence.read_text()),args.module)
    import signal
    def interrupted(signum,frame):raise TimeoutError('operator interrupted')
    previous={sig:signal.signal(sig,interrupted) for sig in (signal.SIGTERM,signal.SIGINT)}
    try:result=maintenance.run_gate(host,kind='timestamp_guards')
    finally:
        for sig,handler in previous.items():signal.signal(sig,handler)
    raise SystemExit(0 if result['status']=='PASS' else 1)


if __name__=='__main__':main()
