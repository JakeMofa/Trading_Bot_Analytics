"""Generated PP task-ownership tests; no network or host activation."""
import asyncio
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.operator_session import OperatorSession, SessionBusy, SessionStopUnproven


class OperatorSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_session_and_explicit_stop(self):
        started = asyncio.Event()
        calls = []
        async def run(stop, seconds):
            calls.append(('run', seconds))
            started.set()
            await stop.wait()
        def off():
            calls.append(('off',))
            return {'collector_enabled': False}
        control = OperatorSession(run, off)
        self.assertTrue((await control.start(max_seconds=60))['process_running'])
        await started.wait()
        with self.assertRaises(SessionBusy):
            await control.start(max_seconds=60)
        self.assertFalse((await control.stop())['process_running'])
        self.assertEqual(calls, [('run', 60), ('off',), ('off',)])
        self.assertTrue((await control.start(max_seconds=30))['process_running'])
        await control.stop()

    async def test_failed_run_requires_explicit_off_before_restart(self):
        entered = asyncio.Event()
        async def failed(stop, seconds):
            entered.set()
            raise RuntimeError('source failed')
        control = OperatorSession(failed, lambda: {'collector_enabled': False})
        await control.start(max_seconds=5)
        await entered.wait()
        await asyncio.wait_for(control._task, 2)
        self.assertEqual(control.state()['last_error'], 'session_failed_or_cancelled')
        with self.assertRaises(SessionStopUnproven):
            await control.start(max_seconds=5)
        await control.stop()
        self.assertIsNone(control.state()['last_error'])

    async def test_unproven_off_blocks_restart(self):
        entered = asyncio.Event()
        async def run(stop, seconds):
            entered.set()
            await stop.wait()
        control = OperatorSession(run, lambda: None)
        await control.start(max_seconds=5)
        await entered.wait()
        with self.assertRaises(SessionStopUnproven):
            await control.stop()
        with self.assertRaises(SessionStopUnproven):
            await control.start(max_seconds=5)

    async def test_invalid_deadlines_never_start(self):
        control = OperatorSession(lambda *_: None, lambda: {'collector_enabled': False})
        for value in (0, 1801, True, 1.5):
            with self.assertRaises(ValueError):
                await control.start(max_seconds=value)
        self.assertFalse(control.state()['process_running'])


if __name__ == '__main__':
    unittest.main()
