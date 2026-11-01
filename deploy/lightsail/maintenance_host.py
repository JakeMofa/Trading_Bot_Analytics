"""Quiescent, exact-rollover release adapter. Requires one reviewed root manifest."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import release_verification as rv
import maintenance_controller as controller

AUTH=Path('/run/tradebot-maintenance-release.json')
DEADLINE=datetime(2026,11,2,1,56,47,671426,tzinfo=timezone.utc)
POLICY={'verify':1800,'other':600,'reap':10,'recovery':180,'interruption':2590,'headroom_mib':controller.MIN_HEADROOM_MIB,'ceiling_mib':5120}
FILES=('deploy.py','release_verification.py','smoke.py','maintenance_controller.py','maintenance_host.py')

class Host:
    def __init__(self,cd,release,bundle):
        self.cd=cd;self.release=release;self.bundle=bundle;self.child=None;self.monitors={};self.doc=None
        self.monitor_restore_required=False;self.protected=None;self.before=None;self.binding=None
        self.record=cd.ROOT/'data/deployments'/('maintenance-'+str(time.time_ns())+'.json')
    def utcnow(self):return datetime.now(timezone.utc).isoformat()
    def cmd(self,*args,seconds=30,user=False):
        rv.require(seconds>10,'insufficient command/reap reservation')
        return self.cd.reviewed_run(*args,user=user,timeout=seconds-10)
    def preflight(self):
        if os.geteuid()!=0:raise controller.Stop('root authority required')
        d=rv.private_read(AUTH)
        rv.require(d.get('approval_confirmed') is True and d.get('policy')==POLICY,'wrong maintenance authorization')
        rv.require(d.get('release')==self.release and d.get('old')==rv.OLD,'wrong maintenance release')
        rv.require(type(d.get('ci_run')) is int and d['ci_run']>0,'exact CI acknowledgment missing')
        rv.require(time.time()<d.get('expires_at',0)<=min(time.time()+3600,DEADLINE.timestamp()),'maintenance authority expired')
        for name in FILES:rv.require(d['helpers'].get(name)==rv.sha(Path(__file__).with_name(name)),'helper hash mismatch')
        rv.require(time.time()+controller.INTERRUPTION<DEADLINE.timestamp(),'insufficient time before storage review deadline')
        # Validate code-only helper restoration before touching services.
        for name,spec in d['original_helpers'].items():
            rv.require(name in FILES,'unexpected helper restoration path')
            if spec is not None:
                p=Path(spec['path']);st=p.stat()
                rv.require(st.st_uid==0 and not p.is_symlink() and not st.st_mode&0o022,'unsafe helper code preservation')
                rv.require(rv.sha(p)==spec['sha256'],'original helper code mismatch')
        rv.require(set(d['original_helpers'])==set(FILES),'incomplete helper restoration manifest')
        self.doc=d
        # All git/flags/services commands are owned and timeout/reap bounded.
        with rv.commands(self.cd,120):
            old=rv.source(self.cd,self.release,self.bundle)
            self.before=self.cd.runtime_preflight();self.protected=self.cd.protected()
        pid=self.before['tradebot-api']['MainPID']
        entries=Path('/proc',pid,'environ').read_bytes().split(b'\0')
        rv.require(b'MAX_LOCAL_STORAGE_MB=5120' in entries,'storage ceiling changed')
        rv.require(not any(x.split(b'=',1)[0] in (b'OPENAI_API_KEY',b'OPENAI_KEY',b'OPENAPIKEY') and x.split(b'=',1)[-1] for x in entries),'paid AI credential present')
        sizes=self.allocation(3);rv.require(sizes['physical_mib']<5120,'physical ceiling reached')
        rv.require(5120-(self.cd.ROOT/'data/btc_intelligence.db').stat().st_size/1048576>=POLICY['headroom_mib'],'main file alone fails capacity gate')
        health=rv.fetch('/health');rv.require(health.get('collector',{}).get('running') is True,'collector stopped')
        initial_state=rv.fetch('/state/current');rv.collection_state(initial_state)
        before=rv.owned_process([sys.executable,str(Path(__file__).with_name('release_verification.py')),'--persistence',str(self.cd.ROOT/'data/btc_intelligence.db'),'--market',str(initial_state['market']['id'])],timeout=2)
        rv.require(before.returncode==0,'baseline persistence unavailable');self.baseline=json.loads(before.stdout)
        for unit in ('tradebot-soak.timer','tradebot-soak.service'):
            self.monitors[unit]=self.cmd('systemctl','show',unit,'-p','ActiveState','--value',seconds=15)
        self.doc=d
        claim=AUTH.with_suffix('.claimed.json');rv.require(not claim.exists(),'maintenance attempt already consumed')
        AUTH.rename(claim)
        return {u:self.before[u]['ActiveState'] for u in controller.WRITERS},old
    def pause_monitor(self,seconds):
        self.monitor_restore_required=True;end=time.monotonic()+seconds
        for u in self.monitors:
            if self.monitors[u]=='active':self.stop(u,min(30,max(.01,end-time.monotonic())))
        return dict(self.monitors)
    def stop(self,unit,seconds):self.cmd('systemctl','stop',unit,seconds=min(90,seconds))
    def start(self,unit,seconds):self.cmd('systemctl','start',unit,seconds=min(60,seconds))
    def restore_monitor(self,state,seconds):
        end=time.monotonic()+seconds;failures=[]
        for u in self.monitors:
            if self.monitors[u]=='active':
                try:self.start(u,max(.01,min(30,end-time.monotonic())))
                except BaseException:failures.append(u)
        if failures:raise controller.Stop('monitor restoration failed')
        self.monitor_restore_required=False
    def require_quiescence(self,seconds):
        end=time.monotonic()+min(10,seconds);identities=set()
        p=self.cd.ROOT/'data/btc_intelligence.db'
        for f in (p,Path(str(p)+'-wal'),Path(str(p)+'-shm')):
            if f.exists():st=f.stat();identities.add((st.st_dev,st.st_ino))
        while True:
            owners=[]
            for process in Path('/proc').iterdir():
                if time.monotonic()>=end:raise controller.Stop('descriptor drain deadline')
                if not process.name.isdigit():continue
                try:
                    for fd in (process/'fd').iterdir():
                        try:
                            st=fd.stat()
                            if (st.st_dev,st.st_ino) in identities:owners.append((process.name,fd.name))
                        except FileNotFoundError:pass
                except FileNotFoundError:pass
            if not owners:return
            if time.monotonic()+.05>=end:raise controller.Stop('remaining database owners')
            time.sleep(.05)
    def allocation(self,seconds):
        p=self.cd.ROOT/'data/btc_intelligence.db'
        n=sum(f.stat().st_size for f in (p,Path(str(p)+'-wal')) if f.exists())
        return {'physical_mib':n/1048576,'headroom_mib':5120-n/1048576,'at':self.utcnow()}
    def identity(self,seconds):
        value=rv.identity(self.cd.ROOT/'data/btc_intelligence.db')
        return {'database':value,'release':self.release,'runtime':self.cmd('git','rev-parse','HEAD',user=True,seconds=min(15,seconds)),
            'helpers':{n:rv.sha(Path(__file__).with_name(n)) for n in FILES},'protected':list(self.cd.protected())}
    def verify(self,reap,seconds):
        # Keep a separate reap allowance inside the granted total step cap.
        work=max(.01,seconds-reap)
        self.child=subprocess.Popen([sys.executable,str(Path(__file__).with_name('release_verification.py')),
            '--child',str(self.cd.ROOT/'data/btc_intelligence.db'),'--seconds',str(work)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:out,err=self.child.communicate(timeout=work)
        except BaseException:
            self.reap_owned_child(reap);raise
        rv.require(self.child.returncode==0,'complete verification child failed')
        result=json.loads(out)
        rv.require(result.get('status')=='PASS' and [x['check'] for x in result['checks']]==['quick_check','foreign_key_check'],'incomplete verification')
        return result
    def reap_owned_child(self,seconds):
        if self.child is not None and self.child.poll() is None:rv.reap(self.child,min(10,seconds))
    def checkout_release(self,seconds):self.cmd('git','checkout','--detach',self.release,user=True,seconds=min(30,seconds))
    def checkout_old(self,old,seconds):self.cmd('git','checkout','--detach',old,user=True,seconds=min(30,seconds))
    def collection_probe(self,before=None):
        #128MiB is the one-use quiescent verification prerequisite, not a post-start
        #allocation waiver. Resumed collection must stay below the hard5120 cap.
        health=rv.fetch('/health');state=rv.fetch('/state/current')
        rv.require(health.get('collector',{}).get('running') is True,'collector not running')
        progress=rv.collection_state(state)
        for source in ('coinbase_stream','polymarket_stream'):
            rv.require(health.get('feeds',{}).get(source,{}).get('status')=='live','feed not live')
        result=rv.owned_process([sys.executable,str(Path(__file__).with_name('release_verification.py')),
            '--persistence',str(self.cd.ROOT/'data/btc_intelligence.db'),'--market',str(state['market']['id'])],timeout=2)
        rv.require(result.returncode==0,'persistence probe failed');progress.update(json.loads(result.stdout))
        now=datetime.now(timezone.utc)
        rv.require(all(-5<=(now-rv.stamp(t)).total_seconds()<=30 for t in progress.values()),'persistence/receipt stale')
        if before:rv.require(all(progress[k]!=before[k] for k in progress),'collection did not advance')
        rv.require(self.allocation(1)['physical_mib']<5120,'physical ceiling reached')
        return progress,health

    def smoke(self,seconds):
        end=time.monotonic()+seconds
        rv.require(end-time.monotonic()>40,'insufficient smoke reservation')
        rv.wait_for_api(min(180,max(.01,end-time.monotonic()-30)))
        rv.require(end-time.monotonic()>30,'insufficient probe reservation')
        first,_=self.collection_probe()
        result=json.loads(self.cmd(sys.executable,str(Path(__file__).with_name('smoke.py')),'--rollover-release','--attempts','1',seconds=max(.01,min(180,end-time.monotonic()))))
        time.sleep(min(5,max(0,end-time.monotonic())))
        rv.require(end-time.monotonic()>30,'insufficient final probe reservation')
        self.collection_probe(first)
        with rv.commands(self.cd,max(.01,end-time.monotonic()-30)):after=self.cd.runtime_preflight()
        rv.require(self.cmd('git','rev-parse','HEAD',user=True,seconds=15)==self.release,'wrong deployed revision')
        rv.require(self.cd.protected()==self.protected,'configuration changed')
        rv.require(all(after[u]['ActiveState']==self.before[u]['ActiveState'] and after[u]['NRestarts']==self.before[u]['NRestarts'] for u in controller.WRITERS),'service state/restart mismatch')
        rv.require(self.allocation(1)['physical_mib']<5120,'physical ceiling reached')
        return {'status':'PASS','endpoints':result,'allocation':self.allocation(1),'at':self.utcnow(),
            'before_receipts':self.baseline,'after_receipts':first,
            'receipt_gap_upper_seconds':{k:(rv.stamp(first[k])-rv.stamp(self.baseline[k])).total_seconds() for k in self.baseline}}
    def save(self,report):
        self.record.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        report.update(release=self.release,at=self.utcnow())
        self.record.write_text(json.dumps(report,indent=2)+'\n');self.record.chmod(0o600)
        print(json.dumps(report),flush=True)
    def restore_helpers(self):
        if self.doc is None:return
        failures=[]
        for name,spec in self.doc['original_helpers'].items():
            try:
                target=Path(__file__).with_name(name)
                rv.require(rv.sha(target)==self.doc['helpers'][name],'installed helper changed before restoration')
                if spec is None:target.unlink() # Introduced helper CODE only, never data.
                else:
                    target.write_bytes(Path(spec['path']).read_bytes());target.chmod(spec['mode'])
                    rv.require(rv.sha(target)==spec['sha256'],'helper restoration mismatch')
            except BaseException:failures.append(name)
        if failures:raise controller.Stop('helper restoration incomplete: '+','.join(failures))


def execute(cd,release,bundle):
    host=Host(cd,release,bundle);previous={}
    def interrupted(sig,frame):
        for signal_number in previous:signal.signal(signal_number,signal.SIG_IGN)
        raise controller.Stop('maintenance interrupted')
    try:
        for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):previous[sig]=signal.signal(sig,interrupted)
        result=controller.run(host)
    finally:
        try:host.restore_helpers()
        except BaseException as error:
            if 'result' in locals():
                result.update(status='MANUAL_ACTION_REQUIRED',helper_restoration='FAILED',helper_failure_type=type(error).__name__);host.save(result)
            raise
        else:
            if 'result' in locals():result['helper_restoration']='PASS';host.save(result)
        finally:
            for sig,handler in previous.items():signal.signal(sig,handler)
    if result['status']!='DEPLOYED_SMOKE_TESTED':raise SystemExit(1)
