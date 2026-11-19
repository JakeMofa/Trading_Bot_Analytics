"""Bounded archive history for explicit API requests on the selected PP origin."""
import threading
import uuid

from .archive_codec import ArchiveLimits
from .cloud_origin_binding import cloud_binding
from .cloud_runtime_profile import cloud_files,storage_paths
from .archive_transport import ScopedArchiveTransport
from .history import ArchiveHistory, HistoryError
from .lifecycle import LifecycleRepository, LifecycleHold


class RuntimeHistory:
    def __init__(self, repository, raw_factory, *, origin_id):
        self.repository = repository
        self.raw_factory = raw_factory
        self.origin_id = origin_id
        self._admission = threading.BoundedSemaphore(1)

    def read_generation(self, generation_id, **kwargs):
        try:
            if str(uuid.UUID(generation_id)) != generation_id:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise HistoryError('invalid_generation', 'generation must be a canonical UUID') from None
        if not self._admission.acquire(blocking=False):
            raise HistoryError('history_busy', 'historical retrieval is already running')
        raw = None
        try:
            generation = self.repository.generation(generation_id)
            if generation['origin_id'] != self.origin_id:
                raise HistoryError('history_origin_mismatch', 'generation belongs to another origin')
            # Local history needs no cloud identity. Cloud retrieval is created
            # only for an explicit request for a retired generation.
            # Transport construction is lazy. A seal can retire between the
            # initial identity lookup and the repository's locked snapshot.
            owner = self
            class LazyRaw:
                def read_authenticated(self, key, **options):
                    nonlocal raw
                    if raw is None:
                        raw = owner.raw_factory()
                    return raw.read_authenticated(key, **options)
            transport = ScopedArchiveTransport(LazyRaw(), None,
                origin_id=self.origin_id, generation_id=generation_id)
            return ArchiveHistory(self.repository, transport, ArchiveLimits()).read_generation(
                generation_id, **kwargs)
        finally:
            try:
                if raw is not None:
                    close = getattr(raw, 'close', None)
                    if close is not None:
                        close()
            finally:
                self._admission.release()


class ReadRepository(LifecycleRepository):
    def __init__(self, connection_factory, *, origin_id):
        super().__init__(connection_factory)
        self.origin_id = origin_id

    def local_history(self, generation_id, after, limits):
        with self.transaction() as connection:
            connection.execute("SET LOCAL lock_timeout='250ms'")
            connection.execute('LOCK TABLE raw.events IN ACCESS SHARE MODE')
            generation = connection.execute(
                'SELECT * FROM archive.generations WHERE generation_id=%s',
                (generation_id,)).fetchone()
            if generation is None or generation['origin_id'] != self.origin_id:
                raise LifecycleHold('unknown history generation')
            if generation['state'] == 'retired':
                return generation, None, False
            # Parent and attached partition relation locks precede state
            # lookup, so transactional retirement cannot remove the rows
            # between that lookup and the page query.
            rows, more = self._page(connection, generation_id, after, limits)
            return generation, rows, more


def configured_history(settings, store, environ):
    flag = environ.get('TRADEBOT_PP_ARCHIVE_HISTORY', 'false')
    if flag == 'false':
        return None
    if (flag != 'true' or settings.environment != 'preprod' or
            settings.data_mode != 'pp_live'):
        raise ValueError('archive history requires exact PP live identity')
    cloud_binding(settings.origin_id)
    files=cloud_files(settings.origin_id,reader=True)
    from .supabase_storage import SupabaseStorageTransport

    def raw():
        return SupabaseStorageTransport.from_machine_files(*storage_paths(files), reader=True,origin_id=settings.origin_id)

    repository = ReadRepository(lambda: store.connection(readonly=True), origin_id=settings.origin_id)
    return RuntimeHistory(repository, raw, origin_id=settings.origin_id)
