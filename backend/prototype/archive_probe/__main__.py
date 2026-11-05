"""One isolated archive upload/readback. Live execution requires --live."""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import pwd
import signal
import subprocess
import sys
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import (
    HTTPRedirectHandler, ProxyHandler, Request, build_opener,
)

PROJECT = 'https://xttdqeimdujweijxcuro.supabase.co'
BUCKET = 'market-raw'
PREFIX = 'ab72-readiness/2026-11-03-v1/'
GENERATION = '72000000000000000000000000000001'
UNIT = 'tradebot-lifecycle.service'
COMMAND = ['/opt/tradebot/.venv/bin/python', 'backend/app/run_cloud_lifecycle.py', 'run']
MAX_BYTES = 65536


class Hold(Exception):
    pass


def require(condition, reason):
    if not condition:
        raise Hold(reason)


def unit_properties():
    fields = ['ActiveState', 'MainPID', 'User', 'WorkingDirectory']
    result = subprocess.check_output(
        ['systemctl', 'show', UNIT, *('-p'+field for field in fields)],
        timeout=3, text=True,
    )
    return dict(line.split('=', 1) for line in result.splitlines())


def running_identity():
    require(sys.platform == 'linux' and os.geteuid() == 0, 'live binding requires Linux root')
    props = unit_properties()
    require(props.get('MainPID', '').isdigit() and int(props['MainPID']) > 1, 'no lifecycle PID')
    pid = int(props['MainPID'])
    proc = Path('/proc') / str(pid)
    account = pwd.getpwnam('tradebot')
    start = (proc/'stat').read_bytes().rsplit(b')', 1)[1].split()[19]
    command = (proc/'cmdline').read_bytes().rstrip(b'\0').decode().split('\0')
    config = dict(item.decode().split('=', 1) for item in
                  (proc/'environ').read_bytes().split(b'\0') if b'=' in item)
    identity = dict(active=props.get('ActiveState'), user=props.get('User'),
                    directory=props.get('WorkingDirectory'), uid=proc.stat().st_uid,
                    cwd=str((proc/'cwd').resolve()), command=command)
    require(unit_properties() == props and
            (proc/'stat').read_bytes().rsplit(b')', 1)[1].split()[19] == start,
            'lifecycle process changed during binding')
    validate_binding(identity, config, account.pw_uid)
    os.initgroups(account.pw_name, account.pw_gid)
    os.setgid(account.pw_gid)
    os.setuid(account.pw_uid)
    return config, pid


def validate_binding(identity, config, expected_uid):
    require(identity == dict(active='active', user='tradebot', directory='/opt/tradebot',
                             uid=expected_uid, cwd='/opt/tradebot', command=COMMAND),
            'archive runtime identity mismatch')
    require(config.get('SUPABASE_URL', '').rstrip('/') == PROJECT, 'runtime project mismatch')
    require(config.get('SUPABASE_RAW_BUCKET', BUCKET) == BUCKET, 'runtime bucket mismatch')
    require(config.get('ENABLE_SUPABASE_SYNC', '').strip().lower() in ('1','true','yes','on')
            and bool(config.get('SUPABASE_SECRET_KEY')), 'archive runtime credentials or enablement missing')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def main(args, report):
    # -IS plus the origin check prevents fallback to installed or checkout modules.
    try:
        import retention_recovery
        import retention
        import retention_timestamp_guards
    except ModuleNotFoundError as error:
        raise Hold(f'missing bundled dependency: {error.name}') from None
    for module in (retention_recovery, retention, retention_timestamp_guards):
        require(Path(module.__file__).parent == Path(sys.argv[0]).resolve(),
                'archive dependency loaded outside probe bundle')

    if args.live:
        config, pid = running_identity()
        endpoint = PROJECT
        report['runtime_pid'] = pid
    else:
        fixture = json.loads(args.mock.read_text())
        config = fixture['config']
        validate_binding(fixture['identity'], config, fixture['expected_uid'])
        endpoint = fixture['endpoint']
        parsed = urlsplit(endpoint)
        require(parsed.scheme == 'http' and parsed.hostname == '127.0.0.1'
                and parsed.port is not None and parsed.netloc == f'127.0.0.1:{parsed.port}'
                and not (parsed.path or parsed.query or parsed.fragment),
                'mock endpoint must be loopback')
    report['stage'] = 'synthetic fixture'
    rows = [
        dict(source='ab72_qualification', event_id=f'2026-11-03-v1-{i}',
             received_at=f'2026-11-03T00:00:0{i}.000000+00:00',
             source_time=f'2026-11-03T00:00:0{i}.000000+00:00',
             price='1.000000000000000001', size='0.01', side='buy', payload={'synthetic': True})
        for i in (1, 2)
    ]
    raw = ''.join(json.dumps({'dataset':'stream_events','row':row}, separators=(',', ':'))+'\n'
                  for row in rows).encode()
    # Use GzipFile rather than gzip.compress(mtime=0), whose header varies by Python version.
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode='wb', mtime=0) as archive:
        archive.write(raw)
    body = buffer.getvalue()
    digest = hashlib.sha256(body).hexdigest()
    key = f'{PREFIX}{GENERATION}/stream_events/{digest}.jsonl.gz'
    manifest = dict(source='coinbase', bucket=BUCKET, object_path=key,
                    compressed_bytes=len(body), sha256=digest, event_count=len(rows),
                    started_at=rows[0]['received_at'], ended_at=rows[-1]['received_at'],
                    verified_at=rows[-1]['received_at'],
                    metadata=dict(dataset='stream_events', generation_id=GENERATION,
                                  verification='authenticated_readback_sha256',
                                  first_source_key=json.dumps([rows[0]['source'],rows[0]['event_id']]),
                                  last_source_key=json.dumps([rows[-1]['source'],rows[-1]['event_id']])))
    expected = {retention_recovery.identity('stream_events', row): row for row in rows}

    def verify(payload):
        _, found = retention_recovery.verify_archive(manifest, payload, expected)
        require(found == expected, 'synthetic row contents differ')

    require(len(body) <= MAX_BYTES, 'object exceeds approved size')
    verify(body)
    report['object_path'] = key
    opener = build_opener(ProxyHandler({}), NoRedirect())
    token = config['SUPABASE_SECRET_KEY']
    headers = {'apikey': token, 'Authorization': 'Bearer '+token, 'Cache-Control': 'no-store'}
    base = endpoint + '/storage/v1/object/'

    def request(method, path, expected_status, data=None):
        report['attempts'] += 1
        request_headers = dict(headers)
        if data is not None:
            request_headers.update({'x-upsert': 'false', 'Content-Type': 'application/gzip'})
        req = Request(base+path, data=data, method=method, headers=request_headers)
        try:
            with opener.open(req, timeout=10) as response:
                require(response.status in expected_status, f'{method} HTTP {response.status}')
                if method == 'GET':
                    payload = response.read(MAX_BYTES+1)
                    require(len(payload) <= MAX_BYTES, 'readback exceeds approved size')
                    return payload
        except HTTPError as error:
            error.close()
            require(error.code in expected_status, f'{method} HTTP {error.code}')

    get_path = f'authenticated/{BUCKET}/{key}'
    report['stage'] = 'isolated object absence'
    request('GET', get_path, {404})
    report['stage'] = 'conditional upload'
    request('POST', f'{BUCKET}/{key}', set(range(200,300)), body)
    report['stage'] = 'authenticated readback'
    verify(request('GET', get_path, {200}))
    report.update(result='PASS', bytes=len(body), sha256=digest, rows=len(rows),
                  first=list(expected)[0], last=list(expected)[-1], objects=1, structured_rows=0)


def deadline(*_):
    raise Hold('probe deadline expired')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--live', action='store_true')
    mode.add_argument('--mock', type=Path)
    args = parser.parse_args()
    report = {'stage': 'runtime binding', 'attempts': 0}
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(170)
    try:
        main(args, report)
    except Exception as error:
        report.update(result='BLOCKED' if report['attempts']==0 else 'FAIL',
                      reason=str(error) if isinstance(error, Hold) else type(error).__name__)
    finally:
        signal.alarm(0)
    print(json.dumps(report))
    sys.exit(report['result'] != 'PASS')
