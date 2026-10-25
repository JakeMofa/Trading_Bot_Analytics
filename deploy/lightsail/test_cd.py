"""Test material-failure rollback and fail-closed revision/CI controls without production."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DeploymentTests(unittest.TestCase):
    def test_failed_smoke_restores_old_code_and_rechecks_health(self):
        cd = load('deploy')
        old, new = 'a' * 40, 'b' * 40
        calls = []
        def git(*args):
            calls.append(args)
            if args == ('rev-parse', 'HEAD'):
                return old
            if args[0] == 'ls-tree':
                return ''
            if args[:2] == ('bundle', 'list-heads'):
                return new + ' ' + cd.BRANCH
            if args == ('rev-parse', 'FETCH_HEAD'):
                return new
            if args[:2] == ('diff', '--name-only'):
                return 'backend/app/api.py'
            return ''
        with tempfile.TemporaryDirectory() as directory, patch.object(cd, 'ROOT', Path(directory)), \
             patch.object(cd, 'git', side_effect=git), patch.object(cd, 'preflight', return_value={}), \
             patch.object(cd, 'protected', return_value=('hash', 0o600, 1)), \
             patch.object(cd, 'run'), patch.object(cd, 'services'), \
             patch.object(cd, 'smoke', side_effect=[{}, RuntimeError('material failure'), {}]) as smoke:
            with self.assertRaises(SystemExit):
                cd.deploy(new, Path(directory) / 'input.bundle')
            self.assertIn(('checkout', '--detach', new), calls)
            self.assertIn(('checkout', '--detach', old), calls)
            self.assertEqual(smoke.call_count, 3)

    def test_preflight_failure_never_checks_out_or_rolls_back(self):
        cd = load('deploy')
        with patch.object(cd, 'preflight', side_effect=RuntimeError()), patch.object(cd, 'git') as git:
            with self.assertRaises(RuntimeError):
                cd.deploy('b' * 40, Path('input.bundle'))
            git.assert_not_called()

    def test_non_dispatch_or_wrong_branch_is_rejected_before_network(self):
        verify = load('verify_ci')
        for event, branch in [('push', 'refs/heads/codex/lightsail-deployment'), ('workflow_dispatch', 'refs/heads/main')]:
            with patch.dict('os.environ', {'APPROVED_REVISION': 'b' * 40, 'GITHUB_EVENT_NAME': event, 'GITHUB_REF': branch}), \
                 patch.object(verify.urllib.request, 'urlopen') as network:
                with self.assertRaises(AssertionError):
                    verify.main()
                network.assert_not_called()

    def test_wrong_bundle_ref_is_rejected_before_checkout(self):
        cd = load('deploy')
        with patch.object(cd, 'preflight', return_value={}), patch.object(cd, 'protected'), \
             patch.object(cd, 'smoke'), patch.object(cd, 'git', side_effect=['a' * 40, '', 'b' * 40 + ' refs/heads/main']) as git:
            with self.assertRaisesRegex(AssertionError, 'approved branch'):
                cd.deploy('b' * 40, Path('input.bundle'))
            self.assertFalse(any(call.args[0] == 'checkout' for call in git.call_args_list))


if __name__ == '__main__':
    unittest.main()
