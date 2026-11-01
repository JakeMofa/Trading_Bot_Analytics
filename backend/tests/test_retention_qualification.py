"""Linux harness self-test uses tiny generated data, not a production R5 pass."""
import json
from pathlib import Path
import subprocess
import sys
import unittest


class QualificationHarnessTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform=='linux','Linux qualification harness')
    def test_three_tiny_complete_trials_and_actual_save_ordering(self):
        backend=Path(__file__).resolve().parents[1]
        result=subprocess.run([sys.executable,str(backend/'qualify_retention_sql.py'),
            '--deployed-app',str(backend/'app'),'--candidate',str(backend/'app/retention.py'),
            '--observations','100','--stream-events','100'],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        rows=[json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(rows),3)
        for row in rows:
            self.assertEqual(row['status'],'PASS',row)
            self.assertEqual(row['collector']['saves'],row['collector']['ram_updates'])
            self.assertLess(row['max_write_lock_seconds'],.5)


if __name__=='__main__':unittest.main()
