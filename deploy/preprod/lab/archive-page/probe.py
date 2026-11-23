"""Exercise the archive page and private object in a fresh local Supabase stack."""
import argparse
import json
import os
import stat
from pathlib import Path
import secrets
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import psycopg

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('status', type=Path)
parser.add_argument('--fixture-state', type=Path, help='Private local file for repeatable fixture sign-in')
parser.add_argument('--read-after', type=int, help='Print the first fixture account’s Edge page after this ID')
args = parser.parse_args()
if args.read_after is not None and (args.read_after < 0 or not args.fixture_state or not args.fixture_state.is_file()):
    parser.error('Reading a page requires an existing fixture state and a nonnegative cursor')
config = json.loads(args.status.read_text())
base = "http://127.0.0.1:57321"
if config["API_URL"] != base:
    raise SystemExit("Use a fresh isolated Supabase lab on port 57321")


def call(path, method, key, token=None, body=None, expected=(200,), binary=False):
    headers = {"apikey": key, "Authorization": "Bearer " + (token or key)}
    if body is not None:
        headers["Content-Type"] = "application/octet-stream" if binary else "application/json"
    data = body if binary or body is None else json.dumps(body).encode()
    request = Request(base + path, method=method, headers=headers, data=data)
    try:
        response = urlopen(request, timeout=20)
    except HTTPError as error:
        response = error
    with response:
        if response.status not in expected:
            raise RuntimeError(f"{method} {path.split('?')[0]} returned {response.status}")
        return response.read()


anon = config["ANON_KEY"]
service = config["SERVICE_ROLE_KEY"]
def new_fixture():
    return {
        'accounts': [
            {'email': f'{uuid4()}@example.test', 'password': secrets.token_urlsafe(24)}
            for _ in range(2)
        ],
        'bucket': 'archive-lab-' + uuid4().hex,
    }


if args.fixture_state:
    try:
        descriptor = os.open(args.fixture_state, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        with args.fixture_state.open() as stream:
            mode = os.fstat(stream.fileno())
            if not stat.S_ISREG(mode.st_mode) or mode.st_uid != os.getuid() or mode.st_mode & 0o077:
                raise SystemExit('Fixture state must be an owner-only local file')
            fixture = json.load(stream)
    else:
        fixture = new_fixture()
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(fixture, stream)
else:
    fixture = new_fixture()

users = []
for account in fixture['accounts'][:1] if args.read_after is not None else fixture['accounts']:
    auth = json.loads(call('/auth/v1/token?grant_type=password', 'POST', anon,
                           body=account, expected=(200, 400)))
    if 'access_token' not in auth and args.read_after is not None:
        raise RuntimeError('The local fixture account could not sign in')
    if 'access_token' not in auth:
        auth = json.loads(call('/auth/v1/signup', 'POST', anon, body=account))
    users.append((auth['user']['id'], auth['access_token']))

if args.read_after is not None:
    response = call('/functions/v1/archive-page?after=' + str(args.read_after), 'GET', anon, users[0][1])
    print(json.dumps(json.loads(response)))
    raise SystemExit(0)

with psycopg.connect(host="127.0.0.1", port=57322, user="postgres",
                     password="postgres", dbname="postgres") as db:
    if db.execute("SELECT to_regclass('public.lab_archive_rows') IS NULL").fetchone()[0]:
        db.execute(Path(__file__).with_name("fixture.sql").read_text())
    for (user, _), count in zip(users, [525, 1]):
        db.execute("""insert into public.lab_archive_rows
            select %s::uuid, case when i <= 500 then 'A' else 'B' end,
            i, '0.500000000000000001' from generate_series(1, %s) i ON CONFLICT DO NOTHING""", (user, count))
    db.execute("notify pgrst, 'reload schema'")

# PostgREST asynchronously refreshes its schema cache after the NOTIFY.
for attempt in range(30):
    ready = call("/rest/v1/rpc/lab_archive_page", "POST", anon, users[1][1],
                 {"after_id": 1}, expected=(200, 404))
    if json.loads(ready) == []:
        break
    if attempt == 29 or json.loads(ready).get("code") != "PGRST202":
        raise RuntimeError("PostgREST did not load the fixture function")
    time.sleep(0.2)

for (_, token), count in zip(users, [525, 1]):
    for after in (0, 500):
        want = [{"generation": "A" if i <= 500 else "B", "outbox_id": i,
                 "decimal_text": "0.500000000000000001"}
                for i in range(after + 1, min(count, after + 500) + 1)]
        rest = call("/rest/v1/rpc/lab_archive_page", "POST", anon, token, {"after_id": after})
        edge = call("/functions/v1/archive-page?after=" + str(after), "GET", anon, token)
        assert json.loads(rest) == json.loads(edge) == want

call("/rest/v1/rpc/lab_archive_page", "POST", anon, body={"after_id": 0}, expected=(401, 403))
call("/functions/v1/archive-page", "GET", anon, expected=(401, 403))
call("/functions/v1/archive-page?after=-1", "GET", anon, users[0][1], expected=(400,))
bucket = fixture['bucket']
bucket_result = json.loads(call('/storage/v1/bucket/' + bucket, 'GET', service, expected=(200, 400, 404)))
if bucket_result.get('id') != bucket:
    call('/storage/v1/bucket', 'POST', service, body={'id': bucket, 'name': bucket, 'public': False})
elif bucket_result.get('public') is not False:
    raise RuntimeError('Expected the lab bucket to be private')
raw = b'{"source":"fixture","price":"0.500000000000000001"}\n'
obj = "/storage/v1/object/" + bucket + "/tick.ndjson"
existing = call(obj, "GET", service, expected=(200, 400, 404))
if existing != raw:
    call(obj, "POST", service, body=raw, binary=True, expected=(200, 201))
assert call(obj, "GET", service) == raw
call(obj, "GET", anon, expected=(400, 401, 403, 404))
print("Passed: two scoped identities, first and next pages, decimal-text parity, anonymous denial, invalid cursor, private object byte readback.")
