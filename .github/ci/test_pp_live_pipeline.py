from pathlib import Path
import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('pp_live_pipeline', HERE/'pp_live_pipeline.py')
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class PPLivePipelineTests(unittest.TestCase):
    def test_emergency_off_needs_no_branch_head_source_or_new_release(self):
        class API:
            def read(self, path):
                self_path = '/git/ref/heads/main'
                if path != self_path:
                    raise AssertionError(path)
                return {'object': {'sha': 'a'*40}}
        env = {'PP_LIVE_OPERATION':'off', 'GITHUB_EVENT_NAME':'workflow_dispatch',
               'GITHUB_REF_NAME':'main', 'GITHUB_SHA':'a'*40,
               'GITHUB_REPOSITORY':module.pipeline.REPO}
        self.assertEqual(module.command_for(env, API(), {'controller_sha256':'b'*64}),
                         ('session-v1 off', {'operation':'off'}))

    def test_transport_exposes_only_allowlisted_filesystem_failures(self):
        from types import SimpleNamespace
        for reason,expected in [('pp_filesystem_reserve','pp_filesystem_reserve'),
                                ('arbitrary_secret','controller_report_unavailable')]:
            body=json.dumps({'gate':'BLOCKED','environment':'preprod','reason':reason}).encode()
            with self.subTest(reason=reason), patch.object(module.pipeline,'bounded_process',
                    return_value=SimpleNamespace(returncode=1,stdout=body)):
                with self.assertRaisesRegex(module.pipeline.PipelineHold,expected):
                    module.transport({'user':'test','host':'127.0.0.1'},'session-v1 on 100',
                                     {'PP_DEPLOY_KEY':'fixture','PP_DEPLOY_KNOWN_HOSTS':'fixture'})

    def test_long_pp_session_has_an_explicit_finite_bound(self):
        class API:
            def read(self, path):
                return {'object': {'sha':'a'*40}}
        env = {'PP_LIVE_OPERATION':'on', 'GITHUB_EVENT_NAME':'workflow_dispatch',
               'GITHUB_REF_NAME':'preprod', 'GITHUB_SHA':'a'*40, 'GITHUB_REPOSITORY':module.pipeline.REPO}
        self.assertEqual(module.command_for({**env,'PP_LIVE_SECONDS':'4560'}, API(), {})[0],
                         'session-v1 on 4560')
        with self.assertRaises(ValueError):
            module.command_for({**env,'PP_LIVE_SECONDS':'4561'}, API(), {})

    def test_cycle_needs_exact_anchor_and_finite_duration(self):
        class API:
            def read(self, _path):
                return {'object': {'sha': 'a'*40}}
        anchor = 'b98ac4e9-b073-4df7-bc5b-90fa51c4f039'
        env = {'PP_LIVE_OPERATION': 'on', 'GITHUB_EVENT_NAME': 'workflow_dispatch',
               'GITHUB_REF_NAME': 'preprod', 'GITHUB_SHA': 'a'*40,
               'GITHUB_REPOSITORY': module.pipeline.REPO, 'PP_LIVE_SECONDS': '6600',
               'PP_CYCLE_INITIAL_A': anchor}
        command, proof = module.command_for(env, API(), {})
        self.assertEqual(command, f'session-v1 on 6600 {anchor}')
        self.assertEqual(proof['initial_a'], anchor)
        for change in ({'PP_CYCLE_INITIAL_A': ''}, {'PP_CYCLE_INITIAL_A': anchor.upper()},
                       {'PP_LIVE_SECONDS': '6599'}, {'PP_LIVE_SECONDS': '6601'},
                       {'PP_LIVE_OPERATION': 'off'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                module.command_for(env | change, API(), {})
        result = {'gate': 'PP_LIVE_ON', 'origin_id': 'pp-live-pp', 'collector_enabled': True}
        with self.assertRaises(ValueError):
            module.validated_result('on', result, anchor)
        module.validated_result('on', result | {'initial_a': anchor}, anchor)

    def test_enter_command_binds_generated_proof_and_exact_source_ci(self):
        class API:
            def read(self, path):
                self_path = '/git/ref/heads/preprod'
                if path != self_path:
                    raise AssertionError(path)
                return {'object': {'sha': 'a'*40}}
        env = {'PP_LIVE_OPERATION':'enter', 'GITHUB_EVENT_NAME':'workflow_dispatch',
               'GITHUB_REF_NAME':'preprod', 'GITHUB_SHA':'a'*40,
               'GITHUB_REPOSITORY':module.pipeline.REPO, 'SOURCE_BRANCH':'preprod',
               'APPROVED_REVISION':'b'*40, 'RELEASE_VERSION':'v0.2.0-pp.8',
               'PP_LIVE_IMAGE_ID':'sha256:'+'e'*64, 'PP_DEPLOYMENT_RUN_ID':'123'}
        candidate = {'artifact_sha256':'c'*64, 'version':'v0.2.0-pp.8', 'registry':'ghcr.io/example@sha256:'+'f'*64}
        proof = {'generated_deployment_run_id':123}
        with patch.object(module, 'load_candidate', return_value=(candidate, b'')), \
             patch.object(module, 'generated_deployment', return_value=proof) as deployment, \
             patch.object(module, 'exact_deployed_ci') as ci:
            command, result = module.command_for(env, API(), {'controller_sha256':'d'*64})
        deployment.assert_called_once()
        ci.assert_called_once()
        self.assertEqual(command, 'transition-v1 preprod tradebot-preprod-01 enter '
            + 'b'*40 + ' ' + 'c'*64 + ' ' + 'd'*64 + ' sha256:' + 'e'*64)
        self.assertEqual(result['operation'], 'enter')

    def test_enter_rechecks_published_source_ci_after_branch_moves(self):
        sha, branch = 'a'*40, 'preprod'
        candidate = {'source_sha':sha, 'source_branch':branch, 'source_ci_run_id':71}
        class API:
            def read(self, path):
                if path == '/actions/runs/71':
                    return {'event':'push', 'status':'completed', 'conclusion':'success',
                        'path':'.github/workflows/python-tests.yml', 'head_sha':sha,
                        'head_branch':branch, 'repository':{'full_name':module.pipeline.REPO}}
                if path.startswith('/actions/workflows/python-tests.yml/runs?'):
                    return {'workflow_runs':[{'id':71, 'event':'push', 'status':'completed',
                        'conclusion':'success', 'head_sha':sha, 'head_branch':branch}]}
                raise AssertionError(path)
        self.assertEqual(module.exact_deployed_ci(API(), candidate, branch), 71)
        with self.assertRaises(module.pipeline.PipelineHold):
            module.exact_deployed_ci(API(), candidate, 'main')

    def test_only_reviewed_result_gates_are_accepted(self):
        for operation, gate, origin, enabled in (
            ('enter', 'PP_LIVE_READY_OFF', 'pp-live-pp', False),
            ('leave', 'PP_GENERATED_RESTORED', 'generated-pp', False),
            ('on', 'PP_LIVE_ON', 'pp-live-pp', True),
            ('off', 'PP_LIVE_OFF', 'pp-live-pp', False),
        ):
            with self.subTest(operation=operation):
                expected = {'gate': gate, 'origin_id': origin, 'collector_enabled': enabled}
                self.assertEqual(module.validated_result(operation, expected), expected)
                with self.assertRaises(module.pipeline.PipelineHold):
                    module.validated_result(operation, {**expected, 'collector_enabled': not enabled})

    def test_dispatch_operation_choices_are_all_literal_strings(self):
        # YAML 1.1 treats a bare on/off as a boolean. GitHub rejected the
        # resulting operator choice at dispatch, before creating any job.
        from pathlib import Path
        import re
        import ast
        workflow = (Path(__file__).resolve().parent.parent /
                    'workflows/pp-live-control.yml').read_text()
        section = workflow.split('      operation:', 1)[1].split('      source_branch:', 1)[0]
        choices = re.search(r'^        options: (.+)$', section, re.MULTILINE)
        self.assertIsNotNone(choices)
        self.assertEqual(ast.literal_eval(choices.group(1)), ['enter', 'leave', 'on', 'off'])

    def test_workflow_uses_private_runner_and_shared_pp_concurrency(self):
        text = (HERE.parent/'workflows/pp-live-control.yml').read_text()
        self.assertIn('group: tradebot-preprod', text)
        self.assertIn('runs-on: [self-hosted, tradebot-private]', text)
        self.assertIn('environment: preprod', text)
        self.assertNotIn('PROD_DEPLOY_KEY', text)
        self.assertNotIn('cd-prod', text)

    def test_successful_host_transition_keeps_pipeline_pass_gate(self):
        with tempfile.TemporaryDirectory() as folder:
            for operation, host_gate, origin, enabled in (
                ('enter', 'PP_LIVE_READY_OFF', 'pp-live-pp', False),
                ('on', 'PP_LIVE_ON', 'pp-live-pp', True),
                ('off', 'PP_LIVE_OFF', 'pp-live-pp', False),
                ('leave', 'PP_GENERATED_RESTORED', 'generated-pp', False),
            ):
                with self.subTest(operation=operation):
                    report = Path(folder) / (operation + '.json')
                    env = {'PP_LIVE_OPERATION': operation, 'GITHUB_SHA': 'a' * 40,
                           'GITHUB_RUN_ID': '123', 'PIPELINE_REPORT': str(report)}
                    host = {'gate': host_gate, 'origin_id': origin,
                            'collector_enabled': enabled}
                    with patch.object(module.pipeline, 'GitHub'), \
                         patch.object(module.pipeline, 'target_profile', return_value={}), \
                         patch.object(module, 'command_for', return_value=('reviewed command',
                             {'operation': operation})), \
                         patch.object(module, 'transport', return_value=host), \
                         patch.object(module.os, 'environ', env), \
                         patch('sys.argv', ['pp_live_pipeline.py', 'execute']):
                        self.assertEqual(module.main(), 0)
                    result = json.loads(report.read_text())
                    self.assertEqual(result['gate'], 'PASS')
                    self.assertEqual(result['host_gate'], host_gate)
                    self.assertIs(result['collector_enabled'], enabled)


if __name__ == '__main__':
    unittest.main()
