"""Execute the release SQL against a disposable PostgreSQL temp relation."""
import json
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller import DeploymentHold
from linux_actions import LinuxActions


@unittest.skipUnless(all(os.getenv(key) for key in ('TRADEBOT_TEST_HISTORY_V2_DSN',
    'TRADEBOT_TEST_READER_DSN')), 'isolated PostgreSQL admin and reader required')
class LifetimeInventoryTests(unittest.TestCase):
    def test_synced_history_pending_limit_and_recovery_digest(self):
        import psycopg
        with psycopg.connect(os.environ['TRADEBOT_TEST_HISTORY_V2_DSN']) as db:
            db.execute("""CREATE TEMP TABLE inventory_fixture AS SELECT
                       n::bigint AS id, 'pp-live-pp'::text AS origin_id,
                       n::text AS payload, n::text AS event_id, 'feed' AS source, 'gen' AS generation_id, 'hash' AS content_hash, CASE WHEN n<=10100 THEN now() END AS acknowledged_at
                       FROM generate_series(1,10103) n""")
            class FixtureActions(LinuxActions):
                def _sql(self, budget, query):
                    value = db.execute(query.replace('ops.outbox', 'pg_temp.inventory_fixture').replace('raw.events','pg_temp.inventory_fixture')).fetchone()[0]
                    if isinstance(value, bool):
                        return 't' if value else 'f'
                    return json.dumps(value)
                def _reader_sql(self, budget, query):
                    # The outbox fixture uses the admin session's temp table;
                    # generated-storage preservation uses its real reader ACL.
                    with psycopg.connect(os.environ['TRADEBOT_TEST_READER_DSN'],connect_timeout=5,
                                         options='-c default_transaction_read_only=on') as reader:
                        identity=reader.execute("SELECT current_user,current_setting('transaction_read_only')").fetchone()
                        if identity!=('tradebot_reader','on'):
                            raise AssertionError('inventory fixture reader identity/read-only mismatch')
                        value=reader.execute(query).fetchone()[0]
                    return ('t' if value else 'f') if isinstance(value,bool) else json.dumps(value)
            actions = FixtureActions()
            actions._outbox_release_preflight(None)
            initial_inventory = actions._inventory(None)
            self.assertEqual(initial_inventory['raw.events']['count'], 10103)
            db.execute("UPDATE inventory_fixture SET event_id='altered' WHERE id=10102")
            self.assertNotEqual(actions._inventory(None)['raw.events'], initial_inventory['raw.events'])
            initial = actions._ack_state(None)
            self.assertEqual(initial['pp-live-pp']['count'], 10103)
            self.assertEqual(initial['pp-live-pp']['pending'], 3)
            db.execute("UPDATE inventory_fixture SET payload='changed' WHERE id=10001")
            self.assertNotEqual(initial, actions._ack_state(None))
            db.execute("UPDATE inventory_fixture SET payload=id::text WHERE id=10001")
            self.assertEqual(initial, actions._ack_state(None))
            db.execute("UPDATE inventory_fixture SET acknowledged_at=NULL WHERE id>100")
            with self.assertRaises(DeploymentHold):
                actions._outbox_release_preflight(None)
            with self.assertRaises(DeploymentHold):
                actions._ack_state(None)
