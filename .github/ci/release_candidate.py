"""Manual candidate build/publication. Never deploy; never move tags/replace assets."""
import argparse
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import urllib.error
import urllib.parse
import urllib.request

REPO = 'JakeMofa/Trading_Bot_Analytics'
BRANCHES = {'codex/ci-pr-quality-gates', 'codex/phase1-75-retention-enable', 'codex/lightsail-deployment', 'main'}
NUM = r'(?:0|[1-9][0-9]*)'
IDENT = r'(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)'
VERSION = re.compile(rf'{NUM}\.{NUM}\.{NUM}(?:-{IDENT}(?:\.{IDENT})*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?')
SCOPE = 'read-only-analysis-candidate'


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


class GitHub:
    def call(self, method, path, value=None, binary=False):
        base = 'https://uploads.github.com/repos/' if binary else 'https://api.github.com/repos/'
        body = value if binary else (json.dumps(value).encode() if value is not None else None)
        request = urllib.request.Request(base + REPO + path, data=body, method=method,
            headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
                     'Accept': 'application/vnd.github+json',
                     'Content-Type': 'application/octet-stream' if binary else 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if method == 'GET' and error.code == 404:
                return None
            raise RuntimeError('GitHub operation failed: HTTP ' + str(error.code)) from None


def qualify(api, branch, sha, version, scope, env):
    require(branch in BRANCHES and re.fullmatch('[0-9a-f]{40}', sha), 'unsupported branch or full SHA')
    require(len(version) <= 100 and VERSION.fullmatch(version), 'valid explicit SemVer required')
    require(scope == SCOPE, 'candidate scope required')
    require(env.get('GITHUB_REPOSITORY') == REPO and env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch', 'manual repository dispatch required')
    require(env.get('GITHUB_REF') == 'refs/heads/' + branch and env.get('GITHUB_SHA') == sha, 'dispatch branch/SHA must equal approved source')
    ref = api.call('GET', '/git/ref/heads/' + branch)
    require(ref and ref['object']['sha'] == sha, 'approved branch HEAD moved')
    result = api.call('GET', '/actions/workflows/python-tests.yml/runs?event=push&head_sha=' + sha + '&per_page=100')
    runs = [r for r in (result or {}).get('workflow_runs', []) if r.get('head_sha') == sha
            and r.get('head_branch') == branch and r.get('event') == 'push'
            and r.get('status') == 'completed' and r.get('conclusion') == 'success']
    require(runs, 'passing exact push CI missing')
    run = max(runs, key=lambda r: r['id'])
    return {'id': run['id'], 'source_sha': sha, 'tested_sha': sha, 'event':'push', 'conclusion':'success', 'branch':branch,
            'url': f'https://github.com/{REPO}/actions/runs/{run["id"]}',
            'artifacts_url': f'https://github.com/{REPO}/actions/runs/{run["id"]}#artifacts'}


def exporter():
    spec = importlib.util.spec_from_file_location('candidate_export', Path('backend/build_ab_candidate.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(output, sha, branch, version, scope, evidence):
    require(not output.exists(), 'fresh candidate output required')
    output.mkdir(parents=True)
    source = output / 'source'
    helper = exporter()
    tracked = helper.export(Path.cwd(), sha, source)
    bundle = output / 'source.tar.gz'
    with bundle.open('wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', filename='', mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w') as tar:
            for name in sorted([*tracked['files'], helper.MANIFEST]):
                data = (source / name).read_bytes()
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = 0o755 if tracked['files'].get(name, {}).get('mode') == '100755' else 0o644
                tar.addfile(info, io.BytesIO(data))
    helper.verify_export(source, sha, repo=Path.cwd())
    requirements = (source / 'backend/requirements.txt').read_bytes()
    (output / 'requirements.txt').write_bytes(requirements)
    schema = {n: v['sha256'] for n, v in tracked['files'].items() if n.startswith('supabase/schema/') or '/migrations/' in n}
    compatibility = {'schema_files_sha256': schema,
        'evidence': evidence, 'sqlite': 'generated supported predecessors only; production layout approval required',
        'postgres': 'isolated SQL compatibility; not hosted Supabase drift or auth acceptance',
        'migration': 'no automatic DDL/cutover; review retained legacy/core/A/B references and forward recovery',
        'rollback': 'code rollback after acknowledged A/B writes requires reviewed schema/data compatibility; no automatic database rollback',
        'blockers': ['Phase1.75 remains open; see live roadmap', 'production A/B operator, aggregate capacity, mutation fence and sustained acceptance not qualified']}
    (output / 'compatibility.json').write_bytes(canonical(compatibility))
    (output / 'ci-evidence.json').write_bytes(canonical(evidence))
    assets = {n: {'sha256': digest((output/n).read_bytes()), 'bytes': (output/n).stat().st_size}
              for n in ('source.tar.gz', 'requirements.txt', 'compatibility.json', 'ci-evidence.json')}
    manifest = {'format': 1, 'version': version, 'tag': 'v'+version, 'scope': scope,
        'branch': branch, 'source_sha': sha, 'tested_sha': sha, 'ci': evidence,
        'version_authority': 'release-manifest.json for this candidate, not a repository phase label',
        'assets': assets, 'dependency_manifest': {'path':'requirements.txt','sha256':assets['requirements.txt']['sha256']},
        'runtime': 'source only; direct pins do not freeze transitive dependencies or a Python runtime',
        'state': {'candidate': 'CI-qualified source', 'deployed': 'NOT PERFORMED', 'acceptance_validated': 'NOT PERFORMED'},
        'roadmap': f'https://github.com/{REPO}/blob/{sha}/docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md'}
    (output / 'release-manifest.json').write_bytes(canonical(manifest))
    return manifest


def validate_artifacts(output, expected):
    require(json.loads((output/'release-manifest.json').read_text()) == expected, 'manifest mismatch')
    require(expected['tag'] == 'v'+expected['version'] and VERSION.fullmatch(expected['version']), 'version/tag mismatch')
    require(expected['source_sha'] == expected['tested_sha'] == expected['ci']['tested_sha'] == expected['ci']['source_sha'], 'source/tested SHA mismatch')
    require(set(expected['assets']) == {'source.tar.gz','requirements.txt','compatibility.json','ci-evidence.json'}, 'required assets missing')
    for name, metadata in expected['assets'].items():
        require(name in {'source.tar.gz', 'requirements.txt', 'compatibility.json', 'ci-evidence.json'}, 'unsupported asset')
        body = (output/name).read_bytes()
        require(metadata == {'sha256': digest(body), 'bytes': len(body)}, 'artifact hash/size mismatch')
    helper = exporter()
    helper.verify_export(output/'source', expected['source_sha'], repo=Path.cwd())
    with tarfile.open(output/'source.tar.gz', 'r:gz') as tar:
        members = tar.getmembers()
        files = {str(p.relative_to(output/'source')): p.read_bytes() for p in (output/'source').rglob('*') if p.is_file()}
        require(len(members) == len(files) and {m.name for m in members} == set(files), 'bundle file-set mismatch')
        for member in members:
            require(member.isfile() and member.mode == ((output/'source'/member.name).stat().st_mode & 0o777) and tar.extractfile(member).read() == files[member.name], 'bundle bytes differ from exact source')


def publish(api, output, manifest):
    validate_artifacts(output, manifest)
    tag = manifest['tag']
    path = '/git/ref/tags/' + urllib.parse.quote(tag, safe='')
    marker = '<!--tradebot-manifest-sha256:' + digest((output/'release-manifest.json').read_bytes()) + '-->'
    notes = (f'Candidate {manifest["version"]}; source `{manifest["source_sha"]}`.\n\n'
             f'CI evidence: {manifest["ci"]["url"]}\nRoadmap: {manifest["roadmap"]}\n\n'
             'Deployed: NOT PERFORMED. Acceptance validated: NOT PERFORMED.\n'
             'Phase1.75 OPEN: production A/B operator/capacity/mutation-fence/sustained acceptance unresolved.\n'
             'No automatic deployment, cloud DDL or database rollback.\n'+marker)
    release = api.call('GET', '/releases/tags/'+urllib.parse.quote(tag, safe=''))
    if release:
        require(release.get('prerelease') is True and release.get('target_commitish') == manifest['source_sha']
                and release.get('body') == notes, 'release collision; never overwritten')
    ref = api.call('GET', path)
    if ref:
        require(ref['object'].get('type') == 'commit' and ref['object'].get('sha') == manifest['source_sha'], 'tag collision; never moved')
    else:
        api.call('POST', '/git/refs', {'ref': 'refs/tags/'+tag, 'sha': manifest['source_sha']})
    if release is None:
        release = api.call('POST', '/releases', {'tag_name':tag, 'target_commitish':manifest['source_sha'],
            'name':tag+' candidate', 'body':notes, 'draft':True, 'prerelease':True, 'make_latest':'false'})
    names = set(manifest['assets']) | {'release-manifest.json'}
    existing = {a['name']: a for a in release.get('assets', [])}
    require(set(existing) <= names, 'unexpected existing release assets')
    for name in sorted(names):
        body = (output/name).read_bytes()
        asset = existing.get(name)
        if asset is None:
            require(release.get('draft'), 'published release incomplete; manual review required')
            asset = api.call('POST', f'/releases/{release["id"]}/assets?name='+urllib.parse.quote(name), body, binary=True)
        require(asset.get('digest') == 'sha256:'+digest(body) and asset.get('size') == len(body), 'release asset collision/hash unavailable')
    # Recheck the tag immediately before publication; never repair or force-update it.
    final = api.call('GET', path)
    require(final and final['object'].get('type') == 'commit' and final['object'].get('sha') == manifest['source_sha'], 'tag changed during publication')
    if release.get('draft'):
        api.call('PATCH', f'/releases/{release["id"]}', {'draft':False, 'prerelease':True, 'make_latest':'false'})
    return f'https://github.com/{REPO}/releases/tag/{urllib.parse.quote(tag, safe="")}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--prepared', type=Path)
    args = parser.parse_args()
    branch, sha, version, scope = (os.environ[n] for n in ('RELEASE_BRANCH','RELEASE_SHA','RELEASE_VERSION','RELEASE_SCOPE'))
    require(subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip() == sha, 'checkout/source SHA mismatch')
    api = GitHub()
    evidence = qualify(api, branch, sha, version, scope, os.environ)
    output = Path(os.environ['RELEASE_OUTPUT'])
    manifest = build(output, sha, branch, version, scope, evidence)
    validate_artifacts(output, manifest)
    if args.publish:
        require(args.prepared is not None, 'prepared artifacts required for publication')
        names = set(manifest['assets']) | {'release-manifest.json'}
        require({p.name for p in args.prepared.iterdir()} == names, 'prepared asset set mismatch')
        for name in names:
            require((args.prepared/name).read_bytes() == (output/name).read_bytes(), 'prepared artifact mismatch')
    # Branch and qualifying CI are rechecked before any write action.
    require(qualify(api, branch, sha, version, scope, os.environ) == evidence, 'release evidence changed')
    url = publish(api, output, manifest) if args.publish else 'NOT PUBLISHED (artifact build only)'
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
        summary.write(f'Candidate `{version}` / `{sha}`\n\n{url}\n\nCI: {evidence["url"]}\n\n'
                      'Deployed/acceptance validated: NOT PERFORMED. See compatibility.json and roadmap.\n')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
                summary.write('Release candidate: FAIL/BLOCKED ('+type(error).__name__+'). No deployment performed. '
                              'Publication may be partial; reconcile same inputs after review, never move tags/replace assets.\n')
        raise
