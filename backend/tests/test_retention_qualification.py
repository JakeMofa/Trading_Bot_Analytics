"""Linux harness self-test uses tiny generated data, not a production R5 pass."""
import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import unittest
import tempfile


class QualificationHarnessTests(unittest.TestCase):
    def test_production_guard_identifies_feed_or_collector_without_raw_body(self):
        from datetime import datetime,timezone
        backend=Path(__file__).resolve().parents[1]
        spec=importlib.util.spec_from_file_location('qualification_projection',backend/'qualify_retention_sql.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        now=datetime(2026,10,31,tzinfo=timezone.utc)
        health={'collector':{'running':True},'feeds':{name:{'status':'live','last_data_at':now.isoformat()}
                for name in ('coinbase_stream','polymarket_stream')},'private_fixture':'must not escape'}
        self.assertTrue(module.require_production_health(health,now)['collector_running'])
        health['feeds']['polymarket_stream']['status']='stale'
        with self.assertRaises(module.ProductionGuardStop) as caught:
            module.require_production_health(health,now)
        self.assertEqual(caught.exception.reason,'production_feed_not_fresh_live:polymarket_stream')
        self.assertNotIn('private_fixture',caught.exception.projection)
        health['collector']['running']=False
        with self.assertRaises(module.ProductionGuardStop) as caught:
            module.require_production_health(health,now)
        self.assertEqual(caught.exception.reason,'production_collector_stopped')

    def test_actor_rejects_existing_production_paths_and_symlinks(self):
        backend=Path(__file__).resolve().parents[1]
        spec=importlib.util.spec_from_file_location('qualification_guard',backend/'qualify_retention_sql.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(prefix='generated-retention-') as folder:
            path=Path(folder)/'fixture.db';path.touch()
            module.validate_fixture_path(path)
            with self.assertRaises(ValueError):module.validate_fixture_path(Path('/opt/tradebot/data/btc_intelligence.db'))
            with self.assertRaises(ValueError):module.validate_fixture_path(Path(folder)/'other.db')
            path.unlink();path.symlink_to('/opt/tradebot/data/btc_intelligence.db')
            with self.assertRaises(ValueError):module.validate_fixture_path(path)

    @unittest.skipUnless(sys.platform=='linux','Linux qualification harness')
    def test_three_tiny_complete_trials_and_actual_save_ordering(self):
        backend=Path(__file__).resolve().parents[1]
        result=subprocess.run([sys.executable,str(backend/'qualify_retention_sql.py'),
            '--deployed-app',str(backend/'app'),'--candidate',str(backend/'app/retention.py'),
            '--observations','100','--stream-events','100'],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        rows=[json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(rows),3)
        one=subprocess.run([sys.executable,str(backend/'qualify_retention_sql.py'),
            '--deployed-app',str(backend/'app'),'--candidate',str(backend/'app/retention.py'),
            '--observations','100','--stream-events','100','--trials','1'],capture_output=True,text=True,timeout=10)
        self.assertEqual(one.returncode,0,one.stdout+one.stderr)
        self.assertEqual(len(one.stdout.splitlines()),1)
        for row in rows:
            self.assertEqual(row['status'],'PASS',row)
            self.assertEqual(row['collector']['saves'],row['collector']['ram_updates'])
            self.assertLess(row['max_write_lock_seconds'],.5)


if __name__=='__main__':unittest.main()
