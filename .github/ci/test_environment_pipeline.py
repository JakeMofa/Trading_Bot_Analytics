import datetime as dt
import io
import hashlib
import json
from pathlib import Path
import tempfile
import sys
import unittest
import urllib.request
from unittest.mock import patch
import zipfile

import environment_pipeline as p

SHA = 'a' * 40
DIGEST = hashlib.sha256(b'generated-source').hexdigest()
POLICY = 'c' * 64


def accepted():
    return {'gate': 'PASS', 'environment': 'preprod', 'instance': p.TARGETS['preprod'],
            'source_sha': SHA, 'artifact_sha256': DIGEST, 'policy_sha256': POLICY,
            'run_id': 72, 'run_attempt': 1, 'controls_sha':SHA, 'release_version': 'v0.1.0-rc.1',
            'registry':'ghcr.io/jakemofa/trading_bot_analytics/releases@sha256:'+DIGEST, 'checks': dict.fromkeys(p.REQUIRED_CHECKS, 'PASS'),
            'completed_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
            'paid_ai_enabled': False, 'retention_enabled': False,
            'live_collector_enabled': False, 'production_data_mounted': False, 'acceptance_scope': 'production_candidate','runtime_image_id':'sha256:'+'b'*64}


class API:
    def __init__(self, branch='main'):
        self.branch = branch
        self.head = SHA
        self.ci = [{'id': 12, 'head_sha': SHA, 'head_branch': branch, 'event': 'push',
                    'status': 'completed', 'conclusion': 'success', 'run_attempt': 1}]
        self.run = {'id': 72, 'event': 'workflow_dispatch', 'status': 'completed',
                    'conclusion': 'success', 'head_sha': SHA, 'head_branch': branch,
                    'path': '.github/workflows/cd-pp.yml', 'run_attempt': 1,
                    'repository': {'full_name': p.REPO}}
        self.proof = accepted()
        self.artifacts = [{'id': 99, 'name': 'preprod-acceptance-' + SHA, 'expired': False}]
        self.archive_name = 'deployment.json'

    def read(self, path, binary=False):
        if '/git/ref/' in path:
            return {'object': {'sha': self.head}}
        if '/python-tests.yml/runs?' in path:
            return {'workflow_runs': self.ci}
        if path.endswith('/artifacts?per_page=100'):
            return {'artifacts': self.artifacts}
        if path.endswith('/zip'):
            body = io.BytesIO()
            with zipfile.ZipFile(body, 'w') as zipped:
                zipped.writestr(self.archive_name, json.dumps(self.proof))
            return body.getvalue()
        return self.run


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.published = b'generated-source'
        self.release = patch('release_package.load_candidate', return_value=(
            {'version':'v0.1.0-rc.1', 'registry':'ghcr.io/jakemofa/trading_bot_analytics/releases@sha256:'+DIGEST,
             'artifact_sha256':DIGEST}, self.published))
        self.release.start();self.addCleanup(self.release.stop)
        self.original_archive = p.archive
        def staged(sha, destination):
            destination.write_bytes(self.published)
            return DIGEST
        self.staged = staged

    def env(self, branch='main'):
        return {'GITHUB_REPOSITORY': p.REPO, 'GITHUB_EVENT_NAME': 'workflow_dispatch',
                'GITHUB_REF_NAME': branch, 'GITHUB_SHA': SHA, 'GITHUB_RUN_ID': '72',
                'GITHUB_RUN_ATTEMPT': '1'}

    def profile(self, role):
        return {'instance': p.TARGETS[role], 'region': 'us-east-2', 'host': '192.0.2.1',
                'user': 'tradebot-' + role + '-deploy', 'runtime_qualified': True,
                'controller_sha256': DIGEST, 'qualification_commit': SHA, 'timeout_seconds': 810 if role=='preprod' else 600, 'work_seconds':600,'recovery_seconds':180}

    def test_exact_ci_and_main_production_route(self):
        self.assertEqual(p.qualify_ci(API(), 'production', SHA, self.env())['gate'], 'PASS')
        for branch in ('codex/feature', 'preprod'):
            self.assertEqual(p.qualify_ci(API(branch), 'preprod', SHA, self.env(branch))['gate'], 'PASS')
            with self.assertRaisesRegex(p.PipelineHold, 'branch'):
                p.qualify_ci(API(branch), 'production', SHA, self.env(branch))
        for env, sha in [({**self.env(), 'GITHUB_REPOSITORY': 'foreign/repo'}, SHA),
                         ({**self.env(), 'GITHUB_SHA': 'd'*40}, SHA), (self.env(), 'a'*7),
                         ({**self.env(), 'GITHUB_EVENT_NAME': 'pull_request'}, SHA)]:
            with self.subTest(env=env), self.assertRaises(p.PipelineHold):
                p.qualify_ci(API(), 'preprod', sha, env)

    def test_trusted_main_controls_can_qualify_distinct_preprod_source(self):
        api = API('preprod');controls_sha='f'*40
        original=api.read
        def read(path, **kwargs):
            if path == '/git/ref/heads/main':return {'object':{'sha':controls_sha}}
            return original(path,**kwargs)
        env={**self.env(), 'GITHUB_SHA':controls_sha,'SOURCE_BRANCH':'preprod'}
        with patch.object(api,'read',side_effect=read):
            self.assertEqual(p.qualify_ci(api,'preprod',SHA,env)['branch'],'preprod')
            with self.assertRaises(p.PipelineHold):p.qualify_ci(api,'production',SHA,env)
            with self.assertRaises(p.PipelineHold):p.qualify_ci(api,'preprod',SHA,{**env,'GITHUB_SHA':'e'*40})
            with self.assertRaises(p.PipelineHold):p.qualify_ci(api,'preprod',SHA,{**env,'GITHUB_REF_NAME':'preprod'})

    def test_preprod_controls_cannot_deploy_main_or_production(self):
        api=API('preprod');env={**self.env('preprod'),'SOURCE_BRANCH':'preprod'}
        self.assertEqual(p.qualify_ci(api,'preprod',SHA,env)['branch'],'preprod')
        for role,source in [('production','preprod'),('preprod','main'),('production','main')]:
            with self.subTest(role=role,source=source),self.assertRaises(p.PipelineHold):
                p.qualify_ci(api,role,SHA,{**env,'SOURCE_BRANCH':source})
        with self.assertRaises(p.PipelineHold):
            p.qualify_ci(api,'preprod',SHA,{**env,'GITHUB_REF_NAME':'codex/unreviewed'})

    def test_new_failed_or_rerunning_ci_cannot_reuse_old_success(self):
        for state, conclusion in [('completed', 'failure'), ('in_progress', None), ('completed', 'cancelled')]:
            api = API();api.ci.append({**api.ci[0], 'id': 13, 'status': state, 'conclusion': conclusion})
            with self.subTest(state=state), self.assertRaises(p.PipelineHold):
                p.qualify_ci(api, 'production', SHA, self.env())
        api = API();api.head = 'd'*40
        with self.assertRaisesRegex(p.PipelineHold, 'moved'):
            p.qualify_ci(api, 'production', SHA, self.env())

    def test_workflow_run_rejects_forks_prs_stale_triggers_and_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'event.json'
            event = {**API().ci[0], 'head_repository': {'full_name': p.REPO}}
            env = {**self.env(), 'GITHUB_EVENT_NAME': 'workflow_run', 'GITHUB_EVENT_PATH': str(path)}
            path.write_text(json.dumps({'workflow_run': event}))
            self.assertEqual(p.qualify_ci(API(), 'production', SHA, env)['gate'], 'PASS')
            for changes in [{'event': 'pull_request'}, {'conclusion': 'failure'}, {'head_sha': 'd'*40},
                            {'head_repository': {'full_name': 'foreign/repo'}}, {'id': 11}, {'run_attempt': 2}]:
                path.write_text(json.dumps({'workflow_run': {**event, **changes}}))
                with self.subTest(changes=changes), self.assertRaises(p.PipelineHold):
                    p.qualify_ci(API(), 'production', SHA, env)

    def test_current_unqualified_targets_stop_before_bundle_or_ssh(self):
        with patch.object(p, 'archive') as bundle, patch.object(p, 'transport') as transport:
            for role in p.TARGETS:
                with self.assertRaisesRegex(p.PipelineHold, 'NOT QUALIFIED'):
                    p.deploy(API(), role, SHA, '.github/deploy/targets.json', self.env())
            bundle.assert_not_called();transport.assert_not_called()

    def test_wrong_host_identity_user_hash_or_budget_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'targets.json'
            for changes in [{'instance': p.TARGETS['production']}, {'region': 'us-west-2'},
                            {'user': 'ubuntu'}, {'controller_sha256': ''}, {'qualification_commit': ''},
                            {'timeout_seconds': 1200}, {'host': 'host;bad'}, {'runtime_qualified': 'true'}]:
                path.write_text(json.dumps({'preprod': {**self.profile('preprod'), **changes}}))
                with self.subTest(changes=changes), self.assertRaises(p.PipelineHold):
                    p.target_profile('preprod', path)

    def test_pp_acceptance_requires_exact_run_artifact_source_policy_and_attempt(self):
        self.assertEqual(p.preprod_proof(API(), 72, SHA, DIGEST, POLICY)['gate'], 'PASS')
        for changes in [{'source_sha': 'd'*40}, {'artifact_sha256': 'e'*64}, {'policy_sha256': 'e'*64},
                        {'environment': 'production'}, {'instance': p.TARGETS['production']},
                        {'gate': 'BLOCKED'}, {'run_id': 71}, {'run_attempt': 2}, {'checks': {}},
                        {'live_collector_enabled': True}, {'production_data_mounted': True},
                        {'paid_ai_enabled': True}, {'retention_enabled': True},
                        {'completed_at_utc': (dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=2)).isoformat()},
                        {'completed_at_utc': (dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=1)).isoformat()}]:
            api = API();api.proof.update(changes)
            with self.subTest(changes=changes), self.assertRaises(p.PipelineHold):
                p.preprod_proof(api, 72, SHA, DIGEST, POLICY)

    def test_generated_scope_cannot_authorize_production(self):
        api=API();api.proof['acceptance_scope']='generated_only'
        self.assertEqual(p.validate_result(api.proof,'preprod',SHA,DIGEST)['acceptance_scope'],'generated_only')
        with self.assertRaisesRegex(p.PipelineHold,'generated-only'):
            p.preprod_proof(api,72,SHA,DIGEST,POLICY)
        del api.proof['acceptance_scope']
        with self.assertRaisesRegex(p.PipelineHold,'scope'):
            p.validate_result(api.proof,'preprod',SHA,DIGEST)

    def test_wrong_workflow_failed_run_or_artifact_layout_cannot_authorize_prod(self):
        for changes in [{'event': 'push'}, {'conclusion': 'failure'}, {'status': 'in_progress'},
                        {'head_branch': 'untrusted'}, {'head_sha': 'd'*40},
                        {'path': '.github/workflows/other.yml'}, {'repository': {'full_name': 'foreign/repo'}}]:
            api = API();api.run.update(changes)
            with self.subTest(changes=changes), self.assertRaises(p.PipelineHold):
                p.preprod_proof(api, 72, SHA, DIGEST, POLICY)

    def test_remote_extra_fields_are_not_persisted_and_redirects_do_not_forward_tokens(self):
        result = p.validate_result({**accepted(), 'unexpected_log': 'synthetic-sensitive-value'}, 'preprod', SHA, DIGEST)
        self.assertNotIn('unexpected_log', result)
        self.assertNotIn('synthetic-sensitive-value', json.dumps(result))
        request = urllib.request.Request('https://api.github.com/repos/example',
                                         headers={'Authorization': 'Bearer synthetic'})
        redirect = p.SafeRedirect().redirect_request(request, None, 302, 'Found', {}, 'https://example.invalid/blob')
        self.assertIsNone(redirect.get_header('Authorization'))
        with self.assertRaises(p.PipelineHold):
            p.SafeRedirect().redirect_request(request, None, 302, 'Found', {}, 'http://example.invalid/blob')
        for mode in ('missing', 'expired', 'duplicate', 'path'):
            api = API()
            if mode == 'missing':api.artifacts = []
            if mode == 'expired':api.artifacts[0]['expired'] = True
            if mode == 'duplicate':api.artifacts *= 2
            if mode == 'path':api.archive_name = '../deployment.json'
            with self.subTest(mode=mode), self.assertRaises(p.PipelineHold):
                p.preprod_proof(api, 72, SHA, DIGEST, POLICY)

    def test_transport_host_pins_environment_keys_and_one_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)/'bundle';bundle.write_bytes(b'generated')
            env = {'PP_DEPLOY_KEY': 'synthetic-key', 'PP_DEPLOY_KNOWN_HOSTS': 'synthetic-pin'}
            def success(command, source, timeout):
                key = Path(command[command.index('-i')+1])
                self.assertEqual(key.stat().st_mode & 0o777, 0o600)
                self.assertIn('StrictHostKeyChecking=yes', command)
                self.assertIn('ConnectionAttempts=1', command)
                self.assertEqual(timeout, 810)
                self.assertNotIn('synthetic-key', ' '.join(command))
                self.key = key
                return type('Result', (), {'returncode': 0, 'stdout': json.dumps(accepted()).encode()})()
            with patch.object(p, 'bounded_process', side_effect=success) as run:
                p.transport(self.profile('preprod'), 'preprod', SHA, DIGEST, bundle, env)
                self.assertEqual(run.call_count, 1)
            self.assertFalse(self.key.exists())
            with patch.object(p, 'bounded_process') as run, self.assertRaises(p.PipelineHold):
                p.transport(self.profile('production'), 'production', SHA, DIGEST, bundle, env)
            run.assert_not_called()

    def test_failed_or_timed_out_transport_never_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)/'bundle';bundle.write_bytes(b'generated')
            env = {'PP_DEPLOY_KEY': 'synthetic-key', 'PP_DEPLOY_KNOWN_HOSTS': 'synthetic-pin'}
            for effect in [p.subprocess.TimeoutExpired('ssh', 600),
                           type('Result', (), {'returncode': 1, 'stdout': b''})()]:
                with patch.object(p, 'bounded_process', side_effect=effect if isinstance(effect, Exception) else None,
                                  return_value=effect) as run:
                    with self.assertRaises((p.PipelineHold, p.subprocess.TimeoutExpired)):
                        p.transport(self.profile('preprod'), 'preprod', SHA, DIGEST, bundle, env)
                    self.assertEqual(run.call_count, 1)

    def test_generated_child_output_and_deadline_are_bounded_and_reaped(self):
        real_popen = p.subprocess.Popen
        for script, timeout in [('import time;time.sleep(10)', 0.05),
                                ('import sys;sys.stdout.write("x"*131072);sys.stdout.flush()', 2),
                                ('import sys;sys.stderr.write("x"*32768);sys.stderr.flush()', 2)]:
            children = []
            def start(*args, **kwargs):
                process = real_popen(*args, **kwargs);children.append(process);return process
            with self.subTest(script=script), patch.object(p.subprocess, 'Popen', side_effect=start):
                with self.assertRaises(p.PipelineHold):
                    p.bounded_process([sys.executable, '-c', script], p.subprocess.DEVNULL, timeout)
                self.assertEqual(len(children), 1)
                self.assertIsNotNone(children[0].poll())
        result = p.bounded_process([sys.executable, '-c', 'print("ok")'], p.subprocess.DEVNULL, 2)
        self.assertEqual((result.returncode, result.stdout), (0, b'ok\n'))

    def test_pp_proof_is_required_before_production_transport(self):
        with patch.object(p, 'target_profile', return_value=self.profile('production')), \
             patch.object(p, 'archive', side_effect=self.staged), patch.object(p, 'transport') as transport, \
             patch.object(p, 'preprod_proof', side_effect=p.PipelineHold('no proof')):
            with self.assertRaises(p.PipelineHold):
                p.deploy(API(), 'production', SHA, '.github/deploy/targets.json', self.env(), '72')
            transport.assert_not_called()

    def test_successful_deployment_report_is_runtime_evidence_not_source_ci(self):
        with patch.object(p, 'target_profile', return_value=self.profile('preprod')), \
             patch.object(p, 'archive', side_effect=self.staged), \
             patch.object(p, 'transport', return_value=p.validate_result(accepted(), 'preprod', SHA, DIGEST)) as transport:
            report = p.deploy(API(), 'preprod', SHA, '.github/deploy/targets.json', self.env())
            self.assertEqual(report['scope'], 'exact-source runtime deployment and acceptance')
            self.assertEqual(report['source_sha'], SHA)
            self.assertEqual(report['run_id'], 72)
            transport.assert_called_once()

    def test_branch_moving_after_preflight_stops_before_ssh(self):
        api = API();original = api.read;reads = []
        def moved(path, **kwargs):
            if '/git/ref/' in path:
                reads.append(path)
                if len(reads) > 1:return {'object': {'sha': 'd'*40}}
            return original(path, **kwargs)
        with patch.object(api, 'read', side_effect=moved), \
             patch.object(p, 'target_profile', return_value=self.profile('preprod')), \
             patch.object(p, 'archive', side_effect=self.staged), patch.object(p, 'transport') as transport:
            with self.assertRaisesRegex(p.PipelineHold, 'moved before deployment'):
                p.deploy(api, 'preprod', SHA, '.github/deploy/targets.json', self.env())
            transport.assert_not_called()

    def test_workflow_jobs_keep_secrets_after_preflight_and_legacy_routes_gated(self):
        for short, role in [('pp', 'preprod'), ('prod', 'production')]:
            text = Path('.github/workflows/cd-'+short+'.yml').read_text()
            self.assertIn('needs: preflight', text)
            before, after = text.split('\n  deploy:', 1)
            self.assertNotIn('secrets.', before)
            self.assertIn('environment: '+role, after)
            self.assertNotIn('pull_request_target', text)
            self.assertNotIn('  push:', text)
            self.assertIn('timeout-minutes: 15', text)
            self.assertIn('ref: ${{ github.sha }}' if short=='pp' else 'ref: main', text)
            self.assertIn('RELEASE_VERSION:', text)
            text = Path('.github/workflows/ci-'+short+'.yml').read_text()
            self.assertIn('workflows: ["CI — Tradebot checks"]', text)
            self.assertNotIn('secrets.', text)
            self.assertNotIn('pip install', text)
        self.assertFalse(Path('.github/workflows/deploy-tradebot.yml').exists(), 'independent PR must not import the old deployment bypass')


if __name__ == '__main__':
    unittest.main()
