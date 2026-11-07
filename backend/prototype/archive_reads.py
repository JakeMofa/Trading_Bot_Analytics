"""Generated integration adapter: bounded authenticated GETs; never retries writes.

The caller supplies the ORIGINAL phase deadline. Each HTTP request gets the
remaining budget as an inactivity timeout; late responses are rejected.
This is NOT a hard wall-clock HTTP deadline: trickled responses require a
reviewed enclosing phase supervisor before production integration. Verification stays outside this
transport helper, so corrupt evidence never becomes a retryable response.
"""
import math
import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote
import httpx

class ArchiveHold(RuntimeError):
    pass
class ArchiveMissing(ArchiveHold):
    pass

class BoundedArchiveReads:
    def __init__(self, cloud, deadline, clock=time.monotonic, sleep=time.sleep, max_bytes=64*1024**2,
                 jitter=lambda: random.uniform(0, .250), wall=lambda: datetime.now(timezone.utc)):
        self.cloud, self.deadline = cloud, deadline
        self.clock, self.sleep, self.jitter, self.wall = clock, sleep, jitter, wall
        self.max_bytes=max_bytes

    def download_bytes(self, bucket, path):
        for attempt in range(3):
            remaining = self.deadline - self.clock()
            if remaining <= 0:
                raise ArchiveHold('archive GET deadline exhausted')
            response = None
            try:
                with self.cloud.client.stream('GET',
                    f'{self.cloud.config.url}/storage/v1/object/authenticated/'
                    f'{quote(bucket, safe="")}/{quote(path, safe="/")}',
                    headers=self.cloud._headers(**{'Cache-Control': 'no-store'}),
                    timeout=remaining) as response:
                    response.raise_for_status()
                    data=bytearray()
                    for block in response.iter_bytes():
                        if self.clock() >= self.deadline:
                            raise ArchiveHold('archive GET returned after deadline')
                        if len(data)+len(block)>self.max_bytes:raise ArchiveHold('archive response resource bound')
                        data.extend(block)
                    if self.clock() >= self.deadline:raise ArchiveHold('archive GET returned after deadline')
                    return bytes(data)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code==404:raise ArchiveMissing('archive object missing') from None
                if exc.response.status_code != 429 and not 500 <= exc.response.status_code < 600:
                    raise ArchiveHold(f'archive GET permanent HTTP {exc.response.status_code}') from None
            except (httpx.TimeoutException, httpx.NetworkError):
                pass
            if attempt == 2:
                raise ArchiveHold('archive GET transient attempts exhausted')
            delay = (1, 2)[attempt] + min(.250, max(0, self.jitter()))
            if response is not None and 'Retry-After' in response.headers:
                value = response.headers['Retry-After']
                try:
                    retry = float(value)
                    if retry < 0 or not math.isfinite(retry):
                        raise ValueError()
                except ValueError:
                    try:
                        date = parsedate_to_datetime(value)
                        if date.tzinfo is None: raise ValueError()
                        retry = max(0, (date - self.wall()).total_seconds())
                    except (ValueError, TypeError, OverflowError):
                        raise ArchiveHold('invalid archive Retry-After') from None
                delay = max(delay, retry)
            if delay >= self.deadline - self.clock():
                raise ArchiveHold('archive retry deferred: insufficient original deadline')
            self.sleep(delay)

# The hard supervisor runs the entire logical GET, retries, body read and backoff
# in ONE child. Parent reads nonblocking framed output against the SAME deadline.
# No worker thread is abandoned with an outstanding network request.
class HardArchiveReads:
    def __init__(self, cloud, deadline, max_bytes=64*1024**2, operation=None):
        self.cloud,self.deadline,self.max_bytes=cloud,deadline,max_bytes
        self.last_child_pid=None;self.operation=operation
    def download_bytes(self,bucket,path):
        import multiprocessing,os,selectors,socket,threading
        if threading.current_thread() is not threading.main_thread() or threading.active_count()!=1:
            raise ArchiveHold('hard GET requires isolated single-thread worker')
        if 'fork' not in multiprocessing.get_all_start_methods():raise ArchiveHold('hard GET supervisor unavailable')
        if time.monotonic()>=self.deadline:raise ArchiveHold('archive GET deadline exhausted')
        parent,child=socket.socketpair();parent.setblocking(False)
        def run():
            parent.close()
            try:
                data=(self.operation() if self.operation else BoundedArchiveReads(self.cloud,self.deadline,max_bytes=self.max_bytes).download_bytes(bucket,path))
                if len(data)>self.max_bytes:raise ArchiveHold('archive response resource bound')
                child.sendall(b'1'+data)
            except ArchiveMissing:
                try:child.sendall(b'2')
                except OSError:pass
            except BaseException:
                # Never serialize exception text/headers/configuration.
                try:child.sendall(b'0')
                except OSError:pass
            finally:child.close()
        worker=multiprocessing.get_context('fork').Process(target=run)
        selector=selectors.DefaultSelector();data=bytearray()
        try:
            worker.start();self.last_child_pid=worker.pid;child.close();selector.register(parent,selectors.EVENT_READ)
            while True:
                remaining=self.deadline-time.monotonic()
                if remaining<=0:raise ArchiveHold('hard archive GET deadline exceeded')
                if not selector.select(remaining):raise ArchiveHold('hard archive GET deadline exceeded')
                block=parent.recv(min(65536,self.max_bytes+2-len(data)))
                if not block:break
                data.extend(block)
                if len(data)>self.max_bytes+1:raise ArchiveHold('archive response resource bound')
            if time.monotonic()>=self.deadline:raise ArchiveHold('late archive GET result')
            if data and data[0]==50:raise ArchiveMissing('archive object missing')
            if not data or data[0]!=49:raise ArchiveHold('archive GET held by child')
            return bytes(data[1:])
        finally:
            selector.close();parent.close();child.close()
            if worker.pid:
                # SIGKILL and reap; no second operation/retry after a deadline.
                if worker.is_alive():worker.kill()
                worker.join()
                worker.close()
