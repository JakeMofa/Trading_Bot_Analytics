"""Create/clean only a disposable container bound to an ID and unique owner receipt."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid

LABEL = 'org.tradebot.ci.owner'


def run(args):
    return subprocess.run(['docker', *args], text=True, capture_output=True, timeout=20)


def cleanup_record(record):
    identity, owner = record['id'], record['owner']
    if not re.fullmatch('[0-9a-f]{64}', identity) or not re.fullmatch('[0-9a-f]{32}', owner):
        raise ValueError('invalid generated ownership receipt')
    found = run(['container', 'inspect', identity])
    if found.returncode:
        if 'No such' in found.stderr:
            return False
        raise RuntimeError('cannot establish generated container identity')
    objects = json.loads(found.stdout)
    if (len(objects) != 1 or objects[0]['Id'] != identity
            or objects[0]['Config'].get('Labels', {}).get(LABEL) != owner):
        raise RuntimeError('generated container ownership mismatch; preserving instance')
    removed = run(['rm', '--force', '--volumes', identity])
    if removed.returncode:
        raise RuntimeError('owned generated container cleanup failed')
    return True


def cleanup(receipt):
    if receipt.exists():
        return cleanup_record(json.loads(receipt.read_text()))
    return False


def create(image, name, receipt):
    if not name.startswith('tradebot-schema-') or receipt.exists():
        raise ValueError('fresh generated identity/receipt required')
    owner = uuid.uuid4().hex
    created = run(['create', '--name', name, '--label', LABEL + '=' + owner,
                   '--network', 'none', '--memory', '512m', '--cpus', '1',
                   '--pids-limit', '128', '--tmpfs', '/var/lib/postgresql/data:rw,size=256m',
                   '--tmpfs', '/var/run/postgresql:rw,size=8m',
                   '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', image])
    if created.returncode:
        # A name collision never produces a receipt and never invokes cleanup by name.
        raise RuntimeError('generated container creation failed; existing instances preserved')
    identity = created.stdout.strip()
    if not re.fullmatch('[0-9a-f]{64}', identity):
        raise RuntimeError('creation returned no valid container identity')
    record = {'id': identity, 'owner': owner}
    try:
        receipt.parent.mkdir(parents=True, exist_ok=True)
        with receipt.open('x') as file:
            json.dump(record, file)
    except Exception:
        cleanup_record(record)
        raise
    return identity


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cleanup', type=Path, required=True)
    args = parser.parse_args()
    cleanup(args.cleanup)
