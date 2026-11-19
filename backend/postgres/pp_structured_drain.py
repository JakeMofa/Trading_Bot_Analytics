"""Default-OFF, finite PP structured outbox drain; no runtime entrypoint.

This schedules only the existing fresh-readback workers. It cannot upload raw
evidence, retire a partition, or run from a deployed service. A separate
reviewed host control and measured cloud throughput are required before use.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import time

from .active_structured import ActiveStructuredWorker, SealedStructuredWorker, PP_STRUCTURED_ORIGIN
from .archive_codec import ArchiveLimit, ArchiveLimits
from .lifecycle import LifecycleHold


@dataclass(frozen=True)
class DrainLimits:
    max_cycles: int = 12
    max_rows: int = 300
    max_cloud_operations: int = 24
    max_seconds: float = 180.0
    max_cycle_rows: int = 25
    handoff_seconds: float = 0.1

    def __post_init__(self):
        if (any(type(value) is not int for value in
                (self.max_cycles, self.max_rows, self.max_cloud_operations,
                 self.max_cycle_rows)) or
                any(type(value) not in (int, float) or not math.isfinite(value)
                    for value in (self.max_seconds, self.handoff_seconds)) or
                not 1 <= self.max_cycles <= 12 or
                not 1 <= self.max_rows <= 300 or
                not 2 <= self.max_cloud_operations <= 24 or
                not 10 <= self.max_seconds <= 180 or
                not 1 <= self.max_cycle_rows <= 50 or
                not 0 <= self.handoff_seconds <= 0.1):
            raise ValueError('PP structured drain limits exceed reviewed bounds')


def drain_bounded(repository, transport_factory, *, execute=False,
                  limits=DrainLimits(), clock=time.monotonic, sleep=time.sleep):
    """Drain sealed A before collecting B, under finite independent budgets.

    Each selected generation is rechecked inside the origin-wide advisory lock
    by its worker. Its local ACK occurs only after authenticated cloud readback.
    A failure propagates; callers must reconcile cloud receipts and local ACKs.
    """
    if execute is not True:
        raise LifecycleHold('explicit PP structured drain execution required')
    if repository.pending_outbox_limit != 10_000:
        raise LifecycleHold('PP outbox safety cap changed')
    deadline = clock() + limits.max_seconds
    rows_done = operations = cycles = 0
    while cycles < limits.max_cycles and rows_done < limits.max_rows:
        if deadline - clock() < 10:
            break
        pending = repository.structured_pending_generations(PP_STRUCTURED_ORIGIN)
        if not pending:
            return {'status': 'drained', 'acknowledged': rows_done,
                    'cycles': cycles, 'cloud_operations': operations,
                    'retirement': 'off', 'raw_archive': 'not_started'}
        chosen = pending[0]
        if (chosen['state'] not in ('sealed', 'verified', 'collecting') or
                any(item['state'] in ('sealed', 'verified') for item in pending[1:])
                and chosen['state'] == 'collecting'):
            raise LifecycleHold('sealed structured backlog was not selected first')
        if operations + 2 > limits.max_cloud_operations:
            break
        remaining = deadline - clock()
        cycle_seconds = min(20.0, remaining - 5.0)
        if cycle_seconds < 5:
            break
        cycle_limits = ArchiveLimits(
            max_rows=min(limits.max_cycle_rows, limits.max_rows - rows_done),
            max_object_bytes=256 * 1024,
            max_decoded_bytes=256 * 1024,
            max_cycle_bytes=512 * 1024,
            max_requests=2,
            max_seconds=cycle_seconds,
            request_timeout_seconds=min(4.0, cycle_seconds))
        generation = chosen['generation_id']
        worker_type = (SealedStructuredWorker if chosen['state'] in ('sealed', 'verified')
                       else ActiveStructuredWorker)
        # The factory is a pure constructor. A later runtime review must prove
        # it performs no network I/O and passes this budget to any connection.
        worker = worker_type(repository, transport_factory(
            generation, timeout_seconds=cycle_seconds),
                             origin_id=PP_STRUCTURED_ORIGIN, limits=cycle_limits)
        result = worker.cycle(generation)
        if result.get('status') == 'idle':
            # Selection precedes the worker's origin lock. Another worker may
            # acknowledge the selected page in that gap; reselect without
            # claiming its ACK or assuming a cloud request happened here.
            if result.get('acknowledged') != 0 or result.get('requests', 0) != 0:
                raise LifecycleHold('ambiguous idle structured cycle')
            cycles += 1
            continue
        count = result['acknowledged']
        used = result['requests']
        if not 1 <= count <= cycle_limits.max_rows or used != 2:
            raise LifecycleHold('structured drain cycle did not prove fresh readback')
        rows_done += count
        operations += used
        cycles += 1
        if clock() >= deadline:
            raise ArchiveLimit('structured drain deadline after committed cycle; reconcile ACK')
        # Release the origin lock between cycles; collector work is never part
        # of this function or blocked on this session's handoff delay.
        if (limits.handoff_seconds and cycles < limits.max_cycles and
                rows_done < limits.max_rows and deadline - clock() > 10):
            sleep(limits.handoff_seconds)
    return {'status': 'bounded_stop', 'acknowledged': rows_done,
            'cycles': cycles, 'cloud_operations': operations,
            'retirement': 'off', 'raw_archive': 'not_started'}
