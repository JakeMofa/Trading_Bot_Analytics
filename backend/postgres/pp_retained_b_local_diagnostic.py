"""Read-only timings for the exact stopped trial06 B first structured page."""
import json
from datetime import timezone
from pathlib import Path

from .archive_codec import ArchiveIntegrityError, encoded, sha256
from .connection import connect
from .lifecycle import ArchiveWorker, LifecycleRepository
from .pp_retirement_report import bound_catalog
from .pp_retirement_verify import retirement_failure
from .pp_structured_probe import private_dsn
from .rehearsal_profile import SIXTH_TRIAL_ORIGIN
from .retirement_accounting import accounted, measured_context, phase


SEALED = 'e07e981a-2617-43ac-a050-fcf4455a12f1'
SUCCESSOR = '77ee5f30-7c3d-4285-8807-7d5543cf4bde'
SEAL_HASH = 'c89d16e6066a3f33f0ce5ee1902a754ff2397d84d9c6c901b4fbb3c2cd51a85b'
SEALED_AT = '2026-11-23T23:00:29.987862+00:00'
PAGE_ROWS = 500
PAGE_BYTES = 4 * 1024 * 1024
LOCAL_DSN = Path('/run/secrets/pp_retained_reader_dsn')


def require(condition, reason):
    if not condition:
        raise ArchiveIntegrityError(reason)


def local_one(db, name, query, parameters=None):
    with phase(name):
        return db.execute(query, parameters).fetchone()


@accounted
def diagnose(factory):
    with phase('retained_local_connect'):
        connection = factory()
    with connection as db, measured_context(
        db.transaction(), enter='retained_transaction_begin', finish='retained_transaction_finish',
    ):
        for name, statement in (
            ('retained_snapshot_mode', 'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'),
            ('retained_transaction_timeout', "SET LOCAL transaction_timeout='3500ms'"),
            ('retained_statement_timeout', "SET LOCAL statement_timeout='2s'"),
            ('retained_lock_timeout', "SET LOCAL lock_timeout='250ms'"),
        ):
            with phase(name):
                db.execute(statement)
        identity = local_one(db, 'retained_local_identity',
            "SELECT current_user AS role, current_database() AS database, "
            "current_setting('transaction_read_only') AS read_only")
        require(identity == dict(role='tradebot_reader', database='tradebot_pp', read_only='on'),
                'exact local PP reader required')
        active = local_one(db, 'retained_writer_off',
            'SELECT 1 FROM ops.writer_state WHERE collector_enabled OR collector_session_id IS NOT NULL '
            'OR collector_lease_expires_at IS NOT NULL LIMIT 1')
        require(active is None, 'PP writer is not quiescent')
        writer = local_one(db, 'retained_writer_pointer',
            'SELECT generation_id, epoch FROM ops.writer_state WHERE origin_id=%s',
            (SIXTH_TRIAL_ORIGIN,))
        require(writer == dict(generation_id=SUCCESSOR, epoch=5), 'retained writer changed')
        generation = local_one(db, 'retained_generation',
            'SELECT * FROM archive.generations WHERE origin_id=%s AND generation_id=%s',
            (SIXTH_TRIAL_ORIGIN, SEALED))
        require(generation and generation['slot'] == 'B' and generation['state'] == 'verified'
                and not generation['hold_reason'] and generation['retired_at'] is None
                and generation['seal_count'] == 24896 and generation['seal_hash'] == SEAL_HASH
                and generation['sealed_at'].astimezone(timezone.utc).isoformat() == SEALED_AT,
                'original retained seal changed')
        attached = local_one(db, 'retained_attachment',
            """SELECT EXISTS (SELECT FROM pg_inherits i
               WHERE i.inhparent='raw.events'::regclass AND i.inhrelid=to_regclass(%s)
               AND pg_get_expr((SELECT relpartbound FROM pg_class WHERE oid=i.inhrelid), i.inhrelid)
               =format('FOR VALUES IN (%%L)',%s::text)) AS present""",
            ('raw.' + generation['partition_name'], SEALED))
        require(attached['present'] is True, 'retained B partition is unattached')
        with phase('retained_manifest_query'):
            catalog = LifecycleRepository._manifests(db, SEALED)
        with phase('retained_manifest_integrity'):
            require(len(catalog) == 50 and bound_catalog(generation, catalog),
                    'original archive catalog changed')
        coverage = local_one(db, 'retained_outbox_coverage',
            """SELECT count(*) AS rows, count(*) FILTER (WHERE acknowledged_at IS NULL) AS pending
               FROM (SELECT id, acknowledged_at FROM ops.outbox
                     WHERE origin_id=%s AND generation_id=%s LIMIT 27529) AS bounded""",
            (SIXTH_TRIAL_ORIGIN, SEALED))
        require(coverage == dict(rows=27528, pending=0), 'original outbox coverage changed')
        rows = LifecycleRepository._pending(db, SEALED, PAGE_ROWS, include_acknowledged=True,
                                            max_bytes=PAGE_BYTES)
    with phase('retained_page_canonicalize'):
        records = ArchiveWorker.structured_records(rows)
        ids = [row['id'] for row in records]
        require(len(ids) == PAGE_ROWS and ids == sorted(set(ids)) and ids[0] > 0
                and all(row['origin_id'] == SIXTH_TRIAL_ORIGIN and row['generation_id'] == SEALED
                        for row in records), 'first-page identities changed')
        canonical = encoded(records)
        require(len(canonical) <= PAGE_BYTES, 'first page exceeds byte limit')
        return dict(status='local_page_verified', rows=len(records), canonical_bytes=len(canonical),
                    ordered_ids_sha256=sha256(encoded(ids)), canonical_sha256=sha256(canonical))


def diagnostic_report(factory):
    try:
        result = diagnose(factory)
    except Exception as error:
        result = retirement_failure(error)
    return dict(result, stage='retained_b_local', origin_id=SIXTH_TRIAL_ORIGIN,
                generation_id=SEALED, hosted_requests=0, retirement_authorized=False)


def main():
    result = diagnostic_report(lambda: connect(private_dsn(LOCAL_DSN), readonly=True))
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'local_page_verified' else 1


if __name__ == '__main__':
    raise SystemExit(main())
