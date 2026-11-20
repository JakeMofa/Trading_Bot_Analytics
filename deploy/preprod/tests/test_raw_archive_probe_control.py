"""Generated PP raw archive profile/authority controls; zero cloud calls."""
from contextlib import nullcontext
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compose_render import render_config
from controller import DeploymentHold
import raw_archive_probe_control as control
from raw_archive_probe_profile import validate_raw_archive_profile, validate_recurring_profile


ROOT = Path(__file__).resolve().parents[3]
FOLDER = ROOT / 'deploy/preprod'
IMAGE = 'sha256:' + 'a' * 64
GENERATION = '11111111-1111-4111-8111-111111111111'


def rendered(*overlays, profile="raw_archive_probe"):
    env = {**os.environ, 'PP_APP_IMAGE': IMAGE,
           'PP_SECRET_DIR': '/etc/tradebot/pp-postgres',
           'PP_RUNTIME_SECRET_DIR': '/etc/tradebot/pp-runtime'}
    command = ['docker', 'compose', '--env-file', '/dev/null',
               '--project-name', 'tradebot-pp-foundation',
               '--project-directory', str(FOLDER)]
    for name in ('compose.yaml', 'runtime.compose.yaml', *overlays):
        command.extend(('-f', str(FOLDER / name)))
    command.extend(('--profile', 'migration', '--profile', profile,
                    'config', '--format', 'json'))
    return render_config(command, env=env, timeout=5)


class ProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = rendered()
        cls.live = rendered('runtime.live.compose.yaml')
        cls.probe = rendered('runtime.live.compose.yaml',
                             'runtime.raw-archive-probe.compose.yaml')

    def check(self, profile):
        return validate_raw_archive_profile(self.base, self.live, profile, ROOT, IMAGE)

    def test_exact_profile_and_persistent_services_unchanged(self):
        self.check(self.probe)
        for name in ('api', 'calculation', 'lifecycle', 'operator'):
            self.assertEqual(self.probe['services'][name], self.live['services'][name])
            self.assertFalse(any('supabase_auth' in str(item)
                                 for item in self.probe['services'][name].get('secrets', ())))
        service = self.probe['services']['raw_archive_probe']
        self.assertEqual(service['user'], '0:0')
        self.assertEqual(service['restart'], 'no')
        self.assertTrue(service['read_only'])
        self.assertEqual(service['cap_drop'], ['ALL'])
        self.assertIn('no-new-privileges:true', service['security_opt'])
        self.assertEqual(set(service['networks']), {'database', 'raw_archive_probe_egress'})
        self.assertFalse(service.get('ports') or service.get('volumes'))

    def test_recurring_archive_privileges(self):
        profile = rendered('runtime.live.compose.yaml','runtime.sealed-archive.compose.yaml',
                           profile='sealed_archive')
        self.check(self.probe)
        validate_recurring_profile(self.probe, profile)
        profile['services']['sealed_archive']['secrets'].append({'source':'pp_history_dsn'})
        with self.assertRaises(DeploymentHold):
            validate_recurring_profile(self.probe, profile)

    def test_unsafe_profile_changes_stop(self):
        mutations = (
            lambda p: p['services']['raw_archive_probe'].update(restart='always'),
            lambda p: p['services']['raw_archive_probe'].update(cap_drop=[]),
            lambda p: p['services']['raw_archive_probe']['environment'].update(TRADEBOT_RETIREMENT_ENABLED='true'),
            lambda p: p['services']['raw_archive_probe']['secrets'].append({'source':'admin','target':'/run/secrets/admin'}),
            lambda p: p['services']['api']['secrets'].append({'source':'supabase_auth_password','target':'/run/secrets/password'}),
            lambda p: p['secrets']['supabase_auth_password'].update(file='/etc/tradebot/production/password'),
            lambda p: p['networks']['raw_archive_probe_egress'].update(external=True),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate.__code__.co_firstlineno):
                profile = deepcopy(self.probe)
                mutate(profile)
                with self.assertRaises(DeploymentHold):
                    self.check(profile)


class ControlTests(unittest.TestCase):
    def test_storage_files_are_root_only_distinct_and_uid_bound(self):
        class FakePath:
            def __init__(self, name): self.name = name
            def lstat(self): return records[self.name]
            def read_text(self, **_): return GENERATION
            def __truediv__(self, name): return FakePath(name)
        regular = 0o100000
        records = {'cloud': SimpleNamespace(st_mode=0o040700, st_uid=0)}
        for index, name in enumerate(control.CLOUD_FILES):
            records[name] = SimpleNamespace(st_mode=regular | (0o644 if name == 'pp_history_ca' else 0o600),
                st_uid=0, st_nlink=1, st_size=100, st_dev=1, st_ino=index+1)
        with patch.object(control, 'CLOUD_DIR', FakePath('cloud')), \
             patch.object(control, 'Path', side_effect=lambda path: FakePath(Path(path).name)):
            control._storage_files()
            with patch.object(FakePath, 'read_text', return_value='wrong-auth-uid'):
                with self.assertRaises(ValueError): control._storage_files()
            for name, field, bad in (('supabase_auth_password','st_mode',regular | 0o644),
                                     ('supabase_auth_uid','st_uid',10001),
                                     ('supabase_auth_email','st_nlink',2),
                                     ('pp_storage_api_key','st_ino',2)):
                original = getattr(records[name],field)
                setattr(records[name],field,bad)
                with self.assertRaises(DeploymentHold): control._storage_files()
                setattr(records[name],field,original)

    def test_preflight_has_no_cloud_call_and_execute_uses_one_owned_container(self):
        context = SimpleNamespace(request=SimpleNamespace(source_sha='a'*40,
            artifact_sha256='b'*64), image=IMAGE, source=ROOT)
        actions = Mock(attempt_id='c'*32, oneoffs={})
        actions._json.side_effect = lambda raw: json.loads(raw)
        installed = Path('/installed/controller.pyz')
        with patch.object(control, 'preflight', return_value=(context, actions, 'd'*64)), \
             patch.object(control, '_consume') as consume, \
             patch.object(control, '_stage_local_secret', return_value=nullcontext()), \
             patch.object(control, '_secure_file', return_value=(json.dumps({
                 'generation_id': GENERATION, 'expected_seal_count': 25,
                 'expected_manifest_count': 0}), None)), \
             patch.object(control, '_compose', return_value=json.dumps({
                 'status':'cycle_complete','raw_coverage':'partial',
                 'origin_id':'pp-live-pp','generation_id':GENERATION,
                 'retirement':'off','raw_rows':25,'outbox_rows':2,
                 'bounds':{'rows':25,'decoded_bytes':256*1024,
                           'cloud_operations':8,'seconds':20}}).encode()) as compose:
            dry = control.run('raw-archive-probe-v1 preflight', installed)
            self.assertEqual(dry['gate'], 'PP_RAW_ARCHIVE_PREFLIGHT_PASS')
            consume.assert_not_called()
            compose.assert_not_called()
            result = control.run('raw-archive-probe-v1 execute', installed)
            self.assertEqual(result['gate'], 'PP_RAW_ARCHIVE_ONCE_PASS')
            self.assertEqual(result['retirement'], 'off')
            self.assertEqual(result['raw_rows'], 25)
            consume.assert_called_once()
            args = compose.call_args.args[4]
            self.assertEqual(args[-1], '--execute')
            self.assertIn(GENERATION, args)
            self.assertEqual(actions.oneoffs,
                             {'tradebot-pp-deploy-' + 'c'*32 + '-1':'raw_archive_probe'})
            actions._cleanup_oneoffs.assert_called_once()

    def test_child_timeout_still_recovers_owned_container(self):
        context = SimpleNamespace(request=SimpleNamespace(source_sha='a'*40,
            artifact_sha256='b'*64), image=IMAGE, source=ROOT)
        actions = Mock(attempt_id='c'*32, oneoffs={})
        with patch.object(control, 'preflight', return_value=(context, actions, 'd'*64)), \
             patch.object(control, '_consume'), \
             patch.object(control, '_stage_local_secret', return_value=nullcontext()), \
             patch.object(control, '_secure_file', return_value=(json.dumps({
                 'generation_id': GENERATION, 'expected_seal_count': 25,
                 'expected_manifest_count': 0}), None)), \
             patch.object(control, '_compose', side_effect=TimeoutError):
            with self.assertRaises(DeploymentHold):
                control.run('raw-archive-probe-v1 execute', Path('/installed/controller.pyz'))
        actions._cleanup_oneoffs.assert_called_once()

    def test_cleanup_failure_cannot_be_reported_as_pass(self):
        context = SimpleNamespace(request=SimpleNamespace(source_sha='a'*40,
            artifact_sha256='b'*64), image=IMAGE, source=ROOT)
        actions = Mock(attempt_id='c'*32, oneoffs={})
        actions._json.side_effect = lambda raw: json.loads(raw)
        actions._cleanup_oneoffs.side_effect = DeploymentHold('owned_container_still_running')
        with patch.object(control, 'preflight', return_value=(context, actions, 'd'*64)), \
             patch.object(control, '_consume'), \
             patch.object(control, '_stage_local_secret', return_value=nullcontext()), \
             patch.object(control, '_secure_file', return_value=(json.dumps({
                 'generation_id': GENERATION, 'expected_seal_count': 25,
                 'expected_manifest_count': 0}), None)), \
             patch.object(control, '_compose', return_value=b'{}'):
            with self.assertRaises(DeploymentHold):
                control.run('raw-archive-probe-v1 execute', Path('/installed/controller.pyz'))

    def test_ambiguous_result_stops_even_after_container_exits(self):
        context = SimpleNamespace(request=SimpleNamespace(source_sha='a'*40,
            artifact_sha256='b'*64), image=IMAGE, source=ROOT)
        actions = Mock(attempt_id='c'*32, oneoffs={})
        actions._json.side_effect = lambda raw: json.loads(raw)
        with patch.object(control, 'preflight', return_value=(context, actions, 'd'*64)), \
             patch.object(control, '_consume'), \
             patch.object(control, '_stage_local_secret', return_value=nullcontext()), \
             patch.object(control, '_secure_file', return_value=(json.dumps({
                 'generation_id': GENERATION, 'expected_seal_count': 25,
                 'expected_manifest_count': 0}), None)), \
             patch.object(control, '_compose', return_value=b'{"status":"cycle_complete","retirement":"off"}'):
            with self.assertRaises(DeploymentHold):
                control.run('raw-archive-probe-v1 execute', Path('/installed/controller.pyz'))


if __name__ == '__main__':
    unittest.main()
