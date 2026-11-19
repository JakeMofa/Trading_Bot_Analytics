"""Bounded, sanitized diagnostics; observations never grant retirement authority.

Nested spans overlap: totals must not be added together. Bytes are the existing
logical budget charges, not PostgreSQL/HTTP wire bytes. No identifiers or error
messages are retained. Diagnostic failures cannot replace an operation outcome.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import re
import time

_ACTIVE = ContextVar('retirement_accounting', default=None)
PHASES = frozenset(('local_open', 'local_finish', 'inventory', 'raw_read_decode',
    'raw_local_compare', 'raw_auth_token', 'structured_local_page', 'structured_readback',
    'structured_compare', 'history_connect', 'history_checkout', 'history_release', 'history_transaction',
    'history_identity_checkpoint', 'history_exact_revisions', 'history_latest_receipts',
    'history_newer_revisions', 'history_projections', 'permit_drop'))


class Accounting:
    def __init__(self, clock=time.monotonic):
        self.clock, self.started, self.budget = clock, clock(), None
        self.phases, self.failed_phase, self.sqlstate = {}, None, None
        self.unavailable = False

    def snapshot(self):
        try:
            budget = self.budget
            return {'elapsed_seconds': round(self.clock()-self.started, 6),
                'requests': budget.requests if budget else 0,
                'logical_bytes': budget.bytes if budget else 0,
                'remaining_seconds': round(max(0, budget.deadline-budget.clock()), 6) if budget else None,
                'exhausted_limit': getattr(budget, 'exhausted_limit', None),
                'failed_phase': self.failed_phase, 'sqlstate': self.sqlstate,
                'phases': self.phases.copy(), 'diagnostics_unavailable': self.unavailable,
                'nested_phase_totals_overlap': True}
        except Exception:
            return {'diagnostics_unavailable': True}


def bind_budget(budget):
    active = _ACTIVE.get()
    if active is not None:
        active.budget = budget


@contextmanager
def phase(name):
    active = _ACTIVE.get()
    if active is None:
        yield
        return
    started = None
    try:
        if name not in PHASES:
            raise ValueError('unknown phase')
        started = active.clock()
        requests = active.budget.requests if active.budget else 0
        size = active.budget.bytes if active.budget else 0
    except Exception:
        active.unavailable = True
    try:
        yield
    except BaseException as error:
        try:
            if name in PHASES and active.failed_phase is None:
                active.failed_phase = name
            code = getattr(error, 'sqlstate', None)
            if isinstance(code, str) and re.fullmatch('[0-9A-Z]{5}', code):
                active.sqlstate = code
        except Exception:
            active.unavailable = True
        raise
    finally:
        try:
            if started is not None:
                elapsed = max(0, active.clock()-started)
                row = active.phases.setdefault(name, {'calls':0, 'seconds':0.,
                    'max_seconds':0., 'requests':0, 'logical_bytes':0})
                row['calls'] += 1
                row['seconds'] = round(row['seconds']+elapsed, 6)
                row['max_seconds'] = round(max(row['max_seconds'], elapsed), 6)
                row['requests'] += (active.budget.requests if active.budget else 0)-requests
                row['logical_bytes'] += (active.budget.bytes if active.budget else 0)-size
        except Exception:
            active.unavailable = True


@contextmanager
def measured_context(manager, *, enter, finish):
    # ExitStack would obscure commit/rollback time. The original manager retains
    # full exception suppression/rollback semantics, including failed __enter__.
    with phase(enter):
        value = manager.__enter__()
    try:
        yield value
    except BaseException:
        import sys
        with phase(finish):
            suppress = manager.__exit__(*sys.exc_info())
        if not suppress:
            raise
    else:
        with phase(finish):
            manager.__exit__(None, None, None)


def accounted(operation):
    @wraps(operation)
    def wrapped(*args, **kwargs):
        accounting = Accounting()
        token = _ACTIVE.set(accounting)
        try:
            result = operation(*args, **kwargs)
            result['phase_accounting'] = accounting.snapshot()
            return result
        except Exception as error:
            # The original exception/type/message remains authoritative.
            try:
                error.retirement_accounting = accounting.snapshot()
            except Exception:
                pass
            raise
        finally:
            _ACTIVE.reset(token)
    return wrapped
