"""Default-off bridge from official read-only feeds to acknowledged PP writes.

The caller owns the sole-collector fence and durable enable control. This module
has no process entry point and cannot enable collection by itself.
"""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from contextlib import aclosing
from datetime import datetime, timezone
import time

from .feed_writer import feed_writer
from .boundary_trace import boundary_trace
from .coinbase_timing import ACTIVE_TIMING, configured_timing
from .contract import source_timestamp
from .live_sources import (coinbase_once, discover_polymarket_15m,
                           fetch_coinbase_closed_candles, fetch_polymarket_bbo)
from .live_diagnostics import LiveDiagnostic, diagnose


COINBASE_RECONNECT_DELAYS = (1, 2, 4, 8, 16, 30)
COINBASE_RECONNECT_MAX_STARTS = 3
COINBASE_RECONNECT_WINDOW_SECONDS = 60
COINBASE_RETRYABLE = frozenset({
    'coinbase_stream.ws_closed_ok', 'coinbase_stream.ws_closed_error',
    'coinbase_stream.timeout', 'coinbase_stream.transport',
})


# Only failed read-only GETs can be retried by the regular discovery cycle.
# Storage, ownership, authentication and decoded data errors stay fatal.
POLYMARKET_DISCOVERY_UNAVAILABLE = frozenset({
    'polymarket_discovery.http_404', 'polymarket_discovery.http_429',
    'polymarket_discovery.http_5xx', 'polymarket_discovery.timeout',
    'polymarket_discovery.transport',
})
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
                           pause=_pause_or_stop, clock=time.monotonic, timing=None,
                           wall_clock=lambda: datetime.now(timezone.utc)):
    """Persist serially; rate-limit transient source reconnects within the lease.

    A new subscription may replay a source event. Store's durable identity and
    content-hash check handles that replay; this loop never synthesizes ticks.
    """
    _live_store(store)
    timing = timing if timing is not None else configured_timing()
    token = ACTIVE_TIMING.set(timing)
    try:
        async with feed_writer(store):
            return await _coinbase_session(store, stop, source=source, pause=pause,
                                           clock=clock, timing=timing, wall_clock=wall_clock)
    finally:
        try:
            if timing is not None:
                timing.flush('session_exit')
        finally:
            ACTIVE_TIMING.reset(token)


def _fresh_progress(event, acknowledgement, wall_clock, previous_epoch):
    # Only a newly durable, genuinely current source event resets backoff.
    # Replays, stale backlog and future timestamps never manufacture recovery.
    if not isinstance(acknowledgement, dict) or acknowledgement.get('duplicate') is not False:
        return None
    try:
        epoch = source_timestamp(event['source_time'])[1]
        age = source_timestamp(wall_clock().isoformat())[1] - epoch
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    if 0 <= age <= 30 and (previous_epoch is None or epoch > previous_epoch):
        return epoch
    return None


async def _buffered_ticks(source, stop, timing):
    """Read ahead up to 32 ticks. A full queue backpressures the socket without eviction."""
    queue = asyncio.Queue(maxsize=32)
    stopped = asyncio.create_task(stop.wait())

    async def read_ticks():
        async with aclosing(source(stop)) as stream:
            while not stop.is_set():
                incoming = asyncio.ensure_future(anext(stream))
                try:
                    done, _ = await asyncio.wait((incoming, stopped), return_when=asyncio.FIRST_COMPLETED)
                    if incoming not in done:
                        return
                    try:
                        event = incoming.result()
                    except StopAsyncIteration:
                        return
                    if stop.is_set():
                        return
                    queued_at = timing.clock() if timing is not None else None
                    sample = dict(timing.last_event or {}) if timing is not None else None
                    if sample is not None:
                        sample['persistence_queue_depth'] = queue.qsize()
                    await queue.put((event, queued_at, sample))
                finally:
                    if not incoming.done():
                        incoming.cancel()
                    # A stop can race successful completion, including end of stream.
                    await asyncio.gather(incoming, return_exceptions=True)

    async def read():
        try:
            await read_ticks()
        except Exception as error:
            # Surface transport failures in order, after already-received ticks.
            await queue.put(error)
        else:
            await queue.put(None)

    reader = asyncio.create_task(read())
    try:
        while True:
            item = await queue.get()
            if item is None:
                break
            if isinstance(item, Exception):
                raise item
            yield item
    finally:
        reader.cancel()
        stopped.cancel()
        await asyncio.gather(reader, stopped, return_exceptions=True)


async def _persist_tick(store, event, timing, queued_at, sample):
    if timing is None:
        return await _step('coinbase_write', asyncio.to_thread(store.ingest, event))
    submitted = timing.clock()
    worker = {}

    def persist():
        worker['started'] = timing.clock()
        worker['started_at'] = timing.wall().isoformat()
        try:
            return store.ingest(event)
        finally:
            worker['completed'] = timing.clock()
            worker['completed_at'] = timing.wall().isoformat()

    outcome = 'raised'
    try:
        acknowledgement = await _step('coinbase_write', asyncio.to_thread(persist))
        outcome = 'returned'
        return acknowledgement
    finally:
        if worker.get('completed') is None:
            outcome = 'inflight_at_cancel'
        timing.saved(submitted=submitted, worker=worker, outcome=outcome,
                     sample=sample, queued_at=queued_at)


async def _coinbase_session(store, stop, *, source, pause, clock, timing, wall_clock):
    reconnect_starts = deque()
    reconnects = 0
    failures_without_fresh_progress = 0
    previous_progress_epoch = None
    while not stop.is_set():
        try:
            async with aclosing(_buffered_ticks(source, stop, timing)) as ticks:
                async for event, queued_at, sample in ticks:
                    acknowledgement = await _persist_tick(store, event, timing, queued_at, sample)
                    progress = _fresh_progress(event, acknowledgement, wall_clock, previous_progress_epoch)
                    if progress is not None:
                        previous_progress_epoch = progress
                        failures_without_fresh_progress = 0
            return
        except Exception as error:
            diagnostic = error if isinstance(error, LiveDiagnostic) else diagnose('coinbase_stream', error)
            if diagnostic.code not in COINBASE_RETRYABLE or stop.is_set():
                raise diagnostic from None
            delay = COINBASE_RECONNECT_DELAYS[min(failures_without_fresh_progress,
                                                  len(COINBASE_RECONNECT_DELAYS)-1)]
            failures_without_fresh_progress += 1
            waited = 0
            while not stop.is_set():
                now = clock()
                while reconnect_starts and now - reconnect_starts[0] >= COINBASE_RECONNECT_WINDOW_SECONDS:
                    reconnect_starts.popleft()
                rate_wait = (max(0, reconnect_starts[0] + COINBASE_RECONNECT_WINDOW_SECONDS - now)
                             if len(reconnect_starts) >= COINBASE_RECONNECT_MAX_STARTS else 0)
                wait = max(delay - waited, rate_wait)
                if wait <= 0:
                    break
                if rate_wait > 0 and timing is not None:
                    timing.cooldown(diagnostic.code, reconnects + 1, wait)
                before = clock()
                await pause(stop, wait)
                waited += max(0, clock() - before)
            if stop.is_set():
                return
            # Count actual reconnect starts, not failure timestamps or a
            # cancelled pause. The supervisor's finite deadline and database
            # lease continue to bound this same session; no ON is issued here.
            reconnect_starts.append(clock())
            reconnects += 1
            if timing is not None:
                timing.reconnect(diagnostic.code, reconnects, waited)



async def coinbase_candle_cycle(store, client, stop: asyncio.Event, *, now=None,
                                fetch=fetch_coinbase_closed_candles):
    """Persist only returned closed candles; scheduling must be low frequency."""
    _live_store(store)
    if stop.is_set():
        return 0
    events = await _step('coinbase_candles', fetch(client, now or datetime.now(timezone.utc)))
    acknowledged = 0
    revisions = 0
    for event in events:
        if stop.is_set():
            break
        try:
            await _step('coinbase_candle_write', asyncio.to_thread(store.ingest, event))
        except LiveDiagnostic as error:
            if error.code != 'coinbase_candle_write.candle_revision_conflict':
                raise
            revisions += 1
            continue
        acknowledged += 1
    if revisions:
        logging.getLogger(__name__).warning('pp_candle_revisions_rejected count=%d', revisions)
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
    boundary_trace('discovery_start')
    try:
        market = await _step('polymarket_discovery',
                             discover(client, now or datetime.now(timezone.utc)))
    except LiveDiagnostic as error:
        boundary_trace('discovery_error', reason=error.code)
        if error.code not in POLYMARKET_DISCOVERY_UNAVAILABLE:
            raise
        logging.getLogger(__name__).warning('pp_discovery_unavailable reason=%s', error.code)
        return None
    if market is None:
        boundary_trace('discovery_empty')
        return None
    boundary_trace('market_identified', market)
    if stop.is_set():
        return None
    await _step('polymarket_market_write', asyncio.to_thread(store.ingest, market))
    if stop.is_set():
        return None
    try:
        quote = await _step('polymarket_bbo', fetch(client, market))
    except LiveDiagnostic as error:
        boundary_trace('quote_unavailable', market, reason=error.code)
        if error.code not in POLYMARKET_QUOTE_UNAVAILABLE:
            raise
        logging.getLogger(__name__).warning('pp_quote_unavailable reason=%s', error.code)
        return None
    if quote is None:
        boundary_trace('quote_unavailable', market, reason='matching_book_empty')
        logging.getLogger(__name__).warning('pp_quote_unavailable reason=matching_book_empty')
        return None
    if stop.is_set():
        return None
    if quote.get('market_id') != market['market_id']:
        raise LiveDiagnostic('polymarket_bbo', 'identity_mismatch')
    boundary_trace('bbo_received', market, quote=quote)
    ack = await _step('polymarket_bbo_write', asyncio.to_thread(store.ingest, quote))
    boundary_trace('commit_ack', market, quote=quote,
                   duplicate=ack.get('duplicate') if isinstance(ack, dict) else None)
    return market['market_id']
