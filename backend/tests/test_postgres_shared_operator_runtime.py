"""Native generated PG17 wiring: schema checks, shared roles and shutdown."""
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

from fastapi.testclient import TestClient
from psycopg import OperationalError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import test_postgres_trial07_permit as fixture
from postgres.cloud_origin_binding import DISPLAY_ORIGIN
from postgres.operator_api import create_operator_app
from postgres.operator_runtime import create_runtime
from postgres.shared_read_connection import SharedReadConnection


class SharedOperatorRuntime(unittest.TestCase):
    require_migration_ledger = True
    setup = fixture.Trial07Permit
    setUpClass = setup.__dict__['setUpClass']
    tearDownClass = setup.__dict__['tearDownClass']
    admin = setup.__dict__['admin']

    def test_actual_runtime_keeps_one_reader_across_status_and_closes_at_shutdown(self):
        token = 'generated-test-operator-token-at-least-thirty-two-bytes'
        reader = (os.environ['TRADEBOT_TEST_READER_DSN'] if self.external else
                  f'host={self.socket} user=tradebot_reader dbname=tradebot_pp')
        env = {'TRADEBOT_ENVIRONMENT': 'preprod', 'TRADEBOT_DATA_MODE': 'pp_live',
               'TRADEBOT_ORIGIN_ID': DISPLAY_ORIGIN,
               'TRADEBOT_DATABASE_DSN_FILE': '/run/secrets/lifecycle_dsn',
               'TRADEBOT_OPERATOR_TOKEN_FILE': '/run/secrets/operator_token',
               'TRADEBOT_APP_DSN_FILE': '/run/secrets/app_dsn',
               'TRADEBOT_COLLECTOR_ENABLED': 'false', 'TRADEBOT_PP_LIVE_CONTROL': 'true',
               'TRADEBOT_PP_WINDOW_POLICY': 'benchmark-watch-v1',
               'TRADEBOT_PP_BOUNDARY_INITIAL_A': str(uuid.uuid4())}
        captured = {}

        def app_factory(*args, **kwargs):
            captured.update(kwargs)
            return create_operator_app(*args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in (('lifecycle_dsn', self.lifecycle_dsn),
                                ('app_dsn', self.app_dsn), ('watch_api_reader_dsn', reader),
                                ('operator_token', token)):
                file = root / name
                file.write_text(value)
                file.chmod(0o400)
            with patch('postgres.operator_runtime.create_operator_app', app_factory):
                app = create_runtime(env, secret_dir=root, expected_uid=os.getuid())
        store = captured['feed_store']
        self.assertIsInstance(store.reads, SharedReadConnection)
        producer = store.for_producer(str(uuid.uuid4()))
        self.assertIs(producer.reads, store.reads)

        def backend_pid():
            with producer.connection(True) as db:
                row = db.execute("SELECT pg_backend_pid() AS pid, current_user AS login, "
                                 "current_setting('transaction_read_only') AS mode").fetchone()
            self.assertEqual((row['login'], row['mode']), ('tradebot_reader', 'on'))
            return row['pid']

        pid = backend_pid()
        with TestClient(app) as client:
            for _ in range(4):
                response = client.get('/collector/status',
                                      headers={'Authorization': 'Bearer ' + token})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertFalse(response.json()['collector_enabled'])
                self.assertEqual(backend_pid(), pid)
            with self.admin() as db:
                active = db.execute('SELECT state, xact_start FROM pg_stat_activity '
                                    'WHERE pid=%s', (pid,)).fetchone()
            self.assertEqual(active['state'], 'idle')
            self.assertIsNone(active['xact_start'])
        with self.assertRaises(OperationalError):
            producer.connection(True)
        with self.admin() as db:
            # No retained physical reader remains after application shutdown.
            until = time.monotonic() + 1
            while True:
                db.execute('SELECT pg_stat_clear_snapshot()').fetchone()
                remaining = db.execute('SELECT count(*) AS n FROM pg_stat_activity '
                                       'WHERE pid=%s', (pid,)).fetchone()['n']
                if not remaining or time.monotonic() >= until:
                    break
                time.sleep(.005)
        self.assertEqual(remaining, 0)


if __name__ == '__main__':
    unittest.main()
