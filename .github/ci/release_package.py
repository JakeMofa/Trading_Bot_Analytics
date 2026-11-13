"""Create-only source releases and GHCR carriers; never starts a market collector.

The scratch image is a registry envelope, not an application runtime image.
Published digests and source checksums identify rollback candidates. Applying
one still requires the environment's reviewed runtime/database compatibility.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tempfile
import urllib.error

import environment_pipeline as pipeline

REGISTRY = 'ghcr.io/jakemofa/trading_bot_analytics/releases'
SEMVER = re.compile(r'v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?')
LIMIT = 16 * 1024**2
ROADMAP = 'https://github.com/' + pipeline.REPO + '/blob/main/docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md'


def require(value, message):
    pipeline.require(value, message)


def version(value):
    require(isinstance(value, str) and SEMVER.fullmatch(value), 'explicit v-prefixed SemVer required')
    return value


def command(args, **kwargs):
    # Child errors never echo arbitrary remote output or credentials.
    try:
        return subprocess.run(args, check=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=120, **kwargs).stdout
    except subprocess.SubprocessError as exc:
        raise pipeline.PipelineHold('bounded release subprocess failed; inspect sanitized checkpoint') from exc


def absent(api, path):
    try:
        api.read(path)
    except urllib.error.HTTPError as error:
        require(error.code == 404, 'release absence could not be established')
        return
    raise pipeline.PipelineHold('version already exists; never overwrite tags, packages or releases')


def registry_absent(api, tag):
    # Query the authenticated package catalog, not Docker's ambiguous CLI error text.
    for page in range(1, 101):
        try:
            rows = api.read_registry(page)
        except urllib.error.HTTPError as error:
            require(error.code == 404 and page == 1, 'registry absence could not be established')
            return
        require(isinstance(rows, list), 'invalid registry catalog')
        for row in rows:
            require(tag not in row.get('metadata', {}).get('container', {}).get('tags', []),
                    'registry version already exists; never overwrite')
        if len(rows) < 100:
            return
    raise pipeline.PipelineHold('registry catalog exceeds review bound')


def check_archive(raw):
    require(0 < len(raw) <= LIMIT, 'source archive exceeds bound')
    total = 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        members = archive.getmembers()
        require(len(members) <= 10000, 'source member count exceeds bound')
        for member in members:
            path = PurePosixPath(member.name)
            require(not path.is_absolute() and '..' not in path.parts, 'unsafe source path')
            require(member.isdir() or member.isfile(), 'links and special files are not deployable')
            for part in path.parts:
                require(part not in {'data', '.git', '.venv', 'node_modules', '__pycache__'}, 'local data excluded')
                require(not (part == '.env' or part.startswith('.env.') or part.startswith('.env '))
                        or part == '.env.example', 'environment credentials excluded')
            require(path.suffix.lower() not in {'.db', '.sqlite', '.sqlite3', '.pem', '.key', '.log'},
                    'database, key and log files excluded')
            total += member.size
        require(total <= 64 * 1024**2, 'expanded source exceeds bound')
    return hashlib.sha256(raw).hexdigest()


def manifest(sha, tag, digest, ci_id, run_id, requirements_digest):
    require(pipeline.SHA.fullmatch(sha) and pipeline.DIGEST.fullmatch(digest), 'exact source and artifact digest required')
    return {'format': 'tradebot-source-release-v1', 'version': version(tag),
            'source_sha': sha, 'artifact_sha256': digest, 'source_ci_run_id': int(ci_id),
            'publication_run_id': int(run_id), 'repository': pipeline.REPO,
            'requirements_sha256': requirements_digest, 'package_kind': 'source-bundle-not-runtime',
            'state': 'CANDIDATE', 'deployed': False, 'acceptance_validated': False,
            'database_changes_applied': False, 'database_rollback_supported': False,
            'roadmap': ROADMAP}


def write_carrier(root, data):
    (root/'manifest.json').write_text(json.dumps(data, indent=2)+'\n')
    # No base image, package install, application execution, network or database.
    (root/'Dockerfile').write_text(
        'FROM scratch\n'
        'LABEL org.opencontainers.image.source="https://github.com/'+pipeline.REPO+'"\n'
        'LABEL org.opencontainers.image.revision="'+data['source_sha']+'"\n'
        'LABEL org.opencontainers.image.version="'+data['version']+'"\n'
        'LABEL org.opencontainers.image.description="Tradebot versioned source bundle; not a runtime image"\n'
        'COPY source.tar.gz manifest.json /release/\n')
    (root/'.dockerignore').write_text('*\n!source.tar.gz\n!manifest.json\n!Dockerfile\n')


def prepare(root, api, env):
    require(env.get('GITHUB_REF') == 'refs/heads/main' and env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch',
            'release control runs only from main via manual dispatch')
    sha = env.get('APPROVED_REVISION', '')
    require(env.get('SOURCE_BRANCH') in {'main', 'preprod'}, 'release source must be main or preprod')
    qualified = pipeline.qualify_ci(api, 'preprod', sha, env)
    tag = version(env.get('RELEASE_VERSION', ''))
    absent(api, '/git/ref/tags/'+tag)
    absent(api, '/releases/tags/'+tag)
    root.mkdir(parents=True, exist_ok=False)
    path = root/'source.tar.gz'
    pipeline.archive(sha, path)
    digest = check_archive(path.read_bytes())
    requirements = command(['git', 'show', sha+':backend/requirements.txt'])
    data = manifest(sha, tag, digest, qualified['source_ci_run_id'], env['GITHUB_RUN_ID'],
                    hashlib.sha256(requirements).hexdigest())
    data.update(controls_sha=env['GITHUB_SHA'], source_branch=qualified['branch'])
    write_carrier(root, data)
    return data


def package(root, env):
    data = json.loads((root/'manifest.json').read_text())
    require(data['source_sha'] == env['APPROVED_REVISION'] and data['version'] == version(env['RELEASE_VERSION']),
            'prepared package binding changed')
    require(check_archive((root/'source.tar.gz').read_bytes()) == data['artifact_sha256'], 'prepared source changed')
    require(env.get('GITHUB_REF') == 'refs/heads/main', 'package publication requires main')
    reference = REGISTRY+':'+data['version']
    # Fail closed for a tag collision or unavailable registry; no retag/overwrite.
    command(['docker', 'login', 'ghcr.io', '-u', env['GITHUB_ACTOR'], '--password-stdin'],
            input=env['GH_TOKEN'].encode())
    registry_absent(pipeline.GitHub(), data['version'])
    command(['docker', 'build', '--network=none', '--tag', reference, str(root)])
    command(['docker', 'push', reference])
    # Pin the manifest returned by the registry, not the mutable version tag.
    raw = command(['docker', 'buildx', 'imagetools', 'inspect', reference, '--format', '{{json .Manifest}}'])
    digest = json.loads(raw)['digest']
    require(re.fullmatch(r'sha256:[0-9a-f]{64}', digest), 'registry digest missing')
    data['registry'] = REGISTRY+'@'+digest
    (root/'release-manifest.json').write_text(json.dumps(data, indent=2)+'\n')
    if env.get('GITHUB_OUTPUT'):
        with open(env['GITHUB_OUTPUT'], 'a') as output:
            output.write('digest='+digest+'\n')
    return data


def publish(root, api, env):
    data = json.loads((root/'release-manifest.json').read_text())
    require(data['publication_run_id'] == int(env['GITHUB_RUN_ID'])
            and data['source_sha'] == env['APPROVED_REVISION'] and data['version'] == version(env['RELEASE_VERSION']),
            'publication binding changed')
    require(check_archive((root/'source.tar.gz').read_bytes()) == data['artifact_sha256'], 'source changed before publication')
    # Recheck exact main/CI and version absence immediately before publication.
    pipeline.qualify_ci(api, 'preprod', data['source_sha'], env)
    absent(api, '/git/ref/tags/'+data['version'])
    absent(api, '/releases/tags/'+data['version'])
    sums = ''.join(hashlib.sha256((root/name).read_bytes()).hexdigest()+'  '+name+'\n'
                   for name in ('source.tar.gz', 'release-manifest.json'))
    (root/'SHA256SUMS').write_text(sums)
    notes = ('CANDIDATE — not deployed; acceptance NOT PERFORMED.\n\n'
             'Source: `'+data['source_sha']+'`\n\n'
             'Registry source bundle (not an application runtime image): `'+data['registry']+'`\n\n'
             '[Exact source CI](https://github.com/'+pipeline.REPO+'/actions/runs/'+str(data['source_ci_run_id'])+')\n\n'
             'Deploy to PP with CD Preprod, then promote this same source to production with CD Prod/Main. '
             'Both are manual and require qualified host controls. A main merge, tag or Release never deploys. '
             'GitHub environment deployment history records actual deployment results separately.\n\n'
             'Rollback requires reviewed code/schema compatibility. No database rollback, data copy or restore is included.\n\n'
             'Open Phase 1.75 gates: PP PostgreSQL adapter/schema qualification, verified archive lifecycle, '
             'production migration/fencing/recovery, I7 freshness/rollover and sustained operation.\n\n'
             '[Authoritative roadmap]('+ROADMAP+')\n')
    (root/'NOTES.md').write_text(notes)
    command(['gh', 'release', 'create', data['version'], '--repo', pipeline.REPO,
             '--target', data['source_sha'], '--prerelease', '--draft', '--title', data['version']+' — candidate',
             '--notes-file', str(root/'NOTES.md'), str(root/'source.tar.gz'),
             str(root/'release-manifest.json'), str(root/'SHA256SUMS')])
    # A partial failure leaves the draft/package untouched for reconciliation, never auto retries.
    command(['gh', 'release', 'edit', data['version'], '--repo', pipeline.REPO, '--draft=false'])
    return data


def load_candidate(api, tag, sha):
    tag = version(tag)
    release = api.read('/releases/tags/'+tag)
    require(not release.get('draft') and release.get('tag_name') == tag, 'published candidate required')
    ref = api.read('/git/ref/tags/'+tag)
    require(ref.get('object', {}).get('type') == 'commit' and ref['object']['sha'] == sha,
            'release tag/source changed')
    assets = release.get('assets', [])
    def asset(name, limit):
        selected = [a for a in assets if a.get('name') == name and 0 < a.get('size', 0) <= limit]
        require(len(selected) == 1, 'unique bounded release asset required')
        return api.read('/releases/assets/'+str(int(selected[0]['id'])), binary=True, max_bytes=limit)
    data = json.loads(asset('release-manifest.json', 65536))
    require(data.get('format') == 'tradebot-source-release-v1' and data.get('source_sha') == sha
            and data.get('version') == tag and data.get('repository') == pipeline.REPO
            and re.fullmatch(re.escape(REGISTRY)+r'@sha256:[0-9a-f]{64}', data.get('registry', '')),
            'release manifest binding mismatch')
    run = api.read('/actions/runs/'+str(int(data['publication_run_id'])))
    require(run.get('event') == 'workflow_dispatch' and run.get('status') == 'completed'
            and run.get('conclusion') == 'success' and run.get('path') == '.github/workflows/release-candidate.yml'
            and run.get('head_branch') == 'main' and run.get('head_sha') == data.get('controls_sha')
            and run.get('repository', {}).get('full_name') == pipeline.REPO,
            'trusted successful publication run required')
    raw = asset('source.tar.gz', LIMIT)
    require(check_archive(raw) == data.get('artifact_sha256'), 'published source checksum mismatch')
    return data, raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['prepare', 'package', 'publish', 'fixture', 'summary'])
    parser.add_argument('scope', nargs='?')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    env = os.environ
    if args.operation == 'summary':
        if env.get('GITHUB_STEP_SUMMARY'):
            with open(env['GITHUB_STEP_SUMMARY'], 'a') as output:
                output.write('Backend suite executed against this checkout. Generated/local SQLite tests only; '
                             'no live Supabase, VM, PostgreSQL migration or production acceptance.\n\n[Roadmap]('+ROADMAP+')\n')
        return 0
    if args.operation == 'fixture':
        root = args.output;root.mkdir(parents=True, exist_ok=False)
        raw = command(['git', 'archive', '--format=tar.gz', 'HEAD'])
        (root/'source.tar.gz').write_bytes(raw)
        sha = command(['git', 'rev-parse', 'HEAD']).decode().strip()
        data = manifest(sha, 'v0.0.0-test', check_archive(raw), 1, 1, '0'*64)
        write_carrier(root, data)
        return 0
    try:
        api = pipeline.GitHub()
        if args.operation == 'prepare':data = prepare(args.output, api, env)
        elif args.operation == 'package':data = package(args.output, env)
        else:data = publish(args.output, api, env)
        if env.get('GITHUB_STEP_SUMMARY'):
            with open(env['GITHUB_STEP_SUMMARY'], 'a') as output:
                output.write('Candidate '+data['version']+' / '+data['source_sha']+' — '+args.operation+' completed. '
                             'Deployed: NO. Acceptance: NOT PERFORMED.\n\n[Roadmap]('+ROADMAP+')\n')
        return 0
    except (ValueError, KeyError, OSError, subprocess.SubprocessError, tarfile.TarError):
        print('Release STOP: required source, registry or publication check failed; no automatic retry. '
              'A partial package/draft must be reconciled before another version is attempted.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
