"""Explicit PP-only single-session reuse, with no transaction/snapshot reuse.

The normal factory remains the default. Every checkout revalidates fixed private
files/TLS/DSN scope; the transport still checks database/login inside each short
transaction. Exceptions discard the physical connection. No retry or local ACK
is performed here, including after an ambiguous commit.
"""
from contextlib import contextmanager
import hashlib
from threading import Lock
import time

from psycopg.pq import TransactionStatus

from .archive_codec import ArchiveIntegrityError, ArchiveLimit, ArchiveUnavailable
from .pp_history_connection import PPHistoryConnectionFactory


def session_reuse_requested(environ):
    value = environ.get('TRADEBOT_PP_REUSE_HISTORY_SESSION', 'false')
    if value not in ('true', 'false'):
        raise ArchiveIntegrityError('exact PP session reuse opt-in required')
    return value == 'true'


class ReusablePPHistoryConnectionFactory(PPHistoryConnectionFactory):
    """One physical authenticated session for one serial PP worker.

    Checkout never queues or holds a transaction open between operations. Fixed
    30-second idle / 300-second lifetime eligibility bounds discard stale sessions
    on the next checkout; shutdown releases the single retained role slot. A valid root-managed password rotation reconnects;
    unsafe or wrongly scoped bindings discard the existing session and HOLD.
    """
    MAX_IDLE_SECONDS = 30
    MAX_LIFETIME_SECONDS = 300

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lock = Lock()
        self._connection = None
        self._binding_hash = None
        self._created_at = self._last_used_at = 0
        self._shutdown = False

    def _discard(self):
        connection, self._connection = self._connection, None
        self._binding_hash = None
        if connection is not None:
            # close() discards any uncommitted transaction. Never issue an
            # unbudgeted rollback/retry on a failed or ambiguous connection.
            connection.close()

    @staticmethod
    def _idle(connection):
        return connection.info.transaction_status == TransactionStatus.IDLE

    @contextmanager
    def __call__(self, *, timeout_seconds):
        if not self._lock.acquire(blocking=False):
            raise ArchiveUnavailable('private PP history session busy')
        try:
            if self._shutdown:
                raise ArchiveUnavailable('private PP history session closed')
            secret, deadline = self._validated_dsn(timeout_seconds)
            binding_hash = hashlib.sha256(secret).digest()
            now = time.monotonic()
            connection = self._connection
            if connection is not None:
                if (connection.closed or connection.broken or binding_hash != self._binding_hash
                        or now - self._last_used_at >= self.MAX_IDLE_SECONDS
                        or now - self._created_at >= self.MAX_LIFETIME_SECONDS):
                    self._discard()
                elif not self._idle(connection):
                    raise ArchiveIntegrityError('private PP history session not idle')
            if self._connection is None:
                self._connection = self._open(secret, deadline)
                self._binding_hash = binding_hash
                self._created_at = time.monotonic()
            connection = self._connection
            if time.monotonic() >= deadline:
                raise ArchiveLimit('private PP history checkout deadline reached')
            if not self._idle(connection):
                raise ArchiveIntegrityError('private PP history session not idle')
            # The caller must enter and finish its own explicit transaction.
            # Transport identity and SET LOCAL deadlines run within that tx.
            yield connection
            if time.monotonic() >= deadline:
                raise ArchiveLimit('private PP history operation deadline reached; reconcile')
            if connection.closed or connection.broken or not self._idle(connection):
                raise ArchiveIntegrityError('private PP history transaction not finished')
            self._last_used_at = time.monotonic()
        except BaseException:
            self._discard()
            raise
        finally:
            self._lock.release()

    def close(self):
        if not self._lock.acquire(blocking=False):
            raise ArchiveUnavailable('private PP history session busy')
        try:
            self._shutdown = True
            self._discard()
        finally:
            self._lock.release()
