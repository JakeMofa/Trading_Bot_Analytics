"""Manual, pinned PP-only transport for an already deployed live trial image."""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import uuid
import zipfile

import environment_pipeline as pipeline
from release_package import load_candidate


def require(value, reason):
    if not value:
        raise pipeline.PipelineHold(reason)


def generated_deployment(api, run_id, sha, digest, version, registry, image):
    require(str(run_id).isdigit() and int(run_id) > 0, 'generated PP deployment run required')
    run = api.read('/actions/runs/' + str(run_id))
    require(run.get('event') == 'workflow_dispatch' and run.get('status') == 'completed'
            and run.get('conclusion') == 'success' and run.get('path') == '.github/workflows/cd-pp.yml'
            and run.get('head_branch') in ('main', 'preprod')
            and run.get('repository', {}).get('full_name') == pipeline.REPO,
            'successful generated PP deployment required')
    artifacts = api.read('/actions/runs/' + str(run_id) + '/artifacts?per_page=100')['artifacts']
    found = [a for a in artifacts if a.get('name') == 'preprod-acceptance-' + sha and not a.get('expired')]
    require(len(found) == 1, 'unique generated PP acceptance required')
    raw = api.read('/actions/artifacts/' + str(found[0]['id']) + '/zip', binary=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        require(archive.namelist() == ['deployment.json'] and archive.getinfo('deployment.json').file_size <= 65536,
                'unexpected PP acceptance artifact')
        report = json.loads(archive.read('deployment.json'))
    pipeline.validate_result(report, 'preprod', sha, digest)
    require(report.get('acceptance_scope') == 'generated_only' and report.get('runtime_image_id') == image
            and report.get('release_version') == version and report.get('registry') == registry
            and report.get('run_id') == int(run_id)
            and report.get('run_attempt') == run.get('run_attempt', 1)
            and report.get('controls_sha') == run.get('head_sha'),
            'installed generated source and image proof mismatch')
    return {'source_sha': sha, 'artifact_sha256': digest, 'image_id': image,
            'generated_deployment_run_id': int(run_id)}


def exact_deployed_ci(api, candidate, branch):
    """Recheck immutable release CI after a controller-only policy commit moves HEAD."""
    sha = candidate['source_sha']
    require(branch in ('preprod', 'main') and candidate.get('source_branch') == branch,
            'published PP source branch mismatch')
    run_id = candidate.get('source_ci_run_id')
    require(isinstance(run_id, int) and run_id > 0, 'published exact source CI missing')
    run = api.read('/actions/runs/' + str(run_id))
    require(run.get('event') == 'push' and run.get('status') == 'completed'
            and run.get('conclusion') == 'success'
            and run.get('path') == '.github/workflows/python-tests.yml'
            and run.get('head_sha') == sha and run.get('head_branch') == branch
            and run.get('repository', {}).get('full_name') == pipeline.REPO,
            'published exact push CI failed or changed')
    runs = api.read('/actions/workflows/python-tests.yml/runs?event=push&head_sha=' + sha + '&per_page=100')['workflow_runs']
    matching = [item for item in runs if item.get('head_sha') == sha
                and item.get('head_branch') == branch and item.get('event') == 'push']
    require(matching, 'exact source CI run missing')
    latest = max(matching, key=lambda item: (item['id'], item.get('run_attempt', 1)))
    require(latest.get('id') == run_id and latest.get('status') == 'completed'
            and latest.get('conclusion') == 'success', 'newer exact source CI failed or is incomplete')
    return run_id


def command_for(env, api, profile):
    operation = env.get('PP_LIVE_OPERATION')
    require(operation in ('enter', 'leave', 'on', 'off'), 'invalid PP live operation')
    require(env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
            and env.get('GITHUB_REF_NAME') in ('main', 'preprod')
            and env.get('GITHUB_REPOSITORY') == pipeline.REPO, 'reviewed manual PP controls required')
    controls = api.read('/git/ref/heads/' + env['GITHUB_REF_NAME'])
    require(controls['object']['sha'] == env.get('GITHUB_SHA'), 'PP control branch moved')
    anchor = env.get('PP_CYCLE_INITIAL_A', '')
    trial_origin=env.get('PP_TRIAL_ORIGIN','')
    if trial_origin:
        require(trial_origin=='pp-live-pp-trial-20261119-03' and bool(anchor)
                and operation in ('enter','on'),'exact anchored PP trial origin required')
    if anchor:
        try:
            canonical = str(uuid.UUID(anchor))
        except ValueError:
            canonical = None
        require(canonical == anchor and operation in ('enter', 'on'),
                'canonical PP cycle initial A required for enter or on')
    if operation in ('on', 'off'):
        if operation == 'off':
            return 'session-v1 off', {'operation': 'off'}
        seconds = env.get('PP_LIVE_SECONDS', '')
        require(re.fullmatch(r'[0-9]{1,4}', seconds) is not None
                and (int(seconds) == 6600 if anchor else 1 <= int(seconds) <= 4560),
                'bounded session seconds required')
        binding = ({'initial_a': anchor} if anchor else {}) | ({'trial_origin':trial_origin} if trial_origin else {})
        return ('session-v1 on ' + str(int(seconds)) + (' ' + anchor if anchor else '') + (' '+trial_origin if trial_origin else ''),
                {'operation': 'on', 'max_seconds': int(seconds)} | binding)
    sha = env.get('APPROVED_REVISION', '')
    require(pipeline.SHA.fullmatch(sha) is not None, 'exact PP source required')
    candidate, _ = load_candidate(api, env.get('RELEASE_VERSION', ''), sha)
    image = env.get('PP_LIVE_IMAGE_ID', '')
    require(re.fullmatch(r'sha256:[0-9a-f]{64}', image) is not None, 'exact runtime image required')
    proof = generated_deployment(api, env.get('PP_DEPLOYMENT_RUN_ID', ''), sha,
        candidate['artifact_sha256'], candidate['version'], candidate['registry'], image)
    if operation == 'enter':
        branch = env.get('SOURCE_BRANCH')
        exact_deployed_ci(api, candidate, branch)
    command = 'transition-v1 preprod tradebot-preprod-01 ' + operation + ' ' + sha + ' ' + \
        candidate['artifact_sha256'] + ' ' + profile['controller_sha256'] + ' ' + image
    if anchor:
        command += ' ' + anchor
        proof['initial_a'] = anchor
        if trial_origin:
            command+=' '+trial_origin
            proof['trial_origin']=trial_origin
    return command, {**proof, 'operation': operation, 'release_version': candidate['version']}


def transport(profile, command, env):
    key, known = env.get('PP_DEPLOY_KEY', ''), env.get('PP_DEPLOY_KNOWN_HOSTS', '')
    require(key and known, 'dedicated PP deploy key and independent host pin required')
    with tempfile.TemporaryDirectory(prefix='tradebot-pp-live-') as directory:
        root = Path(directory)
        for name, value in (('key', key), ('known_hosts', known)):
            path = root / name
            path.write_text(value + '\n')
            path.chmod(0o600)
        args = ['ssh', '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
            '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=10',
            '-o', 'ConnectionAttempts=1', '-o', 'ServerAliveInterval=15',
            '-o', 'ServerAliveCountMax=2', '-o', 'UserKnownHostsFile=' + str(root/'known_hosts'),
            '-i', str(root/'key'), profile['user'] + '@' + profile['host'], command]
        with open('/dev/null', 'rb') as source:
            result = pipeline.bounded_process(args, source,
                810 if command.startswith('transition-v1 ') else 240)
        if result.returncode:
            diagnostic = pipeline.blocked_controller_diagnostic(result.stdout,'preprod',None,None)
            raise pipeline.PipelineHold(diagnostic['reason'])
        require(len(result.stdout) <= 8192, 'PP live controller response exceeds bound')
        return json.loads(result.stdout)


def validated_result(operation, result, initial_a=None, trial_origin=None):
    expected = {'enter':'PP_LIVE_READY_OFF', 'leave':'PP_GENERATED_RESTORED',
                'on':'PP_LIVE_ON', 'off':'PP_LIVE_OFF'}[operation]
    expected_origin='generated-pp' if operation=='leave' else (trial_origin or 'pp-live-pp')
    valid_origin=(result.get('origin_id') in ('pp-live-pp','pp-live-pp-trial-20261119-01','pp-live-pp-trial-20261119-02','pp-live-pp-trial-20261119-03')
                  if operation=='off' else result.get('origin_id')==expected_origin)
    require(result.get('gate') == expected and valid_origin
            and result.get('collector_enabled') is (operation == 'on')
            and result.get('initial_a') == initial_a, 'PP live result mismatch')
    return {'gate': expected, 'origin_id': result['origin_id'],
            'collector_enabled': result['collector_enabled']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('preflight', 'execute'))
    args = parser.parse_args()
    env = os.environ
    report = {'gate': 'BLOCKED', 'scope': 'pp_live_transition',
              'operation': env.get('PP_LIVE_OPERATION', '')}
    try:
        api = pipeline.GitHub()
        profile = pipeline.target_profile('preprod', '.github/deploy/targets.json')
        command, proof = command_for(env, api, profile)
        report = {'gate': 'PASS', 'scope': 'pp_live_preflight', **proof}
        if args.stage == 'execute':
            host_result = validated_result(proof['operation'], transport(profile, command, env),
                                           proof.get('initial_a'),proof.get('trial_origin'))
            report.update({key: value for key, value in host_result.items() if key != 'gate'})
            report['host_gate'] = host_result['gate']
            report['scope'] = 'pp_live_host_result'
            report['controls_sha'] = env['GITHUB_SHA']
            report['run_id'] = int(env['GITHUB_RUN_ID'])
            report['completed_at_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
    except pipeline.PipelineHold as error:
        report = {'gate': 'BLOCKED', 'scope': 'pp_live_transition',
                  'operation': env.get('PP_LIVE_OPERATION', ''), 'reason': str(error)}
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, zipfile.BadZipFile):
        report = {'gate': 'BLOCKED', 'scope': 'pp_live_transition',
                  'operation': env.get('PP_LIVE_OPERATION', ''), 'reason': 'qualified PP live control evidence unavailable'}
    path = Path(env.get('PIPELINE_REPORT', 'ci-evidence/pp-live/result.json'))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return 0 if report['gate'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
