"""Exact canonical-byte reuse must preserve independent receipt/origin checks."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from postgres.archive_codec import ArchiveIntegrityError, encoded, sha256
from postgres.history_v2_transport import HistoryV2PostgresTransport


ORIGIN = 'pp-live-pp'
GENERATION = '00000000-0000-4000-8000-000000000019'


def record(index):
    payload = dict(origin_id=ORIGIN, source='coinbase', symbol='BTC-USD',
        granularity=60, time=1795000000+index*60, low='100.00000000000000000001',
        high='101.23000000000000000009', open='100.4500', close='100.6700',
        volume='1E-9', first_seen='2026-11-19T10:00:00+00:00',
        payload={'unicode': '雪 / café', 'escaped': '\\"\n',
                 'values': [None, False, 0, '0.00000000000000000001']},
        content_hash='a'*64)
    return dict(id=index, origin_id=ORIGIN, generation_id=GENERATION,
        entity_type='core.candles',
        entity_id=encoded([ORIGIN, 'coinbase', 'BTC-USD', 60, payload['time']]).decode(),
        content_hash=payload['content_hash'], payload=payload)


def receipt(item):
    raw = encoded(item)
    return dict(outbox_id=item['id'], total=len(raw), metadata_total=300,
        envelope=raw, entity_type=item['entity_type'], entity_id=item['entity_id'],
        content_hash=item['content_hash'], payload_hash=sha256(encoded(item['payload'])),
        envelope_hash=sha256(raw))


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, statement, parameters):
        return self

    def fetchall(self):
        return self.rows


class CanonicalReadbackTests(unittest.TestCase):
    def setUp(self):
        self.transport = HistoryV2PostgresTransport(lambda **kw: None,
            origin_id=ORIGIN, generation_id=GENERATION,
            expected_database='generated', expected_role='generated')
        self.records = [record(1), record(2)]

    def test_joined_authenticated_envelopes_equal_original_canonical_page(self):
        envelopes = []
        returned = self.transport._read_revisions(Rows([receipt(r) for r in self.records]),
            [1, 2], 8192, _canonical_envelopes=envelopes)
        original = encoded(self.records)
        self.assertEqual(returned, self.records)
        self.assertEqual(b'[' + b','.join(envelopes) + b']', original)
        self.assertEqual(self.transport._validate(self.records, max_bytes=8192), original)
        self.assertEqual(len(original), len(b'[' + b','.join(envelopes) + b']'))

    def test_every_receipt_field_remains_independently_checked(self):
        for name in ('entity_type', 'entity_id', 'content_hash', 'payload_hash', 'envelope_hash'):
            rows = [receipt(r) for r in self.records]
            rows[0][name] = 'b'*64
            with self.subTest(name=name), self.assertRaises(ArchiveIntegrityError):
                self.transport._read_revisions(Rows(rows), [1, 2], 8192,
                    _canonical_envelopes=[])

    def test_corrupt_or_cross_origin_envelopes_cannot_supply_reused_bytes(self):
        for name in ('noncanonical', 'origin', 'generation', 'id_order'):
            items = copy.deepcopy(self.records)
            if name == 'origin':
                items[0]['origin_id'] = 'production'
            elif name == 'generation':
                items[0]['generation_id'] = GENERATION[:-1] + '8'
            rows = [receipt(r) for r in items]
            if name == 'noncanonical':
                rows[0]['envelope'] += b' '
                rows[0]['envelope_hash'] = sha256(rows[0]['envelope'])
            elif name == 'id_order':
                rows.reverse()
            envelopes = []
            with self.subTest(name=name), self.assertRaises(ArchiveIntegrityError):
                self.transport._read_revisions(Rows(rows), [1, 2], 8192,
                    _canonical_envelopes=envelopes)
            self.assertEqual(envelopes, [])


if __name__ == '__main__':
    unittest.main()
