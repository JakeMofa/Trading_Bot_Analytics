"""Explicit, default-OFF one-cycle PP structured-history diagnostic.

This is not a service entrypoint. It imports at most one bounded outbox page,
requires fresh authenticated cloud readback before local ACK, and cannot
authorize raw archive acceptance or local partition retirement.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import uuid

from .active_structured import ActiveStructuredWorker, SealedStructuredWorker
from .archive_codec import ArchiveLimits
from .lifecycle import LifecycleHold, LifecycleRepository


ORIGIN = 'pp-live-pp'
LOCAL_DSN = Path('/run/secrets/lifecycle_dsn')
MAX_PENDING = 10_000
LIMITS = ArchiveLimits(max_rows=25, max_object_bytes=256 * 1024,
                       max_decoded_bytes=256 * 1024, max_cycle_bytes=512 * 1024,
                       max_requests=2, max_seconds=20, request_timeout_seconds=4)
OFF_FLAGS = ('ENABLE_SUPABASE_SYNC', 'ENABLE_LOCAL_RETENTION',
             'ENABLE_OPENAI_ANALYST', 'TRADEBOT_CLOUD_ENABLED',
             'TRADEBOT_RETIREMENT_ENABLED')


def check_environment(environ: dict[str, str], *, recurring=False) -> None:
    enabled = ('TRADEBOT_PP_STRUCTURED_RECURRING' if recurring
               else 'TRADEBOT_PP_STRUCTURED_ONE_SHOT')
    other = ('TRADEBOT_PP_STRUCTURED_ONE_SHOT' if recurring
             else 'TRADEBOT_PP_STRUCTURED_RECURRING')
    if (environ.get('TRADEBOT_ENVIRONMENT') != 'preprod' or
            environ.get('TRADEBOT_DATA_MODE') != 'pp_live' or
            environ.get('TRADEBOT_ORIGIN_ID') != ORIGIN or
            environ.get(enabled) != 'true' or environ.get(other, 'false') != 'false'):
        raise LifecycleHold('exact PP structured worker identity required')
    if any(environ.get(flag, 'false').lower() not in ('false', '0', 'off')
           for flag in OFF_FLAGS):
        raise LifecycleHold('cloud service, retirement and paid AI must remain OFF')
    if environ.get('TRADEBOT_DATABASE_DSN_FILE') != str(LOCAL_DSN) or \
            environ.get('TRADEBOT_DATABASE_DSN'):
        raise LifecycleHold('exact local lifecycle credential file required')


def private_dsn(path: Path) -> str:
    """Read only the fixed mounted lifecycle credential; never log its value."""
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
            info.st_uid not in (0, os.geteuid()) or
            info.st_mode & 0o077 or not 1 <= info.st_size <= 4096):
        raise LifecycleHold('unsafe lifecycle credential file')
    value = path.read_text().strip()
    if not value:
        raise LifecycleHold('empty lifecycle credential file')
    return value


class PinnedRepository:
    """Recheck the selected page inside the worker's same-origin sync lock."""

    def __init__(self, repository, *, expected_state: str,
                 expected_first_id: int):
        self.repository = repository
        self.expected_state = expected_state
        self.expected_first_id = expected_first_id

    def __getattr__(self, name):
        return getattr(self.repository, name)

    def generation(self, generation_id):
        row = self.repository.generation(generation_id)
        if row['origin_id'] != ORIGIN or row['state'] != self.expected_state:
            raise LifecycleHold('generation changed after operator review')
        return row

    def outbox(self, generation_id, limit, max_bytes):
        with self.repository.transaction() as connection:
            bounded = connection.execute('''SELECT count(*) AS total FROM
                (SELECT 1 FROM ops.outbox WHERE origin_id=%s AND
                 acknowledged_at IS NULL LIMIT %s) AS pending''',
                (ORIGIN, MAX_PENDING + 1)).fetchone()['total']
        if bounded > MAX_PENDING:
            raise LifecycleHold('PP structured backlog exceeds reviewed cap')
        rows = self.repository.outbox(generation_id, limit, max_bytes)
        if not rows or rows[0]['id'] != self.expected_first_id:
            raise LifecycleHold('first pending outbox identity changed')
        return rows


def probe_once(repository, transport, *, generation_id: str,
               expected_state: str, expected_first_id: int) -> dict:
    if (expected_state not in ('collecting', 'sealed', 'verified') or
            isinstance(expected_first_id, bool) or
            not isinstance(expected_first_id, int) or expected_first_id <= 0):
        raise ValueError('invalid reviewed PP outbox target')
    try:
        if str(uuid.UUID(generation_id)) != generation_id:
            raise ValueError('noncanonical generation')
    except (TypeError, ValueError, AttributeError):
        raise ValueError('invalid reviewed generation identity') from None
    pinned = PinnedRepository(repository, expected_state=expected_state,
                              expected_first_id=expected_first_id)
    worker = (ActiveStructuredWorker if expected_state == 'collecting'
              else SealedStructuredWorker)(pinned, transport, origin_id=ORIGIN,
                                           limits=LIMITS)
    result = worker.cycle(generation_id)
    return {'status': result['status'], 'origin_id': ORIGIN,
            'generation_id': generation_id,
            'acknowledged': result['acknowledged'],
            'retirement': 'off', 'raw_archive': 'not_started',
            'bounds': {'rows': LIMITS.max_rows,
                       'decoded_bytes': LIMITS.max_decoded_bytes,
                       'cloud_operations': LIMITS.max_requests,
                       'seconds': LIMITS.max_seconds}}


def main(argv=None, environ=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generation-id', required=True)
    parser.add_argument('--expected-state', choices=('collecting', 'sealed', 'verified'),
                        required=True)
    parser.add_argument('--expected-first-outbox-id', type=int, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({'status': 'STOP', 'reason': 'explicit_execute_required'}))
        return 1
    try:
        check_environment(dict(os.environ if environ is None else environ))
        from .connection import connect
        from .history_v2_transport import HistoryV2PostgresTransport
        from .migrate import validate_schema
        from .pp_history_connection import PPHistoryConnectionFactory

        dsn = private_dsn(LOCAL_DSN)
        factory = lambda: connect(dsn, environment='preprod')
        with factory() as connection:
            validate_schema(connection, 'preprod')
        repository = LifecycleRepository(factory, environment='preprod',
                                         pending_outbox_limit=MAX_PENDING)
        transport = HistoryV2PostgresTransport(
            PPHistoryConnectionFactory(), origin_id=ORIGIN,
            generation_id=args.generation_id, expected_database='postgres',
            expected_role='tradebot_pp_history')
        result = probe_once(repository, transport,
                            generation_id=args.generation_id,
                            expected_state=args.expected_state,
                            expected_first_id=args.expected_first_outbox_id)
    except Exception as error:
        # Never log a DSN, provider response, SQL row, or exception text.
        print(json.dumps({'status': 'HOLD',
                          'reason': getattr(error, 'code', type(error).__name__),
                          'ack_status': 'unconfirmed_after_error',
                          'retirement': 'off'}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
