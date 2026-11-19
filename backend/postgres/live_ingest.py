"""Default-off bridge from official read-only feeds to acknowledged PP writes.

The caller owns the sole-collector fence and durable enable control. This module
has no process entry point and cannot enable collection by itself.
"""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
import time

from .coinbase_timing import ACTIVE_TIMING, configured_timing
from .live_sources import (coinbase_once, discover_polymarket_15m,
                           fetch_coinbase_closed_candles, fetch_polymarket_bbo)
from .live_diagnostics import LiveDiagnostic, diagnose


COINBASE_RECONNECT_DELAYS = (1, 2, 4)
COINBASE_RECONNECT_WINDOW_SECONDS = 60
COINBASE_RECONNECT_MAX_TOTAL = 12
COINBASE_RETRYABLE = frozenset({
    'coinbase_stream.ws_closed_ok', 'coinbase_stream.ws_closed_error',
    'coinbase_stream.timeout', 'coinbase_stream.transport',
})


# Only a failed quote GET can be retried by the regular discovery cycle.
# Storage, ownership, authentication and decoded data errors stay fatal.
POLYMARKET_QUOTE_UNAVAILABLE = frozenset({
    'polymarket_bbo.http_404', 'polymarket_bbo.http_429', 'polymarket_bbo.http_5xx',
    'polymarket_bbo.timeout', 'polymarket_bbo.transport',
})


async def _pause_or_stop(stop: asyncio.Event, delay: float):
    try:
        await asyncio.wait_for(stop.wait(), timeout=delay)
    except asyncio.TimeoutError:
        pass


async def _step(operation, awaitable):
    try:
        return await awaitable
    except LiveDiagnostic:
        raise
    except Exception as error:
        raise diagnose(operation, error) from None


def _live_store(store):
    settings = store.settings
    if settings.environment != 'preprod' or settings.data_mode != 'pp_live' or not settings.origin_id.startswith('pp-live-') or len(settings.origin_id) <= len('pp-live-'):
        raise ValueError('live ingestion requires a distinct PP live origin')


async def coinbase_session(store, stop: asyncio.Event, *, source=coinbase_once,
                           pause=_pause_or_stop, clock=time.monotonic, timing=None):
    """Persist serially; retry only bounded transient source disconnects.

    A new subscription may replay a source event. Store's durable identity and
    content-hash check handles that replay; this loop never synthesizes ticks.
    """
    _live_store(store)
    timing = timing if timing is not None else configured_timing()
    token = ACTIVE_TIMING.set(timing)
    try:
        return await _coinbase_session(store, stop, source=source, pause=pause,
                                       clock=clock, timing=timing)
    finally:
        try:
            if timing is not None:
                timing.flush('session_exit')
        finally:
            ACTIVE_TIMING.reset(token)


async def _coinbase_session(store, stop, *, source, pause, clock, timing):
    failures = deque()
    reconnects = 0
    while not stop.is_set():
        try:
            async for event in source(stop):
                if stop.is_set():
                    break
                if timing is None:
                    await _step('coinbase_write', asyncio.to_thread(store.ingest, event))
                else:
                    submitted = timing.clock()
                    worker = {}
                    outcome = 'raised'
                    def persist():
                        worker['started'] = timing.clock()
                        worker['started_at'] = timing.wall().isoformat()
                        try:
                            return store.ingest(event)
                        finally:
                            worker['completed'] = timing.clock()
                            worker['completed_at'] = timing.wall().isoformat()
                    try:
                        await _step('coinbase_write', asyncio.to_thread(persist))
                        outcome = 'returned'
                    finally:
                        if worker.get('completed') is None:
                            outcome = 'inflight_at_cancel'
                        timing.saved(submitted=submitted, worker=worker, outcome=outcome)
            return
        except Exception as error:
            diagnostic = error if isinstance(error, LiveDiagnostic) else diagnose('coinbase_stream', error)
            if diagnostic.code not in COINBASE_RETRYABLE or stop.is_set():
                raise diagnostic from None
            now = clock()
            while failures and now - failures[0] >= COINBASE_RECONNECT_WINDOW_SECONDS:
                failures.popleft()
            if (len(failures) >= len(COINBASE_RECONNECT_DELAYS)
                    or reconnects >= COINBASE_RECONNECT_MAX_TOTAL):
                raise diagnostic from None
            delay = COINBASE_RECONNECT_DELAYS[len(failures)]
            failures.append(now)
            reconnects += 1
            if timing is not None:
                timing.reconnect(diagnostic.code, reconnects, delay)
            await pause(stop, delay)


async def coinbase_candle_cycle(store, client, stop: asyncio.Event, *, now=None,
                                fetch=fetch_coinbase_closed_candles):
    """Persist only returned closed candles; scheduling must be low frequency."""
    _live_store(store)
    if stop.is_set():
        return 0
    events = await _step('coinbase_candles', fetch(client, now or datetime.now(timezone.utc)))
    acknowledged = 0
    for event in events:
        if stop.is_set():
            break
        await _step('coinbase_candle_write', asyncio.to_thread(store.ingest, event))
        acknowledged += 1
    return acknowledged


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
    market = await _step('polymarket_discovery',
                         discover(client, now or datetime.now(timezone.utc)))
    if market is None or stop.is_set():
        return None
    await _step('polymarket_market_write', asyncio.to_thread(store.ingest, market))
    if stop.is_set():
        return None
    try:
        quote = await _step('polymarket_bbo', fetch(client, market))
    except LiveDiagnostic as error:
        if error.code not in POLYMARKET_QUOTE_UNAVAILABLE:
            raise
        logging.getLogger(__name__).warning('pp_quote_unavailable reason=%s', error.code)
        return None
    if quote is None:
        logging.getLogger(__name__).warning('pp_quote_unavailable reason=matching_book_empty')
        return None
    if stop.is_set():
        return None
    if quote.get('market_id') != market['market_id']:
        raise LiveDiagnostic('polymarket_bbo', 'identity_mismatch')
    await _step('polymarket_bbo_write', asyncio.to_thread(store.ingest, quote))
    return market['market_id']
