import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'prototype'))
from continuous_budget import proposal,GIB
class Tests(unittest.TestCase):
    def test_all_files_count_once_and_target_does_not_silently_change_runtime(self):
        report=proposal()
        self.assertEqual(report['parts_total_bytes'],sum(report['parts_bytes'].values()))
        self.assertEqual(report['parts_bytes']['A_main_WAL_SHM']+report['parts_bytes']['B_main_WAL_SHM'],10*GIB)
        self.assertFalse(report['production_authorized']);self.assertFalse(report['full_profile_runtime_supported'])
        self.assertGreater(report['qualification_resource_gap']['workspace_shortfall_bytes'],19*GIB)
        self.assertLess(report['extrapolations_not_qualification']['active_window_at_trigger_seconds'],72*3600)
        self.assertIsNone(report['temporary_recovery']['production_runway_seconds'])
    def test_larger_retained_file_is_never_credited_as_free_space(self):
        self.assertEqual(proposal(6*GIB)['parts_total_bytes']-proposal(5*GIB)['parts_total_bytes'],GIB)
        with self.assertRaises(ValueError):proposal(-1)
