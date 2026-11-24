"""Finite read-only proof of retained PP archives; never retirement qualification.

This intentionally does not call verify()/bind_seal_window(): an expired seal is
reported as expired, never moved. A later audit can measure the same workload
under an operation cap but cannot satisfy the original A-to-B trial deadline.
"""
import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
import re
import uuid

from .archive_codec import ArchiveIntegrityError, ArchiveLimit, CycleBudget
from .cloud_origin_binding import SIXTH_TRIAL_ORIGIN, cloud_binding
from .cloud_runtime_profile import cloud_files, require_trial_files, selected_cloud_origin, storage_paths
from .history_v2_envelope import CLOUD_COLUMNS
from .lifecycle import ArchiveWorker, LifecycleHold, LifecycleRepository, _DeadlineConnection
from .pp_retirement_report import bound_catalog
from .pp_retirement_verify import (ORIGIN, Target, TwoMarketReadbackLimits,
    RetirementTransport, inventory, retirement_failure, retirement_history_factory)
from .retirement_accounting import accounted, bind_budget, measured_context, phase

STOPPED_TRIAL = 'pp-live-pp-trial-20261119-03'
SCOPED_RETAINED_TRIALS = (STOPPED_TRIAL, SIXTH_TRIAL_ORIGIN)
LOCAL_DSN = '/run/secrets/pp_retained_reader_dsn'
LOCAL_TABLES = ('ops.environment_identity', 'archive.generations', 'archive.manifests',
    'raw.events', 'ops.outbox', 'ops.writer_state')
REMOTE_TABLES = tuple('history_v2.'+key.split('.')[1] for key in CLOUD_COLUMNS) + (
    'history_v2.generation_checkpoints', 'history_v2.structured_receipts',
    'history_v2.structured_revision_payloads')
OFF_FLAGS = ('TRADEBOT_PP_EXACT_RETIREMENT', 'TRADEBOT_PP_RETIREMENT_READBACK',
    'TRADEBOT_RETIREMENT_ENABLED', 'ENABLE_LOCAL_RETENTION', 'ENABLE_OPENAI_ANALYST',
    'TRADEBOT_CLOUD_ENABLED', 'ENABLE_SUPABASE_SYNC', 'TRADEBOT_COLLECTOR_ENABLED')


@dataclass(frozen=True)
class AuditTarget:
    sealed: str
    collecting: str
    seal_hash: str
    count: int
    structured_rows: int
    raw_objects: int
    structured_pages: int
    original_deadline_utc: str
    historical_off: bool = False

    def validate(self):
        if self.historical_off:
            if (str(uuid.UUID(self.sealed)) != self.sealed or self.collecting != self.sealed
                    or not re.fullmatch('[0-9a-f]{64}', self.seal_hash)
                    or type(self.count) is not int or self.count < 1):
                raise LifecycleHold('exact historical OFF writer and seal required')
        else:
            Target(self.sealed,self.collecting,self.seal_hash,self.count).validate()
        deadline=datetime.fromisoformat(self.original_deadline_utc)
        if deadline.tzinfo is None or deadline.astimezone(timezone.utc).isoformat() != self.original_deadline_utc:
            raise LifecycleHold('exact original UTC seal deadline required')
        if (any(type(n) is not int or n < 1 for n in (
                self.structured_rows,self.raw_objects,self.structured_pages)) or
                self.raw_objects+self.structured_pages+1 > 192):
            raise LifecycleHold('exact finite retained audit scope required')


def require_select(db, tables, *, latest_index=False):
    columns="""relation, has_schema_privilege(current_user,
        split_part(relation,'.',1),'USAGE') AND
        has_table_privilege(current_user,relation,'SELECT') AS allowed"""
    parameters=(list(tables),)
    if latest_index:
        from .history_v2_latest_receipts import ABI_SQL,INDEX_NAME
        columns+=',('+ABI_SQL+') AS latest_index_valid'
        parameters=(INDEX_NAME,*parameters)
    rows=db.execute('SELECT '+columns+' FROM unnest(%s::text[]) relation',parameters).fetchall()
    if len(rows) != len(tables) or any(row['allowed'] is not True for row in rows):
        raise LifecycleHold('audit requires existing SELECT privileges; grants are not automatic')
    if latest_index and any(row['latest_index_valid'] is not True for row in rows):
        raise ArchiveIntegrityError('PP latest receipt index ABI unavailable')


@contextmanager
def local_snapshot(factory,budget, *, monitor=False):
    # No lifecycle credential, generation UPDATE lock, reader lease write,
    # checkpoint, permit or destructive method is used by this path.
    with factory() as connection:
        with connection.transaction():
            connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            remaining=max(1,int(1000*(budget.deadline-budget.clock())))
            connection.execute("SELECT set_config('transaction_timeout',%s,true)",(f'{remaining}ms',))
            db=_DeadlineConnection(connection,budget)
            identity=db.execute('SELECT current_user AS role, current_database() AS database, '
                "current_setting('transaction_read_only') AS read_only").fetchone()
            if identity != dict(role='tradebot_reader',database='tradebot_pp',read_only='on'):
                raise LifecycleHold('exact read-only local PP reader required')
            require_select(db,LOCAL_TABLES)
            if monitor:
                db.execute("SET LOCAL application_name='tradebot-retained-archive-audit'")
            db.execute("SET LOCAL lock_timeout='250ms'")
            # Compatible with B persistence; prevents concurrent partition DROP.
            db.execute('LOCK TABLE raw.events IN ACCESS SHARE MODE')
            yield db
            budget.check()


def remote_preflight(structured,budget):
    # This is a separately counted logical authenticated cloud operation.
    # The fixed existing PP login has write grants; this route uses it only in
    # enforced read-only transactions and reports its actual role honestly.
    timeout=budget.request(0)
    deadline=budget.clock()+timeout
    with measured_context(structured.connection_factory(timeout_seconds=timeout),
                          enter='history_checkout',finish='history_release') as db:
        with phase('history_transaction'), db.transaction():
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            remaining=deadline-budget.clock()
            if remaining <= 0: raise ArchiveLimit('audit preflight page deadline reached')
            structured._limit(db,remaining,catalog_search_path=structured.indexed_latest)
            structured._identity(db)
            require_select(db,REMOTE_TABLES,latest_index=structured.indexed_latest)
    if budget.clock() >= deadline: raise ArchiveLimit('audit preflight page deadline reached')
    budget.check()


@accounted
def audit(factory,transport,target, *, origin=None):
    target.validate()
    if origin is None:
        origin = ORIGIN
    if (origin not in (ORIGIN, *SCOPED_RETAINED_TRIALS) or transport.origin_id != origin
            or transport.generation_id != target.sealed
            or (origin in SCOPED_RETAINED_TRIALS and (
                transport.structured.expected_role != cloud_binding(origin).reader_role
                or getattr(transport.raw, "_reader", False) is not True
                or getattr(getattr(transport.raw, "_origin_binding", None), "origin_id", None) != origin))):
        raise LifecycleHold('exact PP retained archive transport required')
    limits=TwoMarketReadbackLimits()
    with CycleBudget(limits) as budget:
        bind_budget(budget)
        with measured_context(local_snapshot(factory,budget,monitor=origin in SCOPED_RETAINED_TRIALS),enter='local_open',finish='local_finish') as db:
            generation=db.execute('SELECT * FROM archive.generations WHERE origin_id=%s AND generation_id=%s',
                (origin,target.sealed)).fetchone()
            manifests=LifecycleRepository._manifests(db,target.sealed)
            slot = 'B' if target.historical_off or origin == SIXTH_TRIAL_ORIGIN else 'A'
            if (not generation or generation['slot'] != slot or generation['seal_count'] != target.count
                    or generation['seal_hash'] != target.seal_hash or not bound_catalog(generation,manifests)
                    or len(manifests) != target.raw_objects):
                raise LifecycleHold('reviewed retained seal or catalog changed')
            active=db.execute('''SELECT generation_id,collector_enabled,collector_session_id,
                collector_lease_expires_at FROM ops.writer_state WHERE origin_id=%s''',(origin,)).fetchone()
            if not active or str(active['generation_id']) != target.collecting:
                raise LifecycleHold('reviewed writer generation changed')
            if target.historical_off and (active['collector_enabled'] or active['collector_session_id'] is not None
                    or active['collector_lease_expires_at'] is not None):
                raise LifecycleHold('reviewed historical writer is not durably OFF')
            if origin in SCOPED_RETAINED_TRIALS:
                writers_on = db.execute("""SELECT EXISTS (SELECT 1 FROM ops.writer_state
                    WHERE collector_enabled OR collector_session_id IS NOT NULL
                        OR collector_lease_expires_at IS NOT NULL) AS running""").fetchone()
                if writers_on['running']:
                    raise LifecycleHold('retained trial requires all writers OFF')
                if origin == SIXTH_TRIAL_ORIGIN:
                    chain = db.execute('''SELECT generation_id,slot,state,started_at,sealed_at,
                        retired_at,to_regclass('raw.'||partition_name) IS NOT NULL AS present,
                        EXISTS(SELECT FROM pg_inherits WHERE inhparent='raw.events'::regclass
                            AND inhrelid=to_regclass('raw.'||partition_name)) AS attached
                        FROM archive.generations WHERE origin_id=%s
                        ORDER BY created_at,generation_id LIMIT 4''',(origin,)).fetchall()
                    if (target.historical_off or len(chain) != 3
                            or [row['slot'] for row in chain] != ['A','B','A']
                            or [row['state'] for row in chain] != ['retired','verified','collecting']
                            or [row['present'] for row in chain] != [False,True,True]
                            or [row['attached'] for row in chain] != [False,True,True]
                            or chain[0]['retired_at'] is None or chain[1]['retired_at'] is not None
                            or str(chain[1]['generation_id']) != target.sealed
                            or str(chain[2]['generation_id']) != target.collecting
                            or chain[0]['sealed_at'] != chain[1]['started_at']
                            or chain[1]['sealed_at'] != chain[2]['started_at']):
                        raise LifecycleHold('retained trial06 chain or attachments changed')
                    pending = db.execute('''SELECT EXISTS(SELECT FROM ops.outbox
                        WHERE origin_id=%s AND acknowledged_at IS NULL) AS pending''',(origin,)).fetchone()
                    if pending['pending']:
                        raise LifecycleHold('retained trial06 outbox is not fully acknowledged')
                elif target.historical_off:
                    other = db.execute("""SELECT generation_id FROM archive.generations
                        WHERE origin_id=%s AND slot='A' AND state='verified'
                            AND retired_at IS NULL AND sealed_at=%s""",
                        (origin, generation['started_at'])).fetchall()
                    if len(other) != 1:
                        raise LifecycleHold('retained B requires its verified A predecessor')
                else:
                    successor = db.execute("""SELECT slot, state, retired_at, started_at FROM archive.generations
                        WHERE origin_id=%s AND generation_id=%s""", (origin, target.collecting)).fetchone()
                    if (not successor or successor['slot'] != 'B' or successor['state'] != 'verified'
                            or successor['retired_at'] is not None or successor['started_at'] != generation['sealed_at']):
                        raise LifecycleHold('retained A requires its verified B successor')
            actual=db.execute('SELECT count(*) AS count FROM raw.events WHERE generation_id=%s',
                (target.sealed,)).fetchone()['count']
            if actual != target.count:
                raise LifecycleHold('reviewed retained raw count changed')
            checked=db.execute('SELECT clock_timestamp() AS now').fetchone()['now']
            original_deadline=generation['sealed_at']+timedelta(minutes=30)
            if original_deadline.astimezone(timezone.utc).isoformat() != target.original_deadline_utc:
                raise LifecycleHold('reviewed original seal timestamp changed')
            with phase('inventory'):
                estimate=inventory(db,target.sealed,manifests,budget,fresh_machine_session=True)
            if (estimate['structured_rows'] != target.structured_rows or
                    estimate['structured_pages_examined'] != target.structured_pages or
                    not estimate['structured_inventory_complete'] or
                    estimate['fit'] == 'exceeds_limits' or estimate['requests_minimum']+1 > limits.max_requests):
                raise LifecycleHold('reviewed retained structured scope changed or exceeds audit limits')
            remote_preflight(transport.structured,budget)
            # Worker only reads raw/local/structured. It never calls a retirement
            # method; local READ ONLY and reader privileges independently deny it.
            readback=ArchiveWorker(LifecycleRepository(factory),transport,limits).fresh_retirement_readback(
                db,generation,manifests,budget)
            if readback['structured_count'] != target.structured_rows:
                raise ArchiveIntegrityError('retained audit structured coverage changed')
            budget.check()
    timely=budget.clock() < budget.deadline
    return {'status':'retained_archive_audit_verified' if timely else 'retained_archive_audit_after_operation_deadline',
        'evidence_scope':'read_only_retained_archive_audit', 'retirement_authorized':False,
        'original_trial_satisfied':False, 'original_seal_deadline_utc':original_deadline.isoformat(),
        'original_seal_expired_at_audit_start':checked >= original_deadline,
        'operation_deadline_met':timely, 'local_role':'tradebot_reader',
        'structured_role':transport.structured.expected_role,
        'structured_transactions':'repeatable_read_read_only',
        'latest_receipt_lookup':'indexed_tie_safe_lateral' if transport.structured.indexed_latest else 'rank',
        'origin_id':origin, 'sealed':target.sealed,'opposite':None if target.historical_off else target.collecting,
        'historical_off':target.historical_off,'inventory':estimate,**readback}


def check_environment(environ, *, origin=ORIGIN):
    if (environ.get('TRADEBOT_ENVIRONMENT') != 'preprod' or
            environ.get('TRADEBOT_DATA_MODE') != 'pp_live' or
            origin not in (ORIGIN, *SCOPED_RETAINED_TRIALS) or
            environ.get('TRADEBOT_ORIGIN_ID') != origin or
            environ.get('TRADEBOT_PP_RETAINED_ARCHIVE_AUDIT') != 'true' or
            environ.get('TRADEBOT_DATABASE_DSN_FILE') != LOCAL_DSN or
            environ.get('TRADEBOT_DATABASE_DSN') or
            any(environ.get(flag,'false') != 'false' for flag in OFF_FLAGS) or
            (os.path.lexists if origin in SCOPED_RETAINED_TRIALS else os.path.exists)('/run/secrets/pp_retirement_ticket')):
        raise LifecycleHold('isolated read-only retained audit identity required; no retirement ticket')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('sealed','collecting','seal-hash','original-deadline-utc'): parser.add_argument('--'+name,required=True)
    for name in ('count','structured-rows','raw-objects','structured-pages'):
        parser.add_argument('--'+name,type=int,required=True)
    parser.add_argument('--historical-off', action='store_true',
                        help='audit the exact historical sealed B whose writer pointer stays OFF')
    args=parser.parse_args()
    raw=history=None
    try:
        target=AuditTarget(args.sealed,args.collecting,args.seal_hash,args.count,
            args.structured_rows,args.raw_objects,args.structured_pages,args.original_deadline_utc,
            historical_off=args.historical_off)
        target.validate()
        origin=selected_cloud_origin(os.environ)
        check_environment(os.environ, origin=origin)
        require_trial_files(os.environ, origin, reader=True, structured=True, storage=True)
        from .connection import connect
        from .pp_structured_probe import private_dsn
        from .history_v2_transport import HistoryV2PostgresTransport
        from .history_v2_latest_receipts import indexed_latest_requested
        from .supabase_storage import SupabaseStorageTransport
        from pathlib import Path
        dsn=private_dsn(Path(LOCAL_DSN))
        factory=lambda:connect(dsn,environment='preprod',readonly=True)
        history=retirement_history_factory(os.environ)
        structured=HistoryV2PostgresTransport(history,origin_id=origin,generation_id=target.sealed,
            expected_database='postgres',expected_role=cloud_binding(origin).role(reader=True),
            indexed_latest=indexed_latest_requested(os.environ))
        raw=SupabaseStorageTransport.from_machine_files(
            *storage_paths(cloud_files(origin, reader=True)), reader=True, origin_id=origin)
        result=audit(factory, RetirementTransport(raw, structured, origin_id=origin,
            generation_id=target.sealed), target, origin=origin)
        print(json.dumps(result,sort_keys=True))
        return 0 if result['operation_deadline_met'] else 1
    except Exception as error:
        failure = retirement_failure(error)
        failure.update(evidence_scope='read_only_retained_archive_audit', original_trial_satisfied=False)
        print(json.dumps(failure, sort_keys=True, allow_nan=False))
        return 1
    finally:
        try:
            if history is not None and hasattr(history,'close'): history.close()
        finally:
            if raw is not None: raw.close()


if __name__ == '__main__':
    raise SystemExit(main())
