import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('foundation', SOURCE / 'foundation.py')
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)


class FoundationControls(unittest.TestCase):
    def setUp(self):
        self.marker = dict(environment='preprod', project='Tradebot', live_collector_authorized=False,
                           paid_ai_authorized=False, production_data_copied=False, application_installed=False)

    def host(self, **changes):
        values = dict(hostname='tradebot-preprod-01', marker=self.marker,
                      disk_free=12*f.GIB, available_memory=2*f.GIB, os_id='ubuntu', version='24.04')
        values.update(changes)
        return f.validate_host(**values)

    def test_correct_host(self):
        self.host()

    def test_wrong_host_and_environment_fail_closed(self):
        for changes in ({'hostname':'tradebot-analytics-01'}, {'marker':{**self.marker,'environment':'production'}}, {'marker':{**self.marker,'application_installed':True}}):
            with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                self.host(**changes)

    def test_missing_flag_and_resources_rejected(self):
        marker = dict(self.marker)
        del marker['paid_ai_authorized']
        for changes in ({'marker':marker}, {'disk_free':10*f.GIB-1}, {'available_memory':f.GIB-1}, {'version':'22.04'}):
            with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                self.host(**changes)

    def test_secret_symlink_rejected_without_modification(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'real').mkdir()
            (root/'link').symlink_to(root/'real')
            with self.assertRaises(RuntimeError):
                f.prepare_secrets(root/'link')
            self.assertEqual(list((root/'real').iterdir()), [])

    def test_secret_contents_not_leaked_on_failure(self):
        with self.assertRaises(RuntimeError) as caught:
            f.run([sys.executable,'-c',"import sys;print('secret-value');sys.exit(3)"])
        self.assertNotIn('secret-value',str(caught.exception))

    def test_timed_out_child_is_reaped(self):
        started=time.monotonic()
        with self.assertRaisesRegex(RuntimeError,'terminated and reaped'):
            f.run([sys.executable,'-c','import time;time.sleep(20)'],timeout=.05)
        self.assertLess(time.monotonic()-started,2)

    def test_no_public_ports_or_general_services(self):
        text=(SOURCE/'compose.yaml').read_text()
        self.assertNotIn('ports:',text)
        self.assertNotIn('privileged:',text)
        self.assertNotIn('/var/run/docker.sock',text)
        self.assertIn('internal: true',text)
        self.assertIn(f.IMAGE,text)

    def test_unsafe_rendered_configuration_stops_before_start(self):
        safe={'services':{'postgres':{'image':f.IMAGE,'mem_limit':512*1024**2,'memswap_limit':512*1024**2}},'networks':{'database':{'internal':True}}}
        for mode in ('image','ports','memory','network'):
            config=json.loads(json.dumps(safe))
            if mode=='image': config['services']['postgres']['image']='postgres:latest'
            if mode=='ports': config['services']['postgres']['ports']=[5432]
            if mode=='memory': config['services']['postgres']['mem_limit']=1024**3
            if mode=='network': config['networks']['database']['internal']=False
            with self.subTest(mode=mode), patch.object(f,'compose',return_value=json.dumps(config)), self.assertRaises(RuntimeError):
                f.verify_configuration(Path('/unused'))

    def test_compose_string_memory_values_are_validated(self):
        safe={'services':{'postgres':{'image':f.IMAGE,'mem_limit':'536870912','memswap_limit':'536870912'}},'networks':{'database':{'internal':True}}}
        with patch.object(f,'compose',return_value=json.dumps(safe)):
            f.verify_configuration(Path('/unused'))

    def test_unreviewed_schema_is_rejected(self):
        with patch.object(f,'sql',return_value='[]'), self.assertRaisesRegex(RuntimeError,'schema drift'):
            f.verify_schema(Path('/unused'))

    def test_password_file_newlines_are_trimmed_server_side(self):
        text=(SOURCE/'init.sh').read_text()
        self.assertEqual(text.count("btrim(pg_read_file("),3)
        self.assertIn("E'\\n\\r '",text)

    def test_ci_cannot_execute_on_pp(self):
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true'}), patch.object(f.os,'geteuid',return_value=0), patch.object(f,'MARKER') as marker, patch.object(sys,'argv',['foundation.py','ci']):
            marker.exists.return_value=True
            with self.assertRaises(RuntimeError):
                f.main()
        f.DEADLINE=None

if __name__=='__main__':
    unittest.main()
