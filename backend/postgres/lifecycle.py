"""PostgreSQL A/B generations, durable archive jobs, and generated retirement.

Runtime cloud mutation authority is unqualified (CP6). This module supplies no
cloud adapter and never enables real retirement. The only destructive method is
explicit isolated generated qualification, backed by a txid-bound SQL gate.
"""
from __future__ import annotations

from contextlib import contextmanager, nullcontext
from threading import local
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import json
import uuid

from . import pp_space
from .rehearsal_profile import (canonical_anchor, lease_cap, require_cycle_alignment,
                                CYCLE_ORIGINS, TRIAL_ORIGINS)
from .retirement_accounting import phase
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
        self._worker_session = local()

    @contextmanager
    def transaction(self):
        budget = ACTIVE_BUDGET.get()
        # connect() is bounded to five seconds by the common connection contract.
        # Do not begin another connection when that reserve no longer fits.
        locked = getattr(self._worker_session, 'connection', None)
        if locked is None and budget and budget.deadline - budget.clock() <= 5:
            raise ArchiveLimit('insufficient cycle time for another database connection')
        with (self.connection_factory() if locked is None else nullcontext(locked)) as connection:
            with connection.transaction():
                if budget:
                    budget.check()
                    remaining = max(1, int(1000 * (budget.deadline - budget.clock())))
                    connection.execute("SELECT set_config('transaction_timeout',%s,true)",
                                       (f'{remaining}ms',))
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

    def enable_collector(self, origin_id: str, *, session_id: str,
                         expected_generation_id: str, max_seconds: int, rehearsal_anchor=None) -> dict:
        """Enable one finite PP writer lease after separate host admission.

        The operator runtime calls this only after its host control gate;
        this database lease alone cannot establish that production is fenced.
        """
        if self.environment != 'preprod' or not origin_id.startswith('pp-live-') or \
                len(origin_id) <= len('pp-live-') or len(origin_id) > 128:
            raise LifecycleHold('unsupported collector enable scope')
        try:
            cap = lease_cap(rehearsal_anchor)
        except ValueError as error:
            raise LifecycleHold(str(error)) from None
        if origin_id in TRIAL_ORIGINS and rehearsal_anchor is None:
            raise LifecycleHold('exact trial origin requires two-leg cycle admission')
        if rehearsal_anchor is not None and (origin_id not in CYCLE_ORIGINS or expected_generation_id != rehearsal_anchor
                                              or max_seconds != cap):
            raise LifecycleHold('two-leg rehearsal requires exact initial PP A')
        if isinstance(max_seconds, bool) or not isinstance(max_seconds, int) or not 1 <= max_seconds <= cap:
            raise LifecycleHold('collector lease duration outside bounded window')
        for value in (session_id, expected_generation_id):
            try:
                canonical = str(uuid.UUID(value)) if isinstance(value, str) else None
            except (ValueError, AttributeError):
                canonical = None
            if canonical != value:
                raise LifecycleHold('collector lease identity must be canonical UUID')
        with self.transaction() as connection:
            # A row lock protects one origin. Serialize admission across all PP
            # live origins in this database as well, so an alternate origin
            # cannot start a second collector behind the operator's lease.
            connection.execute("SELECT pg_advisory_xact_lock(hashtextextended('tradebot-pp-live-collector',0))")
            other = connection.execute('''SELECT 1 FROM ops.writer_state
                WHERE origin_id LIKE %s AND origin_id<>%s
                  AND collector_enabled AND collector_lease_expires_at>clock_timestamp()
                LIMIT 1''', ('pp-live-%', origin_id)).fetchone()
            if other:
                raise LifecycleHold('another PP live collector owns this database')
            writer = connection.execute('''SELECT generation_id,epoch,collector_enabled
                FROM ops.writer_state WHERE origin_id=%s FOR UPDATE''', (origin_id,)).fetchone()
            if writer is None or writer['collector_enabled'] or str(writer['generation_id']) != expected_generation_id:
                raise LifecycleHold('collector writer unavailable or generation changed')
            generation = connection.execute('''SELECT state,slot,hold_reason FROM archive.generations
                WHERE origin_id=%s AND generation_id=%s''',
                (origin_id, expected_generation_id)).fetchone()
            if generation is None or generation['state'] != 'collecting':
                raise LifecycleHold('collector generation is not collecting')
            if rehearsal_anchor is not None:
                # Existing retained A/B are evidence, not a fresh trial. Never
                # recycle them or inherit an expired retirement authority.
                occupied = connection.execute('''SELECT 1 FROM archive.generations
                    WHERE origin_id=%s AND generation_id<>%s AND state<>'retired' LIMIT 1''',
                    (origin_id, rehearsal_anchor)).fetchone()
                if generation['slot'] != 'A' or occupied:
                    raise LifecycleHold('two-leg rehearsal requires initial A and free B slot')
            if generation['hold_reason'] == 'pp_window_relation_limit':
                raise LifecycleHold('PP window allocation limit requires review')
            if generation['hold_reason'] == 'other_slot_not_retired':
                raise LifecycleHold('occupied generation slot blocks PP collector restart')
            if origin_id in CYCLE_ORIGINS or generation['hold_reason'] in (
                    'pp_filesystem_reserve','pp_filesystem_sample_unavailable'):
                space = pp_space.sample()
                if space['space_hold']:
                    raise LifecycleHold(space['space_hold'])
                # A fresh admission can clear only a previously recorded disk hold.
                connection.execute('''UPDATE archive.generations SET hold_reason=NULL
                    WHERE generation_id=%s AND hold_reason IN
                    ('pp_filesystem_reserve','pp_filesystem_sample_unavailable')''',
                    (expected_generation_id,))
            result = connection.execute('''UPDATE ops.writer_state SET collector_enabled=true,
                collector_session_id=%s::uuid,
                collector_lease_expires_at=clock_timestamp()+(%s * interval '1 second'),
                epoch=epoch+1,updated_at=clock_timestamp()
                WHERE origin_id=%s RETURNING epoch,collector_lease_expires_at,updated_at''',
                (session_id, max_seconds, origin_id)).fetchone()
            if rehearsal_anchor is not None:
                try:
                    require_cycle_alignment(result['updated_at'])
                except ValueError as error:
                    raise LifecycleHold(str(error)) from None
                self._checkpoint(connection, {'origin_id':origin_id,'generation_id':rehearsal_anchor},
                    'rehearsal:two-leg-session', {'session_id':session_id,
                        'lease_expires_at':result['collector_lease_expires_at'].isoformat(),
                        'admitted_at':result['updated_at'].isoformat(),
                        'initial_a':rehearsal_anchor,'lease_seconds':cap})
        return {'collector_enabled': True, 'epoch': result['epoch'],
                'lease_expires_at': result['collector_lease_expires_at']}

    def disable_collector(self, origin_id: str, now: datetime | None = None) -> dict:
        """Stop writes, or prove a never-bootstrapped PP live origin is empty.

        This method does not grant an ON lease. Host ownership and operator
        admission remain separate from the durable OFF proof.
        """
        if self.environment != 'preprod' or not origin_id or len(origin_id) > 160:
            raise LifecycleHold('unsupported collector stop scope')
        now = now or utcnow()
        with self.transaction() as connection:
            # Bootstrap uses this same lock before creating either row. In the
            # empty case it prevents a generation from appearing between the
            # absence checks and the OFF result; the writer row still drains
            # in-flight acknowledged writes when it exists.
            connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                               ('tradebot-generation-bootstrap:' + origin_id,))
            writer = connection.execute('''SELECT epoch,collector_enabled,collector_session_id,collector_lease_expires_at
                FROM ops.writer_state WHERE origin_id=%s FOR UPDATE''', (origin_id,)).fetchone()
            if writer is None:
                if not origin_id.startswith('pp-live-') or len(origin_id) <= len('pp-live-') or \
                        len(origin_id) > 128:
                    raise LifecycleHold('collector writer identity missing')
                if connection.execute('''SELECT 1 FROM archive.generations
                    WHERE origin_id=%s LIMIT 1''', (origin_id,)).fetchone():
                    raise LifecycleHold('orphan generation requires explicit forward recovery')
                # No writer or generation exists for this exact live origin.
                # Do not bootstrap a file, invent an epoch, or grant an ON lease.
                return {'collector_enabled': False, 'epoch': None}
            if writer['collector_enabled'] or writer['collector_session_id'] is not None or \
                    writer['collector_lease_expires_at'] is not None:
                updated = connection.execute('''UPDATE ops.writer_state
                    SET collector_enabled=false,collector_session_id=NULL,
                    collector_lease_expires_at=NULL,epoch=epoch+1,updated_at=%s
                    WHERE origin_id=%s RETURNING epoch''', (now, origin_id)).fetchone()
                epoch = updated['epoch']
            else:
                epoch = writer['epoch']
            return {'collector_enabled': False, 'epoch': epoch}

    def collector_state(self, origin_id: str) -> dict:
        """Read the durable writer flag; no process-liveness claim is implied."""
        if self.environment != 'preprod' or not origin_id.startswith('pp-live-') or len(origin_id) <= len('pp-live-'):
            raise LifecycleHold('unsupported collector status scope')
        with self.connection_factory() as connection:
            row = connection.execute('''SELECT collector_enabled AND
                collector_lease_expires_at>clock_timestamp() AS collector_enabled,
                collector_enabled AS stored_enabled,collector_lease_expires_at,
                epoch,generation_id,updated_at
                FROM ops.writer_state WHERE origin_id=%s''', (origin_id,)).fetchone()
        if row is None:
            return {'collector_enabled': False, 'epoch': None,
                    'generation_id': None, 'updated_at': None, 'initialized': False}
        return {**dict(row), 'initialized': True}

    def owns_collector(self, origin_id: str, session_id: str) -> bool:
        """Check this exact PP session's unexpired lease, never another origin's."""
        if self.environment != 'preprod' or not origin_id.startswith('pp-live-'):
            return False
        try:
            if str(uuid.UUID(session_id)) != session_id:
                return False
        except (ValueError, TypeError, AttributeError):
            return False
        with self.connection_factory() as connection:
            row = connection.execute('''SELECT collector_enabled AND
                collector_session_id=%s::uuid AND
                collector_lease_expires_at>clock_timestamp() AS owned
                FROM ops.writer_state WHERE origin_id=%s''',
                (session_id, origin_id)).fetchone()
        return bool(row and row['owned'])

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

    @staticmethod
    def _rehearsal_phase(connection, origin, anchor, current):
        initial = connection.execute('''SELECT * FROM archive.generations
            WHERE origin_id=%s AND generation_id=%s''', (origin, anchor)).fetchone()
        if initial is None or initial['slot'] != 'A':
            raise LifecycleHold('initial rehearsal A missing')
        chain = connection.execute('''SELECT * FROM archive.generations
            WHERE origin_id=%s AND created_at>=%s
            ORDER BY created_at,generation_id LIMIT 4''', (origin, initial['created_at'])).fetchall()
        if (not 1 <= len(chain) <= 3 or str(chain[0]['generation_id']) != anchor
                or chain[-1]['generation_id'] != current['generation_id']
                or [row['slot'] for row in chain] != ['A','B','A'][:len(chain)]):
            raise LifecycleHold('rehearsal generation chain changed')
        for previous, successor in zip(chain, chain[1:]):
            if previous['sealed_at'] != successor['started_at']:
                raise LifecycleHold('rehearsal switch boundary changed')
        if len(chain) == 3 and chain[0]['state'] != 'retired':
            raise LifecycleHold('initial A retirement missing')
        return len(chain)-1

    @staticmethod
    def _observed_market_pair(connection, origin, generation, start, now):
        # A session begun mid-market must wait for the next full official interval.
        # Use exact UTC quarters, then validate both venue IDs and their source
        # and receipt timestamps inside the selected generation.
        return connection.execute("""WITH start_at AS (
            SELECT ceil(extract(epoch FROM %s::timestamptz)/900)*900 AS boundary)
            SELECT m.market_id, m.start_epoch, m.end_epoch
            FROM core.markets m CROSS JOIN start_at
            WHERE m.origin_id=%s AND m.source='polymarket_us' AND m.duration=900
              AND m.start_epoch IN (boundary,boundary+900)
              AND m.end_epoch=m.start_epoch+900
              AND boundary+1800<=extract(epoch FROM %s::timestamptz)
              AND EXISTS (SELECT FROM raw.events e
                 WHERE e.origin_id=m.origin_id AND e.generation_id=%s
                 AND e.market_id=m.market_id AND e.source=m.source AND e.kind='quote'
                 AND e.source_epoch>=m.start_epoch AND e.source_epoch<m.end_epoch
                 AND e.received_at>=to_timestamp(m.start_epoch::double precision)
                 AND e.received_at<to_timestamp(m.end_epoch::double precision))
            ORDER BY m.start_epoch,m.market_id LIMIT 3""",
            (start,origin,now,generation)).fetchall()

    def switch_if_due(self, origin_id: str, policy=RotationPolicy(), now=None, *, require_live_lease=False, market_pair_trial=False, rehearsal_anchor=None) -> dict:
        now = now or utcnow()
        with self.transaction() as connection:
            writer = connection.execute('SELECT * FROM ops.writer_state WHERE origin_id=%s FOR UPDATE',
                                        (origin_id,)).fetchone()
            if not writer:
                raise LifecycleHold('writer not bootstrapped')
            if market_pair_trial and (not require_live_lease or self.environment!='preprod'
                                      or not origin_id.startswith('pp-live-')):
                raise LifecycleHold('invalid PP market-window qualification')
            if rehearsal_anchor is not None:
                canonical_anchor(rehearsal_anchor)
                if not market_pair_trial or self.environment != 'preprod' or origin_id not in CYCLE_ORIGINS:
                    raise LifecycleHold('invalid two-leg PP rehearsal scope')
            if require_live_lease:
                # The writer row is locked. Use database time so ready/OFF,
                # expired or stopped sessions cannot seal A during deployment.
                lease = connection.execute('''SELECT collector_enabled AND
                    collector_session_id IS NOT NULL AND
                    collector_lease_expires_at > clock_timestamp() AS active
                    FROM ops.writer_state WHERE origin_id=%s''', (origin_id,)).fetchone()
                if not lease['active']:
                    return {'status': 'idle', 'reason': 'collector_off',
                            'generation_id': writer['generation_id']}
            count = connection.execute('''SELECT count(*) AS count FROM
                (SELECT 1 FROM archive.generations WHERE origin_id=%s AND state<>'retired' LIMIT 3) g''',
                                       (origin_id,)).fetchone()['count']
            if count > 2:
                raise LifecycleHold('nonretired generation bound exceeded')
            space = pp_space.sample() if market_pair_trial else {}
            if space.get('space_hold'):
                reason = space['space_hold']
                connection.execute("""UPDATE archive.generations SET hold_reason=%s
                    WHERE generation_id=%s""", (reason, writer['generation_id']))
                connection.execute("""UPDATE ops.writer_state SET collector_enabled=false,
                    collector_session_id=NULL,collector_lease_expires_at=NULL,epoch=epoch+1,
                    updated_at=%s WHERE origin_id=%s""", (now, origin_id))
                return {'status':'held','reason':reason,'collector_enabled':False,
                        'generation_id':writer['generation_id'], **space}
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
            cycle = None
            if rehearsal_anchor is not None:
                admission = connection.execute('''SELECT cursor FROM archive.checkpoints
                    WHERE origin_id=%s AND generation_id=%s AND consumer='rehearsal:two-leg-session' ''',
                    (origin_id,rehearsal_anchor)).fetchone()
                proof = admission['cursor'] if admission else {}
                if (proof.get('initial_a') != rehearsal_anchor
                        or proof.get('session_id') != str(writer['collector_session_id'])
                        or proof.get('lease_expires_at') != writer['collector_lease_expires_at'].isoformat()
                        or proof.get('lease_seconds') != lease_cap(rehearsal_anchor)):
                    raise LifecycleHold('two-leg session admission changed or missing')
                cycle = self._rehearsal_phase(connection, origin_id, rehearsal_anchor, current)
                if cycle == 2:
                    return {'status':'collecting','reason':'two_leg_rehearsal_complete',
                            'generation_id':current['generation_id'],'allocated_bytes':allocation, **space}
            if market_pair_trial and current['slot']=='B' and rehearsal_anchor is None:
                # Report elapsed B observation using the actual switch time.
                # Normal operator OFF / lease expiry owns orderly shutdown.
                return {'status':'collecting','generation_id':current['generation_id'],
                        'allocated_bytes':allocation,
                        'b_observation_elapsed': now-current['started_at'] >= timedelta(minutes=30), **space}
            pair = []
            if market_pair_trial:
                # writer.updated_at records actual lease enable or last rotation.
                start = max(writer['updated_at'],current['started_at'])
                pair = self._observed_market_pair(connection, origin_id, current['generation_id'], start, now)
                reason = 'two_official_markets' if (len(pair)==2 and
                    pair[0]['end_epoch']==pair[1]['start_epoch']) else None
            else:
                reason = policy.due(current['started_at'], now, allocation)
            if not reason:
                return {'status': 'collecting', 'generation_id': current['generation_id'],
                        'allocated_bytes': allocation, **space}
            slot = 'B' if current['slot'] == 'A' else 'A'
            occupied = connection.execute('''SELECT 1 FROM archive.generations
                WHERE origin_id=%s AND slot=%s AND state<>'retired' LIMIT 1''',
                                          (origin_id, slot)).fetchone()
            if occupied:
                connection.execute('UPDATE archive.generations SET hold_reason=%s WHERE generation_id=%s',
                                   ('other_slot_not_retired', current['generation_id']))
                result = {'status': 'held', 'reason': 'other_slot_not_retired',
                          'generation_id': current['generation_id']}
                if origin_id.startswith('pp-live-'):
                    # This writer row is already locked FOR UPDATE. Drain any
                    # in-flight acknowledgement, then commit the hold and OFF
                    # together so no new PP write can enter the occupied slot.
                    connection.execute('''UPDATE ops.writer_state
                        SET collector_enabled=false,collector_session_id=NULL,
                            collector_lease_expires_at=NULL,epoch=epoch+1,updated_at=%s
                        WHERE origin_id=%s AND (collector_enabled OR
                            collector_session_id IS NOT NULL OR collector_lease_expires_at IS NOT NULL)''',
                        (now, origin_id))
                    result['collector_enabled'] = False
                return result
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
                    'generation_id': new['generation_id'], 'slot': slot, 'seal_count': count,
                    **({**space, 'window_market_ids':[row['market_id'] for row in pair],
                        'window_start_epoch':str(pair[0]['start_epoch']),
                        'window_end_epoch':str(pair[-1]['end_epoch']),
                        'next_generation_started_at':now.isoformat()} if pair else {})}

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
    def _pending(connection, generation_id, limit, *, include_acknowledged=False, max_bytes=4 * 1024 * 1024, after_id=0):
        condition = '' if include_acknowledged else 'AND acknowledged_at IS NULL'
        sizes = connection.execute(f'''SELECT id,octet_length(row_to_json(o)::text) AS bytes
            FROM ops.outbox o WHERE generation_id=%s AND id>%s {condition} ORDER BY id LIMIT %s''',
                                   (generation_id, after_id, limit)).fetchall()
        chosen, total = [], 0
        for row in sizes:
            cost = row['bytes'] * 2 + 256
            if total + cost > max_bytes:
                if not chosen:
                    raise ArchiveLimit('structured readback exceeds byte bound')
                break
            chosen.append(row['id'])
            total += cost
        if not chosen:
            return []
        return connection.execute(f'''SELECT * FROM ops.outbox WHERE generation_id=%s {condition}
            AND id>%s AND id<=%s ORDER BY id LIMIT %s''', (generation_id, after_id, chosen[-1], limit)).fetchall()

    def outbox(self, generation_id, limit, max_bytes=4 * 1024 * 1024):
        with self.transaction() as connection:
            return self._pending(connection, generation_id, limit, max_bytes=max_bytes)

    def structured_pending_generations(self, origin_id):
        """Choose sealed evidence before active evidence without changing either.

        A later active generation must never project ahead of a pending sealed
        generation. This is a bounded hint: each worker rechecks its generation
        and pending rows under its own origin-wide sync lock before cloud I/O.
        """
        if not isinstance(origin_id, str) or not 1 <= len(origin_id) <= 160:
            raise LifecycleHold('bounded structured origin required')
        with self.transaction() as connection:
            count = connection.execute('''SELECT count(*) AS total FROM
                (SELECT 1 FROM ops.outbox WHERE origin_id=%s AND
                 acknowledged_at IS NULL LIMIT %s) pending''',
                (origin_id, self.pending_outbox_limit + 1)).fetchone()['total']
            if count > self.pending_outbox_limit:
                raise LifecycleHold('pending structured outbox bound exceeded')
            rows = connection.execute('''WITH pending AS (
                SELECT generation_id, min(id) AS first_id FROM ops.outbox
                WHERE origin_id=%s AND acknowledged_at IS NULL
                GROUP BY generation_id)
                SELECT p.generation_id,p.first_id,g.state,g.origin_id
                FROM pending p LEFT JOIN archive.generations g
                  ON g.generation_id=p.generation_id
                ORDER BY CASE WHEN g.state IN ('sealed','verified') THEN 0
                              WHEN g.state='collecting' THEN 1 ELSE 2 END,
                         p.first_id LIMIT 3''', (origin_id,)).fetchall()
        if len(rows) > 2 or any(row['generation_id'] is None or
                                row['origin_id'] != origin_id or
                                row['state'] not in ('collecting','sealed','verified')
                                for row in rows):
            raise LifecycleHold('unqualified structured generation backlog')
        return [{'generation_id': row['generation_id'], 'state': row['state'],
                 'first_id': row['first_id']} for row in rows]

    def has_other_pending(self, origin_id, generation_id):
        """Hold active sync until earlier sealed-generation evidence drains.

        The single-writer switch fences writes into the sealed generation. Any
        other pending generation for this origin is therefore an unresolved
        ordering dependency, including states requiring operator recovery.
        """
        with self.transaction() as connection:
            return connection.execute('''SELECT 1 FROM ops.outbox
                WHERE origin_id=%s AND generation_id<>%s
                AND acknowledged_at IS NULL LIMIT 1''',
                (origin_id, generation_id)).fetchone() is not None

    def structured_sync_lock(self, origin_id):
        """Serialize structured imports and fresh receipt acknowledgements."""
        return self._origin_lock('tradebot-structured-sync:', origin_id)

    def raw_archive_lock(self, origin_id):
        """Serialize archive manifest writers independently of structured I/O."""
        return self._origin_lock('tradebot-raw-archive:', origin_id)

    @contextmanager
    def _origin_lock(self, namespace, origin_id):
        locked = getattr(self._worker_session, 'connection', None)
        budget = ACTIVE_BUDGET.get()
        if budget:
            budget.check()
            if locked is None and budget.deadline - budget.clock() <= 5:
                raise ArchiveLimit('insufficient cycle time for sync lock connection')
        with (self.connection_factory() if locked is None else nullcontext(locked)) as connection:
            if locked is None:
                connection.autocommit = True
                connection.execute("SET statement_timeout='1000ms'")
            key = namespace + origin_id
            held_keys = getattr(self._worker_session, 'held_keys', frozenset())
            if key in held_keys:
                raise LifecycleHold('another structured sync worker is active')
            acquired = connection.execute('''SELECT
                pg_try_advisory_lock(hashtextextended(%s,0)) AS acquired''',
                (key,)).fetchone()['acquired']
            if not acquired:
                raise LifecycleHold('another structured sync worker is active')
            # One synchronous worker owns this backend until unlock. Autocommit
            # keeps the lock session idle between individual local transactions.
            self._worker_session.connection = connection
            self._worker_session.held_keys = held_keys | {key}
            try:
                if budget:
                    budget.check()
                yield
            finally:
                self._worker_session.held_keys = held_keys
                if locked is None:
                    del self._worker_session.connection
                # Connection close releases the lock even if this unlock fails.
                connection.execute('SELECT pg_advisory_unlock(hashtextextended(%s,0))',
                                   (key,))

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
    def retirement(self, generation_id, *, expected_origin=None):
        """Lock generation, readers, and protected evidence for final readback.

        Writers in the other slot need neither this lock nor this connection.
        Abort/exception rolls back the txid checkpoint and DROP together.
        """
        with self.transaction() as connection:
            if expected_origin is None:
                generation = connection.execute(
                    'SELECT * FROM archive.generations WHERE generation_id=%s FOR UPDATE',
                    (generation_id,)).fetchone()
            else:
                # Decide scope in the locking statement itself. A separate read and
                # check after FOR UPDATE would still contend with another origin.
                generation = connection.execute(
                    'SELECT * FROM archive.generations WHERE origin_id=%s AND generation_id=%s FOR UPDATE',
                    (expected_origin, generation_id)).fetchone()
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
        # An unleased SQL reader may start during remote verification. Avoid
        # queuing an exclusive parent-table lock behind it and stalling B.
        connection.execute("SET LOCAL lock_timeout='5ms'")
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

    def fresh_retirement_readback(self, connection, generation, manifests, budget):
        """Compare the exact sealed raw and structured rows under the caller's generation lock.

        Keep all authenticated reads inside one bounded operation. A caller may
        use this as diagnostic evidence; it grants no authority to remove data.
        """
        generation_id = generation['generation_id']
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
            with phase('raw_read_decode'):
                decoded = read_verified(self.transport, manifest, budget)
            with phase('raw_local_compare'):
                self.repository.verify_local_chunk(connection, generation_id, manifest, decoded, self.limits)
            budget.check()
        after_id = 0
        structured_count = 0
        while True:
            budget.check()
            with phase('structured_local_page'):
                rows = self.repository._pending(connection, generation_id,
                    self.limits.max_rows, include_acknowledged=True,
                    max_bytes=self.limits.max_decoded_bytes, after_id=after_id)
                if not rows:
                    break
                records = self.structured_records(rows)
                ids = [row['id'] for row in records]
                if (ids[0] <= after_id or ids != sorted(set(ids)) or
                        any(row['origin_id'] != generation['origin_id'] or
                            str(row['generation_id']) != str(generation_id) for row in records)):
                    raise ArchiveIntegrityError('final structured page identity mismatch')
                size = len(encoded(records))
                if size > self.limits.max_decoded_bytes:
                    raise ArchiveLimit('final structured readback exceeds byte budget')
            with phase('structured_readback'):
                retrieved = self.transport.read_structured_authenticated(
                    records, max_bytes=self.limits.max_decoded_bytes,
                    timeout_seconds=budget.request(size))
            budget.check()
            with phase('structured_compare'):
                if encoded(retrieved) != encoded(records):
                    raise ArchiveIntegrityError('final structured readback mismatch')
            structured_count += len(rows)
            after_id = ids[-1]
        return {'manifest_digest':digest,'raw_count':generation['seal_count'],
                'objects_read':len(manifests),'structured_count':structured_count,
                'last_structured_id':after_id,'requests':budget.requests,'bytes':budget.bytes}

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
                readback = self.fresh_retirement_readback(connection, generation, manifests, budget)
                digest = readback['manifest_digest']
                budget.check()
                self.repository.retire_in_transaction(connection, generation, digest)
            return {'status': 'retired_generated', 'generation_id': generation_id,
                    'requests': budget.requests, 'bytes': budget.bytes}
        except BaseException as error:
            self._record_hold(generation_id, error, budget)
            raise
