"""Independent feed lifecycles inside one durably fenced Benchmark collector."""

import asyncio
import logging

from .live_diagnostics import LiveDiagnostic

LOG = logging.getLogger(__name__)


async def run_watch_sources(store, stop, runners, desired=None, effective=None, *, interval=2):
    if desired is None:
        from .feed_controls import desired_feeds

        desired = desired_feeds
    if effective is None:
        from .feed_controls import record_effective

        effective = record_effective
    # A source may have multiple independent readers, e.g. Coinbase trades and
    # candles. Source pause drains each reader without cancelling other sources.
    active = {}
    held = set()
    while_paused = set()
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
                    try:
                        task.result()
                    except Exception as error:
                        code = error.code if isinstance(error, LiveDiagnostic) else type(error).__name__
                        LOG.warning('pp_watch_feed_held source=%s reader=%s reason=%s', source, name, code)
                        held.add(name)
                        await asyncio.to_thread(effective, store, name, 'held')
                    else:
                        if not signal.is_set():
                            LOG.warning('pp_watch_feed_held source=%s reader=%s reason=ended', source, name)
                            held.add(name)
                            await asyncio.to_thread(effective, store, name, 'held')
                if not enabled[source]:
                    if name not in while_paused:
                        await asyncio.to_thread(effective, store, name, 'paused')
                    while_paused.add(name)
                    continue
                if name in while_paused:
                    held.discard(name)
                    while_paused.discard(name)
                if name not in held:
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
