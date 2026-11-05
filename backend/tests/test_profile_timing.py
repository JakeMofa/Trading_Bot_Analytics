import asyncio,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'prototype'))
from profile_timing import Heartbeat,Timeline

class Clock:
    def __init__(self):self.now=0.
    def time(self):return self.now
    def select(self,timeout=None):
        if timeout is not None and timeout>0:self.now+=timeout
        return []
    def block(self,seconds):self.now+=seconds

class Tests(unittest.TestCase):
    def mechanism(self,fair):
        clock=Clock();loop=asyncio.new_event_loop()
        async def run():
            trace=Timeline(clock.time);beat=Heartbeat(trace,clock=clock.time);await beat.start()
            for i in range(4):
                trace.call('save',clock.block,.4,index=i)
                if fair:await beat.yield_due()
                else:await asyncio.sleep(0)
            await beat.close();return beat.maximum,beat.report()
        try:
            with patch.object(loop,'time',clock.time),patch.object(loop._selector,'select',clock.select):return loop.run_until_complete(run())
        finally:loop.close()
    def test_zero_yield_can_combine_subsecond_saves_past_one_second(self):
        maximum,report=self.mechanism(False)
        self.assertGreaterEqual(maximum,1.19)
        self.assertTrue(all(e['wall_seconds']<1 for w in report['worst_windows'] for e in w['events']))
        self.assertGreaterEqual(report['worst_windows'][0]['main_sync_overlap_seconds'],1.19)
    def test_overdue_handoff_preserves_same_work_and_one_second_gate_without_pacing(self):
        maximum,report=self.mechanism(True)
        self.assertLess(maximum,1)
        self.assertEqual(report['timing_calls'],4)
        self.assertGreater(report['due_timer_handoffs'],0)
        self.assertAlmostEqual(report['handoff_seconds'],0.)
    def test_diagnostics_contain_no_operation_return_payload(self):
        trace=Timeline();trace.call('save',lambda:'generated-secret-payload')
        self.assertNotIn('generated-secret-payload',str(list(trace.events)))
