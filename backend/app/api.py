"""FastAPI service layer over the in-memory BTC intelligence state."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import sqlite3
import time

from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse

from live_state import LiveState
from streaming import DEFAULT_MAX_STORAGE_MB, run as run_collectors


def _collector_status(task):
    if task is None:
        return {'enabled': False, 'running': False, 'error': None}
    if not task.done():
        return {'enabled': True, 'running': True, 'error': None}
    if task.cancelled():
        return {'enabled': True, 'running': False, 'error': 'cancelled'}
    try:
        error = task.exception()
    except asyncio.CancelledError:
        error = None
    return {
        'enabled': True,
        'running': False,
        'error': type(error).__name__ if error else None,
    }


def _read_prediction_history(db_path, limit):
    if db_path != ':memory:' and not Path(db_path).exists():
        return []
    db = sqlite3.connect(db_path)
    try:
        db.execute('PRAGMA query_only=ON')
        columns = {row[1] for row in db.execute('PRAGMA table_info(predictions)')}
        required = {
            'id', 'market_id', 'model_version', 'as_of', 'created_at',
            'seconds_remaining', 'probability_up', 'probability_down', 'abstain_reason'
        }
        if not required.issubset(columns):
            return []
        rows = db.execute('''SELECT id,market_id,model_version,as_of,created_at,
          seconds_remaining,probability_up,probability_down,abstain_reason
          FROM predictions ORDER BY id DESC LIMIT ?''', (limit,)).fetchall()
        names = ('id','market_id','model_version','as_of','created_at',
                 'seconds_remaining','probability_up','probability_down','abstain_reason')
        return [dict(zip(names, row)) for row in rows]
    finally:
        db.close()


def create_app(live_state=None, db_path=None, start_collectors=True):
    state = live_state or LiveState()
    resolved_db_path = db_path or os.getenv('SQLITE_DB_PATH', 'data/btc_intelligence.db')

    @asynccontextmanager
    async def lifespan(app):
        task = None
        if start_collectors:
            interval = max(15, int(os.getenv('REST_INTERVAL_SECONDS', '30')))
            max_storage = max(
                1, int(os.getenv('MAX_LOCAL_STORAGE_MB', str(DEFAULT_MAX_STORAGE_MB))))
            task = asyncio.create_task(
                run_collectors(
                    resolved_db_path,
                    seconds=0,
                    interval=interval,
                    max_storage_mb=max_storage,
                    live_state=state,
                    install_signal_handlers=False),
                name='btc-intelligence-collectors')
        app.state.collector_task = task
        try:
            yield
        finally:
            if task and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    app = FastAPI(
        title='BTC Intelligence API',
        version='0.1.0',
        description='Local read-only API over the BTC 15-minute Live State Engine.',
        lifespan=lifespan,
    )
    app.state.live_state = state
    app.state.db_path = resolved_db_path
    app.state.start_collectors = start_collectors
    app.state.collector_task = None

    @app.middleware('http')
    async def response_time(request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        response.headers['X-Process-Time-Ms'] = f'{(time.perf_counter()-started)*1000:.3f}'
        return response

    @app.get('/')
    async def root():
        return {
            'service': 'btc-intelligence-api',
            'version': app.version,
            'docs': '/docs',
        }

    @app.get('/state/current')
    async def current_state():
        return state.snapshot()

    @app.get('/forecast/current')
    async def current_forecast():
        snapshot = state.snapshot()
        return {
            'market': snapshot.get('market'),
            'forecast': snapshot.get('forecast'),
            'missing_data': snapshot.get('missing_data', []),
            'updated_at': snapshot.get('updated_at'),
        }

    @app.get('/models/current')
    async def current_models():
        snapshot = state.snapshot()
        return {
            'market': snapshot.get('market'),
            'models': snapshot.get('models', {}),
            'updated_at': snapshot.get('updated_at'),
        }

    @app.get('/health')
    async def health():
        snapshot = state.snapshot()
        collector = _collector_status(app.state.collector_task)
        required_missing = [
            item for item in snapshot.get('missing_data', [])
            if item not in ('trade_flow', 'btc_order_book')
        ]
        status = 'ok' if not required_missing and collector.get('error') is None else 'degraded'
        return {
            'status': status,
            'collector': collector,
            'feeds': snapshot.get('feeds', {}),
            'missing_data': snapshot.get('missing_data', []),
            'updated_at': snapshot.get('updated_at'),
        }

    @app.get('/history/predictions')
    async def prediction_history(limit: int = Query(default=100, ge=1, le=500)):
        return {
            'items': await asyncio.to_thread(
                _read_prediction_history, resolved_db_path, limit),
            'limit': limit,
        }

    @app.get('/events')
    async def events():
        async def stream():
            last_token = object()
            while True:
                snapshot = state.snapshot()
                token = snapshot.get('updated_at')
                if token != last_token:
                    yield f"data: {json.dumps(snapshot, separators=(',', ':'))}\n\n"
                    last_token = token
                await asyncio.sleep(0.25)

        return StreamingResponse(
            stream(),
            media_type='text/event-stream',
            headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
        )

    return app


app = create_app()
