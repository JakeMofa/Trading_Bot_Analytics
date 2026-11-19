"""Seal only final fresh A after both exact trial retirements and durable OFF.

The existing raw/structured workers own cloud transfer and authenticated ACKs.
This finite local command needs no cloud credential, ticket or collector lease.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
import re
from datetime import timedelta

from .archive_codec import ArchiveLimits, CycleBudget, encoded, sha256
from .lifecycle import LifecycleHold, LifecycleRepository
from .pp_raw_archive_probe import OFF_FLAGS
from .rehearsal_profile import TRIAL_ORIGIN as ORIGIN, canonical_anchor, lease_cap, require_cycle_alignment
from .domain import timestamp
from .pp_structured_probe import LOCAL_DSN, private_dsn

CONSUMER = 'trial-tail:seal-only-v1'
MAX_RAW_ROWS = 128 * 500  # Existing sealed archive catalog, without enlargement.
LIMITS = ArchiveLimits(max_seconds=20)


@dataclass(frozen=True)
class TailTarget:
    origin: str
    anchor: str
    retired_b: str
    generation: str
    writer_epoch: int
    raw_count: int
    operation: str
    source: str
    trial_source: str

    def validate(self):
        from .pp_historical_drain import SealTarget
        SealTarget(self.generation,self.writer_epoch,self.raw_count,self.operation,self.source).validate()
        canonical_anchor(self.anchor)
        canonical_anchor(self.retired_b)
        if (self.origin != ORIGIN or len({self.anchor,self.retired_b,self.generation}) != 3
                or not isinstance(self.trial_source,str)
                or not re.fullmatch('[0-9a-f]{40}',self.trial_source)):
            raise LifecycleHold('exact trial origin, three distinct generations and source required')


def _completed_trial(db, target, current):
    rows=db.execute('SELECT * FROM archive.generations WHERE origin_id=%s '
                    'ORDER BY created_at,generation_id LIMIT 4 FOR SHARE',(ORIGIN,)).fetchall()
    if (len(rows) != 3 or [r['generation_id'] for r in rows] !=
            [target.anchor,target.retired_b,target.generation]
            or [r['slot'] for r in rows] != ['A','B','A']
            or rows[-1]['generation_id'] != current['generation_id']):
        raise LifecycleHold('exact two-transition trial chain required')
    admission=db.execute('SELECT cursor FROM archive.checkpoints WHERE origin_id=%s '
        "AND generation_id=%s AND consumer='rehearsal:two-leg-session' FOR SHARE",
        (ORIGIN,target.anchor)).fetchone()
    proof=admission['cursor'] if admission else {}
    try:
        canonical_anchor(proof['session_id'])
        admitted=timestamp(proof['admitted_at'])
        expiry=timestamp(proof['lease_expires_at'])
        require_cycle_alignment(admitted)
        if (proof['initial_a'] != target.anchor or type(proof['lease_seconds']) is not int or proof['lease_seconds'] != lease_cap(target.anchor)
                or not 0 < (expiry-admitted).total_seconds() <= lease_cap(target.anchor)
                or admitted < rows[0]['created_at']):
            raise ValueError('admission changed')
    except (KeyError,TypeError,ValueError):
        raise LifecycleHold('original exact trial admission missing or changed') from None
    receipts=[]
    for previous, successor in zip(rows,rows[1:]):
        if (previous['state'] != 'retired' or not previous['retired_at']
                or not previous['verified_at'] or not previous['sealed_at']
                or successor['started_at'] != previous['sealed_at']
                or not admitted <= previous['sealed_at'] <= previous['verified_at'] <= previous['retired_at']
                or previous['retired_at'] > expiry
                or previous['retired_at'] >= previous['sealed_at']+timedelta(minutes=30)
                or previous['seal_count'] is None or previous['seal_count'] < 1
                or not re.fullmatch('[0-9a-f]{64}',previous['seal_hash'] or '')
                or db.execute('SELECT to_regclass(%s) AS child',
                              ('raw.'+previous['partition_name'],)).fetchone()['child'] is not None):
            raise LifecycleHold('completed exact trial retirement missing or changed')
        row=db.execute('SELECT cursor FROM archive.checkpoints WHERE origin_id=%s '
            "AND generation_id=%s AND consumer='retirement:pp-fresh-readback' FOR SHARE",
            (ORIGIN,previous['generation_id'])).fetchone()
        receipt=row['cursor'] if row else {}
        if (receipt.get('active') != successor['generation_id']
                or receipt.get('enabled') is not True
                or receipt.get('policy') != 'pp-exact-retirement-v1'
                or receipt.get('source') != target.trial_source
                or receipt.get('seal_hash') != previous['seal_hash']
                or receipt.get('count') != previous['seal_count']
                or type(receipt.get('active_new_rows')) is not int or receipt['active_new_rows'] < 1
                or type(receipt.get('txid')) is not int or receipt['txid'] < 1
                or not all(isinstance(receipt.get(k),str) and re.fullmatch('[0-9a-f]{64}',receipt[k])
                           for k in ('policy_epoch','history_reader_proof'))):
            raise LifecycleHold('exact trial retirement checkpoint changed')
        receipts.append(sha256(encoded(receipt)))
    if rows[0]['retired_at'] > rows[1]['sealed_at']:
        raise LifecycleHold('initial A was not retired before fresh A creation')
    return dict(admission_sha256=sha256(encoded(proof)),retirement_sha256=receipts)


def seal_final_a(repository, target: TailTarget, *, execute=False):
    """Seal the exact final trial A without creating a successor or retiring it.

    Locking the writer drains previously admitted Store writes. The same global
    admission lock prevents ON while durable OFF is rechecked. The old writer
    remains on a sealed generation, so normal activation/ingestion cannot resume.
    A retry only acknowledges this identical completed operation; it never reseals.
    """
    target.validate()
    if execute is not True or repository.environment != 'preprod':
        raise LifecycleHold('explicit PP final trial seal execution required')
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
            raise LifecycleHold('exact final trial writer must be durably OFF')
        other_writers=db.execute("SELECT collector_enabled,collector_session_id,collector_lease_expires_at "
            "FROM ops.writer_state WHERE origin_id LIKE 'pp-live-%' ORDER BY origin_id FOR UPDATE").fetchall()
        if (any(r['collector_enabled'] or r['collector_session_id'] is not None
                or r['collector_lease_expires_at'] is not None for r in other_writers)
                or db.execute('SELECT 1 FROM ops.writer_state WHERE collector_enabled LIMIT 1').fetchone()):
            raise LifecycleHold('final trial sealing requires all PP collectors OFF')
        generation = db.execute('SELECT * FROM archive.generations WHERE origin_id=%s '
                                'AND generation_id=%s FOR UPDATE', (ORIGIN,target.generation)).fetchone()
        if not generation or generation['slot'] != 'A':
            raise LifecycleHold('exact final trial A required')
        completed = _completed_trial(db,target,generation)
        count = db.execute('SELECT count(*) AS n FROM (SELECT 1 FROM raw.events WHERE origin_id=%s '
                           'AND generation_id=%s LIMIT %s) bounded',
                           (ORIGIN,target.generation,MAX_RAW_ROWS+1)).fetchone()['n']
        if count != target.raw_count:
            raise LifecycleHold('reviewed final trial raw count changed')
        previous = db.execute('SELECT cursor FROM archive.checkpoints WHERE origin_id=%s '
                              'AND generation_id=%s AND consumer=%s',
                              (ORIGIN,target.generation,CONSUMER)).fetchone()
        identity = dict(operation=target.operation,source=target.source,
                        origin=ORIGIN,anchor=target.anchor,retired_b=target.retired_b,
                        trial_source=target.trial_source,**completed,
                        previous_writer_epoch=target.writer_epoch,raw_count=target.raw_count,
                        policy='pp-final-trial-tail-v1',retirement_authorized=False,
                        trial_completion_claimed=False)
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
            raise LifecycleHold('final trial A or writer epoch changed')
        if db.execute('SELECT 1 FROM archive.manifests WHERE generation_id=%s LIMIT 1',
                      (target.generation,)).fetchone():
            raise LifecycleHold('unsealed final trial A already has archive manifests')
        # Check the actual physical child and exact partition bound before seal.
        child = 'events_g_'+target.generation.replace('-','')
        attached = db.execute("""SELECT 1 FROM pg_inherits i JOIN pg_class c ON c.oid=i.inhrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace WHERE i.inhparent='raw.events'::regclass
            AND n.nspname='raw' AND c.relname=%s AND
            pg_get_expr(c.relpartbound,c.oid)=format('FOR VALUES IN (%%L)',%s::text)""",
            (child,target.generation)).fetchone()
        if not attached:
            raise LifecycleHold('exact final trial raw partition unavailable')
        sealed_at = db.execute('SELECT clock_timestamp() AS at').fetchone()['at']
        if generation['started_at'] is None or sealed_at < generation['started_at']:
            raise LifecycleHold('final trial generation start is invalid')
        db.execute("UPDATE archive.generations SET state='sealed',sealed_at=%s,seal_count=%s "
                   'WHERE origin_id=%s AND generation_id=%s',
                   (sealed_at,target.raw_count,ORIGIN,target.generation))
        db.execute('UPDATE ops.writer_state SET epoch=epoch+1,updated_at=%s WHERE origin_id=%s',
                   (sealed_at,ORIGIN))
        receipt = dict(identity,sealed_at=sealed_at.isoformat(),
                       txid=db.execute('SELECT txid_current() AS txid').fetchone()['txid'])
        repository._checkpoint(db,generation,CONSUMER,receipt)
    return dict(status='sealed_final_a_for_archive',generation_id=target.generation,**receipt)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--origin',required=True,choices=[ORIGIN])
    parser.add_argument('--anchor',required=True)
    parser.add_argument('--retired-b',required=True)
    parser.add_argument('--trial-source',required=True)
    parser.add_argument('--generation', required=True)
    parser.add_argument('--writer-epoch', required=True, type=int)
    parser.add_argument('--raw-count', required=True, type=int)
    parser.add_argument('--operation', required=True)
    parser.add_argument('--source', required=True)
    args = parser.parse_args(argv)
    try:
        target = TailTarget(args.origin,args.anchor,args.retired_b,args.generation,args.writer_epoch,
                            args.raw_count,args.operation,args.source,args.trial_source)
        target.validate()
        if (not args.execute or os.getenv('TRADEBOT_PP_FINAL_TAIL_DRAIN') != 'true'
                or os.getenv('TRADEBOT_ENVIRONMENT') != 'preprod'
                or os.getenv('TRADEBOT_DATA_MODE') != 'pp_live'
                or os.getenv('TRADEBOT_ORIGIN_ID') != ORIGIN
                or os.getenv('TRADEBOT_PP_CYCLE_INITIAL_A') != args.anchor
                or os.getenv('TRADEBOT_PP_WINDOW_POLICY') != 'two-official-markets-cycle'
                or os.getenv('TRADEBOT_DATABASE_DSN_FILE') != str(LOCAL_DSN)
                or os.getenv('TRADEBOT_DATABASE_DSN')
                or any(os.getenv(flag,'false').lower() not in ('false','0','off') for flag in OFF_FLAGS)):
            raise LifecycleHold('exact default-OFF historical maintenance profile required')
        from .connection import connect
        from .migrate import validate_schema
        dsn=private_dsn(LOCAL_DSN)
        def factory():
            return connect(dsn,environment='preprod')
        with factory() as db:
            if db.execute('SELECT session_user AS login').fetchone()['login'] != 'tradebot_lifecycle':
                raise LifecycleHold('final trial sealing requires lifecycle login')
            validate_schema(db,'preprod')
        result=seal_final_a(LifecycleRepository(factory),target,execute=True)
        print(json.dumps(result,sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps(dict(status='HOLD',reason=getattr(error,'code',type(error).__name__),
                              retirement_authorized=False,trial_completion_claimed=False)))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
