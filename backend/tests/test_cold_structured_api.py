"""Injected API composition only: no hosted credentials or network."""
import asyncio
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
import sys
from threading import Event
import unittest
from unittest.mock import Mock, patch

import httpx

from fastapi.testclient import TestClient
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.api import create_app
from postgres.archive_codec import ArchiveUnavailable
from postgres.config import Settings
from postgres.cold_structured_queries import RegisteredStructuredHistory, ColdQueryBusy
from test_cold_structured_history import setup


def registry(count=51):
    reader, source, rows, manifest = setup(count)
    query = dict(reader=reader, manifest=manifest, entity_type='core.predictions', market_id='market')
    return RegisteredStructuredHistory({'reviewed': query}, clock=lambda: 0), source, rows, manifest


def client_for(service=None, settings=None):
    return TestClient(create_app(settings or Settings(data_mode='pp_live', origin_id='pp-live-pp'),
        store=Mock(predictions=Mock(return_value=[])), history=Mock(),
        structured_history=service, refresh=False))


class ColdStructuredApiTests(unittest.TestCase):
    def test_default_route_absent_and_bad_environment_rejected(self):
        client = client_for()
        self.assertEqual(client.get('/history/structured/reviewed').status_code, 404)
        service, source, rows, manifest = registry()
        with self.assertRaises(ValueError):
            client_for(service, Settings())
        source.read_revisions.assert_not_called()

    def test_explicit_reviewed_query_pages_and_exact_decimal_response(self):
        service, source, rows, manifest = registry()
        client = client_for(service)
        first = client.get('/history/structured/reviewed')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()['rows'], rows[:50])
        self.assertEqual(first.json()['coverage']['whole_market_coverage'], 'not_established')
        service._next_start = float('-inf')
        second = client.get('/history/structured/reviewed', params=first.json()['next_cursor'])
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()['rows'], rows[50:])

    def test_prior_cursor_cannot_be_blessed_against_changed_server_manifest(self):
        service, source, rows, manifest = registry()
        first = service.read_query('reviewed')
        # A separately reviewed registry revision no longer has the same scope.
        service._queries['reviewed']['manifest'] = manifest[:-1]
        service._next_start = float('-inf')
        source.read_revisions.reset_mock()
        response = client_for(service).get('/history/structured/reviewed', params=first['next_cursor'])
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['detail']['code'], 'archive_integrity')
        source.read_revisions.assert_not_called()

    def test_unknown_query_and_invalid_continuation_do_not_call_cloud(self):
        service, source, rows, manifest = registry()
        client = client_for(service)
        self.assertEqual(client.get('/history/structured/not-reviewed').status_code, 404)
        self.assertEqual(client.get('/history/structured/reviewed?after_id=0').status_code, 422)
        failed = client.get('/history/structured/reviewed?after_id=999')
        self.assertEqual(failed.status_code, 503)
        self.assertEqual(failed.json()['detail']['code'], 'archive_integrity')
        source.read_revisions.assert_not_called()

    def test_cloud_outage_is_explicit_and_hot_local_routes_remain_independent(self):
        service, source, rows, manifest = registry()
        source.read_revisions.side_effect = OSError('secret detail')
        client = client_for(service)
        response = client.get('/history/structured/reviewed')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('secret', response.text)
        for path in ('/state/current', '/forecast/current', '/history/predictions', '/health'):
            self.assertEqual(client.get(path).status_code, 200)
        self.assertEqual(source.read_revisions.call_count, 1)

    def test_global_admission_and_rate_limit_do_not_queue(self):
        service, source, rows, manifest = registry(1)
        started, release = Event(), Event()
        def blocked(*args, **kwargs):
            started.set()
            self.assertTrue(release.wait(2))
            return rows
        source.read_revisions.side_effect = blocked
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(service.read_query, 'reviewed')
            self.assertTrue(started.wait(2))
            try:
                with self.assertRaises(ColdQueryBusy):
                    service.read_query('reviewed')
            finally:
                release.set()
            self.assertEqual(pending.result()['rows'], rows)
        response = client_for(service).get('/history/structured/reviewed')
        self.assertEqual(response.status_code, 429)
        self.assertEqual(source.read_revisions.call_count, 1)

    def test_registry_copies_manifest_and_rejects_arbitrary_reader(self):
        service, source, rows, manifest = registry(1)
        manifest[0]['envelope_sha256'] = 'b'*64
        self.assertEqual(service.read_query('reviewed')['rows'], rows)
        with self.assertRaises(ValueError):
            RegisteredStructuredHistory({'injected': dict(reader=Mock(), manifest=[],
                entity_type='core.predictions', market_id='market')})


    def test_cancelled_before_start_and_submit_failure_release_reserved_admission(self):
        service, source, rows, manifest = registry(1)
        try:
            pending = Future()
            with patch.object(service._executor, 'submit', return_value=pending):
                self.assertIs(service.submit_query('reviewed'), pending)
                self.assertTrue(pending.cancel())
            source.read_revisions.assert_not_called()
            service._next_start = float('-inf')
            with patch.object(service._executor, 'submit', side_effect=RuntimeError('executor closed')):
                with self.assertRaises(RuntimeError):
                    service.submit_query('reviewed')
            service._next_start = float('-inf')
            self.assertEqual(service.read_query('reviewed')['rows'], rows)
        finally:
            service.close()

    def test_app_shutdown_closes_registry_and_rejects_new_submissions(self):
        service, source, rows, manifest = registry(1)
        with client_for(service) as client:
            self.assertEqual(client.get('/history/structured/reviewed').status_code, 200)
        with self.assertRaises(ArchiveUnavailable):
            service.submit_query('reviewed')
        self.assertEqual(source.read_revisions.call_count, 1)


class ColdStructuredDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_busy_and_cancelled_cold_requests_cannot_occupy_local_executor(self):
        # A single local worker is enough for local reads even while cold I/O
        # blocks. Before dedicated dispatch, the second cold request queued here.
        loop = asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=1))
        service, source, rows, manifest = registry(1)
        started, release = Event(), Event()
        def blocked(*args, **kwargs):
            started.set()
            if not release.wait(3):
                raise AssertionError('cold fixture was not released')
            return rows
        source.read_revisions.side_effect = blocked
        app = create_app(Settings(data_mode='pp_live', origin_id='pp-live-pp'),
            store=Mock(predictions=Mock(return_value=[])), history=Mock(),
            structured_history=service, refresh=False)
        first = None
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url='http://test') as client:
                first = asyncio.create_task(client.get('/history/structured/reviewed'))
                for _ in range(100):
                    if started.is_set():
                        break
                    await asyncio.sleep(.005)
                self.assertTrue(started.is_set())
                busy = await asyncio.wait_for(client.get('/history/structured/reviewed'), .5)
                self.assertEqual(busy.status_code, 429)
                for path in ('/history/predictions', '/forecast/current', '/state/current'):
                    self.assertEqual((await asyncio.wait_for(client.get(path), .5)).status_code, 200)
                first.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await first
                self.assertEqual((await asyncio.wait_for(
                    client.get('/history/structured/reviewed'), .5)).status_code, 429)
                self.assertEqual(source.read_revisions.call_count, 1)
                release.set()
                # Wait for worker-owned cleanup, rather than the cancelled HTTP task.
                for _ in range(100):
                    if service._admission.acquire(blocking=False):
                        service._admission.release()
                        break
                    await asyncio.sleep(.005)
                else:
                    self.fail('cold worker did not release its admission')
                service._next_start = float('-inf')
                self.assertEqual((await client.get('/history/structured/reviewed')).status_code, 200)
        finally:
            release.set()
            if first is not None and not first.done():
                first.cancel()
                await asyncio.gather(first, return_exceptions=True)
            await asyncio.to_thread(service.close)


if __name__ == '__main__':
    unittest.main()
