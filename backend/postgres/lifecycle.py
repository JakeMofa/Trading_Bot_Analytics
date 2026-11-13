"""PostgreSQL A/B generations, durable archive jobs, and generated retirement.

Runtime cloud mutation authority is unqualified (CP6). This module supplies no
cloud adapter and never enables real retirement. The only destructive method is
explicit isolated generated qualification, backed by a txid-bound SQL gate.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import json
import uuid

from .archive_codec import (ACTIVE_BUDGET, ArchiveError, ArchiveIntegrityError, ArchiveLimit,
                            ArchiveLimits, CycleBudget, encoded, manifest_set_hash,
                            pack_chunk, read_verified, row_cursor, sha256, wire)


class LifecycleHold(ArchiveError):
    code = 'lifecycle_hold'


def utcnow():
    return datetime.now(timezone.utc)


class _DeadlineConnection:
    """Apply the remaining cycle deadline to each SQL operation, not each job."""
    def __init__(self, connection, budget):
        self.connection, self.budget = connection, budget

    def execute(self, query, parameters=None):
        self.budget.check()
        remaining = max(1, int(1000 * (self.budget.deadline - self.budget.clock())))
        self.connection.execute("SELECT set_config('statement_timeout',%s,true)",
                                (str(min(5000, remaining)),))
        result = self.connection.execute(query, parameters)
        self.budget.check()
        return result


@dataclass(frozen=True)
class RotationPolicy:
    """A configured size fixture is not a production capacity qualification."""
    qualified_size_bytes: int | None = None

    def __post_init__(self):
        if self.qualified_size_bytes is not None and self.qualified_size_bytes <= 0:
            raise ValueError('qualified size must be positive')

    def due(self, started_at: datetime, now: datetime, allocated_bytes: int) -> str | None:
        if now.tzinfo is None or started_at.tzinfo is None:
            raise ValueError('rotation times must be timezone-aware')
        if now - started_at >= timedelta(hours=72):
            return 'age_72h'
        if self.qualified_size_bytes is not None and allocated_bytes >= self.qualified_size_bytes:
            return 'qualified_size'
        return None


def validate_manifest_chain(manifests: list[dict], generation: dict):
    after = None
    total = 0
    if not manifests:
        raise LifecycleHold('archive manifest absent')
    for item in manifests:
        coverage = item['coverage']
        if (coverage['origin_id'] != generation['origin_id'] or
                coverage['generation_id'] != generation['generation_id'] or
                coverage['dataset'] != 'raw.events' or coverage['after'] != after):
            raise ArchiveIntegrityError('archive coverage discontinuity')
        if item['row_count'] == 0 and len(manifests) != 1:
            raise ArchiveIntegrityError('empty archive chunk inside generation')
        total += item['row_count']
        after = coverage['last']
    if total != generation['seal_count']:
        raise LifecycleHold('archive coverage incomplete')
    return manifest_set_hash(manifests)


class LifecycleRepository:
    def __init__(self, connection_factory, *, environment='preprod', pending_outbox_limit=10000):
        if not 1 <= pending_outbox_limit <= 100000:
            raise ValueError('pending outbox count bound must be 1..100000')
        self.connection_factory = connection_factory
        self.environment = environment
        self.pending_outbox_limit = pending_outbox_limit

    @contextmanager
    def transaction(self):
        budget = ACTIVE_BUDGET.get()
        # connect() is bounded to five seconds by the common connection contract.
        # Do not begin another connection when that reserve no longer fits.
        if budget and budget.deadline - budget.clock() <= 5:
            raise ArchiveLimit('insufficient cycle time for another database connection')
        with self.connection_factory() as connection:
            with connection.transaction():
                connection.execute("SET LOCAL statement_timeout='5000ms'")
                connection.execute("SET LOCAL lock_timeout='1000ms'")
                yield _DeadlineConnection(connection, budget) if budget else connection
                if budget:
                    budget.check()

    def bootstrap(self, origin_id: str, now: datetime | None = None) -> dict:
        if not origin_id or len(origin_id) > 160:
            raise ValueError('origin_id required and bounded')
        now = now or utcnow()
        with self.transaction() as connection:
            # No writer row exists yet. Serialize only explicit bootstrap.
            connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                               ('tradebot-generation-bootstrap:' + origin_id,))
            writer = connection.execute('SELECT * FROM ops.writer_state WHERE origin_id=%s FOR UPDATE',
                                        (origin_id,)).fetchone()
            if writer:
                return connection.execute('SELECT * FROM archive.generations WHERE generation_id=%s',
                                          (writer['generation_id'],)).fetchone()
            if connection.execute("SELECT 1 FROM archive.generations WHERE origin_id=%s AND state<>'retired' LIMIT 1",
                                  (origin_id,)).fetchone():
                raise LifecycleHold('orphan generation requires explicit forward recovery')
            generation = self._create(connection, origin_id, 'A', now)
            connection.execute("UPDATE archive.generations SET state='collecting',started_at=%s WHERE generation_id=%s",
                               (now, generation['generation_id']))
            connection.execute('''INSERT INTO ops.writer_state
                (origin_id,generation_id,epoch,collector_enabled,updated_at) VALUES(%s,%s,1,false,%s)''',
                               (origin_id, generation['generation_id'], now))
            return connection.execute('SELECT * FROM archive.generations WHERE generation_id=%s',
                                      (generation['generation_id'],)).fetchone()

    @staticmethod
    def _create(connection, origin_id, slot, now):
        generation_id = str(uuid.uuid4())
        partition_name = 'events_g_' + uuid.UUID(generation_id).hex
        connection.execute('''INSERT INTO archive.generations
            (origin_id,generation_id,slot,state,partition_name,created_at)
            VALUES(%s,%s,%s,'prepared',%s,%s)''',
                           (origin_id, generation_id, slot, partition_name, now))
        connection.execute('SELECT archive.create_generation_partition(%s,%s)',
                           (origin_id, generation_id))
        return {'origin_id': origin_id, 'generation_id': generation_id, 'slot': slot}

    def switch_if_due(self, origin_id: str, policy=RotationPolicy(), now=None) -> dict:
        now = now or utcnow()
        with self.transaction() as connection:
            writer = connection.execute('SELECT * FROM ops.writer_state WHERE origin_id=%s FOR UPDATE',
                                        (origin_id,)).fetchone()
            if not writer:
                raise LifecycleHold('writer not bootstrapped')
            count = connection.execute('''SELECT count(*) AS count FROM
                (SELECT 1 FROM archive.generations WHERE origin_id=%s AND state<>'retired' LIMIT 3) g''',
                                       (origin_id,)).fetchone()['count']
            if count > 2:
                raise LifecycleHold('nonretired generation bound exceeded')
            pending = connection.execute('''SELECT count(*) AS count FROM
                (SELECT 1 FROM ops.outbox WHERE origin_id=%s AND acknowledged_at IS NULL LIMIT %s) o''',
                                         (origin_id, self.pending_outbox_limit + 1)).fetchone()['count']
            if pending > self.pending_outbox_limit:
                raise LifecycleHold('pending structured outbox bound exceeded')
            current = connection.execute('SELECT * FROM archive.generations WHERE generation_id=%s FOR UPDATE',
                                         (writer['generation_id'],)).fetchone()
            if current['state'] != 'collecting':
                raise LifecycleHold('writer generation not collecting')
            allocation = connection.execute('SELECT pg_total_relation_size(to_regclass(%s)) AS size',
                                            ('raw.' + current['partition_name'],)).fetchone()['size']
            if allocation is None:
                raise LifecycleHold('collecting partition missing')
            reason = policy.due(current['started_at'], now, allocation)
            if not reason:
                return {'status': 'collecting', 'generation_id': current['generation_id'],
                        'allocated_bytes': allocation}
            slot = 'B' if current['slot'] == 'A' else 'A'
            occupied = connection.execute('''SELECT 1 FROM archive.generations
                WHERE origin_id=%s AND slot=%s AND state<>'retired' LIMIT 1''',
                                          (origin_id, slot)).fetchone()
            if occupied:
                connection.execute('UPDATE archive.generations SET hold_reason=%s WHERE generation_id=%s',
                                   ('other_slot_not_retired', current['generation_id']))
                return {'status': 'held', 'reason': 'other_slot_not_retired',
                        'generation_id': current['generation_id']}
            count = connection.execute('SELECT count(*) AS count FROM raw.events WHERE generation_id=%s',
                                       (current['generation_id'],)).fetchone()['count']
            new = self._create(connection, origin_id, slot, now)
            connection.execute("""UPDATE archive.generations SET state='sealed',sealed_at=%s,
                seal_count=%s,hold_reason=NULL WHERE generation_id=%s""", (now, count, current['generation_id']))
            connection.execute("UPDATE archive.generations SET state='collecting',started_at=%s WHERE generation_id=%s",
                               (now, new['generation_id']))
            connection.execute('''UPDATE ops.writer_state SET generation_id=%s,epoch=epoch+1,updated_at=%s
                WHERE origin_id=%s''', (new['generation_id'], now, origin_id))
            return {'status': 'switched', 'reason': reason, 'sealed_generation_id': current['generation_id'],
                    'generation_id': new['generation_id'], 'slot': slot, 'seal_count': count}

    def generation(self, generation_id: str) -> dict:
        with self.transaction() as connection:
            row = connection.execute('SELECT * FROM archive.generations WHERE generation_id=%s',
                                     (generation_id,)).fetchone()
            if not row:
                raise LifecycleHold('unknown generation')
            return row

    @staticmethod
    def _manifests(connection, generation_id):
        rows = connection.execute('SELECT * FROM archive.manifests WHERE generation_id=%s ORDER BY manifest_id LIMIT 129',
                                  (generation_id,)).fetchall()
        if len(rows) > 128:
            raise ArchiveLimit('generation manifest catalog exceeds bounded qualification')
        # Fixed-width sequence in manifest_id is deterministic across restarts.
        return rows

    def manifests(self, generation_id):
        with self.transaction() as connection:
            return self._manifests(connection, generation_id)

    def archive_page(self, generation_id, after, limits):
        with self.transaction() as connection:
            generation = connection.execute('SELECT * FROM archive.generations WHERE generation_id=%s FOR SHARE',
                                            (generation_id,)).fetchone()
            if not generation or generation['state'] not in ('sealed', 'verified'):
                raise LifecycleHold('generation not sealed')
            return self._page(connection, generation_id, after, limits)

    @staticmethod
    def _page(connection, generation_id, after, limits):
        condition = '' if after is None else 'AND (source COLLATE "C",event_id COLLATE "C")>(%s,%s)'
        parameters = [generation_id, *(after or []), limits.max_rows + 1]
        # Fetch sizes before payloads: neither a huge row nor many large rows may
        # cause an unbounded allocation on the lifecycle worker.
        sizes = connection.execute(f'''SELECT source,event_id,octet_length(row_to_json(e)::text) AS bytes
            FROM raw.events e WHERE generation_id=%s {condition}
            ORDER BY source COLLATE "C",event_id COLLATE "C" LIMIT %s''', parameters).fetchall()
        chosen, total = [], 1024  # conservative header/JSON serialization allowance
        for item in sizes[:limits.max_rows]:
            # JSONB's textual spaces can shrink, never expand, in canonical form;
            # allowance covers wire conversion of numeric values to strings.
            cost = item['bytes'] * 2 + 256
            if total + cost > limits.max_decoded_bytes:
                if not chosen:
                    raise ArchiveLimit('single raw row exceeds archive chunk bound')
                break
            total += cost
            chosen.append([item['source'], item['event_id']])
        if not chosen:
            return [], False
        rows = connection.execute(f'''SELECT * FROM raw.events WHERE generation_id=%s {condition}
            AND (source COLLATE "C",event_id COLLATE "C")<=(%s,%s)
            ORDER BY source COLLATE "C",event_id COLLATE "C"''',
                                  [generation_id, *(after or []), *chosen[-1]]).fetchall()
        return rows, len(sizes) > len(chosen)

    def record_manifest(self, generation_id, manifest):
        with self.transaction() as connection:
            generation = connection.execute('SELECT * FROM archive.generations WHERE generation_id=%s FOR UPDATE',
                                            (generation_id,)).fetchone()
            if generation['state'] not in ('sealed', 'verified'):
                raise LifecycleHold('generation changed during archive')
            prior = connection.execute('''SELECT * FROM archive.manifests WHERE generation_id=%s AND manifest_id=%s''',
                                       (generation_id, manifest['manifest_id'])).fetchone()
            if prior:
                for key in ('object_key', 'sha256', 'byte_count', 'row_count', 'coverage'):
                    if prior[key] != manifest[key]:
                        raise ArchiveIntegrityError('conflicting manifest retry')
                return
            connection.execute('''INSERT INTO archive.manifests
                (origin_id,generation_id,manifest_id,format_version,object_key,sha256,row_count,byte_count,
                 coverage,created_at,verified_at,verification)
                VALUES(%s,%s,%s,1,%s,%s,%s,%s,%s::jsonb,%s,%s,%s::jsonb)''',
                               (generation['origin_id'], generation_id, manifest['manifest_id'],
                                manifest['object_key'], manifest['sha256'], manifest['row_count'],
                                manifest['byte_count'], encoded(manifest['coverage']).decode(),
                                utcnow(), utcnow(), json.dumps({'method': 'fresh_authenticated_readback'})))
            self._checkpoint(connection, generation, 'raw.events',
                             {'manifest_id': manifest['manifest_id'], 'after': manifest['coverage']['last']})

    @staticmethod
    def _checkpoint(connection, generation, consumer, cursor):
        connection.execute('''INSERT INTO archive.checkpoints(origin_id,generation_id,consumer,cursor,acknowledged_at)
            VALUES(%s,%s,%s,%s::jsonb,%s) ON CONFLICT(origin_id,generation_id,consumer)
            DO UPDATE SET cursor=excluded.cursor,acknowledged_at=excluded.acknowledged_at''',
                           (generation['origin_id'], generation['generation_id'], consumer,
                            encoded(cursor).decode(), utcnow()))

    def mark_verified(self, generation_id):
        with self.transaction() as connection:
            generation = connection.execute('SELECT * FROM archive.generations WHERE generation_id=%s FOR UPDATE',
                                            (generation_id,)).fetchone()
            if generation['state'] not in ('sealed', 'verified'):
                raise LifecycleHold('generation not sealed')
            digest = validate_manifest_chain(self._manifests(connection, generation_id), generation)
            connection.execute("""UPDATE archive.generations SET state='verified',verified_at=%s,
                seal_hash=%s,hold_reason=NULL WHERE generation_id=%s""", (utcnow(), digest, generation_id))
            return digest

    @staticmethod
    def _pending(connection, generation_id, limit, *, include_acknowledged=False, max_bytes=4 * 1024 * 1024):
        condition = '' if include_acknowledged else 'AND acknowledged_at IS NULL'
        sizes = connection.execute(f'''SELECT id,octet_length(row_to_json(o)::text) AS bytes
            FROM ops.outbox o WHERE generation_id=%s {condition} ORDER BY id LIMIT %s''',
                                   (generation_id, limit)).fetchall()
        chosen, total = [], 0
        for row in sizes:
            cost = row['bytes'] * 2 + 256
            if total + cost > max_bytes:
                if include_acknowledged or not chosen:
                    raise ArchiveLimit('structured readback exceeds byte bound')
                break
            chosen.append(row['id'])
            total += cost
        if not chosen:
            return []
        return connection.execute(f'''SELECT * FROM ops.outbox WHERE generation_id=%s {condition}
            AND id<=%s ORDER BY id LIMIT %s''', (generation_id, chosen[-1], limit)).fetchall()

    def outbox(self, generation_id, limit, max_bytes=4 * 1024 * 1024):
        with self.transaction() as connection:
            return self._pending(connection, generation_id, limit, max_bytes=max_bytes)

    def acknowledge(self, generation_id, records):
        with self.transaction() as connection:
            generation = connection.execute('SELECT * FROM archive.generations WHERE generation_id=%s FOR SHARE',
                                            (generation_id,)).fetchone()
            for record in records:
                result = connection.execute('''UPDATE ops.outbox SET acknowledged_at=%s
                    WHERE id=%s AND generation_id=%s AND content_hash=%s AND payload=%s::jsonb''',
                                            (utcnow(), record['id'], generation_id, record['content_hash'],
                                             encoded(record['payload']).decode()))
                if result.rowcount != 1:
                    raise ArchiveIntegrityError('outbox content changed during acknowledgement')
                self._checkpoint(connection, generation, 'structured:' + record['entity_type'],
                                 {'outbox_id': record['id'], 'entity_id': record['entity_id'],
                                  'content_hash': record['content_hash']})

    @contextmanager
    def retirement(self, generation_id):
        """Lock generation, readers, and protected evidence for final readback.

        Writers in the other slot need neither this lock nor this connection.
        Abort/exception rolls back the txid checkpoint and DROP together.
        """
        with self.transaction() as connection:
            generation = connection.execute('SELECT * FROM archive.generations WHERE generation_id=%s FOR UPDATE',
                                            (generation_id,)).fetchone()
            if not generation or generation['state'] != 'verified':
                raise LifecycleHold('generation not verified')
            if connection.execute('''SELECT 1 FROM archive.reader_leases
                    WHERE generation_id=%s AND expires_at>clock_timestamp() LIMIT 1''', (generation_id,)).fetchone():
                raise LifecycleHold('readers not drained')
            if connection.execute('SELECT 1 FROM ops.outbox WHERE generation_id=%s AND acknowledged_at IS NULL LIMIT 1',
                                  (generation_id,)).fetchone():
                raise LifecycleHold('structured outbox not acknowledged')
            unprotected = connection.execute('''SELECT 1 FROM core.protected_evidence p
                WHERE p.generation_id=%s AND NOT EXISTS(SELECT 1 FROM ops.outbox o
                WHERE o.origin_id=p.origin_id AND o.generation_id=p.generation_id
                AND o.entity_type='core.protected_evidence' AND o.content_hash=p.content_hash
                AND o.payload->>'evidence_id'=p.evidence_id AND o.payload->>'origin_id'=p.origin_id
                AND o.acknowledged_at IS NOT NULL) LIMIT 1''', (generation_id,)).fetchone()
            if unprotected:
                raise LifecycleHold('protected evidence not independently verified')
            actual = connection.execute('SELECT count(*) AS count FROM raw.events WHERE generation_id=%s',
                                        (generation_id,)).fetchone()['count']
            if actual != generation['seal_count']:
                raise LifecycleHold('sealed raw count changed')
            yield connection, generation, self._manifests(connection, generation_id)

    def verify_local_chunk(self, connection, generation_id, manifest, decoded, limits):
        local, _ = self._page(connection, generation_id, manifest['coverage']['after'],
                              replace(limits, max_rows=max(1, manifest['row_count'])))
        if wire(local) != decoded:
            raise ArchiveIntegrityError('sealed local content differs from authenticated archive')

    def retire_in_transaction(self, connection, generation, digest):
        connection.execute('UPDATE archive.generations SET hold_reason=NULL WHERE generation_id=%s',
                           (generation['generation_id'],))
        txid = connection.execute('SELECT txid_current() AS txid').fetchone()['txid']
        self._checkpoint(connection, generation, 'retirement:fresh-readback',
                         {'gate_scope': 'immutable-generated', 'authorized_txid': txid,
                          'sha256': digest, 'row_count': generation['seal_count'], 'retirement_enabled': True})
        connection.execute('SELECT archive.retire_generation_partition(%s,%s)',
                           (generation['origin_id'], generation['generation_id']))

    def hold(self, generation_id, reason):
        with self.transaction() as connection:
            connection.execute("UPDATE archive.generations SET hold_reason=%s WHERE generation_id=%s AND state<>'retired'",
                               (reason[:160], generation_id))

    def local_history(self, generation_id, after, limits):
        with self.transaction() as connection:
            generation = connection.execute('SELECT * FROM archive.generations WHERE generation_id=%s FOR SHARE',
                                            (generation_id,)).fetchone()
            if not generation:
                raise LifecycleHold('unknown generation')
            if generation['state'] == 'retired':
                return generation, None, False
            # The generation SHARE lock is the authoritative in-flight SQL reader
            # barrier. The durable lease additionally supports long external readers.
            rows, more = self._page(connection, generation_id, after, limits)
            return generation, rows, more

    @contextmanager
    def reader_lease(self, generation_id, holder, seconds=30):
        if not 0 < seconds <= 60 or not holder or len(holder) > 160:
            raise ValueError('reader lease holder/TTL invalid')
        lease_id = str(uuid.uuid4())
        with self.transaction() as connection:
            generation = connection.execute('SELECT * FROM archive.generations WHERE generation_id=%s FOR SHARE',
                                            (generation_id,)).fetchone()
            if not generation or generation['state'] == 'retired':
                raise LifecycleHold('local generation unavailable')
            connection.execute('''INSERT INTO archive.reader_leases
                (lease_id,origin_id,generation_id,holder,expires_at) VALUES(%s,%s,%s,%s,%s)''',
                               (lease_id, generation['origin_id'], generation_id, holder,
                                utcnow() + timedelta(seconds=seconds)))
        try:
            yield lease_id
        finally:
            with self.transaction() as connection:
                connection.execute('DELETE FROM archive.reader_leases WHERE lease_id=%s', (lease_id,))


class ArchiveWorker:
    def __init__(self, repository, transport, limits=ArchiveLimits()):
        self.repository, self.transport, self.limits = repository, transport, limits

    @staticmethod
    def structured_records(rows):
        keys = ('id', 'origin_id', 'generation_id', 'entity_type', 'entity_id', 'content_hash', 'payload')
        return [wire({key: row[key] for key in keys}) for row in rows]

    def sync_outbox(self, generation_id, budget):
        rows = self.repository.outbox(generation_id, self.limits.max_rows, self.limits.max_decoded_bytes)
        if not rows:
            return 0
        records = self.structured_records(rows)
        size = len(encoded(records))
        if size > self.limits.max_decoded_bytes:
            raise ArchiveLimit('structured batch byte limit reached')
        self.transport.put_structured(records, timeout_seconds=budget.request(size))
        budget.check()
        retrieved = self.transport.read_structured_authenticated(
            records, max_bytes=self.limits.max_decoded_bytes,
            timeout_seconds=budget.request(size))
        budget.check()
        if encoded(retrieved) != encoded(records):
            raise ArchiveIntegrityError('structured authenticated readback mismatch')
        self.repository.acknowledge(generation_id, records)
        return len(records)

    def archive_cycle(self, generation_id):
        budget = CycleBudget(self.limits)
        try:
            with budget:
                return self._archive_cycle(generation_id, budget)
        except BaseException as error:
            # Includes cancellation. No raw mutation has occurred on this path.
            self._record_hold(generation_id, error, budget)
            raise

    def _record_hold(self, generation_id, error, budget):
        # Failure reporting must not extend an expired work deadline or mask the
        # original cancellation. The raw partition is preserved even if DB is down.
        try:
            with budget:
                budget.check()
                self.repository.hold(generation_id, getattr(error, 'code', type(error).__name__))
        except Exception:
            pass

    def _archive_cycle(self, generation_id, budget):
        generation = self.repository.generation(generation_id)
        if generation['state'] not in ('sealed', 'verified'):
            raise LifecycleHold('generation not sealed')
        synced = self.sync_outbox(generation_id, budget)
        manifests = self.repository.manifests(generation_id)
        after = manifests[-1]['coverage']['last'] if manifests else None
        rows, more = self.repository.archive_page(generation_id, after, self.limits)
        if rows or not manifests:
            blob, manifest = pack_chunk(rows, origin_id=generation['origin_id'],
                                        generation_id=generation_id, after=after, limits=self.limits)
            manifest['manifest_id'] = f'raw.events:{len(manifests):012d}'
            # Origin is hashed so arbitrary source namespaces never form paths.
            manifest['object_key'] = (f'raw-v1/{sha256(generation["origin_id"].encode())}/'
                                      f'{generation_id}/{manifest["sha256"]}.jsonl.gz')
            self.transport.put_if_absent(manifest['object_key'], blob,
                                         timeout_seconds=budget.request(len(blob)))
            budget.check()
            if read_verified(self.transport, manifest, budget) != wire(rows):
                raise ArchiveIntegrityError('raw authenticated readback mismatch')
            self.repository.record_manifest(generation_id, manifest)
        if not more:
            self.repository.mark_verified(generation_id)
        return {'status': 'archived' if not more else 'partial', 'outbox_rows': synced,
                'raw_rows': len(rows), 'requests': budget.requests, 'bytes': budget.bytes,
                'retirement': 'held_cp6_authority_unqualified'}

    def retire_generated(self, generation_id, *, qualification_enabled=False):
        """Only isolated immutable mock qualification; no production/cloud permit.

        Every object and structured record is re-read inside this transaction.
        Persisted verification timestamps never authorize destructive operations.
        """
        if (not qualification_enabled or self.repository.environment != 'preprod' or
                self.transport.authority_scope != 'immutable-generated'):
            raise LifecycleHold('runtime retirement disabled; CP6 authority unresolved')
        budget = CycleBudget(self.limits)
        try:
            with budget, self.repository.retirement(generation_id) as (connection, generation, manifests):
                if not generation['origin_id'].startswith('generated-'):
                    raise LifecycleHold('only isolated generated origins may retire')
                digest = validate_manifest_chain(manifests, generation)
                if digest != generation['seal_hash']:
                    raise ArchiveIntegrityError('sealed manifest set changed')
                # Preflight total cost before any network request. Final readback is
                # one bounded operation, never assembled from prior cycle proofs.
                if len(manifests) + 1 > self.limits.max_requests:
                    raise ArchiveLimit('final readback exceeds request budget')
                if sum(item['byte_count'] for item in manifests) > self.limits.max_cycle_bytes:
                    raise ArchiveLimit('final readback exceeds byte budget')
                for manifest in manifests:
                    decoded = read_verified(self.transport, manifest, budget)
                    self.repository.verify_local_chunk(connection, generation_id, manifest, decoded, self.limits)
                    budget.check()
                rows = self.repository._pending(connection, generation_id,
                                                self.limits.max_rows + 1, include_acknowledged=True,
                                                max_bytes=self.limits.max_decoded_bytes)
                if len(rows) > self.limits.max_rows:
                    raise ArchiveLimit('final structured readback exceeds row budget')
                records = self.structured_records(rows)
                if records:
                    size = len(encoded(records))
                    if size > self.limits.max_decoded_bytes:
                        raise ArchiveLimit('final structured readback exceeds byte budget')
                    retrieved = self.transport.read_structured_authenticated(
                        records, max_bytes=self.limits.max_decoded_bytes,
                        timeout_seconds=budget.request(size))
                    budget.check()
                    if encoded(retrieved) != encoded(records):
                        raise ArchiveIntegrityError('final structured readback mismatch')
                budget.check()
                self.repository.retire_in_transaction(connection, generation, digest)
            return {'status': 'retired_generated', 'generation_id': generation_id,
                    'requests': budget.requests, 'bytes': budget.bytes}
        except BaseException as error:
            self._record_hold(generation_id, error, budget)
            raise
