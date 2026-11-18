"""Generated, network-free structured history envelope tests."""
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from postgres.archive_codec import ArchiveIntegrityError, encoded
from postgres.domain import digest
from postgres.history_v2_envelope import (CLOUD_COLUMNS, IMPORT_ORDER, TABLE_KEYS,
    cloud_row, cloud_row_matches, projection_order, validate_outbox_batch)


ORIGIN = 'generated-pp'
GENERATION = '00000000-0000-4000-8000-000000000001'


def item(table, *, row_id=1, digest='a' * 64):
    keys = TABLE_KEYS[table]
    values = {'origin_id': ORIGIN, 'market_id': 'market-1', 'snapshot_id': 'snapshot-1',
              'evidence_id': 'evidence-1', 'prediction_id': 'prediction-1',
              'outcome_id': 'outcome-1', 'source': 'coinbase', 'symbol': 'BTC-USD',
              'granularity': 60, 'time': 1800000000}
    payload = {key: values[key] for key in keys}
    payload['content_hash'] = digest
    if table == 'core.current_prices':
        payload['generation_id'] = GENERATION
    return {'id': row_id, 'origin_id': ORIGIN, 'generation_id': GENERATION,
            'entity_type': table, 'entity_id': encoded([payload[k] for k in keys]).decode(),
            'content_hash': digest, 'payload': payload}


class HistoryV2EnvelopeTests(unittest.TestCase):
    def check(self, records):
        return validate_outbox_batch(records, origin_id=ORIGIN, generation_id=GENERATION)

    def test_all_supported_tables_reorder_for_foreign_keys(self):
        items = [item(table, row_id=index + 1) for index, table in enumerate(reversed(IMPORT_ORDER))]
        self.assertEqual([row['entity_type'] for row in self.check(items)], list(IMPORT_ORDER))

    def test_wrong_origin_generation_identity_hash_or_payload_holds(self):
        valid = item('core.current_prices')
        for mutation in (
            {'origin_id': 'production'},
            {'generation_id': '00000000-0000-4000-8000-000000000002'},
            {'entity_id': '["wrong"]'},
            {'content_hash': 'invalid'},
            {'entity_type': 'raw.events'},
            {'payload': {**valid['payload'], 'origin_id': 'production'}},
            {'payload': {**valid['payload'], 'generation_id': 'wrong'}},
        ):
            with self.subTest(mutation=mutation), self.assertRaises(ArchiveIntegrityError):
                self.check([{**valid, **mutation}])

    def test_conflicting_revisions_in_one_batch_hold(self):
        first = item('core.markets')
        second = item('core.markets', row_id=2, digest='b' * 64)
        with self.assertRaises(ArchiveIntegrityError):
            self.check([first, second])
        same_hash_changed_body = item('core.candles', row_id=3)
        same_hash_changed_body['payload']['close'] = '100.01'
        with self.assertRaises(ArchiveIntegrityError):
            self.check([item('core.candles'), same_hash_changed_body])

    def test_bounds_and_unexpected_envelope_fields_hold(self):
        with self.assertRaises(ArchiveIntegrityError):
            self.check([item('core.markets')] * 501)
        with self.assertRaises(ArchiveIntegrityError):
            self.check([{**item('core.markets'), 'extra': True}])
        with self.assertRaises(ArchiveIntegrityError):
            self.check([{**item('core.markets'), 'id': True}])

    def test_cloud_columns_match_applied_private_schema(self):
        import re
        schema = (Path(__file__).resolve().parents[2] / 'supabase' / 'migrations' /
                  '20261116050000_history_v2_private.sql').read_text()
        for table, columns in CLOUD_COLUMNS.items():
            name = table.split('.')[1]
            body = re.search(r'CREATE TABLE history_v2\.' + name + r' \((.*?)\n\);',
                             schema, re.DOTALL)
            self.assertIsNotNone(body, name)
            actual = re.findall(r'(?:^|,)\s*([a-z_]+) (?:text|integer|bigint|timestamptz|jsonb|history_v2\.)',
                                body.group(1))
            self.assertEqual(set(columns), set(actual), name)

    def test_snapshot_edge_hash_is_derived_but_not_a_cloud_column(self):
        row = dict(origin_id=ORIGIN, snapshot_id='snapshot-1', evidence_id='evidence-1')
        record = item('core.snapshot_evidence', digest=digest(row))
        self.assertEqual(cloud_row(record), row)
        self.assertTrue(cloud_row_matches(record, row))
        with self.assertRaises(ArchiveIntegrityError):
            cloud_row({**record, 'content_hash': 'b' * 64})
        with self.assertRaises(ArchiveIntegrityError):
            cloud_row({**record, 'payload': {**record['payload'], 'evidence_id': 'wrong'}})
        self.assertFalse(cloud_row_matches(record, {**row, 'content_hash': record['content_hash']}))

    def test_exact_cloud_readback_preserves_decimal_scale_and_source_timestamp(self):
        record = item('core.current_prices')
        record['payload'] = dict(origin_id=ORIGIN, source='coinbase', symbol='BTC-USD',
            event_id='tick-1', generation_id=GENERATION,
            source_time='2026-11-17T12:00:00.123456789Z', source_epoch='1794916800.123456789',
            received_at='2026-11-17T12:00:01+00:00',
            available_at='2026-11-17T12:00:01+00:00', price='100.2300', size='0.0100',
            payload={'price': '100.2300', 'feed': 'coinbase'}, content_hash=record['content_hash'])
        row = cloud_row(record)
        self.assertTrue(cloud_row_matches(record, {**row, 'received_at': '2026-11-17T07:00:01-05:00'}))
        self.assertFalse(cloud_row_matches(record, {**row, 'price': '100.23'}))
        self.assertFalse(cloud_row_matches(record, {**row, 'source_time': '2026-11-17T12:00:00.123456789+00:00'}))
        self.assertFalse(cloud_row_matches(record, {**row, 'payload': {'price': '100.23'}}))

    def test_mutable_revision_order_is_monotonic_and_conflict_safe(self):
        first = item('core.current_prices')
        first['payload']['source_epoch'] = '1794916800.1'
        first['payload']['received_at'] = '2026-11-17T12:00:01+00:00'
        newer = item('core.current_prices', row_id=2, digest='b' * 64)
        newer['payload'].update(source_epoch='1794916800.2',
                                received_at='2026-11-17T12:00:02+00:00')
        self.assertEqual(projection_order(first, first), 'identical')
        self.assertEqual(projection_order(first, newer), 'newer_requires_atomic_cloud_update')
        with self.assertRaises(ArchiveIntegrityError):
            projection_order(newer, first)
        with self.assertRaises(ArchiveIntegrityError):
            projection_order(first, {**newer, 'payload': {**newer['payload'],
                'source_epoch': first['payload']['source_epoch'],
                'received_at': first['payload']['received_at']}})
        market = item('core.markets')
        market['payload']['last_seen'] = '2026-11-17T12:00:01Z'
        updated = item('core.markets', row_id=2, digest='c' * 64)
        updated['payload']['last_seen'] = '2026-11-17T12:00:02Z'
        self.assertEqual(projection_order(market, updated), 'newer_requires_atomic_cloud_update')


if __name__ == '__main__':
    unittest.main()
