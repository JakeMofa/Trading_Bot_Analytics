import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

SPEC=importlib.util.spec_from_file_location('controller_bundle',Path(__file__).parents[1]/'controller_bundle.py')
builder=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(builder)


class BundleTests(unittest.TestCase):
    def test_deterministic_self_contained_package_and_isolated_refusal(self):
        with tempfile.TemporaryDirectory() as folder:
            a,b=Path(folder)/'a.pyz',Path(folder)/'b.pyz'
            self.assertEqual(builder.build(a),builder.build(b))
            with zipfile.ZipFile(a) as archive:
                self.assertEqual(set(archive.namelist()),{'__main__.py','controller.py','linux_actions.py'})
            result=subprocess.run([sys.executable,'-IS',str(a)],cwd=folder,env={},capture_output=True,text=True,timeout=3)
            self.assertEqual(result.returncode,1)
            self.assertIn('entrypoint_precondition_failed',result.stdout)
            self.assertEqual(result.stderr,'')

    def test_existing_qualified_bundle_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'qualified.pyz';path.write_bytes(b'preserve')
            with self.assertRaises(FileExistsError):builder.build(path)
            self.assertEqual(path.read_bytes(),b'preserve')
