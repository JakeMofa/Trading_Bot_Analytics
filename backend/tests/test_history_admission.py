"""Exercise history admission with real background threads and gated fixture reads."""
import asyncio
from pathlib import Path
import sys
from threading import Event
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.history import HistoryError
from postgres.market_history import MarketHistory
from postgres.prediction_history import PredictionHistory


class HistoryAdmissionTests(unittest.IsolatedAsyncioTestCase):
    async def start_read(self, reader):
        """Hold a worker until the test releases it, even if its caller cancels."""
        loop = asyncio.get_running_loop()
        started = asyncio.Event()
        released = asyncio.Event()
        finish = Event()

        def read():
            loop.call_soon_threadsafe(started.set)
            if not finish.wait(5):
                raise TimeoutError('history fixture was not released')
            return 'page'

        release_slot = reader.slot.release

        def notify_release():
            release_slot()
            released.set()

        self.enterContext(patch.object(reader, '_read', side_effect=read))
        self.enterContext(patch.object(reader.slot, 'release', side_effect=notify_release))
        self.addCleanup(finish.set)
        request = asyncio.create_task(reader.read_async())
        await asyncio.wait_for(started.wait(), timeout=5)
        return request, finish, released

    async def test_same_reader_rejects_concurrent_requests(self):
        reader = MarketHistory(None)
        request, finish, _ = await self.start_read(reader)
        with self.assertRaises(HistoryError) as error:
            await reader.read_async()
        self.assertEqual(error.exception.code, 'history_busy')
        with self.assertRaises(HistoryError) as error:
            reader.read()
        self.assertEqual(error.exception.code, 'history_busy')
        finish.set()
        self.assertEqual(await request, 'page')

    async def test_cancelled_caller_leaves_slot_held_until_worker_finishes(self):
        reader = PredictionHistory(None)
        request, finish, released = await self.start_read(reader)
        request.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await request
        with self.assertRaises(HistoryError) as error:
            await reader.read_async()
        self.assertEqual(error.exception.code, 'history_busy')
        self.assertFalse(released.is_set())

        finish.set()
        await asyncio.wait_for(released.wait(), timeout=5)
        self.assertEqual(await reader.read_async(), 'page')

    async def test_market_and_prediction_readers_can_run_at_the_same_time(self):
        market, finish_market, _ = await self.start_read(MarketHistory(None))
        predictions, finish_predictions, _ = await self.start_read(PredictionHistory(None))
        self.assertFalse(market.done())
        self.assertFalse(predictions.done())

        finish_predictions.set()
        self.assertEqual(await predictions, 'page')
        self.assertFalse(market.done())
        finish_market.set()
        self.assertEqual(await market, 'page')
