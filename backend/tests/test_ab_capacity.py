import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'prototype'))
from capacity import proposal,GIB,MIB
class Tests(unittest.TestCase):
    def test_144h_aggregate_legacy_and_filesystem_not_hidden(self):
        p=proposal(5323907072,45171712,49807597568,{'wal_peak_bytes':{'core':4148872}})
        self.assertEqual(p['normal_ceiling_bytes'],16*GIB)
        self.assertEqual(p['migration_ceiling_bytes'],21*GIB)
        self.assertEqual(p['components']['raw_144h_estimate_bytes'],10616832000)
        self.assertGreater(p['components']['retained_legacy_bytes'],5*GIB)
        self.assertTrue(p['filesystem_arithmetic_pass']);self.assertEqual(p['result'],'NOT_PROVEN')
        self.assertEqual(p['blocked_retirement_extra_raw_slots'],0)
    def test_working_space_and_low_filesystem_fail_arithmetic(self):
        p=proposal(5323907072,45171712,10*GIB,{})
        self.assertFalse(p['filesystem_arithmetic_pass']);self.assertEqual(p['result'],'NOT_PROVEN')
        self.assertGreaterEqual(p['components']['archive_TEMP_filesystem_allowance_bytes'],128*MIB)
