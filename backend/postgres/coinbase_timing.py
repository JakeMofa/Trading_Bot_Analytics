"""Opt-in, bounded timing observations; never raw data or a collector policy.

Parser ingress means a complete WebSocket message parsed before its receive
queue, not NIC arrival. UTC joins source clocks; monotonic clocks measure local
durations. Queue metadata overflow becomes unavailable and never drops a tick.
"""
from collections import deque
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import os
import re
import time

from websockets.asyncio.client import ClientConnection
from websockets.frames import DATA_OPCODES, Frame

from .contract import source_timestamp

ACTIVE_TIMING = ContextVar('pp_coinbase_timing', default=None)
LOG = logging.getLogger(__name__)


def configured_timing(environ=None):
    value = (os.environ if environ is None else environ).get('TRADEBOT_PP_COINBASE_TIMING', 'false')
    if value not in ('true', 'false'):
        raise ValueError('exact Coinbase timing opt-in required')
    return CoinbaseTiming() if value == 'true' else None


def observed_connection(timing):
    """Supported create_connection extension; original protocol handling wins."""
    class ObservedConnection(ClientConnection):
        def process_event(self, event):
            if isinstance(event, Frame) and event.opcode in DATA_OPCODES and event.fin:
                timing.parser_ingress()
            super().process_event(event)
    return ObservedConnection


class CoinbaseTiming:
    MAX_PENDING_MESSAGES = 256
    SUMMARY_SECONDS = 5
    MAX_LOG_BYTES = 4096
    MAX_TIMESTAMP_CHARS = 64

    def __init__(self, *, clock=time.monotonic,
                 wall=lambda: datetime.now(timezone.utc), emit=None):
        self.clock, self.wall = clock, wall
        self.emit = emit or (lambda value: LOG.warning('coinbase_timing %s', json.dumps(value, sort_keys=True)))
        self.pending = deque()
        self.queue_metadata_lost = False
        self.last_read = self.last_event = self.max_save_sample = self.max_lag_sample = None
        self.window_start = clock()
        self.counts, self.metrics, self.total_counts = {}, {}, {}
        self.emit_failures = 0

    def _count(self, name):
        self.counts[name] = self.counts.get(name, 0) + 1
        self.total_counts[name] = self.total_counts.get(name, 0) + 1

    def _metric(self, name, value):
        if value is None:
            return
        stat = self.metrics.setdefault(name, dict(n=0, sum=0.0, max=value))
        stat['n'] += 1
        stat['sum'] += value
        stat['max'] = max(stat['max'], value)

    def connection_attempt(self):
        self.pending.clear()
        self.queue_metadata_lost = False
        self.last_read = self.last_event = None
        self._count('connection_attempts')

    def parser_ingress(self):
        if self.queue_metadata_lost:
            return
        if len(self.pending) >= self.MAX_PENDING_MESSAGES:
            self.pending.clear()
            self.queue_metadata_lost = True
            self._count('queue_metadata_overflows')
            return
        self.pending.append((self.clock(), self.wall().isoformat()))

    def read_started(self):
        self.read_start = self.clock()
        self.read_start_at = self.wall().isoformat()

    def read_completed(self):
        at = self.clock()
        ingress = self.pending.popleft() if self.pending and not self.queue_metadata_lost else None
        self.last_read = dict(recv_started_at=self.read_start_at,
            recv_completed_at=self.wall().isoformat(), recv_wait_ms=(at-self.read_start)*1000,
            parser_ingress_at=ingress[1] if ingress else None,
            parser_queue_ms=(at-ingress[0])*1000 if ingress else None,
            ingress_basis='websocket_parser_complete_message' if ingress else 'unavailable')
        self._count('messages_read')

    @staticmethod
    def _age_ms(later, earlier):
        try:
            return float((source_timestamp(later)[1]-source_timestamp(earlier)[1])*1000)
        except (ValueError, TypeError, KeyError):
            return None

    def parsed(self, event):
        if event is None:
            self._count('non_price_messages')
            return
        sample = dict(self.last_read or {})
        identifier = str(event.get('event_id', ''))
        def timestamp(value):
            if not isinstance(value, str) or len(value) > self.MAX_TIMESTAMP_CHARS:
                return None
            try:
                source_timestamp(value)
            except (ValueError, TypeError):
                return None
            return value
        sample.update(event_id=identifier if re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', identifier) else None,
            source_time=timestamp(event.get('source_time')), received_at=timestamp(event.get('received_at')))
        sample['source_to_dequeue_ms'] = self._age_ms(sample.get('recv_completed_at'), sample['source_time'])
        sample['source_to_parser_ms'] = self._age_ms(sample.get('parser_ingress_at'), sample['source_time'])
        self.last_event = sample

    def saved(self, *, submitted, worker, outcome, sample=None, queued_at=None):
        sample = dict((self.last_event or {}) if sample is None else sample)
        sample['persistence_queue_ms'] = (submitted-queued_at)*1000 if queued_at is not None else None
        sample['outcome'] = outcome
        sample.update(save_started_at=worker.get('started_at'), save_completed_at=worker.get('completed_at'))
        started, completed = worker.get('started'), worker.get('completed')
        sample['save_ms'] = (completed-started)*1000 if completed is not None and started is not None else None
        sample['worker_queue_ms'] = (started-submitted)*1000 if started is not None else None
        sample['resume_ms'] = (self.clock()-completed)*1000 if completed is not None else None
        self._count('save_attempts')
        self._count('save_' + outcome)
        for name in ('save_ms','worker_queue_ms','persistence_queue_ms','persistence_queue_depth','resume_ms','recv_wait_ms',
                     'parser_queue_ms','source_to_parser_ms','source_to_dequeue_ms'):
            self._metric(name, sample.get(name))
        if self.max_save_sample is None or (sample['save_ms'] or 0) > (self.max_save_sample.get('save_ms') or 0):
            self.max_save_sample = sample
        if self.max_lag_sample is None or (sample.get('source_to_dequeue_ms') or 0) > (self.max_lag_sample.get('source_to_dequeue_ms') or 0):
            self.max_lag_sample = sample
        if self.clock()-self.window_start >= self.SUMMARY_SECONDS:
            self.flush('interval')

    def reconnect(self, code, attempt, delay):
        # code is the existing allowlisted LiveDiagnostic.code, never an error body.
        self._count('reconnects')
        self.flush('reconnect', dict(code=code, attempt=attempt, delay_seconds=delay))

    def cooldown(self, code, attempt, delay):
        # Same allowlisted network diagnostic, with an explicit rate-limit branch.
        self._count('rate_limit_cooldowns')
        self.flush('reconnect_cooldown', dict(code=code, attempt=attempt,
            delay_seconds=delay, scope='rolling_rate_limit'))

    def flush(self, reason, details=None):
        value = dict(type='coinbase_timing', reason=reason,
            at=self.wall().isoformat(), interval_seconds=self.clock()-self.window_start,
            counts=dict(self.counts), session_totals=dict(self.total_counts), metrics={name:dict(n=stat['n'], mean=stat['sum']/stat['n'], max=stat['max'])
                for name,stat in self.metrics.items()}, max_save_sample=self.max_save_sample, max_lag_sample=self.max_lag_sample,
            queue_metadata_lost=self.queue_metadata_lost, details=details,
            prior_emit_failures=self.emit_failures)
        try:
            if len(json.dumps(value, sort_keys=True, allow_nan=False).encode()) > self.MAX_LOG_BYTES:
                value.update(max_save_sample=None, max_lag_sample=None, sample_metadata_omitted=True)
            if len(json.dumps(value, sort_keys=True, allow_nan=False).encode()) > self.MAX_LOG_BYTES:
                value = dict(type='coinbase_timing', reason='bounded_summary_overflow',
                             sample_metadata_omitted=True, prior_emit_failures=self.emit_failures)
            self.emit(value)
            self.emit_failures = 0
        except Exception:
            # Diagnostic output failure must not change raw ingestion policy.
            self.emit_failures += 1
        self.counts, self.metrics = {}, {}
        self.max_save_sample = self.max_lag_sample = None
        self.window_start = self.clock()
