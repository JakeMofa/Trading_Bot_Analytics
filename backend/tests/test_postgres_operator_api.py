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
                'updated_at': datetime(2026, 11, 16, tzinfo=timezone.utc)}

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
        self.assertIsNone(state.json()['process_running'])
        off = self.client.post('/collector/off', headers=self.headers)
        self.assertEqual(off.status_code, 200)
        self.assertFalse(off.json()['collector_enabled'])
        self.assertEqual(self.repository.calls, [('status', 'pp-live-fixture'),
                                                 ('off', 'pp-live-fixture')])

    def test_on_mode_and_docs_are_unavailable(self):
        for path in ('/collector/on', '/mode', '/docs', '/openapi.json'):
            self.assertEqual(self.client.post(path, headers=self.headers).status_code, 404)
        self.assertEqual(self.repository.calls, [])

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
