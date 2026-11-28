"""One bounded PP collector task; no runtime wiring or automatic start."""
from __future__ import annotations

import asyncio
import logging

from .live_diagnostics import LiveDiagnostic
from .rehearsal_profile import lease_cap


class SessionBusy(RuntimeError):
    pass


class SessionStopUnproven(RuntimeError):
    pass


class OperatorSession:
    def __init__(self, run, durable_off, *, rehearsal_anchor=None):
        if not callable(run) or not callable(durable_off):
            raise ValueError('runner and durable OFF callback required')
        self.max_session_seconds = lease_cap(rehearsal_anchor)
        self._rehearsal = rehearsal_anchor is not None
        self._run = run
        self._durable_off = durable_off
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._stop: asyncio.Event | None = None
        self._last_error: str | None = None
        self._last_failure_code: str | None = None
        self._failure_acknowledged = False

    def state(self):
        return {'process_running': self._task is not None and not self._task.done(),
                'last_error': self._last_error,
                'failure_code': self._last_failure_code, 'failure_acknowledged': self._failure_acknowledged}

    async def start(self, *, max_seconds: int):
        if not isinstance(max_seconds, int) or isinstance(max_seconds, bool) or not 1 <= max_seconds <= self.max_session_seconds:
            raise ValueError('session deadline outside configured finite window')
        if self._rehearsal and max_seconds != self.max_session_seconds:
            raise ValueError('two-leg rehearsal requires its explicit complete finite budget')
        async with self._lock:
            if self._task is not None and not self._task.done():
                raise SessionBusy('PP collector session already running')
            # A previous task may have failed while its durable state is unknown.
            # Recovery requires an explicit OFF acknowledgement before re-entry.
            if self._last_error is not None:
                raise SessionStopUnproven('previous session requires explicit OFF')
            self._last_failure_code = None
            self._failure_acknowledged = False
            self._stop = asyncio.Event()
            self._task = asyncio.create_task(self._execute(self._stop, max_seconds))
            return self.state()

    async def _execute(self, stop, max_seconds):
        try:
            await self._run(stop, max_seconds)
        except BaseException as error:
            self._last_error = 'session_failed_or_cancelled'
            self._last_failure_code = (error.code if isinstance(error, LiveDiagnostic)
                                       else 'session.cancelled' if isinstance(error, asyncio.CancelledError)
                                       else 'session.unclassified')
        finally:
            try:
                result = await asyncio.to_thread(self._durable_off)
                if not isinstance(result, dict) or result.get('collector_enabled') is not False:
                    self._last_error = 'durable_off_unproven'
                    self._last_failure_code = 'session.durable_off_unproven'
            except BaseException:
                self._last_error = 'durable_off_unproven'
                self._last_failure_code = 'session.durable_off_unproven'
            if self._last_failure_code:
                logging.getLogger(__name__).warning(
                    'pp_collector_session_stopped reason=%s', self._last_failure_code)

    async def stop(self, *, timeout_seconds: float = 5):
        if not 0 < timeout_seconds <= 5:
            raise ValueError('bounded stop required')
        async with self._lock:
            self._failure_acknowledged = False
            if self._stop is not None:
                self._stop.set()
            task = self._task
            if task is not None and not task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout_seconds)
                except asyncio.TimeoutError:
                    task.cancel()
                    # Cancellation does not prove the callback finished. The
                    # DB lease remains the final write guard until expiry.
                    self._last_error = 'session_stop_timed_out'
                    self._last_failure_code = 'session.stop_timed_out'
            try:
                result = await asyncio.to_thread(self._durable_off)
            except Exception:
                result = None
            if not isinstance(result, dict) or result.get('collector_enabled') is not False:
                self._last_error = 'durable_off_unproven'
                self._last_failure_code = 'session.durable_off_unproven'
                raise SessionStopUnproven('durable OFF acknowledgement missing')
            if task is None or task.done():
                self._last_error = None
                self._failure_acknowledged = self._last_failure_code is not None
            elif self._last_error is not None:
                raise SessionStopUnproven('collector task still running')
            return self.state()
