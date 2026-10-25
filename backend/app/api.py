"""FastAPI service layer over the in-memory BTC intelligence state."""
import asyncio
from contextlib import asynccontextmanager, closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import time

from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse, FileResponse, PlainTextResponse

from cloud_lifecycle import read_lifecycle_status
from live_state import LiveState
from streaming import DEFAULT_MAX_STORAGE_MB, run as run_collectors
from system_monitoring import read_history, host_status, read_ensemble, elapsed


def _readonly(db_path):
    return sqlite3.connect(Path(db_path).resolve().as_uri() + '?mode=ro', uri=True, timeout=0.2)


def _saved_dashboard(db_path, chart=False):
    # Reuse the existing bounded history/context queries, never start the legacy server/relay.
    from dashboard import open_readonly, status, chart_data
    try:
        with closing(open_readonly(db_path)) as db:
            db.execute('PRAGMA busy_timeout=200')
            deadline = time.monotonic() + 1
            db.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
            if chart:
                return chart_data(db)
            saved = status(db)
            return {key: saved[key] for key in (
                'evaluation', 'news', 'news_last_seen', 'outcomes', 'evidence')}
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError):
        return {'status': 'unavailable', 'points': [], 'market': None} if chart else {'status': 'unavailable'}


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


def _live_health(snapshot, collector):
    required_missing = [item for item in snapshot.get('missing_data', [])
                        if item not in ('trade_flow', 'btc_order_book')]
    return 'ok' if not required_missing and collector.get('error') is None else 'degraded'


def _env_enabled(name, default="false"):
    return str(os.getenv(name, default)).strip().lower() in ("1", "true", "yes", "on")


def _read_cloud_status(db_path):
    try:
        status = _read_cloud_datasets(db_path)
    except (OSError, sqlite3.Error):
        status = {'enabled': _env_enabled('ENABLE_SUPABASE_SYNC'), 'status': 'unavailable', 'datasets': []}
    try:
        status["lifecycle"] = read_lifecycle_status(db_path)
    except Exception as error:
        status["lifecycle"] = {"status": "unavailable", "error": type(error).__name__}
    # Error detail and free-form checkpoint keys can include private diagnostic data.
    if 'last_error_detail' in status.get('lifecycle', {}):
        status['lifecycle']['last_error_detail'] = None
    for dataset in status.get('datasets', []):
        dataset['detail'] = None
        dataset['last_source_key'] = None
    return status


def _read_cloud_datasets(db_path):
    enabled = _env_enabled("ENABLE_SUPABASE_SYNC")
    if db_path != ":memory:" and not Path(db_path).exists():
        return {"enabled": enabled, "status": "no_local_database", "datasets": []}
    db = _readonly(db_path)
    try:
        db.execute("PRAGMA query_only=ON")
        exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='cloud_sync_state'"
        ).fetchone()
        if not exists:
            return {
                "enabled": enabled,
                "status": "not_started" if enabled else "disabled",
                "datasets": [],
            }
        rows = db.execute(
            """SELECT dataset,last_source_id,last_source_time,last_source_key,
                      rows_synced,status,detail,updated_at
               FROM cloud_sync_state ORDER BY dataset"""
        ).fetchall()
        names = (
            "dataset", "last_source_id", "last_source_time", "last_source_key",
            "rows_synced", "status", "detail", "updated_at",
        )
        datasets = [dict(zip(names, row)) for row in rows]
        unhealthy = [row for row in datasets if row["status"] not in ("ok", "verified")]
        status = "disabled" if not enabled else (
            "degraded" if unhealthy else ("ok" if datasets else "not_started")
        )
        return {"enabled": enabled, "status": status, "datasets": datasets}
    finally:
        db.close()


def _read_prediction_history(db_path, limit):
    if db_path != ':memory:' and not Path(db_path).exists():
        return []
    db = _readonly(db_path)
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


def create_app(live_state=None, db_path=None, start_collectors=True, telemetry_path=None):
    state = live_state or LiveState()
    resolved_db_path = db_path or os.getenv('SQLITE_DB_PATH', 'data/btc_intelligence.db')

    resolved_telemetry = telemetry_path or os.getenv('SYSTEM_TELEMETRY_PATH') or str(Path(resolved_db_path).parent / 'cloud-soak.jsonl')

    def live_snapshot():
        snapshot = state.snapshot()
        snapshot['generated_at'] = datetime.now(timezone.utc).isoformat()
        estimate = state.baseline_forecast()
        if estimate:
            estimate.update({'market_id': (snapshot.get('market') or {}).get('id'),
                             'as_of': (snapshot.get('coinbase') or {}).get('source_time'),
                             'snapshot_as_of': (snapshot.get('feature_snapshot') or {}).get('as_of')})
        snapshot['live_estimate'] = estimate
        return snapshot

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

    @app.get('/dashboard', include_in_schema=False)
    async def dashboard_page():
        return FileResponse(Path(__file__).with_name('dashboard.html'), media_type='text/html', headers={'Cache-Control': 'no-store'})

    @app.get('/dashboard/plan', response_class=PlainTextResponse)
    async def dashboard_plan():
        path = Path(__file__).resolve().parents[2] / 'docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md'
        return await asyncio.to_thread(path.read_text)

    @app.get('/history/context')
    async def historical_context():
        return await asyncio.to_thread(_saved_dashboard, resolved_db_path)

    @app.get('/history/coinbase-chart')
    async def historical_chart():
        return await asyncio.to_thread(_saved_dashboard, resolved_db_path, True)

    @app.get('/system/history')
    async def system_history(limit: int = Query(default=288, ge=1, le=288)):
        return await asyncio.to_thread(read_history, resolved_telemetry, limit)

    @app.get('/system/status')
    async def system_status():
        history = await asyncio.to_thread(read_history, resolved_telemetry, 1)
        result = await asyncio.to_thread(host_status, resolved_db_path, history)
        snapshot = state.snapshot()
        feeds = {}
        for name in ('coinbase', 'polymarket'):
            feed = snapshot.get('feeds', {}).get(name + '_stream', {})
            data = snapshot.get(name) or {}
            age_seconds = elapsed(data.get('received_at') or feed.get('last_data_at'))
            reported_status = feed.get('status', 'unavailable')
            effective_status = reported_status
            if reported_status in ('live', 'running'):
                effective_status = 'unavailable' if age_seconds is None else 'stale' if age_seconds > 90 else reported_status
            feeds[name] = {'status': effective_status, 'reported_status': reported_status,
                           'age_seconds': age_seconds,
                           'reconnects_cumulative': feed.get('reconnects')}
        collector = _collector_status(app.state.collector_task)
        result.update({'api': 'responding', 'live_engine_status': _live_health(snapshot, collector),
                       'collector': collector, 'feeds': feeds,
                       'openai_enabled': _env_enabled('ENABLE_OPENAI_ANALYST'),
                       'retention_enabled': _env_enabled('ENABLE_LOCAL_RETENTION'),
                       'cloud': await asyncio.to_thread(_read_cloud_status, resolved_db_path)})
        return result

    @app.get('/state/current')
    async def current_state():
        return live_snapshot()

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
        models = snapshot.get('models', {})
        ensemble = await asyncio.to_thread(read_ensemble, resolved_db_path)
        if ensemble:
            ensemble['current_market'] = ensemble['market_id'] == (snapshot.get('market') or {}).get('id')
            ensemble['age_seconds'] = elapsed(ensemble['as_of'])
            models['ensemble_v1'] = ensemble
        return {
            'market': snapshot.get('market'),
            'models': models,
            'updated_at': snapshot.get('updated_at'),
        }

    @app.get('/health')
    async def health():
        snapshot = state.snapshot()
        collector = _collector_status(app.state.collector_task)
        status = _live_health(snapshot, collector)
        cloud = await asyncio.to_thread(_read_cloud_status, resolved_db_path)
        return {
            'status': status,
            'collector': collector,
            'feeds': snapshot.get('feeds', {}),
            'missing_data': snapshot.get('missing_data', []),
            'cloud': cloud,
            'updated_at': snapshot.get('updated_at'),
        }

    @app.get('/cloud/status')
    async def cloud_status():
        return await asyncio.to_thread(_read_cloud_status, resolved_db_path)

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
                snapshot = live_snapshot()
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
