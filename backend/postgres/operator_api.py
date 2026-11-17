"""Unstarted, private PP operator surface; never mounted in the dashboard API.

The host controller must bind and authenticate this service separately. It
cannot enable collection, change the data mode, or touch production.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import hmac

from fastapi import FastAPI, Header, HTTPException, Query

from .operator_session import SessionBusy, SessionStopUnproven


def create_operator_app(repository, *, origin_id: str, token: str, session=None):
    if not origin_id.startswith('pp-live-') or len(origin_id) <= len('pp-live-'):
        raise ValueError('operator origin must be a distinct PP live origin')
    if not isinstance(token, str) or len(token) < 32 or len(token) > 256 or not token.isascii():
        raise ValueError('operator token must be bounded ASCII secret')
    secret = ('Bearer ' + token).encode('ascii')
    @asynccontextmanager
    async def lifespan(_app):
        try:
            yield
        finally:
            if session is not None:
                await session.stop()

    app = FastAPI(title='Private PP collector control', docs_url=None,
                  redoc_url=None, openapi_url=None, lifespan=lifespan)

    def require_operator(authorization: str | None):
        candidate = authorization.encode('utf-8') if authorization is not None else b''
        if len(candidate) != len(secret) or not hmac.compare_digest(candidate, secret):
            raise HTTPException(401, 'operator authentication required',
                                headers={'WWW-Authenticate': 'Bearer'})

    @app.get('/collector/status')
    async def status(authorization: str | None = Header(default=None)):
        require_operator(authorization)
        try:
            durable = await asyncio.to_thread(repository.collector_state, origin_id)
        except Exception:
            raise HTTPException(503, 'collector state unavailable') from None
        return {'environment': 'preprod', 'origin_id': origin_id,
                'collector_enabled': bool(durable['collector_enabled']),
                'epoch': durable['epoch'], 'generation_id': durable['generation_id'],
                'updated_at': durable['updated_at'],
                'initialized': durable['initialized'],
                'lease_expires_at': durable.get('collector_lease_expires_at'),
                'lease_expired': bool(durable.get('stored_enabled') and not durable['collector_enabled']),
                'process_running': session.state()['process_running'] if session else None,
                'live_fence_qualified': False}

    if session is not None:
        @app.post('/collector/on', status_code=202)
        async def on(max_seconds: int = Query(default=900, ge=1, le=1800),
                     authorization: str | None = Header(default=None)):
            require_operator(authorization)
            try:
                result = await session.start(max_seconds=max_seconds)
            except SessionBusy:
                raise HTTPException(409, 'PP collector already running') from None
            except SessionStopUnproven:
                raise HTTPException(503, 'PP collector requires explicit OFF') from None
            # The task may still be enabling its lease. Report acceptance only;
            # status must independently read the durable writer state.
            return {'environment': 'preprod', 'origin_id': origin_id,
                    'accepted': True, 'process_running': result['process_running']}

    @app.post('/collector/off')
    async def off(authorization: str | None = Header(default=None)):
        require_operator(authorization)
        try:
            if session is not None:
                await session.stop()
            durable = await asyncio.to_thread(repository.disable_collector, origin_id)
        except Exception:
            raise HTTPException(503, 'collector stop unavailable') from None
        return {'environment': 'preprod', 'origin_id': origin_id,
                **durable, 'process_running': session.state()['process_running'] if session else None,
                'live_fence_qualified': False}

    return app
