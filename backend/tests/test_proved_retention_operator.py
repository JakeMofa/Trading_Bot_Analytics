import json
from pathlib import Path
import subprocess
import sys
import unittest
SCRIPT=Path(__file__).resolve().parents[1]/'run_proved_retention_trial.py'


class ProvedOperatorTests(unittest.TestCase):
    def test_default_does_not_open_database_or_enable_retention(self):
        result=subprocess.run([sys.executable,str(SCRIPT)],capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(result.stdout)['mode'],'plan_only')
    def test_unconfigured_execution_fails_before_any_data_operation(self):
        result=subprocess.run([sys.executable,str(SCRIPT),'--execute'],capture_output=True,text=True)
        self.assertEqual(result.returncode,1)
        self.assertEqual(json.loads(result.stdout)['stage'],'validate_operator')


if __name__=='__main__':unittest.main()
