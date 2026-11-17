"""Default-off bridge from official read-only feeds to acknowledged PP writes.

The caller owns the sole-collector fence and durable enable control. This module
has no process entry point and cannot enable collection by itself.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from .live_sources import coinbase_once, discover_polymarket_15m, fetch_polymarket_bbo


def _live_store(store):
    settings = store.settings
    if settings.environment != 'preprod' or settings.data_mode != 'pp_live' or not settings.origin_id.startswith('pp-live-') or len(settings.origin_id) <= len('pp-live-'):
        raise ValueError('live ingestion requires a distinct PP live origin')


async def coinbase_session(store, stop: asyncio.Event, *, source=coinbase_once):
    """Persist each ticker before reading the next; propagate holds and failures."""
    _live_store(store)
    async for event in source(stop):
        if stop.is_set():
            break
        await asyncio.to_thread(store.ingest, event)


async def polymarket_cycle(store, client, stop: asyncio.Event, *, now=None,
                           discover=discover_polymarket_15m,
                           fetch=fetch_polymarket_bbo):
    """Discover independently, then persist the matching market and BBO.

    A discovery failure or missing current market never reuses an old identity.
    Both writes remain subject to Store's durable collector flag and identity
    checks. A failure after the market write is visible as a missing quote.
    """
    _live_store(store)
    if stop.is_set():
        return None
    market = await discover(client, now or datetime.now(timezone.utc))
    if market is None or stop.is_set():
        return None
    await asyncio.to_thread(store.ingest, market)
    if stop.is_set():
        return None
    quote = await fetch(client, market)
    if stop.is_set():
        return None
    if quote.get('market_id') != market['market_id']:
        raise ValueError('quote market identity changed before persistence')
    await asyncio.to_thread(store.ingest, quote)
    return market['market_id']
