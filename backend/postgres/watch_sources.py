"""Independent feed lifecycles inside one durably fenced Benchmark collector."""

import asyncio
import logging

from websockets.exceptions import InvalidHandshake

from .live_diagnostics import LiveDiagnostic

LOG = logging.getLogger(__name__)


def retryable_source(error):
    if isinstance(error, ExceptionGroup):
        return all(retryable_source(item) for item in error.exceptions)
    if isinstance(error, LiveDiagnostic):
        stage, category = error.code.split('.')
        return stage in {
            'polymarket_discovery',
            'polymarket_bbo',
            'coinbase_candles',
            'coinbase_stream',
        } and category not in {'write_rejected', 'identity_mismatch', 'unexpected'}
    return isinstance(error, InvalidHandshake)


async def run_watch_sources(store, stop, runners, desired=None, effective=None, *, interval=2, retry_min=2):
    if desired is None:
        from .feed_controls import desired_feeds

        desired = desired_feeds
    if effective is None:
        from .feed_controls import record_effective

        def effective(source_store, component, state):
            return record_effective(source_store, component, state, session_id=source_store.producer_session_id)
    # A source may have multiple independent readers, e.g. Coinbase trades and
    # candles. Source pause drains each reader without cancelling other sources.
    active = {}
    held = set()
    while_paused = set()
    retry_at = {}
    failures = {}
    clock = asyncio.get_running_loop().time
    try:
        while not stop.is_set():
            enabled = await asyncio.to_thread(desired, store)
            if set(enabled) != {'polymarket', 'coinbase', 'robinhood'} or any(
                type(x) is not bool for x in enabled.values()
            ):
                raise ValueError('invalid Benchmark feed controls')
            for name, (source, runner) in runners.items():
                prior = active.get(name)
                if prior:
                    signal, task = prior
                    if not enabled[source]:
                        signal.set()
                    if not task.done():
                        continue
                    del active[name]
                    error = task.exception()
                    if not signal.is_set():
                        reason = (
                            error.code
                            if isinstance(error, LiveDiagnostic)
                            else type(error).__name__
                            if error
                            else 'ended'
                        )
                        if error is None or retryable_source(error):
                            delay = min(60, retry_min * 2 ** min(failures.get(name, 0), 6))
                            failures[name] = failures.get(name, 0) + 1
                            retry_at[name] = clock() + delay
                            LOG.warning(
                                'pp_watch_feed_retry source=%s reader=%s reason=%s delay=%s',
                                source,
                                name,
                                reason,
                                delay,
                            )
                            await asyncio.to_thread(effective, store, name, 'retrying')
                        else:
                            LOG.warning(
                                'pp_watch_feed_held source=%s reader=%s reason=%s', source, name, reason
                            )
                            held.add(name)
                            await asyncio.to_thread(effective, store, name, 'held')
                if not enabled[source]:
                    if name not in while_paused:
                        await asyncio.to_thread(effective, store, name, 'paused')
                    while_paused.add(name)
                    continue
                if name in while_paused:
                    held.discard(name)
                    retry_at.pop(name, None)
                    failures.pop(name, None)
                    while_paused.discard(name)
                if name not in held and clock() >= retry_at.get(name, 0):
                    signal = asyncio.Event()
                    active[name] = (signal, asyncio.create_task(runner(signal), name='benchmark-' + name))
                    await asyncio.to_thread(effective, store, name, 'running')
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except TimeoutError:
                pass
    finally:
        for signal, _ in active.values():
            signal.set()
        tasks = [task for _, task in active.values()]
        if tasks:
            try:
                await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=10)
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
