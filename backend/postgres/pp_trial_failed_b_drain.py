"""Exact failed03 stopped-B maintenance seal; no successor, transfer or retirement.

This explicitly preserves the failed PP26 trial. It cannot complete either
retirement leg or authorize collection. The existing03 archive worker may later
archive the sealed B using its separately reviewed normal controls.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
import os
import re
import uuid

from .archive_codec import ArchiveError, ArchiveLimits, CycleBudget, encoded, sha256, wire
from .lifecycle import LifecycleHold, LifecycleRepository, validate_manifest_chain
from .pp_raw_archive_probe import OFF_FLAGS
from .pp_structured_probe import LOCAL_DSN, private_dsn

ORIGIN = 'pp-live-pp-trial-20261119-03'
INITIAL_A = '15a239c9-2f9b-4bdc-bd89-7cd1e2812f45'
FAILED_B = '381070ac-3624-4826-8dc6-7ea5a272f97e'
TRIAL_SOURCE = '08ea1b99299475da24b96f778ebf12bf76a64e25'
SESSION_ID = '142a0c69-147d-4b90-8483-ac6d9773e7f9'
A_SEAL_HASH = '2d13fca5162dba62169331c3aa9e87cfca9939d03e256a9054776d6871d8d083'
A_RAW_ROWS, A_ACK_ROWS = 24649, 26480
B_RAW_ROWS, B_ACK_ROWS = 12301, 13210
OFF_EPOCH = 4
CONSUMER = 'trial:failed-03-b-maintenance-seal-v1'
PREPARE_CONSUMER = 'trial:initial-a-prepare-v1'
ADMISSION_CONSUMER = 'rehearsal:two-leg-session'
MAX_ROWS = 64_000
LIMITS = ArchiveLimits(max_seconds=20)
DISABLED = (*OFF_FLAGS, 'TRADEBOT_PP_EXACT_RETIREMENT', 'TRADEBOT_PP_RETIREMENT_READBACK')


GUARD_CODES = {'all writers must be durably OFF with null session and lease': 'failed03_all_writers_must_be_durably_off_with_null_session_and_lease',
 'canonical maintenance operation required': 'failed03_canonical_maintenance_operation_required',
 'exact default OFF failed03 B maintenance profile required': 'failed03_exact_default_off_failed03_b_maintenance_profile_required',
 'exact lifecycle database identity required': 'failed03_exact_lifecycle_database_identity_required',
 'exact retained A and failed B chain required': 'failed03_exact_retained_a_and_failed_b_chain_required',
 'exact reviewed failed03 B target required': 'failed03_exact_reviewed_failed03_b_target_required',
 'explicit bounded failed03 maintenance required': 'failed03_explicit_bounded_failed03_maintenance_required',
 'failed B is no longer retainable': 'failed03_failed_b_is_no_longer_retainable',
 'failed B start is invalid': 'failed03_failed_b_start_is_invalid',
 'failed03 B or stopped writer epoch changed': 'failed03_failed03_b_or_stopped_writer_epoch_changed',
 'failed03 B seal replay differs from completed operation': 'failed03_failed03_b_seal_replay_differs_from_completed_operation',
 'failed03 projection closure incomplete': 'failed03_failed03_projection_closure_incomplete',
 'failed03 readers must be drained': 'failed03_failed03_readers_must_be_drained',
 'original finite failed03 admission changed': 'failed03_original_finite_failed03_admission_changed',
 'original preparation and admission required': 'failed03_original_preparation_and_admission_required',
 'original preparation changed': 'failed03_original_preparation_changed',
 'protected identity must be a lowercase ASCII SHA256': 'failed03_protected_identity_must_be_a_lowercase_ascii_sha256',
 'protected original hash projection is not acknowledged': 'failed03_protected_original_hash_projection_is_not_acknowledged',
 'retained A authenticated catalog or coverage changed': 'failed03_retained_a_authenticated_catalog_or_coverage_changed',
 'reviewed partition metadata changed': 'failed03_reviewed_partition_metadata_changed',
 'reviewed physical partition attachment changed': 'failed03_reviewed_physical_partition_attachment_changed',
 'reviewed raw or acknowledged projection count changed': 'failed03_reviewed_raw_or_acknowledged_projection_count_changed',
 'reviewed retained A verification changed': 'failed03_reviewed_retained_a_verification_changed',
 'separately qualified maintenance source required': 'failed03_separately_qualified_maintenance_source_required',
 'stopped03 writer must remain on B': 'failed03_stopped03_writer_must_remain_on_b',
 'unsealed B already has archive manifests': 'failed03_unsealed_b_already_has_archive_manifests'}

class FailedBGuard(LifecycleHold):
    def __init__(self, reason):
        self.code = GUARD_CODES.get(reason, 'failed03_unrecognized_guard')
        super().__init__(self.code)


def require(value, reason):
    if not value:
        raise FailedBGuard(reason)


def public_failure(error):
    if type(error) is FailedBGuard:
        reason = error.code if error.code in GUARD_CODES.values() else 'failed03_unrecognized_guard'
    elif isinstance(error, ArchiveError) and getattr(error, 'code', None) in (
            'archive_error', 'archive_limit', 'archive_integrity', 'archive_unavailable', 'lifecycle_hold'):
        reason = error.code
    else:
        reason = {'LockNotAvailable': 'maintenance_lock_timeout', 'QueryCanceled': 'maintenance_query_timeout',
                  'ConnectionTimeout': 'maintenance_connection_timeout'}.get(type(error).__name__, 'failed03_maintenance_failed')
    return dict(status='HOLD', stage='failed03_b_maintenance', reason=reason,
                retirement_authorized=False, original_trial_satisfied=False, successor_created=False)


@dataclass(frozen=True)
class SealTarget:
    generation: str
    initial_a: str
    writer_epoch: int
    raw_count: int
    outbox_count: int
    trial_source: str
    operation: str
    source: str

    def validate(self):
        require(self.generation == FAILED_B and self.initial_a == INITIAL_A
                and self.trial_source == TRIAL_SOURCE
                and type(self.writer_epoch) is int and self.writer_epoch == OFF_EPOCH
                and type(self.raw_count) is int and self.raw_count == B_RAW_ROWS
                and type(self.outbox_count) is int and self.outbox_count == B_ACK_ROWS
                and 0 < self.raw_count <= MAX_ROWS and 0 < self.outbox_count <= MAX_ROWS,
                'exact reviewed failed03 B target required')
        try:
            valid_operation = isinstance(self.operation, str) and str(uuid.UUID(self.operation)) == self.operation
        except (ValueError, TypeError, AttributeError):
            valid_operation = False
        require(valid_operation and uuid.UUID(self.operation).int != 0,
                'canonical maintenance operation required')
        require(isinstance(self.source, str) and re.fullmatch('[0-9a-f]{40}', self.source)
                and self.source != TRIAL_SOURCE and set(self.source) != {'0'},
                'separately qualified maintenance source required')


def _partition(db, row):
    child = 'events_g_' + row['generation_id'].replace('-', '')
    require(row['partition_name'] == child, 'reviewed partition metadata changed')
    attached = db.execute("""SELECT EXISTS(SELECT 1 FROM pg_inherits i
        JOIN pg_class c ON c.oid=i.inhrelid JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE i.inhparent='raw.events'::regclass AND n.nspname='raw' AND c.relname=%s
          AND pg_get_expr(c.relpartbound,c.oid)=format('FOR VALUES IN (%%L)',%s::text)) AS valid""",
                          (child, row['generation_id'])).fetchone()['valid']
    require(attached is True, 'reviewed physical partition attachment changed')


def _counts(db, generation, raw_count, outbox_count):
    count = db.execute('SELECT count(*) AS n FROM (SELECT 1 FROM raw.events '
                       'WHERE origin_id=%s AND generation_id=%s LIMIT %s) bounded',
                       (ORIGIN, generation, MAX_ROWS + 1)).fetchone()['n']
    outbox = db.execute('SELECT count(*) AS n, count(*) FILTER (WHERE acknowledged_at IS NULL) AS pending '
                       'FROM (SELECT acknowledged_at FROM ops.outbox WHERE origin_id=%s '
                       'AND generation_id=%s LIMIT %s) bounded',
                       (ORIGIN, generation, MAX_ROWS + 1)).fetchone()
    require(count == raw_count and outbox == dict(n=outbox_count, pending=0),
            'reviewed raw or acknowledged projection count changed')


def _references(db):
    # Match the existing retirement closure: every protected original hash must
    # have its own acknowledged immutable envelope. No reference is rewritten.
    # Store._protect generates lowercase SHA256 identities. With this explicit
    # fail-closed ASCII contract and the fixed ASCII origin, PostgreSQL to_json
    # exactly matches domain.canonical([origin,evidence_id]) without Unicode drift.
    invalid = db.execute("SELECT 1 FROM core.protected_evidence WHERE origin_id=%s "
                         "AND generation_id IN (%s,%s) AND evidence_id !~ '^[0-9a-f]{64}$' LIMIT 1",
                         (ORIGIN, INITIAL_A, FAILED_B)).fetchone()
    require(not invalid, 'protected identity must be a lowercase ASCII SHA256')
    # LIMIT 1 preserves the unique-key semantics and prevents a broad anti-join
    # plan from evaluating the composite JSON predicate across unrelated rows.
    missing = db.execute("""SELECT 1 FROM core.protected_evidence p
        WHERE p.origin_id=%s AND p.generation_id IN (%s,%s)
          AND NOT EXISTS(SELECT 1 FROM LATERAL (
            SELECT candidate.generation_id,candidate.payload,candidate.acknowledged_at
            FROM ops.outbox candidate
            WHERE candidate.origin_id=p.origin_id AND candidate.entity_type='core.protected_evidence'
              AND candidate.entity_id='['||to_json(p.origin_id)::text||','||to_json(p.evidence_id)::text||']'
              AND candidate.content_hash=p.content_hash LIMIT 1) o
            WHERE o.generation_id=p.generation_id
              AND o.payload->>'evidence_id'=p.evidence_id
              AND o.payload->>'origin_id'=p.origin_id
              AND jsonb_populate_record(NULL::core.protected_evidence,o.payload) IS NOT DISTINCT FROM p
              AND o.acknowledged_at IS NOT NULL) LIMIT 1""",
                         (ORIGIN, INITIAL_A, FAILED_B)).fetchone()
    require(not missing, 'protected original hash projection is not acknowledged')


def _prepared_admission(db, a, b):
    saved = {}
    for consumer in (PREPARE_CONSUMER, ADMISSION_CONSUMER):
        row = db.execute('SELECT cursor FROM archive.checkpoints WHERE origin_id=%s '
                         'AND generation_id=%s AND consumer=%s FOR SHARE',
                         (ORIGIN, INITIAL_A, consumer)).fetchone()
        require(row is not None, 'original preparation and admission required')
        saved[consumer] = row['cursor']
    require(saved[PREPARE_CONSUMER] == dict(policy=PREPARE_CONSUMER, initial_a=INITIAL_A,
                                          source_sha=TRIAL_SOURCE), 'original preparation changed')
    admission = saved[ADMISSION_CONSUMER]
    try:
        admitted = datetime.fromisoformat(admission['admitted_at'])
        expires = datetime.fromisoformat(admission['lease_expires_at'])
        valid = (admission['initial_a'] == INITIAL_A and admission['session_id'] == SESSION_ID
                 and type(admission['lease_seconds']) is int and admission['lease_seconds'] == 6600
                 and admitted.tzinfo is not None and expires.tzinfo is not None
                 and (expires - admitted).total_seconds() == 6600
                 and a['started_at'] <= admitted <= a['sealed_at'] == b['started_at'] < expires)
    except (KeyError, TypeError, ValueError):
        valid = False
    require(valid, 'original finite failed03 admission changed')
    return sha256(encoded(saved))


def seal_failed_b(repository, target: SealTarget, *, execute=False):
    """Seal only stopped03 B atomically; retained A and all references stay intact."""
    target.validate()
    require(execute is True and repository.environment == 'preprod'
            and repository.pending_outbox_limit == 10_000, 'explicit bounded failed03 maintenance required')
    with CycleBudget(LIMITS), repository.raw_archive_lock(ORIGIN), \
            repository.structured_sync_lock(ORIGIN), repository.transaction() as db:
        identity = db.execute("""SELECT current_database()='tradebot_pp'
            AND session_user='tradebot_lifecycle' AND count(*)=1
            AND bool_and(singleton AND environment='preprod' AND database_name='tradebot_pp'
                         AND foundation_version=1) AS valid FROM ops.environment_identity""").fetchone()
        require(identity and identity['valid'] is True, 'exact lifecycle database identity required')
        db.execute("SELECT pg_advisory_xact_lock(hashtextextended('tradebot-pp-live-collector',0))")
        writers = db.execute('SELECT * FROM ops.writer_state ORDER BY origin_id FOR UPDATE').fetchall()
        require(all(not row['collector_enabled'] and row['collector_session_id'] is None
                    and row['collector_lease_expires_at'] is None for row in writers),
                'all writers must be durably OFF with null session and lease')
        writer = next((row for row in writers if row['origin_id'] == ORIGIN), None)
        require(writer and writer['generation_id'] == FAILED_B, 'stopped03 writer must remain on B')
        rows = db.execute('SELECT * FROM archive.generations WHERE origin_id=%s '
                          'ORDER BY created_at,generation_id LIMIT 3 FOR UPDATE', (ORIGIN,)).fetchall()
        require(len(rows) == 2 and [r['generation_id'] for r in rows] == [INITIAL_A, FAILED_B]
                and [r['slot'] for r in rows] == ['A', 'B'], 'exact retained A and failed B chain required')
        a, b = rows
        require(a['state'] == 'verified' and a['hold_reason'] is None and a['retired_at'] is None
                and a['seal_count'] == A_RAW_ROWS and a['seal_hash'] == A_SEAL_HASH,
                'reviewed retained A verification changed')
        require(b['retired_at'] is None and b['state'] in ('collecting', 'sealed', 'verified'),
                'failed B is no longer retainable')
        for row in rows:
            _partition(db, row)
        require(not db.execute('SELECT 1 FROM archive.reader_leases WHERE origin_id=%s '
                               'AND expires_at>clock_timestamp() LIMIT 1', (ORIGIN,)).fetchone(),
                'failed03 readers must be drained')
        require(not db.execute('SELECT 1 FROM ops.outbox WHERE origin_id=%s '
                               'AND (acknowledged_at IS NULL OR generation_id IS NULL '
                               'OR generation_id NOT IN (%s,%s)) LIMIT 1',
                               (ORIGIN, INITIAL_A, FAILED_B)).fetchone(), 'failed03 projection closure incomplete')
        _counts(db, INITIAL_A, A_RAW_ROWS, A_ACK_ROWS)
        _counts(db, FAILED_B, B_RAW_ROWS, B_ACK_ROWS)
        _references(db)
        catalog = repository._manifests(db, INITIAL_A)
        prefix = 'raw-v1/' + sha256(ORIGIN.encode()) + '/' + INITIAL_A + '/'
        require(catalog and all(row['manifest_id'] == f'raw.events:{n:012d}'
                and row['object_key'] == prefix + row['sha256'] + '.jsonl.gz'
                and row['verified_at'] is not None
                and row['verification'] == {'method': 'fresh_authenticated_readback'}
                for n, row in enumerate(catalog))
                and validate_manifest_chain(catalog, a) == A_SEAL_HASH,
                'retained A authenticated catalog or coverage changed')
        # This hashes bounded catalog metadata, never rereads or rearchives A raw payloads.
        retained = sha256(encoded(dict(generation=wire(a), manifests=wire(catalog))))
        admission = _prepared_admission(db, a, b)
        previous = db.execute('SELECT cursor FROM archive.checkpoints WHERE origin_id=%s '
                              'AND generation_id=%s AND consumer=%s',
                              (ORIGIN, FAILED_B, CONSUMER)).fetchone()
        expected = dict(policy=CONSUMER, origin_id=ORIGIN, initial_a=INITIAL_A, generation_id=FAILED_B,
                        operation=target.operation, source=target.source, trial_source=TRIAL_SOURCE,
                        previous_writer_epoch=target.writer_epoch, raw_count=B_RAW_ROWS,
                        outbox_count=B_ACK_ROWS, retained_a_sha256=retained,
                        original_admission_sha256=admission, retirement_authorized=False,
                        original_trial_satisfied=False, successor_created=False)
        if previous:
            receipt = previous['cursor']
            require(all(receipt.get(k) == v for k, v in expected.items())
                    and b['state'] in ('sealed', 'verified') and b['sealed_at'] is not None
                    and b['sealed_at'].isoformat() == receipt.get('sealed_at')
                    and b['seal_count'] == B_RAW_ROWS and writer['epoch'] == OFF_EPOCH + 1,
                    'failed03 B seal replay differs from completed operation')
            return dict(status='already_sealed', **receipt)
        require(writer['epoch'] == OFF_EPOCH and b['state'] == 'collecting' and b['hold_reason'] is None
                and all(b[key] is None for key in ('sealed_at', 'seal_count', 'seal_hash', 'verified_at')),
                'failed03 B or stopped writer epoch changed')
        require(not db.execute('SELECT 1 FROM archive.manifests WHERE origin_id=%s AND generation_id=%s LIMIT 1',
                               (ORIGIN, FAILED_B)).fetchone(), 'unsealed B already has archive manifests')
        sealed_at = db.execute('SELECT clock_timestamp() AS at').fetchone()['at']
        require(b['started_at'] is not None and sealed_at >= b['started_at'], 'failed B start is invalid')
        db.execute("UPDATE archive.generations SET state='sealed',sealed_at=%s,seal_count=%s "
                   'WHERE origin_id=%s AND generation_id=%s', (sealed_at, B_RAW_ROWS, ORIGIN, FAILED_B))
        db.execute('UPDATE ops.writer_state SET epoch=epoch+1,updated_at=%s WHERE origin_id=%s',
                   (sealed_at, ORIGIN))
        receipt = dict(expected, sealed_at=sealed_at.isoformat(),
                       txid=db.execute('SELECT txid_current() AS txid').fetchone()['txid'])
        repository._checkpoint(db, b, CONSUMER, receipt)
    return dict(status='sealed_for_failed03_b_archive', **receipt)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    for name in ('generation', 'initial-a', 'trial-source', 'operation', 'source'):
        parser.add_argument('--' + name, required=True)
    for name in ('writer-epoch', 'raw-count', 'outbox-count'):
        parser.add_argument('--' + name, required=True, type=int)
    args = parser.parse_args(argv)
    try:
        target = SealTarget(args.generation, args.initial_a, args.writer_epoch, args.raw_count,
                            args.outbox_count, args.trial_source, args.operation, args.source)
        target.validate()
        require(args.execute and os.getenv('TRADEBOT_PP_FAILED_B_DRAIN') == 'true'
                and os.getenv('TRADEBOT_ENVIRONMENT') == 'preprod'
                and os.getenv('TRADEBOT_DATA_MODE') == 'pp_live' and os.getenv('TRADEBOT_ORIGIN_ID') == ORIGIN
                and os.getenv('TRADEBOT_DATABASE_DSN_FILE') == str(LOCAL_DSN)
                and not os.getenv('TRADEBOT_DATABASE_DSN')
                and not os.path.lexists('/run/secrets/pp_retirement_ticket')
                and all(os.getenv(flag, 'false').lower() in ('false', 'off', '0') for flag in DISABLED),
                'exact default OFF failed03 B maintenance profile required')
        from .connection import connect
        from .migrate import validate_schema
        dsn = private_dsn(LOCAL_DSN)
        def factory():
            return connect(dsn, environment='preprod')
        with factory() as db:
            validate_schema(db, 'preprod')
        result = seal_failed_b(LifecycleRepository(factory), target, execute=True)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps(public_failure(error), sort_keys=True))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
