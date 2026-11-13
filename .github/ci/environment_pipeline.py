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


class PipelineHold(ValueError):
    """Only fixed, local diagnostic messages; never remote payloads or secrets."""


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

    def _read(self, url, binary=False, max_bytes=1024 * 1024):
        request = urllib.request.Request(url,
            headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
                     'Accept': 'application/octet-stream' if binary else 'application/vnd.github+json'})
        with urllib.request.build_opener(SafeRedirect()).open(request, timeout=20) as response:
            data = response.read(max_bytes + 1)
        require(len(data) <= max_bytes, 'API evidence exceeds size bound')
        return data if binary else json.loads(data)

    def read(self, path, binary=False, max_bytes=1024 * 1024):
        require(path.startswith('/') and not path.startswith('//'), 'repository-relative API path required')
        return self._read('https://api.github.com/repos/' + REPO + path, binary, max_bytes)


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
    require(proof.get('checks') == dict.fromkeys(REQUIRED_CHECKS, 'PASS'), 'PP acceptance checks incomplete')
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
    require(result.get('checks') == dict.fromkeys(REQUIRED_CHECKS, 'PASS'), 'controller acceptance incomplete')
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
        require(completed.returncode == 0, 'deployment controller failed; no automatic retry')
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
