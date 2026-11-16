"""Generated fail-closed PP live write-fence tests, without a database."""
from contextlib import contextmanager
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.live_contract import coinbase_ticker
from postgres.store import StorageHold, Store


class FakeConnection:
    def __init__(self):
        self.statements = []

    def execute(self, statement, _params):
        self.statements.append(statement)
        return self

    def fetchone(self):
        return {'generation_id': '00000000-0000-4000-8000-000000000001',
                'state': 'collecting', 'collector_enabled': False}


class LiveWriteFenceTests(unittest.TestCase):
    def test_disabled_durable_collector_rejects_before_raw_write(self):
        event = coinbase_ticker({'type': 'ticker', 'product_id': 'BTC-USD', 'trade_id': 12,
                                 'time': '2026-11-15T12:05:00Z', 'price': '100000.001'},
                                '2026-11-15T12:05:01Z')
        store = Store(SimpleNamespace(origin_id='pp-live-test', data_mode='pp_live'))
        connection = FakeConnection()
        @contextmanager
        def connected(_readonly=False):
            yield connection
        store.connection = connected
        with self.assertRaisesRegex(StorageHold, 'durably disabled'):
            store.ingest(event)
        self.assertEqual(len(connection.statements), 1)
        self.assertIn('collector_enabled', connection.statements[0])

    def test_wrong_mode_rejects_before_connection(self):
        event = coinbase_ticker({'type': 'ticker', 'product_id': 'BTC-USD', 'trade_id': 12,
                                 'time': '2026-11-15T12:05:00Z', 'price': '100000.001'},
                                '2026-11-15T12:05:01Z')
        store = Store(SimpleNamespace(origin_id='generated-pp', data_mode='generated'))
        store.connection = lambda *_args: self.fail('wrong-mode event reached database')
        with self.assertRaisesRegex(ValueError, 'data_mode'):
            store.ingest(event)


if __name__ == '__main__':
    unittest.main()
