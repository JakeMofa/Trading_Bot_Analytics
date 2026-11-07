import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'prototype'))
import run_legacy_import_qualification as runner

class Tests(unittest.TestCase):
    def test_linux_missing_visibility_holds_before_workspace_preparation(self):
        with patch.object(runner.sys,'platform','linux'),patch.object(runner.os,'geteuid',return_value=1000),patch.object(runner.tempfile,'mkdtemp') as allocate:
            with self.assertRaisesRegex(RuntimeError,'before preparation'):runner.require_descriptor_visibility()
            allocate.assert_not_called()
    def test_existing_root_route_preserves_visibility_requirement(self):
        with patch.object(runner.sys,'platform','linux'),patch.object(runner.os,'geteuid',return_value=0):runner.require_descriptor_visibility()
