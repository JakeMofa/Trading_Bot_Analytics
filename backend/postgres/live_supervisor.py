"""Bounded, default-off PP collection coordinator with independent feed tasks.

No runtime entry point is provided. A reviewed host controller must establish
and continuously prove sole-collector ownership, durably enable the PP writer,
start this coordinator without automatic restart, and durably disable it on exit.
"""
from __future__ import annotations

import asyncio
import logging

from psycopg import Error as PostgresError

from .rehearsal_profile import lease_cap, CYCLE_ORIGINS
from datetime import datetime, timezone

from .cloud_origin_binding import DISPLAY_ORIGIN
from .rehearsal_profile import WATCH_LEASE_SECONDS
from . import benchmark_telemetry as metrics
from .ownership_probe import OwnershipProbe, submit_ownership
from .live_ingest import (_live_store, coinbase_candle_cycle, coinbase_session,
                          polymarket_cycle)
from .live_diagnostics import (CollectorHold, LiveDiagnostic, OwnershipConnectionLimit,
                               READ_CAPACITY_BACKOFF, connection_capacity, diagnose)


async def _pause_or_stop(stop: asyncio.Event, seconds: float):
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


async def run_bounded(store, client, stop: asyncio.Event, *, owner_check, disable_collector,
                      max_seconds: float, market_interval: float = 5,
                      candle_interval: float = 60,
                      coinbase=coinbase_session, market=polymarket_cycle,
                      candles=coinbase_candle_cycle,
                      clock=lambda: datetime.now(timezone.utc), rehearsal_anchor=None):
    """Run three independent read-only feed tasks while ownership stays valid.

    `owner_check` must prove the current session ID and unexpired durable
    writer lease together. A failed or inconclusive check ends the session.
    Source-only Coinbase stream retries are rate-limited in coinbase_session;
    candle transport/429/5xx failures wait for the normal candle cadence. Other
    failures abort, and this session deadline bounds all retries. Retry does not
    publish data, so source-age health still becomes stale. `stop` is only a
    process signal; the host controller must
    persist OFF in PostgreSQL before considering a stop complete.
    """
    _live_store(store)
    if rehearsal_anchor is not None and store.settings.origin_id not in CYCLE_ORIGINS:
        raise ValueError('two-leg rehearsal requires exact PP origin')
    if not callable(owner_check) or not callable(disable_collector) or not 0 < max_seconds <= lease_cap(rehearsal_anchor):
        raise ValueError('bounded session, ownership checker and durable stop required')
    if not 1 <= market_interval <= 10 or not 60 <= candle_interval <= 300:
        raise ValueError('source cadence outside qualified bounds')

    async def read_ownership(probe):
        for delay in READ_CAPACITY_BACKOFF:
            try:
                return await submit_ownership(owner_check, probe)
            except OwnershipConnectionLimit:
                if delay is None:
                    raise
                probe.mark('retry_wait')
                await asyncio.sleep(delay)

    async def assert_fence():
        # The operator callback checks the session ID, durable enable flag,
        # and lease expiry together in one database read.
        probe = OwnershipProbe()
        loop = asyncio.get_running_loop()
        deadline_at = loop.time() + 2
        deadline = asyncio.timeout_at(deadline_at)
        try:
            async with deadline:
                owned = await read_ownership(probe)
                # A stalled loop can deliver a ready result before processing
                # an overdue timeout callback. Late proof is never authority.
                if loop.time() >= deadline_at:
                    raise TimeoutError
        except TimeoutError:
            probe.report('async_deadline' if deadline.expired() or loop.time() >= deadline_at
                         else 'worker_timeout')
            raise LiveDiagnostic('ownership', 'timeout') from None
        except OwnershipConnectionLimit:
            probe.report('capacity')
            raise LiveDiagnostic('ownership', 'database_connection_limit') from None
        except PostgresError as error:
            probe.report('sql_cancelled' if error.sqlstate == '57014' else 'database_error')
            category = 'timeout' if error.sqlstate == '57014' else 'database_unavailable'
            raise LiveDiagnostic('ownership', category) from None
        except Exception as error:
            probe.report('error')
            raise diagnose('ownership', error) from None
        except asyncio.CancelledError:
            probe.report('cancelled')
            raise
        if owned is not True:
            probe.report('false_owner')
            raise LiveDiagnostic('ownership', 'lease_lost')
        probe.report('success')

    async def watch_fence():
        with metrics.monitor_session(store.settings.origin_id, getattr(store, 'producer_session_id', None)) as pulse:
            while not stop.is_set():
                await assert_fence()
                pulse()
                await _pause_or_stop(stop, 1)

    async def coinbase_stream(stop=stop):
        await coinbase(store, stop)
        if not stop.is_set():
            raise LiveDiagnostic('coinbase_stream', 'ended')

    async def market_loop():
        from . import quote_display, quote_session
        if quote_display.enabled(store.settings):
            await quote_session.run(store, client, stop, market_interval, clock)
            return
        while not stop.is_set():
            await market(store, client, stop, now=clock())
            await _pause_or_stop(stop, market_interval)

    async def candle_loop(stop=stop):
        unavailable_cycles = 0
        while not stop.is_set():
            try:
                if unavailable_cycles:
                    metrics.issue('coinbase_candles', 'retry')
                await candles(store, client, stop, now=clock())
            except LiveDiagnostic as error:
                # _step separates fetch from durable write: only these provider
                # failures may degrade the optional reference feed. Never turn a
                # write timeout, schema/auth error, or arbitrary exception into a
                # retry. No row or freshness acknowledgement is synthesized.
                if error.code not in {
                    'coinbase_candles.timeout', 'coinbase_candles.transport',
                    'coinbase_candles.http_429', 'coinbase_candles.http_5xx',
                }:
                    raise
                unavailable_cycles += 1
                logging.getLogger(__name__).warning(
                    'pp_candles_unavailable reason=%s consecutive_cycles=%d',
                    error.code, unavailable_cycles)
            else:
                if unavailable_cycles:
                    logging.getLogger(__name__).warning(
                        'pp_candles_cycle_recovered unavailable_cycles=%d',
                        unavailable_cycles)
                    unavailable_cycles = 0
            await _pause_or_stop(stop, candle_interval)

    tasks = []
    stop_task = None
    try:
        await assert_fence()  # No source opens first.
        named = {'ownership': watch_fence, 'coinbase_stream': coinbase_stream,
                 'polymarket_loop': market_loop, 'coinbase_candle_loop': candle_loop}
        renewable = store.settings.origin_id == DISPLAY_ORIGIN and max_seconds == WATCH_LEASE_SECONDS
        if renewable:
            from . import quote_session
            from .watch_sources import run_watch_sources
            readers = {'polymarket': ('polymarket', lambda event: quote_session.run(
                           store, client, event, market_interval, clock, include_robinhood=False)),
                       'coinbase_stream': ('coinbase', coinbase_stream),
                       'coinbase_candles': ('coinbase', candle_loop),
                       'robinhood': ('robinhood', lambda event: quote_session.run_robinhood(store,event))}
            named = {'ownership': watch_fence, 'selected_feeds': lambda: run_watch_sources(store,stop,readers)}
        tasks = [asyncio.create_task(task()) for task in named.values()]
        names = dict(zip(tasks, named))
        stop_task = asyncio.create_task(stop.wait())
        # The dedicated host supervisor renews a short fenced lease. A missing
        # heartbeat makes assert_fence stop all feeds even across market changes.
        done, _ = await asyncio.wait([*tasks, stop_task], timeout=None if renewable else max_seconds,
                                     return_when=asyncio.FIRST_COMPLETED)
        if not done:
            raise LiveDiagnostic('session', 'deadline_reached')
        for task in tasks:
            if task in done:
                if task.cancelled():
                    if not stop.is_set():
                        raise LiveDiagnostic(names[task], 'ended')
                    continue
                error = task.exception()
                if error:
                    if isinstance(error, LiveDiagnostic):
                        raise error from None
                    if names[task] == 'selected_feeds' and isinstance(error, PostgresError):
                        # Only the typed SQLSTATE or an exact native startup
                        # failure identifies a capacity refusal.
                        category = ('database_connection_limit' if connection_capacity(error)
                                    else 'timeout' if error.sqlstate == '57014'
                                    else 'database_unavailable')
                        raise LiveDiagnostic('selected_feeds', category) from None
                    raise diagnose(names[task], error) from None
                if not stop.is_set():
                    raise LiveDiagnostic(names[task], 'ended')
        # An orderly stop lets already-received quotes finish under the same
        # lease. A failed fence or writer still takes the immediate OFF path.
        from . import quote_display
        if stop.is_set():
            # The native reader owns a bounded persistence queue. Alternate
            # source adapters retain the original cancel-on-stop contract.
            draining = {'selected_feeds'} if renewable else {'coinbase_stream'} if coinbase is coinbase_session else set()
            if quote_display.enabled(store.settings):
                draining.add('polymarket_loop')
            await asyncio.wait_for(asyncio.gather(*(task for task in tasks if names[task] in draining)),
                                   timeout=10)
        return 'stopped'
    finally:
        pending = [*tasks, *([stop_task] if stop_task else [])]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        try:
            result = await asyncio.wait_for(asyncio.to_thread(disable_collector), timeout=5)
            if result is not False and not (isinstance(result, dict) and result.get('collector_enabled') is False):
                raise ValueError('durable OFF acknowledgement missing')
        except Exception:
            raise LiveDiagnostic('session', 'durable_off_unproven') from None
