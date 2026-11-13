"""Read-only dashboard API. Hot requests/SSE read RAM; hydration is independent."""
import asyncio
from contextlib import asynccontextmanager
import json
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
    return 'ok' if not required and snapshot['storage_status']=='ok' else 'degraded'


def history_context():
    return {'status':'unsupported','unsupported':['evaluation','news','linked_historical_cases'],
            'evaluation':{'distinct_confirmed_markets_by_checkpoint':{},'distinct_confirmed_markets':0},
            'news':[],'news_last_seen':None,'outcomes':[],'evidence':None}


async def event_stream(state, disconnected=None, interval=0.25):
    """Initial full snapshot on every reconnect; timed updates propagate staleness."""
    while disconnected is None or not await disconnected():
        snapshot = state.snapshot()
        yield f"id: {snapshot['revision']}\ndata: {json.dumps(snapshot,separators=(',',':'),allow_nan=False)}\n\n"
        await asyncio.sleep(interval)


def create_app(settings=None, store=None, state=None, *, history=None, refresh=True):
    settings = settings or Settings.from_env()
    store = store or Store(settings)
    state = state or LiveState(settings)

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
                    data = await asyncio.to_thread(store.hydrate,market['id'])
                    state.publish(market['id'],*data)
                except Exception:
                    state.storage_status('unavailable')
            await asyncio.sleep(.5)

    @asynccontextmanager
    async def lifespan(app):
        # Verification is mandatory, including in tests; only explicit migrate CLI mutates schema.
        await asyncio.to_thread(store.verify)
        tasks = []
        if refresh:
            tasks = [asyncio.create_task(discover()),asyncio.create_task(hydrate())]
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)

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
        return {key:snapshot[key] for key in ('market','forecast','missing_data','updated_at','environment','data_mode')}

    @app.get('/models/current')
    async def models():
        snapshot = state.snapshot()
        return {key:snapshot[key] for key in ('market','models','updated_at','environment','data_mode','unsupported')}

    @app.get('/health')
    async def status():
        snapshot = state.snapshot()
        return {**settings.public(),'status':health(snapshot),'feeds':snapshot['feeds'],
                'missing_data':snapshot['missing_data'],'storage_status':snapshot['storage_status'],
                'updated_at':snapshot['updated_at'],'cloud':{'enabled':False,'status':'disabled','datasets':[]}}

    @app.get('/history/predictions')
    async def predictions(limit: int=Query(default=100,ge=1,le=500)):
        try:
            items = await asyncio.to_thread(store.predictions,limit)
        except Exception:
            raise HTTPException(503,'Local prediction history unavailable') from None
        return {'items':items,'limit':limit,'tier':'local','origin_id':settings.origin_id}

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
