"""I7 timestamp lookup equivalence and independent discovery/publication."""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from collector import connect
from streaming import initialize, feature_loop, rest_loop, publish_feature_cycle
from live_state import LiveState


class FreshnessTests(unittest.TestCase):
    def test_feature_loop_uses_15_second_cadence_and_does_not_call_rest(self):
        async def exercise(db):
            stop=asyncio.Event(); intervals=[]
            async def pause(stop,seconds):
                intervals.append(seconds);stop.set()
            with patch('streaming.feature_cycle',return_value=None),patch('streaming.rest_cycle') as rest,patch('streaming.pause',side_effect=pause),patch('builtins.print'):
                await feature_loop('unused',db,stop)
                rest.assert_not_called()
            self.assertEqual(intervals,[15])
        db=connect(':memory:');initialize(db)
        try:asyncio.run(exercise(db))
        finally:db.close()

    def state(self, now):
        state=LiveState()
        state.set_market({'id':'m1','slug':'m1','start':(now-timedelta(minutes=1)).isoformat(),
                          'end':(now+timedelta(minutes=1)).isoformat(),'target_usd':'100'})
        return state

    def cycle(self, now, market='m1'):
        return ((market,{'target_usd':'100'},{}),1,now.isoformat(),None)

    def test_publication_requires_active_matching_market_and_fresh_asof(self):
        now=datetime(2026,10,31,12,tzinfo=timezone.utc)
        for age,market,accepted in ((0,'m1',True),(30,'m1',True),(31,'m1',False),(-1,'m1',False),(0,'m2',False)):
            with self.subTest(age=age,market=market):
                state=self.state(now)
                self.assertEqual(publish_feature_cycle(self.cycle(now-timedelta(seconds=age),market),state,now),accepted)
                self.assertEqual(state.snapshot(now)['feature_snapshot'] is not None,accepted)
        state=self.state(now)
        self.assertFalse(publish_feature_cycle(self.cycle(now+timedelta(minutes=1)),state,now+timedelta(minutes=1)))
        state.set_market(None)
        self.assertFalse(publish_feature_cycle(self.cycle(now),state,now))

    def test_discovery_advances_and_no_second_feature_starts_while_worker_waits(self):
        entered,release=threading.Event(),threading.Event()
        calls=[]
        def slow_cycle(path):
            calls.append(threading.get_ident()); entered.set()
            if not release.wait(3):raise AssertionError('test did not release worker')
            return None
        async def exercise(db):
            stop=asyncio.Event(); discovery=asyncio.Event()
            async def pause_loop(stop,seconds):
                # REST keeps iterating while the feature worker is blocked.
                await asyncio.sleep(0)
                if release.is_set():stop.set()
            def sync(db,state):discovery.set()
            with patch('streaming.feature_cycle',side_effect=slow_cycle),patch('streaming.rest_cycle',return_value=[]),patch('streaming.sync_live_market',side_effect=sync),patch('streaming.pause',side_effect=pause_loop),patch('builtins.print'):
                feature=asyncio.create_task(feature_loop('unused',db,stop))
                rest=asyncio.create_task(rest_loop('unused',db,stop,30))
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait,1))
                    discovery.clear()
                    await asyncio.wait_for(discovery.wait(),1)
                    for _ in range(5):await asyncio.sleep(0)
                    self.assertEqual(len(calls),1)
                    self.assertFalse(feature.done())
                finally:
                    release.set();stop.set()
                    await asyncio.wait_for(asyncio.gather(feature,rest),2)
        db=connect(':memory:');initialize(db)
        try:asyncio.run(exercise(db))
        finally:db.close()

    def test_cancellation_drains_single_worker_without_publication(self):
        entered,release=threading.Event(),threading.Event()
        def slow(path):
            entered.set()
            if not release.wait(3):raise AssertionError('worker not drained')
            return None
        async def exercise(db):
            stop=asyncio.Event()
            with patch('streaming.feature_cycle',side_effect=slow),patch('streaming.publish_feature_cycle') as publish,patch('builtins.print'):
                task=asyncio.create_task(feature_loop('unused',db,stop))
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait,1))
                    task.cancel()
                    for _ in range(3):await asyncio.sleep(0)
                    self.assertFalse(task.done())
                    task.cancel()
                    for _ in range(3):await asyncio.sleep(0)
                    self.assertFalse(task.done())
                finally:
                    release.set()
                    with self.assertRaises(asyncio.CancelledError):await asyncio.wait_for(task,2)
                publish.assert_not_called()
        db=connect(':memory:');initialize(db)
        try:asyncio.run(exercise(db))
        finally:db.close()


if __name__=='__main__':unittest.main()
