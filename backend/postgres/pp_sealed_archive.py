"""Recurring PP raw archival. A sealed generation stays local after verification."""
import argparse
import json
import os
import signal
from threading import Event

from .archive_codec import ArchiveError, ArchiveLimit, ArchiveLimits, ArchiveUnavailable, CycleBudget
from .archive_transport import ScopedArchiveTransport
from .lifecycle import ArchiveWorker, LifecycleHold, LifecycleRepository
from .pp_raw_archive_probe import FILES, OFF_FLAGS, ORIGIN
from .pp_structured_probe import LOCAL_DSN, private_dsn


# These are the existing archive codec/Storage bounds. Real throughput must
# be measured on PP before selecting a rotation size for continuous use.
LIMITS = ArchiveLimits(max_rows=500, max_requests=8)
MANIFEST_LIMIT = 128


class RawWorker(ArchiveWorker):
    def sync_outbox(self, generation_id, budget):
        if self.repository.outbox(generation_id, 1, LIMITS.max_decoded_bytes):
            raise LifecycleHold('sealed structured records awaiting verified acknowledgement')
        return 0


def cycle(repository, raw, origin=ORIGIN):
    with CycleBudget(LIMITS) as budget, repository.structured_sync_lock(origin):
        with repository.transaction() as connection:
            row = connection.execute("""SELECT generation_id,seal_count FROM archive.generations
                WHERE origin_id=%s AND state='sealed' ORDER BY sealed_at,generation_id LIMIT 1""",
                (origin,)).fetchone()
        if row is None:
            return {'status': 'idle'}
        generation = str(row['generation_id'])
        if row['seal_count'] > MANIFEST_LIMIT * LIMITS.max_rows:
            raise ArchiveLimit('sealed generation exceeds bounded catalog')
        manifests = repository.manifests(generation)
        if len(manifests) == MANIFEST_LIMIT:
            # Crash between the final manifest commit and mark_verified may
            # leave a complete catalog; allow finalization, never page 129.
            if sum(item['row_count'] for item in manifests) != row['seal_count']:
                raise ArchiveLimit('sealed generation exhausted catalog')
        transport = ScopedArchiveTransport(raw, None, origin_id=origin, generation_id=generation)
        worker = RawWorker(repository, transport, LIMITS)
        result = worker._archive_cycle(generation, budget)
        return {'status': result['status'], 'rows': result['raw_rows'],
                'generation_id': generation, 'retirement': 'off'}


def serve(repository, raw, stopped):
    delay = 1
    while not stopped.is_set():
        try:
            result = cycle(repository, raw)
            delay = 5 if result['status'] == 'idle' else 0.1
        except (ArchiveUnavailable, LifecycleHold) as error:
            result = {'status': 'waiting', 'reason': error.code}
            delay = min(60, max(1, delay * 2))
        except ArchiveError as error:
            print(json.dumps({'status': 'hold', 'reason': error.code}), flush=True)
            return 1
        print(json.dumps(result), flush=True)
        stopped.wait(delay)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    required = {name: FILES[name] for name in FILES if 'HISTORY' not in name}
    required.update(TRADEBOT_ENVIRONMENT='preprod', TRADEBOT_DATA_MODE='pp_live',
                    TRADEBOT_ORIGIN_ID=ORIGIN, TRADEBOT_PP_SEALED_ARCHIVE='true')
    if (not args.execute or any(os.getenv(k) != v for k, v in required.items())
            or os.getenv('TRADEBOT_DATABASE_DSN') or
            any(os.getenv(flag, 'false').lower() not in ('false', 'off', '0') for flag in OFF_FLAGS)):
        return 1
    from .connection import connect
    from .migrate import validate_schema
    from .supabase_storage import SupabaseStorageTransport
    stopped = Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    try:
        dsn = private_dsn(LOCAL_DSN)
        factory = lambda: connect(dsn, environment='preprod')
        with factory() as connection:
            if connection.execute('SELECT current_user AS role').fetchone()['role'] != 'tradebot_lifecycle':
                raise LifecycleHold('wrong database role')
            validate_schema(connection, 'preprod')
        raw = SupabaseStorageTransport.from_machine_files(*(
            FILES['TRADEBOT_PP_STORAGE_' + name + '_FILE']
            for name in ('API_KEY', 'AUTH_EMAIL', 'AUTH_PASSWORD', 'AUTH_UID')))
        try:
            return serve(LifecycleRepository(factory), raw, stopped)
        finally:
            raw.close()
    except Exception as error:
        print(json.dumps({'status': 'hold', 'reason': type(error).__name__}), flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
