"""Bounded, default-off PP collection coordinator with independent feed tasks.

No runtime entry point is provided. A reviewed host controller must establish
and continuously prove sole-collector ownership, durably enable the PP writer,
start this coordinator without automatic restart, and durably disable it on exit.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from .live_ingest import (_live_store, coinbase_candle_cycle, coinbase_session,
                          polymarket_cycle)


class CollectorHold(RuntimeError):
    pass


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
                      clock=lambda: datetime.now(timezone.utc)):
    """Run three independent read-only feed tasks while ownership stays valid.

    A failed source or ownership check aborts the whole session. No retry can
    hide stale data. `stop` is only a process signal; the host controller must
    persist OFF in PostgreSQL before considering a stop complete.
    """
    _live_store(store)
    if not callable(owner_check) or not callable(disable_collector) or not 0 < max_seconds <= 1800:
        raise ValueError('bounded session, ownership checker and durable stop required')
    if not 1 <= market_interval <= 10 or not 60 <= candle_interval <= 300:
        raise ValueError('source cadence outside qualified bounds')

    def assert_fence():
        if owner_check() is not True or store.collector_enabled() is not True:
            raise CollectorHold('PP collector ownership or durable writer flag lost')

    async def watch_fence():
        while not stop.is_set():
            await asyncio.wait_for(asyncio.to_thread(assert_fence), timeout=2)
            await _pause_or_stop(stop, 1)

    async def coinbase_stream():
        await coinbase(store, stop)
        if not stop.is_set():
            raise CollectorHold('Coinbase stream ended without a stop')

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
        tasks = [asyncio.create_task(task()) for task in
                 (watch_fence, coinbase_stream, market_loop, candle_loop)]
        stop_task = asyncio.create_task(stop.wait())
        done, _ = await asyncio.wait([*tasks, stop_task], timeout=max_seconds,
                                     return_when=asyncio.FIRST_COMPLETED)
        if not done:
            raise CollectorHold('bounded PP collector session reached deadline')
        for task in tasks:
            if task in done:
                error = task.exception()
                if error:
                    raise error
                if not stop.is_set():
                    raise CollectorHold('collector task ended unexpectedly')
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
            raise CollectorHold('durable PP collector stop unproven') from None
