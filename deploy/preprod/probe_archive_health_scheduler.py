"""Exercise archive health scheduling on the dedicated local Supabase lab."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import os
import sys
import time

import psycopg
from psycopg.types.json import Jsonb
from postgres.retirement_telemetry import summarize

from archive_status_sample import classify_observation

if len(sys.argv) != 2:
    raise SystemExit("usage: probe_archive_health_scheduler.py HISTORICAL_AUDIT_JSON")

with Path(sys.argv[1]).open() as source:
    report = summarize(json.load(source))
assert report["outcome"] == "completed" and report["retirement_authorized"] is False

connection = dict(host="127.0.0.1", port=57322, user="postgres", password=os.environ["TRADEBOT_HEALTH_LAB_PASSWORD"],
                  dbname="postgres", autocommit=True)
queue = "lab_archive_health"
now = datetime(2026, 11, 19, 19, tzinfo=timezone.utc)
max_age = timedelta(minutes=2)
fresh = {
    "scope": "pp_live_read_only_resource_sample",
    "origin_id": "pp-live-pp",
    "observed_at_utc": now.isoformat(),
    "database": {"writer": {"collector_enabled": False, "generation_id": "generated-A"}},
}
samples = {
    "historical-complete": fresh,
    "stale-observation": dict(fresh, observed_at_utc=(now - timedelta(minutes=3)).isoformat()),
}
with psycopg.connect(**connection) as db:
    db.execute("CREATE EXTENSION IF NOT EXISTS pg_cron")
    db.execute("CREATE EXTENSION IF NOT EXISTS pgmq")
    db.execute("CREATE SCHEMA archive_health_lab")
    db.execute("""
        CREATE TABLE archive_health_lab.signal (
            job_key text PRIMARY KEY,
            status text NOT NULL,
            first_page_seconds numeric,
            observation text NOT NULL,
            collector text NOT NULL
        )
    """)
    db.execute("SELECT pgmq.create(%s)", (queue,))
    db.execute("CREATE TABLE archive_health_lab.scheduled_key (key text PRIMARY KEY)")
    statement = """
        WITH scheduled AS (
            INSERT INTO archive_health_lab.scheduled_key VALUES ('historical-complete')
            ON CONFLICT DO NOTHING RETURNING key
        )
        SELECT pgmq.send('lab_archive_health', jsonb_build_object('key', key)) FROM scheduled
    """
    job = db.execute("SELECT cron.schedule('lab-archive-health', '1 second', %s)", (statement,)).fetchone()[0]

    def read(visibility):
        return db.execute("SELECT msg_id,read_ct,message FROM pgmq.read(%s,%s,1)", (queue,visibility)).fetchone()

    try:
        until = time.monotonic() + 15
        first = None
        while first is None and time.monotonic() < until:
            first = read(2)
            if first is None:
                time.sleep(0.1)
        assert first and first[1:] == (1, {"key":"historical-complete"})
    finally:
        assert db.execute("SELECT cron.unschedule(%s)", (job,)).fetchone()[0]

    def publish(message_id, key, evidence):
        status = evidence["outcome"] if evidence else "unknown"
        seconds = evidence["first_page"]["seconds"] if evidence else None
        sample = classify_observation(samples.get(key), now=now, max_age=max_age)
        db.execute(
            "INSERT INTO archive_health_lab.signal VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (key, status, seconds, sample["observation"], sample["collector"]),
        )
        assert db.execute("SELECT pgmq.archive(%s,%s)", (queue,message_id)).fetchone()[0]

    with db.transaction(force_rollback=True):
        publish(first[0],first[2]["key"],report)
    assert db.execute("SELECT count(*) FROM archive_health_lab.signal").fetchone()[0] == 0
    time.sleep(2.05)
    retry = read(5)
    assert retry == (first[0],2,first[2])
    with db.transaction():
        publish(retry[0],retry[2]["key"],report)

    # A second schedule or delivery with the same logical key keeps a single status.
    db.execute("SELECT pgmq.send(%s,%s)", (queue,Jsonb(first[2])))
    db.execute("SELECT pgmq.send(%s,%s)", (queue,Jsonb({"key":"missing-evidence"})))
    db.execute("SELECT pgmq.send(%s,%s)", (queue, Jsonb({"key": "stale-observation"})))
    while message := read(5):
        key = message[2]["key"]
        with db.transaction():
            publish(message[0],key,report if key == first[2]["key"] else None)
    result = db.execute("""
        SELECT job_key, status, first_page_seconds::text, observation, collector
        FROM archive_health_lab.signal ORDER BY job_key
    """).fetchall()
    assert result == [
        ("historical-complete", "completed", str(report["first_page"]["seconds"]), "fresh", "off"),
        ("missing-evidence", "unknown", None, "missing", "unknown"),
        ("stale-observation", "unknown", None, "stale", "unknown"),
    ], result
    print(json.dumps({"cron_delivery":True,"rolled_back_completed_status":True,
        "redelivery_same_message":True,"idempotent_duplicate":True,"missing_evidence":"unknown",
        "statuses":result,"retirement_authorized":False}))
