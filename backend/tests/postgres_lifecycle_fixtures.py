"""Isolated generated fixtures only. This transport has no network capabilities."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import uuid

from postgres.archive_codec import (ArchiveIntegrityError, ArchiveUnavailable,
                                    encoded, manifest_set_hash, row_cursor, wire)
from postgres.lifecycle import LifecycleHold, validate_manifest_chain


class ImmutableMemoryTransport:
    authority_scope = 'immutable-generated'

    def __init__(self):
        self.objects, self.structured = {}, {}
        self.calls = []
        self.fail_put = self.ambiguous_put = self.fail_get = False
        self.cancel_put = False
        self.corrupt_structured = False

    def put_if_absent(self, key, data, *, timeout_seconds):
        assert 0 < timeout_seconds <= 60
        self.calls.append(('put', key))
        if self.cancel_put:
            raise KeyboardInterrupt()
        if self.fail_put:
            raise ArchiveUnavailable('generated outage')
        if key in self.objects and self.objects[key] != data:
            raise ArchiveIntegrityError('immutable object conflict')
        self.objects[key] = data
        if self.ambiguous_put:
            raise ArchiveUnavailable('generated ambiguous upload')

    def read_authenticated(self, key, *, max_bytes, timeout_seconds):
        assert 0 < timeout_seconds <= 60
        self.calls.append(('authenticated_get', key))
        if self.fail_get or key not in self.objects:
            raise ArchiveUnavailable('generated object missing')
        data = self.objects[key]
        if len(data) > max_bytes:
            raise ArchiveIntegrityError('read exceeds byte bound')
        return data

    def put_structured(self, records, *, timeout_seconds):
        self.calls.append(('structured_put', len(records)))
        for row in records:
            key = self._key(row)
            if key in self.structured and self.structured[key] != row:
                raise ArchiveIntegrityError('immutable structured conflict')
            self.structured[key] = deepcopy(row)

    def read_structured_authenticated(self, records, *, max_bytes, timeout_seconds):
        self.calls.append(('structured_authenticated_get', len(records)))
        try:
            result = [deepcopy(self.structured[self._key(row)]) for row in records]
        except KeyError as exc:
            raise ArchiveUnavailable('structured row missing') from exc
        if self.corrupt_structured and result:
            result[0]['payload'] = {'changed': True}
        if len(encoded(result)) > max_bytes:
            raise ArchiveIntegrityError('structured byte bound')
        return result

    @staticmethod
    def _key(row):
        return row['origin_id'], row['entity_type'], row['entity_id'], row['content_hash']


def generated_rows(generation_id, count=5, origin='generated-lifecycle-unit'):
    now = datetime(2026, 11, 12, tzinfo=timezone.utc)
    return [{'generation_id': generation_id, 'origin_id': origin,
             'source': 'coinbase', 'event_id': f'event-{index:04d}', 'kind': 'trade',
             'market_id': None, 'symbol': 'BTC-USD',
             'source_time': '2026-11-12T00:00:00.123456789Z',
             'source_epoch': Decimal('1794441600.123456789'),
             'received_at': now, 'available_at': now,
             'price': Decimal('12345.123456789012345678901234567890'),
             'size': None, 'payload': {'source': 'generated', 'missing': None},
             'raw_payload': '{"price":"12345.123456789012345678901234567890"}',
             'content_hash': str(index).zfill(64)} for index in range(count)]


class MemoryRepository:
    environment = 'preprod'

    def __init__(self, rows=None):
        generation_id = str(uuid.uuid4())
        self.rows = rows if rows is not None else generated_rows(generation_id)
        if self.rows:
            generation_id = self.rows[0]['generation_id']
        self.generation_id = generation_id
        self.record = {'origin_id': 'generated-lifecycle-unit', 'generation_id': generation_id,
                       'state': 'sealed', 'seal_count': len(self.rows), 'seal_hash': None,
                       'sealed_at': datetime(2026, 11, 12, tzinfo=timezone.utc), 'hold_reason': None}
        self.catalog, self.outbox_rows = [], []
        self.reader = self.protected_hold = False
        self.retire_calls = 0

    def generation(self, generation_id):
        assert generation_id == self.generation_id
        return deepcopy(self.record)

    def manifests(self, generation_id):
        return deepcopy(self.catalog)

    def archive_page(self, generation_id, after, limits):
        candidates = [row for row in self.rows if after is None or row_cursor(row) > after]
        return deepcopy(candidates[:limits.max_rows]), len(candidates) > limits.max_rows

    def record_manifest(self, generation_id, manifest):
        self.catalog.append(deepcopy(manifest))

    def mark_verified(self, generation_id):
        self.record.update(state='verified', seal_hash=validate_manifest_chain(self.catalog, self.record), hold_reason=None)

    def outbox(self, generation_id, limit, max_bytes=None):
        return deepcopy([row for row in self.outbox_rows if not row.get('acknowledged_at')][:limit])

    def acknowledge(self, generation_id, records):
        ids = {row['id'] for row in records}
        for row in self.outbox_rows:
            if row['id'] in ids:
                row['acknowledged_at'] = 'verified'

    def hold(self, generation_id, reason):
        self.record['hold_reason'] = reason

    @contextmanager
    def retirement(self, generation_id):
        if self.record['state'] != 'verified':
            raise LifecycleHold('not verified')
        if self.reader:
            raise LifecycleHold('readers not drained')
        if self.protected_hold:
            raise LifecycleHold('protected evidence not independently verified')
        if any(not row.get('acknowledged_at') for row in self.outbox_rows):
            raise LifecycleHold('structured outbox not acknowledged')
        yield None, deepcopy(self.record), deepcopy(self.catalog)

    def _pending(self, connection, generation_id, limit, **kwargs):
        return deepcopy(self.outbox_rows[:limit])

    def verify_local_chunk(self, connection, generation_id, manifest, decoded, limits):
        rows = [row for row in self.rows if (manifest['coverage']['after'] is None or row_cursor(row) > manifest['coverage']['after'])]
        rows = rows[:max(1, manifest['row_count'])]
        if wire(rows) != decoded:
            raise ArchiveIntegrityError('sealed local content differs')

    def retire_in_transaction(self, connection, generation, digest):
        assert digest == self.record['seal_hash']
        self.retire_calls += 1
        self.record['state'] = 'retired'
        self.rows.clear()

    def local_history(self, generation_id, after, limits):
        if self.record['state'] == 'retired':
            return deepcopy(self.record), None, False
        rows, more = self.archive_page(generation_id, after, limits)
        return deepcopy(self.record), rows, more


def outbox_row(repository):
    return {'id': 1, 'origin_id': repository.record['origin_id'],
            'generation_id': repository.generation_id, 'entity_type': 'core.current_prices',
            'entity_id': '["generated-lifecycle-unit","coinbase","BTC-USD"]',
            'content_hash': 'a' * 64, 'payload': wire(repository.rows[0]),
            'created_at': datetime.now(timezone.utc), 'acknowledged_at': None}
