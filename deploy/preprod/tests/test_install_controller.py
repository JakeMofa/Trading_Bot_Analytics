from pathlib import Path
import importlib.util
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).parents[1]
sys.path.insert(0,str(HERE))
def load(name):
    spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
installer=load('install_controller');builder=load('controller_bundle')


class InstallationControls(unittest.TestCase):
    def test_bundle_hash_and_members_required_before_installation(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'controller.pyz';info=builder.build(path)
            self.assertEqual(installer.checked_bundle(path,info['sha256']),path.read_bytes())
            with self.assertRaises(Exception):installer.checked_bundle(path,'0'*64)
            alias=Path(folder)/'link.pyz';alias.symlink_to(path)
            with self.assertRaises(Exception):installer.checked_bundle(alias,info['sha256'])

    def test_authority_binds_exact_source_and_does_not_replace_existing(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);lib=root/'lib';lib.mkdir();authority=root/'authority';authority.mkdir()
            info=builder.build(lib/'controller.pyz')
            with patch.object(installer,'LIB',lib),patch.object(installer,'AUTHORITY',authority), \
                 patch.object(installer.HostBinding,'from_marker'),patch.object(installer,'directory'):
                result=installer.authorize('a'*40,'b'*64,info['sha256'])
                self.assertFalse(result['deployment_dispatched'])
                permit=json.loads((authority/'authorization.json').read_text())
                self.assertEqual(permit['source_sha'],'a'*40)
                self.assertEqual(permit['data_mode'],'generated')
                self.assertFalse(permit['live_collector_enabled'])
                original=(authority/'authorization.json').read_bytes()
                with self.assertRaises(Exception):installer.authorize('c'*40,'d'*64,info['sha256'])
                self.assertEqual((authority/'authorization.json').read_bytes(),original)
