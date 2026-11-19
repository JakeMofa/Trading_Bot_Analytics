"""Bounded PP receipt-bound envelope repair; no projection writes or local ACKs.

Inventory is local-only. Execution requires an exact reviewed generation, upper
outbox ID, count and canonical envelope digest. Partial cloud commits are retained;
the same scope can be replayed idempotently after reconciliation.
"""
import argparse
import hashlib
import json
import os
import re
import time
import uuid

from .archive_codec import ArchiveIntegrityError, ArchiveLimit, encoded
from .lifecycle import ArchiveWorker, LifecycleHold, LifecycleRepository
from .pp_structured_probe import LOCAL_DSN, ORIGIN, check_environment, private_dsn, retain_revisions

PAGE_ROWS = 50
PAGE_BYTES = 256 * 1024
MAX_ROWS = 10_000
MAX_PAGES = 512
MAX_BYTES = 64 * 1024 * 1024
MAX_SECONDS = 1800
REQUEST_SECONDS = 4


def validate_target(generation, through_id):
    if (str(uuid.UUID(generation)) != generation or type(through_id) is not int
            or through_id < 1):
        raise ValueError('canonical generation and positive upper ID required')


def signature(records):
    digest = hashlib.sha256()
    for record in records:
        digest.update(encoded(record) + b'\n')
    return digest.hexdigest()


class LocalPages:
    def __init__(self, factory, generation, through_id):
        validate_target(generation, through_id)
        self.factory, self.generation, self.through_id = factory, generation, through_id

    def __call__(self, after):
        with self.factory() as db, db.transaction():
            db.execute('SET TRANSACTION READ ONLY')
            db.execute("SET LOCAL statement_timeout='4s'")
            generation = db.execute('''SELECT origin_id,state FROM archive.generations
                WHERE generation_id=%s''', (self.generation,)).fetchone()
            if not generation or generation['origin_id'] != ORIGIN or generation['state'] == 'retired':
                raise LifecycleHold('retained PP generation required')
            rows = LifecycleRepository._pending(db, self.generation, PAGE_ROWS,
                include_acknowledged=True, max_bytes=PAGE_BYTES, after_id=after)
            rows = [row for row in rows if row['id'] <= self.through_id]
            if any(row['origin_id'] != ORIGIN or row['acknowledged_at'] is None for row in rows):
                raise LifecycleHold('only previously acknowledged PP records may be backfilled')
            return ArchiveWorker.structured_records(rows)


def inventory(pages, through_id, *, clock=time.monotonic, deadline=None):
    deadline = deadline if deadline is not None else clock() + MAX_SECONDS
    after = count = size = 0
    digest, scopes = hashlib.sha256(), []
    while after < through_id:
        if clock() >= deadline:
            raise ArchiveLimit('local backfill inventory deadline')
        records = pages(after)
        if not records:
            raise ArchiveIntegrityError('reviewed upper outbox ID absent')
        ids = [row['id'] for row in records]
        if (len(records) > PAGE_ROWS or ids != sorted(set(ids))
                or ids[0] <= after or ids[-1] > through_id):
            raise ArchiveIntegrityError('backfill page order or scope changed')
        page_bytes = len(encoded(records))
        count += len(records)
        size += page_bytes
        if (page_bytes > PAGE_BYTES or count > MAX_ROWS or size > MAX_BYTES
                or len(scopes) >= MAX_PAGES):
            raise ArchiveLimit('backfill inventory exceeds reviewed bounds')
        for record in records:
            digest.update(encoded(record) + b'\n')
        scopes.append((after, ids[-1], len(records), signature(records)))
        after = ids[-1]
    if clock() >= deadline:
        raise ArchiveLimit('local backfill inventory deadline')
    return {'rows': count, 'bytes': size, 'sha256': digest.hexdigest(),
            'pages': len(scopes), 'through_id': through_id}, scopes


def backfill(pages, transport, through_id, *, expected_count, expected_sha256,
             clock=time.monotonic):
    if (type(expected_count) is not int or not 1 <= expected_count <= MAX_ROWS
            or not isinstance(expected_sha256, str)
            or not re.fullmatch('[0-9a-f]{64}', expected_sha256)):
        raise ValueError('reviewed count and SHA256 required')
    started = clock()
    deadline = started + MAX_SECONDS
    local, scopes = inventory(pages, through_id, clock=clock, deadline=deadline)
    if (local['rows'], local['sha256']) != (expected_count, expected_sha256):
        raise ArchiveIntegrityError('reviewed local backfill scope changed')
    completed = 0
    for after, last, count, digest in scopes:
        records = pages(after)
        if (len(records) != count or records[-1]['id'] != last
                or signature(records) != digest):
            raise ArchiveIntegrityError('local backfill page changed')
        def remaining():
            allowance = min(REQUEST_SECONDS, deadline - clock())
            if allowance < 2:
                raise ArchiveLimit('backfill operation deadline')
            return allowance
        # Existing receipt/hash equality and append-only revision insertion are
        # atomic remotely. Fresh independent readback authenticates stored bytes.
        transport.backfill_verified_revisions(records, timeout_seconds=remaining())
        retrieved = transport.read_revisions([row['id'] for row in records],
            max_bytes=PAGE_BYTES, timeout_seconds=remaining())
        if encoded(retrieved) != encoded(records):
            raise ArchiveIntegrityError('fresh backfill readback mismatch')
        if clock() >= deadline:
            raise ArchiveLimit('backfill deadline after remote commit; reconcile scope')
        completed += count
    return {'status': 'verified', 'origin_id': ORIGIN, **local,
            'verified_rows': completed, 'cloud_operations': 2 * len(scopes),
            'elapsed_seconds': round(clock() - started, 3),
            'local_ack_changes': 0, 'projection_changes': 0, 'retirement_authorized': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generation-id', required=True)
    parser.add_argument('--through-id', required=True, type=int)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--expected-count', type=int)
    parser.add_argument('--expected-sha256')
    args = parser.parse_args(argv)
    try:
        validate_target(args.generation_id, args.through_id)
        check_environment(os.environ)
        from .connection import connect
        from .history_v2_transport import HistoryV2PostgresTransport
        from .migrate import validate_schema
        from .pp_history_connection import PPHistoryConnectionFactory
        dsn = private_dsn(LOCAL_DSN)
        def local():
            return connect(dsn, environment='preprod')
        with local() as db:
            if db.execute('SELECT current_user AS role').fetchone()['role'] != 'tradebot_lifecycle':
                raise LifecycleHold('exact lifecycle identity required')
            validate_schema(db, 'preprod')
        pages = LocalPages(local, args.generation_id, args.through_id)
        if args.execute:
            if (os.environ.get('TRADEBOT_PP_REVISION_BACKFILL') != 'true'
                    or not retain_revisions(os.environ)):
                raise LifecycleHold('explicit revision repair and capture opt-ins required')
            transport = HistoryV2PostgresTransport(PPHistoryConnectionFactory(), origin_id=ORIGIN,
                generation_id=args.generation_id, expected_database='postgres',
                expected_role='tradebot_pp_history', retain_revisions=True)
            result = backfill(pages, transport, args.through_id,
                expected_count=args.expected_count, expected_sha256=args.expected_sha256)
        else:
            result, _ = inventory(pages, args.through_id)
            result.update(status='inventory_only', cloud_operations=0, origin_id=ORIGIN,
                          generation_id=args.generation_id, retirement_authorized=False)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps({'status': 'HOLD', 'reason': getattr(error, 'code', type(error).__name__),
            'partial_cloud_commits': 'reconcile_exact_scope', 'local_ack_changes': 0,
            'retirement_authorized': False}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
