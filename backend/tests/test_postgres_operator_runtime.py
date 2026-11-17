"""Default-off operator runtime secret/role tests; no actual PP access."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.operator_runtime import create_runtime, fence_live_startup


ENV = {'TRADEBOT_ENVIRONMENT': 'preprod', 'TRADEBOT_DATA_MODE': 'pp_live',
       'TRADEBOT_ORIGIN_ID': 'pp-live-fixture',
       'TRADEBOT_DATABASE_DSN_FILE': '/run/secrets/lifecycle_dsn',
       'TRADEBOT_OPERATOR_TOKEN_FILE': '/run/secrets/operator_token',
       'TRADEBOT_COLLECTOR_ENABLED': 'false'}
TOKEN = 'fixture-operator-token-at-least-thirty-two-bytes'


class FakeConnection:
    def __init__(self, login='tradebot_lifecycle'):
        self.login = login

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params=None):
        self.query = query
        return self

    def fetchone(self):
        return {'login': self.login}


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        for name, value in [('lifecycle_dsn', 'postgresql://fake'),
                            ('operator_token', TOKEN)]:
            path = self.root / name
            path.write_text(value)
            path.chmod(0o400)
        self.calls = []

    def connector(self, dsn, *, environment):
        self.calls.append((dsn, environment))
        return FakeConnection()

    def create(self, environ=None, connector=None):
        with patch('postgres.operator_runtime.validate_schema') as validated:
            app = create_runtime(ENV if environ is None else environ,
                                 secret_dir=self.root, expected_uid=os.getuid(),
                                 connector=connector or self.connector)
            validated.assert_called_once()
        return app

    def test_bound_runtime_has_only_private_status_and_off(self):
        app = self.create()
        client = TestClient(app)
        self.assertEqual(client.get('/docs').status_code, 404)
        self.assertEqual(client.post('/collector/on', headers={'Authorization':'Bearer '+TOKEN}).status_code, 404)
        self.assertEqual(client.get('/collector/status').status_code, 401)
        self.assertEqual(self.calls, [('postgresql://fake', 'preprod')])

    def test_wrong_mode_paths_flags_or_role_fail_before_serving(self):
        for change in ({'TRADEBOT_DATA_MODE':'generated'},
                       {'TRADEBOT_ORIGIN_ID':'generated-pp'},
                       {'TRADEBOT_OPERATOR_TOKEN_FILE':'/tmp/token'},
                       {'TRADEBOT_DATABASE_DSN':'credential'},
                       {'ENABLE_OPENAI_ANALYST':'true'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.create({**ENV, **change})
        self.assertEqual(self.calls, [])
        with self.assertRaisesRegex(ValueError, 'lifecycle role'):
            self.create(connector=lambda *_args, **_kw: FakeConnection('tradebot_app'))

    def test_missing_symlink_wrong_owner_mode_and_short_token_fail_closed(self):
        token = self.root / 'operator_token'
        token.chmod(0o644)
        with self.assertRaises(ValueError):
            self.create()
        token.chmod(0o400)
        token.unlink()
        token.symlink_to(self.root / 'lifecycle_dsn')
        with self.assertRaises(OSError):
            self.create()
        token.unlink()
        token.write_text('short')
        token.chmod(0o400)
        with self.assertRaises(ValueError):
            self.create()
        self.assertEqual(self.calls, [])

    def test_unsafe_secret_directory_rejected_before_database_access(self):
        self.root.chmod(0o777)
        with self.assertRaises(ValueError):
            self.create()
        self.assertEqual(self.calls, [])

    def test_live_control_requires_separate_app_secret_and_role(self):
        live = {**ENV, 'TRADEBOT_PP_LIVE_CONTROL': 'true',
                'TRADEBOT_APP_DSN_FILE': '/run/secrets/app_dsn'}
        with self.assertRaises(OSError):
            self.create(live)
        path = self.root / 'app_dsn'
        path.write_text('postgresql://app-fixture')
        path.chmod(0o400)
        with self.assertRaisesRegex(ValueError, 'app role'):
            self.create(live)

        def connector(dsn, *, environment):
            return FakeConnection('tradebot_app' if dsn == 'postgresql://app-fixture'
                                  else 'tradebot_lifecycle')

        class Session:
            def state(self):
                return {'process_running': False}
            async def start(self, *, max_seconds):
                return {'process_running': True}
            async def stop(self):
                return {'process_running': False}

        with patch('postgres.operator_runtime.validate_schema'), \
             patch('postgres.operator_runtime.LifecycleRepository') as repository:
            repository.return_value.collector_state.return_value={
                'initialized':False,'collector_enabled':False}
            app = create_runtime(live, secret_dir=self.root, expected_uid=os.getuid(),
                                 connector=connector,
                                 session_builder=lambda repo, origin, dsn: Session())
            self.assertEqual(repository.return_value.collector_state.call_count,2)
        client = TestClient(app)
        self.assertEqual(client.post('/collector/on').status_code, 401)
        self.assertEqual(client.post('/collector/on',
                          headers={'Authorization':'Bearer '+TOKEN}).status_code, 202)

    def test_live_restart_revokes_prior_lease_before_serving(self):
        class Repository:
            def __init__(self):
                self.enabled=True
                self.stops=0
            def collector_state(self, origin):
                self.asserted_origin=origin
                return {'initialized':True,'collector_enabled':self.enabled,
                        'stored_enabled':self.enabled}
            def disable_collector(self, origin):
                self.stops+=1
                self.enabled=False
                return {'collector_enabled':False}
        repository=Repository()
        fence_live_startup(repository,'pp-live-fixture')
        self.assertEqual((repository.stops,repository.asserted_origin),(1,'pp-live-fixture'))
        fence_live_startup(repository,'pp-live-fixture')
        self.assertEqual(repository.stops,1)
        repository.enabled=True
        repository.disable_collector=lambda _origin:{'collector_enabled':True}
        with self.assertRaisesRegex(ValueError,'durable OFF unproven'):
            fence_live_startup(repository,'pp-live-fixture')


if __name__ == '__main__':
    unittest.main()
