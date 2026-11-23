"""Measure a fixed generated page on a private Unix-socket PostgreSQL 17 cluster."""
import argparse
import json
from contextlib import nullcontext
from pathlib import Path
from statistics import median
import subprocess
import sys
import tempfile
from time import perf_counter

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from postgres.archive_codec import encoded, sha256
from postgres.history_v2_transport import HistoryV2PostgresTransport
from postgres.retirement_accounting import accounted
from tests.test_history_v2_canonical_readback import GENERATION, ORIGIN, record


def sample(transport, connection, records, expected):
    @accounted
    def read():
        returned, _ = transport.read_retirement_revisions(
            records, max_bytes=4 * 1024**2, timeout_seconds=4)
        return {"page": returned}

    # Separate counter reads from the timed call. Only this isolated process
    # submits the target query, so exactly one new execution must be observed.
    def counter():
        return connection.execute("""
            SELECT coalesce(sum(calls),0) calls,
                   coalesce(sum(total_exec_time),0) ms
            FROM pg_stat_statements
            WHERE query LIKE 'WITH sizes AS (%'
            """).fetchone()

    before = counter()
    started = perf_counter()
    result = read()
    elapsed = perf_counter() - started
    after = counter()
    assert after["calls"] - before["calls"] == 1
    assert encoded(result["page"]) == expected
    phases = result["phase_accounting"]["phases"]
    return {
        "full_page_ms": round(elapsed * 1000, 3),
        "exact_server_exec_ms": round(after["ms"] - before["ms"], 3),
        **{name + "_ms": round(phases[name]["seconds"] * 1000, 3)
           for name in ("history_exact_execute", "history_exact_fetch",
                        "history_exact_validate", "history_exact_revisions")}
    }


def benchmark(private_dir):
    connect = dict(host=str(private_dir), port=5432, dbname="postgres", user="fixture",
                   row_factory=dict_row, autocommit=True, prepare_threshold=None)
    with psycopg.connect(**connect) as connection:
        assert connection.info.server_version // 10000 == 17
        connection.execute("CREATE EXTENSION pg_stat_statements")
        for role in ("anon", "authenticated", "service_role", "tradebot_pp_history"):
            connection.execute(f"CREATE ROLE {role} NOLOGIN")
        for path in ("backend/postgres/history_v2_contract.sql",
                     "supabase/migrations/20261118012340_structured_receipts_v2.sql",
                     "supabase/migrations/20261119020000_pp_structured_revision_payloads.sql",
                     "supabase/migrations/20261119103056_pp_receipt_latest_identity_index.sql"):
            connection.execute((ROOT / path).read_text())
        transport = HistoryV2PostgresTransport(
            lambda **_: nullcontext(connection), origin_id=ORIGIN,
            generation_id=GENERATION, expected_database="postgres", expected_role="fixture",
            retain_revisions=True, indexed_latest=True)
        records = [record(index) for index in range(1, 501)]
        transport.put_structured(records, timeout_seconds=60)
        connection.execute("ANALYZE")
        expected = encoded(records)
        warmup = sample(transport, connection, records, expected)
        runs = [sample(transport, connection, records, expected) for _ in range(5)]
        return {"scope": "Synthetic 500-candle page, local Unix socket, fresh read-only transaction per run, one reused connection.",
                "limitations": "PostgreSQL execution is nested in execute. Residual includes planning, protocol, driver and local transfer. No network-only timing or hosted B speedup measured.",
                "postgres_version_num": connection.info.server_version, "driver": psycopg.__version__,
                "page_sha256": sha256(expected), "canonical_bytes": len(expected),
                "rows": len(records), "warmup": warmup, "samples": runs,
                "median": {key: median(s[key] for s in runs) for key in warmup}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-bin", type=Path, required=True,
                        help="Directory containing PostgreSQL 17 binaries")
    pg = parser.parse_args().pg_bin.resolve()
    with tempfile.TemporaryDirectory(prefix="tb-exact-", dir="/tmp") as tmp:
        data = Path(tmp) / "pgdata"
        subprocess.run([pg / "initdb", "-D", data, "-U", "fixture", "-A", "trust",
                        "--no-locale", "-E", "UTF8"], check=True, stdout=subprocess.DEVNULL)
        options = f"-k {tmp} -c listen_addresses='' -p 5432 -c shared_preload_libraries=pg_stat_statements"
        subprocess.run([pg / "pg_ctl", "-D", data, "-l", Path(tmp) / "pg.log",
                        "-o", options, "-w", "start"], check=True, stdout=subprocess.DEVNULL)
        try:
            print(json.dumps(benchmark(Path(tmp)), indent=2))
        finally:
            subprocess.run([pg / "pg_ctl", "-D", data, "-m", "fast", "-w", "stop"],
                           check=True, stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
