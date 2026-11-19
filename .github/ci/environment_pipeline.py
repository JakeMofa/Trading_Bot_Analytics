"""Environment CI qualification and guarded, manual deployment transport.

Source CI is reused, never relabelled as runtime acceptance. Unqualified target
controllers stop before secrets, bundle creation, or any SSH connection.
"""
import argparse
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile

REPO = 'JakeMofa/Trading_Bot_Analytics'
SHA = re.compile(r'[0-9a-f]{40}')
DIGEST = re.compile(r'[0-9a-f]{64}')
TARGETS = {'preprod': 'tradebot-preprod-01', 'production': 'tradebot-analytics-01'}
WORKFLOWS = {'preprod': 'cd-pp.yml', 'production': 'cd-prod.yml'}
REQUIRED_CHECKS = {'api', 'sse', 'schema', 'migration', 'data_correctness',
                   'collector_ownership', 'disabled_flags', 'recovery',
                   'freshness', 'market_identity'}
PREPROD_REQUIRED_CHECKS = REQUIRED_CHECKS | {'operator_control'}
PP_INSTALLED_CONTROLLER = '1e10e1064d37a1629098d90793d3ad7719d127368881b8305f49ce8c1a4907c5'
PP_IDENTITY_COMMIT = '414e3c232ba54d61bc4a71e8315fd3d1b1e620e3'
PP_IDENTITY_RUN = 44502043684
CONTROLLER_REASONS = frozenset({
    'entrypoint_precondition_failed', 'generated_runtime_check_failed',
    'generated_api_readiness_timeout', 'generated_operator_readiness_timeout',
    'generated_api_state_check_failed', 'generated_operator_state_check_failed',
    'controller_action_failed', 'controller_digest_mismatch', 'wrong_host_binding',
    'unsafe_host_binding', 'authority_binding_mismatch', 'authority_changed',
    'authority_expired_or_invalid', 'authority_nonce_invalid',
    'authority_not_validated', 'authority_scope_mismatch', 'child_deadline_exceeded',
    'child_failed', 'child_io_bound', 'child_output_bound', 'deadline_exceeded',
    'archive_digest_mismatch', 'archive_source_mismatch', 'archive_forbidden_content',
    'archive_unsafe_path', 'archive_unsafe_type', 'archive_file_bound',
    'unsafe_staging_root', 'incomplete_runtime_acceptance', 'unsafe_runtime_flags',
    'prior_runtime_evidence_invalid', 'recovery_not_proven',
    'existing_postgres_required', 'postgres_identity_mismatch',
    'postgres_durability_disabled', 'postgres_resource_mismatch',
    'unsafe_history_reader_credential', 'archive_history_runtime_flag_mismatch',
    'history_reader_proof_changed', 'unsafe_history_reader_proof',
    'incomplete_history_reader_proof', 'unsafe_history_reader_authority',
    'history_reader_identity_mismatch', 'unqualified_history_reader_profile',
    'pp_filesystem_database_identity', 'pp_filesystem_volume_binding',
    'pp_filesystem_source_binding', 'pp_filesystem_device_mismatch',
    'pp_filesystem_container_identity', 'pp_filesystem_runtime_binding',
    'pp_filesystem_reserve', 'pp_filesystem_sample_unavailable',
    'insufficient_host_headroom', 'invalid_inventory_evidence',
    'outbox_inventory_exceeds_release_bound','outbox_inventory_invalid', 'unexpected_outbox_origin',
    'prior_oneoff_requires_operator_inspection', 'inventory_exceeds_generated_bound',
    'database_changed_after_writer_fence', 'candidate_writer_fence_failed',
    'prior_ack_state_unproven', 'pre_migration_database_changed',
    'pre_migration_restore_not_proven', 'prior_container_identity_changed',
    'prior_stopped_container_changed', 'partial_prior_recovery_still_running',
    'explicit_migration_not_proven', 'generated_bootstrap_not_proven',
    'generated_acceptance_incomplete', 'api_not_healthy',
    'freshness_or_market_not_proven', 'runtime_flag_mismatch',
    'runtime_image_or_process_mismatch', 'runtime_secret_binding_mismatch',
    'schema_check_not_proven', 'wrong_postgres_environment',
    'wrong_postgres_project', 'wrong_postgres_volume',
    'acknowledged_prediction_not_preserved', 'ambiguous_deployment_oneoff',
    'archive_compressed_bound', 'archive_duplicate_member', 'archive_expanded_bound',
    'archive_member_bound', 'archive_path_conflict', 'archive_runtime_files_missing',
    'archive_unsafe_mode', 'authority_already_consumed', 'authority_timezone_required',
    'built_image_binding_mismatch', 'cpu_limit_mismatch', 'database_network_not_internal',
    'database_volume_changed', 'deployment_oneoff_not_removed',
    'deployment_oneoff_still_running', 'explicit_migration_required',
    'host_api_loopback_unavailable', 'host_api_response_too_large',
    'host_api_wrong_state', 'host_operator_loopback_unavailable',
    'invalid_built_image_id', 'invalid_child_command', 'invalid_command',
    'invalid_container_identity', 'invalid_digest', 'invalid_memory_limit',
    'invalid_recovery_anchor', 'invalid_runtime_evidence', 'invalid_source_sha',
    'invalid_work_budget', 'loopback_port_not_published',
    'migration_changed_existing_evidence', 'migration_recovery_evidence_changed',
    'missing_container_inspection', 'missing_runtime_service',
    'missing_security_option', 'oneoff_ownership_mismatch',
    'oneoff_restart_not_fenced', 'operator_not_default_off',
    'operator_on_get_unexpectedly_accepted', 'operator_on_route_mismatch',
    'operator_response_too_large', 'operator_unauthorized_response_mismatch',
    'operator_without_auth_accepted', 'postgres_identity_not_verified',
    'postgres_restarted_during_api_recovery', 'preflight_required',
    'prior_api_recovery_timeout', 'prior_database_postcheck_changed',
    'prior_postgres_not_bound', 'prior_runtime_duplicate_container',
    'prior_runtime_image_unproven', 'prior_runtime_missing_or_ambiguous',
    'prior_schema_ledger_unproven', 'resource_limit_mismatch',
    'restart_persistence_not_proven', 'root_entrypoint_required',
    'runtime_command_or_project_mismatch', 'runtime_network_mismatch',
    'runtime_public_port', 'runtime_pull_not_allowed',
    'runtime_resource_or_privilege_mismatch', 'runtime_unexpected_data_mount',
    'trusted_file_too_large', 'unbound_image_id', 'unbound_service_image',
    'unbounded_application_tmpfs', 'unbounded_container_logs',
    'unexpected_application_environment', 'unexpected_application_secret',
    'unexpected_compose_project_or_services', 'unexpected_postgres_mount',
    'unexpected_postgres_secret_mapping', 'unexpected_pre_migration_oneoff',
    'unexpected_published_port', 'unexpected_restart_policy',
    'unexpected_secret', 'unexpected_service_network',
    'unowned_container_blocks_runtime_fence', 'unprepared_foundation_secret',
    'unprepared_or_unexpected_postgres_mount', 'unprepared_runtime_secret',
    'unqualified_host_os', 'unqualified_python_base', 'unreviewed_postgres_command',
    'unsafe_api_loopback_network', 'unsafe_application_environment',
    'unsafe_application_runtime', 'unsafe_database_network',
    'unsafe_database_volume', 'unsafe_loopback_port', 'unsafe_operator_token',
    'unsafe_parent', 'unsafe_postgres_mount', 'unsafe_postgres_runtime',
    'unsafe_postgres_secret_mount', 'unsafe_secret_directory',
    'unsafe_secret_path', 'unsafe_service_override', 'unsafe_trusted_file',
    'unsafe_trusted_file_mode', 'unsupported_deployment_oneoff',
    'wrong_acceptance_scope', 'wrong_postgres_network', 'wrong_target',
})
CONTROLLER_STAGES = frozenset({'validation', 'preflight', 'build', 'migrate', 'start', 'smoke'})
CONTROLLER_RECOVERY = frozenset({
    'unproven_preserve_and_inspect', 'prior_runtime_unchanged',
    'prior_runtime_restored_pre_migration', 'stop_candidate_keep_database',
    'forward_candidate',
})
ENTRYPOINT_REASONS = frozenset({
    'pp_filesystem_database_identity',
    'pp_filesystem_volume_binding',
    'pp_filesystem_source_binding',
    'pp_filesystem_device_mismatch',
    'pp_filesystem_container_identity',
    'pp_filesystem_runtime_binding',
    'pp_filesystem_reserve',
    'pp_filesystem_sample_unavailable',
    'entrypoint_precondition_failed', 'generated_runtime_check_failed',
    'generated_api_readiness_timeout', 'generated_operator_readiness_timeout',
    'generated_api_state_check_failed', 'generated_operator_state_check_failed',
})


def required_checks(role):
    return PREPROD_REQUIRED_CHECKS if role == 'preprod' else REQUIRED_CHECKS


class PipelineHold(ValueError):
    """Only fixed, local diagnostic messages; never remote payloads or secrets."""


class ControllerFailure(PipelineHold):
    """A failed, single SSH attempt with only allowlisted controller codes."""

    def __init__(self, diagnostic):
        super().__init__('deployment controller failed; no automatic retry')
        self.diagnostic = diagnostic


def require(value, message):
    if not value:
        raise PipelineHold(message)


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        require(urllib.parse.urlparse(url).scheme == 'https', 'HTTPS redirect required')
        redirected = super().redirect_request(request, response, code, message, headers, url)
        if redirected:
            redirected.remove_header('Authorization')
        return redirected


class GitHub:
    def read_registry(self, page):
        require(isinstance(page, int) and 1 <= page <= 100, 'bounded registry page required')
        return self._read('https://api.github.com/users/JakeMofa/packages/container/trading_bot_analytics%2Freleases/versions?per_page=100&page='+str(page))

    def _read(self, url, binary=False, max_bytes=1024 * 1024, *, artifact_zip=False):
        # Actions artifact ZIP redirects with GitHub's JSON media type, while
        # release assets require octet-stream to return their bytes.
        request = urllib.request.Request(url,
            headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
                     'Accept': ('application/octet-stream' if binary and not artifact_zip
                                else 'application/vnd.github+json')})
        with urllib.request.build_opener(SafeRedirect()).open(request, timeout=20) as response:
            data = response.read(max_bytes + 1)
        require(len(data) <= max_bytes, 'API evidence exceeds size bound')
        return data if binary else json.loads(data)

    def read(self, path, binary=False, max_bytes=1024 * 1024):
        require(path.startswith('/') and not path.startswith('//'), 'repository-relative API path required')
        artifact_zip = binary and path.startswith('/actions/artifacts/') and path.endswith('/zip')
        return self._read('https://api.github.com/repos/' + REPO + path, binary, max_bytes,
                          artifact_zip=artifact_zip)


def branch_allowed(role, branch):
    return branch == 'main' if role == 'production' else (
        branch in {'main', 'preprod'} or bool(re.fullmatch(r'codex/[A-Za-z0-9._/-]+', branch)))


def qualify_ci(api, role, sha, env):
    require(role in TARGETS and SHA.fullmatch(sha), 'role and full source SHA required')
    require(env.get('GITHUB_REPOSITORY') == REPO, 'wrong repository')
    if env.get('GITHUB_EVENT_NAME') == 'workflow_run':
        event = json.loads(Path(env['GITHUB_EVENT_PATH']).read_text())['workflow_run']
        require(event.get('event') == 'push' and event.get('conclusion') == 'success', 'successful push trigger required')
        require(event.get('head_sha') == sha and event.get('head_repository', {}).get('full_name') == REPO,
                'trigger source/repository mismatch')
        branch = event['head_branch']
    else:
        require(env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch', 'manual or successful source CI trigger required')
        branch = env.get('SOURCE_BRANCH', env.get('GITHUB_REF_NAME', ''))
        if env.get('SOURCE_BRANCH'):
            control_branch=env.get('GITHUB_REF_NAME')
            require(control_branch=='main' or (role=='preprod' and control_branch=='preprod' and branch=='preprod'),
                    'controls must come from main or exact preprod for PP only')
            controls = api.read('/git/ref/heads/'+control_branch)
            require(controls['object']['sha'] == env.get('GITHUB_SHA'), 'control branch moved')
        else:
            require(env.get('GITHUB_SHA') == sha, 'dispatch SHA differs from source')
    require(branch_allowed(role, branch), 'branch cannot qualify for this environment')
    current = api.read('/git/ref/heads/' + urllib.parse.quote(branch, safe='/'))
    require(current['object']['sha'] == sha, 'source branch moved')
    runs = api.read('/actions/workflows/python-tests.yml/runs?event=push&head_sha=' + sha + '&per_page=100')['workflow_runs']
    candidates = [r for r in runs if r.get('head_sha') == sha and r.get('head_branch') == branch
                  and r.get('event') == 'push']
    require(candidates, 'exact source push CI missing')
    latest = max(candidates, key=lambda r: (r['id'], r.get('run_attempt', 1)))
    require(latest.get('status') == 'completed' and latest.get('conclusion') == 'success',
            'latest exact source CI is not successful')
    if env.get('GITHUB_EVENT_NAME') == 'workflow_run':
        require(latest['id'] == event['id'] and latest.get('run_attempt', 1) == event.get('run_attempt', 1),
                'superseded CI trigger')
    return {'source_sha': sha, 'branch': branch, 'source_ci_run_id': latest['id'],
            'source_ci_attempt': latest.get('run_attempt', 1), 'environment': role,
            'gate': 'PASS', 'scope': 'source CI only; deployment/acceptance NOT PERFORMED'}


def target_profile(role, path):
    profile = json.loads(Path(path).read_text())[role]
    require(profile.get('instance') == TARGETS[role] and profile.get('region') == 'us-east-2',
            'target identity mismatch')
    require(profile.get('runtime_qualified') is True, 'runtime/controller NOT QUALIFIED; deployment remains disabled')
    require(DIGEST.fullmatch(profile.get('controller_sha256', '')), 'qualified controller hash missing')
    require(profile.get('qualification_commit') and SHA.fullmatch(profile['qualification_commit']),
            'controller qualification commit missing')
    if role == 'preprod':
        require(profile.get('work_seconds') == 600 and profile.get('recovery_seconds') == 180
                and profile.get('timeout_seconds') == 810, 'reviewed PP work/recovery/transport budgets required')
        require(profile['controller_sha256'] == PP_INSTALLED_CONTROLLER
                and profile['qualification_commit'] == PP_IDENTITY_COMMIT,
                'PP installed controller release binding mismatch')
        evidence_name = profile.get('qualification_evidence')
        require(type(evidence_name) is str and re.fullmatch(
            r'docs/PLAN/evidence/pp-controller-identity-[0-9]{4}-[0-9]{2}-[0-9]{2}(?:-[0-9a-f]{8})?\.json',
            evidence_name), 'PP controller identity evidence path missing')
        evidence_path = Path(evidence_name)
        require(evidence_path.is_file() and not evidence_path.is_symlink()
                and evidence_path.stat().st_size <= 4096, 'PP controller identity evidence unavailable')
        evidence = json.loads(evidence_path.read_text())
        run = evidence.get('qualification_run')
        require(evidence.get('scope') == 'pp_controller_identity_only'
                and evidence.get('environment') == role
                and evidence.get('instance') == profile['instance']
                and evidence.get('controller_sha256') == profile['controller_sha256']
                and evidence.get('qualification_commit') == profile['qualification_commit']
                and evidence.get('qualification_result') == 'PASS'
                and evidence.get('artifact_gate') == 'IDENTITY_PASS'
                and evidence.get('artifact_database_changed') is False
                and type(run) is int and run == PP_IDENTITY_RUN
                and evidence.get('artifact_name') == 'pp-controller-identity-' + str(run),
                'PP controller profile and identity evidence mismatch')
    else:
        require(profile.get('timeout_seconds') == 600, 'reviewed production controller deadline required')
    require(profile.get('user') == 'tradebot-' + role + '-deploy', 'dedicated deployment identity required')
    require(re.fullmatch(r'[A-Za-z0-9.-]+', profile.get('host', '')), 'invalid target host')
    return profile


def archive(sha, destination):
    subprocess.run(['git', 'archive', '--format=tar.gz', '--output=' + str(destination), sha],
                   check=True, timeout=30)
    require(destination.stat().st_size <= 16 * 1024**2, 'source archive exceeds 16 MiB bound')
    return hashlib.sha256(destination.read_bytes()).hexdigest()


def preprod_proof(api, run_id, sha, artifact_digest, policy_digest):
    require(str(run_id).isdigit() and int(run_id) > 0, 'successful PP deployment run ID required')
    run = api.read('/actions/runs/' + str(run_id))
    require(run.get('event') == 'workflow_dispatch' and run.get('status') == 'completed'
            and run.get('conclusion') == 'success'
            and run.get('path') == '.github/workflows/cd-pp.yml'
            and branch_allowed('preprod', run.get('head_branch', ''))
            and run.get('repository', {}).get('full_name') == REPO,
            'PP run identity, source or result mismatch')
    artifacts = api.read('/actions/runs/' + str(run_id) + '/artifacts?per_page=100')['artifacts']
    matches = [a for a in artifacts if a.get('name') == 'preprod-acceptance-' + sha and not a.get('expired')]
    require(len(matches) == 1, 'unique retained PP acceptance artifact required')
    raw = api.read('/actions/artifacts/' + str(matches[0]['id']) + '/zip', binary=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as zipped:
        require(zipped.namelist() == ['deployment.json'], 'unexpected acceptance archive contents')
        require(zipped.getinfo('deployment.json').file_size <= 65536, 'acceptance report exceeds bound')
        proof = json.loads(zipped.read('deployment.json'))
    require(proof.get('source_sha') == sha and proof.get('artifact_sha256') == artifact_digest
            and proof.get('policy_sha256') == policy_digest and proof.get('environment') == 'preprod'
            and proof.get('instance') == TARGETS['preprod'] and proof.get('gate') == 'PASS'
            and proof.get('run_id') == int(run_id) and proof.get('run_attempt') == run.get('run_attempt', 1)
            and proof.get('controls_sha') == run.get('head_sha'),
            'PP acceptance bindings mismatch')
    require(proof.get('checks') == dict.fromkeys(PREPROD_REQUIRED_CHECKS, 'PASS'), 'PP acceptance checks incomplete')
    require(proof.get('acceptance_scope') == 'production_candidate',
            'generated-only PP checks cannot authorize production promotion')
    validate_result(proof, 'preprod', sha, artifact_digest)
    issued = dt.datetime.fromisoformat(proof['completed_at_utc'])
    require(issued.utcoffset() is not None, 'timezone required in PP evidence')
    age = (dt.datetime.now(dt.timezone.utc) - issued).total_seconds()
    require(0 <= age <= 24 * 3600, 'PP acceptance is expired or in the future')
    return proof


def validate_result(result, role, sha, digest):
    require(result.get('gate') == 'PASS' and result.get('environment') == role
            and result.get('instance') == TARGETS[role] and result.get('source_sha') == sha
            and result.get('artifact_sha256') == digest, 'controller result mismatch')
    require(result.get('checks') == dict.fromkeys(required_checks(role), 'PASS'), 'controller acceptance incomplete')
    require(result.get('paid_ai_enabled') is False and result.get('retention_enabled') is False,
            'paid AI and retention must stay OFF for this release route')
    if role == 'preprod':
        require(result.get('live_collector_enabled') is False and result.get('production_data_mounted') is False,
                'PP must not collect live markets or mount production data')
        require(result.get('acceptance_scope') in ('generated_only','production_candidate'),
                'explicit PP acceptance scope required')
        require(re.fullmatch(r'sha256:[0-9a-f]{64}',result.get('runtime_image_id','')) is not None,
                'actual PP runtime image identity required')
    # Never persist arbitrary controller stdout fields (logs or credentials).
    safe = {'gate', 'environment', 'instance', 'source_sha', 'artifact_sha256',
            'checks', 'paid_ai_enabled', 'retention_enabled'}
    if role == 'preprod':
        safe.update({'live_collector_enabled', 'production_data_mounted', 'acceptance_scope', 'runtime_image_id'})
    return {key: result[key] for key in safe}


def blocked_controller_diagnostic(raw, role, sha, digest):
    """Discard arbitrary controller output; retain only fixed diagnostic codes.

    A nonzero SSH exit can also contain sshd text, a traceback, or a partial
    report. None of those bytes may enter Actions artifacts or summaries.
    """
    generic = {'gate': 'BLOCKED', 'reason': 'controller_report_unavailable'}
    if not isinstance(raw, bytes) or not raw or len(raw) > 4096:
        return generic
    try:
        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('duplicate controller field')
                result[key] = value
            return result
        report = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_pairs)
    except (UnicodeError, ValueError, RecursionError):
        return generic
    if (not isinstance(report, dict) or report.get('gate') != 'BLOCKED'
            or report.get('environment') != role
            or report.get('instance', TARGETS[role]) != TARGETS[role]):
        return generic
    bound = 'source_sha' in report or 'artifact_sha256' in report
    if bound:
        if report.get('source_sha') != sha or report.get('artifact_sha256') != digest:
            return generic
    elif (type(report.get('reason')) is not str or report['reason'] not in ENTRYPOINT_REASONS
          or 'failed_stage' in report or 'recovery' in report):
        # The root entrypoint emits a small unbound precondition report. The
        # controller core must bind any richer stage/recovery evidence to the
        # exact source and artifact sent by this single SSH attempt.
        return generic
    reason = report.get('reason')
    safe = {'gate': 'BLOCKED', 'reason': reason if type(reason) is str and reason in CONTROLLER_REASONS
            else 'controller_reason_unclassified'}
    stage = report.get('failed_stage')
    if type(stage) is str and stage in CONTROLLER_STAGES:
        safe['stage'] = stage
    recovery = report.get('recovery')
    if isinstance(recovery, dict):
        code = recovery.get('strategy', recovery.get('status'))
        if type(code) is str and code in CONTROLLER_RECOVERY:
            safe['recovery'] = code
    return safe


def transport(profile, role, sha, digest, bundle, env):
    # No fallback to repository production credentials or the operator's human key.
    prefix = 'PP' if role == 'preprod' else 'PROD'
    key = env.get(prefix + '_DEPLOY_KEY', '')
    known = env.get(prefix + '_DEPLOY_KNOWN_HOSTS', '')
    require(key and known, 'environment-specific key and host pin required')
    with tempfile.TemporaryDirectory(prefix='tradebot-environment-') as directory:
        root = Path(directory)
        for name, value in [('key', key), ('known_hosts', known)]:
            p = root / name
            p.write_text(value + '\n')
            p.chmod(0o600)
        command = ['ssh', '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
                   '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=10',
                   '-o', 'ConnectionAttempts=1', '-o', 'ServerAliveInterval=15',
                   '-o', 'ServerAliveCountMax=2', '-o', 'UserKnownHostsFile=' + str(root/'known_hosts'),
                   '-i', str(root/'key'), profile['user'] + '@' + profile['host'],
                   'deploy-v1 ' + role + ' ' + profile['instance'] + ' ' + sha + ' ' + digest + ' ' + profile['controller_sha256']]
        with bundle.open('rb') as source:
            completed = bounded_process(command, source, profile['timeout_seconds'])
        if completed.returncode != 0:
            raise ControllerFailure(blocked_controller_diagnostic(completed.stdout, role, sha, digest))
        require(len(completed.stdout) <= 65536, 'controller report exceeds bound')
        return validate_result(json.loads(completed.stdout), role, sha, digest)


def bounded_process(command, source, timeout):
    """Bound both streams and terminate/reap the owned SSH child on failure."""
    process = subprocess.Popen(command, stdin=source, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    selector = selectors.DefaultSelector()
    streams = {'stdout': bytearray(), 'stderr': bytearray()}
    deadline = time.monotonic() + timeout
    try:
        selector.register(process.stdout, selectors.EVENT_READ, 'stdout')
        selector.register(process.stderr, selectors.EVENT_READ, 'stderr')
        while selector.get_map():
            remaining = deadline - time.monotonic()
            require(remaining > 0, 'deployment controller deadline exceeded')
            for ready, _ in selector.select(min(remaining, 1)):
                data = os.read(ready.fd, 8192)
                if not data:
                    selector.unregister(ready.fileobj)
                    continue
                stream = streams[ready.data]
                stream.extend(data)
                require(len(stream) <= (65536 if ready.data == 'stdout' else 8192),
                        'deployment controller output exceeds bound')
        require(deadline > time.monotonic(), 'deployment controller deadline exceeded')
        code = process.wait(timeout=max(0.001, deadline-time.monotonic()))
        return subprocess.CompletedProcess(command, code, bytes(streams['stdout']), b'')
    finally:
        selector.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()


def deploy(api, role, sha, profile_path, env, pp_run_id=''):
    require(env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch', 'manual deployment required')
    control_branch=env.get('GITHUB_REF_NAME')
    require(control_branch=='main' or (role=='preprod' and control_branch=='preprod' and env.get('SOURCE_BRANCH')=='preprod'),
            'deployment controls require main or exact preprod for PP only')
    qualified = qualify_ci(api, role, sha, env)
    profile = target_profile(role, profile_path)  # Before any SSH or bundle creation.
    from release_package import load_candidate
    candidate, published = load_candidate(api, env.get('RELEASE_VERSION', ''), sha)
    policy_digest = hashlib.sha256(Path(profile_path).read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='tradebot-source-') as directory:
        bundle = Path(directory)/'source.tar.gz'
        bundle.write_bytes(published)
        digest = hashlib.sha256(published).hexdigest()
        require(digest == candidate['artifact_sha256'], 'published source digest mismatch')
        if role == 'production':
            proof = preprod_proof(api, pp_run_id, sha, digest, policy_digest)
            require(proof.get('release_version') == candidate['version'] and proof.get('registry') == candidate['registry'], 'PP candidate version or registry digest mismatch')
        current = api.read('/git/ref/heads/' + urllib.parse.quote(qualified['branch'], safe='/'))
        require(current['object']['sha'] == sha, 'source branch moved before deployment')
        result = transport(profile, role, sha, digest, bundle, env)
    return {**qualified, **result, 'policy_sha256': policy_digest,
            'release_version': candidate['version'], 'registry': candidate['registry'],
            'controls_sha': env['GITHUB_SHA'],
            'scope': 'exact-source runtime deployment and acceptance',
            'run_id': int(env['GITHUB_RUN_ID']), 'run_attempt': int(env['GITHUB_RUN_ATTEMPT']),
            'completed_at_utc': dt.datetime.now(dt.timezone.utc).isoformat()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['ci', 'preflight', 'deploy'])
    parser.add_argument('role', choices=TARGETS)
    args = parser.parse_args()
    env = os.environ
    role = args.role
    report = {'environment': role, 'gate': 'BLOCKED', 'scope': args.mode}
    try:
        sha = env['APPROVED_REVISION']
        api = GitHub()
        if args.mode == 'ci':
            report = qualify_ci(api, role, sha, env)
        elif args.mode == 'preflight':
            require(env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch', 'manual deployment required')
            report = qualify_ci(api, role, sha, env)
            target_profile(role, '.github/deploy/targets.json')
            from release_package import load_candidate
            candidate, _published = load_candidate(api, env.get('RELEASE_VERSION', ''), sha)
            if role == 'production':
                with tempfile.TemporaryDirectory(prefix='tradebot-promotion-check-') as directory:
                    digest = candidate['artifact_sha256']
                    policy = hashlib.sha256(Path('.github/deploy/targets.json').read_bytes()).hexdigest()
                    proof = preprod_proof(api, env.get('PREPROD_RUN_ID', ''), sha, digest, policy)
                    require(proof.get('release_version') == candidate['version'] and proof.get('registry') == candidate['registry'], 'PP candidate version or registry digest mismatch')
            report['scope'] = 'deployment preflight; no runtime mutation'
        else:
            report = deploy(api, role, sha, '.github/deploy/targets.json', env, env.get('PREPROD_RUN_ID', ''))
    except ControllerFailure as error:
        report = {'environment': role, 'gate': 'BLOCKED', 'scope': args.mode,
                  'reason': str(error), 'controller': error.diagnostic}
    except PipelineHold as error:
        report = {'environment': role, 'gate': 'BLOCKED', 'scope': args.mode, 'reason': str(error)}
    except (ValueError, TypeError, KeyError, OSError, subprocess.SubprocessError, zipfile.BadZipFile):
        # Do not persist arbitrary remote responses, URLs, keys, or stderr.
        report = {'environment': role, 'gate': 'BLOCKED', 'scope': args.mode,
                  'reason': 'Required exact CI, qualified runtime/controller, PP evidence or deployment check did not pass. See the authoritative roadmap.'}
    destination = Path(env.get('PIPELINE_REPORT', 'ci-evidence/environment.json'))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + '\n')
    if env.get('GITHUB_STEP_SUMMARY'):
        with open(env['GITHUB_STEP_SUMMARY'], 'a') as summary:
            summary.write('### ' + role + ': ' + report['gate'] + '\n\n' + report['scope'] + '\n\n'
                          'Roadmap: docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md\n')
    return 0 if report['gate'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
