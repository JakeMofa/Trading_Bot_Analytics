"""Physical client budgets for the single-process services of the Benchmark watch."""

from threading import BoundedSemaphore, Lock

from psycopg import Connection, OperationalError

from .connection import EnvironmentMismatch, connect
from .store import Store


class LocalAdmissionBusy(OperationalError):
    """No local slot was available before any connection attempt or statement."""


class _AdmittedConnection(Connection):
    # The allocator sets the callback only after startup and identity checks.
    _return_slot = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._close_lock = Lock()

    def close(self):
        with self._close_lock:
            super().close()
            if self._return_slot is not None:
                self._return_slot()
                self._return_slot = None

    def __exit__(self, *error):
        try:
            return super().__exit__(*error)
        finally:
            # psycopg's normal __exit__ may raise on COMMIT before close.
            self.close()


class SessionBudget:
    def __init__(self, dsn, login, limit):
        self._dsn = dsn
        self.login = login
        self._slots = BoundedSemaphore(limit)

    def open(self, *, readonly, wait=1.0):
        if not self._slots.acquire(timeout=wait):
            raise LocalAdmissionBusy('bounded local database admission busy')
        db = None
        try:
            db = connect(self._dsn, readonly=readonly, factory=_AdmittedConnection.connect)
            if db.info.user != self.login or db.read_only is not readonly:
                raise EnvironmentMismatch('Benchmark local database login or transaction mode mismatch')
            db._return_slot = self._slots.release
            return db
        except BaseException:
            if db is not None:
                db.close()
            self._slots.release()
            raise


class WatchOperatorStore(Store):
    """A single operator process shares its two budgets with each producer session."""

    read_login = 'tradebot_reader'

    def __init__(self, settings, writes, reads, *, producer_session_id=None):
        super().__init__(settings, producer_session_id=producer_session_id)
        self.writes = writes
        self.reads = reads

    def for_producer(self, session):
        return WatchOperatorStore(self.settings, self.writes, self.reads, producer_session_id=session)

    def connection(self, readonly=False):
        if readonly:
            return self.reads.open(readonly=True, wait=0.20)
        return self.writes.open(readonly=False)


class WatchCalculationStore(Store):
    def __init__(self, settings):
        super().__init__(settings)
        self._slots = SessionBudget(settings.dsn, 'tradebot_app', 2)

    def connection(self, readonly=False):
        return self._slots.open(readonly=readonly)
