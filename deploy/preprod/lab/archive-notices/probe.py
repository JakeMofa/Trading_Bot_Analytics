"""Check private archive notifications against the local port-57321 Supabase lab."""
import json
from pathlib import Path
import secrets
import sys
from time import monotonic
from urllib.request import Request, urlopen
from uuid import uuid4

import psycopg
from websockets.sync.client import connect


def signup(key):
    data = json.dumps({"email": f"{uuid4()}@example.test",
                       "password": secrets.token_urlsafe(24)}).encode()
    request = Request("http://127.0.0.1:57321/auth/v1/signup", data=data,
                      headers={"apikey": key, "Content-Type": "application/json"})
    with urlopen(request, timeout=10) as response:
        user = json.load(response)
    return user["user"]["id"], user["access_token"]


def join(socket, topic, jwt):
    socket.send(json.dumps({"topic": "realtime:" + topic, "event": "phx_join",
                            "ref": "1", "join_ref": "1", "payload": {
                                "access_token": jwt, "config": {"private": True,
                                "broadcast": {"self": False, "ack": False},
                                "presence": {"key": ""}, "postgres_changes": []}}}))
    deadline = monotonic() + 10
    while True:
        msg = json.loads(socket.recv(timeout=max(0, deadline - monotonic())))
        if msg["event"] == "phx_reply" and msg["ref"] == "1":
            return msg["payload"]["status"]


def notices(socket, seconds):
    result = []
    deadline = monotonic() + seconds
    while monotonic() < deadline:
        try:
            msg = json.loads(socket.recv(timeout=max(0, deadline - monotonic())))
        except TimeoutError:
            break
        if msg["event"] == "broadcast":
            result.append(msg["payload"])
    return result


config = json.loads(Path(sys.argv[1]).read_text())
if config["API_URL"] != "http://127.0.0.1:57321":
    raise SystemExit("Expected the isolated local archive lab")
key = config["ANON_KEY"]
owner, jwt = signup(key)
_, other_jwt = signup(key)
topic = "archive-status:" + owner
url = "ws://127.0.0.1:57321/realtime/v1/websocket?vsn=1.0.0&apikey=" + key
gen = str(uuid4())
with psycopg.connect(host="127.0.0.1", port=57322, dbname="postgres", user="postgres",
                     password="postgres", autocommit=True) as db:
    if not db.execute("select to_regclass('lab_archive_notices.status')").fetchone()[0]:
        with db.transaction():
            db.execute(Path(__file__).with_name("fixture.sql").read_text())
    with connect(url) as allowed, connect(url) as denied:
        assert join(allowed, topic, jwt) == "ok"
        assert join(denied, topic, other_jwt) == "error"
        # The local Realtime service starts its replication slot on demand.
        for _ in range(15):
            db.execute("select realtime.send('{}'::jsonb, 'lab_ready', %s, true)", (topic,))
            if any(e["event"] == "lab_ready" for e in notices(allowed, 1)):
                break
        else:
            raise RuntimeError("Realtime replication did not deliver a readiness message")
        sql = """insert into lab_archive_notices.status values (%s,%s,%s)
                 on conflict (subscriber,generation) do update set phase=excluded.phase"""
        with db.transaction(force_rollback=True):
            db.execute(sql, (owner, gen, "held"))
        db.execute(sql, (owner, gen, "sealed"))
        db.execute(sql, (owner, gen, "sealed"))
        db.execute(sql, (owner, gen, "verified"))
        events = [e for e in notices(allowed, 6) if e["event"] != "lab_ready"]
        for event in events:
            event["payload"].pop("id", None)  # Supabase attaches a message UUID.
        assert [(e["event"], e["payload"]) for e in events] == [
            ("archive_status", {"generation": gen, "phase": p}) for p in ("sealed", "verified")
        ], [(e.get("event"), e.get("payload", {}).get("phase")) for e in events]
print("Passed: owner joined, other identity denied, two ordered committed notifications, duplicate and rollback silent.")
