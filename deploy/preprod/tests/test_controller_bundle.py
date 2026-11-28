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
                self.assertEqual(set(archive.namelist()),{'__main__.py','controller.py','linux_actions.py','outbox_inventory.py','metadata_inventory.py',
                    'live_profile.py','live_transition.py','transition_control.py',
                    'structured_probe_profile.py','structured_probe_control.py',
                    'raw_archive_probe_profile.py','raw_archive_probe_control.py',
                    'trial_cloud_profile.py','trial_cloud_control.py','trial_history_reader.py','watch_service.py','install_controller.py'})
            result=subprocess.run([sys.executable,'-IS',str(a)],cwd=folder,env={},capture_output=True,text=True,timeout=3)
            self.assertEqual(result.returncode,1)
            self.assertIn('entrypoint_precondition_failed',result.stdout)
            self.assertEqual(result.stderr,'')

    def test_packaged_entrypoint_preserves_only_public_disk_failure(self):
        harness = """import os,runpy,sys
sys.path.insert(0,sys.argv[1])
from controller import DeploymentHold,HostBinding
def refuse():
    raise DeploymentHold(sys.argv[1])
bundle,code=sys.argv[1:]
sys.argv=[bundle,code]
os.geteuid=lambda:0
HostBinding.from_marker=staticmethod(refuse)
runpy.run_path(bundle,run_name='__main__')
"""
        with tempfile.TemporaryDirectory() as folder:
            bundle=Path(folder)/'controller.pyz'
            builder.build(bundle)
            for cause,want in [('pp_filesystem_device_mismatch','pp_filesystem_device_mismatch'),
                               ('pp_filesystem_reserve','pp_filesystem_reserve'),
                               ('trial_authority_rebind_pending','trial_authority_rebind_pending'),
                               ('arbitrary_database_details','entrypoint_precondition_failed')]:
                with self.subTest(cause=cause):
                    result=subprocess.run([sys.executable,'-IS','-c',harness,str(bundle),cause],
                                          cwd=folder,env={},capture_output=True,text=True,timeout=5)
                    self.assertEqual(result.returncode,1)
                    self.assertIn(want,result.stdout)
                    self.assertEqual(result.stderr,'')

    def test_existing_qualified_bundle_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'qualified.pyz';path.write_bytes(b'preserve')
            with self.assertRaises(FileExistsError):builder.build(path)
            self.assertEqual(path.read_bytes(),b'preserve')
