"""The PP observer reports durable receipts without changing feed intake."""
import asyncio
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.live_ingest import polymarket_cycle


class BoundaryTraceTests(unittest.IsolatedAsyncioTestCase):
    async def test_optional_receipt_trace(self):
        market = {'market_id': 'm', 'payload': {'slug': 's', 'start': 'start', 'end': 'end'}}
        quote = {'market_id': 'm', 'event_id': 'q-1', 'received_at': 'receipt',
                 'payload': {'best_bid': '0.25', 'best_ask': None}, 'raw_payload': 'private'}
        store = SimpleNamespace(settings=SimpleNamespace(environment='preprod', data_mode='pp_live',
                                origin_id='pp-live-fixture'), ingest=Mock(return_value={'duplicate': False}))
        logger = 'postgres.boundary_trace'
        for enabled in ('0', '1'):
            with self.subTest(enabled=enabled), patch.dict(os.environ, TRADEBOT_PP_BOUNDARY_TRACE=enabled):
                guard = self.assertLogs(logger, 'WARNING') if enabled == '1' else self.assertNoLogs(logger, 'WARNING')
                with guard as logs:
                    self.assertEqual('m', await polymarket_cycle(store, None, asyncio.Event(),
                                     discover=AsyncMock(return_value=market), fetch=AsyncMock(return_value=quote)))
                if enabled == '1':
                    rows = [json.loads(record.getMessage().removeprefix('pp_boundary_trace ')) for record in logs.records]
                    self.assertEqual(['discovery_start', 'market_identified', 'bbo_received', 'commit_ack'],
                                     [r['stage'] for r in rows])
                    self.assertEqual('q-1', rows[-1]['event_id'])
                    self.assertIsNone(rows[-1]['best_ask'])
                    self.assertFalse(rows[-1]['duplicate'])
                    self.assertNotIn('private', str(rows))
        self.assertEqual(4, store.ingest.call_count)
