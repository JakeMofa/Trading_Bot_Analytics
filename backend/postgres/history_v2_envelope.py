"""Fail-closed validation of local outbox rows before private history import.

This does not grant cloud access or acknowledge an outbox row. In particular,
mutable market and current-price projections need separately reviewed ordering.
"""
from __future__ import annotations

import re

from .archive_codec import ArchiveIntegrityError, encoded


HASH = re.compile(r'[0-9a-f]{64}\Z')
TABLE_KEYS = {
    'core.markets': ('origin_id', 'market_id'),
    'core.candles': ('origin_id', 'source', 'symbol', 'granularity', 'time'),
    'core.current_prices': ('origin_id', 'source', 'symbol'),
    'core.protected_evidence': ('origin_id', 'evidence_id'),
    'core.feature_snapshots': ('origin_id', 'snapshot_id'),
    'core.snapshot_evidence': ('origin_id', 'snapshot_id', 'evidence_id'),
    'core.predictions': ('origin_id', 'prediction_id'),
    'core.outcomes': ('origin_id', 'outcome_id'),
}
# Parent records must be imported before their foreign-key dependents.
IMPORT_ORDER = (
    'core.markets', 'core.candles', 'core.current_prices',
    'core.protected_evidence', 'core.feature_snapshots',
    'core.snapshot_evidence', 'core.predictions', 'core.outcomes',
)
MUTABLE_PROJECTIONS = frozenset({'core.markets', 'core.current_prices'})


def validate_outbox_batch(records: list[dict], *, origin_id: str,
                          generation_id: str) -> list[dict]:
    """Return records in FK-safe order; reject ambiguous identity or payload.

    The local outbox's content hash identifies the source/projection revision.
    It is not a generic hash of the entire row and cannot be recomputed here.
    The later importer must compare exact cloud readback before local ack.
    """
    if not isinstance(records, list) or len(records) > 500 or not origin_id or not generation_id:
        raise ArchiveIntegrityError('invalid structured batch scope')
    seen = {}
    validated = []
    for record in records:
        if not isinstance(record, dict) or set(record) != {
                'id', 'origin_id', 'generation_id', 'entity_type', 'entity_id',
                'content_hash', 'payload'}:
            raise ArchiveIntegrityError('invalid structured outbox envelope')
        table = record['entity_type']
        if table not in TABLE_KEYS or record['origin_id'] != origin_id or \
                record['generation_id'] != generation_id or \
                not isinstance(record['id'], int) or record['id'] <= 0 or \
                not isinstance(record['content_hash'], str) or \
                not HASH.fullmatch(record['content_hash']):
            raise ArchiveIntegrityError('invalid structured identity or scope')
        row = record['payload']
        if not isinstance(row, dict) or row.get('origin_id') != origin_id or \
                row.get('content_hash') != record['content_hash']:
            raise ArchiveIntegrityError('structured payload does not match envelope')
        if 'generation_id' in row and row['generation_id'] != generation_id:
            raise ArchiveIntegrityError('structured generation mismatch')
        keys = TABLE_KEYS[table]
        if any(key not in row or row[key] is None for key in keys):
            raise ArchiveIntegrityError('structured primary key missing')
        identity = [row[key] for key in keys]
        try:
            if record['entity_id'] != encoded(identity).decode('utf-8'):
                raise ArchiveIntegrityError('structured primary key mismatch')
        except (TypeError, ValueError, UnicodeError):
            raise ArchiveIntegrityError('invalid structured primary key encoding') from None
        index = (table, record['entity_id'])
        previous = seen.get(index)
        if previous is not None and previous != record['content_hash']:
            # A single batch cannot resolve ordering of mutable revisions.
            raise ArchiveIntegrityError('conflicting revisions in structured batch')
        seen[index] = record['content_hash']
        validated.append(record)
    return sorted(validated, key=lambda row: (IMPORT_ORDER.index(row['entity_type']), row['id']))
