"""Read-only dashboard API. Hot requests/SSE read RAM; hydration is independent."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import time

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse

from .config import Settings
from .domain import utcnow
from .live_state import LiveState
from .store import Store


def health(snapshot):
    required = set(snapshot['missing_data'])-{'trade_flow','btc_order_book'}
    collector_ok = snapshot['data_mode'] != 'pp_live' or snapshot['collector']['enabled'] is True
    return 'ok' if not required and snapshot['storage_status']=='ok' and collector_ok else 'degraded'


def history_context():
    return {'status':'unsupported','unsupported':['evaluation','news','linked_historical_cases'],
            'evaluation':{'distinct_confirmed_markets_by_checkpoint':{},'distinct_confirmed_markets':0},
            'news':[],'news_last_seen':None,'outcomes':[],'evidence':None}


async def event_stream(state, disconnected=None, interval=0.25):
    """Initial full snapshot on every reconnect; timed updates propagate staleness."""
    while disconnected is None or not await disconnected():
        first = state.first_quote_signal
        snapshot = state.snapshot()
        yield f"id: {snapshot['revision']}\ndata: {json.dumps(snapshot,separators=(',',':'),allow_nan=False)}\n\n"
        try:
            await asyncio.wait_for(first.wait(), interval)
        except TimeoutError:
            pass


def create_app(settings=None, store=None, state=None, *, history=None,
               structured_history=None, refresh=True):
    settings = settings or Settings.from_env()
    store = store or Store(settings)
    state = state or LiveState(settings)
    if structured_history is not None:
        from .cold_structured_queries import RegisteredStructuredHistory
        if (not isinstance(structured_history, RegisteredStructuredHistory)
                or settings.environment != 'preprod' or settings.data_mode != 'pp_live'
                or settings.origin_id != structured_history.origin_id):
            raise ValueError('structured history API requires trusted PP query registry')
    if history is None:
        from .runtime_history import configured_history
        history = configured_history(settings, store, os.environ)

    from .market_history import MarketHistory, Window
    from .history import HistoryError
    from .archive_codec import ArchiveIntegrityError, ArchiveLimit
    from .runtime_history import RuntimeHistory
    from .prediction_history import PredictionHistory, configured_archive
    market_history = MarketHistory(store, history.raw_factory if isinstance(history, RuntimeHistory) else None)
    prediction_history = PredictionHistory(store, configured_archive(settings, os.environ))

    async def discover():
        while True:
            try:
                market = await asyncio.to_thread(store.active_market)
                state.discover(market)
                state.storage_status('ok')
            except Exception:
                # Keep last identity for diagnosis; snapshot clock independently expires it.
                state.storage_status('unavailable')
            await asyncio.sleep(.5)

    async def hydrate():
        while True:
            snapshot = state.snapshot()
            market = snapshot.get('market')
            if market and market['active']:
                try:
                    data = await asyncio.to_thread(store.hydrate,market['id'],with_latest_saved=True)
                    state.publish(market['id'],*data)
                except Exception:
                    state.storage_status('unavailable')
            else:
                try:
                    price = await asyncio.to_thread(store.current_price)
                    state.publish_price(price)
                except Exception:
                    state.storage_status('unavailable')
            await asyncio.sleep(.5)

    async def monitor_collector():
        while True:
            try:
                enabled = await asyncio.to_thread(store.collector_enabled)
                state.collector_status(enabled if type(enabled) is bool else None)
            except Exception:
                state.collector_status(None)
            await asyncio.sleep(1)

    async def monitor_archived_quotes():
        while True:
            counters = state.snapshot()['quote_counts']
            if counters:
                started = counters['started_at']
                try:
                    count = await asyncio.to_thread(store.archived_quote_count, started)
                except Exception:
                    count = None
                state.archive_count(started, count)
            await asyncio.sleep(15)

    @asynccontextmanager
    async def lifespan(app):
        # Verification is mandatory, including in tests; only explicit migrate CLI mutates schema.
        await asyncio.to_thread(store.verify)
        tasks = []
        if refresh:
            tasks = [asyncio.create_task(discover()),asyncio.create_task(hydrate())]
            if settings.data_mode == 'pp_live':
                tasks.append(asyncio.create_task(monitor_collector()))
                if settings.origin_id == MONITORED_ORIGIN:
                    async def monitor_window():
                        while True:
                            await telemetry.snapshot()
                            await asyncio.sleep(15)
                    tasks.append(asyncio.create_task(monitor_window()))
                from . import quote_display
                if quote_display.enabled(settings):
                    tasks.append(asyncio.create_task(quote_display.receive(state)))
                    tasks.append(asyncio.create_task(monitor_archived_quotes()))
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            if structured_history is not None:
                await asyncio.to_thread(structured_history.close)

    app = FastAPI(title='BTC Intelligence PostgreSQL API',version='0.2.0',lifespan=lifespan)
    app.state.live_state = state

    @app.middleware('http')
    async def timing(request,call_next):
        started = time.perf_counter()
        response = await call_next(request)
        response.headers['X-Process-Time-Ms'] = f'{(time.perf_counter()-started)*1000:.3f}'
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/')
    async def root():
        return {'service':'btc-intelligence-api','version':app.version,'docs':'/docs',**settings.public()}

    @app.get('/dashboard',include_in_schema=False)
    async def dashboard():
        return FileResponse(Path(__file__).with_name('dashboard.html'),media_type='text/html')

    @app.get('/dashboard/plan',response_class=PlainTextResponse)
    async def plan():
        return await asyncio.to_thread((Path(__file__).resolve().parents[2]/'docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md').read_text)

    @app.get('/state/current')
    @app.get('/api/state',include_in_schema=False)
    async def current():
        return state.snapshot()

    @app.get('/forecast/current')
    async def forecast():
        snapshot = state.snapshot()
        return {key:snapshot[key] for key in ('market','forecast','saved_prediction','live_estimate','live_estimate_status','missing_data','updated_at','environment','data_mode')}

    @app.get('/models/current')
    async def models():
        snapshot = state.snapshot()
        return {key:snapshot[key] for key in ('market','models','updated_at','environment','data_mode','unsupported')}

    from .benchmark_telemetry import BenchmarkTelemetry, ORIGIN as MONITORED_ORIGIN
    if settings.data_mode == 'pp_live' and settings.origin_id == MONITORED_ORIGIN:
        telemetry = BenchmarkTelemetry(store, state)
        app.get('/system/telemetry')(telemetry.snapshot)

    @app.get('/health')
    async def status():
        snapshot = state.snapshot()
        return {**settings.public(),'status':health(snapshot),'feeds':snapshot['feeds'],
                'collector':snapshot['collector'],
                'missing_data':snapshot['missing_data'],'storage_status':snapshot['storage_status'],
                'updated_at':snapshot['updated_at'],'cloud':{'enabled':False,'status':'disabled','datasets':[]}}

    async def history_window(reader, market_id, start, end, as_of, cursor, limit, *options):
        try:
            window = Window.parse(market_id, start, end, as_of)
            return await reader.read_async(window, cursor, limit, *options)
        except HistoryError as error:
            status = 429 if error.code == 'history_busy' else 422
            raise HTTPException(status, {'code':error.code}) from None
        except ArchiveLimit:
            raise HTTPException(503, {'code':'history_budget_exceeded'}) from None
        except ArchiveIntegrityError:
            raise HTTPException(503, {'code':'history_integrity_failed'}) from None
        except Exception:
            raise HTTPException(503, {'code':'history_unavailable'}) from None

    @app.get('/history/market-events')
    async def market_events(market_id: str=Query(min_length=1,max_length=128),
                            start: str=Query(max_length=64), end: str=Query(max_length=64),
                            as_of: str=Query(max_length=64), cursor: str|None=Query(default=None,max_length=2048),
                            limit: int=Query(default=100,ge=1,le=500)):
        return await history_window(market_history,market_id,start,end,as_of,cursor,limit)

    @app.get('/history/market-predictions')
    async def market_predictions(market_id: str=Query(min_length=1,max_length=128),
                            start: str=Query(max_length=64), end: str=Query(max_length=64),
                            as_of: str=Query(max_length=64), cursor: str|None=Query(default=None,max_length=2048),
                            limit: int=Query(default=100,ge=1,le=500), include_archive: bool=False):
        return await history_window(prediction_history,market_id,start,end,as_of,cursor,limit,include_archive)

    @app.get('/history/predictions')
    async def predictions(limit: int=Query(default=100,ge=1,le=500)):
        try:
            items = await asyncio.to_thread(store.predictions,limit)
        except Exception:
            raise HTTPException(503,'Local prediction history unavailable') from None
        return {'items':items,'limit':limit,'tier':'local','origin_id':settings.origin_id}

    # No environment variable, public manifest, writer credential or default
    # source enables this route. A reviewed server composition must inject it.
    if structured_history is not None:
        @app.get('/history/structured/{query_id}')
        async def structured(query_id: str, after_id: int | None=Query(default=None,ge=1),
                             scope_sha256: str | None=Query(default=None,min_length=64,max_length=64)):
            from .archive_codec import ArchiveError
            try:
                pending = structured_history.submit_query(
                    query_id, after_id=after_id, scope_sha256=scope_sha256)
                # HTTP cancellation must not release admission or cancel queued
                # cleanup while the independently bounded source is still active.
                return await asyncio.shield(asyncio.wrap_future(pending))
            except ArchiveError as error:
                code = error.code
                status = 404 if code == 'cold_history_unknown_query' else (
                    429 if code == 'cold_history_busy' else 503)
                raise HTTPException(status, {'status':'failed','code':code}) from None
            except Exception:
                raise HTTPException(503, {'status':'failed','code':'cold_history_unavailable'}) from None

    @app.get('/history/coinbase-chart')
    async def chart():
        try:
            return await asyncio.to_thread(store.chart)
        except Exception:
            raise HTTPException(503,'Local chart history unavailable') from None

    @app.get('/history/context')
    async def context():
        return history_context()

    @app.get('/history/archive/{generation_id}')
    async def archive(generation_id: str,limit: int=Query(default=100,ge=1,le=500),after_event_id: str|None=None):
        if history is None:
            raise HTTPException(503,'Archive retrieval disabled')
        try:
            return await asyncio.to_thread(history.read_generation,generation_id,dataset='raw.events',limit=limit,after_event_id=after_event_id)
        except Exception as error:
            raise HTTPException(503,{'status':'failed','code':getattr(error,'code','history_unavailable')}) from None

    @app.get('/cloud/status')
    async def cloud():
        return {'enabled':False,'status':'disabled','datasets':[],'lifecycle':{'status':'unavailable'}}

    @app.get('/system/history')
    async def system_history(limit: int=Query(default=288,ge=1,le=288)):
        return {'status':'unsupported','items':[],'limit':limit}

    @app.get('/system/status')
    async def system_status():
        snapshot = state.snapshot()
        return {**settings.public(),'api':'responding','live_engine_status':health(snapshot),
                'collector':snapshot['collector'],
                'host':{'status':'unavailable','captured_at':None},'services':{},'services_stale':True,
                'database':{'engine':'postgresql','status':snapshot['storage_status']},
                'feeds':snapshot['feeds'],'openai_enabled':False,'retention_enabled':False,
                'cloud':{'enabled':False,'status':'disabled','datasets':[],'lifecycle':{'status':'unavailable'}}}

    @app.get('/events')
    async def events(request: Request):
        return StreamingResponse(event_stream(state,request.is_disconnected),media_type='text/event-stream',
                                 headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

    return app


app = create_app()
