"""Generated HTTP only; no Supabase writes, privileges, or PP retirement."""
from pathlib import Path
import sys
import unittest

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from postgres.archive_codec import ArchiveIntegrityError, ArchiveLimits, encoded
from postgres.archive_transport import ScopedArchiveTransport
from postgres.lifecycle import ArchiveWorker, LifecycleHold
from postgres.supabase_storage import SupabaseStorageTransport
from postgres_lifecycle_fixtures import ImmutableMemoryTransport, MemoryRepository


class ScopedArchiveTransportTests(unittest.TestCase):
    def setUp(self):
        self.repository = MemoryRepository()
        self.origin = self.repository.record['origin_id']
        self.generation = self.repository.generation_id
        self.objects = {}
        self.requests = []
        self.corrupt = False

        def handle(request):
            self.requests.append((request.method, request.url.path))
            key = request.url.path.split('/market-raw/', 1)[-1]
            if request.method == 'POST':
                self.assertEqual(request.headers['x-upsert'], 'false')
                if key in self.objects:
                    return httpx.Response(409, json={'code': 'KeyAlreadyExists'})
                self.objects[key] = request.content
                return httpx.Response(200, json={'Key': key})
            if key not in self.objects:
                return httpx.Response(404, json={'code': 'NoSuchKey'})
            return httpx.Response(200, content=b'corrupted' if self.corrupt else self.objects[key])

        self.client = httpx.Client(transport=httpx.MockTransport(handle), trust_env=False)
        self.addCleanup(self.client.close)
        raw = SupabaseStorageTransport('generated-public-project-key',
                                       'generated-private-access-token', client=self.client)
        self.structured = ImmutableMemoryTransport()
        self.transport = ScopedArchiveTransport(raw, self.structured,
            origin_id=self.origin, generation_id=self.generation)
        self.worker = ArchiveWorker(self.repository, self.transport, ArchiveLimits(max_rows=5))

    def _outbox(self):
        row = self.repository.rows[0]
        payload = {key: row[key] for key in ('origin_id', 'source', 'symbol', 'event_id',
            'generation_id', 'source_time', 'source_epoch', 'received_at',
            'available_at', 'price', 'size', 'payload', 'content_hash')}
        return {'id': 1, 'origin_id': self.origin, 'generation_id': self.generation,
                'entity_type': 'core.current_prices',
                'entity_id': encoded([self.origin, row['source'], row['symbol']]).decode(),
                'content_hash': row['content_hash'], 'payload': payload,
                'acknowledged_at': None}

    def test_mock_storage_and_structured_readback_preserve_raw_and_hold_retirement(self):
        self.repository.outbox_rows = [self._outbox()]
        result = self.worker.archive_cycle(self.generation)
        self.assertEqual(result['status'], 'archived')
        self.assertEqual(result['outbox_rows'], 1)
        self.assertEqual(result['raw_rows'], 5)
        self.assertEqual(len(self.repository.rows), 5)
        self.assertEqual(len(self.repository.catalog), 1)
        self.assertIsNotNone(self.repository.outbox_rows[0]['acknowledged_at'])
        self.assertEqual([method for method, _ in self.requests], ['POST', 'GET'])
        self.assertIn(('structured_authenticated_get', 1), self.structured.calls)
        with self.assertRaisesRegex(LifecycleHold, 'runtime retirement disabled'):
            self.worker.retire_generated(self.generation, qualification_enabled=True)
        self.assertEqual(len(self.repository.rows), 5)

    def test_origin_generation_mismatch_stops_before_network_or_structured_write(self):
        with self.assertRaises(ArchiveIntegrityError):
            self.transport.put_if_absent('raw-v1/' + '0' * 64 + '/' + self.generation +
                                         '/' + '0' * 64 + '.jsonl.gz', b'x', timeout_seconds=2)
        with self.assertRaises(ArchiveIntegrityError):
            self.transport.put_structured([{**self._outbox(), 'origin_id': 'production'}],
                                          timeout_seconds=2)
        self.assertEqual(self.requests, [])
        self.assertEqual(self.structured.calls, [])

    def test_corrupt_mock_authenticated_readback_keeps_sealed_raw(self):
        self.corrupt = True
        with self.assertRaises(ArchiveIntegrityError):
            self.worker.archive_cycle(self.generation)
        self.assertEqual(len(self.repository.rows), 5)
        self.assertEqual(self.repository.catalog, [])
        self.assertEqual(self.repository.record['state'], 'sealed')
        self.assertEqual([method for method, _ in self.requests], ['POST', 'GET'])


if __name__ == '__main__':
    unittest.main()
