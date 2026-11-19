"""Default-off direct PostgreSQL importer for private structured history.

The caller supplies a narrowly scoped connection factory. No service creates
this adapter yet; PP-only grants do not enable runtime sync. Each cloud transaction
applies ordered revisions and immutable receipts together; a separate read
verifies those receipts before the local worker may acknowledge its outbox.
"""
from __future__ import annotations

from datetime import datetime, timezone
import time
import json

from psycopg import sql
from psycopg.types.json import Jsonb

from .retirement_accounting import measured_context, phase
from .archive_codec import (ArchiveIntegrityError, ArchiveLimit,
                            ArchiveUnavailable, encoded, sha256, wire)
from .history_v2_envelope import (CLOUD_COLUMNS, IMPORT_ORDER, MUTABLE_PROJECTIONS,
                                  TABLE_KEYS, cloud_row, cloud_row_matches,
                                  projection_order, validate_outbox_stream)

from .cloud_origin_binding import cloud_binding, TRIAL_ORIGIN

PP_STRUCTURED_ORIGIN = 'pp-live-pp'


class HistoryV2PostgresTransport:
    authority_scope = 'supabase-unqualified'

    def __init__(self, connection_factory, *, origin_id: str,
                 generation_id: str, expected_database: str,
                 expected_role: str, retain_revisions: bool = False,
                 indexed_latest: bool = False, sync_barriers: bool = False):
        binding = cloud_binding(origin_id) if origin_id == TRIAL_ORIGIN else None
        if (not callable(connection_factory) or origin_id not in (PP_STRUCTURED_ORIGIN, TRIAL_ORIGIN) or
                (origin_id == TRIAL_ORIGIN and (expected_database != 'postgres' or
                 expected_role not in (binding.writer_role, binding.reader_role))) or
                not generation_id or
                not expected_database or not expected_role):
            raise ValueError('private structured importer binding required')
        if type(retain_revisions) is not bool:
            raise ValueError('boolean revision-retention selection required')
        if type(indexed_latest) is not bool:
            raise ArchiveIntegrityError('boolean PP latest receipt opt-in required')
        if type(sync_barriers) is not bool or (sync_barriers and origin_id != TRIAL_ORIGIN):
            raise ArchiveIntegrityError('synchronized batches require exact trial opt-in')
        self.sync_barriers=sync_barriers
        self._read_only = origin_id == TRIAL_ORIGIN and expected_role == binding.reader_role
        self.indexed_latest = indexed_latest
        self.retain_revisions = retain_revisions
        self.connection_factory = connection_factory
        self.origin_id, self.generation_id = origin_id, generation_id
        self.expected_database, self.expected_role = expected_database, expected_role

    def _validate(self, records, *, max_bytes=4 * 1024 * 1024):
        validate_outbox_stream(records, origin_id=self.origin_id,
                               generation_id=self.generation_id)
        canonical = encoded(records)
        if len(canonical) > max_bytes:
            raise ArchiveLimit('private structured batch exceeds byte bound')
        return canonical

    @staticmethod
    def _limit(connection, timeout_seconds, *, catalog_search_path=False):
        if (isinstance(timeout_seconds, bool) or
                not isinstance(timeout_seconds, (int, float)) or
                not 0 < timeout_seconds <= 60):
            raise ArchiveLimit('invalid private structured deadline')
        milliseconds = max(1, int(timeout_seconds * 1000))
        # PostgreSQL 17 bounds the entire import/readback transaction, not
        # merely each statement. Unsupported servers fail closed here.
        setting = ",set_config('search_path','pg_catalog',true)" if catalog_search_path else ''
        connection.execute("""SELECT set_config('transaction_timeout',%s,true),
            set_config('statement_timeout',%s,true), set_config('lock_timeout',%s,true)"""+setting,
            (f'{milliseconds}ms', f'{milliseconds}ms', f'{min(milliseconds, 1000)}ms'))

    @staticmethod
    def _deadline(timeout_seconds):
        if (isinstance(timeout_seconds, bool) or
                not isinstance(timeout_seconds, (int, float)) or
                not 0 < timeout_seconds <= 60):
            raise ArchiveLimit('invalid private structured deadline')
        return time.monotonic() + timeout_seconds

    def _identity(self, connection):
        actual = connection.execute('SELECT current_database() AS database, current_user AS role').fetchone()
        self._check_identity(actual)

    def _check_identity(self,actual):
        if (actual['database'] != self.expected_database or
                actual['role'] != self.expected_role):
            raise ArchiveIntegrityError('private structured database identity mismatch')

    @staticmethod
    def _entity_locks(connection, records):
        # One ordered acquisition prevents both per-row RTTs and lock-order
        # inversions. The per-origin stream lock still serializes importers.
        keys = sorted({'history-v2:' + row['origin_id'] + ':' +
                       row['entity_type'] + ':' + row['entity_id'] for row in records})
        connection.execute("""SELECT pg_advisory_xact_lock(hashtextextended(key,0))
            FROM unnest(%s::text[]) AS locks(key) ORDER BY key""", (keys,))

    @staticmethod
    def _projection_rows(connection, records, *, for_update=False):
        # Queue distinct entity reads before waiting for any result. No write
        # decision is made until the entire read phase has synchronized.
        with connection.pipeline():
            cursors=HistoryV2PostgresTransport._projection_cursors(connection,records,for_update=for_update)
        return {key:cursor.fetchone() for key,cursor in cursors.items()}

    @staticmethod
    def _projection_cursors(connection,records,*,for_update=False):
        cursors={}
        for record in records:
            key=(record['entity_type'],record['entity_id'])
            if key in cursors:continue
            table,condition,values=HistoryV2PostgresTransport._table_and_condition(record)
            lock=sql.SQL(' FOR UPDATE') if for_update and record['entity_type'] in MUTABLE_PROJECTIONS else sql.SQL('')
            cursors[key]=connection.execute(sql.SQL('SELECT * FROM {} WHERE {}{}').format(table,condition,lock),values)
        return cursors

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

    def _receipts(self, connection, records):
        """Read the exact page's receipts in one bounded remote round trip."""
        return self._checked_receipts(self._receipt_cursor(connection,records).fetchall(),records)

    def _receipt_cursor(self,connection,records):
        return connection.execute('''SELECT outbox_id,entity_type,entity_id,
            content_hash,payload_hash,envelope_hash FROM history_v2.structured_receipts
            WHERE origin_id=%s AND generation_id=%s AND outbox_id=ANY(%s::bigint[])''',
            (self.origin_id, self.generation_id,
             [record['id'] for record in records]))

    @staticmethod
    def _checked_receipts(rows,records):
        receipts = {row['outbox_id']: row for row in rows}
        if len(receipts) != len(rows) or len(receipts) > len(records):
            raise ArchiveIntegrityError('private structured receipt set invalid')
        return receipts

    @staticmethod
    def _insert_receipts(connection, rows):
        # Projection writes precede receipts in the same atomic transaction.
        # One bounded VALUES statement replaces one network round trip per row.
        for offset in range(0, len(rows), 25):
            page = rows[offset:offset + 25]
            placeholders = sql.SQL(',').join(
                sql.SQL('(%s,%s,%s,%s,%s,%s,%s,%s)') for _ in page)
            statement = sql.SQL('''INSERT INTO history_v2.structured_receipts
                (origin_id,generation_id,outbox_id,entity_type,entity_id,
                 content_hash,payload_hash,envelope_hash) VALUES {}''').format(placeholders)
            connection.execute(statement, [value for row in page for value in row])

    def _append_revisions(self, connection, records):
        # Handle replay/backfill with the same receipt verification and a
        # byte-exact conflict check. Only the reviewed PP role may append.
        for start in range(0,len(records),25):
            page=records[start:start+25]
            values=[(self.origin_id,self.generation_id,r['id'],encoded(r)) for r in page]
            placeholders=sql.SQL(',').join(sql.SQL('(%s,%s,%s,%s)') for _ in values)
            connection.execute(sql.SQL("""INSERT INTO history_v2.structured_revision_payloads
                (origin_id,generation_id,outbox_id,envelope) VALUES {}
                ON CONFLICT (origin_id,generation_id,outbox_id) DO NOTHING""").format(placeholders),
                [v for row in values for v in row])
            actual=self._read_revisions(connection,[r['id'] for r in page],sum(len(v[3]) for v in values))
            if encoded(actual) != encoded(page):
                raise ArchiveIntegrityError('stored historical envelope conflicts')

    def _read_revisions(self, connection, ids, max_bytes, *, generation_id=None,
                        _canonical_envelopes=None):
        generation_id = generation_id or self.generation_id
        rows=self._revision_cursor(connection,ids,max_bytes,generation_id=generation_id).fetchall()
        return self._decode_revisions(rows,ids,max_bytes,generation_id=generation_id,
                                      _canonical_envelopes=_canonical_envelopes)

    def _revision_cursor(self,connection,ids,max_bytes,*,generation_id=None):
        generation_id=generation_id or self.generation_id
        # Materialize only the requested identities once. The previous plan
        # could rescan a generation for every row through the window/rejoins.
        # Keep the byte/metadata limits in the same snapshot and suppress all
        # variable-width output when either aggregate is too large.
        return connection.execute("""WITH selected AS MATERIALIZED (
                SELECT p.outbox_id,p.envelope,r.entity_type,r.entity_id,
                       r.content_hash,r.payload_hash,r.envelope_hash
                FROM history_v2.structured_revision_payloads p
                JOIN history_v2.structured_receipts r ON
                    (r.origin_id,r.generation_id,r.outbox_id)=
                    (p.origin_id,p.generation_id,p.outbox_id)
                WHERE p.origin_id=%s AND p.generation_id=%s AND p.outbox_id=ANY(%s::bigint[])
                  AND r.origin_id=%s AND r.generation_id=%s AND r.outbox_id=ANY(%s::bigint[])),
            sizes AS (
                SELECT *,sum(octet_length(envelope)) OVER () AS total,
                    sum(coalesce(octet_length(entity_type),0)
                      + coalesce(octet_length(entity_id),0)
                      + coalesce(octet_length(content_hash),0)
                      + coalesce(octet_length(payload_hash),0)
                      + coalesce(octet_length(envelope_hash),0)) OVER () AS metadata_total
                FROM selected),
            bounded AS (SELECT *,total<=%s AND metadata_total<=%s AS fits FROM sizes)
            SELECT outbox_id,total,metadata_total,
                   CASE WHEN fits THEN envelope END AS envelope,
                   CASE WHEN fits THEN entity_type END AS entity_type,
                   CASE WHEN fits THEN entity_id END AS entity_id,
                   CASE WHEN fits THEN content_hash END AS content_hash,
                   CASE WHEN fits THEN payload_hash END AS payload_hash,
                   CASE WHEN fits THEN envelope_hash END AS envelope_hash
            FROM bounded ORDER BY outbox_id""",
            (self.origin_id,generation_id,ids,self.origin_id,generation_id,ids,max_bytes,max_bytes))

    def _decode_revisions(self,rows,ids,max_bytes,*,generation_id=None,_canonical_envelopes=None):
        generation_id=generation_id or self.generation_id
        if [r['outbox_id'] for r in rows] != ids:
            raise ArchiveIntegrityError('historical revision or receipt missing')
        records=[]
        for row in rows:
            if (row['total']>max_bytes or row['metadata_total']>max_bytes
                    or row['envelope'] is None):
                raise ArchiveLimit('stored revision batch exceeds read bound')
            raw=bytes(row['envelope'])
            try:
                record=json.loads(raw)
            except (ValueError,UnicodeError):
                raise ArchiveIntegrityError('stored revision encoding invalid') from None
            if (not isinstance(record,dict) or record.get('id')!=row['outbox_id'] or
                    encoded(record)!=raw):
                raise ArchiveIntegrityError('stored revision not canonical')
            validate_outbox_stream([record],origin_id=self.origin_id,generation_id=generation_id)
            # raw has already passed exact canonical re-encoding above. Hash
            # those same authenticated bytes instead of serializing them again.
            self._check_receipt_hashes(row,record,
                sha256(encoded(record['payload'])),sha256(raw))
            records.append(record)
            if _canonical_envelopes is not None:
                _canonical_envelopes.append(raw)
        return records

    def backfill_verified_revisions(self, records, *, timeout_seconds):
        """Insert original bytes for independently matched existing receipts only."""
        if not self.retain_revisions:
            raise ArchiveIntegrityError('historical revision backfill disabled')
        self._validate(records)
        deadline=self._deadline(timeout_seconds)
        try:
            with self.connection_factory(timeout_seconds=timeout_seconds) as connection:
                remaining=deadline-time.monotonic()
                if remaining<=0:
                    raise ArchiveLimit('historical revision backfill deadline reached')
                with connection.transaction():
                    self._limit(connection,remaining)
                    self._identity(connection)
                    receipts=self._receipts(connection,records)
                    for record in records:
                        receipt=receipts.get(record['id'])
                        if receipt is None:
                            raise ArchiveIntegrityError('existing receipt required for backfill')
                        self._check_receipt(receipt,record)
                    self._append_revisions(connection,records)
            if time.monotonic()>=deadline:
                raise ArchiveLimit('historical revision backfill deadline reached')
        except (ArchiveIntegrityError,ArchiveLimit):
            raise
        except Exception:
            raise ArchiveUnavailable('historical revision backfill unavailable') from None

    def read_revisions(self, ids, *, max_bytes, timeout_seconds):
        """Recover prior PP revisions directly from private history by exact IDs."""
        if (not isinstance(ids,list) or not 1<=len(ids)<=500 or
                any(type(x) is not int or not 0<x<2**63 for x in ids) or ids!=sorted(set(ids)) or
                type(max_bytes) is not int or not 1<=max_bytes<=4*1024**2):
            raise ArchiveLimit('invalid historical revision read bound')
        deadline=self._deadline(timeout_seconds)
        try:
            with self.connection_factory(timeout_seconds=timeout_seconds) as connection:
                remaining=deadline-time.monotonic()
                if remaining<=0:
                    raise ArchiveLimit('historical revision connection deadline reached')
                with connection.transaction():
                    self._limit(connection,remaining)
                    self._identity(connection)
                    records=self._read_revisions(connection,ids,max_bytes)
            if time.monotonic()>=deadline:
                raise ArchiveLimit('historical revision read deadline reached')
            return records
        except (ArchiveIntegrityError,ArchiveLimit):
            raise
        except Exception:
            raise ArchiveUnavailable('historical revision read unavailable') from None

    def _checkpoint_covers(self, connection, generation_id, last_id, *, verify_latest_index=False):
        columns='cursor,content_hash'
        parameters=(self.origin_id,generation_id)
        if verify_latest_index:
            from .history_v2_latest_receipts import ABI_SQL,INDEX_NAME
            columns+=',('+ABI_SQL+') AS latest_index_valid'
            parameters=(INDEX_NAME,*parameters)
        row = connection.execute(
            'SELECT '+columns+""" FROM history_v2.generation_checkpoints
               WHERE origin_id=%s AND generation_id=%s AND dataset='structured:outbox'""",
            parameters).fetchone()
        if (not row or type(row['cursor'].get('outbox_id')) is not int or
                row['cursor']['outbox_id'] < last_id or
                row['content_hash'] != sha256(encoded(row['cursor']))):
            raise ArchiveIntegrityError('private structured checkpoint mismatch')
        if verify_latest_index:
            from .history_v2_latest_receipts import checked_index
            return checked_index(connection,row['latest_index_valid'])

    def read_retirement_revisions(self, records, *, max_bytes, timeout_seconds):
        """Read the exact historical inputs and authenticate their current projections."""
        expected = self._validate(records, max_bytes=max_bytes)
        deadline = self._deadline(timeout_seconds)
        try:
            with measured_context(self.connection_factory(timeout_seconds=timeout_seconds),
                                  enter='history_checkout', finish='history_release') as connection:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ArchiveLimit('retirement readback deadline reached')
                with phase('history_transaction'), connection.transaction():
                    # B is free to advance. All receipt, envelope, cursor and
                    # projection reads on this connection use the same snapshot.
                    with phase('history_identity_checkpoint'):
                        connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                        self._limit(connection, remaining,catalog_search_path=self.indexed_latest)
                        self._identity(connection)
                        checked=self._checkpoint_covers(connection, self.generation_id, records[-1]['id'],
                            verify_latest_index=self.indexed_latest)
                    with phase('history_exact_revisions'):
                        canonical_envelopes = []
                        archived = self._read_revisions(connection, [r['id'] for r in records], max_bytes,
                            _canonical_envelopes=canonical_envelopes)
                        # Every element is the exact canonical byte sequence
                        # already checked by _read_revisions, in checked ID order.
                        # Joining them is exactly the canonical JSON array used
                        # before; keep byte equality, rather than hash equality.
                        canonical = b'[' + b','.join(canonical_envelopes) + b']'
                        if canonical != expected:
                            raise ArchiveIntegrityError('historical retirement revision mismatch')
                    size = len(canonical)
                    # Do not retain the temporary byte copies while the wider
                    # latest-receipt and projection reads are in flight.
                    del canonical_envelopes, canonical, expected
                    final = {(r['entity_type'], r['entity_id']): r for r in archived}
                    with phase('history_latest_receipts'):
                        from .history_v2_latest_receipts import latest_receipts
                        receipts = latest_receipts(connection,self.origin_id,list(final),
                            indexed=self.indexed_latest,_checked=checked)
                    if len(receipts) != len(final):
                        raise ArchiveIntegrityError('latest projection receipt missing')
                    changed = {}
                    for receipt in receipts:
                        key = (receipt['entity_type'], receipt['entity_id'])
                        gen, index = str(receipt['generation_id']), receipt['outbox_id']
                        prior = final[key]
                        if index == prior['id'] and gen == self.generation_id:
                            continue
                        if index <= prior['id']:
                            raise ArchiveIntegrityError('conflicting latest revision identity')
                        changed.setdefault(gen, {})[index] = key
                    with phase('history_newer_revisions'):
                        for gen, by_id in changed.items():
                            ids = sorted(by_id)
                            self._checkpoint_covers(connection, gen, ids[-1])
                            current = self._read_revisions(connection, ids, max_bytes-size,
                                                           generation_id=gen)
                            for r in current:
                                key = by_id[r['id']]
                                if (r['entity_type'], r['entity_id']) != key:
                                    raise ArchiveIntegrityError('latest revision identity mismatch')
                                if r['entity_type'] in MUTABLE_PROJECTIONS:
                                    projection_order(final[key], r)
                                elif encoded(r['payload']) != encoded(final[key]['payload']):
                                    raise ArchiveIntegrityError('immutable historical entity changed')
                                size += len(encoded(r))
                                final[key] = r
                    with phase('history_projections'):
                        projections = self._projection_rows(connection, final.values())
                        for key, r in final.items():
                            if not cloud_row_matches(r, wire(projections[key])):
                                raise ArchiveIntegrityError('current projection lacks matching revision')
            if time.monotonic() >= deadline:
                raise ArchiveLimit('retirement readback deadline reached')
            return archived, size
        except (ArchiveIntegrityError, ArchiveLimit):
            raise
        except Exception:
            raise ArchiveUnavailable('historical retirement readback unavailable') from None

    @staticmethod
    def _check_receipt(receipt, record):
        payload_hash, envelope_hash = HistoryV2PostgresTransport._receipt_hashes(record)
        HistoryV2PostgresTransport._check_receipt_hashes(receipt,record,payload_hash,envelope_hash)

    @staticmethod
    def _check_receipt_hashes(receipt, record, payload_hash, envelope_hash):
        if (receipt['entity_type'] != record['entity_type'] or
                receipt['entity_id'] != record['entity_id'] or
                receipt['content_hash'] != record['content_hash'] or
                receipt['payload_hash'] != payload_hash or
                receipt['envelope_hash'] != envelope_hash):
            raise ArchiveIntegrityError('private structured receipt conflict')

    @staticmethod
    def _insert_or_update(connection, record, existing):
        row = cloud_row(record)
        table, condition, keys = HistoryV2PostgresTransport._table_and_condition(record)
        # The caller holds all entity locks and advances a checked in-memory
        # projection after each queued revision, including duplicate entity IDs.
        if existing is not None:
            if record['entity_type'] not in MUTABLE_PROJECTIONS:
                if not cloud_row_matches(record, wire(existing)):
                    raise ArchiveIntegrityError('private immutable structured conflict')
                return existing
            previous = {'entity_type': record['entity_type'],
                        'entity_id': record['entity_id'],
                        'origin_id': record['origin_id'],
                        'content_hash': existing['content_hash'],
                        'payload': wire(existing)}
            order = projection_order(previous, record)
            if order == 'identical':
                if not cloud_row_matches(record, wire(existing)):
                    raise ArchiveIntegrityError('private mutable structured conflict')
                return existing
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
        return row

    def _upsert_checkpoint(self,connection,cursor,row_count,digest):
        connection.execute('''INSERT INTO history_v2.generation_checkpoints
                        (origin_id,generation_id,dataset,cursor,row_count,
                         content_hash,acknowledged_at)
                        VALUES(%s,%s,'structured:outbox',%s,%s,%s,%s)
                        ON CONFLICT(origin_id,generation_id,dataset)
                        DO UPDATE SET cursor=EXCLUDED.cursor,row_count=EXCLUDED.row_count,
                            content_hash=EXCLUDED.content_hash,
                            acknowledged_at=EXCLUDED.acknowledged_at''',
                        (self.origin_id, self.generation_id, Jsonb(cursor),
                         row_count,
                         digest, datetime.now(timezone.utc)))

    def _read_batch(self,connection,records,max_bytes,remaining):
        # Identity is still verified before any scoped data SELECT. Independent
        # bounded reads share a synchronization; every result is checked before
        # return/ACK. No transaction or snapshot is cached across operations.
        with connection.pipeline():
            self._limit(connection,remaining)
            identity=connection.execute('SELECT current_database() AS database, current_user AS role')
        self._check_identity(identity.fetchone())
        final={(record['entity_type'],record['entity_id']):record for record in records}
        with connection.pipeline():
            checkpoint=connection.execute("""SELECT cursor,content_hash FROM history_v2.generation_checkpoints
                WHERE origin_id=%s AND generation_id=%s AND dataset='structured:outbox' """,
                (self.origin_id,self.generation_id))
            receipts=self._receipt_cursor(connection,records)
            revisions=self._revision_cursor(connection,[r['id'] for r in records],max_bytes) if self.retain_revisions else None
            projections=self._projection_cursors(connection,final.values())
        checkpoint=checkpoint.fetchone()
        if (not checkpoint or checkpoint['cursor'].get('outbox_id',0)<records[-1]['id']
                or checkpoint['content_hash']!=sha256(encoded(checkpoint['cursor']))):
            raise ArchiveIntegrityError('private structured checkpoint mismatch')
        receipts=self._checked_receipts(receipts.fetchall(),records)
        for record in records:
            receipt=receipts.get(record['id'])
            if receipt is None:raise ArchiveIntegrityError('private structured receipt missing')
            self._check_receipt(receipt,record)
        if revisions is not None:
            recovered=self._decode_revisions(revisions.fetchall(),[r['id'] for r in records],max_bytes)
            if encoded(recovered)!=encoded(records):
                raise ArchiveIntegrityError('private structured revision readback mismatch')
        for key,record in final.items():
            row=projections[key].fetchone()
            if row is None:raise ArchiveIntegrityError('private structured projection missing')
            if not cloud_row_matches(record,wire(row)):
                raise ArchiveIntegrityError('private structured projection changed')

    def _append_revision_commands(self,connection,records):
        # Preserve the existing maximum 25-row physical INSERT statements.
        for start in range(0,len(records),25):
            page=records[start:start+25]
            values=[(self.origin_id,self.generation_id,r['id'],encoded(r)) for r in page]
            placeholders=sql.SQL(',').join(sql.SQL('(%s,%s,%s,%s)') for _ in values)
            connection.execute(sql.SQL("""INSERT INTO history_v2.structured_revision_payloads
                (origin_id,generation_id,outbox_id,envelope) VALUES {}
                ON CONFLICT (origin_id,generation_id,outbox_id) DO NOTHING""").format(placeholders),
                [v for row in values for v in row])

    def put_structured(self, records: list[dict], *, timeout_seconds: float) -> None:
        if self.sync_barriers and len(records)>50:
            raise ArchiveLimit('trial synchronized batch exceeds fifty rows')
        if self._read_only:
            raise ArchiveIntegrityError('trial structured reader has no append operation')
        self._validate(records,max_bytes=256*1024 if self.sync_barriers else 4*1024*1024)
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
                    receipts = self._receipts(connection, records)
                    new_receipts = []
                    ordered = sorted(records, key=lambda item:
                        (IMPORT_ORDER.index(item['entity_type']), item['id']))
                    self._entity_locks(connection, ordered)
                    projections = self._projection_rows(connection, ordered, for_update=True)
                    # Synchronize writes once, in FK order. Client checks still
                    # run sequentially; repeated mutable keys see their prior
                    # proposed revision, never the stale initial snapshot.
                    with connection.pipeline():
                        for record in ordered:
                            receipt = receipts.get(record['id'])
                            if receipt is not None:
                                if checkpoint is None or record['id'] > previous_id:
                                    raise ArchiveIntegrityError('private receipt beyond checkpoint')
                                self._check_receipt(receipt, record)
                                continue
                            if record['id'] <= previous_id:
                                raise ArchiveIntegrityError('private structured checkpoint gap')
                            key = (record['entity_type'], record['entity_id'])
                            projections[key] = self._insert_or_update(connection, record, projections[key])
                            payload_hash, envelope_hash = self._receipt_hashes(record)
                            new_receipts.append((self.origin_id, self.generation_id,
                                record['id'], record['entity_type'], record['entity_id'],
                                record['content_hash'], payload_hash, envelope_hash))
                            inserted += 1
                    last_id=records[-1]['id']
                    cursor={'outbox_id':max(last_id,previous_id)}
                    digest=sha256(encoded(cursor))
                    row_count=(checkpoint['row_count'] if checkpoint else 0)+inserted
                    if self.sync_barriers:
                        size=sum(len(encoded(r)) for r in records)
                        with connection.pipeline():
                            self._insert_receipts(connection,new_receipts)
                            if self.retain_revisions:
                                self._append_revision_commands(connection,records)
                                revisions=self._revision_cursor(connection,[r['id'] for r in records],size)
                            self._upsert_checkpoint(connection,cursor,row_count,digest)
                        if self.retain_revisions:
                            actual=self._decode_revisions(revisions.fetchall(),[r['id'] for r in records],size)
                            if encoded(actual)!=encoded(records):
                                raise ArchiveIntegrityError('stored historical envelope conflicts')
                    else:
                        self._insert_receipts(connection,new_receipts)
                        if self.retain_revisions:self._append_revisions(connection,records)
                        self._upsert_checkpoint(connection,cursor,row_count,digest)
            if time.monotonic() >= deadline:
                raise ArchiveLimit('private structured import deadline reached')
        except (ArchiveIntegrityError, ArchiveLimit):
            raise
        except Exception:
            raise ArchiveUnavailable('private structured import unavailable') from None

    def read_structured_authenticated(self, records: list[dict], *, max_bytes: int,
                                      timeout_seconds: float) -> list[dict]:
        if self.sync_barriers and (len(records)>50 or max_bytes>256*1024):
            raise ArchiveLimit('trial synchronized read exceeds reviewed bounds')
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
                    if self.sync_barriers:
                        self._read_batch(connection,records,max_bytes,remaining)
                    else:
                        self._limit(connection, remaining)
                        self._identity(connection)
                        checkpoint = connection.execute('''SELECT cursor,content_hash FROM
                            history_v2.generation_checkpoints WHERE origin_id=%s AND
                            generation_id=%s AND dataset='structured:outbox' ''',
                            (self.origin_id, self.generation_id)).fetchone()
                        if (not checkpoint or checkpoint['cursor'].get('outbox_id', 0) < records[-1]['id'] or
                                checkpoint['content_hash'] != sha256(encoded(checkpoint['cursor']))):
                            raise ArchiveIntegrityError('private structured checkpoint mismatch')
                        receipts = self._receipts(connection, records)
                        final = {}
                        for record in records:
                            receipt = receipts.get(record['id'])
                            if receipt is None:
                                raise ArchiveIntegrityError('private structured receipt missing')
                            self._check_receipt(receipt, record)
                            final[(record['entity_type'], record['entity_id'])] = record
                        if self.retain_revisions:
                            revisions = self._read_revisions(connection,
                                [record['id'] for record in records], max_bytes)
                            if encoded(revisions) != encoded(records):
                                raise ArchiveIntegrityError('private structured revision readback mismatch')
                        projections = self._projection_rows(connection, final.values())
                        for record in final.values():
                            row = projections[(record['entity_type'], record['entity_id'])]
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
