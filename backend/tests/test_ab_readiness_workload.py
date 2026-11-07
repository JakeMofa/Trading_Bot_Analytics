import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'prototype'))
from readiness_workload import plan,GIB
class Tests(unittest.TestCase):
    def test_fixed_shapes_include_overlap_and_do_not_promote_proposed_caps(self):
        p=plan();self.assertEqual(p['result'],'NOT_PROVEN')
        self.assertTrue(p['current_2GiB_limit_cannot_fit'])
        self.assertTrue(p['proposed_workspace_fits_assumptions'])
        self.assertGreater(p['parts_bytes']['legacy'],5*GIB)
        self.assertIsNone(p['normal_production_ceiling']);self.assertIsNone(p['migration_production_ceiling'])
        self.assertEqual(p['spec']['embedded_reference_cardinality'],'UNKNOWN_DO_NOT_FABRICATE')
    def test_no_per_generation_cap_or_hidden_ledger(self):
        p=plan();self.assertGreater(p['parts_bytes']['core_ledger_assumed'],6*GIB)
        self.assertEqual(p['spec']['requested_workspace_bytes'],40*GIB)
        self.assertEqual(p['spec']['requested_wall_seconds'],172800)
        self.assertEqual(p['spec']['max_processes'],3)
        self.assertEqual(p['spec']['required_host_available_memory_bytes'],2*GIB)
