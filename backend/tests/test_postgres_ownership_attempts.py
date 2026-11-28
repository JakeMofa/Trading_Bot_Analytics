"""Separate native outcomes from delivery delay without logging private input."""
import asyncio
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postgres.live_diagnostics import OwnershipConnectionLimit
from postgres.ownership_probe import OwnershipProbe, is_ownership_check, submit_ownership


class OwnershipAttemptDiagnostics(unittest.IsolatedAsyncioTestCase):
    async def test_capacity_then_true_keeps_each_result_and_delivery_timing(self):
        probe = OwnershipProbe()
        seen = []

        def busy():
            seen.append(is_ownership_check())
            raise OwnershipConnectionLimit('private text must not be logged')

        with self.assertRaises(OwnershipConnectionLimit):
            await submit_ownership(busy, probe)

        def owned():
            seen.append(is_ownership_check())
            return True

        self.assertIs(await submit_ownership(owned, probe), True)
        self.assertFalse(is_ownership_check())
        self.assertEqual(seen, [True, True])
        # A failure report exposes both results even if the latest worker
        # completed: it does not reinterpret cumulative phases as one attempt.
        with self.assertLogs('postgres.ownership_probe', 'WARNING') as logs:
            probe.report('async_deadline')
        doc = json.loads(logs.output[-1].split('pp_ownership_check ', 1)[1])
        self.assertEqual([a['result'] for a in doc['attempts']], ['capacity', 'true'])
        for attempt in doc['attempts']:
            self.assertGreaterEqual(attempt['native_ms'], 0)
            self.assertGreaterEqual(attempt['resume_ms'], 0)
        self.assertNotIn('private text', str(doc))

    async def test_false_and_truthy_non_boolean_are_not_recorded_as_true(self):
        probe = OwnershipProbe()
        self.assertIs(await submit_ownership(lambda: False, probe), False)
        self.assertEqual(await submit_ownership(lambda: 1, probe), 1)
        self.assertEqual([a['result'] for a in probe.attempts], ['false', 'other'])

    def test_attempt_history_is_bounded(self):
        probe = OwnershipProbe()
        for _ in range(3):
            probe.submitted()
        with self.assertRaises(ValueError):
            probe.submitted()


if __name__ == '__main__':
    unittest.main()
