"""Read the identical sealed trial06 B page via the deployed PP32 verifier.

Run inside the operator's retained-readonly container with /app/backend on
PYTHONPATH. Output contains timings and digests; no archived rows or DSNs.
"""
import argparse
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import time

from postgres.archive_codec import ArchiveIntegrityError, encoded
from postgres.history_v2_transport import HistoryV2PostgresTransport
from postgres.lifecycle import ArchiveWorker, LifecycleRepository
from postgres.pp_history_connection import PPHistoryConnectionFactory
from postgres.pp_history_session import ReusablePPHistoryConnectionFactory

ORIGIN = 'pp-live-pp-trial-20261119-06'
GENERATION = 'e07e981a-2617-43ac-a050-fcf4455a12f1'
ROLE = 'tradebot_pp_trial_20261119_06_reader'
PAGE_SIZE = 500
BYTE_CAP = 4 * 1024 * 1024
PAGE_SECONDS = 4


def check(value, reason):
    if not value:
        raise ArchiveIntegrityError(reason)


def page_pin(records):
    ids = [r['id'] for r in records]
    check(len(ids) == PAGE_SIZE and ids == sorted(set(ids)) and ids[0] > 0,
          'first-page IDs invalid')
    check(all(r['origin_id'] == ORIGIN and str(r['generation_id']) == GENERATION for r in records),
          'unexpected page identity')
    body = encoded(records)
    check(len(body) <= BYTE_CAP, 'page exceeds byte bound')
    return dict(rows=len(ids), first_id=ids[0], last_id=ids[-1],
                ordered_ids_sha256=sha256(encoded(ids)).hexdigest(),
                canonical_sha256=sha256(body).hexdigest(), canonical_bytes=len(body)), body


def local_page(factory):
    with factory() as db, db.transaction():
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        db.execute("SET LOCAL transaction_timeout='5s'")
        db.execute("SET LOCAL statement_timeout='2s'")
        identity = db.execute("SELECT current_user AS role,current_database() AS db,"
                              "current_setting('transaction_read_only') AS ro").fetchone()
        check(identity == {'role':'tradebot_reader','db':'tradebot_pp','ro':'on'}, 'local identity')
        active = db.execute('SELECT 1 FROM ops.writer_state WHERE collector_enabled '
                            'OR collector_session_id IS NOT NULL OR collector_lease_expires_at IS NOT NULL '
                            'LIMIT 1').fetchone()
        check(active is None, 'writers active')
        rows = LifecycleRepository._pending(db, GENERATION, PAGE_SIZE, include_acknowledged=True,
                                            max_bytes=BYTE_CAP, after_id=0)
    return ArchiveWorker.structured_records(rows)


class Timings:
    def __init__(self):
        self.parts = defaultdict(float)

    @contextmanager
    def measure(self, name):
        started = time.perf_counter()
        try:
            yield
        finally:
            self.parts[name] += time.perf_counter() - started


class TimedCursor:
    def __init__(self, cursor, times):
        self.cursor, self.times = cursor, times

    def fetchone(self):
        with self.times.measure('client_buffered_fetch_conversion'):
            return self.cursor.fetchone()

    def fetchall(self):
        with self.times.measure('client_buffered_fetch_conversion'):
            return self.cursor.fetchall()


class TimedConnection:
    def __init__(self, raw, times):
        self.raw, self.times = raw, times
        self.pipelined = False

    def transaction(self):
        return self.raw.transaction()

    def execute(self, query, params=None):
        key = 'pipeline_enqueue' if self.pipelined else 'execute_receive_driver'
        with self.times.measure(key):
            cursor = self.raw.execute(query, params)
        return TimedCursor(cursor, self.times)

    @contextmanager
    def pipeline(self):
        started = time.perf_counter()
        try:
            with self.raw.pipeline():
                self.pipelined = True
                yield
                started = time.perf_counter()
        finally:
            self.pipelined = False
            self.times.parts['pipeline_drain_receive'] += time.perf_counter() - started


class ProfiledHistory(HistoryV2PostgresTransport):
    def __init__(self, factory, times):
        self.times = times
        super().__init__(factory, origin_id=ORIGIN, generation_id=GENERATION,
                         expected_database='postgres', expected_role=ROLE, indexed_latest=True)

    def _validate(self, records, **kwargs):
        with self.times.measure('input_validate_encode'):
            return super()._validate(records, **kwargs)

    def _decode_revisions(self, rows, ids, max_bytes, **kwargs):
        with self.times.measure('revision_decode_integrity'):
            return super()._decode_revisions(rows, ids, max_bytes, **kwargs)


def stats_snapshot(factory):
    """Quiet-window aggregation of the reader's history SQL only; no SQL text leaves the DB."""
    try:
        with factory(timeout_seconds=4) as db, db.transaction():
            db.execute('SET TRANSACTION READ ONLY')
            db.execute("SET LOCAL statement_timeout='2s'")
            marker = db.execute("SELECT stats_reset, dealloc FROM extensions.pg_stat_statements_info").fetchone()
            rows = db.execute("""SELECT queryid, calls, rows, total_exec_time
                FROM extensions.pg_stat_statements
                WHERE dbid=(SELECT oid FROM pg_database WHERE datname=current_database())
                AND userid=(SELECT oid FROM pg_roles WHERE rolname=current_user)
                AND toplevel AND query ILIKE '%history_v2%' AND query NOT ILIKE '%pg_stat_statements%'
                """).fetchall()
        return marker, {r['queryid']:r for r in rows}
    except Exception:
        return None


def stats_delta(before, after):
    if before is None or after is None or before[0] != after[0]:
        return None
    old, new = before[1], after[1]
    if not old.keys() <= new.keys():
        return None
    calls = rows = 0
    milliseconds = 0.0
    for key, current in new.items():
        prior = old.get(key, {})
        changes = [current[name] - prior.get(name, 0) for name in ('calls','rows','total_exec_time')]
        if min(changes) < 0:
            return None
        calls += changes[0]
        rows += changes[1]
        milliseconds += changes[2]
    if not calls:
        return None
    return dict(calls=calls, rows=rows, server_execution_seconds=round(milliseconds / 1000, 6))


def profile(local, remote, pin, sample_stats=None):
    runs = []
    connections = []
    for label in ('cold_session','warm_session_1','warm_session_2','warm_session_3'):
        times = Timings()
        @contextmanager
        def checkout(*, timeout_seconds):
            started = time.perf_counter()
            with remote(timeout_seconds=timeout_seconds) as db:
                times.parts['hosted_checkout'] += time.perf_counter() - started
                if connections:
                    check(db is connections[0], 'warm session was replaced')
                else:
                    connections.append(db)
                yield TimedConnection(db, times)

        before = sample_stats() if sample_stats else None
        started_at_utc = datetime.now(timezone.utc).isoformat()
        started = time.perf_counter()
        with times.measure('local_page_preparation'):
            records = local_page(local)
            current, canonical = page_pin(records)
            check(current == pin, 'sealed page differs from pin')
        verifier = ProfiledHistory(checkout, times)
        with times.measure('hosted_verified_read_wall'):
            archived, _ = verifier.read_retirement_revisions(records, max_bytes=BYTE_CAP,
                                                              timeout_seconds=PAGE_SECONDS)
        with times.measure('final_byte_comparison'):
            check(encoded(archived) == canonical, 'authenticated bytes differ')
        elapsed = time.perf_counter() - started
        ended_at_utc = datetime.now(timezone.utc).isoformat()
        after = sample_stats() if sample_stats else None
        runs.append(dict(mode=label, started_at_utc=started_at_utc, ended_at_utc=ended_at_utc,
                         seconds=round(elapsed, 6), under_four_seconds=elapsed < 4,
                         phase_seconds={k:round(v,6) for k,v in times.parts.items()},
                         history_sql_counters=stats_delta(before,after)))
    return runs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--without-server-stats', action='store_true')
    args = parser.parse_args()
    from postgres.connection import connect
    from postgres.pp_structured_probe import private_dsn
    from postgres.pp_retained_archive_audit import check_environment
    from postgres.pp_retained_b_local_diagnostic import diagnose, LOCAL_DSN
    check_environment(os.environ, origin=ORIGIN)
    dsn = private_dsn(LOCAL_DSN)
    def local():
        return connect(dsn, environment='preprod', readonly=True)
    # Full seal/attachment/manifest/ACK checks precede measured page reads.
    baseline = diagnose(local)
    pin, _ = page_pin(local_page(local))
    check(all(pin[k] == baseline[k] for k in ('canonical_bytes','canonical_sha256','ordered_ids_sha256')),
          'retained diagnostic and pin disagree')
    params = ('/run/secrets/pp_trial_history_reader_dsn','/run/secrets/pp_history_ca')
    remote = ReusablePPHistoryConnectionFactory(*params, origin_id=ORIGIN, reader=True)
    observer = PPHistoryConnectionFactory(*params, origin_id=ORIGIN, reader=True)
    try:
        sample = None if args.without_server_stats else lambda: stats_snapshot(observer)
        runs = profile(local, remote, pin, sample)
        print(json.dumps(dict(status='verified', origin=ORIGIN, generation=GENERATION,
              pin=pin, runs=runs, cold_definition='first hosted physical session; disk caches uncontrolled',
              counters='scoped history SQL only, comparable with exclusive quiet reader',
              phase_timings_overlap=True, pure_transfer_seconds=None, retirement_authorized=False)))
    finally:
        remote.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps(dict(status='HOLD', error_type=type(error).__name__, retirement_authorized=False)))
        raise SystemExit(1) from None
