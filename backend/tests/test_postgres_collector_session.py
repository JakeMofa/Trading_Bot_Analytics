"""Generated activation-boundary tests; no live source or host mutation."""
import asyncio
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.collector_session import run_session
from postgres.live_supervisor import CollectorHold


class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_bad_owner_never_enables_or_starts_sources(self):
        calls = []
        def enable():
            calls.append('enable')
            return {'collector_enabled': True}
        def disable():
            calls.append('off')
            return {'collector_enabled': False}
        async def supervisor(*args, **kwargs):
            self.fail('sources started')
        with self.assertRaises(CollectorHold):
            await run_session(None, None, asyncio.Event(), owner_check=lambda: False,
                              enable_collector=enable, disable_collector=disable,
                              max_seconds=60, supervisor=supervisor)
        self.assertEqual(calls, ['off'])

    async def test_ambiguous_enable_still_requires_off(self):
        calls = []
        def enable():
            calls.append('enable')
            return None
        def disable():
            calls.append('off')
            return {'collector_enabled': False}
        with self.assertRaisesRegex(CollectorHold, 'enable unproven'):
            await run_session(None, None, asyncio.Event(), owner_check=lambda: True,
                              enable_collector=enable, disable_collector=disable,
                              max_seconds=60)
        self.assertEqual(calls, ['enable', 'off'])

    async def test_owner_lost_after_enable_prevents_source_start(self):
        calls = []
        def owner():
            calls.append('owner')
            return len(calls) == 1
        def enable():
            calls.append('enable')
            return {'collector_enabled': True}
        def disable():
            calls.append('off')
            return {'collector_enabled': False}
        with self.assertRaisesRegex(CollectorHold, 'lost during activation'):
            await run_session(None, None, asyncio.Event(), owner_check=owner,
                              enable_collector=enable, disable_collector=disable,
                              max_seconds=60)
        self.assertEqual(calls, ['owner', 'enable', 'owner', 'off'])

    async def test_normal_session_and_failure_both_end_off(self):
        calls = []
        def enable():
            calls.append('enable')
            return {'collector_enabled': True}
        def disable():
            calls.append('off')
            return {'collector_enabled': False}
        async def supervisor(*args, **kwargs):
            calls.append('supervisor')
            return 'stopped'
        result = await run_session(None, None, asyncio.Event(), owner_check=lambda: True,
                                   enable_collector=enable, disable_collector=disable,
                                   max_seconds=60, supervisor=supervisor)
        self.assertEqual(result, 'stopped')
        self.assertEqual(calls, ['enable', 'supervisor', 'off'])
        async def failed(*args, **kwargs):
            raise RuntimeError('source failed')
        with self.assertRaisesRegex(RuntimeError, 'source failed'):
            await run_session(None, None, asyncio.Event(), owner_check=lambda: True,
                              enable_collector=enable, disable_collector=disable,
                              max_seconds=60, supervisor=failed)
        self.assertEqual(calls[-2:], ['enable', 'off'])

    async def test_unproven_off_cannot_return_success(self):
        async def supervisor(*args, **kwargs):
            return 'stopped'
        with self.assertRaisesRegex(CollectorHold, 'stop unproven'):
            await run_session(None, None, asyncio.Event(), owner_check=lambda: True,
                              enable_collector=lambda: {'collector_enabled': True},
                              disable_collector=lambda: None,
                              max_seconds=60, supervisor=supervisor)

    async def test_cancelled_session_commits_off(self):
        entered = asyncio.Event()
        calls = []
        async def supervisor(*args, **kwargs):
            entered.set()
            await asyncio.Event().wait()
        def disable():
            calls.append('off')
            return {'collector_enabled': False}
        task = asyncio.create_task(run_session(
            None, None, asyncio.Event(), owner_check=lambda: True,
            enable_collector=lambda: {'collector_enabled': True},
            disable_collector=disable, max_seconds=60, supervisor=supervisor))
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(calls, ['off'])


if __name__ == '__main__':
    unittest.main()
