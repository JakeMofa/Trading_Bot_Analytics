"""Default-off, origin-bound raw and structured archive transport.

This composes separately qualified cloud clients. It never grants retirement
authority: live Storage policies, history_v2 grants, and privileged mutation
fencing remain CP6 gates. The structured writer is injected so generated tests
can exercise the full archive worker without provisioning cloud credentials.
"""
from __future__ import annotations

import uuid

from .archive_codec import ArchiveIntegrityError, sha256
from .history_v2_envelope import validate_outbox_batch


class ScopedArchiveTransport:
    authority_scope = 'supabase-unqualified'

    def __init__(self, raw, structured, *, origin_id: str, generation_id: str):
        try:
            canonical = str(uuid.UUID(generation_id))
        except (TypeError, ValueError, AttributeError):
            canonical = None
        if (not isinstance(origin_id, str) or not origin_id or len(origin_id) > 160
                or canonical != generation_id):
            raise ValueError('invalid archive origin or generation binding')
        self.raw, self.structured = raw, structured
        self.origin_id, self.generation_id = origin_id, generation_id
        self._prefix = f'raw-v1/{sha256(origin_id.encode())}/{generation_id}/'

    def _key(self, key):
        if not isinstance(key, str) or not key.startswith(self._prefix):
            raise ArchiveIntegrityError('archive object outside bound generation')

    def put_if_absent(self, key, data, *, timeout_seconds):
        self._key(key)
        return self.raw.put_if_absent(key, data, timeout_seconds=timeout_seconds)

    def read_authenticated(self, key, *, max_bytes, timeout_seconds):
        self._key(key)
        return self.raw.read_authenticated(key, max_bytes=max_bytes,
                                           timeout_seconds=timeout_seconds)

    def put_structured(self, records, *, timeout_seconds):
        validate_outbox_batch(records, origin_id=self.origin_id,
                              generation_id=self.generation_id)
        return self.structured.put_structured(records, timeout_seconds=timeout_seconds)

    def read_structured_authenticated(self, records, *, max_bytes, timeout_seconds):
        validate_outbox_batch(records, origin_id=self.origin_id,
                              generation_id=self.generation_id)
        rows = self.structured.read_structured_authenticated(
            records, max_bytes=max_bytes, timeout_seconds=timeout_seconds)
        validate_outbox_batch(rows, origin_id=self.origin_id,
                              generation_id=self.generation_id)
        return rows
