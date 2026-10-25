"""Fail closed unless dispatch targets approved branch HEAD with exact push CI success."""
import json
import os
import re
import urllib.request


def main():
    sha = os.environ['APPROVED_REVISION']
    assert re.fullmatch('[0-9a-f]{40}', sha), 'full revision required'
    assert os.environ['GITHUB_EVENT_NAME'] == 'workflow_dispatch'
    assert os.environ['GITHUB_REF'] == 'refs/heads/codex/lightsail-deployment'
    assert os.environ['GITHUB_SHA'] == sha, 'dispatch and input revision differ'
    repo = os.environ['GITHUB_REPOSITORY']
    assert repo == 'JakeMofa/Trading_Bot_Analytics'
    def get(path):
        request = urllib.request.Request('https://api.github.com/repos/' + repo + path,
                                        headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
                                                 'Accept': 'application/vnd.github+json'})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    assert get('/git/ref/heads/codex/lightsail-deployment')['object']['sha'] == sha, 'branch moved'
    runs = get('/actions/workflows/python-tests.yml/runs?event=push&head_sha=' + sha)['workflow_runs']
    assert any(run['head_sha'] == sha and run['head_branch'] == 'codex/lightsail-deployment'
               and run['status'] == 'completed' and run['conclusion'] == 'success' for run in runs), 'exact revision CI has not passed'
    print('Approved deployment branch HEAD and exact-revision CI verified')


if __name__ == '__main__':
    main()
