"""Private operator surface tests; no network or live-collector activation."""
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.operator_api import create_operator_app


TOKEN = 'fixture-operator-token-at-least-thirty-two-bytes'


class Repository:
    def __init__(self):
        self.calls = []
        self.enabled = True

    def collector_state(self, origin):
        self.calls.append(('status', origin))
        return {'collector_enabled': self.enabled, 'epoch': 3,
                'generation_id': 'generated-id',
                'updated_at': datetime(2026, 11, 16, tzinfo=timezone.utc),
                'initialized': True}

    def disable_collector(self, origin):
        self.calls.append(('off', origin))
        self.enabled = False
        return {'collector_enabled': False, 'epoch': 4}


class OperatorApiTests(unittest.TestCase):
    def setUp(self):
        self.repository = Repository()
        self.client = TestClient(create_operator_app(self.repository,
                                  origin_id='pp-live-fixture', token=TOKEN))
        self.headers = {'Authorization': 'Bearer ' + TOKEN}

    def test_only_authenticated_status_and_off_reach_repository(self):
        for headers in ({}, {'Authorization': 'Bearer wrong'},
                        {'Authorization': 'Basic ' + TOKEN}):
            self.assertEqual(self.client.get('/collector/status', headers=headers).status_code, 401)
            self.assertEqual(self.client.post('/collector/off', headers=headers).status_code, 401)
        self.assertEqual(self.repository.calls, [])
        state = self.client.get('/collector/status', headers=self.headers)
        self.assertEqual(state.status_code, 200)
        self.assertTrue(state.json()['collector_enabled'])
        self.assertTrue(state.json()['initialized'])
        self.assertIsNone(state.json()['process_running'])
        self.assertIsNone(state.json()['session_failure_code'])
        off = self.client.post('/collector/off', headers=self.headers)
        self.assertEqual(off.status_code, 200)
        self.assertFalse(off.json()['collector_enabled'])
        self.assertEqual(self.repository.calls, [('status', 'pp-live-fixture'),
                                                 ('off', 'pp-live-fixture')])

    def test_on_mode_and_docs_are_unavailable(self):
        for path in ('/collector/on', '/mode', '/docs', '/openapi.json'):
            self.assertEqual(self.client.post(path, headers=self.headers).status_code, 404)
        self.assertEqual(self.repository.calls, [])

    def test_reader_shutdown_follows_stop_and_also_runs_after_stop_failure(self):
        for fail in (False, True):
            with self.subTest(stop_fails=fail):
                calls = []

                class Session:
                    async def stop(self):
                        calls.append('stop')
                        if fail:
                            raise RuntimeError('fixture durable stop unavailable')

                app = create_operator_app(self.repository, origin_id='pp-live-fixture',
                                          token=TOKEN, session=Session(),
                                          reader_cleanup=lambda: calls.append('reader-close'))
                if fail:
                    with self.assertRaisesRegex(RuntimeError, 'fixture durable stop'):
                        with TestClient(app):
                            pass
                else:
                    with TestClient(app):
                        pass
                self.assertEqual(calls, ['stop', 'reader-close'])

    def test_explicit_off_keeps_reader_available_for_status_and_later_on(self):
        calls = []
        app = create_operator_app(self.repository, origin_id='pp-live-fixture', token=TOKEN,
                                  reader_cleanup=lambda: calls.append('reader-close'))
        with TestClient(app) as client:
            self.assertEqual(client.post('/collector/off', headers=self.headers).status_code, 200)
            self.assertEqual(client.get('/collector/status', headers=self.headers).status_code, 200)
            self.assertEqual(calls, [])
        self.assertEqual(calls, ['reader-close'])

    def test_bounded_diagnostic_only_on_authenticated_private_status(self):
        class FailedSession:
            def state(self):
                return {'process_running': False, 'failure_code': 'polymarket_bbo.http_404'}
        client = TestClient(create_operator_app(self.repository, origin_id='pp-live-fixture',
                                                token=TOKEN, session=FailedSession()))
        self.assertEqual(client.get('/collector/status').status_code, 401)
        response = client.get('/collector/status', headers=self.headers)
        self.assertEqual(response.json()['session_failure_code'], 'polymarket_bbo.http_404')

    def test_on_is_private_and_reports_acceptance_without_claiming_durable_enable(self):
        class Session:
            def __init__(self):
                self.calls = []
                self.running = False
            def state(self):
                return {'process_running': self.running}
            async def start(self, *, max_seconds):
                self.calls.append(max_seconds)
                self.running = True
                return self.state()
            async def stop(self):
                self.running = False
                return self.state()
        session = Session()
        client = TestClient(create_operator_app(self.repository, origin_id='pp-live-fixture',
                                                token=TOKEN, session=session))
        self.assertEqual(client.post('/collector/on').status_code, 401)
        self.assertEqual(session.calls, [])
        started = client.post('/collector/on?max_seconds=120', headers=self.headers)
        self.assertEqual(started.status_code, 202)
        self.assertEqual(session.calls, [120])
        self.assertNotIn('collector_enabled', started.json())
        self.assertTrue(client.get('/collector/status', headers=self.headers).json()['process_running'])
        stopped = client.post('/collector/off', headers=self.headers)
        self.assertEqual(stopped.status_code, 200)
        self.assertFalse(stopped.json()['process_running'])

    def test_operator_shutdown_requests_durable_stop(self):
        calls = []
        class Session:
            def state(self):
                return {'process_running': False}
            async def stop(self):
                calls.append('off')
                return {'process_running': False}
        with TestClient(create_operator_app(self.repository,
                            origin_id='pp-live-fixture', token=TOKEN, session=Session())):
            pass
        self.assertEqual(calls, ['off'])

    def test_expired_lease_is_reported_off_without_claiming_process_state(self):
        class Expired(Repository):
            def collector_state(self, origin):
                return {**super().collector_state(origin), 'collector_enabled': False,
                        'stored_enabled': True,
                        'collector_lease_expires_at': datetime(2026, 11, 16, tzinfo=timezone.utc)}
        client = TestClient(create_operator_app(Expired(), origin_id='pp-live-fixture', token=TOKEN))
        state = client.get('/collector/status', headers=self.headers)
        self.assertEqual(state.status_code, 200)
        self.assertFalse(state.json()['collector_enabled'])
        self.assertTrue(state.json()['lease_expired'])
        self.assertIsNone(state.json()['process_running'])

    def test_invalid_origin_or_token_fail_at_creation(self):
        for origin in ('generated-pp', 'pp-live-'):
            with self.assertRaises(ValueError):
                create_operator_app(self.repository, origin_id=origin, token=TOKEN)
        for token in ('short', 'x' * 257, 'é' * 40):
            with self.assertRaises(ValueError):
                create_operator_app(self.repository, origin_id='pp-live-fixture', token=token)

    def test_repository_failure_is_unavailable_without_details(self):
        class Broken(Repository):
            def collector_state(self, origin):
                raise RuntimeError('sensitive internal error')
        client = TestClient(create_operator_app(Broken(), origin_id='pp-live-fixture', token=TOKEN))
        response = client.get('/collector/status', headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('sensitive', response.text)


if __name__ == '__main__':
    unittest.main()
