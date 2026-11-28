"""Narrow private operator routes; the publicly readable API exposes state only."""
import asyncio

from fastapi import Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from . import feed_controls as controls

BROWSER_ORIGIN='http://127.0.0.1:18433'


class Preference(BaseModel):
    model_config=ConfigDict(extra='forbid')
    enabled: StrictBool
    revision: StrictInt=Field(ge=0,le=2**53-1)


def install(app, store, token, require_operator):
    controls.check_store(store)
    app.add_middleware(CORSMiddleware,allow_origins=[BROWSER_ORIGIN],allow_methods=['GET','PUT'],
                       allow_headers=['Authorization','Content-Type'],allow_credentials=False)

    def check_grant(authorization,origin):
        if origin is not None and origin!=BROWSER_ORIGIN:
            raise HTTPException(403,'unexpected dashboard origin')
        if not controls.verify(token,authorization):
            raise HTTPException(401,'source controls locked or expired')

    @app.post('/collector/feeds/session')
    async def issue_grant(response:Response,authorization:str|None=Header(default=None),origin:str|None=Header(default=None)):
        if origin is not None:
            raise HTTPException(403,'operator channel required')
        require_operator(authorization)
        response.headers['Cache-Control']='no-store'
        return controls.mint(token)

    @app.get('/collector/feeds')
    async def state(response:Response,authorization:str|None=Header(default=None),origin:str|None=Header(default=None)):
        check_grant(authorization,origin)
        response.headers['Cache-Control']='no-store'
        try:
            return {'origin':controls.ORIGIN,'feeds':await asyncio.to_thread(controls.read_controls,store)}
        except Exception:
            raise HTTPException(503,'feed preferences unavailable') from None

    @app.put('/collector/feeds/{feed}')
    async def set_preference(feed:str, preference:Preference,authorization:str|None=Header(default=None),origin:str|None=Header(default=None)):
        check_grant(authorization,origin)
        if feed not in controls.FEEDS:
            raise HTTPException(404,'unknown feed')
        try:
            result=await asyncio.to_thread(controls.set_desired,store,feed,preference.enabled,preference.revision)
        except controls.RevisionConflict:
            raise HTTPException(409,'feed preference changed; refresh and retry') from None
        except Exception:
            raise HTTPException(503,'feed preference could not be confirmed') from None
        return {'origin':controls.ORIGIN,'feed':feed,**result}
