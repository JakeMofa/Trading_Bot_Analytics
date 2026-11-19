"""Default-off PP collector session orchestration.

The host controller supplies a qualified cross-VM ownership check and a
durable enable operation. This module has no runtime entry point or ON API.
"""
from __future__ import annotations

import asyncio

from .rehearsal_profile import lease_cap

from .live_supervisor import CollectorHold, run_bounded


async def run_session(store, client, stop: asyncio.Event, *, owner_check,
                      enable_collector, disable_collector, max_seconds: float,
                      supervisor=run_bounded, rehearsal_anchor=None):
    """Fail closed at every activation boundary and leave the writer OFF."""
    if not callable(owner_check) or not callable(enable_collector) or \
            not callable(disable_collector) or not 0 < max_seconds <= lease_cap(rehearsal_anchor):
        raise ValueError('bounded session and durable ownership controls required')

    try:
        if stop.is_set() or await asyncio.to_thread(owner_check) is not True:
            raise CollectorHold('PP collector ownership unavailable')
        # Do not abandon an enable thread on cancellation: it could commit ON
        # after the finally block commits OFF. This runs only in the separate
        # operator process; the database callback must have its own deadline.
        enabled = enable_collector()
        if not isinstance(enabled, dict) or enabled.get('collector_enabled') is not True:
            raise CollectorHold('durable PP collector enable unproven')
        if stop.is_set() or await asyncio.to_thread(owner_check) is not True:
            raise CollectorHold('PP collector ownership lost during activation')
        return await supervisor(store, client, stop, owner_check=owner_check,
                                disable_collector=disable_collector,
                                max_seconds=max_seconds,
                                **({'rehearsal_anchor': rehearsal_anchor} if rehearsal_anchor else {}))
    finally:
        # Also covers an ambiguous enable result or failure before the
        # supervisor starts. OFF is idempotent and must be acknowledged.
        result = disable_collector()
        if not isinstance(result, dict) or result.get('collector_enabled') is not False:
            raise CollectorHold('durable PP collector stop unproven')
