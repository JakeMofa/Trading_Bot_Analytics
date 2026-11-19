"""Default-off PP generation switcher. No feed intake, cloud I/O, or retirement."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import threading

from .lifecycle import LifecycleRepository, RotationPolicy
from .rehearsal_profile import cycle_anchor, CYCLE_POLICY


def configuration(environ):
    if environ.get('TRADEBOT_ENVIRONMENT', 'preprod') != 'preprod':
        raise ValueError('CP4 worker supports isolated preprod only')
    mode = environ.get('TRADEBOT_DATA_MODE', 'generated')
    if mode not in ('generated', 'replay', 'pp_live'):
        raise ValueError('unsupported PP lifecycle mode')
    disabled = {'false', '0', 'off'}
    if environ.get('TRADEBOT_COLLECTOR_ENABLED', 'false').lower() not in disabled:
        raise ValueError('real collector must remain OFF')
    if environ.get('TRADEBOT_CLOUD_ENABLED', 'false').lower() not in disabled:
        raise ValueError('cloud mutation authority remains CP6-unqualified')
    if environ.get('TRADEBOT_RETIREMENT_ENABLED', 'false').lower() not in disabled:
        raise ValueError('runtime retirement remains OFF')
    origin = environ.get('TRADEBOT_ORIGIN_ID', 'generated-pp')
    if not origin or len(origin) > 128:
        raise ValueError('origin identity required and bounded')
    if mode == 'generated' and not origin.startswith('generated-'):
        raise ValueError('generated mode requires generated- origin namespace')
    if mode == 'pp_live' and (not origin.startswith('pp-live-') or
                              len(origin) <= len('pp-live-') or
                              environ.get('TRADEBOT_PP_LIVE_LIFECYCLE') != 'true'):
        raise ValueError('PP live lifecycle requires explicit origin and opt-in')
    if mode != 'pp_live' and origin.startswith('pp-live-'):
        raise ValueError('PP live origin cannot be used for test lifecycle')
    size = environ.get('TRADEBOT_QUALIFIED_GENERATION_BYTES')
    trial = environ.get('TRADEBOT_PP_WINDOW_POLICY')
    anchor = cycle_anchor(environ)
    if trial is not None and (trial not in ('two-official-markets', CYCLE_POLICY) or mode != 'pp_live'
            or environ.get('TRADEBOT_ENVIRONMENT') != 'preprod' or origin != 'pp-live-pp'):
        raise ValueError('invalid PP market-window qualification profile')
    if mode == 'pp_live' and size is not None:
        raise ValueError('PP live size override unavailable')
    pending = int(environ.get('TRADEBOT_OUTBOX_MAX_PENDING', '10000'))
    if not 10 <= pending <= 100000:
        raise ValueError('pending outbox bound must be 10..100000')
    from .generated_storage import requested
    generated_storage=requested(environ,mode,origin)
    return {'origin_id': origin, 'mode': mode, 'generated_storage':generated_storage,
            'policy': RotationPolicy(int(size) if size else None),
            'pending_outbox_limit': pending, 'market_pair_trial': trial is not None, 'rehearsal_anchor': anchor}


def read_dsn(environ):
    path = environ.get('TRADEBOT_DATABASE_DSN_FILE')
    if not path:
        raise ValueError('TRADEBOT_DATABASE_DSN_FILE required for dedicated lifecycle identity')
    if environ.get('TRADEBOT_DATABASE_DSN'):
        raise ValueError('lifecycle runtime requires one file-based database credential source')
    value = Path(path).read_text().strip()
    if not value:
        raise ValueError('lifecycle database credential file is empty')
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--bootstrap', action='store_true', help='explicitly prepare first generated A generation')
    operation=parser.add_mutually_exclusive_group()
    operation.add_argument('--stop-collector', action='store_true', help='durably stop a PP live collector only')
    operation.add_argument('--collector-status', action='store_true', help='read the PP live collector lease only')
    parser.add_argument('--interval-seconds', type=float, default=30)
    args = parser.parse_args(argv)
    if (args.stop_collector or args.collector_status) and (args.once or args.bootstrap):
        parser.error('collector recovery commands cannot run bootstrap or rotation')
    if not 1 <= args.interval_seconds <= 60:
        parser.error('interval must be 1..60 seconds')
    config = configuration(os.environ)
    if (args.stop_collector or args.collector_status) and config['mode'] != 'pp_live':
        parser.error('collector recovery commands require explicit PP live mode')
    from .connection import connect
    from .migrate import validate_schema
    dsn = read_dsn(os.environ)
    factory = lambda: connect(dsn, environment='preprod')
    with factory() as connection:
        validate_schema(connection, 'preprod')
    repository = LifecycleRepository(factory, pending_outbox_limit=config['pending_outbox_limit'])
    if args.stop_collector or args.collector_status:
        if args.stop_collector:
            result=repository.disable_collector(config['origin_id'])
            print(json.dumps({'environment':'preprod','origin_id':config['origin_id'],
                              'collector_enabled':result['collector_enabled'],
                              'epoch':result['epoch']}),flush=True)
        else:
            result=repository.collector_state(config['origin_id'])
            print(json.dumps({'environment':'preprod','origin_id':config['origin_id'],
                              'collector_enabled':result['collector_enabled'],
                              'initialized':result['initialized'],
                              'epoch':result['epoch']}),flush=True)
        return 0
    if args.bootstrap:
        if config['mode'] not in ('generated', 'pp_live'):
            parser.error('bootstrap requires a generated or explicitly enabled PP live origin')
        repository.bootstrap(config['origin_id'])
    stop = threading.Event()
    for name in ('SIGINT', 'SIGTERM'):
        signal.signal(getattr(signal, name), lambda *_: stop.set())
    while not stop.is_set():
        try:
            generated=None
            if config['generated_storage']:
                from .generated_storage import drain
                generated=drain(repository)
            result = repository.switch_if_due(config['origin_id'], config['policy'],
                                              require_live_lease=config['mode'] == 'pp_live',
                                              market_pair_trial=config['market_pair_trial'],
                                              rehearsal_anchor=config['rehearsal_anchor'])
            result.update(archive='held_no_qualified_transport', retirement='off')
            if generated is not None:result['generated_storage']=generated
            if config['mode'] == 'pp_live' and result.get('reason') in (
                    'other_slot_not_retired','pp_filesystem_reserve','pp_filesystem_sample_unavailable'):
                # The repository atomically committed OFF with the hold. The
                # supervisor must not keep presenting this as normal rotation.
                if result.get('collector_enabled') is not False:
                    raise ValueError('PP collector OFF not proven after occupied slot')
                print(json.dumps(result), flush=True)
                return 1
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
