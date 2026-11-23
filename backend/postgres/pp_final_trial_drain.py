"""Explicit terminal fresh trial A seal for archive-only maintenance; never rotate or retire.

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
from .rehearsal_profile import NEXT_TRIAL_ORIGIN as ORIGIN, THIRD_TRIAL_ORIGIN, FOURTH_TRIAL_ORIGIN, FIFTH_TRIAL_ORIGIN, canonical_anchor, cycle_anchor
from .pp_trial_prepare import CONSUMER as PREPARE_CONSUMER
from .pp_structured_probe import LOCAL_DSN, private_dsn

CONSUMER = 'trial:final-a-maintenance-seal-v1'
MAINTENANCE_ORIGINS=frozenset({ORIGIN,THIRD_TRIAL_ORIGIN,FOURTH_TRIAL_ORIGIN,FIFTH_TRIAL_ORIGIN})
MAX_OUTBOX_ROWS = 10_000  # Original02 total; pending queue capacity is unchanged.
THIRD_MAX_ACKNOWLEDGED_ROWS = 64_000  # Existing bounded maintenance inventory only.
MAX_RAW_ROWS = 128 * 500  # Existing sealed archive catalog, without enlargement.
LIMITS = ArchiveLimits(max_seconds=20)


def acknowledged_row_limit(origin_id):
    if origin_id not in MAINTENANCE_ORIGINS:
        raise LifecycleHold('exact final trial maintenance origin required')
    return THIRD_MAX_ACKNOWLEDGED_ROWS if origin_id in (THIRD_TRIAL_ORIGIN,FOURTH_TRIAL_ORIGIN,FIFTH_TRIAL_ORIGIN) else MAX_OUTBOX_ROWS


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

    def validate(self, *, origin_id=ORIGIN):
        canonical_anchor(self.initial_a)
        if (any(not isinstance(value, str) or str(uuid.UUID(value)) != value
                for value in (self.generation, self.operation))
                or self.generation == self.initial_a
                or type(self.outbox_count) is not int or not 1 <= self.outbox_count <= acknowledged_row_limit(origin_id)
                or type(self.writer_epoch) is not int or self.writer_epoch < 0
                or type(self.raw_count) is not int or not 1 <= self.raw_count <= MAX_RAW_ROWS
                or not isinstance(self.trial_source,str) or not re.fullmatch('[0-9a-f]{40}',self.trial_source)
                or not isinstance(self.source, str) or not re.fullmatch('[0-9a-f]{40}', self.source)):
            raise LifecycleHold('exact bounded final trial seal target required')



def completed_chain(db, target, *, origin_id=ORIGIN):
    """Read preserved provenance under existing privileges; never read permit secrets."""
    from datetime import datetime, timedelta
    rows=db.execute('SELECT * FROM archive.generations WHERE origin_id=%s '
                    'ORDER BY created_at,generation_id LIMIT 4',(origin_id,)).fetchall()
    if (len(rows)!=3 or [row['slot'] for row in rows]!=['A','B','A']
            or rows[0]['generation_id']!=target.initial_a or rows[2]['generation_id']!=target.generation
            or len({row['generation_id'] for row in rows})!=3):
        raise LifecycleHold('exact complete final A chain required')
    checkpoints={}
    for consumer in (PREPARE_CONSUMER,'rehearsal:two-leg-session'):
        saved=db.execute('SELECT cursor FROM archive.checkpoints WHERE origin_id=%s '
                         'AND generation_id=%s AND consumer=%s',(origin_id,target.initial_a,consumer)).fetchone()
        checkpoints[consumer]=saved['cursor'] if saved else {}
    prepared=checkpoints[PREPARE_CONSUMER];admitted=checkpoints['rehearsal:two-leg-session']
    try:
        admission_valid=(prepared.get('policy')==PREPARE_CONSUMER
            and prepared.get('initial_a')==target.initial_a and prepared.get('source_sha')==target.trial_source
            and admitted.get('initial_a')==target.initial_a and admitted.get('lease_seconds')==6600
            and str(uuid.UUID(admitted['session_id']))==admitted['session_id']
            and datetime.fromisoformat(admitted['admitted_at'])<=rows[0]['sealed_at']
            and datetime.fromisoformat(admitted['lease_expires_at'])>rows[1]['sealed_at'])
    except (KeyError,ValueError,TypeError,AttributeError):
        admission_valid=False
    if not admission_valid:
        raise LifecycleHold('original final trial admission changed or missing')
    for previous,successor in zip(rows,rows[1:]):
        checkpoint=db.execute('SELECT cursor FROM archive.checkpoints WHERE origin_id=%s '
            "AND generation_id=%s AND consumer='retirement:pp-fresh-readback'",
            (origin_id,previous['generation_id'])).fetchone()
        proof=checkpoint['cursor'] if checkpoint else {}
        if (previous['state']!='retired' or previous['retired_at'] is None
                or previous['sealed_at'] is None or previous['verified_at'] is None
                or not previous['sealed_at']<=previous['verified_at']<=previous['retired_at']
                or previous['retired_at']>=previous['sealed_at']+timedelta(minutes=30)
                or previous['sealed_at']!=successor['started_at']
                or proof.get('enabled') is not True or proof.get('policy')!='pp-exact-retirement-v1'
                or proof.get('source')!=target.trial_source or proof.get('seal_hash')!=previous['seal_hash']
                or proof.get('count')!=previous['seal_count'] or proof.get('active')!=successor['generation_id']
                or type(proof.get('txid')) is not int or proof['txid']<1
                or type(proof.get('active_new_rows')) is not int or proof['active_new_rows']<1
                or not isinstance(proof.get('policy_epoch'),str)
                or not re.fullmatch('[0-9a-f]{64}',proof['policy_epoch'])
                or not isinstance(proof.get('history_reader_proof'),str)
                or not re.fullmatch('[0-9a-f]{64}',proof['history_reader_proof'])):
            raise LifecycleHold('two actual deadline-bound retirements required before final seal')
        child='events_g_'+previous['generation_id'].replace('-','')
        if (previous['partition_name']!=child or db.execute('SELECT to_regclass(%s) AS child',
                ('raw.'+child,)).fetchone()['child'] is not None):
            raise LifecycleHold('retired predecessor partition must be absent')
    return rows

def seal_final_a(repository, target: SealTarget, *, execute=False, origin_id=ORIGIN):
    """Seal the exact stopped terminal fresh trial A, preserving its writer pointer and all evidence.

    Locking the writer drains previously admitted Store writes. The same global
    admission lock prevents ON while durable OFF is rechecked. The old writer
    remains on a sealed generation, so normal activation/ingestion cannot resume.
    A retry only acknowledges this identical completed operation; it never reseals.
    """
    target.validate(origin_id=origin_id)
    if execute is not True or repository.environment != 'preprod' or origin_id not in MAINTENANCE_ORIGINS:
        raise LifecycleHold('explicit PP final trial seal execution required')
    with CycleBudget(LIMITS), repository.raw_archive_lock(origin_id), \
            repository.structured_sync_lock(origin_id), repository.transaction() as db:
        valid = db.execute("""SELECT current_database()='tradebot_pp'
            AND session_user='tradebot_lifecycle' AND count(*)=1
            AND bool_and(singleton AND environment='preprod' AND database_name='tradebot_pp'
                         AND foundation_version=1) AS valid FROM ops.environment_identity""").fetchone()
        if not valid or valid['valid'] is not True:
            raise LifecycleHold('exact PP database and lifecycle identity required')
        db.execute("SELECT pg_advisory_xact_lock(hashtextextended('tradebot-pp-live-collector',0))")
        writer = db.execute('SELECT * FROM ops.writer_state WHERE origin_id=%s FOR UPDATE',
                            (origin_id,)).fetchone()
        if (not writer or writer['generation_id'] != target.generation or writer['collector_enabled']
                or writer['collector_session_id'] is not None
                or writer['collector_lease_expires_at'] is not None):
            raise LifecycleHold('exact trial writer must be durably OFF')
        writers = db.execute("SELECT * FROM ops.writer_state WHERE origin_id LIKE 'pp-live-%' "
                             'ORDER BY origin_id FOR UPDATE').fetchall()
        if any(row['collector_enabled'] or row['collector_session_id'] is not None
               or row['collector_lease_expires_at'] is not None for row in writers):
            raise LifecycleHold('final trial sealing requires all PP collectors durably OFF')
        generation = db.execute('SELECT * FROM archive.generations WHERE origin_id=%s '
                                'AND generation_id=%s FOR UPDATE', (origin_id,target.generation)).fetchone()
        if not generation or generation['slot'] != 'A':
            raise LifecycleHold('exact terminal fresh trial A required')
        completed_chain(db,target,origin_id=origin_id)
        outbox = db.execute('SELECT count(*) AS n, count(*) FILTER (WHERE acknowledged_at IS NULL) AS pending '
                            'FROM (SELECT acknowledged_at FROM ops.outbox WHERE origin_id=%s '
                            'AND generation_id=%s LIMIT %s) bounded',
                            (origin_id,target.generation,acknowledged_row_limit(origin_id)+1)).fetchone()
        if outbox['n'] != target.outbox_count or outbox['pending'] != 0:
            raise LifecycleHold('exact final trial outbox must be fully acknowledged')
        count = db.execute('SELECT count(*) AS n FROM (SELECT 1 FROM raw.events WHERE origin_id=%s '
                           'AND generation_id=%s LIMIT %s) bounded',
                           (origin_id,target.generation,MAX_RAW_ROWS+1)).fetchone()['n']
        if count != target.raw_count:
            raise LifecycleHold('reviewed final trial raw count changed')
        # Check the actual physical child and exact partition bound before seal.
        child = 'events_g_'+target.generation.replace('-','')
        attached = db.execute("""SELECT 1 FROM pg_inherits i JOIN pg_class c ON c.oid=i.inhrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace WHERE i.inhparent='raw.events'::regclass
            AND n.nspname='raw' AND c.relname=%s AND
            pg_get_expr(c.relpartbound,c.oid)=format('FOR VALUES IN (%%L)',%s::text)""",
            (child,target.generation)).fetchone()
        if not attached or generation['partition_name']!=child:
            raise LifecycleHold('exact final trial raw partition unavailable')
        previous = db.execute('SELECT cursor FROM archive.checkpoints WHERE origin_id=%s '
                              'AND generation_id=%s AND consumer=%s',
                              (origin_id,target.generation,CONSUMER)).fetchone()
        identity = dict(origin_id=origin_id,initial_a=target.initial_a,
                        operation=target.operation,source=target.source,trial_source=target.trial_source,
                        previous_writer_epoch=target.writer_epoch,raw_count=target.raw_count,
                        outbox_count=target.outbox_count,policy=CONSUMER,two_leg_retirement_chain_verified=True,retirement_authorized=False,
                        original_trial_satisfied=False)
        if previous:
            receipt = previous['cursor']
            if (any(receipt.get(k) != v for k,v in identity.items())
                    or generation['state'] not in ('sealed','verified')
                    or generation['sealed_at'].isoformat() != receipt.get('sealed_at')
                    or generation['seal_count'] != target.raw_count
                    or writer['epoch'] != target.writer_epoch+1):
                raise LifecycleHold('final trial seal replay does not match')
            return dict(status='already_sealed',generation_id=target.generation,**receipt)
        if (writer['epoch'] != target.writer_epoch or generation['state'] != 'collecting'
                or any(generation[field] is not None for field in
                       ('sealed_at','seal_count','seal_hash','verified_at','retired_at'))):
            raise LifecycleHold('terminal fresh trial A or writer epoch changed')
        if db.execute('SELECT 1 FROM archive.manifests WHERE generation_id=%s LIMIT 1',
                      (target.generation,)).fetchone():
            raise LifecycleHold('unsealed terminal fresh trial A already has archive manifests')
        sealed_at = db.execute('SELECT clock_timestamp() AS at').fetchone()['at']
        if generation['started_at'] is None or sealed_at < generation['started_at']:
            raise LifecycleHold('final trial generation start is invalid')
        db.execute("UPDATE archive.generations SET state='sealed',sealed_at=%s,seal_count=%s "
                   'WHERE origin_id=%s AND generation_id=%s',
                   (sealed_at,target.raw_count,origin_id,target.generation))
        db.execute('UPDATE ops.writer_state SET epoch=epoch+1,updated_at=%s WHERE origin_id=%s',
                   (sealed_at,origin_id))
        receipt = dict(identity,sealed_at=sealed_at.isoformat(),
                       txid=db.execute('SELECT txid_current() AS txid').fetchone()['txid'])
        repository._checkpoint(db,generation,CONSUMER,receipt)
    return dict(status='sealed_for_final_trial_archive',generation_id=target.generation,**receipt)



def audit_final_a(factory, transport, target: SealTarget, *, seal_hash, raw_objects, structured_pages, origin_id=ORIGIN):
    """Bounded independent read-only verification; no successor or trial authority.

    The caller supplies separately staged trial reader transports, never writer
    credentials. No seal window, retirement checkpoint or ticket is created.
    """
    from .archive_codec import ArchiveIntegrityError
    from .cloud_origin_binding import cloud_binding
    if origin_id not in MAINTENANCE_ORIGINS:raise LifecycleHold('exact final trial audit origin required')
    TRIAL_READER=cloud_binding(origin_id).reader_role
    from .lifecycle import ArchiveWorker
    from .pp_retained_archive_audit import local_snapshot, remote_preflight
    from .pp_retirement_report import bound_catalog
    from .pp_retirement_verify import RetirementTransport, TwoMarketReadbackLimits, inventory
    target.validate(origin_id=origin_id)
    if (not isinstance(transport,RetirementTransport) or not isinstance(seal_hash,str) or not re.fullmatch('[0-9a-f]{64}',seal_hash)
            or any(type(n) is not int or n < 1 for n in (raw_objects,structured_pages))
            or raw_objects > 128 or raw_objects+structured_pages+1 > 192
            or transport.origin_id != origin_id or transport.generation_id != target.generation
            or transport.structured.expected_role != TRIAL_READER
            or transport.structured.origin_id != origin_id
            or transport.structured.generation_id != target.generation
            or getattr(transport.raw,'_reader',False) is not True
            or getattr(getattr(transport.raw,'_origin_binding',None),'origin_id',None) != origin_id):
        raise LifecycleHold('exact independent final trial reader scope required')
    limits=TwoMarketReadbackLimits()
    with CycleBudget(limits) as budget, local_snapshot(factory,budget) as db:
        generation=db.execute('SELECT * FROM archive.generations WHERE origin_id=%s AND generation_id=%s',
                              (origin_id,target.generation)).fetchone()
        checkpoint=db.execute('SELECT cursor FROM archive.checkpoints WHERE origin_id=%s '
                              'AND generation_id=%s AND consumer=%s',
                              (origin_id,target.generation,CONSUMER)).fetchone()
        receipt=checkpoint['cursor'] if checkpoint else {}
        expected=dict(origin_id=origin_id,initial_a=target.initial_a,operation=target.operation,source=target.source,trial_source=target.trial_source,
            previous_writer_epoch=target.writer_epoch,raw_count=target.raw_count,outbox_count=target.outbox_count,
            policy=CONSUMER,two_leg_retirement_chain_verified=True,retirement_authorized=False,original_trial_satisfied=False)
        writer=db.execute('SELECT * FROM ops.writer_state WHERE origin_id=%s',(origin_id,)).fetchone()
        completed_chain(db,target,origin_id=origin_id)
        if (not generation or generation['state']!='verified' or generation['slot']!='A'
                or generation['seal_count']!=target.raw_count or generation['seal_hash']!=seal_hash
                or any(receipt.get(k)!=v for k,v in expected.items())
                or generation['sealed_at'].isoformat()!=receipt.get('sealed_at')
                or not writer or writer['generation_id']!=target.generation
                or writer['epoch']!=target.writer_epoch+1 or writer['collector_enabled']
                or writer['collector_session_id'] is not None or writer['collector_lease_expires_at'] is not None):
            raise LifecycleHold('reviewed final trial maintenance seal changed')
        if db.execute('SELECT 1 FROM ops.outbox WHERE origin_id=%s AND acknowledged_at IS NULL LIMIT 1',
                      (origin_id,)).fetchone():
            raise LifecycleHold('final trial structured evidence not fully acknowledged')
        actual=db.execute('SELECT count(*) AS n FROM raw.events WHERE origin_id=%s AND generation_id=%s',
                          (origin_id,target.generation)).fetchone()['n']
        if actual!=target.raw_count:
            raise LifecycleHold('reviewed final trial raw count changed')
        manifests=LifecycleRepository._manifests(db,target.generation)
        if len(manifests)!=raw_objects or not bound_catalog(generation,manifests):
            raise LifecycleHold('reviewed final trial catalog changed')
        estimate=inventory(db,target.generation,manifests,budget,fresh_machine_session=True)
        if (estimate['structured_rows']!=target.outbox_count
                or estimate['structured_pages_examined']!=structured_pages
                or not estimate['structured_inventory_complete'] or estimate['fit']=='exceeds_limits'
                or estimate['requests_minimum']+1>limits.max_requests):
            raise LifecycleHold('reviewed final trial readback scope exceeds bounds')
        remote_preflight(transport.structured,budget)
        readback=ArchiveWorker(LifecycleRepository(factory),transport,limits).fresh_retirement_readback(
            db,generation,manifests,budget)
        if readback['structured_count']!=target.outbox_count:
            raise ArchiveIntegrityError('final trial structured readback count changed')
        budget.check()
    return dict(status='final_trial_archive_audit_verified',origin_id=origin_id,generation_id=target.generation,
                evidence_scope='read_only_final_trial_maintenance_audit',retirement_authorized=False,
                original_trial_satisfied=False,local_role='tradebot_reader',structured_role=TRIAL_READER,
                operation_deadline_met=True,inventory=estimate,**readback)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin',choices=sorted(MAINTENANCE_ORIGINS),default=ORIGIN)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--generation', required=True)
    parser.add_argument('--initial-a', required=True)
    parser.add_argument('--outbox-count', required=True, type=int)
    parser.add_argument('--writer-epoch', required=True, type=int)
    parser.add_argument('--raw-count', required=True, type=int)
    parser.add_argument('--operation', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--trial-source', required=True)
    args = parser.parse_args(argv)
    try:
        target = SealTarget(args.generation,args.initial_a,args.writer_epoch,args.raw_count,args.outbox_count,args.trial_source,args.operation,args.source)
        target.validate(origin_id=args.origin)
        if (not args.execute or os.getenv('TRADEBOT_PP_FINAL_TRIAL_DRAIN') != 'true'
                or os.getenv('TRADEBOT_ENVIRONMENT') != 'preprod'
                or os.getenv('TRADEBOT_DATA_MODE') != 'pp_live'
                or os.getenv('TRADEBOT_ORIGIN_ID') != args.origin
                or cycle_anchor(os.environ) != target.initial_a
                or os.getenv('TRADEBOT_DATABASE_DSN_FILE') != str(LOCAL_DSN)
                or os.getenv('TRADEBOT_DATABASE_DSN')
                or os.path.exists('/run/secrets/pp_retirement_ticket')
                or any(os.getenv(flag,'false').lower() not in ('false','0','off') for flag in OFF_FLAGS)):
            raise LifecycleHold('exact default-OFF final trial maintenance profile required')
        from .connection import connect
        from .migrate import validate_schema
        dsn=private_dsn(LOCAL_DSN)
        def factory():
            return connect(dsn,environment='preprod')
        with factory() as db:
            if db.execute('SELECT session_user AS login').fetchone()['login'] != 'tradebot_lifecycle':
                raise LifecycleHold('final trial sealing requires lifecycle login')
            validate_schema(db,'preprod')
        result=seal_final_a(LifecycleRepository(factory),target,execute=True,origin_id=args.origin)
        print(json.dumps(result,sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps(dict(status='HOLD',reason=getattr(error,'code',type(error).__name__),
                              retirement_authorized=False,original_trial_satisfied=False)))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
