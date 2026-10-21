"""Run the local BTC Intelligence FastAPI service."""
import os
from pathlib import Path

import uvicorn


def load_local_env():
    path = Path(__file__).resolve().parents[2] / '.env'
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        name, value = line.split('=', 1)
        name, value = name.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        os.environ.setdefault(name, value)


def enabled(value):
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def main():
    load_local_env()
    host = os.getenv('FASTAPI_HOST', '127.0.0.1')
    port = int(os.getenv('FASTAPI_PORT', '8000'))
    reload_enabled = enabled(os.getenv('FASTAPI_RELOAD', 'false'))
    uvicorn.run(
        'api:app',
        host=host,
        port=port,
        reload=reload_enabled,
        app_dir=str(Path(__file__).resolve().parent),
    )


if __name__ == '__main__':
    main()
