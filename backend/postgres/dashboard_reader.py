"""Local PostgreSQL budget shared by every public Benchmark dashboard view."""

from .connection import EnvironmentMismatch
from .history import HistoryError
from .store import Store
from .watch_connections import LocalAdmissionBusy, SessionBudget


class WatchDashboardStore(Store):
    def __init__(self, settings):
        super().__init__(settings)
        self._slots = SessionBudget(settings.dsn, 'tradebot_reader', 2)

    def connection(self, readonly=False):
        if not readonly:
            raise EnvironmentMismatch('Benchmark dashboard requires a read-only transaction')
        try:
            return self._slots.open(readonly=True, wait=0.25)
        except LocalAdmissionBusy:
            raise HistoryError('history_busy', 'local dashboard readers are busy') from None
