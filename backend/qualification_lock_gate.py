"""Incremental Linux strace6.8 WAL WRITE-lock gate for private generated fixtures.

No production imports. Uses syscall entry/exit brackets, not transaction flags.
Ambiguous evidence is never a pass. Decimal times avoid float boundary rounding.
"""
import ast
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import time

class TraceUnavailable(RuntimeError):pass
class LockGateFailure(RuntimeError):pass

class LockGate:
    def __init__(self, trace, database, pid):
        self.trace=Path(trace);self.database=str(Path(database).resolve());self.pid=int(pid)
        self.position=0;self.buffer='';self.pending=None;self.active=None
        self.rows=[];self.enabled=False;self.lines=0;self.parse_seconds=0.
    def drain(self):
        at=time.monotonic()
        try:
            if not self.trace.exists():raise TraceUnavailable('main syscall trace missing')
            with self.trace.open() as stream:
                stream.seek(self.position)
                while True:
                    chunk=stream.read(65536)
                    if not chunk:break
                    self.buffer+=chunk
                    while '\n' in self.buffer:
                        line,self.buffer=self.buffer.split('\n',1);self.consume(line)
                self.position=stream.tell()
        finally:self.parse_seconds+=time.monotonic()-at
    def arm(self):
        if not self.trace.exists():raise TraceUnavailable('main syscall trace missing')
        # Preparation is outside the measured retention scope. If WRITE is
        # already held, the next BEGIN will lack an acquisition and fail closed.
        with self.trace.open() as stream:stream.seek(0,2);self.position=stream.tell()
        self.enabled=True;self.active=None
    def consume(self,line):
        self.lines+=1
        m=re.match(r'(\d+\.\d+)\s+(.*)',line)
        if not m:return # per-TID file; only timestamp-prefixed syscalls qualify
        start=Decimal(m[1]);body=m[2];observed=start
        if '<unfinished ...>' in body:
            if self.pending is not None:raise TraceUnavailable('nested unfinished syscall')
            self.pending=(start,body.replace(' <unfinished ...>',''));return
        if body.startswith('<... '):
            if self.pending is None:raise TraceUnavailable('unmatched resumed syscall')
            start,first=self.pending;self.pending=None;body=first+body.split('resumed>',1)[1]
        duration=re.search(r'<([0-9.]+)>$',body)
        if duration is None:return
        end=max(start+Decimal(duration[1]),observed)
        if not self.enabled:return
        if 'LOCKDIAG' in body:
            match=re.search(r'write\(2.*?, ("(?:[^"\\]|\\.)*")',body)
            if not match:raise TraceUnavailable('truncated marker')
            value=json.loads(ast.literal_eval(match[1]).split('LOCKDIAG ',1)[1])
            if value['pid']!=self.pid:raise TraceUnavailable('wrong marker PID')
            event=value['event']
            if event=='begin_entry':
                if self.active is not None:raise TraceUnavailable('overlapping BEGIN markers')
                self.active={'begin':value,'acquire':[],'release':[],'syncs':[],'writes':0}
            elif self.active is not None and event=='commit_entry':self.active['commit']=value
            elif self.active is not None and event=='commit_return':self.finish(value)
            return
        if self.active is None:return
        path=self.database+'-shm>'
        if body.startswith('fcntl(') and path in body:
            lock=re.search(r'l_type=(F_\w+), l_whence=SEEK_SET, l_start=(\d+), l_len=(\d+)',body)
            if lock and int(lock[2])<=120<int(lock[2])+int(lock[3]) and ') = 0 ' in body:
                if int(lock[2])!=120 or int(lock[3])!=1 or 'F_SETLK,' not in body:
                    raise TraceUnavailable('ambiguous WRITE lock range or locking API')
                if lock[1]=='F_WRLCK':self.active['acquire'].append((start,end))
                elif lock[1]=='F_UNLCK':self.active['release'].append((start,end))
                else:raise TraceUnavailable('unexpected shared WRITE-byte lock')
        if body.startswith(('fdatasync(','fsync(')) and self.database in body:
            self.active['syncs'].append((start,end,'wal' if self.database+'-wal>' in body else 'db',end-start))
        if body.startswith('pwrite64(') and self.database in body:self.active['writes']+=1
    def finish(self,marker):
        a=self.active
        if 'commit' not in a or len(a['acquire'])!=1 or len(a['release'])!=1:
            raise TraceUnavailable('missing or ambiguous lock/commit evidence')
        acquire,release=a['acquire'][0],a['release'][0]
        if not acquire[1]<=release[0]:raise TraceUnavailable('invalid WRITE syscall ordering')
        commit=a['commit'];real=Decimal(marker['real_ns']-commit['real_ns'])/Decimal(10**9)
        mono=Decimal(marker['mono_ns']-commit['mono_ns'])/Decimal(10**9)
        if abs(real-mono)>Decimal('.001'):raise TraceUnavailable('clock bridge disagreement')
        # strace timestamps/durations are microsecond-rounded: expand both ends.
        upper=release[1]-acquire[0]+Decimal('.000002')
        row={'occupancy_upper_seconds':float(upper),'occupancy_lower_seconds':float(max(Decimal(0),release[0]-acquire[1]-Decimal('.000002'))),
             'commit_call_seconds':float(mono),'begin_to_commit_return_seconds':(marker['mono_ns']-a['begin']['mono_ns'])/1e9,
             'post_release_seconds':float(Decimal(marker['real_ns'])/Decimal(10**9)-release[1]),
             'lock_held_sync_seconds':float(sum((d for s,e,f,d in a['syncs'] if e<=release[0]),Decimal(0))),
             'post_release_sync_seconds':float(sum((d for s,e,f,d in a['syncs'] if s>=release[1]),Decimal(0))),
             'writes':a['writes']}
        self.rows.append(row);self.active=None
        if upper>Decimal('.5'):raise LockGateFailure('validated WRITE occupancy exceeded500ms')
        if mono>1:raise LockGateFailure('commit call exceeded1000ms')
        if row['begin_to_commit_return_seconds']>1:raise LockGateFailure('transaction total exceeded1000ms')
    def batch(self, expected):
        self.drain()
        if len(self.rows)!=expected or self.active is not None or self.pending is not None:
            raise TraceUnavailable('batch completed without complete syscall evidence')
    def summary(self):
        return {'method':'Linux per-TID strace entry/exit brackets plus2us rounding reserve',
                'transactions':len(self.rows),'max_occupancy_upper_seconds':max((r['occupancy_upper_seconds'] for r in self.rows),default=None),
                'parse_seconds':self.parse_seconds,'lines':self.lines,'batches':self.rows,
                'tracing_overhead':'changes wall timing; no untraced control, baseline overhead not isolated'}
