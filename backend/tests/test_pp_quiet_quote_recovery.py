"""Deterministic tests for quiet Polymarket quote recovery."""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.live_diagnostics import SourceHTTPFailure
from postgres.quote_recovery import QuietQuoteRecovery, QuoteFeedSnapshot, RecoveredQuote


class QuietQuoteRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.start = datetime(2026, 11, 27, 20, tzinfo=timezone.utc)
        self.elapsed = 0
        self.market = {
            'market_id': 'first',
            'payload': {'start': self.start.isoformat(),
                        'end': (self.start + timedelta(minutes=15)).isoformat()},
        }
        self.snapshot = QuoteFeedSnapshot(self.market)
        self.quote = {'market_id': 'first', 'payload': {'best_bid': '0.45'},
                      'provenance': {'feed': 'polymarket_us_bbo'}}
        self.fetch = AsyncMock(return_value=self.quote)
        self.published = []
        self.failures = []
        self.recovery = QuietQuoteRecovery(
            lambda: self.snapshot, self.fetch, self.published.append,
            on_failure=self.failures.append, clock=self.clock, monotonic=lambda: self.elapsed,
        )

    def clock(self):
        return self.start + timedelta(seconds=self.elapsed)

    async def test_probes_a_quiet_market_at_threshold_and_respects_cadence(self):
        self.elapsed = 29
        await self.recovery.check()
        self.fetch.assert_not_awaited()
        self.elapsed = 30
        await self.recovery.check()
        self.fetch.assert_awaited_once_with(self.market)
        self.assertEqual(self.published, [RecoveredQuote('first', self.clock(), self.quote)])
        self.elapsed = 53
        await self.recovery.check()
        self.fetch.assert_awaited_once()
        self.elapsed = 54
        await self.recovery.check()
        self.assertEqual(self.fetch.await_count, 2)

    async def test_current_usable_websocket_frame_delays_recovery(self):
        self.elapsed = 60
        self.snapshot = replace(self.snapshot, last_ws_at=self.clock(), ws_revision=1)
        self.elapsed = 89
        await self.recovery.check()
        self.fetch.assert_not_awaited()
        self.elapsed = 90
        await self.recovery.check()
        self.fetch.assert_awaited_once()

    async def test_empty_response_is_published_and_failures_back_off(self):
        self.fetch.side_effect = [
            SourceHTTPFailure(429, 'limited'), SourceHTTPFailure(503, 'unavailable'),
            None,
        ]
        self.elapsed = 30
        await self.recovery.check()
        self.elapsed = 60
        await self.recovery.check()
        self.elapsed = 119
        await self.recovery.check()
        self.assertEqual(self.fetch.await_count, 2)
        self.assertEqual(self.published, [])
        self.assertEqual(self.failures, ['polymarket_bbo.http_429', 'polymarket_bbo.http_5xx'])
        self.elapsed = 120
        await self.recovery.check()
        self.assertEqual(self.published, [RecoveredQuote('first', self.clock(), None)])

    async def test_one_probe_at_a_time_and_new_ws_observation_wins(self):
        fetching = asyncio.Event()
        respond = asyncio.Event()

        async def fetch(_):
            fetching.set()
            await respond.wait()
            return self.quote

        self.fetch.side_effect = fetch
        self.elapsed = 30
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(self.recovery.check())
            await asyncio.wait_for(fetching.wait(), timeout=1)
            await self.recovery.check()
            self.snapshot = replace(self.snapshot, last_ws_at=self.clock(), ws_revision=1)
            respond.set()
        self.fetch.assert_awaited_once()
        self.assertEqual(self.published, [])

    async def test_pause_and_market_end_guard_publication(self):
        self.elapsed = 30
        self.snapshot = replace(self.snapshot, paused=True)
        await self.recovery.check()
        self.fetch.assert_not_awaited()
        self.snapshot = replace(self.snapshot, paused=False)

        async def pause(_):
            self.snapshot = replace(self.snapshot, paused=True)
            return self.quote

        async def expire(_):
            self.elapsed = 900
            return self.quote

        self.fetch.side_effect = pause
        await self.recovery.check()
        self.snapshot = replace(self.snapshot, paused=False)
        self.elapsed = 60
        self.fetch.side_effect = expire
        await self.recovery.check()
        self.assertEqual(self.fetch.await_count, 2)
        self.assertEqual(self.published, [])

    async def test_wrong_market_response_is_a_failure(self):
        self.elapsed = 30
        self.fetch.return_value = {**self.quote, 'market_id': 'wrong'}
        await self.recovery.check()
        self.assertEqual(self.published, [])
        self.assertEqual(self.failures, ['polymarket_bbo.identity_mismatch'])

    async def test_whole_request_deadline_is_bounded(self):
        async def hang(_):
            await asyncio.Event().wait()

        self.fetch.side_effect = hang
        self.recovery.request_deadline = 0
        self.elapsed = 30
        await self.recovery.check()
        self.assertEqual(self.published, [])
        self.assertEqual(self.failures, ['polymarket_bbo.timeout'])
