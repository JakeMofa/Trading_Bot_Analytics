"""Generated-only Linux attach handshake; preparation is never syscall traced."""
import ctypes
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time
from qualification_lock_gate import TraceUnavailable

TRACE_LIMIT_BYTES=32*1024**2

class TracePhase:
    def __init__(self,prefix,database):
        self.prefix=Path(prefix);self.database=Path(database);self.process=None
        self.stderr=None
    def start(self,db):
        # Exact child PID only. A pipe holds exec until this generated process
        # explicitly permits that tracer under Linux Yama; never permits ANY pid.
        read,write=os.pipe()
        helper=('import os,resource,sys;resource.setrlimit(resource.RLIMIT_FSIZE,('+str(TRACE_LIMIT_BYTES)+','+str(TRACE_LIMIT_BYTES)+'));'
                'os.read(int(sys.argv[1]),1);os.close(int(sys.argv[1]));os.execvp("strace",sys.argv[2:])')
        command=['strace','-ff','-ttt','-T','-yy','-s','256','-e',
                 'trace=fcntl,writev,fdatasync,fsync','-o',str(self.prefix),'-p',str(os.getpid())]
        self.stderr=self.prefix.with_suffix('.attach').open('w')
        try:
            self.process=subprocess.Popen([sys.executable,'-c',helper,str(read),*command],pass_fds=(read,),stderr=self.stderr)
            libc=ctypes.CDLL(None,use_errno=True)
            if libc.prctl(0x59616d61,self.process.pid,0,0,0)!=0:
                raise TraceUnavailable('cannot authorize exact generated tracer PID')
            os.write(write,b'1')
        finally:os.close(read);os.close(write)
        until=time.monotonic()+2
        while True:
            if self.process.poll() is not None:raise TraceUnavailable('generated tracer attachment failed')
            status=Path('/proc/self/status').read_text()
            tracer=int(next(l.split()[1] for l in status.splitlines() if l.startswith('TracerPid:')))
            if tracer==self.process.pid:break
            if time.monotonic()>=until:raise TraceUnavailable('generated tracer attachment timeout')
            time.sleep(.005)
        os.environ['TRADEBOT_LOCK_PHASE']='1'
        db._mark('trace_ready')
        trace=Path(str(self.prefix)+'.'+str(os.getpid()))
        while not trace.exists() or 'trace_ready' not in trace.read_text():
            if self.process.poll() is not None or time.monotonic()>=until:
                raise TraceUnavailable('trace-ready marker missing')
            time.sleep(.005)
        return {'pid':self.process.pid,'trace_ready_at_monotonic':time.monotonic(),
                'syscalls':'fcntl,writev,fdatasync,fsync','trace_limit_bytes':TRACE_LIMIT_BYTES}
    def stop(self):
        os.environ.pop('TRADEBOT_LOCK_PHASE',None)
        if self.process is not None:
            self.process.send_signal(signal.SIGINT) if self.process.poll() is None else None
            try:self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill();self.process.wait(timeout=1)
                raise TraceUnavailable('generated tracer did not detach normally')
        if self.stderr is not None:self.stderr.close()
