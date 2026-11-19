"""Server-owned query registry: clients cannot submit manifests or origins."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import re
import threading
import time

from .archive_codec import ArchiveIntegrityError, ArchiveUnavailable
from .cold_structured_history import ColdStructuredHistory, ORIGIN


class ColdQueryUnavailable(ArchiveUnavailable):
    code = 'cold_history_unknown_query'


class ColdQueryBusy(ArchiveUnavailable):
    code = 'cold_history_busy'


class RegisteredStructuredHistory:
    """Inject only reviewed queries; one remote request at a time, <=4 starts/s.

    Registry authentication/selection is an operator prerequisite. Registration
    is a trusted in-process composition API, not an HTTP upload endpoint.
    """
    origin_id = ORIGIN

    def __init__(self, queries, *, clock=time.monotonic):
        if not isinstance(queries, dict) or not 1 <= len(queries) <= 32:
            raise ValueError('bounded trusted cold-query registry required')
        self._queries = {}
        for key, query in queries.items():
            if (not isinstance(key, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', key)
                    or set(query) != {'reader', 'manifest', 'entity_type', 'market_id'}
                    or not isinstance(query['reader'], ColdStructuredHistory)
                    or query['reader'].origin_id != ORIGIN):
                raise ValueError('trusted PP cold-query binding required')
            self._queries[key] = {**query, 'manifest': deepcopy(query['manifest'])}
        self._admission = threading.BoundedSemaphore(1)
        self._clock, self._next_start = clock, float('-inf')
        self._state_lock = threading.Lock()
        self._closed = False
        # No thread is started until an admitted API request is submitted.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='cold-history')

    def _reserve(self, query_id, *, after_id=None, scope_sha256=None):
        query = self._queries.get(query_id)
        if query is None:
            raise ColdQueryUnavailable('reviewed historical query unavailable')
        if not self._admission.acquire(blocking=False):
            raise ColdQueryBusy('historical retrieval already running')
        try:
            with self._state_lock:
                if self._closed:
                    raise ArchiveUnavailable('historical query registry closed')
                now = self._clock()
                if now < self._next_start:
                    raise ColdQueryBusy('historical request rate exceeded')
                self._next_start = now + .25
            cursor = None
            if after_id is not None or scope_sha256 is not None:
                if type(after_id) is not int or not isinstance(scope_sha256, str):
                    raise ArchiveIntegrityError('invalid historical continuation')
                cursor = dict(scope_sha256=scope_sha256, after_id=after_id)
            return query, cursor
        except BaseException:
            self._admission.release()
            raise

    def _read_reserved(self, query, cursor):
        try:
            return query['reader'].read_page(query['manifest'],
                entity_type=query['entity_type'], market_id=query['market_id'], cursor=cursor)
        finally:
            self._admission.release()

    def read_query(self, query_id, *, after_id=None, scope_sha256=None):
        query, cursor = self._reserve(query_id, after_id=after_id, scope_sha256=scope_sha256)
        return self._read_reserved(query, cursor)

    def submit_query(self, query_id, *, after_id=None, scope_sha256=None):
        # Reserve on the caller/event-loop thread, before executor submission.
        # At most one cold task can occupy this dedicated executor or its queue.
        query, cursor = self._reserve(query_id, after_id=after_id, scope_sha256=scope_sha256)
        try:
            with self._state_lock:
                if self._closed:
                    raise ArchiveUnavailable('historical query registry closed')
                future = self._executor.submit(self._read_reserved, query, cursor)
        except BaseException:
            self._admission.release()
            raise
        # A cancelled queued future never enters _read_reserved's finally.
        future.add_done_callback(lambda done: self._admission.release() if done.cancelled() else None)
        return future

    def close(self):
        with self._state_lock:
            self._closed = True
        # Admitted work retains its slot and connection until its own cleanup.
        self._executor.shutdown(wait=True, cancel_futures=False)
