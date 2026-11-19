"""Generated storage is explicitly selected and cannot alias live sync."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from postgres.generated_storage import requested,drain,HEADROOM
from postgres.lifecycle import LifecycleHold
from postgres.store import StorageHold
from postgres.acceptance import qualify


class GeneratedStorageTests(unittest.TestCase):
    def test_selection_rejects_live_replay_foreign_origin_and_malformed(self):
        self.assertFalse(requested({},'generated','generated-pp'))
        self.assertTrue(requested({'TRADEBOT_GENERATED_LOCAL_STORAGE':'true'},'generated','generated-pp'))
        for mode,origin,value in [('pp_live','pp-live-pp','true'),('replay','generated-pp','true'),
                ('generated','generated-other','true'),('generated','generated-pp','TRUE')]:
            with self.assertRaises(LifecycleHold):
                requested({'TRADEBOT_GENERATED_LOCAL_STORAGE':value},mode,origin)

    def test_pending_cap_cannot_be_raised_for_generated_drain(self):
        for cap in (9999,10001):
            with self.assertRaises(LifecycleHold):
                drain(SimpleNamespace(environment='preprod',pending_outbox_limit=cap))
        self.assertEqual(HEADROOM,128)

    def test_acceptance_refuses_full_queue_before_seeding_or_http(self):
        store=Mock()
        store.require_generated_headroom.side_effect=StorageHold('pending bound')
        settings=SimpleNamespace(data_mode='generated',origin_id='generated-pp')
        with (patch('postgres.acceptance.Settings.from_env',return_value=settings),
              patch('postgres.acceptance.Store',return_value=store),
              patch('postgres.acceptance.generated_events') as events,
              patch('postgres.acceptance.httpx.Client') as http):
            with self.assertRaises(StorageHold):qualify('http://api:8000')
            events.assert_not_called();http.assert_not_called();store.ingest.assert_not_called()
