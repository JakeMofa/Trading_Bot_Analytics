"""Compare the full archive write/readback/ACK on a pinned 1,000-row .4 sample.

Accepts only an operator-supplied export from the retained read-only snapshot,
never a DSN or a remote endpoint. Fixture initialization uses a fresh PG17
Unix socket with TCP disabled. Output contains timings and checksums only.
"""

import argparse, sys, json, time, statistics
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "backend/tests")]
from postgres.archive_codec import encoded, sha256
from postgres.cloud_origin_binding import cloud_binding
from postgres.connection import connect
from postgres.lifecycle import LifecycleRepository
from postgres.outbox_packing import envelope
from postgres.active_structured import ActiveStructuredWorker
from postgres.archive_codec import ArchiveLimits

RECURRING_LIMITS = ArchiveLimits(
    max_rows=50,
    max_object_bytes=262144,
    max_decoded_bytes=262144,
    max_cycle_bytes=524288,
    max_requests=2,
    max_seconds=20,
    request_timeout_seconds=4,
)
from postgres.history_v2_transport import HistoryV2PostgresTransport
from test_pp_initial_trial_drain import InitialSealNative as Native

O = "pp-live-pp-display-20261127-02"
G = "e11000be-bcb0-4b45-9c13-dd8f65a99b67"
CLOUD = cloud_binding(O)
PIN = "45abec643063a9e16528863dfcdc696e7fb600c1e6e0152654cf15038eea374a"


def run(mode, rows):
    expected = [r["id"] for r in rows]
    Native.setUpClass()
    try:
        assert str(Native.socket).startswith("/tmp/initial-trial-seal-")
        with Native.admin("postgres") as db:
            db.execute(
                "CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role"
            )
            for sql in sorted((ROOT / "supabase/migrations").glob("*.sql")):
                db.execute(sql.read_text())
            db.execute(
                (
                    ROOT / "supabase/review/pp_display_20261127_02_structured.sql"
                ).read_text()
            )
            for role in (CLOUD.writer_role, CLOUD.reader_role):
                db.execute("ALTER ROLE " + role + " LOGIN")
        with Native.admin() as db:
            db.execute(
                """INSERT INTO archive.generations(origin_id,generation_id,slot,state,partition_name,created_at,started_at)
     VALUES(%s,%s,'A','collecting',%s,now(),now())""",
                (O, G, "events_g_" + G.replace("-", "")),
            )
            params = [
                (
                    r["id"],
                    O,
                    G,
                    r["entity_type"],
                    r["entity_id"],
                    r["content_hash"],
                    Jsonb(r["payload"]),
                    r["created_at"],
                )
                for r in rows
            ]
            db.cursor().executemany(
                """INSERT INTO ops.outbox(id,origin_id,generation_id,entity_type,entity_id,content_hash,payload,created_at)
    OVERRIDING SYSTEM VALUE VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
                params,
            )
            db.execute("ANALYZE ops.outbox")
        repo = LifecycleRepository(lambda: connect(Native.lifecycle_dsn))
        if mode == "conservative":

            def old(g, n, b):
                with repo.transaction() as db:
                    return repo._pending(db, g, n, max_bytes=b)

            repo.outbox = old
        host = psycopg.connect(
            host=str(Native.socket),
            dbname="postgres",
            user=CLOUD.writer_role,
            row_factory=dict_row,
            autocommit=True,
        )

        @contextmanager
        def factory(*, timeout_seconds):
            yield host

        t = HistoryV2PostgresTransport(
            factory,
            origin_id=O,
            generation_id=G,
            expected_database="postgres",
            expected_role=CLOUD.writer_role,
            retain_revisions=True,
            sync_barriers=True,
        )
        obs = Counter()
        pages = []
        ident = []

        def measure(obj, attr, field, record=False):
            func = getattr(obj, attr)

            def wrapper(*args, **kwargs):
                start = time.perf_counter()
                v = func(*args, **kwargs)
                obs[field] += time.perf_counter() - start
                if record:
                    records = args[0]
                    size = len(encoded(records))
                    assert len(records) <= 50 and size <= 262144
                    pages.append([len(records), size])
                    ident.extend(r["id"] for r in records)
                return v

            setattr(obj, attr, wrapper)

        measure(repo, "outbox", "local_page_sql_fetch_and_pack")
        measure(repo, "acknowledge", "local_ack")
        measure(t, "put_structured", "archive_import", True)
        measure(t, "read_structured_authenticated", "authenticated_readback")
        worker = ActiveStructuredWorker(repo, t, origin_id=O, limits=RECURRING_LIMITS)
        start = time.perf_counter()
        count = 0
        while count < len(rows):
            v = worker.cycle(G)
            assert v["status"] == "acknowledged"
            count += v["acknowledged"]
        total = time.perf_counter() - start
        assert ident == expected
        with psycopg.connect(
            host=str(Native.socket),
            dbname="postgres",
            user=CLOUD.reader_role,
            row_factory=dict_row,
        ) as ro:
            ro.read_only = True
            hosted = ro.execute(
                "SELECT outbox_id,envelope FROM history_v2.structured_revision_payloads WHERE origin_id=%s AND generation_id=%s ORDER BY outbox_id",
                (O, G),
            ).fetchall()
            assert len(hosted) == len(rows)
            assert all(
                r["outbox_id"] == s["id"]
                and bytes(r["envelope"]) == encoded(envelope(s))
                for r, s in zip(hosted, rows)
            )
        with Native.admin() as db:
            assert db.execute(
                "SELECT count(*) AS n FROM ops.outbox WHERE acknowledged_at IS NOT NULL"
            ).fetchone()["n"] == len(rows)
        host.close()
        return dict(
            mode=mode,
            pages=len(pages),
            rows=len(ident),
            rows_per_page=round(len(rows) / len(pages), 3),
            median_rows_per_page=statistics.median(p[0] for p in pages),
            max_page_bytes=max(p[1] for p in pages),
            total_encoded_bytes=sum(p[1] for p in pages),
            seconds=round(total, 6),
            rows_per_second=round(len(rows) / total, 3),
            phase_seconds={k: round(v, 6) for k, v in obs.items()},
            hosted_and_local_ack_verified=1000,
        )
    finally:
        Native.tearDownClass()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Private JSON result of the first 1,000 .4 rows ordered by id",
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="Metadata-only measurement file"
    )
    args = parser.parse_args()
    if args.input.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("input exceeds bounded export size")
    rows = json.loads(args.input.read_bytes())
    if len(rows) != 1000 or sha256(encoded([envelope(r) for r in rows])) != PIN:
        raise ValueError("expected exact retained .4 page pin")
    if not all(
        r["origin_id"] == O
        and r["generation_id"] == G
        and r["acknowledged_at"] is not None
        for r in rows
    ):
        raise ValueError("scope or acknowledgement mismatch")
    expected = [r["id"] for r in rows]
    out = []
    for mode in ("conservative", "exact", "exact", "conservative"):
        r = run(mode, rows)
        out.append(r)
        print(json.dumps(r), flush=True)
    j = dict(
        origin=O,
        generation=G,
        collector_release="60bb1c8968e2fe08ff9493b8f84ccf5f877aa674",
        workload="first 1000 committed retained .4 outbox rows ordered by actual id; export under one PP read-only snapshot; replay only on disposable PG17 Unix sockets",
        min_id=expected[0],
        max_id=expected[-1],
        canonical_input_sha256=sha256(encoded([envelope(r) for r in rows])),
        row_limit=RECURRING_LIMITS.max_rows,
        decoded_byte_limit=RECURRING_LIMITS.max_decoded_bytes,
        phases="Import and authenticated readback include driver, database and loopback transfer. No production network latency simulated. The restricted second role verified every final canonical envelope.",
        runs=out,
    )
    args.output.write_text(json.dumps(j, indent=2) + "\n")
