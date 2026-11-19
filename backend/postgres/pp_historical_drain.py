"""Explicit old-PP B seal for archive-only maintenance; never rotate or retire.

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
from .pp_raw_archive_probe import OFF_FLAGS, ORIGIN
from .pp_structured_probe import LOCAL_DSN, private_dsn

CONSUMER = 'historical-drain:seal-only-v1'
MAX_RAW_ROWS = 128 * 500  # Existing sealed archive catalog, without enlargement.
LIMITS = ArchiveLimits(max_seconds=20)


@dataclass(frozen=True)
class SealTarget:
    generation: str
    writer_epoch: int
    raw_count: int
    operation: str
    source: str

    def validate(self):
        if (any(not isinstance(value, str) or str(uuid.UUID(value)) != value
                for value in (self.generation, self.operation))
                or type(self.writer_epoch) is not int or self.writer_epoch < 0
                or type(self.raw_count) is not int or not 1 <= self.raw_count <= MAX_RAW_ROWS
                or not isinstance(self.source, str) or not re.fullmatch('[0-9a-f]{40}', self.source)):
            raise LifecycleHold('exact bounded historical seal target required')


def seal_offline_b(repository, target: SealTarget, *, execute=False):
    """Seal the exact stopped historic B, preserving its writer pointer and A.

    Locking the writer drains previously admitted Store writes. The same global
    admission lock prevents ON while durable OFF is rechecked. The old writer
    remains on a sealed generation, so normal activation/ingestion cannot resume.
    A retry only acknowledges this identical completed operation; it never reseals.
    """
    target.validate()
    if execute is not True or repository.environment != 'preprod':
        raise LifecycleHold('explicit PP historical seal execution required')
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
            raise LifecycleHold('exact historic writer must be durably OFF')
        if db.execute("SELECT 1 FROM ops.writer_state WHERE origin_id LIKE 'pp-live-%' "
                      'AND collector_enabled LIMIT 1').fetchone():
            raise LifecycleHold('historical sealing requires all PP collectors OFF')
        generation = db.execute('SELECT * FROM archive.generations WHERE origin_id=%s '
                                'AND generation_id=%s FOR UPDATE', (ORIGIN,target.generation)).fetchone()
        if not generation or generation['slot'] != 'B':
            raise LifecycleHold('exact historical B required')
        count = db.execute('SELECT count(*) AS n FROM (SELECT 1 FROM raw.events WHERE origin_id=%s '
                           'AND generation_id=%s LIMIT %s) bounded',
                           (ORIGIN,target.generation,MAX_RAW_ROWS+1)).fetchone()['n']
        if count != target.raw_count:
            raise LifecycleHold('reviewed historical raw count changed')
        previous = db.execute('SELECT cursor FROM archive.checkpoints WHERE origin_id=%s '
                              'AND generation_id=%s AND consumer=%s',
                              (ORIGIN,target.generation,CONSUMER)).fetchone()
        identity = dict(operation=target.operation,source=target.source,
                        previous_writer_epoch=target.writer_epoch,raw_count=target.raw_count,
                        policy='pp-historical-drain-v1',retirement_authorized=False,
                        original_trial_satisfied=False)
        if previous:
            receipt = previous['cursor']
            if (any(receipt.get(k) != v for k,v in identity.items())
                    or generation['state'] not in ('sealed','verified')
                    or generation['sealed_at'].isoformat() != receipt.get('sealed_at')
                    or generation['seal_count'] != target.raw_count
                    or writer['epoch'] != target.writer_epoch+1):
                raise LifecycleHold('historical seal replay does not match')
            return dict(status='already_sealed',generation_id=target.generation,**receipt)
        if (writer['epoch'] != target.writer_epoch or generation['state'] != 'collecting'
                or any(generation[field] is not None for field in
                       ('sealed_at','seal_count','seal_hash','verified_at','retired_at'))):
            raise LifecycleHold('historic B or writer epoch changed')
        if db.execute('SELECT 1 FROM archive.manifests WHERE generation_id=%s LIMIT 1',
                      (target.generation,)).fetchone():
            raise LifecycleHold('unsealed historical B already has archive manifests')
        # Check the actual physical child and exact partition bound before seal.
        child = 'events_g_'+target.generation.replace('-','')
        attached = db.execute("""SELECT 1 FROM pg_inherits i JOIN pg_class c ON c.oid=i.inhrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace WHERE i.inhparent='raw.events'::regclass
            AND n.nspname='raw' AND c.relname=%s AND
            pg_get_expr(c.relpartbound,c.oid)=format('FOR VALUES IN (%%L)',%s::text)""",
            (child,target.generation)).fetchone()
        if not attached:
            raise LifecycleHold('exact historical raw partition unavailable')
        sealed_at = db.execute('SELECT clock_timestamp() AS at').fetchone()['at']
        if generation['started_at'] is None or sealed_at < generation['started_at']:
            raise LifecycleHold('historical generation start is invalid')
        db.execute("UPDATE archive.generations SET state='sealed',sealed_at=%s,seal_count=%s "
                   'WHERE origin_id=%s AND generation_id=%s',
                   (sealed_at,target.raw_count,ORIGIN,target.generation))
        db.execute('UPDATE ops.writer_state SET epoch=epoch+1,updated_at=%s WHERE origin_id=%s',
                   (sealed_at,ORIGIN))
        receipt = dict(identity,sealed_at=sealed_at.isoformat(),
                       txid=db.execute('SELECT txid_current() AS txid').fetchone()['txid'])
        repository._checkpoint(db,generation,CONSUMER,receipt)
    return dict(status='sealed_for_historical_archive',generation_id=target.generation,**receipt)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--generation', required=True)
    parser.add_argument('--writer-epoch', required=True, type=int)
    parser.add_argument('--raw-count', required=True, type=int)
    parser.add_argument('--operation', required=True)
    parser.add_argument('--source', required=True)
    args = parser.parse_args(argv)
    try:
        target = SealTarget(args.generation,args.writer_epoch,args.raw_count,args.operation,args.source)
        target.validate()
        if (not args.execute or os.getenv('TRADEBOT_PP_HISTORICAL_DRAIN') != 'true'
                or os.getenv('TRADEBOT_ENVIRONMENT') != 'preprod'
                or os.getenv('TRADEBOT_DATA_MODE') != 'pp_live'
                or os.getenv('TRADEBOT_ORIGIN_ID') != ORIGIN
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
                raise LifecycleHold('historical sealing requires lifecycle login')
            validate_schema(db,'preprod')
        result=seal_offline_b(LifecycleRepository(factory),target,execute=True)
        print(json.dumps(result,sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps(dict(status='HOLD',reason=getattr(error,'code',type(error).__name__),
                              retirement_authorized=False,original_trial_satisfied=False)))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
