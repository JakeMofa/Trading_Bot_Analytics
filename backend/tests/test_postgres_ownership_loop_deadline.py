"""Offline regressions for a delayed event loop and database-only tooling."""
import asyncio
from pathlib import Path
import subprocess
import sys
import textwrap
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from postgres.live_diagnostics import LiveDiagnostic
from postgres.live_supervisor import run_bounded


class OwnershipLoopDeadline(unittest.IsolatedAsyncioTestCase):
    async def test_completed_native_true_delivered_after_deadline_cannot_open_sources(self):
        # A completion callback scheduled before the awaiting task can block the
        # loop until after its deadline. The native DB read itself is fast.
        native_results = []
        wrap = asyncio.wrap_future

        def bridge_with_stall(future, **kwargs):
            bridged = wrap(future, **kwargs)
            if not native_results:
                def delay_consumer(completed):
                    native_results.append(completed.result())
                    time.sleep(2.10)
                bridged.add_done_callback(delay_consumer)
            return bridged

        store = SimpleNamespace(settings=SimpleNamespace(
            environment='preprod', data_mode='pp_live', origin_id='pp-live-generated-late-delivery'))
        source = AsyncMock()
        disable = Mock(return_value={'collector_enabled': False})
        with patch('postgres.ownership_probe.asyncio.wrap_future', bridge_with_stall), \
             self.assertLogs('postgres.ownership_probe', 'WARNING') as logs:
            with self.assertRaises(LiveDiagnostic) as caught:
                await run_bounded(store, None, asyncio.Event(), owner_check=lambda: True,
                                  disable_collector=disable, max_seconds=4,
                                  coinbase=source, market=source, candles=source)
        self.assertEqual(caught.exception.code, 'ownership.timeout')
        self.assertEqual(native_results, [True])
        self.assertTrue(any('"outcome":"async_deadline"' in line for line in logs.output))
        source.assert_not_awaited()
        disable.assert_called_once_with()


class DatabaseOnlyImport(unittest.TestCase):
    def test_generic_connection_avoids_vendor_clients_and_private_executor(self):
        script = textwrap.dedent("""
            import sys
            from unittest.mock import Mock, patch
            sys.path.insert(0, sys.argv[1])
            from postgres.connection import connect
            db = Mock()
            with patch('postgres.connection.validate_environment'), \\
                 patch('concurrent.futures.ThreadPoolExecutor',
                       side_effect=AssertionError('database-only caller constructed a worker')):
                assert connect('fixture', factory=lambda *args, **kwargs: db) is db
            assert 'postgres.live_diagnostics' not in sys.modules
            assert 'httpx' not in sys.modules and 'websockets' not in sys.modules
        """)
        child = subprocess.run([sys.executable, '-I', '-c', script, str(BACKEND)],
                               capture_output=True, text=True, timeout=15)
        self.assertEqual(child.returncode, 0, child.stderr)
