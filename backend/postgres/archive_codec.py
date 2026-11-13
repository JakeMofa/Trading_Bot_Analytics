"""Bounded, deterministic raw archive format; monetary/source strings stay exact.

This is a local format/transport contract, not a Supabase client. CP6 owns the
real private bucket, credentials, grants, and mutation-authority qualification.
"""
from __future__ import annotations

from dataclasses import dataclass
from contextvars import ContextVar
from datetime import datetime
from decimal import Decimal
import gzip
import hashlib
import io
import json
import time
from typing import Any, Protocol


ACTIVE_BUDGET = ContextVar('tradebot_archive_budget', default=None)


class ArchiveError(RuntimeError):
    code = 'archive_error'


class ArchiveLimit(ArchiveError):
    code = 'archive_limit'


class ArchiveIntegrityError(ArchiveError):
    code = 'archive_integrity'


class ArchiveUnavailable(ArchiveError):
    code = 'archive_unavailable'


def wire(value: Any) -> Any:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ArchiveIntegrityError('nonfinite decimal')
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: wire(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [wire(item) for item in value]
    return value


def encoded(value: Any) -> bytes:
    return json.dumps(wire(value), ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class ArchiveLimits:
    max_rows: int = 500
    max_object_bytes: int = 2 * 1024 * 1024
    max_decoded_bytes: int = 4 * 1024 * 1024
    max_cycle_bytes: int = 16 * 1024 * 1024
    max_requests: int = 24
    max_seconds: float = 20.0
    request_timeout_seconds: float = 4.0

    def __post_init__(self):
        if not 1 <= self.max_rows <= 5000:
            raise ValueError('archive row limit must be 1..5000')
        if not 1 <= self.max_requests <= 128:
            raise ValueError('archive request limit must be 1..128')
        if not 0 < self.request_timeout_seconds <= self.max_seconds <= 60:
            raise ValueError('archive deadlines must be positive and at most 60 seconds')
        if not 0 < self.max_object_bytes <= self.max_decoded_bytes <= 16 * 1024 * 1024:
            raise ValueError('archive object/decoded byte bounds invalid')
        if not self.max_object_bytes <= self.max_cycle_bytes <= 64 * 1024 * 1024:
            raise ValueError('archive cycle byte bound invalid')


class CycleBudget:
    """Transport implementations must enforce passed I/O time and byte bounds."""
    def __init__(self, limits: ArchiveLimits, clock=time.monotonic):
        self.limits, self.clock = limits, clock
        self.deadline = clock() + limits.max_seconds
        self.requests = self.bytes = 0

    def check(self):
        if self.clock() >= self.deadline:
            raise ArchiveLimit('cycle deadline reached')

    def __enter__(self):
        self._token = ACTIVE_BUDGET.set(self)
        return self

    def __exit__(self, *_):
        ACTIVE_BUDGET.reset(self._token)

    def request(self, byte_allowance: int = 0) -> float:
        self.check()
        if self.requests >= self.limits.max_requests:
            raise ArchiveLimit('cycle request limit reached')
        self.account(byte_allowance)
        self.requests += 1
        return min(self.limits.request_timeout_seconds, self.deadline - self.clock())

    def account(self, size: int):
        if size < 0 or self.bytes + size > self.limits.max_cycle_bytes:
            raise ArchiveLimit('cycle byte limit reached')
        self.bytes += size


class ArchiveTransport(Protocol):
    """Authenticated, bounded I/O. No replacement/delete/upsert operations.

    A duplicate put succeeds only when its stored bytes/content are identical.
    An ambiguous put raises; caller keeps local partitions and retries readback.
    Cloud adapters must not claim immutable-generated authority.
    """
    authority_scope: str

    def put_if_absent(self, key: str, data: bytes, *, timeout_seconds: float) -> None: ...
    def read_authenticated(self, key: str, *, max_bytes: int,
                           timeout_seconds: float) -> bytes: ...
    def put_structured(self, records: list[dict], *, timeout_seconds: float) -> None: ...
    def read_structured_authenticated(self, records: list[dict], *, max_bytes: int,
                                     timeout_seconds: float) -> list[dict]: ...


def row_cursor(row: dict) -> list[str]:
    return [row['source'], row['event_id']]


def _validate_rows(rows: list[dict], origin_id: str, generation_id: str):
    previous = None
    for row in rows:
        if row.get('origin_id') != origin_id or row.get('generation_id') != generation_id:
            raise ArchiveIntegrityError('archive identity outside generation')
        if not isinstance(row.get('source'), str) or not isinstance(row.get('event_id'), str):
            raise ArchiveIntegrityError('invalid event identity')
        current = row_cursor(row)
        if previous is not None and current <= previous:
            raise ArchiveIntegrityError('archive identities repeated or out of order')
        previous = current


def pack_chunk(rows: list[dict], *, origin_id: str, generation_id: str,
               after: list[str] | None, limits: ArchiveLimits) -> tuple[bytes, dict]:
    if len(rows) > limits.max_rows:
        raise ArchiveLimit('archive row limit reached')
    rows = wire(rows)
    _validate_rows(rows, origin_id, generation_id)
    if rows and after is not None and row_cursor(rows[0]) <= after:
        raise ArchiveIntegrityError('archive cursor does not advance')
    header = {'format_version': 1, 'dataset': 'raw.events', 'origin_id': origin_id,
              'generation_id': generation_id, 'after': after}
    raw = encoded(header) + b'\n' + b''.join(encoded(row) + b'\n' for row in rows)
    if len(raw) > limits.max_decoded_bytes:
        raise ArchiveLimit('archive decoded byte limit reached')
    blob = gzip.compress(raw, mtime=0)
    if len(blob) > limits.max_object_bytes:
        raise ArchiveLimit('archive compressed byte limit reached')
    coverage = {**header, 'first': row_cursor(rows[0]) if rows else None,
                'last': row_cursor(rows[-1]) if rows else after,
                'decoded_bytes': len(raw), 'decoded_sha256': sha256(raw),
                'identity_sha256': sha256(encoded([row_cursor(row) for row in rows]))}
    return blob, {'sha256': sha256(blob), 'byte_count': len(blob),
                  'row_count': len(rows), 'format_version': 1, 'coverage': coverage}


def unpack_chunk(blob: bytes, manifest: dict, limits: ArchiveLimits) -> list[dict]:
    if len(blob) > limits.max_object_bytes or len(blob) != manifest['byte_count']:
        raise ArchiveIntegrityError('archive byte count mismatch')
    if sha256(blob) != manifest['sha256']:
        raise ArchiveIntegrityError('archive compressed checksum mismatch')
    coverage = manifest['coverage']
    if manifest['format_version'] != 1 or coverage['dataset'] != 'raw.events':
        raise ArchiveIntegrityError('unsupported archive format/dataset')
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(blob)) as stream:
            raw = stream.read(limits.max_decoded_bytes + 1)
        if len(raw) > limits.max_decoded_bytes:
            raise ArchiveLimit('archive decode limit reached')
        if len(raw) != coverage['decoded_bytes'] or sha256(raw) != coverage['decoded_sha256']:
            raise ArchiveIntegrityError('archive decoded checksum mismatch')
        lines = raw.splitlines()
        header = json.loads(lines[0])
        rows = [json.loads(line) for line in lines[1:]]
    except (OSError, EOFError, ValueError, IndexError) as exc:
        raise ArchiveIntegrityError('invalid archive encoding') from exc
    expected = {key: coverage[key] for key in ('format_version', 'dataset', 'origin_id',
                                              'generation_id', 'after')}
    if header != expected or len(rows) != manifest['row_count'] or len(rows) > limits.max_rows:
        raise ArchiveIntegrityError('archive header/count mismatch')
    _validate_rows(rows, coverage['origin_id'], coverage['generation_id'])
    first = row_cursor(rows[0]) if rows else None
    last = row_cursor(rows[-1]) if rows else coverage['after']
    if first != coverage['first'] or last != coverage['last']:
        raise ArchiveIntegrityError('archive identity boundaries mismatch')
    if rows and coverage['after'] is not None and first <= coverage['after']:
        raise ArchiveIntegrityError('archive overlaps previous cursor')
    if sha256(encoded([row_cursor(row) for row in rows])) != coverage['identity_sha256']:
        raise ArchiveIntegrityError('archive identity checksum mismatch')
    return rows


def read_verified(transport: ArchiveTransport, manifest: dict,
                  budget: CycleBudget) -> list[dict]:
    timeout = budget.request(manifest['byte_count'])
    blob = transport.read_authenticated(manifest['object_key'],
                                        max_bytes=budget.limits.max_object_bytes,
                                        timeout_seconds=timeout)
    budget.check()
    return unpack_chunk(blob, manifest, budget.limits)


def manifest_set_hash(manifests: list[dict]) -> str:
    return sha256(encoded([{key: item[key] for key in
                           ('manifest_id', 'sha256', 'row_count', 'byte_count', 'coverage')}
                          for item in manifests]))
