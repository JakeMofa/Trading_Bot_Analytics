"""Network-free active outbox safety and ordering tests."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from postgres.active_structured import ActiveStructuredWorker
from postgres.archive_codec import ArchiveIntegrityError, ArchiveLimits, ArchiveUnavailable, encoded
from postgres.history_v2_envelope import validate_outbox_stream
from postgres.lifecycle import LifecycleHold


ORIGIN = 'pp-live-fixture'
GENERATION = '00000000-0000-4000-8000-000000000001'
NEXT_GENERATION = '00000000-0000-4000-8000-000000000002'


def price(outbox_id, source_epoch, *, digest=None, generation_id=GENERATION):
    row = dict(origin_id=ORIGIN, source='coinbase', symbol='BTC-USD',
               event_id=f'tick-{outbox_id}', generation_id=generation_id,
               source_time=f'2026-11-18T00:00:{outbox_id:02d}Z',
               source_epoch=str(source_epoch),
               received_at=f'2026-11-18T00:00:{outbox_id:02d}Z',
               available_at=f'2026-11-18T00:00:{outbox_id:02d}Z',
               price='100.2300', size=None, payload={'source': 'fixture'},
               content_hash=digest or f'{outbox_id:064x}')
    return {'id': outbox_id, 'origin_id': ORIGIN, 'generation_id': generation_id,
            'entity_type': 'core.current_prices',
            'entity_id': encoded([ORIGIN, 'coinbase', 'BTC-USD']).decode(),
            'content_hash': row['content_hash'], 'payload': row}


class Repository:
    def __init__(self, rows):
        self.rows, self.acknowledged = rows, []
        self.state, self.origin = 'collecting', ORIGIN
        self.generation_id = GENERATION
        self.other_rows = []

    def generation(self, generation_id):
        assert generation_id == self.generation_id
        return {'origin_id': self.origin, 'state': self.state}

    def has_other_pending(self, origin_id, generation_id):
        assert origin_id == self.origin and generation_id == self.generation_id
        return bool(self.other_rows)

    def outbox(self, generation_id, limit, max_bytes):
        return deepcopy(self.rows[:limit])

    def acknowledge(self, generation_id, records):
        self.acknowledged.extend(record['id'] for record in records)
        self.rows = self.rows[len(records):]


class Transport:
    def __init__(self):
        self.calls, self.remote = [], None
        self.fail_put = self.fail_read = self.corrupt = False

    def put_structured(self, records, *, timeout_seconds):
        self.calls.append('put')
        if self.fail_put:
            raise ArchiveUnavailable('generated outage')
        self.remote = deepcopy(records)

    def read_structured_authenticated(self, records, *, max_bytes, timeout_seconds):
        self.calls.append('read')
        if self.fail_read:
            raise ArchiveUnavailable('generated readback failure')
        result = deepcopy(self.remote)
        if self.corrupt:
            result[0]['payload']['price'] = 'wrong'
        return result


class ActiveStructuredTests(unittest.TestCase):
    def test_newer_b_waits_for_pending_a_before_any_cloud_projection(self):
        pending_a = [price(10, '1794960010')]
        repository = Repository([price(11, '1794960011',
                                       generation_id=NEXT_GENERATION)])
        repository.generation_id = NEXT_GENERATION
        repository.other_rows = pending_a
        transport = Transport()
        with self.assertRaises(LifecycleHold):
            ActiveStructuredWorker(repository, transport,
                                   origin_id=ORIGIN).cycle(NEXT_GENERATION)
        self.assertEqual(transport.calls, [])
        self.assertEqual(repository.acknowledged, [])
        self.assertEqual([row['id'] for row in repository.other_rows], [10])
        repository.other_rows = []  # A's separate verified sync drained.
        result = ActiveStructuredWorker(repository, transport,
                                        origin_id=ORIGIN).cycle(NEXT_GENERATION)
        self.assertEqual(result['acknowledged'], 1)
        self.assertEqual(repository.acknowledged, [11])

    def test_multiple_mutable_revisions_keep_order_and_ack_after_readback(self):
        rows = [price(1, '1794960001'), price(2, '1794960002')]
        self.assertEqual([row['id'] for row in validate_outbox_stream(
            rows, origin_id=ORIGIN, generation_id=GENERATION)], [1, 2])
        repository, transport = Repository(rows), Transport()
        result = ActiveStructuredWorker(repository, transport,
                                        origin_id=ORIGIN).cycle(GENERATION)
        self.assertEqual(result['acknowledged'], 2)
        self.assertEqual(result['raw_archive'], 'not_started')
        self.assertEqual(transport.calls, ['put', 'read'])
        self.assertEqual(repository.acknowledged, [1, 2])

    def test_outage_corruption_and_wrong_generation_never_ack(self):
        for failure in ('fail_put', 'fail_read', 'corrupt'):
            with self.subTest(failure=failure):
                repository, transport = Repository([price(1, '1794960001')]), Transport()
                setattr(transport, failure, True)
                with self.assertRaises((ArchiveUnavailable, ArchiveIntegrityError)):
                    ActiveStructuredWorker(repository, transport,
                        origin_id=ORIGIN).cycle(GENERATION)
                self.assertEqual(repository.acknowledged, [])
                self.assertEqual(len(repository.rows), 1)
        repository = Repository([price(1, '1794960001')])
        repository.origin = 'production'
        transport = Transport()
        with self.assertRaises(LifecycleHold):
            ActiveStructuredWorker(repository, transport,
                                   origin_id=ORIGIN).cycle(GENERATION)
        self.assertEqual(transport.calls, [])

    def test_stale_revision_duplicate_id_and_unbounded_batch_hold(self):
        valid = price(1, '1794960001')
        for rows in ([price(2, '1794960002'), valid],
                     [valid, {**price(2, '1794960002'), 'id': 1}],
                     [valid] * 501):
            with self.assertRaises(ArchiveIntegrityError):
                validate_outbox_stream(rows, origin_id=ORIGIN,
                                       generation_id=GENERATION)
        stale = [price(1, '1794960002'), price(2, '1794960001')]
        with self.assertRaises(ArchiveIntegrityError):
            validate_outbox_stream(stale, origin_id=ORIGIN,
                                   generation_id=GENERATION)

    def test_no_sync_after_seal_or_wrong_origin(self):
        repository, transport = Repository([price(1, '1794960001')]), Transport()
        repository.state = 'sealed'
        with self.assertRaises(LifecycleHold):
            ActiveStructuredWorker(repository, transport,
                                   origin_id=ORIGIN).cycle(GENERATION)
        with self.assertRaises(ValueError):
            ActiveStructuredWorker(repository, transport,
                                   origin_id='production')
        self.assertEqual(transport.calls, [])


if __name__ == '__main__':
    unittest.main()
