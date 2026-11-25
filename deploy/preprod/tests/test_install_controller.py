from pathlib import Path
import importlib.util
import json
import sys
import stat
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch,Mock

HERE=Path(__file__).parents[1]
sys.path.insert(0,str(HERE))
def load(name):
    spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
installer=load('install_controller');builder=load('controller_bundle')


class InstallationControls(unittest.TestCase):
    def test_raw_archive_authority_binds_exact_sealed_generation_without_dispatch(self):
        active={'state':'ready_off','environment':'preprod','instance':'tradebot-preprod-01',
                'source_sha':'a'*40,'artifact_sha256':'b'*64,
                'controller_sha256':'c'*64,'image_id':'sha256:'+'d'*64}
        with tempfile.TemporaryDirectory() as folder:
            authority=Path(folder)/'raw.json'
            with patch.object(installer,'RAW_ARCHIVE_AUTHORITY',authority), \
                 patch.object(installer.HostBinding,'from_marker'), \
                 patch.object(installer,'_read_active',return_value=active), \
                 patch.object(installer,'checked_bundle'), \
                 patch.object(installer,'_candidate'), \
                 patch.object(installer,'directory'):
                result=installer.authorize_raw_archive_probe(
                    '11111111-1111-4111-8111-111111111111',25,0)
                self.assertFalse(result['deployment_dispatched'])
                permit=json.loads(authority.read_text())
                self.assertEqual(permit['scope'],'pp_raw_archive_one_shot')
                self.assertEqual((permit['expected_seal_count'],
                                  permit['expected_manifest_count']),(25,0))
                self.assertFalse(permit['retirement_enabled'])
                original=authority.read_bytes()
                with self.assertRaises(Exception):
                    installer.authorize_raw_archive_probe(
                        '11111111-1111-4111-8111-111111111111',25,0)
                self.assertEqual(authority.read_bytes(),original)
                with self.assertRaises(Exception):
                    installer.authorize_raw_archive_probe('bad',25,0)

    def test_structured_probe_authority_is_exact_and_does_not_dispatch(self):
        active={'state':'ready_off','environment':'preprod','instance':'tradebot-preprod-01',
                'source_sha':'a'*40,'artifact_sha256':'b'*64,
                'controller_sha256':'c'*64,'image_id':'sha256:'+'d'*64}
        with tempfile.TemporaryDirectory() as folder:
            authority=Path(folder)/'probe.json'
            with patch.object(installer,'PROBE_AUTHORITY',authority), \
                 patch.object(installer.HostBinding,'from_marker'), \
                 patch.object(installer,'_read_active',return_value=active), \
                 patch.object(installer,'checked_bundle'), \
                 patch.object(installer,'_candidate'), \
                 patch.object(installer,'directory'):
                result=installer.authorize_structured_probe(
                    '11111111-1111-4111-8111-111111111111','sealed',7)
                self.assertFalse(result['deployment_dispatched'])
                permit=json.loads(authority.read_text())
                self.assertEqual(permit['scope'],'pp_structured_one_shot')
                self.assertEqual(permit['expected_first_outbox_id'],7)
                self.assertFalse(permit['retirement_enabled'])
                self.assertFalse(permit['cloud_enabled'])
                with self.assertRaises(Exception):
                    installer.authorize_structured_probe(
                        '11111111-1111-4111-8111-111111111111','sealed',7)
                with self.assertRaises(Exception):
                    installer.authorize_structured_probe('bad','sealed',7)

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
                 patch.object(installer.HostBinding,'from_marker',return_value=installer.HostBinding(
                     'tradebot-preprod-benchmark-4gb','preprod','Tradebot',False,False,False)), \
                 patch.object(installer,'directory'):
                result=installer.authorize('a'*40,'b'*64,info['sha256'])
                self.assertFalse(result['deployment_dispatched'])
                permit=json.loads((authority/'authorization.json').read_text())
                self.assertEqual(permit['source_sha'],'a'*40)
                self.assertEqual(permit['instance'],'tradebot-preprod-benchmark-4gb')
                self.assertEqual(permit['data_mode'],'generated')
                self.assertFalse(permit['live_collector_enabled'])
                original=(authority/'authorization.json').read_bytes()
                with self.assertRaises(Exception):installer.authorize('c'*40,'d'*64,info['sha256'])
                self.assertEqual((authority/'authorization.json').read_bytes(),original)

    def test_installed_controller_rejects_nonroot_or_writable_files(self):
        for mode,uid,accepted in [(0o600,0,True),(0o644,0,True),(0o620,0,False),
                                  (0o602,0,False),(0o600,1234,False)]:
            with self.subTest(mode=oct(mode),uid=uid):
                path=Mock()
                path.lstat.return_value=SimpleNamespace(st_mode=stat.S_IFREG|mode,st_uid=uid)
                path.read_bytes.return_value=b'qualified-controller'
                if accepted:
                    self.assertEqual(installer.read_installed_controller(path),b'qualified-controller')
                else:
                    with self.assertRaises(Exception):installer.read_installed_controller(path)
                    path.read_bytes.assert_not_called()

    def test_authorized_key_is_root_owned_publicly_readable_and_immutable(self):
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder)
            with patch.object(installer,'directory') as directory,patch.object(installer,'write_new_or_same') as write:
                installer.install_authorized_key(home,'ssh-ed25519 generated-public-key')
                directory.assert_called_once_with(home/'.ssh',0o755)
                self.assertEqual(write.call_args.args[0],home/'.ssh/authorized_keys')
                self.assertEqual(write.call_args.args[2],0o644)
                self.assertTrue(write.call_args.args[1].startswith(b'restrict,command="/usr/local/bin/tradebot-pp-deploy" '))
