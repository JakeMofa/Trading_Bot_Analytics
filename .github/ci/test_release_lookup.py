"""Exercise the existing release lookup without tokens, network or operator writes."""
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch


class LookupTests(unittest.TestCase):
    def test_only_successful_exact_push_on_deployment_branch_qualifies(self):
        spec = importlib.util.spec_from_file_location('ci_verify', Path('deploy/lightsail/verify_ci.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sha = 'a'*40
        env = {'APPROVED_REVISION': sha, 'GITHUB_EVENT_NAME': 'workflow_dispatch',
               'GITHUB_REF': 'refs/heads/codex/lightsail-deployment', 'GITHUB_SHA': sha,
               'GITHUB_REPOSITORY': 'JakeMofa/Trading_Bot_Analytics', 'GH_TOKEN': 'synthetic'}
        valid = {'head_sha': sha, 'head_branch': 'codex/lightsail-deployment',
                 'status': 'completed', 'conclusion': 'success'}
        for changed, accepted in [({}, True), ({'head_sha': 'b'*40}, False),
                                  ({'head_branch': 'main'}, False),
                                  ({'status': 'in_progress'}, False),
                                  ({'conclusion': 'failure'}, False),
                                  ({'conclusion': 'cancelled'}, False)]:
            def response(request, timeout):
                self.assertEqual(timeout, 30)
                if '/git/ref/' in request.full_url:
                    value = {'object': {'sha': sha}}
                else:
                    self.assertIn('event=push&head_sha=' + sha, request.full_url)
                    self.assertIn('/python-tests.yml/runs?', request.full_url)
                    value = {'workflow_runs': [dict(valid, **changed)]}
                return io.BytesIO(json.dumps(value).encode())
            with self.subTest(changed=changed), patch.dict('os.environ', env), \
                    patch.object(module.urllib.request, 'urlopen', side_effect=response):
                if accepted:
                    module.main()
                else:
                    with self.assertRaises(AssertionError):
                        module.main()
