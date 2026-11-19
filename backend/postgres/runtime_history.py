"""Bounded archive history for explicit API requests on the selected PP origin."""
import threading

from .archive_codec import ArchiveLimits
from .archive_transport import ScopedArchiveTransport
from .history import ArchiveHistory, HistoryError


class RuntimeHistory:
    def __init__(self, repository, raw_factory, *, origin_id):
        self.repository = repository
        self.raw_factory = raw_factory
        self.origin_id = origin_id
        self._admission = threading.BoundedSemaphore(1)

    def read_generation(self, generation_id, **kwargs):
        if not self._admission.acquire(blocking=False):
            raise HistoryError('history_busy', 'historical retrieval is already running')
        raw = None
        try:
            generation = self.repository.generation(generation_id)
            if generation['origin_id'] != self.origin_id:
                raise HistoryError('history_origin_mismatch', 'generation belongs to another origin')
            # Local history needs no cloud identity. Cloud retrieval is created
            # only for an explicit request for a retired generation.
            if generation['state'] == 'retired':
                raw = self.raw_factory()
                transport = ScopedArchiveTransport(raw, None, origin_id=self.origin_id,
                                                    generation_id=generation_id)
            else:
                transport = None
            return ArchiveHistory(self.repository, transport, ArchiveLimits()).read_generation(
                generation_id, **kwargs)
        finally:
            if raw is not None:
                close = getattr(raw, 'close', None)
                if close is not None:
                    close()
            self._admission.release()


def configured_history(settings, store, environ):
    flag = environ.get('TRADEBOT_PP_ARCHIVE_HISTORY', 'false')
    if flag == 'false':
        return None
    if (flag != 'true' or settings.environment != 'preprod' or
            settings.data_mode != 'pp_live' or settings.origin_id != 'pp-live-pp'):
        raise ValueError('archive history requires exact PP live identity')
    from .lifecycle import LifecycleRepository, LifecycleHold
    from .supabase_storage import SupabaseStorageTransport

    def raw():
        return SupabaseStorageTransport.from_machine_files(
            '/run/secrets/history_reader_api_key', '/run/secrets/history_reader_email',
            '/run/secrets/history_reader_password', '/run/secrets/history_reader_uid', reader=True)

    class ReadRepository(LifecycleRepository):
        def local_history(self, generation_id, after, limits):
            with self.transaction() as connection:
                generation = connection.execute(
                    'SELECT * FROM archive.generations WHERE generation_id=%s',
                    (generation_id,)).fetchone()
                if generation is None or generation['origin_id'] != settings.origin_id:
                    raise LifecycleHold('unknown history generation')
                if generation['state'] == 'retired':
                    return generation, None, False
                # The SELECT's relation lock protects the rows while reading.
                # A concurrent drop before it begins becomes unavailable.
                rows, more = self._page(connection, generation_id, after, limits)
                return generation, rows, more

    repository = ReadRepository(lambda: store.connection(readonly=True),
                                environment='preprod')
    return RuntimeHistory(repository, raw, origin_id=settings.origin_id)
