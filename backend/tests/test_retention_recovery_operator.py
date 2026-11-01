import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
spec=importlib.util.spec_from_file_location('recovery_operator',Path(__file__).resolve().parents[1]/'prepare_retention_recovery.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class RecoveryOperatorTests(unittest.TestCase):
    def test_default_is_plan_only(self):
        result=subprocess.run([sys.executable,str(Path(module.__file__))],capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(result.stdout)['mode'],'plan_only')
    def test_invalid_execution_reports_safe_stage_without_environment_values(self):
        env=dict(os.environ,OPENAI_API_KEY='synthetic_do_not_log_this_value')
        result=subprocess.run([sys.executable,str(Path(module.__file__)),'--execute-read-only'],
                              capture_output=True,text=True,env=env)
        self.assertEqual(result.returncode,1)
        value=json.loads(result.stdout)
        self.assertEqual(value['status'],'STOP');self.assertEqual(value['stage'],'validate_operator')
        self.assertNotIn('synthetic_do_not_log_this_value',result.stdout+result.stderr)

    def test_private_proof_is_immutable_and_world_unreadable(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'proof.json';sha=module.private_save(p,{'records':[{'id':1}]})
            self.assertEqual(len(sha),64);self.assertEqual(p.stat().st_mode&0o777,0o600)
            with self.assertRaises(FileExistsError):module.private_save(p,{'records':[]})
            self.assertEqual(json.loads(p.read_text())['records'],[{'id':1}])
            self.assertEqual([x.name for x in Path(folder).iterdir()],['proof.json'])
    def test_public_directory_cannot_store_raw_proof(self):
        with tempfile.TemporaryDirectory() as folder:
            os.chmod(folder,0o755)
            with self.assertRaises(ValueError):module.private_save(Path(folder)/'proof.json',{})


if __name__=='__main__':unittest.main()
