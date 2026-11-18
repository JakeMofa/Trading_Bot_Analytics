"""Default-off direct PostgreSQL importer for private structured history.

The caller supplies a narrowly scoped connection factory. No service creates
this adapter yet, and no Supabase grants are installed. Each cloud transaction
applies ordered revisions and immutable receipts together; a separate read
verifies those receipts before the local worker may acknowledge its outbox.
"""
from __future__ import annotations

from datetime import datetime, timezone
import time

from psycopg import sql
from psycopg.types.json import Jsonb

from .archive_codec import (ArchiveIntegrityError, ArchiveLimit,
                            ArchiveUnavailable, encoded, sha256, wire)
from .history_v2_envelope import (CLOUD_COLUMNS, IMPORT_ORDER, MUTABLE_PROJECTIONS,
                                  TABLE_KEYS, cloud_row, cloud_row_matches,
                                  projection_order, validate_outbox_stream)


class HistoryV2PostgresTransport:
    authority_scope = 'supabase-unqualified'

    def __init__(self, connection_factory, *, origin_id: str,
                 generation_id: str, expected_database: str,
                 expected_role: str):
        if (not callable(connection_factory) or not isinstance(origin_id, str) or
                not origin_id.startswith('pp-live-') or not generation_id or
                not expected_database or not expected_role):
            raise ValueError('private structured importer binding required')
        self.connection_factory = connection_factory
        self.origin_id, self.generation_id = origin_id, generation_id
        self.expected_database, self.expected_role = expected_database, expected_role

    def _validate(self, records, *, max_bytes=4 * 1024 * 1024):
        validate_outbox_stream(records, origin_id=self.origin_id,
                               generation_id=self.generation_id)
        if len(encoded(records)) > max_bytes:
            raise ArchiveLimit('private structured batch exceeds byte bound')

    @staticmethod
    def _limit(connection, timeout_seconds):
        if (isinstance(timeout_seconds, bool) or
                not isinstance(timeout_seconds, (int, float)) or
                not 0 < timeout_seconds <= 60):
            raise ArchiveLimit('invalid private structured deadline')
        milliseconds = max(1, int(timeout_seconds * 1000))
        # PostgreSQL 17 bounds the entire import/readback transaction, not
        # merely each statement. Unsupported servers fail closed here.
        connection.execute("SELECT set_config('transaction_timeout',%s,true)",
                           (f'{milliseconds}ms',))
        connection.execute("SELECT set_config('statement_timeout',%s,true)",
                           (f'{milliseconds}ms',))
        connection.execute("SELECT set_config('lock_timeout',%s,true)",
                           (f'{min(milliseconds, 1000)}ms',))

    @staticmethod
    def _deadline(timeout_seconds):
        if (isinstance(timeout_seconds, bool) or
                not isinstance(timeout_seconds, (int, float)) or
                not 0 < timeout_seconds <= 60):
            raise ArchiveLimit('invalid private structured deadline')
        return time.monotonic() + timeout_seconds

    def _identity(self, connection):
        actual = connection.execute('SELECT current_database() AS database, current_user AS role').fetchone()
        if (actual['database'] != self.expected_database or
                actual['role'] != self.expected_role):
            raise ArchiveIntegrityError('private structured database identity mismatch')

    @staticmethod
    def _entity_lock(connection, record):
        connection.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',
                           ('history-v2:' + record['origin_id'] + ':' +
                            record['entity_type'] + ':' + record['entity_id'],))

    @staticmethod
    def _table_and_condition(record):
        table = sql.Identifier('history_v2', record['entity_type'].split('.')[1])
        keys = TABLE_KEYS[record['entity_type']]
        condition = sql.SQL(' AND ').join(
            sql.SQL('{}=%s').format(sql.Identifier(key)) for key in keys)
        values = [record['payload'][key] for key in keys]
        return table, condition, values

    @staticmethod
    def _receipt_hashes(record):
        return sha256(encoded(record['payload'])), sha256(encoded(record))

    def _receipt(self, connection, record):
        return connection.execute('''SELECT entity_type,entity_id,content_hash,
            payload_hash,envelope_hash FROM history_v2.structured_receipts
            WHERE origin_id=%s AND generation_id=%s AND outbox_id=%s''',
            (self.origin_id, self.generation_id, record['id'])).fetchone()

    @staticmethod
    def _check_receipt(receipt, record):
        payload_hash, envelope_hash = HistoryV2PostgresTransport._receipt_hashes(record)
        if (receipt['entity_type'] != record['entity_type'] or
                receipt['entity_id'] != record['entity_id'] or
                receipt['content_hash'] != record['content_hash'] or
                receipt['payload_hash'] != payload_hash or
                receipt['envelope_hash'] != envelope_hash):
            raise ArchiveIntegrityError('private structured receipt conflict')

    @staticmethod
    def _insert_or_update(connection, record):
        row = cloud_row(record)
        table, condition, keys = HistoryV2PostgresTransport._table_and_condition(record)
        # The entity advisory lock serializes immutable inserts and replays
        # across generations. Only mutable projections need a row lock; the
        # private importer has no UPDATE privilege on immutable tables.
        row_lock = (sql.SQL(' FOR UPDATE') if record['entity_type'] in MUTABLE_PROJECTIONS
                    else sql.SQL(''))
        existing = connection.execute(
            sql.SQL('SELECT * FROM {} WHERE {}{}').format(table, condition, row_lock),
            keys).fetchone()
        if existing is not None:
            if record['entity_type'] not in MUTABLE_PROJECTIONS:
                if not cloud_row_matches(record, wire(existing)):
                    raise ArchiveIntegrityError('private immutable structured conflict')
                return
            previous = {'entity_type': record['entity_type'],
                        'entity_id': record['entity_id'],
                        'origin_id': record['origin_id'],
                        'content_hash': existing['content_hash'],
                        'payload': wire(existing)}
            order = projection_order(previous, record)
            if order == 'identical':
                if not cloud_row_matches(record, wire(existing)):
                    raise ArchiveIntegrityError('private mutable structured conflict')
                return
        columns = tuple(CLOUD_COLUMNS[record['entity_type']])
        values = [Jsonb(row[name]) if isinstance(row[name], (dict, list))
                  else row[name] for name in columns]
        if existing is None:
            statement = sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(
                table, sql.SQL(',').join(map(sql.Identifier, columns)),
                sql.SQL(',').join(sql.Placeholder() for _ in columns))
        else:
            statement = sql.SQL('UPDATE {} SET {} WHERE {}').format(
                table,
                sql.SQL(',').join(sql.SQL('{}=%s').format(sql.Identifier(name))
                                  for name in columns), condition)
            values += keys
        connection.execute(statement, values)

    def put_structured(self, records: list[dict], *, timeout_seconds: float) -> None:
        self._validate(records)
        deadline = self._deadline(timeout_seconds)
        try:
            with self.connection_factory(timeout_seconds=timeout_seconds) as connection:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ArchiveLimit('private structured connection deadline reached')
                with connection.transaction():
                    self._limit(connection, remaining)
                    self._identity(connection)
                    connection.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',
                        ('history-v2:stream:' + self.origin_id,))
                    checkpoint = connection.execute('''SELECT cursor,row_count FROM
                        history_v2.generation_checkpoints WHERE origin_id=%s AND
                        generation_id=%s AND dataset='structured:outbox' FOR UPDATE''',
                        (self.origin_id, self.generation_id)).fetchone()
                    previous_id = (checkpoint['cursor'].get('outbox_id', 0)
                                   if checkpoint else 0)
                    inserted = 0
                    # Outbox IDs reflect concurrent local transactions, not
                    # a guaranteed FK topological order. Preserve revision
                    # order within each table while importing parents first.
                    for record in sorted(records, key=lambda item:
                                         (IMPORT_ORDER.index(item['entity_type']), item['id'])):
                        self._entity_lock(connection, record)
                        receipt = self._receipt(connection, record)
                        if receipt is not None:
                            if checkpoint is None or record['id'] > previous_id:
                                raise ArchiveIntegrityError('private receipt beyond checkpoint')
                            self._check_receipt(receipt, record)
                            continue
                        if record['id'] <= previous_id:
                            raise ArchiveIntegrityError('private structured checkpoint gap')
                        self._insert_or_update(connection, record)
                        payload_hash, envelope_hash = self._receipt_hashes(record)
                        connection.execute('''INSERT INTO history_v2.structured_receipts
                            (origin_id,generation_id,outbox_id,entity_type,entity_id,
                             content_hash,payload_hash,envelope_hash)
                            VALUES(%s,%s,%s,%s,%s,%s,%s,%s)''',
                            (self.origin_id, self.generation_id, record['id'],
                             record['entity_type'], record['entity_id'],
                             record['content_hash'], payload_hash, envelope_hash))
                        inserted += 1
                    last_id = records[-1]['id']
                    cursor = {'outbox_id': max(last_id, previous_id)}
                    digest = sha256(encoded(cursor))
                    connection.execute('''INSERT INTO history_v2.generation_checkpoints
                        (origin_id,generation_id,dataset,cursor,row_count,
                         content_hash,acknowledged_at)
                        VALUES(%s,%s,'structured:outbox',%s,%s,%s,%s)
                        ON CONFLICT(origin_id,generation_id,dataset)
                        DO UPDATE SET cursor=EXCLUDED.cursor,row_count=EXCLUDED.row_count,
                            content_hash=EXCLUDED.content_hash,
                            acknowledged_at=EXCLUDED.acknowledged_at''',
                        (self.origin_id, self.generation_id, Jsonb(cursor),
                         (checkpoint['row_count'] if checkpoint else 0) + inserted,
                         digest, datetime.now(timezone.utc)))
            if time.monotonic() >= deadline:
                raise ArchiveLimit('private structured import deadline reached')
        except (ArchiveIntegrityError, ArchiveLimit):
            raise
        except Exception:
            raise ArchiveUnavailable('private structured import unavailable') from None

    def read_structured_authenticated(self, records: list[dict], *, max_bytes: int,
                                      timeout_seconds: float) -> list[dict]:
        if not isinstance(max_bytes, int) or not 0 < max_bytes <= 16 * 1024 * 1024:
            raise ArchiveLimit('invalid private structured read bound')
        self._validate(records, max_bytes=max_bytes)
        deadline = self._deadline(timeout_seconds)
        try:
            with self.connection_factory(timeout_seconds=timeout_seconds) as connection:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ArchiveLimit('private structured connection deadline reached')
                with connection.transaction():
                    self._limit(connection, remaining)
                    self._identity(connection)
                    checkpoint = connection.execute('''SELECT cursor,content_hash FROM
                        history_v2.generation_checkpoints WHERE origin_id=%s AND
                        generation_id=%s AND dataset='structured:outbox' ''',
                        (self.origin_id, self.generation_id)).fetchone()
                    if (not checkpoint or checkpoint['cursor'].get('outbox_id', 0) < records[-1]['id'] or
                            checkpoint['content_hash'] != sha256(encoded(checkpoint['cursor']))):
                        raise ArchiveIntegrityError('private structured checkpoint mismatch')
                    final = {}
                    for record in records:
                        receipt = connection.execute('''SELECT entity_type,entity_id,
                            content_hash,payload_hash,envelope_hash FROM
                            history_v2.structured_receipts WHERE origin_id=%s AND
                            generation_id=%s AND outbox_id=%s''',
                            (self.origin_id, self.generation_id, record['id'])).fetchone()
                        if receipt is None:
                            raise ArchiveIntegrityError('private structured receipt missing')
                        self._check_receipt(receipt, record)
                        final[(record['entity_type'], record['entity_id'])] = record
                    for record in final.values():
                        table, condition, keys = self._table_and_condition(record)
                        row = connection.execute(
                            sql.SQL('SELECT * FROM {} WHERE {}').format(table, condition),
                            keys).fetchone()
                        if row is None:
                            raise ArchiveIntegrityError('private structured projection missing')
                        if not cloud_row_matches(record, wire(row)):
                            # A newer-looking mutable row is not proof it was
                            # imported through this receipt stream. Do not
                            # acknowledge local evidence without an exact
                            # fresh projection match.
                            raise ArchiveIntegrityError('private structured projection changed')
            if time.monotonic() >= deadline:
                raise ArchiveLimit('private structured readback deadline reached')
            return records
        except (ArchiveIntegrityError, ArchiveLimit):
            raise
        except Exception:
            raise ArchiveUnavailable('private structured readback unavailable') from None
