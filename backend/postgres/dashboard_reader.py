"""Local PostgreSQL budget shared by every public Benchmark dashboard view."""

from contextlib import contextmanager
from threading import BoundedSemaphore

from .connection import EnvironmentMismatch
from .history import HistoryError
from .store import Store


class WatchDashboardStore(Store):
    """Two concurrent client sessions in the single public API process.

    The foundation allows four sessions for tradebot_reader. The remaining
    slots serve independent operator/controller readbacks. Admission covers
    connection establishment, transaction use, rollback and close.
    """

    def __init__(self, settings):
        super().__init__(settings)
        self._slots = BoundedSemaphore(2)

    @contextmanager
    def connection(self, readonly=False):
        if not readonly:
            raise EnvironmentMismatch('Benchmark dashboard requires a read-only transaction')
        if not self._slots.acquire(timeout=0.25):
            raise HistoryError('history_busy', 'local dashboard readers are busy')
        try:
            with super().connection(readonly=True) as db:
                # libpq reports the actual connection user. Starting SQL here
                # would invalidate callers' initial SET TRANSACTION ISOLATION.
                if db.info.user != 'tradebot_reader' or not db.read_only:
                    raise EnvironmentMismatch('Benchmark dashboard requires the reader login')
                yield db
        finally:
            self._slots.release()
