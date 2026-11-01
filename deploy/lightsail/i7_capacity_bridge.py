"""One-use 4096 -> 5120 MiB bridge on the existing d56b4a7 runtime.

No application checkout, database connection, retention, copy, snapshot or WAL
operation. Operator verifies exact helper CI before --execute; no GH credentials
are supplied to the VM. Default invocation only prints the plan.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
import urllib.request

ROOT = Path('/opt/tradebot')
REVISION = 'd56b4a73ad6f1a10ba2bac928087cd5d85c6a42a'
UNITS = ('tradebot-api', 'tradebot-ensemble', 'tradebot-lifecycle', 'tradebot-soak.timer')


def replace_guard(text, old, new):
    if len(re.findall(r'(?m)^[ \t]*MAX_LOCAL_STORAGE_MB[ \t]*=', text)) != 1:
        raise ValueError('one explicit guard setting required')
    pattern = re.compile(r'''(?m)^([ \t]*MAX_LOCAL_STORAGE_MB[ \t]*=[ \t]*)(["']?)'''
                         + str(old) + r'''\2([ \t]*)(\r?)$''')
    changed, count = pattern.subn(lambda m: m[1]+m[2]+str(new)+m[2]+m[3]+m[4], text)
    if count != 1:
        raise ValueError('unexpected literal guard setting')
    return changed


class Budget:
    def __init__(self):
        self.started = time.monotonic()
        self.recovery = False

    def seconds(self, cap):
        remaining = (780 if self.recovery else 600) - (time.monotonic()-self.started)
        if remaining <= 0:
            raise TimeoutError('bridge deadline')
        return min(cap, remaining)


def apply_bridge(host, ci_commit, ci_run):
    budget = Budget()
    report = {'revision':REVISION, 'status':'preparing', 'old_guard_mib':4096,
              'guard_mib':5120, 'helper_ci_commit':ci_commit, 'helper_ci_run':ci_run,
              'events':[], 'restart_attempted':False}
    guard_attempted = False
    def phase(name):
        report['events'].append({'phase':name,'at':datetime.now(timezone.utc).isoformat()})
        host.save(report)
    try:
        if not re.fullmatch('[0-9a-f]{40}', ci_commit or '') or ci_run <= 0:
            raise ValueError('trusted exact-helper CI acknowledgment required')
        host.validate(budget)
        phase('preflight_passed')
        guard_attempted = True
        host.set_guard(4096,5120)
        phase('guard_written')
        report['restart_attempted'] = True
        phase('api_restart_requested')
        host.restart(budget)
        phase('api_restart_returned')
        report['observation'] = host.observe(budget)
        host.verify(budget,5120)
        applied = datetime.fromisoformat(next(e['at'] for e in report['events'] if e['phase']=='guard_written'))
        report.update(status='BRIDGE_ACTIVE', applied_at=applied.isoformat(),
                      review_due_at=(applied+timedelta(hours=24)).isoformat(),
                      permanent=False, database_integrity='NOT_CHECKED')
        phase('bridge_verified')
        return report
    except BaseException as error:
        report.update(status='STOP', error_type=type(error).__name__)
        budget.recovery = True
        try:
            if guard_attempted:
                host.restore_guard()
            if report['restart_attempted']:
                host.restart(budget)
                host.verify(budget,4096)
            report['recovery'] = ('original_setting_restored_collection_not_certified'
                                  if guard_attempted else 'no_service_or_config_change')
        except BaseException as error:
            report['recovery'] = 'MANUAL_ACTION_REQUIRED'
            report['recovery_error_type'] = type(error).__name__
        phase('bridge_failed')
        return report


class Host:
    def __init__(self):
        self.directory = None
        self.settings = None
        self.before = None

    def command(self, args, budget, cap=10):
        return subprocess.run(args,cwd=ROOT,text=True,capture_output=True,check=True,
                              timeout=budget.seconds(cap)).stdout.strip()

    def states(self,budget):
        result = {}
        for unit in UNITS:
            raw=self.command(['systemctl','show',unit,'-p','ActiveState','-p','UnitFileState',
                              '-p','MainPID','-p','NRestarts'],budget)
            result[unit]=dict(line.split('=',1) for line in raw.splitlines() if '=' in line)
        return result

    def config_check(self,budget,guard):
        program=("import os,runpy,sys; sys.dont_write_bytecode=True; sys.path.insert(0,'backend/app'); "
                 "from run_api import load_local_env; os.environ.clear(); load_local_env(); "
                 f"assert os.environ.get('MAX_LOCAL_STORAGE_MB')=='{guard}'; "
                 "runpy.run_path('deploy/lightsail/preflight.py',run_name='__main__')")
        self.command(['sudo','-u','tradebot',str(ROOT/'.venv/bin/python'),'-c',program],budget,15)

    def validate(self,budget):
        import shutil
        revision=self.command(['sudo','-u','tradebot','git','rev-parse','HEAD'],budget)
        if revision!=REVISION or self.command(['sudo','-u','tradebot','git','status','--porcelain','--untracked-files=no'],budget):
            raise ValueError('runtime revision/checkout changed')
        db=ROOT/'data/btc_intelligence.db'
        if not db.is_file() or db.is_symlink():raise ValueError('unexpected database')
        used=sum(p.stat().st_size for p in (db,Path(str(db)+'-wal')) if p.exists())
        if used<4096*1024**2 or used>4608*1024**2 or shutil.disk_usage(ROOT).free<10*1024**3:
            raise ValueError('bridge storage precondition failed')
        path=ROOT/'.env';st=path.stat()
        if path.is_symlink() or st.st_mode&0o777!=0o600:raise ValueError('unsafe configuration')
        # Held only in process memory; never printed or copied to evidence.
        self.settings=path.read_bytes()
        replace_guard(self.settings.decode(),4096,5120)
        self.owner=(st.st_uid,st.st_gid)
        self.before=self.states(budget)
        for state in self.before.values():
            if state['ActiveState']!='active' or state['UnitFileState']!='enabled':raise ValueError('unit not active/enabled')
        self.verify(budget,4096)
        health=self.probe('/health')
        if health.get('collector_running') is not False or health.get('guard_status')!='limit_reached':
            raise ValueError('expected guard-stopped collector')
        self.config_check(budget,4096)

    def set_guard(self,old,new):
        path=ROOT/'.env'; current=path.read_bytes()
        expected=self.settings if old==4096 else replace_guard(self.settings.decode(),4096,5120).encode()
        if current!=expected:raise ValueError('configuration changed externally')
        changed=replace_guard(current.decode(),old,new).encode()
        temporary=path.with_name('.env.bridge-'+str(os.getpid()))
        try:
            fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'wb') as output:
                os.fchown(output.fileno(),*self.owner);output.write(changed);output.flush();os.fsync(output.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def restore_guard(self):
        if (ROOT/'.env').read_bytes()!=self.settings:
            self.set_guard(5120,4096)

    def restart(self,budget):
        self.config_check(budget,4096 if budget.recovery else 5120)
        self.command(['systemctl','restart','tradebot-api'],budget,90)

    def verify(self,budget,guard):
        states=self.states(budget)
        for unit,state in states.items():
            if state['ActiveState']!='active' or state['UnitFileState']!='enabled':raise ValueError('unit inactive')
            if unit!='tradebot-api' and self.before and state.get('MainPID')!=self.before[unit].get('MainPID'):
                raise ValueError('unaffected unit changed')
            if state.get('NRestarts','0')!='0':raise ValueError('automatic service restart')
            if unit.endswith('.timer'):continue
            env=dict(x.split('=',1) for x in Path('/proc',state['MainPID'],'environ').read_text().split('\0') if '=' in x)
            if env.get('ENABLE_OPENAI_ANALYST')!='false' or env.get('ENABLE_LOCAL_RETENTION')!='false' or any(env.get(k) for k in ('OPENAI_API_KEY','OPENAPIKEY','OPENAI_KEY')):
                raise ValueError('unsafe runtime flags')
            if unit=='tradebot-api' and env.get('MAX_LOCAL_STORAGE_MB')!=str(guard):raise ValueError('wrong actual guard')
        listeners=self.command(['ss','-ltnH'],budget).splitlines()
        if [line.split()[3] for line in listeners if line.split()[3].endswith(':8000')]!=['127.0.0.1:8000']:
            raise ValueError('private API listener missing')
        processes=self.command(['ps','-u','tradebot','-o','args='],budget).splitlines()
        if sum('backend/app/run_api.py' in line for line in processes)!=1:raise ValueError('collector ownership')
        if any(re.search(r'backend/app/(streaming|run_collector|dashboard)\.py',line) for line in processes):
            raise ValueError('competing collector/dashboard process')
        if self.settings is not None:
            expected=self.settings if guard==4096 else replace_guard(self.settings.decode(),4096,5120).encode()
            path=ROOT/'.env';st=path.stat()
            if path.read_bytes()!=expected or st.st_mode&0o777!=0o600 or (st.st_uid,st.st_gid)!=self.owner:
                raise ValueError('protected configuration changed')

    @staticmethod
    def probe(route):
        started=time.monotonic()
        try:
            with urllib.request.urlopen('http://127.0.0.1:8000'+route,timeout=2) as response:
                value=json.load(response)
            if route=='/health':
                feeds=value.get('feeds',{})
                result={'collector_running':value.get('collector',{}).get('running'),
                        'guard_status':feeds.get('storage_guard',{}).get('status'),
                        'feeds':{k:{x:feeds.get(k,{}).get(x) for x in ('status','last_data_at')}
                                 for k in ('coinbase_stream','polymarket_stream')}}
            else:
                market=value.get('market') or {}
                result={'market':{k:market.get(k) for k in ('id','start','end')},'updated_at':value.get('updated_at')}
        except Exception as error:result={'error_type':type(error).__name__}
        return dict(result,route=route,elapsed_seconds=round(time.monotonic()-started,4))

    def observe(self,budget):
        first=None; samples=0; resets=0; last_stamps=None
        startup_deadline=time.monotonic()+budget.seconds(180)
        ever_ready=False
        with ThreadPoolExecutor(max_workers=2) as pool:
            while True:
                budget.seconds(1)
                started=time.monotonic()
                probes=list(pool.map(self.probe,('/health','/state/current')))
                now=datetime.now(timezone.utc)
                health,state=probes; good=False
                try:
                    stamps=[datetime.fromisoformat(v['last_data_at'].replace('Z','+00:00')) for v in health['feeds'].values()]
                    good=(health['collector_running'] and health['guard_status']=='watching'
                          and all(v['status']=='live' for v in health['feeds'].values())
                          and all(0<=(now-stamp).total_seconds()<30 for stamp in stamps)
                          and datetime.fromisoformat(state['market']['start'])<=now<datetime.fromisoformat(state['market']['end']))
                except (KeyError,TypeError,ValueError,AttributeError):pass
                if first is not None and any('error_type' in p for p in probes):raise ValueError('API failure during bridge observation')
                if not ever_ready and not good and time.monotonic()>=startup_deadline:
                    raise TimeoutError('bridge startup readiness deadline')
                if not good:
                    if first is not None:resets+=1
                    first=None;last_stamps=None
                else:
                    ever_ready=True
                    if first is None:first=started
                    if last_stamps and any(a<b for a,b in zip(stamps,last_stamps)):raise ValueError('feed timestamp regressed')
                    last_stamps=stamps
                self.save_sample({'at':now.isoformat(),'probes':probes,'qualifying':bool(good)})
                samples+=1
                if first is not None and started-first>=300:
                    self.verify(budget,5120)
                    for route in ('/dashboard','/events'):
                        with urllib.request.urlopen('http://127.0.0.1:8000'+route,timeout=2) as response:
                            if route=='/dashboard':
                                if b'<html' not in response.read(4*1024**2).lower():raise ValueError('dashboard unavailable')
                            elif not response.readline(2*1024**2).startswith(b'data: '):raise ValueError('SSE unavailable')
                    return {'continuous_seconds':started-first,'samples':samples,'window_resets':resets,'dashboard_SSE':'PASS'}
                time.sleep(min(max(0,5-(time.monotonic()-started)),budget.seconds(5)))

    def save(self,report):
        if self.directory is None:
            self.directory=ROOT/'data/deployments'/('capacity-bridge-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
            self.directory.mkdir(mode=0o700)
        path=self.directory/'report.json';path.write_text(json.dumps(report,indent=2)+'\n');path.chmod(0o600)
        print(json.dumps(report),flush=True)

    def save_sample(self,sample):
        path=self.directory/'observation.jsonl'
        with path.open('a') as output:
            path.chmod(0o600);output.write(json.dumps(sample)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--ci-verified-commit')
    parser.add_argument('--ci-run',type=int,default=0)
    args=parser.parse_args()
    if not args.execute:
        print(json.dumps({'mode':'PLAN_ONLY','old_guard_mib':4096,'guard_mib':5120,'revision':REVISION}));return
    if os.geteuid()!=0:parser.error('trusted root operator required')
    interrupted=False
    def stop(signum,frame):
        nonlocal interrupted
        if not interrupted:
            interrupted=True
            raise TimeoutError('operator interruption')
    for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):signal.signal(sig,stop)
    with open('/run/lock/tradebot-deploy.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        report=apply_bridge(Host(),args.ci_verified_commit,args.ci_run)
    raise SystemExit(0 if report['status']=='BRIDGE_ACTIVE' else 1)


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'status':'STOP','error_type':type(error).__name__}),flush=True)
        raise SystemExit(1)
