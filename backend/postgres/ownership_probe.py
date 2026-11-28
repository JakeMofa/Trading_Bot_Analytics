"""Bounded ownership worker and non-payload timing diagnostics.

One process-wide worker is independent of the shared ingestion executor. A
cancelled async caller never frees its outstanding-work ticket before the
native call actually exits. This does not cache or otherwise grant authority.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar, copy_context
import json
import logging
from threading import BoundedSemaphore, Lock
from time import monotonic

PHASES = frozenset({'executor_wait', 'worker_busy', 'admission', 'connect',
                    'environment', 'query', 'close', 'retry_wait', 'worker_complete'})
OUTCOMES = frozenset({'success', 'false_owner', 'async_deadline', 'sql_cancelled',
                      'worker_timeout', 'capacity', 'database_error', 'error', 'cancelled', 'abandoned'})
_current = ContextVar('ownership_probe', default=None)
_executor = None
_outstanding = BoundedSemaphore(1)


class OwnershipProbe:
    def __init__(self, *, clock=monotonic):
        self.clock = clock
        self.started = self.changed = clock()
        self.phase = 'executor_wait'
        self.times = {}
        self.lock = Lock()
        self.finished = False
        self.timed_out = False

    def mark(self, phase):
        if phase not in PHASES:
            raise ValueError('unreviewed ownership phase')
        with self.lock:
            now = self.clock()
            self.times[self.phase] = self.times.get(self.phase, 0) + max(0, now-self.changed)
            self.phase, self.changed = phase, now

    def report(self, outcome, *, late=False):
        if outcome not in OUTCOMES:
            raise ValueError('unreviewed ownership outcome')
        with self.lock:
            now = self.clock()
            times = dict(self.times)
            times[self.phase] = times.get(self.phase, 0) + max(0, now-self.changed)
            elapsed = max(0, now-self.started)
            if not late:
                self.finished = True
                self.timed_out = outcome in {'async_deadline', 'cancelled'}
            record = {'outcome':outcome, 'phase':self.phase, 'late_completion':late,
                      'elapsed_ms':round(elapsed*1000, 3),
                      'worker_finished':self.phase == 'worker_complete',
                      'phase_ms':{key:round(value*1000, 3) for key,value in times.items()}}
        # Fast successes do not generate per-second logs. Fixed keys/categories
        # and a finite phase set cannot reveal DSNs, SQL, UUIDs or payloads.
        if outcome != 'success' or elapsed >= .25 or late:
            try:
                logging.getLogger(__name__).warning('pp_ownership_check %s',
                    json.dumps(record, sort_keys=True, separators=(',', ':')))
            except Exception:
                pass  # Diagnostics cannot change ownership or ingestion.

    def worker(self, callback):
        token = _current.set(self)
        try:
            self.mark('admission')
            return callback()
        finally:
            self.mark('worker_complete')
            _current.reset(token)
            with self.lock:
                late = self.finished and self.timed_out
            if late:
                # This says nothing about whether SQL succeeded or failed:
                # the caller already abandoned the proof in either case.
                self.report('abandoned', late=True)


def phase(name):
    probe = _current.get()
    if probe is not None:
        probe.mark(name)


async def submit_ownership(callback, probe):
    """At most one queued/running native ownership job across async sessions."""
    if not _outstanding.acquire(blocking=False):
        from .live_diagnostics import OwnershipConnectionLimit
        probe.mark('worker_busy')
        raise OwnershipConnectionLimit() from None
    try:
        # Generic migration connections use phase() too: importing this module
        # must not import feed/HTTP dependencies or create executor machinery.
        global _executor
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='pp-ownership')
        context = copy_context()
        probe.mark('executor_wait')
        future = _executor.submit(context.run, probe.worker, callback)
    except BaseException:
        _outstanding.release()
        raise
    # concurrent-future completion (not asyncio cancellation) owns admission.
    future.add_done_callback(lambda _future: _outstanding.release())
    return await asyncio.wrap_future(future)
