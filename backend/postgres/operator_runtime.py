"""Dedicated PP operator API runtime; not part of the dashboard container.

This module does not enable collection. The reviewed host profile must mount
only the lifecycle DSN and operator token into a separate loopback-bound
service before it is reachable. No environment credential values are accepted.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat
import asyncio
import uuid

import httpx

from .connection import connect
from .lifecycle import LifecycleRepository
from .migrate import validate_schema
from .operator_api import create_operator_app
from .operator_session import OperatorSession
from .collector_session import run_session
from .config import Settings
from .cloud_origin_binding import DISPLAY_ORIGIN
from .watch_lease import WatchLease
from .store import Store
from .rehearsal_profile import (BOUNDARY_ORIGINS, boundary_anchor, boundary_lease_seconds, cycle_anchor,
                                elapsed_cycle_seconds, lease_cap)


def _owner_reader(app_dsn, connector=connect, *, watch_ownership=False):
    from psycopg import OperationalError
    from .live_diagnostics import OwnershipConnectionLimit, connection_capacity

    def open_readonly():
        try:
            return connector(app_dsn, environment='preprod', readonly=True)
        except OperationalError as error:
            if watch_ownership and connection_capacity(error):
                raise OwnershipConnectionLimit() from None
            raise
    return LifecycleRepository(open_readonly)


def build_live_session(repository, origin, app_dsn, *, rehearsal_anchor=None, rehearsal_window_seconds=None,
                       diagnostic_anchor=None):
    """Prepare a PP-only, explicitly started source task with a finite lease."""
    store = Store(Settings(environment='preprod', data_mode='pp_live',
                           origin_id=origin, dsn=app_dsn))
    store.verify()
    owner_reader = _owner_reader(app_dsn, watch_ownership=origin == DISPLAY_ORIGIN)

    watch = WatchLease(repository, diagnostic_anchor) if origin == DISPLAY_ORIGIN else None

    async def run(stop, max_seconds):
        if origin in BOUNDARY_ORIGINS:
            state = await asyncio.to_thread(repository.collector_state, origin)
            if watch is not None:
                generation_id = await asyncio.to_thread(watch.admit, max_seconds)
            elif (not diagnostic_anchor or state['generation_id'] != diagnostic_anchor
                    or state['epoch'] != 1 or state['stored_enabled'] or max_seconds != boundary_lease_seconds(origin)):
                raise ValueError('exact unused diagnostic generation required')
            else:
                generation_id = diagnostic_anchor
        else:
            generation = await asyncio.to_thread(repository.bootstrap, origin)
            generation_id = str(generation['generation_id'])
        if rehearsal_anchor is not None and generation_id != rehearsal_anchor:
            raise ValueError('two-leg initial A differs from configured generation')
        session_id = str(uuid.uuid4())
        enabled = False

        def owner_check():
            return (owner_reader.owns_collector(origin, session_id) if enabled
                    else not owner_reader.collector_state(origin)['collector_enabled'])

        def enable():
            nonlocal enabled
            if watch is not None:
                watch.session_id = session_id
            result = repository.enable_collector(origin, session_id=session_id,
                         expected_generation_id=generation_id, max_seconds=max_seconds,
                         **({'rehearsal_anchor': rehearsal_anchor} if rehearsal_anchor else {}),
                         **({'rehearsal_window_seconds': rehearsal_window_seconds}
                            if rehearsal_window_seconds is not None else {}))
            enabled = True
            return result

        def disable():
            if watch is not None:
                return watch.release(session_id)
            return repository.disable_collector(origin)

        async with httpx.AsyncClient(timeout=4, follow_redirects=False) as client:
            # Never change an object another source thread may retain after stop.
            source_store = Store(store.settings, producer_session_id=session_id) if watch else store
            return await run_session(source_store, client, stop, owner_check=owner_check,
                         enable_collector=enable,
                         disable_collector=disable,
                         max_seconds=max_seconds,
                         **({'rehearsal_anchor': rehearsal_anchor} if rehearsal_anchor else {}))

    result = OperatorSession(run, lambda: watch.release(watch.session_id) if watch else repository.disable_collector(origin),
                             rehearsal_anchor=rehearsal_anchor)
    if watch:
        result.renew_watch = watch.renew
        result.watch_explicit_off = watch.explicit_off
        result.set_watch_off = watch.set_explicit_off
    return result


def fence_live_startup(repository, origin):
    """A restarted operator cannot inherit a previous process's ON lease."""
    state = repository.collector_state(origin)
    if state['initialized'] and state.get('stored_enabled'):
        stopped = repository.disable_collector(origin)
        if stopped.get('collector_enabled') is not False:
            raise ValueError('PP live startup durable OFF unproven')
    after = repository.collector_state(origin)
    if after['collector_enabled'] or after.get('stored_enabled'):
        raise ValueError('PP live startup collector still enabled')


def _secret(directory: Path, name: str, *, expected_uid: int):
    if directory != Path('/run/secrets') and not directory.is_absolute():
        raise ValueError('absolute secret directory required')
    parent = directory.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid not in (0, expected_uid) or \
            parent.st_mode & 0o022:
        raise ValueError('unsafe operator secret directory')
    path = directory / name
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != expected_uid or \
                stat.S_IMODE(info.st_mode) != 0o400 or info.st_nlink != 1 or info.st_size > 1024:
            raise ValueError('unsafe operator secret file')
        value = os.read(descriptor, 1025).decode('ascii').strip()
        if not value or len(value) > 1024:
            raise ValueError('empty or oversized operator secret')
        return value
    finally:
        os.close(descriptor)


def create_runtime(environ=None, *, secret_dir=Path('/run/secrets'), expected_uid=10001,
                   connector=connect, session_builder=build_live_session):
    environ = os.environ if environ is None else environ
    if environ.get('TRADEBOT_ENVIRONMENT') != 'preprod' or \
            environ.get('TRADEBOT_DATA_MODE') != 'pp_live':
        raise ValueError('operator runtime requires preprod live identity')
    origin = environ.get('TRADEBOT_ORIGIN_ID', '')
    if not origin.startswith('pp-live-') or len(origin) <= len('pp-live-') or len(origin) > 128:
        raise ValueError('invalid PP live origin')
    if environ.get('TRADEBOT_DATABASE_DSN') or environ.get('TRADEBOT_OPERATOR_TOKEN'):
        raise ValueError('operator credentials must come from mounted secret files')
    if environ.get('TRADEBOT_DATABASE_DSN_FILE') != '/run/secrets/lifecycle_dsn' or \
            environ.get('TRADEBOT_OPERATOR_TOKEN_FILE') != '/run/secrets/operator_token':
        raise ValueError('unreviewed operator credential path')
    for name in ('TRADEBOT_COLLECTOR_ENABLED', 'ENABLE_OPENAI_ANALYST',
                 'ENABLE_SUPABASE_SYNC', 'ENABLE_LOCAL_RETENTION'):
        if environ.get(name, 'false').lower() not in ('false', '0', 'off'):
            raise ValueError('operator runtime requires disabled feature flags')
    anchor = cycle_anchor(environ)
    diagnostic_anchor = boundary_anchor(environ) if origin in BOUNDARY_ORIGINS else None
    elapsed_cycle = elapsed_cycle_seconds(environ)
    if anchor is not None and environ.get('TRADEBOT_PP_LIVE_CONTROL') != 'true':
        raise ValueError('two-leg rehearsal requires explicit live control')
    root = Path(secret_dir)
    dsn = _secret(root, 'lifecycle_dsn', expected_uid=expected_uid)
    token = _secret(root, 'operator_token', expected_uid=expected_uid)
    if not 32 <= len(token) <= 256:
        raise ValueError('invalid operator token length')

    def factory():
        return connector(dsn, environment='preprod')

    with factory() as connection:
        login = connection.execute('SELECT session_user AS login').fetchone()['login']
        if login != 'tradebot_lifecycle':
            raise ValueError('operator runtime requires the lifecycle role')
        validate_schema(connection, 'preprod')
    repository = LifecycleRepository(factory)
    live_control = environ.get('TRADEBOT_PP_LIVE_CONTROL', 'false')
    if live_control not in ('true', 'false'):
        raise ValueError('invalid PP live control flag')
    session = None
    status_repository = repository
    if live_control == 'true':
        if environ.get('TRADEBOT_APP_DSN_FILE') != '/run/secrets/app_dsn':
            raise ValueError('PP live app credential path required')
        app_dsn = _secret(root, 'app_dsn', expected_uid=expected_uid)
        with connector(app_dsn, environment='preprod') as connection:
            if connection.execute('SELECT session_user AS login').fetchone()['login'] != 'tradebot_app':
                raise ValueError('PP live writer requires the app role')
            validate_schema(connection, 'preprod')
        fence_live_startup(repository, origin)
        status_repository = _owner_reader(app_dsn, connector)
        session = session_builder(repository, origin, app_dsn,
                    **({'rehearsal_anchor': anchor} if anchor else {}),
                    **({'diagnostic_anchor': diagnostic_anchor} if diagnostic_anchor else {}),
                    **({'rehearsal_window_seconds': elapsed_cycle} if elapsed_cycle is not None else {}))
    required_seconds = boundary_lease_seconds(origin) if diagnostic_anchor else lease_cap(anchor) if anchor else None
    from .feed_controls import ORIGIN as WATCH_ORIGIN
    feed_store = Store(Settings(environment='preprod', data_mode='pp_live', origin_id=origin, dsn=app_dsn)
                       ) if session and origin == WATCH_ORIGIN else None
    return create_operator_app(repository, origin_id=origin, token=token, feed_store=feed_store,
                               session=session, status_repository=status_repository,
                               max_session_seconds=required_seconds or lease_cap(anchor),
                               required_session_seconds=required_seconds)


def main():
    import uvicorn
    app = create_runtime()
    uvicorn.run(app, host='0.0.0.0', port=8001, access_log=False)


if __name__ == '__main__':
    main()
