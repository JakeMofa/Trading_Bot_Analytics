"""Generated PP one-shot mount controls; no host files or cloud writes."""
from copy import deepcopy
from contextlib import nullcontext
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compose_render import render_config
from controller import DeploymentHold
import structured_probe_control as control
from structured_probe_profile import validate_probe_profile

ROOT = Path(__file__).resolve().parents[3]
FOLDER = ROOT / 'deploy/preprod'
IMAGE = 'sha256:' + 'a' * 64


def rendered(*overlays):
    env = {**os.environ, 'PP_APP_IMAGE': IMAGE,
           'PP_SECRET_DIR': '/etc/tradebot/pp-postgres',
           'PP_RUNTIME_SECRET_DIR': '/etc/tradebot/pp-runtime'}
    command = ['docker', 'compose', '--env-file', '/dev/null',
               '--project-name', 'tradebot-pp-foundation',
               '--project-directory', str(FOLDER)]
    for file in ('compose.yaml', 'runtime.compose.yaml', *overlays):
        command.extend(('-f', str(FOLDER / file)))
    command.extend(('--profile', 'migration', '--profile', 'structured_probe',
                    'config', '--format', 'json'))
    return render_config(command, env=env, timeout=5)


class ProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = rendered()
        cls.live = rendered('runtime.live.compose.yaml')
        cls.probe = rendered('runtime.live.compose.yaml',
                             'runtime.structured-probe.compose.yaml')

    def check(self, profile):
        return validate_probe_profile(self.base, self.live, profile, ROOT, IMAGE)

    def test_exact_profile_and_persistent_services_unchanged(self):
        self.check(self.probe)
        for name in ('api', 'calculation', 'lifecycle', 'operator'):
            self.assertEqual(self.probe['services'][name], self.live['services'][name])
            self.assertFalse(any('pp_history' in str(item)
                                 for item in self.probe['services'][name].get('secrets', ())))
        service = self.probe['services']['structured_probe']
        self.assertEqual(service['user'], '0:0')
        self.assertEqual(service['restart'], 'no')
        self.assertTrue(service['read_only'])
        self.assertEqual(service['cap_drop'], ['ALL'])
        self.assertIn('no-new-privileges:true', service['security_opt'])
        self.assertEqual(set(service['networks']), {'database', 'structured_probe_egress'})
        self.assertFalse(service.get('ports') or service.get('volumes') or service.get('use_api_socket'))
        self.assertEqual(service['environment']['TRADEBOT_PP_STRUCTURED_ONE_SHOT'], 'true')
        self.assertEqual(service['environment']['TRADEBOT_PP_RETAIN_REVISIONS'], 'true')

    def test_unsafe_overrides_fail_closed(self):
        mutations = (
            lambda p: p['services']['api']['secrets'].append({'source': 'pp_history_dsn', 'target': '/run/secrets/pp_history_dsn'}),
            lambda p: p['services']['structured_probe'].update(restart='unless-stopped'),
            lambda p: p['services']['structured_probe'].update(read_only=False),
            lambda p: p['services']['structured_probe'].update(volumes=[{'type': 'bind', 'source': '/var/run/docker.sock', 'target': '/var/run/docker.sock'}]),
            lambda p: p['services']['structured_probe'].update(cap_drop=[]),
            lambda p: p['services']['structured_probe']['environment'].update(ENABLE_SUPABASE_SYNC='true'),
            lambda p: p['services']['structured_probe']['environment'].update(TRADEBOT_PP_RETAIN_REVISIONS='false'),
            lambda p: p['services']['structured_probe']['environment'].update(TRADEBOT_ENVIRONMENT='production'),
            lambda p: p['services']['structured_probe']['secrets'].append({'source': 'admin', 'target': '/run/secrets/admin'}),
            lambda p: p['secrets']['pp_history_dsn'].update(file='/etc/tradebot/production/history_dsn'),
            lambda p: p['networks']['structured_probe_egress'].update(external=True),
        )
        for change in mutations:
            with self.subTest(change=change.__code__.co_firstlineno):
                profile = deepcopy(self.probe)
                change(profile)
                with self.assertRaises(DeploymentHold):
                    self.check(profile)


class ControlTests(unittest.TestCase):
    def test_only_exact_sanitized_child_reason_is_public(self):
        report = {'status': 'HOLD', 'reason': 'archive_unavailable',
                  'ack_status': 'unconfirmed_after_error', 'retirement': 'off'}
        self.assertEqual(control._public_child_failure(json.dumps(report).encode()),
                         'pp_structured_archive_unavailable')
        for unsafe in (
            {**report, 'reason': 'postgres://user:secret@host'},
            {**report, 'detail': 'secret'},
            {**report, 'ack_status': 'acknowledged'},
            {**report, 'retirement': 'on'},
            {**report, 'status': 'acknowledged'},
        ):
            with self.subTest(unsafe=unsafe):
                self.assertEqual(control._public_child_failure(json.dumps(unsafe).encode()),
                                 'pp_structured_probe_failed')
        for malformed in (b'{"status":"HOLD","status":"HOLD"}',
                          b'not json', b'x' * 2049):
            self.assertEqual(control._public_child_failure(malformed),
                             'pp_structured_probe_failed')

    def test_structured_compose_exposes_only_allowlisted_nonzero_reason(self):
        context = SimpleNamespace(source=ROOT, image=IMAGE)
        actions = Mock()
        actions._environment.return_value = {}
        budget = Mock()
        report = {'status': 'HOLD', 'reason': 'archive_integrity',
                  'ack_status': 'unconfirmed_after_error', 'retirement': 'off'}
        budget.run.return_value = (1, json.dumps(report).encode())
        with self.assertRaisesRegex(DeploymentHold, '^pp_structured_archive_integrity$'):
            control._compose(actions, context, budget, (), ['run', 'structured_probe'],
                             25, capture_exit=True)
        self.assertEqual(budget.run.call_args.kwargs['output_limit'], 2048)
        self.assertTrue(budget.run.call_args.kwargs['return_status'])
        budget.run.return_value = (1, b'{"reason":"postgres://secret"}')
        with self.assertRaisesRegex(DeploymentHold, '^pp_structured_probe_failed$'):
            control._compose(actions, context, budget, (), ['run', 'structured_probe'],
                             25, capture_exit=True)

    def test_ephemeral_local_credential_is_root_only_and_removed(self):
        original_fstat = control.os.fstat
        original_lstat = Path.lstat
        count = 0
        def fstat(fd):
            nonlocal count
            count += 1
            result = original_fstat(fd)
            owner = 10001 if count <= 2 else 0
            return SimpleNamespace(st_mode=result.st_mode, st_uid=owner,
                st_nlink=result.st_nlink, st_size=result.st_size,
                st_dev=result.st_dev, st_ino=result.st_ino,
                st_mtime_ns=result.st_mtime_ns)
        def lstat(path):
            result = original_lstat(path)
            if path == source.parent:
                return SimpleNamespace(st_mode=0o040700, st_uid=0)
            return result
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'lifecycle_dsn'
            staged = Path(folder) / 'probe-local-dsn'
            source.write_bytes(b'generated-local-credential')
            source.chmod(0o400)
            with patch.object(control.os, 'fstat', side_effect=fstat), \
                 patch.object(Path, 'lstat', lstat):
                with control._stage_local_secret(source, staged):
                    self.assertEqual(staged.read_bytes(), b'generated-local-credential')
                    self.assertEqual(staged.stat().st_mode & 0o777, 0o600)
                self.assertFalse(staged.exists())

    def test_ephemeral_secret_cleanup_failure_reports_stop(self):
        original_fstat = control.os.fstat
        original_lstat = Path.lstat
        original_unlink = Path.unlink
        count = 0
        def fstat(fd):
            nonlocal count
            count += 1
            result = original_fstat(fd)
            return SimpleNamespace(st_mode=result.st_mode,
                st_uid=10001 if count <= 2 else 0,
                st_nlink=result.st_nlink, st_size=result.st_size,
                st_dev=result.st_dev, st_ino=result.st_ino,
                st_mtime_ns=result.st_mtime_ns)
        def lstat(path):
            result = original_lstat(path)
            return SimpleNamespace(st_mode=0o040700, st_uid=0) if path == source.parent else result
        def unlink(path, *args, **kwargs):
            if path == staged: raise OSError('injected cleanup failure')
            return original_unlink(path, *args, **kwargs)
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'lifecycle_dsn'
            staged = Path(folder) / 'probe-local-dsn'
            source.write_bytes(b'generated-local-credential')
            source.chmod(0o400)
            with patch.object(control.os, 'fstat', side_effect=fstat), \
                 patch.object(Path, 'lstat', lstat), \
                 patch.object(Path, 'unlink', unlink):
                with self.assertRaisesRegex(DeploymentHold, 'probe_local_secret_cleanup_failed'):
                    with control._stage_local_secret(source, staged): pass
            original_unlink(staged)

    def test_wrong_host_stops_before_any_file_or_docker_check(self):
        with patch.object(control.HostBinding, 'from_marker', side_effect=DeploymentHold('wrong_host')):
            with patch.object(control, '_files') as files:
                with self.assertRaises(DeploymentHold):
                    control.preflight(Path('/installed/controller.pyz'), Mock())
                files.assert_not_called()

    def test_file_permissions_and_aliases_rejected(self):
        class FakePath:
            def __init__(self, name): self.name = name
            def lstat(self): return records[self.name]
            def __truediv__(self, name): return FakePath(name)
            def read_text(self, **_): return '-----BEGIN CERTIFICATE-----\nX\n-----END CERTIFICATE-----'
        regular = 0o100000
        records = {
            'cloud': SimpleNamespace(st_mode=0o040700, st_uid=0),
            'pp_history_dsn': SimpleNamespace(st_mode=regular | 0o600, st_uid=0, st_nlink=1, st_size=100, st_dev=1, st_ino=1),
            'pp_history_ca': SimpleNamespace(st_mode=regular | 0o644, st_uid=0, st_nlink=1, st_size=100, st_dev=1, st_ino=2),
            'lifecycle_dsn': SimpleNamespace(st_mode=regular | 0o400, st_uid=10001,
                                             st_nlink=1, st_size=100),
        }
        with patch.object(control, 'CLOUD_DIR', FakePath('cloud')), \
             patch.object(control, 'RUNTIME_SECRETS', FakePath('runtime')):
            with patch.object(control.ssl, 'PEM_cert_to_DER_cert', return_value=b'certificate'), \
                 patch.object(control, 'CA_SHA256', control.hashlib.sha256(b'certificate').hexdigest()):
                control._files()
                for name, field, bad in (('pp_history_dsn', 'st_mode', regular | 0o644),
                                         ('pp_history_ca', 'st_uid', 10001),
                                         ('pp_history_dsn', 'st_nlink', 2),
                                         ('pp_history_ca', 'st_ino', 1)):
                    original = getattr(records[name], field)
                    setattr(records[name], field, bad)
                    with self.assertRaises(DeploymentHold): control._files()
                    setattr(records[name], field, original)

    def test_dry_run_issues_no_cloud_call_and_execute_uses_fixed_oneoff(self):
        context = SimpleNamespace(request=SimpleNamespace(source_sha='a'*40,
            artifact_sha256='b'*64), image=IMAGE, source=ROOT)
        actions = Mock()
        actions.attempt_id = 'c'*32
        actions.oneoffs = {}
        actions._json.side_effect = lambda raw: json.loads(raw)
        installed = Path('/installed/controller.pyz')
        with patch.object(control, 'preflight', return_value=(context, actions, 'd'*64)), \
             patch.object(control, '_consume') as consume, \
             patch.object(control, '_stage_local_secret', return_value=nullcontext()), \
             patch.object(control, '_secure_file', return_value=(json.dumps({
                 'generation_id': '11111111-1111-4111-8111-111111111111',
                 'expected_state': 'sealed', 'expected_first_outbox_id': 7}), None)), \
             patch.object(control, '_compose', return_value=b'{"status":"acknowledged","origin_id":"pp-live-pp","retirement":"off","raw_archive":"not_started","acknowledged":7}') as compose:
            dry = control.run('structured-probe-v1 preflight', installed)
            self.assertEqual(dry['gate'], 'PP_STRUCTURED_PREFLIGHT_PASS')
            compose.assert_not_called()
            consume.assert_not_called()
            result = control.run('structured-probe-v1 execute', installed)
            self.assertEqual(result['gate'], 'PP_STRUCTURED_ONCE_PASS')
            args = compose.call_args.args[4]
            self.assertEqual(args[:3], ['run', '--rm', '--no-deps'])
            self.assertNotIn('up', args)
            self.assertIn('structured_probe', args)
            self.assertIn('--execute', args)
            self.assertNotIn('lifecycle', args)
            actions._cleanup_oneoffs.assert_called_once()

    def test_timeout_still_cleans_owned_oneoff(self):
        context = SimpleNamespace(request=SimpleNamespace(source_sha='a'*40,
            artifact_sha256='b'*64), image=IMAGE, source=ROOT)
        actions = Mock(attempt_id='c'*32, oneoffs={})
        with patch.object(control, 'preflight', return_value=(context, actions, 'd'*64)), \
             patch.object(control, '_consume'), \
             patch.object(control, '_stage_local_secret', return_value=nullcontext()), \
             patch.object(control, '_secure_file', return_value=(json.dumps({
                 'generation_id': '11111111-1111-4111-8111-111111111111',
                 'expected_state': 'sealed', 'expected_first_outbox_id': 7}), None)), \
             patch.object(control, '_compose', side_effect=DeploymentHold('child_deadline_exceeded')):
            with self.assertRaises(DeploymentHold):
                control.run('structured-probe-v1 execute', Path('/installed/controller.pyz'))
            actions._cleanup_oneoffs.assert_called_once()

    def test_sanitized_failure_survives_cleanup_and_consumes_permit(self):
        context = SimpleNamespace(request=SimpleNamespace(source_sha='a'*40,
            artifact_sha256='b'*64), image=IMAGE, source=ROOT)
        actions = Mock(attempt_id='c'*32, oneoffs={})
        permit = {'generation_id': '11111111-1111-4111-8111-111111111111',
                  'expected_state': 'sealed', 'expected_first_outbox_id': 7}
        with patch.object(control, 'preflight', return_value=(context, actions, 'd'*64)), \
             patch.object(control, '_consume') as consume, \
             patch.object(control, '_stage_local_secret', return_value=nullcontext()), \
             patch.object(control, '_secure_file', return_value=(json.dumps(permit), None)), \
             patch.object(control, '_compose', side_effect=DeploymentHold('pp_structured_archive_unavailable')):
            with self.assertRaisesRegex(DeploymentHold, '^pp_structured_archive_unavailable$'):
                control.run('structured-probe-v1 execute', Path('/installed/controller.pyz'))
            consume.assert_called_once()
            actions._cleanup_oneoffs.assert_called_once()

        actions._cleanup_oneoffs.side_effect = DeploymentHold('cleanup_failed')
        with patch.object(control, 'preflight', return_value=(context, actions, 'd'*64)), \
             patch.object(control, '_consume'), \
             patch.object(control, '_stage_local_secret', return_value=nullcontext()), \
             patch.object(control, '_secure_file', return_value=(json.dumps(permit), None)), \
             patch.object(control, '_compose', side_effect=DeploymentHold('pp_structured_archive_unavailable')):
            with self.assertRaisesRegex(DeploymentHold, '^cleanup_failed$'):
                control.run('structured-probe-v1 execute', Path('/installed/controller.pyz'))

    def test_idle_or_ambiguous_child_result_is_not_success(self):
        context = SimpleNamespace(request=SimpleNamespace(source_sha='a'*40,
            artifact_sha256='b'*64), image=IMAGE, source=ROOT)
        actions = Mock(attempt_id='c'*32, oneoffs={})
        actions._json.side_effect = lambda raw: json.loads(raw)
        permit = {'generation_id': '11111111-1111-4111-8111-111111111111',
                  'expected_state': 'sealed', 'expected_first_outbox_id': 7}
        with patch.object(control, 'preflight', return_value=(context, actions, 'd'*64)), \
             patch.object(control, '_consume'), \
             patch.object(control, '_stage_local_secret', return_value=nullcontext()), \
             patch.object(control, '_secure_file', return_value=(json.dumps(permit), None)), \
             patch.object(control, '_compose', return_value=b'{"status":"idle","origin_id":"pp-live-pp","retirement":"off","raw_archive":"not_started","acknowledged":0}'):
            with self.assertRaises(DeploymentHold):
                control.run('structured-probe-v1 execute', Path('/installed/controller.pyz'))
            actions._cleanup_oneoffs.assert_called_once()


if __name__ == '__main__': unittest.main()
