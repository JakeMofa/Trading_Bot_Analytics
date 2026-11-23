"""Exercise the archive page and private object in a fresh local Supabase stack."""
import json
from pathlib import Path
import secrets
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import psycopg

config = json.loads(Path(sys.argv[1]).read_text())
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
users = []
for _ in range(2):
    auth = json.loads(call("/auth/v1/signup", "POST", anon, body={
        "email": f"{uuid4()}@example.test", "password": secrets.token_urlsafe(24)
    }))
    users.append((auth["user"]["id"], auth["access_token"]))

with psycopg.connect(host="127.0.0.1", port=57322, user="postgres",
                     password="postgres", dbname="postgres") as db:
    db.execute(Path(__file__).with_name("fixture.sql").read_text())
    for (user, _), count in zip(users, [525, 1]):
        db.execute("""insert into public.lab_archive_rows
            select %s::uuid, case when i <= 500 then 'A' else 'B' end,
            i, '0.500000000000000001' from generate_series(1, %s) i""", (user, count))
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
bucket = "archive-lab-" + uuid4().hex
call("/storage/v1/bucket", "POST", service, body={"id": bucket, "name": bucket, "public": False})
raw = b'{"source":"fixture","price":"0.500000000000000001"}\n'
obj = "/storage/v1/object/" + bucket + "/tick.ndjson"
call(obj, "POST", service, body=raw, binary=True, expected=(200, 201))
assert call(obj, "GET", service) == raw
call(obj, "GET", anon, expected=(400, 401, 403, 404))
print("Passed: two scoped identities, first and next pages, decimal-text parity, anonymous denial, invalid cursor, private object byte readback.")
