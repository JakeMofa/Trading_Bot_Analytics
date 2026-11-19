"""Explicit PP cold reads using a separately qualified SELECT-only identity.

No service registers this source. Its caller owns private TLS/DSN validation and
manifest authenticity. It never accepts the structured writer as a reader.
"""
from __future__ import annotations

import math
import time

from .archive_codec import ArchiveIntegrityError, ArchiveLimit, ArchiveUnavailable
from .cold_structured_history import ColdStructuredHistory, MAX_BYTES, MAX_ROWS, MAX_SECONDS, ORIGIN
from .history_v2_transport import HistoryV2PostgresTransport

READER_ROLE = 'tradebot_pp_history_reader'


class ReadOnlyStructuredSource:
    """Small read-only surface; reuses existing exact envelope/receipt decoder."""
    def __init__(self, connection_factory, *, origin_id, generation_id,
                 expected_database='postgres', clock=time.monotonic):
        self.origin_id, self.generation_id = origin_id, generation_id
        self.connection_factory, self.clock = connection_factory, clock
        self._decoder = HistoryV2PostgresTransport(connection_factory,
            origin_id=origin_id, generation_id=generation_id,
            expected_database=expected_database, expected_role=READER_ROLE)
        # Reuse the query contract's canonical generation/source checks.
        ColdStructuredHistory(self, origin_id=origin_id, generation_id=generation_id)

    @staticmethod
    def _reader_identity(connection):
        row = connection.execute("""SELECT current_user=session_user AS direct_login,
            current_setting('transaction_read_only')='on' AS read_only,
            NOT (r.rolsuper OR r.rolbypassrls OR r.rolcreaterole OR
                 r.rolcreatedb OR r.rolreplication) AS restricted_role,
            has_schema_privilege(current_user,'history_v2','USAGE') AS schema_read,
            NOT has_schema_privilege(current_user,'history_v2','CREATE') AS no_schema_write,
            has_table_privilege(current_user,'history_v2.structured_receipts','SELECT')
              AND has_table_privilege(current_user,
                  'history_v2.structured_revision_payloads','SELECT') AS can_read,
            NOT EXISTS (SELECT FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='history_v2' AND c.relkind IN ('r','p','v','m','f')
                  AND (has_table_privilege(current_user,c.oid,
                      'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN')
                    OR has_any_column_privilege(current_user,c.oid,
                      'INSERT,UPDATE,REFERENCES'))) AS no_table_write
            FROM pg_roles r WHERE r.rolname=current_user""").fetchone()
        required = ('direct_login', 'read_only', 'restricted_role', 'schema_read',
                    'no_schema_write', 'can_read', 'no_table_write')
        if row is None or any(row.get(key) is not True for key in required):
            raise ArchiveIntegrityError('structured history requires a SELECT-only reader')

    def read_revisions(self, ids, *, max_bytes, timeout_seconds):
        if (not isinstance(ids, list) or not 1 <= len(ids) <= MAX_ROWS
                or any(type(key) is not int or not 0 < key < 2**63 for key in ids)
                or ids != sorted(set(ids)) or type(max_bytes) is not int
                or not 1 <= max_bytes <= MAX_BYTES
                or isinstance(timeout_seconds, bool)
                or not isinstance(timeout_seconds, (int, float))
                or not math.isfinite(timeout_seconds)
                or not 0 < timeout_seconds <= MAX_SECONDS):
            raise ArchiveLimit('invalid cold structured source bound')
        deadline = self.clock() + timeout_seconds
        try:
            with self.connection_factory(timeout_seconds=timeout_seconds) as connection:
                # psycopg starts BEGIN READ ONLY on entering the transaction.
                # A factory returning an unfinished transaction fails closed.
                connection.read_only = True
                connection.prepare_threshold = None
                remaining = deadline - self.clock()
                if remaining <= 0:
                    raise ArchiveLimit('cold structured connection deadline reached')
                with connection.transaction():
                    self._decoder._limit(connection, remaining)
                    self._decoder._identity(connection)
                    self._reader_identity(connection)
                    records = self._decoder._read_revisions(connection, ids, max_bytes)
            if self.clock() >= deadline:
                raise ArchiveLimit('cold structured source deadline reached')
            return records
        except (ArchiveIntegrityError, ArchiveLimit):
            raise
        except Exception:
            raise ArchiveUnavailable('cold structured source unavailable') from None


def configured_cold_history(settings, environ, *, generation_id, connection_factory):
    """Construct only on explicit PP opt-in; never read credentials or dial here."""
    flag = environ.get('TRADEBOT_PP_COLD_STRUCTURED_HISTORY', 'false')
    if flag == 'false':
        return None
    if (flag != 'true' or settings.environment != 'preprod'
            or settings.data_mode != 'pp_live' or settings.origin_id != ORIGIN):
        raise ValueError('cold structured history requires explicit PP live binding')
    source = ReadOnlyStructuredSource(connection_factory, origin_id=ORIGIN,
                                      generation_id=generation_id)
    return ColdStructuredHistory(source, origin_id=ORIGIN, generation_id=generation_id)
