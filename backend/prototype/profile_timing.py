"""Bounded timing diagnostics and overdue-heartbeat handoff for a generated fixture.

No payload tracing, production instrumentation, extra writer, pacing sleep or gate
change. Clock/counter overhead is included in heartbeat and whole-run duration.
"""
import asyncio,collections,os,sys,threading,time
from pathlib import Path

try:SCHEDSTATS_ENABLED=Path('/proc/sys/kernel/sched_schedstats').read_text().strip()=='1'
except OSError:SCHEDSTATS_ENABLED=False

def sched_wait():
    if not SCHEDSTATS_ENABLED:return None
    try:return int(Path('/proc/thread-self/schedstat').read_text().split()[1])/1e9
    except (OSError,ValueError,IndexError):return None

def pressure_snapshot():
    if sys.platform!='linux':return {'available':False}
    result={'available':True,'scope':'cgroup counters may include other processes'}
    for name in ('cpu.stat','cpu.pressure','io.pressure','memory.events'):
        try:result[name]=(Path('/sys/fs/cgroup')/name).read_text()[:2048]
        except OSError:result[name]=None
    return result

class Timeline:
    def __init__(self,clock=time.monotonic):
        self.clock=clock;self.start=clock();self.main=threading.get_ident();self.events=collections.deque(maxlen=1024);self.lock=threading.Lock();self.overhead=0.;self.calls=0;self.dropped=False
    def call(self,phase,fn,*args,index=None,**kwargs):
        outer=self.clock();cpu=time.thread_time();wait=sched_wait();begin=self.clock()
        try:return fn(*args,**kwargs)
        finally:
            end=self.clock();after_wait=sched_wait();after_cpu=time.thread_time()
            event={'phase':phase,'index':index,'thread':'main' if threading.get_ident()==self.main else 'worker',
                   'start':begin-self.start,'end':end-self.start,'wall_seconds':end-begin,
                   'thread_cpu_seconds':after_cpu-cpu,'runqueue_wait_seconds':None if wait is None or after_wait is None else max(0,after_wait-wait)}
            with self.lock:
                if len(self.events)==self.events.maxlen:self.dropped=True
                self.events.append(event);self.calls+=1;self.overhead+=max(0,self.clock()-outer-(end-begin))
    def window(self,start,end):
        start-=self.start;end-=self.start
        with self.lock:events=[dict(e) for e in self.events if e['end']>start and e['start']<end];oldest=min((e['start'] for e in self.events if e['thread']=='main'),default=end)
        main=sum(max(0,min(end,e['end'])-max(start,e['start'])) for e in events if e['thread']=='main')
        return {'start':start,'end':end,'main_sync_overlap_seconds':main,
                'events':events[:128],'events_truncated':len(events)>128,
                'main_window_complete':not self.dropped or start>=oldest}

class Heartbeat:
    def __init__(self,timeline,period=.05,clock=time.monotonic):
        self.trace=timeline;self.period=period;self.clock=clock;self.maximum=0.;self.samples=[];self.stopping=False;self.handoffs=0;self.handoff_seconds=0.
    async def start(self):
        self.started=asyncio.Event();self.task=asyncio.create_task(self._run());await self.started.wait()
    async def _run(self):
        loop=asyncio.get_running_loop();prev=self.clock();prev_cpu=time.thread_time();prev_wait=sched_wait()
        self.next_due=prev+self.period;self.tick=loop.create_future();self.started.set()
        while not self.stopping:
            self.next_due=self.clock()+self.period
            await asyncio.sleep(self.period);now=self.clock();cpu=time.thread_time();wait=sched_wait();span=now-prev
            self.maximum=max(self.maximum,span)
            if len(self.samples)<3 or span>min(x['interval_seconds'] for x in self.samples):
                window=self.trace.window(prev,now)
                sample={'interval_seconds':span,'requested_sleep_seconds':self.period,'overdue_seconds':max(0,span-self.period),
                        'thread_cpu_seconds':cpu-prev_cpu,'runqueue_wait_seconds':None if prev_wait is None or wait is None else max(0,wait-prev_wait),**window}
                if span>=.15:sample['resource_snapshot']=pressure_snapshot()
                self.samples=sorted(self.samples+[sample],key=lambda x:x['interval_seconds'],reverse=True)[:3]
            old=self.tick;self.tick=loop.create_future();self.next_due=now+self.period
            if not old.done():old.set_result(None)
            prev=now;prev_cpu=cpu;prev_wait=wait
    async def yield_due(self):
        # Preserve the existing zero-delay yield. If its timer is already due,
        # let that callback finish before another synchronous unit starts.
        await asyncio.sleep(0)
        if self.clock()>=self.next_due:
            self.handoffs+=1;at=self.clock();await asyncio.shield(self.tick);self.handoff_seconds+=self.clock()-at
    async def close(self):
        self.stopping=True;await self.task
    def report(self):
        return {'period_seconds':self.period,'worst_windows':self.samples,'due_timer_handoffs':self.handoffs,
                'handoff_seconds':self.handoff_seconds,'timing_calls':self.trace.calls,'counter_overhead_seconds':self.trace.overhead,
                'max_events_per_window':128,'ring_events':1024,'schedstats_enabled':SCHEDSTATS_ENABLED,'historical_failed_run_has_timeline':False,'worker_events_include_completed_calls_only':True}
