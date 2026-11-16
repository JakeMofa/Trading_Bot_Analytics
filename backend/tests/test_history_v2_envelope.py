"""Generated, network-free structured history envelope tests."""
import unittest

from postgres.archive_codec import ArchiveIntegrityError, encoded
from postgres.history_v2_envelope import IMPORT_ORDER, TABLE_KEYS, validate_outbox_batch


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

    def test_bounds_and_unexpected_envelope_fields_hold(self):
        with self.assertRaises(ArchiveIntegrityError):
            self.check([item('core.markets')] * 501)
        with self.assertRaises(ArchiveIntegrityError):
            self.check([{**item('core.markets'), 'extra': True}])


if __name__ == '__main__':
    unittest.main()
