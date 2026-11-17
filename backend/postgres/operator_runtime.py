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
from .store import Store


def build_live_session(repository, origin, app_dsn):
    """Prepare a PP-only, explicitly started source task with a finite lease."""
    store = Store(Settings(environment='preprod', data_mode='pp_live',
                           origin_id=origin, dsn=app_dsn))
    store.verify()

    async def run(stop, max_seconds):
        generation = await asyncio.to_thread(repository.bootstrap, origin)
        generation_id = str(generation['generation_id'])
        session_id = str(uuid.uuid4())
        enabled = False

        def owner_check():
            return (repository.owns_collector(origin, session_id) if enabled
                    else not repository.collector_state(origin)['collector_enabled'])

        def enable():
            nonlocal enabled
            result = repository.enable_collector(origin, session_id=session_id,
                         expected_generation_id=generation_id, max_seconds=max_seconds)
            enabled = True
            return result

        async with httpx.AsyncClient(timeout=4, follow_redirects=False) as client:
            return await run_session(store, client, stop, owner_check=owner_check,
                         enable_collector=enable,
                         disable_collector=lambda: repository.disable_collector(origin),
                         max_seconds=max_seconds)

    return OperatorSession(run, lambda: repository.disable_collector(origin))


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
    if live_control == 'true':
        if environ.get('TRADEBOT_APP_DSN_FILE') != '/run/secrets/app_dsn':
            raise ValueError('PP live app credential path required')
        app_dsn = _secret(root, 'app_dsn', expected_uid=expected_uid)
        with connector(app_dsn, environment='preprod') as connection:
            if connection.execute('SELECT session_user AS login').fetchone()['login'] != 'tradebot_app':
                raise ValueError('PP live writer requires the app role')
            validate_schema(connection, 'preprod')
        session = session_builder(repository, origin, app_dsn)
    return create_operator_app(repository, origin_id=origin, token=token,
                               session=session)


def main():
    import uvicorn
    app = create_runtime()
    uvicorn.run(app, host='0.0.0.0', port=8001, access_log=False)


if __name__ == '__main__':
    main()
