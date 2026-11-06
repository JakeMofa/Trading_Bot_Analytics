import sys,sqlite3,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from ab72_metadata import inspect,recovery_capacity
class Tests(unittest.TestCase):
    def test_capacity_review_counts_every_retained_byte_and_never_authorizes(self):
        roles=['tradebot-api','tradebot-ensemble','tradebot-lifecycle']
        source={'status':'PASS_READ_ONLY_METADATA','sqlite_opened':False,'at_utc':'2026-11-06T00:00:00Z',
                'allocation':{'sampled_total_bytes':5369188352,'owner_scope':'bound Linux service roots and descendants','bound_service_roles':roles},'filesystem_available_bytes':49795989504,'mem_available_bytes':1379188736}
        result=recovery_capacity(source)
        self.assertEqual(result['required_sum_bytes'],8053542912)
        self.assertEqual(result['quota_margin_bytes'],536391680)
        self.assertTrue(result['quota_arithmetic_fits']);self.assertTrue(result['filesystem_floor_fits'])
        self.assertLess(result['normal_5120mib_remaining_bytes'],0)
        self.assertFalse(result['production_authorized']);self.assertEqual(result['peak_and_write_overrun'],'NOT_PROVEN')
        source['allocation']['sampled_total_bytes']=8*1024**3
        self.assertFalse(recovery_capacity(source)['quota_arithmetic_fits'])
        source['allocation']['bound_service_roles']=roles[:2]
        with self.assertRaises(ValueError):recovery_capacity(source)

    def test_metadata_never_returns_raw_payload_or_fabricated_cardinality(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'generated.db';db=sqlite3.connect(p)
            db.execute('CREATE TABLE observations(id INTEGER PRIMARY KEY,payload TEXT)')
            db.execute("INSERT INTO observations VALUES(671248,'PRIVATE_SENTINEL')");db.commit();db.close()
            result=inspect(p)
            self.assertEqual(result['exact_cardinalities'],'NOT_PROVEN')
            self.assertNotIn('PRIVATE_SENTINEL',str(result));self.assertEqual(result['geometry']['freelist_count'],0)
    def test_rejects_symlink_and_unbounded_budget(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'link';p.symlink_to(Path(root)/'absent')
            with self.assertRaises(ValueError):inspect(p)
            with self.assertRaises(ValueError):inspect(p,6)
