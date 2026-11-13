"""Default-off CP4 lifecycle process. No real feeds, cloud I/O, or retirement."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import threading

from .lifecycle import LifecycleRepository, RotationPolicy


def configuration(environ):
    mode = environ.get('TRADEBOT_DATA_MODE', 'generated')
    if mode not in ('generated', 'replay'):
        raise ValueError('CP4 worker supports generated/replay mode only')
    if environ.get('TRADEBOT_CLOUD_ENABLED', 'false').lower() != 'false':
        raise ValueError('cloud mutation authority remains CP6-unqualified')
    if environ.get('TRADEBOT_RETIREMENT_ENABLED', 'false').lower() != 'false':
        raise ValueError('runtime retirement remains OFF')
    origin = environ.get('TRADEBOT_ORIGIN_ID', 'generated-pp')
    if mode == 'generated' and not origin.startswith('generated-'):
        raise ValueError('generated mode requires generated- origin namespace')
    size = environ.get('TRADEBOT_QUALIFIED_GENERATION_BYTES')
    return {'origin_id': origin, 'mode': mode,
            'policy': RotationPolicy(int(size) if size else None),
            'pending_outbox_limit': int(environ.get('TRADEBOT_OUTBOX_MAX_PENDING', '10000'))}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--bootstrap', action='store_true', help='explicitly prepare first generated A generation')
    parser.add_argument('--interval-seconds', type=float, default=30)
    args = parser.parse_args(argv)
    if not 1 <= args.interval_seconds <= 60:
        parser.error('interval must be 1..60 seconds')
    config = configuration(os.environ)
    from .connection import connect
    from .migrate import validate_schema
    dsn_file = os.environ.get('DSN_FILE')
    if not dsn_file:
        parser.error('DSN_FILE required for dedicated lifecycle identity')
    dsn = Path(dsn_file).read_text().strip()
    factory = lambda: connect(dsn, environment='preprod')
    with factory() as connection:
        validate_schema(connection, 'preprod')
    repository = LifecycleRepository(factory, pending_outbox_limit=config['pending_outbox_limit'])
    if args.bootstrap:
        if config['mode'] != 'generated':
            parser.error('bootstrap flag is only for isolated generated qualification')
        repository.bootstrap(config['origin_id'])
    stop = threading.Event()
    for name in ('SIGINT', 'SIGTERM'):
        signal.signal(getattr(signal, name), lambda *_: stop.set())
    while not stop.is_set():
        try:
            result = repository.switch_if_due(config['origin_id'], config['policy'])
            result.update(archive='held_no_qualified_transport', retirement='off')
            print(json.dumps(result), flush=True)
        except Exception as error:
            # DSN, SQL values, and provider responses never reach process logs.
            print(json.dumps({'status': 'held', 'reason': getattr(error, 'code', type(error).__name__),
                              'archive': 'held_no_qualified_transport', 'retirement': 'off'}), flush=True)
            if args.once:
                return 1
        if args.once:
            return 0
        stop.wait(args.interval_seconds)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
