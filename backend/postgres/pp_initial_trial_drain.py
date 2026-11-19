"""Explicit initial trial A seal for archive-only maintenance; never rotate or retire.

The existing raw/structured workers own cloud transfer and authenticated ACKs.
This finite local command needs no cloud credential, ticket or collector lease.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
import re
import uuid

from .archive_codec import ArchiveLimits, CycleBudget
from .lifecycle import LifecycleHold, LifecycleRepository
from .pp_raw_archive_probe import OFF_FLAGS
from .rehearsal_profile import TRIAL_ORIGIN as ORIGIN, canonical_anchor, cycle_anchor
from .pp_trial_prepare import CONSUMER as PREPARE_CONSUMER
from .pp_structured_probe import LOCAL_DSN, private_dsn

CONSUMER = 'trial:initial-a-maintenance-seal-v1'
MAX_OUTBOX_ROWS = 10_000
MAX_RAW_ROWS = 128 * 500  # Existing sealed archive catalog, without enlargement.
LIMITS = ArchiveLimits(max_seconds=20)


@dataclass(frozen=True)
class SealTarget:
    generation: str
    initial_a: str
    writer_epoch: int
    raw_count: int
    outbox_count: int
    operation: str
    source: str

    def validate(self):
        canonical_anchor(self.initial_a)
        if (any(not isinstance(value, str) or str(uuid.UUID(value)) != value
                for value in (self.generation, self.operation))
                or self.generation != self.initial_a
                or type(self.outbox_count) is not int or not 1 <= self.outbox_count <= MAX_OUTBOX_ROWS
                or type(self.writer_epoch) is not int or self.writer_epoch < 0
                or type(self.raw_count) is not int or not 1 <= self.raw_count <= MAX_RAW_ROWS
                or not isinstance(self.source, str) or not re.fullmatch('[0-9a-f]{40}', self.source)):
            raise LifecycleHold('exact bounded initial trial seal target required')


def seal_initial_a(repository, target: SealTarget, *, execute=False):
    """Seal the exact stopped initial trial A, preserving its writer pointer and all evidence.

    Locking the writer drains previously admitted Store writes. The same global
    admission lock prevents ON while durable OFF is rechecked. The old writer
    remains on a sealed generation, so normal activation/ingestion cannot resume.
    A retry only acknowledges this identical completed operation; it never reseals.
    """
    target.validate()
    if execute is not True or repository.environment != 'preprod':
        raise LifecycleHold('explicit PP initial trial seal execution required')
    with CycleBudget(LIMITS), repository.raw_archive_lock(ORIGIN), \
            repository.structured_sync_lock(ORIGIN), repository.transaction() as db:
        valid = db.execute("""SELECT current_database()='tradebot_pp'
            AND session_user='tradebot_lifecycle' AND count(*)=1
            AND bool_and(singleton AND environment='preprod' AND database_name='tradebot_pp'
                         AND foundation_version=1) AS valid FROM ops.environment_identity""").fetchone()
        if not valid or valid['valid'] is not True:
            raise LifecycleHold('exact PP database and lifecycle identity required')
        db.execute("SELECT pg_advisory_xact_lock(hashtextextended('tradebot-pp-live-collector',0))")
        writer = db.execute('SELECT * FROM ops.writer_state WHERE origin_id=%s FOR UPDATE',
                            (ORIGIN,)).fetchone()
        if (not writer or writer['generation_id'] != target.generation or writer['collector_enabled']
                or writer['collector_session_id'] is not None
                or writer['collector_lease_expires_at'] is not None):
            raise LifecycleHold('exact trial writer must be durably OFF')
        writers = db.execute("SELECT * FROM ops.writer_state WHERE origin_id LIKE 'pp-live-%' "
                             'ORDER BY origin_id FOR UPDATE').fetchall()
        if any(row['collector_enabled'] or row['collector_session_id'] is not None
               or row['collector_lease_expires_at'] is not None for row in writers):
            raise LifecycleHold('initial trial sealing requires all PP collectors durably OFF')
        generation = db.execute('SELECT * FROM archive.generations WHERE origin_id=%s '
                                'AND generation_id=%s FOR UPDATE', (ORIGIN,target.generation)).fetchone()
        if not generation or generation['slot'] != 'A':
            raise LifecycleHold('exact initial trial A required')
        siblings = db.execute('SELECT generation_id FROM archive.generations WHERE origin_id=%s '
                              'ORDER BY generation_id LIMIT 2', (ORIGIN,)).fetchall()
        prepared = db.execute('SELECT cursor FROM archive.checkpoints WHERE origin_id=%s '
                              'AND generation_id=%s AND consumer=%s',
                              (ORIGIN,target.initial_a,PREPARE_CONSUMER)).fetchone()
        if (len(siblings) != 1 or str(siblings[0]['generation_id']) != target.initial_a
                or not prepared or prepared['cursor'].get('initial_a') != target.initial_a
                or prepared['cursor'].get('policy') != PREPARE_CONSUMER):
            raise LifecycleHold('exact prepared single initial trial A required')
        outbox = db.execute('SELECT count(*) AS n, count(*) FILTER (WHERE acknowledged_at IS NULL) AS pending '
                            'FROM (SELECT acknowledged_at FROM ops.outbox WHERE origin_id=%s '
                            'AND generation_id=%s LIMIT %s) bounded',
                            (ORIGIN,target.generation,MAX_OUTBOX_ROWS+1)).fetchone()
        if outbox['n'] != target.outbox_count or outbox['pending'] != 0:
            raise LifecycleHold('exact initial trial outbox must be fully acknowledged')
        count = db.execute('SELECT count(*) AS n FROM (SELECT 1 FROM raw.events WHERE origin_id=%s '
                           'AND generation_id=%s LIMIT %s) bounded',
                           (ORIGIN,target.generation,MAX_RAW_ROWS+1)).fetchone()['n']
        if count != target.raw_count:
            raise LifecycleHold('reviewed initial trial raw count changed')
        # Check the actual physical child and exact partition bound before seal.
        child = 'events_g_'+target.generation.replace('-','')
        attached = db.execute("""SELECT 1 FROM pg_inherits i JOIN pg_class c ON c.oid=i.inhrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace WHERE i.inhparent='raw.events'::regclass
            AND n.nspname='raw' AND c.relname=%s AND
            pg_get_expr(c.relpartbound,c.oid)=format('FOR VALUES IN (%%L)',%s::text)""",
            (child,target.generation)).fetchone()
        if not attached:
            raise LifecycleHold('exact initial trial raw partition unavailable')
        previous = db.execute('SELECT cursor FROM archive.checkpoints WHERE origin_id=%s '
                              'AND generation_id=%s AND consumer=%s',
                              (ORIGIN,target.generation,CONSUMER)).fetchone()
        identity = dict(origin_id=ORIGIN,initial_a=target.initial_a,
                        operation=target.operation,source=target.source,
                        previous_writer_epoch=target.writer_epoch,raw_count=target.raw_count,
                        outbox_count=target.outbox_count,policy=CONSUMER,retirement_authorized=False,
                        original_trial_satisfied=False)
        if previous:
            receipt = previous['cursor']
            if (any(receipt.get(k) != v for k,v in identity.items())
                    or generation['state'] not in ('sealed','verified')
                    or generation['sealed_at'].isoformat() != receipt.get('sealed_at')
                    or generation['seal_count'] != target.raw_count
                    or writer['epoch'] != target.writer_epoch+1):
                raise LifecycleHold('initial trial seal replay does not match')
            return dict(status='already_sealed',generation_id=target.generation,**receipt)
        if (writer['epoch'] != target.writer_epoch or generation['state'] != 'collecting'
                or any(generation[field] is not None for field in
                       ('sealed_at','seal_count','seal_hash','verified_at','retired_at'))):
            raise LifecycleHold('initial trial A or writer epoch changed')
        if db.execute('SELECT 1 FROM archive.manifests WHERE generation_id=%s LIMIT 1',
                      (target.generation,)).fetchone():
            raise LifecycleHold('unsealed initial trial A already has archive manifests')
        sealed_at = db.execute('SELECT clock_timestamp() AS at').fetchone()['at']
        if generation['started_at'] is None or sealed_at < generation['started_at']:
            raise LifecycleHold('initial trial generation start is invalid')
        db.execute("UPDATE archive.generations SET state='sealed',sealed_at=%s,seal_count=%s "
                   'WHERE origin_id=%s AND generation_id=%s',
                   (sealed_at,target.raw_count,ORIGIN,target.generation))
        db.execute('UPDATE ops.writer_state SET epoch=epoch+1,updated_at=%s WHERE origin_id=%s',
                   (sealed_at,ORIGIN))
        receipt = dict(identity,sealed_at=sealed_at.isoformat(),
                       txid=db.execute('SELECT txid_current() AS txid').fetchone()['txid'])
        repository._checkpoint(db,generation,CONSUMER,receipt)
    return dict(status='sealed_for_initial_trial_archive',generation_id=target.generation,**receipt)



def audit_initial_a(factory, transport, target: SealTarget, *, seal_hash, raw_objects, structured_pages):
    """Bounded independent read-only verification; no successor or trial authority.

    The caller supplies separately staged trial reader transports, never writer
    credentials. No seal window, retirement checkpoint or ticket is created.
    """
    from .archive_codec import ArchiveIntegrityError
    from .cloud_origin_binding import TRIAL_READER
    from .lifecycle import ArchiveWorker
    from .pp_retained_archive_audit import local_snapshot, remote_preflight
    from .pp_retirement_report import bound_catalog
    from .pp_retirement_verify import RetirementTransport, TwoMarketReadbackLimits, inventory
    target.validate()
    if (not isinstance(transport,RetirementTransport) or not isinstance(seal_hash,str) or not re.fullmatch('[0-9a-f]{64}',seal_hash)
            or any(type(n) is not int or n < 1 for n in (raw_objects,structured_pages))
            or raw_objects > 128 or raw_objects+structured_pages+1 > 192
            or transport.origin_id != ORIGIN or transport.generation_id != target.generation
            or transport.structured.expected_role != TRIAL_READER
            or transport.structured.origin_id != ORIGIN
            or transport.structured.generation_id != target.generation
            or getattr(transport.raw,'_reader',False) is not True
            or getattr(getattr(transport.raw,'_origin_binding',None),'origin_id',None) != ORIGIN):
        raise LifecycleHold('exact independent initial trial reader scope required')
    limits=TwoMarketReadbackLimits()
    with CycleBudget(limits) as budget, local_snapshot(factory,budget) as db:
        generation=db.execute('SELECT * FROM archive.generations WHERE origin_id=%s AND generation_id=%s',
                              (ORIGIN,target.generation)).fetchone()
        checkpoint=db.execute('SELECT cursor FROM archive.checkpoints WHERE origin_id=%s '
                              'AND generation_id=%s AND consumer=%s',
                              (ORIGIN,target.generation,CONSUMER)).fetchone()
        receipt=checkpoint['cursor'] if checkpoint else {}
        expected=dict(origin_id=ORIGIN,initial_a=target.initial_a,operation=target.operation,source=target.source,
            previous_writer_epoch=target.writer_epoch,raw_count=target.raw_count,outbox_count=target.outbox_count,
            policy=CONSUMER,retirement_authorized=False,original_trial_satisfied=False)
        writer=db.execute('SELECT * FROM ops.writer_state WHERE origin_id=%s',(ORIGIN,)).fetchone()
        siblings=db.execute('SELECT generation_id FROM archive.generations WHERE origin_id=%s LIMIT 2',
                            (ORIGIN,)).fetchall()
        if (not generation or generation['state']!='verified' or generation['slot']!='A'
                or generation['seal_count']!=target.raw_count or generation['seal_hash']!=seal_hash
                or any(receipt.get(k)!=v for k,v in expected.items())
                or generation['sealed_at'].isoformat()!=receipt.get('sealed_at')
                or not writer or writer['generation_id']!=target.generation
                or writer['epoch']!=target.writer_epoch+1 or writer['collector_enabled']
                or writer['collector_session_id'] is not None or writer['collector_lease_expires_at'] is not None
                or len(siblings)!=1):
            raise LifecycleHold('reviewed initial trial maintenance seal changed')
        if db.execute('SELECT 1 FROM ops.outbox WHERE origin_id=%s AND acknowledged_at IS NULL LIMIT 1',
                      (ORIGIN,)).fetchone():
            raise LifecycleHold('initial trial structured evidence not fully acknowledged')
        actual=db.execute('SELECT count(*) AS n FROM raw.events WHERE origin_id=%s AND generation_id=%s',
                          (ORIGIN,target.generation)).fetchone()['n']
        if actual!=target.raw_count:
            raise LifecycleHold('reviewed initial trial raw count changed')
        manifests=LifecycleRepository._manifests(db,target.generation)
        if len(manifests)!=raw_objects or not bound_catalog(generation,manifests):
            raise LifecycleHold('reviewed initial trial catalog changed')
        estimate=inventory(db,target.generation,manifests,budget,fresh_machine_session=True)
        if (estimate['structured_rows']!=target.outbox_count
                or estimate['structured_pages_examined']!=structured_pages
                or not estimate['structured_inventory_complete'] or estimate['fit']=='exceeds_limits'
                or estimate['requests_minimum']+1>limits.max_requests):
            raise LifecycleHold('reviewed initial trial readback scope exceeds bounds')
        remote_preflight(transport.structured,budget)
        readback=ArchiveWorker(LifecycleRepository(factory),transport,limits).fresh_retirement_readback(
            db,generation,manifests,budget)
        if readback['structured_count']!=target.outbox_count:
            raise ArchiveIntegrityError('initial trial structured readback count changed')
        budget.check()
    return dict(status='initial_trial_archive_audit_verified',origin_id=ORIGIN,generation_id=target.generation,
                evidence_scope='read_only_initial_trial_maintenance_audit',retirement_authorized=False,
                original_trial_satisfied=False,local_role='tradebot_reader',structured_role=TRIAL_READER,
                operation_deadline_met=True,inventory=estimate,**readback)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--generation', required=True)
    parser.add_argument('--initial-a', required=True)
    parser.add_argument('--outbox-count', required=True, type=int)
    parser.add_argument('--writer-epoch', required=True, type=int)
    parser.add_argument('--raw-count', required=True, type=int)
    parser.add_argument('--operation', required=True)
    parser.add_argument('--source', required=True)
    args = parser.parse_args(argv)
    try:
        target = SealTarget(args.generation,args.initial_a,args.writer_epoch,args.raw_count,args.outbox_count,args.operation,args.source)
        target.validate()
        if (not args.execute or os.getenv('TRADEBOT_PP_INITIAL_TRIAL_DRAIN') != 'true'
                or os.getenv('TRADEBOT_ENVIRONMENT') != 'preprod'
                or os.getenv('TRADEBOT_DATA_MODE') != 'pp_live'
                or os.getenv('TRADEBOT_ORIGIN_ID') != ORIGIN
                or cycle_anchor(os.environ) != target.initial_a
                or os.getenv('TRADEBOT_DATABASE_DSN_FILE') != str(LOCAL_DSN)
                or os.getenv('TRADEBOT_DATABASE_DSN')
                or os.path.exists('/run/secrets/pp_retirement_ticket')
                or any(os.getenv(flag,'false').lower() not in ('false','0','off') for flag in OFF_FLAGS)):
            raise LifecycleHold('exact default-OFF initial trial maintenance profile required')
        from .connection import connect
        from .migrate import validate_schema
        dsn=private_dsn(LOCAL_DSN)
        def factory():
            return connect(dsn,environment='preprod')
        with factory() as db:
            if db.execute('SELECT session_user AS login').fetchone()['login'] != 'tradebot_lifecycle':
                raise LifecycleHold('initial trial sealing requires lifecycle login')
            validate_schema(db,'preprod')
        result=seal_initial_a(LifecycleRepository(factory),target,execute=True)
        print(json.dumps(result,sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps(dict(status='HOLD',reason=getattr(error,'code',type(error).__name__),
                              retirement_authorized=False,original_trial_satisfied=False)))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
