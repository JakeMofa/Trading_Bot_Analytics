"""Bounded, default-off PP collection coordinator with independent feed tasks.

No runtime entry point is provided. A reviewed host controller must establish
and continuously prove sole-collector ownership, durably enable the PP writer,
start this coordinator without automatic restart, and durably disable it on exit.
"""
from __future__ import annotations

import asyncio

from .rehearsal_profile import lease_cap, CYCLE_ORIGINS
from datetime import datetime, timezone

from .live_ingest import (_live_store, coinbase_candle_cycle, coinbase_session,
                          polymarket_cycle)
from .live_diagnostics import CollectorHold, LiveDiagnostic, diagnose


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

    Source-only Coinbase transport retries are bounded in coinbase_session;
    exhausted retries and all other failures abort the session. Retry does not
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

    def assert_fence():
        if owner_check() is not True or store.collector_enabled() is not True:
            raise LiveDiagnostic('ownership', 'lease_lost')

    async def watch_fence():
        while not stop.is_set():
            try:
                await asyncio.wait_for(asyncio.to_thread(assert_fence), timeout=2)
            except Exception:
                raise LiveDiagnostic('ownership', 'lease_lost') from None
            await _pause_or_stop(stop, 1)

    async def coinbase_stream():
        await coinbase(store, stop)
        if not stop.is_set():
            raise LiveDiagnostic('coinbase_stream', 'ended')

    async def market_loop():
        while not stop.is_set():
            await market(store, client, stop, now=clock())
            await _pause_or_stop(stop, market_interval)

    async def candle_loop():
        while not stop.is_set():
            await candles(store, client, stop, now=clock())
            await _pause_or_stop(stop, candle_interval)

    tasks = []
    stop_task = None
    try:
        await asyncio.wait_for(asyncio.to_thread(assert_fence), timeout=2)  # No source opens first.
        named = {'ownership': watch_fence, 'coinbase_stream': coinbase_stream,
                 'polymarket_loop': market_loop, 'coinbase_candle_loop': candle_loop}
        tasks = [asyncio.create_task(task()) for task in named.values()]
        names = dict(zip(tasks, named))
        stop_task = asyncio.create_task(stop.wait())
        done, _ = await asyncio.wait([*tasks, stop_task], timeout=max_seconds,
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
                    raise diagnose(names[task], error) from None
                if not stop.is_set():
                    raise LiveDiagnostic(names[task], 'ended')
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
