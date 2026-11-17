"""Dedicated PP operator API runtime; not part of the dashboard container.

This module does not enable collection. The reviewed host profile must mount
only the lifecycle DSN and operator token into a separate loopback-bound
service before it is reachable. No environment credential values are accepted.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat

from .connection import connect
from .lifecycle import LifecycleRepository
from .migrate import validate_schema
from .operator_api import create_operator_app


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
                   connector=connect):
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
    return create_operator_app(LifecycleRepository(factory), origin_id=origin, token=token)


def main():
    import uvicorn
    app = create_runtime()
    uvicorn.run(app, host='0.0.0.0', port=8001, access_log=False)


if __name__ == '__main__':
    main()
