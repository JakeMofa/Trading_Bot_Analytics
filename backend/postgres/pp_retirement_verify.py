"""Exact-target, fresh PP retirement readback. The separately permitted operator mode can retire one exact PP partition."""
import argparse
from dataclasses import dataclass
import json
import os
import re
import uuid
from datetime import timedelta

from .archive_codec import ArchiveIntegrityError, ArchiveLimits, CycleBudget, encoded
from .archive_transport import ScopedArchiveTransport
from .retirement_accounting import accounted, bind_budget, measured_context, phase
from .lifecycle import ArchiveWorker, LifecycleHold, LifecycleRepository
from .pp_raw_archive_probe import FILES, ORIGIN, check_environment
from .pp_retirement_report import active_sample, bound_catalog
from .pp_structured_probe import LOCAL_DSN, private_dsn


@dataclass(frozen=True)
class TwoMarketReadbackLimits(ArchiveLimits):
    """Supervised PP-only readback. A page and its network deadline stay small."""
    max_requests: int = 192
    max_cycle_bytes: int = 128 * 1024 * 1024
    max_seconds: float = 240.0

    def __post_init__(self):
        # verify_local_chunk narrows max_rows for the final short object.
        if (type(self.max_rows) is not int or not 1 <= self.max_rows <= 500
                or (self.max_requests, self.max_cycle_bytes, self.max_seconds,
                    self.max_object_bytes, self.max_decoded_bytes, self.request_timeout_seconds)
                != (192, 128*1024**2, 240, 2*1024**2, 4*1024**2, 4)):
            raise ValueError('unexpected two-market verification limits')


def bound_seal_window(db, generation, budget, sampled_before):
    checked_at = db.execute('SELECT clock_timestamp() AS checked_at').fetchone()['checked_at']
    sealed_at = generation['sealed_at']
    if not sealed_at or sealed_at > checked_at:
        raise LifecycleHold('invalid PP generation seal time')
    ends_at = sealed_at + timedelta(minutes=30)
    # Anchor at the monotonic instant BEFORE the database query to avoid
    # extending the wall deadline by round-trip/lock wait. Every connection and
    # cloud call already enforces the remaining monotonic operation budget.
    end_monotonic = sampled_before + (ends_at - checked_at).total_seconds()
    budget.deadline = min(budget.deadline, end_monotonic)
    budget.check()
    remaining = max(1, int((budget.deadline - budget.clock()) * 1000))
    db.execute("SELECT set_config('transaction_timeout',%s,true)",(f'{remaining}ms',))
    return ends_at, end_monotonic


@dataclass(frozen=True)
class Target:
    sealed: str
    collecting: str
    seal_hash: str
    count: int

    def validate(self):
        if (any(str(uuid.UUID(value)) != value for value in (self.sealed, self.collecting))
                or self.sealed == self.collecting or not re.fullmatch('[0-9a-f]{64}',self.seal_hash)
                or type(self.count) is not int or self.count < 1):
            raise ValueError('exact distinct generations, digest and positive row count required')


@dataclass(frozen=True)
class Permit:
    ticket: str
    release: str
    policy_epoch: str
    history_reader_proof: str

    def validate(self):
        if (str(uuid.UUID(self.ticket)) != self.ticket or
                not re.fullmatch('[0-9a-f]{40}', self.release) or
                not re.fullmatch('[0-9a-f]{64}', self.policy_epoch) or
                not re.fullmatch('[0-9a-f]{64}', self.history_reader_proof)):
            raise LifecycleHold('invalid one-use PP retirement permit')


def retire_with_permit(db, generation, target, permit, new_rows):
    # The caller's local generation row lock and all manifest share locks
    # remain held until the verification, permit consumption and DROP commit.
    txid = db.execute('SELECT txid_current() AS txid').fetchone()['txid']
    LifecycleRepository._checkpoint(db, generation, 'retirement:pp-fresh-readback', {
        'txid': txid, 'enabled':True, 'policy':'pp-exact-retirement-v1',
        'policy_epoch':permit.policy_epoch, 'source':permit.release,
        'history_reader_proof':permit.history_reader_proof,
        'seal_hash':target.seal_hash, 'count':target.count, 'active':target.collecting,
        'active_new_rows':new_rows})
    db.execute("SET LOCAL lock_timeout='5ms'")
    db.execute('SELECT archive.retire_pp_generation(%s,%s,%s,%s,%s,%s)',
               (permit.ticket, target.sealed, target.collecting, permit.release, permit.policy_epoch,
                permit.history_reader_proof))


class RetirementTransport(ScopedArchiveTransport):
    """Exact, read-only sealed-generation structured proof, scoped to this command."""
    def read_structured_authenticated(self, records, *, max_bytes, timeout_seconds):
        from .archive_codec import ACTIVE_BUDGET, ArchiveLimit, encoded
        from .history_v2_envelope import validate_outbox_stream
        validate_outbox_stream(records, origin_id=self.origin_id, generation_id=self.generation_id)
        budget = ACTIVE_BUDGET.get()
        if budget is None:
            raise ArchiveLimit('retirement operation budget required')
        requested = len(encoded(records))
        # The worker reserved these exact A bytes. Any newer revision in B
        # must also fit the remaining cycle and page budget.
        allowance = min(max_bytes, requested + budget.limits.max_cycle_bytes - budget.bytes)
        rows, size = self.structured.read_retirement_revisions(
            records, max_bytes=allowance, timeout_seconds=timeout_seconds)
        budget.account(size - requested)
        return rows


def inventory(connection, generation_id, manifests, budget, *, fresh_machine_session):
    """Price the fresh readback using only local sealed records and their real page boundaries."""
    limits = budget.limits
    count = connection.execute(
        'SELECT count(*) AS n FROM ops.outbox WHERE generation_id=%s', (generation_id,)
    ).fetchone()['n']
    result = {
        'raw_objects': len(manifests), 'raw_bytes': sum(m['byte_count'] for m in manifests),
        'structured_rows': count, 'structured_pages_examined': 0, 'structured_bytes_examined': 0,
        'auth_calls_reserved': int(bool(manifests) and fresh_machine_session),
        'request_limit': limits.max_requests, 'byte_limit': limits.max_cycle_bytes,
        'deadline_seconds': limits.max_seconds,
    }
    after = rows_seen = 0
    while True:
        budget.check()
        remaining = count - rows_seen
        pages = (remaining + limits.max_rows - 1) // limits.max_rows
        result['requests_minimum'] = (len(manifests) + result['auth_calls_reserved'] +
                                      result['structured_pages_examined'] + pages)
        result['bytes_minimum'] = result['raw_bytes'] + result['structured_bytes_examined']
        result['structured_inventory_complete'] = remaining == 0
        if any(m['row_count'] > limits.max_rows or m['byte_count'] > limits.max_object_bytes
               or m['coverage']['decoded_bytes'] > limits.max_decoded_bytes for m in manifests):
            result.update(fit='exceeds_limits', reason='raw_object_limit')
            return result
        if result['requests_minimum'] > limits.max_requests or result['bytes_minimum'] > limits.max_cycle_bytes:
            result['fit'] = 'exceeds_limits'
            return result
        if not remaining:
            # Newer B envelopes are visible only to an authenticated cloud read.
            # One decoded page allowance caps all historical and replacement
            # envelopes together; deadlines are enforced separately at runtime.
            result['bytes_upper_bound'] = result['raw_bytes'] + result['structured_pages_examined'] * limits.max_decoded_bytes
            result['fit'] = ('fits_request_and_envelope_byte_limits'
                             if result['bytes_upper_bound'] <= limits.max_cycle_bytes
                             else 'conditional_on_newer_revision_bytes')
            return result
        rows = LifecycleRepository._pending(connection, generation_id, limits.max_rows,
            max_bytes=limits.max_decoded_bytes, include_acknowledged=True, after_id=after)
        if not rows or len(rows) > remaining or rows[-1]['id'] <= after:
            raise ArchiveIntegrityError('sealed structured inventory changed')
        records = ArchiveWorker.structured_records(rows)
        size = len(encoded(records))
        result['structured_bytes_examined'] += size
        result['structured_pages_examined'] += 1
        rows_seen += len(rows)
        after = rows[-1]['id']
        if size > limits.max_decoded_bytes:
            result['fit'] = 'exceeds_limits'
            result['reason'] = 'structured_page_limit'
            return result


@accounted
def verify(repository, transport, target, *, limits=ArchiveLimits(), origin=ORIGIN, inventory_only=False, permit=None):
    target.validate()
    if (repository.environment != 'preprod' or
            (not inventory_only and (transport.origin_id != origin or transport.generation_id != target.sealed)) or
            (origin != ORIGIN and not origin.startswith('generated-'))):
        raise LifecycleHold('wrong retirement readback environment or generation')
    if permit is not None:
        permit.validate()
        if origin != ORIGIN or inventory_only or not isinstance(transport, RetirementTransport):
            raise LifecycleHold('retirement permit requires exact PP cloud readback')
    windowed = isinstance(limits, TwoMarketReadbackLimits)
    if windowed and origin != ORIGIN and not origin.startswith('generated-'):
        raise LifecycleHold('two-market profile is restricted to PP')
    with CycleBudget(limits) as budget:
        bind_budget(budget)
        with measured_context(repository.retirement(target.sealed),
                              enter='local_open', finish='local_finish') as (db, generation, manifests):
            if windowed:
                sampled = budget.clock()
                expires_at, window_end = bound_seal_window(db, generation, budget, sampled)

            if permit is not None:
                # FK inserts block on the generation UPDATE lock; existing catalog
                # entries must also remain immutable for this local transaction.
                db.execute('SELECT manifest_id FROM archive.manifests WHERE generation_id=%s FOR SHARE',
                           (target.sealed,)).fetchall()
                manifests = repository._manifests(db, target.sealed)

            if (generation['origin_id'] != origin or generation['seal_count'] != target.count
                    or generation['seal_hash'] != target.seal_hash or not bound_catalog(generation,manifests)):
                raise LifecycleHold('reviewed seal or authenticated catalog changed')
            before = active_sample(db, origin)
            if (not before or before['generation_id'] != target.collecting
                    or before['slot'] == generation['slot']):
                raise LifecycleHold('reviewed active slot changed')
            if windowed:
                active_start = db.execute('SELECT started_at FROM archive.generations WHERE generation_id=%s',
                                          (target.collecting,)).fetchone()
                if ({generation['slot'], before['slot']} != {'A', 'B'} or not active_start or
                        active_start['started_at'] != generation['sealed_at']):
                    raise LifecycleHold('two-market verification requires the actual opposite-slot handoff')
            with phase('inventory'):
                estimate = inventory(db, target.sealed, manifests, budget, fresh_machine_session=origin == ORIGIN)
            if windowed:
                estimate.update(profile='pp-two-market-v1', seal_deadline_utc=expires_at.isoformat(),
                                remaining_work_seconds=round(budget.deadline-budget.clock(),3))
            if inventory_only or estimate['fit'] == 'exceeds_limits':
                return {'status':'HOLD' if estimate['fit'] == 'exceeds_limits' else 'inventory_only',
                        'retirement_authorized':False, 'sealed':target.sealed, 'collecting':target.collecting,
                        'cloud_requests':0, 'inventory':estimate}
            worker = ArchiveWorker(repository, transport, limits)
            readback = worker.fresh_retirement_readback(db, generation, manifests, budget)
            after = active_sample(db, origin)
            if (not after or after['generation_id'] != target.collecting
                    or after['slot'] != before['slot'] or after['committed_rows'] <= before['committed_rows']):
                raise LifecycleHold('concurrent opposite-slot persistence unobserved')
            budget.check()
            if permit is not None:
                with phase('permit_drop'):
                    retire_with_permit(db, generation, target, permit,
                                       after['committed_rows'] - before['committed_rows'])
                if windowed:
                    # Recheck the DB clock after DROP, with rollback still possible.
                    late = db.execute('SELECT clock_timestamp()>=%s AS late',(expires_at,)).fetchone()['late']
                    if late:
                        raise LifecycleHold('PP seal deadline expired before commit')
                budget.check()
    operation_timely = budget.clock() < budget.deadline
    timely = not windowed or budget.clock() < window_end
    status = 'retired_pp' if permit else 'fresh_readback_verified'
    if not timely:
        # A successful commit is final even if commit confirmation was slow.
        status += '_after_seal_deadline'
    elif windowed and not operation_timely:
        status += '_after_operation_deadline'
    return {'status':status, 'seal_deadline_met':timely if windowed else None,
            'operation_deadline_met':operation_timely if windowed else None,
            'retirement_authorized':permit is not None,
            'policy_version':'pp-retirement-readback-v2','sealed':target.sealed,
            'collecting':target.collecting,'opposite_slot_new_rows':after['committed_rows']-before['committed_rows'],
            'inventory':estimate, **readback}


def retirement_history_factory(environ):
    """Separate one-shot opt-in: recurring worker settings cannot enable reuse."""
    from .pp_history_connection import PPHistoryConnectionFactory
    from .pp_history_session import ReusablePPHistoryConnectionFactory
    reuse = environ.get('TRADEBOT_PP_RETIREMENT_REUSE_HISTORY_SESSION', 'false')
    if reuse not in ('true', 'false'):
        raise LifecycleHold('exact PP retirement session reuse opt-in required')
    return ReusablePPHistoryConnectionFactory() if reuse == 'true' else PPHistoryConnectionFactory()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sealed',required=True)
    parser.add_argument('--collecting',required=True)
    parser.add_argument('--seal-hash',required=True)
    parser.add_argument('--count',required=True,type=int)
    parser.add_argument('--inventory-only', action='store_true', help='estimate locally without cloud credentials or requests')
    parser.add_argument('--two-market-window', action='store_true',
                        help='use the scoped PP budget within 30 minutes of the actual seal')
    parser.add_argument('--retire-with-pp-permit', action='store_true',
                        help='consume the separately issued private exact-generation ticket')
    args=parser.parse_args()
    raw=None
    history_factory=None
    try:
        target=Target(args.sealed, args.collecting, args.seal_hash, args.count)
        target.validate()
        check_environment(os.environ)
        if os.environ.get('TRADEBOT_PP_RETIREMENT_READBACK') != 'true':
            raise LifecycleHold('explicit one-shot readback required')
        from .connection import connect
        from .history_v2_transport import HistoryV2PostgresTransport
        from .migrate import validate_schema
        from .supabase_storage import SupabaseStorageTransport
        dsn = private_dsn(LOCAL_DSN)
        def factory():
            return connect(dsn, environment='preprod')
        with factory() as db:
            if db.execute('SELECT current_user AS role').fetchone()['role'] != 'tradebot_lifecycle':
                raise LifecycleHold('incorrect local readback identity')
            validate_schema(db,'preprod')
        if args.inventory_only and args.retire_with_pp_permit:
            raise LifecycleHold('inventory and retirement are mutually exclusive')
        limits = ArchiveLimits()
        if args.two_market_window:
            if os.environ.get('TRADEBOT_PP_TWO_MARKET_READBACK') != 'true':
                raise LifecycleHold('explicit PP two-market readback gate required')
            limits = TwoMarketReadbackLimits()
        permit = None
        if args.retire_with_pp_permit:
            if os.environ.get('TRADEBOT_PP_EXACT_RETIREMENT') != 'true':
                raise LifecycleHold('explicit PP retirement gate required')
            from .supabase_storage import read_token_file
            ticket = read_token_file('/run/secrets/pp_retirement_ticket')
            permit = Permit(ticket, os.environ.get('TRADEBOT_PP_VERIFIED_SOURCE',''),
                            os.environ.get('TRADEBOT_PP_POLICY_EPOCH_SHA256',''),
                            os.environ.get('TRADEBOT_PP_HISTORY_READER_PROOF_SHA256',''))
            permit.validate()
        if args.inventory_only:
            result = verify(LifecycleRepository(factory), None, target, inventory_only=True, limits=limits)
            print(json.dumps(result,sort_keys=True))
            return 1 if result['status'] == 'HOLD' or result.get('operation_deadline_met') is False else 0
        history_factory = retirement_history_factory(os.environ)
        raw=SupabaseStorageTransport.from_machine_files(*(
            FILES['TRADEBOT_PP_STORAGE_'+key+'_FILE'] for key in ('API_KEY','AUTH_EMAIL','AUTH_PASSWORD','AUTH_UID')))
        structured=HistoryV2PostgresTransport(history_factory,origin_id=ORIGIN,
            generation_id=target.sealed,expected_database='postgres',expected_role='tradebot_pp_history')
        scoped=RetirementTransport(raw,structured,origin_id=ORIGIN,generation_id=target.sealed)
        result = verify(LifecycleRepository(factory),scoped,target,permit=permit,limits=limits)
        print(json.dumps(result,sort_keys=True))
        return 1 if result['status'] == 'HOLD' or result.get('operation_deadline_met') is False else 0
    except Exception as error:
        print(json.dumps({'status':'HOLD','retirement_authorized':False,
                          'reason':getattr(error,'code',type(error).__name__),
                          'partition_outcome':('inspect_generation_and_ticket' if args.retire_with_pp_permit
                                               else 'readback_only'),
                          'phase_accounting':getattr(error,'retirement_accounting',None)}))
        return 1
    finally:
        if history_factory is not None and hasattr(history_factory, 'close'):
            history_factory.close()
        if raw is not None:
            raw.close()


if __name__=='__main__':
    raise SystemExit(main())
