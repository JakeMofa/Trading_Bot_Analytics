"""Default-OFF, one-cycle PP raw archive diagnostic for a sealed generation.

This module has no service or host-controller route. It may upload and verify
one bounded raw page only after a separately reviewed one-use execution path
mounts the restricted Storage and structured-history credentials. It never
authorizes local partition retirement.
"""
from __future__ import annotations

import argparse
import json
import os
import uuid

from .archive_codec import ArchiveLimits, CycleBudget
from .archive_transport import ScopedArchiveTransport
from .lifecycle import ArchiveWorker, LifecycleHold, LifecycleRepository
from .pp_structured_probe import LOCAL_DSN, private_dsn


ORIGIN = 'pp-live-pp'
FILES = {
    'TRADEBOT_DATABASE_DSN_FILE': '/run/secrets/lifecycle_dsn',
    'TRADEBOT_PP_HISTORY_DSN_FILE': '/run/secrets/pp_history_dsn',
    'TRADEBOT_PP_HISTORY_CA_FILE': '/run/secrets/pp_history_ca',
    'TRADEBOT_PP_STORAGE_API_KEY_FILE': '/run/secrets/pp_storage_api_key',
    'TRADEBOT_PP_STORAGE_AUTH_EMAIL_FILE': '/run/secrets/supabase_auth_email',
    'TRADEBOT_PP_STORAGE_AUTH_PASSWORD_FILE': '/run/secrets/supabase_auth_password',
    'TRADEBOT_PP_STORAGE_AUTH_UID_FILE': '/run/secrets/supabase_auth_uid',
}
OFF_FLAGS = ('ENABLE_SUPABASE_SYNC', 'ENABLE_LOCAL_RETENTION',
             'ENABLE_OPENAI_ANALYST', 'TRADEBOT_CLOUD_ENABLED',
             'TRADEBOT_RETIREMENT_ENABLED', 'TRADEBOT_COLLECTOR_ENABLED')
LIMITS = ArchiveLimits(max_rows=25, max_object_bytes=256 * 1024,
                       max_decoded_bytes=256 * 1024,
                       max_cycle_bytes=1024 * 1024, max_requests=8,
                       max_seconds=20, request_timeout_seconds=4)


def check_environment(environ: dict[str, str]) -> None:
    if (environ.get('TRADEBOT_ENVIRONMENT') != 'preprod' or
            environ.get('TRADEBOT_DATA_MODE') != 'pp_live' or
            environ.get('TRADEBOT_ORIGIN_ID') != ORIGIN or
            environ.get('TRADEBOT_PP_RAW_ARCHIVE_ONE_SHOT') != 'true'):
        raise LifecycleHold('exact PP archive one-shot identity required')
    if any(environ.get(flag, 'false').lower() not in ('false', '0', 'off')
           for flag in OFF_FLAGS):
        raise LifecycleHold('persistent cloud, collector, retirement and paid AI must remain OFF')
    if environ.get('TRADEBOT_DATABASE_DSN') or any(
            environ.get(name) != path for name, path in FILES.items()):
        raise LifecycleHold('exact independent PP archive secret paths required')


class PinnedRepository:
    """Reject a changed generation or reviewed manifest count before cloud I/O."""

    def __init__(self, repository, generation_id: str, seal_count: int,
                 manifest_count: int):
        self.repository = repository
        self.generation_id = generation_id
        self.seal_count = seal_count
        self.manifest_count = manifest_count

    def __getattr__(self, name):
        return getattr(self.repository, name)

    def generation(self, generation_id):
        row = self.repository.generation(generation_id)
        if (generation_id != self.generation_id or row['origin_id'] != ORIGIN or
                row['state'] != 'sealed' or row['seal_count'] != self.seal_count):
            raise LifecycleHold('sealed generation changed after review')
        return row

    def manifests(self, generation_id):
        rows = self.repository.manifests(generation_id)
        if generation_id != self.generation_id or len(rows) != self.manifest_count:
            raise LifecycleHold('archive progress changed after review')
        return rows

    def outbox(self, generation_id, limit, max_bytes):
        # The archive worker syncs structured rows before it reads manifests.
        # Recheck reviewed progress before its first possible cloud write.
        self.generation(generation_id)
        self.manifests(generation_id)
        return self.repository.outbox(generation_id, limit, max_bytes)


def archive_once(repository, transport, *, generation_id: str,
                 expected_seal_count: int, expected_manifest_count: int) -> dict:
    try:
        if str(uuid.UUID(generation_id)) != generation_id:
            raise ValueError('noncanonical generation')
    except (TypeError, ValueError, AttributeError):
        raise ValueError('invalid reviewed generation identity') from None
    if (isinstance(expected_seal_count, bool) or
            not isinstance(expected_seal_count, int) or expected_seal_count < 0 or
            isinstance(expected_manifest_count, bool) or
            not isinstance(expected_manifest_count, int) or
            not 0 <= expected_manifest_count <= 128):
        raise ValueError('invalid reviewed generation count')
    pinned = PinnedRepository(repository, generation_id, expected_seal_count,
                              expected_manifest_count)
    with CycleBudget(LIMITS) as overall:
        with repository.structured_sync_lock(ORIGIN):
            # No cloud call is made if the reviewed seal or progress changed.
            pinned.generation(generation_id)
            pinned.manifests(generation_id)
            result = ArchiveWorker(pinned, transport, LIMITS).archive_cycle(generation_id)
            overall.check()
    return {'status': 'cycle_complete', 'raw_coverage': result['status'],
            'origin_id': ORIGIN,
            'generation_id': generation_id, 'outbox_rows': result['outbox_rows'],
            'raw_rows': result['raw_rows'], 'retirement': 'off',
            'bounds': {'rows': LIMITS.max_rows,
                       'decoded_bytes': LIMITS.max_decoded_bytes,
                       'cloud_operations': LIMITS.max_requests,
                       'seconds': LIMITS.max_seconds}}


def main(argv=None, environ=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generation-id', required=True)
    parser.add_argument('--expected-seal-count', required=True, type=int)
    parser.add_argument('--expected-manifest-count', required=True, type=int)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({'status': 'STOP', 'reason': 'explicit_execute_required'}))
        return 1
    raw = None
    try:
        check_environment(dict(os.environ if environ is None else environ))
        from .connection import connect
        from .history_v2_transport import HistoryV2PostgresTransport
        from .migrate import validate_schema
        from .pp_history_connection import PPHistoryConnectionFactory
        from .supabase_storage import SupabaseStorageTransport

        dsn = private_dsn(LOCAL_DSN)
        factory = lambda: connect(dsn, environment='preprod')
        with factory() as connection:
            validate_schema(connection, 'preprod')
        repository = LifecycleRepository(factory, environment='preprod')
        raw = SupabaseStorageTransport.from_machine_files(
            FILES['TRADEBOT_PP_STORAGE_API_KEY_FILE'],
            FILES['TRADEBOT_PP_STORAGE_AUTH_EMAIL_FILE'],
            FILES['TRADEBOT_PP_STORAGE_AUTH_PASSWORD_FILE'],
            FILES['TRADEBOT_PP_STORAGE_AUTH_UID_FILE'])
        structured = HistoryV2PostgresTransport(
            PPHistoryConnectionFactory(), origin_id=ORIGIN,
            generation_id=args.generation_id, expected_database='postgres',
            expected_role='tradebot_pp_history')
        transport = ScopedArchiveTransport(raw, structured,
            origin_id=ORIGIN, generation_id=args.generation_id)
        result = archive_once(repository, transport,
            generation_id=args.generation_id,
            expected_seal_count=args.expected_seal_count,
            expected_manifest_count=args.expected_manifest_count)
    except Exception as error:
        # Never log credentials, provider responses, SQL rows or exception text.
        print(json.dumps({'status': 'HOLD',
                          'reason': getattr(error, 'code', type(error).__name__),
                          'retirement': 'off'}))
        return 1
    finally:
        if raw is not None:
            raw.close()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
