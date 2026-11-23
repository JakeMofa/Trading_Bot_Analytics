"""Publish fresh production /health collector flags for one bounded observation."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import stat
import subprocess
import time

from publish_archive_metrics import point, send


def health_point(ssh):
    result = subprocess.run(
        [*ssh, 'curl --silent --fail --max-time 4 http://127.0.0.1:8000/health'],
        capture_output=True, timeout=12, check=True,
    )
    observed = datetime.now(timezone.utc)
    collector = json.loads(result.stdout)['collector']
    if not all(isinstance(collector.get(k), bool) for k in ('running', 'enabled')):
        raise ValueError('Collector state missing from health response')
    fields = {k: int(collector[k]) for k in ('running', 'enabled')}
    return observed, fields, point('prod_collector', {'environment': 'production'}, fields, observed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ssh-target', required=True)
    parser.add_argument('--identity-file', type=Path, required=True)
    parser.add_argument('--known-hosts', type=Path, required=True)
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--tenant', required=True)
    parser.add_argument('--token-file', type=Path, required=True)
    parser.add_argument('--through', type=datetime.fromisoformat, required=True)
    args = parser.parse_args()
    if args.through.tzinfo is None or not timedelta(0) < args.through-datetime.now(timezone.utc) <= timedelta(hours=3):
        parser.error('Use an absolute deadline within three hours')
    if args.ssh_target.startswith('-') or not args.tenant.isdecimal():
        parser.error('Invalid SSH target or Grafana tenant')
    with args.token_file.open() as credential:
        info = os.fstat(credential.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            parser.error('Token file must be private to its owner')
        token = credential.read().strip()
    if not token:
        parser.error('Empty token file')
    ssh = ['ssh', '-T', '-i', str(args.identity_file), '-o', 'BatchMode=yes', '-o',
           'IdentitiesOnly=yes', '-o', 'StrictHostKeyChecking=yes', '-o',
           f'UserKnownHostsFile={args.known_hosts}', '-o', 'ConnectTimeout=5', args.ssh_target]
    while datetime.now(timezone.utc) < args.through:
        start = time.monotonic()
        try:
            observed, fields, line = health_point(ssh)
            if observed >= args.through:
                break
            send(args.endpoint, args.tenant, token, [line])
            print(json.dumps({'observed': observed.isoformat(), 'accepted': True, **fields}), flush=True)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
            print(json.dumps({'at': datetime.now(timezone.utc).isoformat(), 'error_type': type(error).__name__}), flush=True)
        remaining = (args.through - datetime.now(timezone.utc)).total_seconds()
        time.sleep(max(0, min(60 - (time.monotonic() - start), remaining)))


if __name__ == '__main__':
    main()
