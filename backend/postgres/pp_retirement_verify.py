"""Exact-target, fresh PP retirement readback. This command never drops a partition."""
import argparse
from dataclasses import dataclass
import json
import os
import re
import uuid

from .archive_codec import ArchiveLimits, CycleBudget
from .archive_transport import ScopedArchiveTransport
from .lifecycle import ArchiveWorker, LifecycleHold, LifecycleRepository
from .pp_raw_archive_probe import FILES, ORIGIN, check_environment
from .pp_retirement_report import active_sample, bound_catalog
from .pp_structured_probe import LOCAL_DSN, private_dsn


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


def verify(repository, transport, target, *, limits=ArchiveLimits(), origin=ORIGIN):
    target.validate()
    if (repository.environment != 'preprod' or transport.origin_id != origin
            or transport.generation_id != target.sealed or
            (origin != ORIGIN and not origin.startswith('generated-'))):
        raise LifecycleHold('wrong retirement readback environment or generation')
    worker = ArchiveWorker(repository, transport, limits)
    with CycleBudget(limits) as budget, repository.retirement(target.sealed) as (db, generation, manifests):
        if (generation['origin_id'] != origin or generation['seal_count'] != target.count
                or generation['seal_hash'] != target.seal_hash or not bound_catalog(generation,manifests)):
            raise LifecycleHold('reviewed seal or authenticated catalog changed')
        before = active_sample(db, origin)
        if (not before or before['generation_id'] != target.collecting
                or before['slot'] == generation['slot']):
            raise LifecycleHold('reviewed active slot changed')
        readback = worker.fresh_retirement_readback(db, generation, manifests, budget)
        after = active_sample(db, origin)
        if (not after or after['generation_id'] != target.collecting
                or after['slot'] != before['slot'] or after['committed_rows'] <= before['committed_rows']):
            raise LifecycleHold('concurrent opposite-slot persistence unobserved')
        budget.check()
    return {'status':'fresh_readback_verified','retirement_authorized':False,
            'policy_version':'pp-retirement-readback-v2','sealed':target.sealed,
            'collecting':target.collecting,'opposite_slot_new_rows':after['committed_rows']-before['committed_rows'],
            **readback}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sealed',required=True)
    parser.add_argument('--collecting',required=True)
    parser.add_argument('--seal-hash',required=True)
    parser.add_argument('--count',required=True,type=int)
    args=parser.parse_args()
    raw=None
    try:
        target=Target(**vars(args))
        target.validate()
        check_environment(os.environ)
        if os.environ.get('TRADEBOT_PP_RETIREMENT_READBACK') != 'true':
            raise LifecycleHold('explicit one-shot readback required')
        from .connection import connect
        from .history_v2_transport import HistoryV2PostgresTransport
        from .migrate import validate_schema
        from .pp_history_connection import PPHistoryConnectionFactory
        from .supabase_storage import SupabaseStorageTransport
        dsn = private_dsn(LOCAL_DSN)
        def factory():
            return connect(dsn, environment='preprod')
        with factory() as db:
            if db.execute('SELECT current_user AS role').fetchone()['role'] != 'tradebot_lifecycle':
                raise LifecycleHold('incorrect local readback identity')
            validate_schema(db,'preprod')
        raw=SupabaseStorageTransport.from_machine_files(*(
            FILES['TRADEBOT_PP_STORAGE_'+key+'_FILE'] for key in ('API_KEY','AUTH_EMAIL','AUTH_PASSWORD','AUTH_UID')))
        structured=HistoryV2PostgresTransport(PPHistoryConnectionFactory(),origin_id=ORIGIN,
            generation_id=target.sealed,expected_database='postgres',expected_role='tradebot_pp_history')
        scoped=RetirementTransport(raw,structured,origin_id=ORIGIN,generation_id=target.sealed)
        print(json.dumps(verify(LifecycleRepository(factory),scoped,target),sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps({'status':'HOLD','retirement_authorized':False,
                          'reason':getattr(error,'code',type(error).__name__)}))
        return 1
    finally:
        if raw is not None:
            raw.close()


if __name__=='__main__':
    raise SystemExit(main())
