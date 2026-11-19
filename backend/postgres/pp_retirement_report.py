"""Read-only PP retirement evidence. A diagnostic report never permits removal."""
import argparse
from contextlib import contextmanager
import json
import time
import uuid

from .archive_codec import ArchiveError, sha256
from .connection import connect
from .lifecycle import LifecycleHold, LifecycleRepository, validate_manifest_chain
from .pp_structured_probe import LOCAL_DSN, ORIGIN, private_dsn


@contextmanager
def snapshot(factory):
    with factory() as db:
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        db.execute("SET LOCAL transaction_timeout='5s'")
        db.execute("SET LOCAL statement_timeout='2s'")
        db.execute("SET LOCAL lock_timeout='250ms'")
        yield db


def active_sample(db, origin):
    return db.execute("""SELECT g.generation_id,g.slot,
        (SELECT count(*) FROM raw.events e WHERE e.origin_id=g.origin_id
            AND e.generation_id=g.generation_id) AS committed_rows
        FROM ops.writer_state w JOIN archive.generations g USING(origin_id,generation_id)
        WHERE w.origin_id=%s AND g.state='collecting'""", (origin,)).fetchone()


def bound_catalog(generation, manifests):
    if generation['state'] != 'verified' or not generation['verified_at']:
        return False
    prefix = 'raw-v1/' + sha256(generation['origin_id'].encode()) + '/' + generation['generation_id'] + '/'
    for index, item in enumerate(manifests):
        if (item['manifest_id'] != f'raw.events:{index:012d}' or
                item['object_key'] != prefix + item['sha256'] + '.jsonl.gz' or
                not item['verified_at'] or item['verification'] != {'method': 'fresh_authenticated_readback'}):
            return False
    try:
        return validate_manifest_chain(manifests, generation) == generation['seal_hash']
    except (ArchiveError, KeyError, TypeError):
        return False


def report(factory, generation_id, *, origin=ORIGIN, between_samples=time.sleep):
    if str(uuid.UUID(generation_id)) != generation_id:
        raise ValueError('canonical sealed generation UUID required')
    with snapshot(factory) as db:
        before = active_sample(db, origin)
    between_samples(2)
    with snapshot(factory) as db:
        now = active_sample(db, origin)
        g = db.execute("""SELECT * FROM archive.generations WHERE origin_id=%s AND generation_id=%s
            AND state IN ('sealed','verified')""", (origin,generation_id)).fetchone()
        if not g:
            raise LifecycleHold('exact sealed generation unavailable')
        manifests = LifecycleRepository._manifests(db, generation_id)
        checks = db.execute("""SELECT
            (SELECT count(*) FROM raw.events WHERE generation_id=%(id)s) AS retained_rows,
            (SELECT count(*) FROM archive.reader_leases WHERE generation_id=%(id)s
                AND expires_at>clock_timestamp()) AS active_reader_leases,
            (SELECT count(*) FROM ops.outbox WHERE generation_id=%(id)s
                AND acknowledged_at IS NULL) AS pending_structured,
            (SELECT count(*) FROM core.protected_evidence p WHERE p.generation_id=%(id)s
                AND NOT EXISTS(SELECT FROM ops.outbox o WHERE o.origin_id=p.origin_id
                  AND o.generation_id=p.generation_id AND o.entity_type='core.protected_evidence'
                  AND o.content_hash=p.content_hash AND o.payload->>'evidence_id'=p.evidence_id
                  AND o.payload->>'origin_id'=p.origin_id AND o.acknowledged_at IS NOT NULL))
                AS unmatched_protected_evidence""", {'id':generation_id}).fetchone()
    advancing = bool(before and now and before['generation_id'] == now['generation_id']
                     and now['slot'] != g['slot'] and now['committed_rows'] > before['committed_rows'])
    coverage = bound_catalog(g, manifests)
    holds = ['fresh_cloud_readback_at_removal_unproven','privileged_cloud_mutation_fence_unproven',
             'archive_backed_replay_after_live_removal_unproven','exclusive_reader_drain_unproven',
             'pp_live_retirement_disabled']
    for failed, reason in ((not advancing,'opposite_slot_advancement_unproven'),
            (not coverage,'exact_verified_catalog_missing'),
            (checks['retained_rows'] != g['seal_count'],'changed_raw_count'),
            (checks['active_reader_leases'],'active_reader_leases'),
            (checks['pending_structured'],'pending_structured'),
            (checks['unmatched_protected_evidence'],'unmatched_protected_evidence')):
        if failed:
            holds.append(reason)
    return {'status':'HOLD','retirement_authorized':False,'origin_id':origin,
            'generation_id':generation_id,'sealed_slot':g['slot'],'seal_count':g['seal_count'],
            'catalog_digest':g['seal_hash'],'catalog_readback_bound':coverage,'manifest_count':len(manifests),
            'active_sample_before':before,'active_sample_after':now,'opposite_slot_advanced':advancing,
            **checks,'holds':holds}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('generation_id')
    args = parser.parse_args()
    try:
        dsn = private_dsn(LOCAL_DSN)
        factory = lambda: connect(dsn, environment='preprod', readonly=True)
        print(json.dumps(report(factory,args.generation_id)))
    except Exception as error:
        print(json.dumps({'status':'HOLD','retirement_authorized':False,'reason':type(error).__name__}))
        return 1
    return 0  # Report produced; retirement_authorized stays false.


if __name__ == '__main__':
    raise SystemExit(main())
