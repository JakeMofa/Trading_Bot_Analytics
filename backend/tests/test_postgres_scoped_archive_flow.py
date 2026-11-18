"""Isolated PostgreSQL A→B archive handoff with generated HTTP only.

The fixture is destroyed by Linux CI. It proves no PP or Supabase runtime gate.
"""
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
import unittest
import uuid

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from postgres.archive_codec import ArchiveLimits, encoded
from postgres.archive_transport import ScopedArchiveTransport
from postgres.connection import connect
from postgres.lifecycle import ArchiveWorker, LifecycleHold, LifecycleRepository
from postgres.supabase_storage import SupabaseStorageTransport
from postgres_lifecycle_fixtures import ImmutableMemoryTransport, generated_rows


ENABLED = bool(os.getenv('TRADEBOT_TEST_LIFECYCLE_DSN') and os.getenv('TRADEBOT_TEST_APP_DSN'))


@unittest.skipUnless(ENABLED, 'isolated generated PostgreSQL DSNs not supplied')
class ScopedArchivePostgresFlowTests(unittest.TestCase):
    def test_b_write_survives_a_archive_and_unqualified_retirement_is_blocked(self):
        lifecycle = lambda: connect(os.environ['TRADEBOT_TEST_LIFECYCLE_DSN'],
                                    environment='preprod')
        application = lambda: connect(os.environ['TRADEBOT_TEST_APP_DSN'],
                                      environment='preprod')
        repository = LifecycleRepository(lifecycle)
        origin = 'generated-archive-' + uuid.uuid4().hex
        first = repository.bootstrap(origin, datetime.now(timezone.utc) - timedelta(hours=73))

        def insert(generation_id, suffix):
            row = generated_rows(str(generation_id), 1, origin)[0]
            row['event_id'] = 'event-' + suffix
            row['content_hash'] = suffix.zfill(64)
            columns = list(row)
            placeholders = ','.join('%s::jsonb' if column == 'payload' else '%s'
                                    for column in columns)
            values = [encoded(row[column]).decode() if column == 'payload' else row[column]
                      for column in columns]
            with application() as database:
                with database.transaction():
                    database.execute(f'INSERT INTO raw.events({",".join(columns)}) VALUES({placeholders})',
                                     values)

        insert(first['generation_id'], '1')
        switched = repository.switch_if_due(origin)
        self.assertEqual(switched['status'], 'switched')
        second = switched['generation_id']
        insert(second, '2')  # A is sealed while B acknowledges a new raw write.

        objects = {}
        calls = []
        def handle(request):
            calls.append(request.method)
            key = request.url.path.split('/market-raw/', 1)[-1]
            if request.method == 'POST':
                if key in objects:
                    return httpx.Response(409, json={'code':'KeyAlreadyExists'})
                objects[key] = request.content
                return httpx.Response(200, json={'Key':key})
            return httpx.Response(200, content=objects[key]) if key in objects else httpx.Response(404)

        with httpx.Client(transport=httpx.MockTransport(handle), trust_env=False) as client:
            raw = SupabaseStorageTransport('generated-public-project-key',
                                           'generated-private-access-token', client=client)
            transport = ScopedArchiveTransport(raw, ImmutableMemoryTransport(),
                origin_id=origin, generation_id=str(first['generation_id']))
            worker = ArchiveWorker(repository, transport, ArchiveLimits(max_rows=5))
            result = worker.archive_cycle(str(first['generation_id']))
            self.assertEqual(result['status'], 'archived')
            self.assertEqual(calls, ['POST', 'GET'])
            with self.assertRaisesRegex(LifecycleHold, 'runtime retirement disabled'):
                worker.retire_generated(str(first['generation_id']), qualification_enabled=True)

        with lifecycle() as database:
            counts = database.execute('''SELECT generation_id,count(*) AS count FROM raw.events
                WHERE origin_id=%s GROUP BY generation_id''', (origin,)).fetchall()
            self.assertEqual({str(row['generation_id']):row['count'] for row in counts},
                             {str(first['generation_id']):1, str(second):1})
            states = database.execute('''SELECT generation_id,state FROM archive.generations
                WHERE origin_id=%s''', (origin,)).fetchall()
            self.assertEqual({str(row['generation_id']):row['state'] for row in states},
                             {str(first['generation_id']):'verified', str(second):'collecting'})


if __name__ == '__main__':
    unittest.main()
