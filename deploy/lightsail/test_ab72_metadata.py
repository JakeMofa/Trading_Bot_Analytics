import sys,sqlite3,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from ab72_metadata import inspect
class Tests(unittest.TestCase):
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
