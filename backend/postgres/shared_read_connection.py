"""One private Benchmark reader socket, exclusively borrowed for one fresh transaction.

The operator has a single reader login slot. Give a waiting ownership check the
next borrow ahead of preference and status reads. No borrower inherits another
transaction or reconnects/replays a failed statement.
"""
import math
import os
from threading import Condition, current_thread
from time import monotonic

from psycopg import OperationalError
from psycopg.pq import TransactionStatus

from . import ownership_probe
from .watch_connections import LocalAdmissionBusy


class SharedReadConnection:
    """All private operator reads must share this instance and its physical budget."""

    def __init__(self, budget):
        if budget.login != 'tradebot_reader':
            raise ValueError('Benchmark reader budget required')
        self.login = budget.login
        self._budget = budget
        self._pid = os.getpid()
        self._condition = Condition()
        self._waiting = {True: 0, False: 0}
        self._busy = False
        self._shutdown = False
        self._db = None

    def _check_process(self):
        # An inherited libpq connection must never be queried or closed in a
        # child (including acquiring a Python lock inherited from another thread).
        if self._pid != os.getpid():
            raise RuntimeError('private reader belongs to another process')

    def _reserve(self, owner, wait):
        deadline = monotonic() + wait
        with self._condition:
            if self._shutdown:
                raise OperationalError('private reader is closed')
            if not self._busy and (owner or not self._waiting[True]):
                self._busy = True
                return
            # One ownership admission may wait even when both ordinary places
            # (control preferences and status) are occupied.
            if self._waiting[owner] >= (1 if owner else 2):
                raise LocalAdmissionBusy('private reader queue full')
            self._waiting[owner] += 1
            try:
                while True:
                    remaining = deadline - monotonic()
                    if self._shutdown:
                        raise OperationalError('private reader is closed')
                    if remaining <= 0:
                        raise LocalAdmissionBusy('private reader admission timed out')
                    if not self._busy and (owner or not self._waiting[True]):
                        self._busy = True
                        return
                    self._condition.wait(remaining)
            finally:
                self._waiting[owner] -= 1
                self._condition.notify_all()

    def _discard(self):
        if self._db is None:
            return
        try:
            # The underlying connection releases the SessionBudget token only
            # on actual close. A failed close leaves this broker quarantined.
            self._db.close()
            if not self._db.closed:
                raise OperationalError('private reader close unconfirmed')
        except BaseException:
            with self._condition:
                self._shutdown = True
                self._condition.notify_all()
            raise
        self._db = None

    def _release(self, *, discard):
        with self._condition:
            if not discard and not self._shutdown:
                self._busy = False
                self._condition.notify_all()
                return
        try:
            self._discard()
        finally:
            with self._condition:
                self._busy = False
                self._condition.notify_all()

    def open(self, *, readonly, wait=0.20):
        self._check_process()
        if readonly is not True or type(wait) not in (int, float) or not math.isfinite(wait) or not 0 <= wait <= 0.20:
            raise ValueError('bounded read-only borrow required')
        owner = ownership_probe.is_ownership_check()
        ownership_probe.phase('admission')
        deadline = monotonic() + 2
        self._reserve(owner, wait)
        try:
            if self._db is not None and (self._db.closed or
                    self._db.info.transaction_status != TransactionStatus.IDLE):
                self._discard()
            reused = self._db is not None
            if not reused:
                self._db = self._open_physical(deadline)
            with self._condition:
                if self._shutdown:
                    raise OperationalError('private reader is closed')
            return _Borrow(self, owner, deadline, reused)
        except BaseException:
            self._release(discard=True)
            raise

    def _open_physical(self, deadline):
        with self._condition:
            if self._shutdown:
                raise OperationalError('private reader is closed')
        if monotonic() >= deadline:
            raise TimeoutError('private reader acquisition expired')
        db = self._budget.open(readonly=True, wait=0)
        # Keep ownership of the handle even when validation fails. The same
        # close/physical-ticket quarantine applies to reconnect and startup.
        self._db = db
        if monotonic() >= deadline:
            raise TimeoutError('private reader acquisition expired')
        if db.closed or not db.read_only or db.info.transaction_status != TransactionStatus.IDLE:
            raise OperationalError('private reader is not idle and read-only')
        return db

    def close(self):
        """Reject new borrows; an active native caller will close on return."""
        self._check_process()
        with self._condition:
            self._shutdown = True
            self._condition.notify_all()
            if self._busy or self._db is None:
                return
            self._busy = True
        self._release(discard=True)


class _Borrow:
    def __init__(self, broker, owner, deadline, reused):
        self._broker = broker
        self._db = broker._db
        self._deadline = deadline
        self._reused = reused
        self._thread = current_thread()
        self._owner = owner
        self._started = False
        self._entered = False
        self._finished = False
        self._failed = False

    def _check(self):
        self._broker._check_process()
        if self._thread is not current_thread() or self._finished:
            raise RuntimeError('private reader borrow no longer belongs to caller')

    def __enter__(self):
        self._check()
        if self._entered:
            raise RuntimeError('private reader borrow is already entered')
        self._entered = True
        return self

    def _begin(self):
        if monotonic() >= self._deadline:
            raise TimeoutError('private reader setup expired')
        # psycopg begins READ ONLY before this first SQL. SET LOCAL expires
        # at transaction end. PG17 transaction_timeout also bounds an idle
        # or multi-statement reader until its native worker returns.
        ms, lock, total = ('1900ms', '250ms', '2s') if self._owner else ('200ms', '75ms', '500ms')
        self._db.execute("""SELECT set_config('statement_timeout',%s,true),
            set_config('lock_timeout',%s,true),set_config('transaction_timeout',%s,true)""",
            (ms, lock, total))
        if monotonic() >= self._deadline:
            raise TimeoutError('private reader setup expired')
        self._started = True

    def execute(self, sql, params=None):
        self._check()
        if self._failed:
            raise OperationalError('private reader transaction failed')
        try:
            if not self._started:
                try:
                    self._begin()
                except OperationalError as error:
                    # A terminated idle backend may still look IDLE to libpq.
                    # Only our own startup read may be retried. Once any caller
                    # SQL begins, return its failure without replaying it.
                    state = error.sqlstate
                    disconnected = self._db.broken and (
                        state is None or state.startswith('08') or state in ('57P01', '57P02'))
                    if not self._reused or not disconnected:
                        raise
                    self._broker._discard()
                    self._db = self._broker._open_physical(self._deadline)
                    self._begin()
            cur = self._db.execute(sql, params)
            return _Result(self, cur)
        except BaseException:
            self._failed = True
            raise

    def _finish(self, *, failed):
        self._check()
        self._finished = True
        discard = failed or self._failed
        try:
            if self._failed and not failed:
                raise OperationalError('private reader transaction failed')
            if not discard and self._started:
                if self._db.info.transaction_status != TransactionStatus.INTRANS:
                    raise OperationalError('private reader transaction boundary changed')
                self._db.commit()
            if not discard and self._db.info.transaction_status != TransactionStatus.IDLE:
                raise OperationalError('private reader did not return idle')
        except BaseException:
            discard = True
            raise
        finally:
            # Physical close ends any aborted transaction without handing it
            # to the next caller. A cancelled async waiter cannot call this for
            # a native worker that still owns the borrow.
            self._broker._release(discard=discard)

    def __exit__(self, exc_type, exc, tb):
        self._finish(failed=exc_type is not None)

    def close(self):
        self._check()
        self._finish(failed=self._started)


class _Result:
    """Don't let a cursor or its connection escape the borrow's lifetime."""
    def __init__(self, borrow, cursor):
        self._borrow = borrow
        self._cursor = cursor

    def fetchone(self):
        self._borrow._check()
        return self._cursor.fetchone()

    def fetchall(self):
        self._borrow._check()
        return self._cursor.fetchall()
