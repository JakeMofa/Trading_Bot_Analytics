"""Fail-closed validation of local outbox rows before private history import.

This does not grant cloud access or acknowledge an outbox row. In particular,
mutable market and current-price projections need separately reviewed ordering.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from .archive_codec import ArchiveIntegrityError, encoded
from .domain import digest, timestamp


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

# These are the columns of the applied, private history_v2 contract. A local
# outbox envelope is not itself a cloud row: snapshot_evidence has a derived
# local hash but the cloud FK-edge table deliberately has no hash column.
CLOUD_COLUMNS = {
    'core.markets': ('origin_id', 'market_id', 'source', 'slug', 'duration',
                     'start_time', 'end_time', 'start_epoch', 'end_epoch',
                     'target', 'final', 'result', 'status', 'index_symbol',
                     'rules', 'first_seen', 'last_seen', 'payload', 'content_hash'),
    'core.candles': ('origin_id', 'source', 'symbol', 'granularity', 'time',
                     'low', 'high', 'open', 'close', 'volume', 'first_seen',
                     'payload', 'content_hash'),
    'core.current_prices': ('origin_id', 'source', 'symbol', 'event_id',
                             'generation_id', 'source_time', 'source_epoch',
                             'received_at', 'available_at', 'price', 'size',
                             'payload', 'content_hash'),
    'core.protected_evidence': ('origin_id', 'evidence_id', 'generation_id',
                                 'source', 'event_id', 'kind', 'market_id',
                                 'source_time', 'source_epoch', 'received_at',
                                 'available_at', 'payload', 'raw_payload',
                                 'content_hash'),
    'core.feature_snapshots': ('origin_id', 'snapshot_id', 'market_id', 'as_of',
                                'version', 'values_json', 'quality_json',
                                'evidence_json', 'content_hash'),
    'core.snapshot_evidence': ('origin_id', 'snapshot_id', 'evidence_id'),
    'core.predictions': ('origin_id', 'prediction_id', 'snapshot_id',
                          'market_id', 'model_version', 'as_of', 'created_at',
                          'seconds_remaining', 'probability_up',
                          'probability_down', 'abstain_reason',
                          'assumptions_json', 'payload', 'content_hash'),
    'core.outcomes': ('origin_id', 'outcome_id', 'market_id', 'evidence_id',
                      'result', 'final', 'source_time', 'source_epoch',
                      'confirmed_at', 'available_at', 'payload', 'content_hash'),
}
TIME_COLUMNS = frozenset({'first_seen', 'last_seen', 'received_at',
                          'available_at', 'as_of', 'created_at', 'confirmed_at'})
NUMERIC_COLUMNS = frozenset({'start_epoch', 'end_epoch', 'target', 'final',
                             'low', 'high', 'open', 'close', 'volume',
                             'source_epoch', 'price', 'size',
                             'seconds_remaining', 'probability_up',
                             'probability_down'})


def cloud_row(record: dict) -> dict:
    """Map a validated local envelope to the exact applied cloud row shape.

    This only prepares evidence. It does not write, advance a cursor, grant
    access, or turn a readback into retirement authority.
    """
    table = record.get('entity_type') if isinstance(record, dict) else None
    columns = CLOUD_COLUMNS.get(table)
    if columns is None or not isinstance(record.get('payload'), dict):
        raise ArchiveIntegrityError('unsupported structured cloud row')
    row = record['payload']
    expected = set(columns)
    if table == 'core.snapshot_evidence':
        expected.add('content_hash')
        edge = {key: row.get(key) for key in columns}
        if (set(row) != expected or any(value is None for value in edge.values()) or
                digest(edge) != record.get('content_hash') or
                row['content_hash'] != record['content_hash']):
            raise ArchiveIntegrityError('snapshot evidence edge hash mismatch')
    elif set(row) != expected or row.get('content_hash') != record.get('content_hash'):
        raise ArchiveIntegrityError('structured cloud row does not match contract')
    if row.get('origin_id') != record.get('origin_id'):
        raise ArchiveIntegrityError('structured cloud origin mismatch')
    return {key: row[key] for key in columns}


def cloud_row_matches(record: dict, readback: dict) -> bool:
    """Compare authenticated readback without losing exact numeric spelling.

    PostgreSQL may render timestamptz with another UTC spelling; source_time
    remains a literal evidence field and is compared byte-for-byte.
    """
    expected = cloud_row(record)
    if not isinstance(readback, dict) or set(readback) != set(expected):
        return False
    try:
        for name, value in expected.items():
            actual = readback[name]
            if name in TIME_COLUMNS and value is not None:
                if timestamp(value) != timestamp(actual):
                    return False
            elif name in NUMERIC_COLUMNS and value is not None:
                # Decimal equality would erase the original scale, which is
                # part of our exact financial representation contract.
                if isinstance(actual, (float, bool)) or str(value) != str(actual):
                    return False
            elif encoded(value) != encoded(actual):
                return False
    except (ValueError, TypeError, OverflowError, InvalidOperation):
        return False
    return True


def projection_order(previous: dict, proposed: dict) -> str:
    """Classify a mutable projection without authorizing a cloud overwrite.

    A future cloud adapter must enforce this comparison atomically in the
    database. An older or equal-time conflicting revision is a HOLD.
    """
    if (previous.get('entity_type') != proposed.get('entity_type') or
            previous.get('entity_id') != proposed.get('entity_id') or
            previous.get('origin_id') != proposed.get('origin_id') or
            previous.get('entity_type') not in MUTABLE_PROJECTIONS):
        raise ArchiveIntegrityError('unrelated mutable projection')
    table = proposed['entity_type']
    try:
        if table == 'core.markets':
            old = timestamp(previous['payload']['last_seen'])
            new = timestamp(proposed['payload']['last_seen'])
        else:
            old = (Decimal(str(previous['payload']['source_epoch'])),
                   timestamp(previous['payload']['received_at']))
            new = (Decimal(str(proposed['payload']['source_epoch'])),
                   timestamp(proposed['payload']['received_at']))
        if (isinstance(old, tuple) and (not old[0].is_finite() or not new[0].is_finite())):
            raise ValueError('nonfinite source epoch')
    except (KeyError, TypeError, ValueError, InvalidOperation):
        raise ArchiveIntegrityError('invalid mutable revision order') from None
    if new < old:
        raise ArchiveIntegrityError('stale mutable projection')
    if new == old:
        if proposed['content_hash'] != previous['content_hash'] or \
                encoded(proposed['payload']) != encoded(previous['payload']):
            raise ArchiveIntegrityError('conflicting mutable revision at same time')
        return 'identical'
    return 'newer_requires_atomic_cloud_update'


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
                isinstance(record['id'], bool) or not isinstance(record['id'], int) or record['id'] <= 0 or \
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
        current = (record['content_hash'], encoded(row))
        if previous is not None and previous != current:
            # A single batch cannot resolve ordering of mutable revisions, and
            # a reused immutable hash must not mask a different payload.
            raise ArchiveIntegrityError('conflicting revisions in structured batch')
        seen[index] = current
        validated.append(record)
    return sorted(validated, key=lambda row: (IMPORT_ORDER.index(row['entity_type']), row['id']))
