"""Read-only, exact-hash PP controller check through the dedicated CD identity."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / '.github/deploy/targets.json'


def check(expected, key, known_hosts, *, runner=subprocess.run):
    if re.fullmatch(r'[0-9a-f]{64}', expected) is None:
        raise ValueError('invalid expected controller digest')
    profile = json.loads(PROFILE.read_text())['preprod']
    if profile['instance'] != 'tradebot-preprod-01' or profile['user'] != 'tradebot-preprod-deploy':
        raise ValueError('unexpected PP target identity')
    if not key or not known_hosts:
        raise ValueError('dedicated PP identity and host pin required')
    with tempfile.TemporaryDirectory(prefix='tradebot-pp-identity-') as directory:
        root = Path(directory)
        for name, value in [('key', key), ('known_hosts', known_hosts)]:
            path = root / name
            path.write_text(value + '\n')
            path.chmod(0o600)
        command = [
            'ssh', '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
            '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=10',
            '-o', 'ConnectionAttempts=1', '-o', 'UserKnownHostsFile=' + str(root / 'known_hosts'),
            '-i', str(root / 'key'), profile['user'] + '@' + profile['host'],
            'identity-v1 preprod tradebot-preprod-01 ' + expected,
        ]
        result = runner(command, input=b'', capture_output=True, timeout=20, check=False)
    if result.returncode or len(result.stdout) > 4096:
        raise ValueError('PP controller identity check failed')
    try:
        report = json.loads(result.stdout)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError('invalid PP controller identity response') from exc
    required = {
        'gate': 'IDENTITY_PASS', 'environment': 'preprod',
        'instance': 'tradebot-preprod-01', 'controller_sha256': expected,
        'runtime_qualified': False, 'database_changed': False,
    }
    if report != required:
        raise ValueError('PP controller identity response mismatch')
    return {'gate': 'IDENTITY_PASS', 'instance': required['instance'],
            'controller_sha256': expected, 'database_changed': False}


def main():
    expected = os.environ.get('EXPECTED_CONTROLLER_SHA256', '')
    result = check(expected, os.environ.get('PP_DEPLOY_KEY', ''),
                   os.environ.get('PP_DEPLOY_KNOWN_HOSTS', ''))
    output = Path(os.environ['PIPELINE_REPORT'])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, sort_keys=True) + '\n')
    print('PP dedicated controller identity: PASS')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print('PP dedicated controller identity: STOP (' + type(exc).__name__ + ')', file=sys.stderr)
        raise SystemExit(1)
