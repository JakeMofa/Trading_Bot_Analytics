"""Default-off, bounded structured sync while a PP raw generation collects.

Raw upload, generation verification, and local retirement stay on the sealed
archive path. Nothing in this module is wired to a deployed service.
"""
from __future__ import annotations

from .archive_codec import ArchiveIntegrityError, ArchiveLimits, CycleBudget, encoded, wire
from .history_v2_envelope import validate_outbox_stream
from .lifecycle import LifecycleHold

PP_STRUCTURED_ORIGIN = 'pp-live-pp'


class ActiveStructuredWorker:
    allowed_states = frozenset({'collecting'})
    hold_other_pending = True

    def __init__(self, repository, transport, *, origin_id: str,
                 limits: ArchiveLimits = ArchiveLimits()):
        if origin_id != PP_STRUCTURED_ORIGIN:
            raise ValueError('active structured sync requires exact PP origin')
        self.repository, self.transport = repository, transport
        self.origin_id, self.limits = origin_id, limits

    def cycle(self, generation_id: str) -> dict:
        budget = CycleBudget(self.limits)
        with budget, self.repository.structured_sync_lock(self.origin_id):
            generation = self.repository.generation(generation_id)
            if (generation['origin_id'] != self.origin_id or
                    generation['state'] not in self.allowed_states):
                raise LifecycleHold('structured generation state is not eligible')
            if self.hold_other_pending and self.repository.has_other_pending(self.origin_id, generation_id):
                raise LifecycleHold('another generation has pending structured evidence')
            rows = self.repository.outbox(generation_id, self.limits.max_rows,
                                          self.limits.max_decoded_bytes)
            if not rows:
                return {'status': 'idle', 'acknowledged': 0,
                        'raw_archive': 'not_started', 'retirement': 'off'}
            keys = ('id', 'origin_id', 'generation_id', 'entity_type',
                    'entity_id', 'content_hash', 'payload')
            records = [wire({key: row[key] for key in keys}) for row in rows]
            validate_outbox_stream(records, origin_id=self.origin_id,
                                   generation_id=generation_id)
            size = len(encoded(records))
            if size > self.limits.max_decoded_bytes:
                raise ArchiveIntegrityError('structured stream exceeds byte bound')
            self.transport.put_structured(records, timeout_seconds=budget.request(size))
            budget.check()
            readback = self.transport.read_structured_authenticated(
                records, max_bytes=self.limits.max_decoded_bytes,
                timeout_seconds=budget.request(size))
            budget.check()
            if encoded(readback) != encoded(records):
                raise ArchiveIntegrityError('structured authenticated readback mismatch')
            self.repository.acknowledge(generation_id, records)
            budget.check()
            return {'status': 'acknowledged', 'acknowledged': len(records),
                    'raw_archive': 'not_started', 'retirement': 'off',
                    'requests': budget.requests, 'bytes': budget.bytes}


class SealedStructuredWorker(ActiveStructuredWorker):
    """Drain A's structured outbox while B collects; never upload raw here."""
    allowed_states = frozenset({'sealed', 'verified'})
    hold_other_pending = False
