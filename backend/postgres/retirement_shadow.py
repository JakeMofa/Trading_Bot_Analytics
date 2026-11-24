"""Native PostgreSQL rehearsal for resumable read-back; isolated generated origins only.

The fixture supplies a trusted, pinned destination view spanning raw bytes,
structured revisions and all mutable dependencies. Live transports do not yet
supply this contract. This module never consumes a permit or drops a partition.
"""
from dataclasses import replace
import hmac
from datetime import timedelta
import re

from .archive_codec import ArchiveIntegrityError, CycleBudget, encoded, read_verified, sha256, wire
from .lifecycle import ArchiveWorker, LifecycleHold, validate_manifest_chain
from .pp_retirement_report import active_sample, bound_catalog


JOURNAL_DDL = """CREATE TABLE shadow_qualification.verified_batches(
    scope text NOT NULL, batch text NOT NULL, version text NOT NULL, local_digest text NOT NULL, proof text NOT NULL,
    PRIMARY KEY(scope,batch))"""


def trusted_version(view, batch):
    value = view.version(batch)
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
        raise LifecycleHold('destination version unavailable')
    return value


def verify_shadow(repository, transport, journal_factory, target, *, expected_origin, source, limits, batch_budget, journal_key):
    target.validate()
    if (repository.environment != 'preprod' or not isinstance(expected_origin, str)
            or not expected_origin.startswith('generated-') or transport.origin_id != expected_origin
            or str(transport.generation_id) != target.sealed
            or not re.fullmatch('[0-9a-f]{40}', source)
            or not isinstance(journal_key,bytes) or len(journal_key) < 32
            or type(batch_budget) is not int or batch_budget < 1):
        raise LifecycleHold('isolated shadow scope required')
    reused = fresh = 0
    observed = {}
    # Each receipt uses an independent committed journal transaction. Neither an
    # interruption nor rolling back the local read transaction erases prior work.
    with CycleBudget(limits) as budget, repository.retirement(
            target.sealed, expected_origin=expected_origin) as (db, gen, manifests):
        sampled = budget.clock()
        wall_now = db.execute("SELECT clock_timestamp() AS now").fetchone()["now"]
        if not gen["sealed_at"] or gen["sealed_at"] > wall_now:
            raise LifecycleHold("invalid seal time")
        expires = gen["sealed_at"] + timedelta(minutes=30)
        budget.deadline = min(budget.deadline, sampled + (expires - wall_now).total_seconds())
        budget.check()
        digest = validate_manifest_chain(manifests, gen)
        before = active_sample(db, expected_origin)
        if (not bound_catalog(gen, manifests) or gen['origin_id'] != expected_origin or digest != target.seal_hash
                or digest != gen['seal_hash'] or gen['seal_count'] != target.count
                or not before or before['generation_id'] != target.collecting):
            raise LifecycleHold('shadow target changed')
        scope = sha256(encoded(['shadow-v1', source, expected_origin, target.sealed,
                                target.collecting, digest, target.count, limits.max_rows,
                                limits.max_decoded_bytes]))
        with transport.pin_shadow_versions() as view, journal_factory() as journal:
            # A nested psycopg transaction is a savepoint and would lose the
            # checkpoints on interruption of the surrounding connection.
            from psycopg.pq import TransactionStatus
            if journal.info.transaction_status != TransactionStatus.IDLE:
                raise LifecycleHold('dedicated idle journal connection required')

            def examine(batch, local_digest, compare):
                nonlocal fresh, reused
                budget.check()
                version = trusted_version(view, batch)
                message = encoded([scope, batch, version, local_digest])
                proof = hmac.digest(journal_key, message, 'sha256').hex()
                with journal.transaction():
                    row = journal.execute("""SELECT version,local_digest,proof FROM
                        shadow_qualification.verified_batches WHERE scope=%s AND batch=%s""",
                        (scope, batch)).fetchone()
                if row:
                    if (row['version'], row['local_digest']) != (version, local_digest):
                        raise ArchiveIntegrityError('shadow receipt version or source changed')
                    if not hmac.compare_digest(row['proof'], proof):
                        raise ArchiveIntegrityError('invalid shadow journal signature')
                    reused += 1
                else:
                    if fresh >= batch_budget:
                        return False
                    compare()
                    budget.check()
                    if trusted_version(view, batch) != version:
                        raise ArchiveIntegrityError('destination changed during shadow read')
                    with journal.transaction():
                        journal.execute("""INSERT INTO shadow_qualification.verified_batches
                            (scope,batch,version,local_digest,proof) VALUES (%s,%s,%s,%s,%s)""",
                            (scope, batch, version, local_digest, proof))
                    fresh += 1
                observed[batch] = version
                return True

            def pages():
                for manifest in manifests:
                    local, _ = repository._page(db, target.sealed, manifest['coverage']['after'],
                        replace(limits, max_rows=max(1, manifest['row_count'])))
                    local_raw = wire(local)
                    def compare_raw():
                        if read_verified(transport, manifest, budget) != local_raw:
                            raise ArchiveIntegrityError('shadow local raw bytes differ')
                    yield manifest['manifest_id'], sha256(encoded(local_raw)), compare_raw
                after = 0
                while True:
                    budget.check()
                    rows = repository._pending(db, target.sealed, limits.max_rows,
                        include_acknowledged=True, max_bytes=limits.max_decoded_bytes, after_id=after)
                    if not rows:
                        return
                    records = ArchiveWorker.structured_records(rows)
                    ids = [row['id'] for row in records]
                    if (ids != sorted(set(ids)) or ids[0] <= after or any(
                            row['origin_id'] != expected_origin or
                            str(row['generation_id']) != target.sealed for row in records)):
                        raise ArchiveIntegrityError('invalid shadow page')
                    canonical = encoded(records)
                    if len(canonical) > limits.max_decoded_bytes:
                        raise ArchiveIntegrityError('oversize shadow page')
                    def compare_structured():
                        actual = transport.read_structured_authenticated(records,
                            max_bytes=limits.max_decoded_bytes,
                            timeout_seconds=budget.request(len(canonical)))
                        if encoded(actual) != canonical:
                            raise ArchiveIntegrityError('shadow structured mismatch')
                    yield f'structured:{after}:{ids[-1]}', sha256(canonical), compare_structured
                    after = ids[-1]

            complete = all(examine(*page) for page in pages())
            if complete:
                with journal.transaction():
                    prior = journal.execute("""SELECT batch FROM shadow_qualification.verified_batches
                        WHERE scope=%s""", (scope,)).fetchall()
                if any(trusted_version(view, batch) != version for batch, version in observed.items()):
                    raise ArchiveIntegrityError('destination changed during reconciliation')
                if set(observed) != {row['batch'] for row in prior}:
                    raise ArchiveIntegrityError('shadow page inventory changed')
            finished = active_sample(db, expected_origin)
            if not finished or finished['generation_id'] != target.collecting:
                raise LifecycleHold('active writer changed')
            budget.check()
    return dict(status='shadow_complete' if complete else 'shadow_paused',
                historical_only=True, retirement_authorized=False, fresh_batches=fresh,
                reused_batches=reused, batches_covered=len(observed), source=source, scope=scope,
                seal_sha256=digest)
