"""Phase 1.75.9 verified local retention for raw SQLite evidence.

A raw row is eligible for local deletion only when it is older than the
retention cutoff AND lies inside the source range of a verified raw_archives
manifest (verified_at set after authenticated readback + SHA-256). A sync
checkpoint is never trusted on its own. Only `observations` and
`stream_events` are ever touched. Nothing here runs VACUUM, and live
forecasting never imports or depends on this module.
"""
from bisect import bisect_left, bisect_right
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import copy
import hashlib
from pathlib import Path
import json
import os
import re
import sqlite3
import time

import retention_timestamp_guards as timestamp_guards


DEFAULT_RETENTION_HOURS = 48
DEFAULT_DELETE_BATCH_SIZE = 5000
MANIFEST_COLUMNS = (
    "source,bucket,object_path,sha256,event_count,compressed_bytes,"
    "first_source_id,last_source_id,started_at,ended_at,verified_at,metadata"
)
# SQL normalization is exact (no julianday rounding of microseconds). Validation
# runs separately before any comparison or deletion. Stored evidence is untouched.
TIME_KEY = "(CASE WHEN length(received_at)=25 THEN substr(received_at,1,19)||'.000000+00:00' ELSE received_at END)"
UTC_TIME_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{6})?\+00:00")
MANIFEST_UTC_TIME_RE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?\+00:00")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class RetentionError(RuntimeError):
    pass


@dataclass(frozen=True)
class Spec:
    table: str
    source: str
    key_sql: str
    marker: str


SPECS = {
    "observations": Spec("observations", "polymarket", "id", "?"),
    "stream_events": Spec(
        "stream_events", "coinbase", f"({TIME_KEY},source,event_id)", "(?,?,?)"
    ),
}


def _enabled(value):
    return str(value).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class RetentionConfig:
    enabled: bool = False
    hours: int = DEFAULT_RETENTION_HOURS
    batch_size: int = DEFAULT_DELETE_BATCH_SIZE

    @classmethod
    def from_env(cls):
        return cls.build(
            os.getenv("ENABLE_LOCAL_RETENTION", "false"),
            os.getenv("LOCAL_RAW_RETENTION_HOURS", str(DEFAULT_RETENTION_HOURS)),
            os.getenv("RETENTION_DELETE_BATCH_SIZE", str(DEFAULT_DELETE_BATCH_SIZE)),
        )

    @classmethod
    def build(cls, enabled, hours, batch_size):
        try:
            hours, batch_size = int(hours), int(batch_size)
        except (TypeError, ValueError):
            raise RetentionError("retention hours and batch size must be integers")
        if not 1 <= hours <= 24 * 365:
            raise RetentionError("LOCAL_RAW_RETENTION_HOURS must be 1..8760")
        if not 1 <= batch_size <= 50000:
            raise RetentionError("RETENTION_DELETE_BATCH_SIZE must be 1..50000")
        return cls(_enabled(enabled), hours, batch_size)


def canonical_time(value):
    """Accept only system UTC strings; normalize trusted aware datetime inputs."""
    if isinstance(value, datetime):
        dt = value
    else:
        if not isinstance(value, str) or not UTC_TIME_RE.fullmatch(value):
            raise RetentionError("unsupported received_at representation")
        try:
            dt = datetime.fromisoformat(value)
        except ValueError as exc:
            raise RetentionError("invalid received_at timestamp") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise RetentionError("timestamps must include a timezone")
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")


def canonical_manifest_time(value):
    """Normalize UTC manifest cursors; never relax the raw received_at contract."""
    if not isinstance(value, str) or not MANIFEST_UTC_TIME_RE.fullmatch(value):
        raise RetentionError("unsupported manifest timestamp representation")
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise RetentionError("invalid manifest timestamp") from exc
    return dt.isoformat(timespec="microseconds")


def retention_cutoff(now, hours):
    return canonical_time(now - timedelta(hours=hours))


def fetch_verified_manifests(cloud, bucket):
    """Read verified manifests from Supabase. Any failure aborts retention."""
    return cloud.select(
        "raw_archives",
        {
            "select": MANIFEST_COLUMNS,
            "verified_at": "not.is.null",
            "bucket": f"eq.{bucket}",
            "order": "object_path.asc",
        },
    )


def _between(spec, lo, hi):
    where = f"{spec.key_sql}>={spec.marker} AND {spec.key_sql}<={spec.marker}"
    params = (*lo, *hi)
    if spec.table == "stream_events":
        # Preserve use of the existing raw cursor index. This inclusive second
        # envelope includes both legal widths; exact canonical bounds follow.
        where = "received_at>=? AND received_at<? AND " + where
        params = (lo[0][:19], hi[0][:19] + "~", *params)
    return where, params


def _stream_range_count_validated(db, lo, hi):
    """Exact current count after global strict-UTC validation in this writer TX.

    Only boundary seconds need canonical tuple comparisons. Every valid raw
    timestamp strictly between those seconds is inside the original range,
    regardless of source/event id. No candidate clipping or cached row count.
    """
    spec=SPECS['stream_events'];first,last=lo[0][:19],hi[0][:19]
    if first==last:
        where,params=_between(spec,lo,hi)
        return _count(db,spec,where,params)
    total=_count(db,spec,'received_at>=? AND received_at<?',(first+'~',last))
    exact=f'{spec.key_sql}>={spec.marker} AND {spec.key_sql}<={spec.marker}'
    for second in (first,last):
        total+=_count(db,spec,'received_at>=? AND received_at<? AND '+exact,
                      (second,second+'~',*lo,*hi))
    return total


def _manifest_interval(dataset, manifest, bucket):
    """Return (lo, hi) key tuples, or raise ValueError naming the rejection."""
    spec = SPECS[dataset]
    meta = manifest.get("metadata") or {}
    if not manifest.get("verified_at"):
        raise ValueError("unverified")
    if manifest.get("bucket") != bucket:
        raise ValueError("wrong_bucket")
    if manifest.get("source") != spec.source or meta.get("dataset") != dataset:
        raise ValueError("wrong_dataset")
    if meta.get("verification") != "authenticated_readback_sha256":
        raise ValueError("no_readback_verification")
    if not SHA256_RE.match(str(manifest.get("sha256") or "")):
        raise ValueError("bad_checksum")
    count = manifest.get("event_count")
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        raise ValueError("bad_event_count")
    if not isinstance(manifest.get("compressed_bytes"), int) or manifest["compressed_bytes"] <= 0:
        raise ValueError("bad_object_size")
    if dataset == "observations":
        first, last = manifest.get("first_source_id"), manifest.get("last_source_id")
        for value in (first, last):
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError("missing_source_ids")
        if first > last:
            raise ValueError("bad_range")
        return (first,), (last,)
    try:
        first_key = json.loads(meta.get("first_source_key") or "null")
        last_key = json.loads(meta.get("last_source_key") or "null")
        lo = (canonical_manifest_time(manifest["started_at"]), *first_key)
        hi = (canonical_manifest_time(manifest["ended_at"]), *last_key)
    except (TypeError, ValueError, KeyError, RetentionError):
        raise ValueError("missing_cursor_keys")
    if len(lo) != 3 or len(hi) != 3 or not all(isinstance(v, str) for v in lo + hi):
        raise ValueError("missing_cursor_keys")
    if lo > hi:
        raise ValueError("bad_range")
    return lo, hi


def _merge(intervals):
    merged = []
    for lo, hi in sorted(intervals):
        if merged and lo <= merged[-1][1]:
            if hi > merged[-1][1]:
                merged[-1] = (merged[-1][0], hi)
        else:
            merged.append((lo, hi))
    return merged


def _bad_time_format(db, table):
    if timestamp_guards.available(db, table):
        return timestamp_guards.invalid_exists(db, table)
    if _load_native_time_validator(db):
        return db.execute(f"SELECT 1 FROM {table} WHERE NOT retention_raw_time_valid_v1(received_at) LIMIT 1").fetchone() is not None
    def valid(value):
        try:
            canonical_time(value)
            return 1
        except RetentionError:
            return 0
    db.create_function("retention_valid_time", 1, valid, deterministic=True)
    return db.execute(
        f"SELECT 1 FROM {table} WHERE NOT retention_valid_time(received_at) LIMIT 1"
    ).fetchone() is not None


def _count(db, spec, where, params):
    return db.execute(
        f"SELECT COUNT(*) FROM {spec.table} WHERE {where}", params
    ).fetchone()[0]


class _PreparedManifests(list):
    """Private immutable evidence copy; no current-local facts are cached here."""
    def __init__(self, manifests, bucket):
        super().__init__(copy.deepcopy(manifests))
        self.bucket = bucket
        self.parsed = {}
        for dataset, spec in SPECS.items():
            valid, rejected, considered = [], {}, 0
            for manifest in self:
                if manifest.get("source") != spec.source:
                    continue
                considered += 1
                try:
                    lo, hi = _manifest_interval(dataset, manifest, bucket)
                except ValueError as exc:
                    reason = str(exc)
                    rejected[reason] = rejected.get(reason, 0) + 1
                else:
                    valid.append((lo, hi, manifest["event_count"]))
            self.parsed[dataset] = (valid, rejected, considered)


# The optional binary is built from this reviewed source, never downloaded or
# compiled by application startup. Its manifest pins both source and binary.
NATIVE_TIME_SOURCE_SHA256 = "52df693629ff13f85b5bffbfb30bf8388f9e20ebb836780632678531c7d23c7a"


def _native_library_path():
    return Path(__file__).with_name("_retention_time.so")


def _load_native_time_validator(db):
    library = _native_library_path()
    manifest = library.with_suffix(".json")
    if not library.exists() and not manifest.exists():
        return False  # Portable, safety-equivalent merge path retains its deadline.
    try:
        if library.is_symlink() or manifest.is_symlink():
            raise ValueError("symlink")
        if library.stat().st_size > 2 * 1024 * 1024 or manifest.stat().st_size > 4096:
            raise ValueError("oversize")
        if library.stat().st_mode & 0o022 or manifest.stat().st_mode & 0o022:
            raise ValueError("writable by another role")
        proof = json.loads(manifest.read_text())
        if (type(proof.get("format")) is not int or proof["format"] != 1
                or proof.get("source_sha256") != NATIVE_TIME_SOURCE_SHA256
                or proof.get("binary_sha256") != hashlib.sha256(library.read_bytes()).hexdigest()):
            raise ValueError("native proof mismatch")
        config = getattr(sqlite3, "SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION", None)
        if config is not None and hasattr(db, "setconfig"):
            db.setconfig(config, True)
            try:
                db.load_extension(str(library))
            finally:
                db.setconfig(config, False)
        else:
            db.enable_load_extension(True)
            try:
                db.load_extension(str(library))
            finally:
                db.enable_load_extension(False)
    except (OSError,ValueError,TypeError,AttributeError,sqlite3.Error):
        raise RetentionError("native timestamp validator unavailable or unverified") from None
    return True


class _TimestampCache:
    """Only pure timestamp validity, never mutable row/eligibility facts."""
    def __init__(self, native=False, indexed=False):
        self.native = native
        self.indexed = indexed


def _validated_timestamp_cache(db):
    if db.in_transaction:
        raise RetentionError("timestamp preparation requires no active transaction")
    if all(timestamp_guards.available(db, table) for table in SPECS):
        return _TimestampCache(indexed=True)
    if _load_native_time_validator(db):
        return _TimestampCache(native=True)
    db.execute("DROP TABLE IF EXISTS temp.retention_valid_times")
    db.execute("DROP TABLE IF EXISTS temp.retention_fresh_valid_times")
    db.execute("CREATE TEMP TABLE retention_valid_times(value TEXT PRIMARY KEY) WITHOUT ROWID")
    db.execute("CREATE TEMP TABLE retention_fresh_valid_times(value TEXT PRIMARY KEY) WITHOUT ROWID")
    try:
        for table in SPECS:
            cursor = db.execute(f"SELECT DISTINCT received_at FROM {table}")
            try:
                while True:
                    rows = cursor.fetchmany(1000)
                    if not rows:
                        break
                    for (value,) in rows:
                        canonical_time(value)
                    db.executemany("INSERT OR IGNORE INTO temp.retention_valid_times VALUES(?)", rows)
            finally:
                cursor.close()
        db.commit()  # TEMP preparation only; no caller transaction is inherited.
    except BaseException:
        db.rollback()
        db.execute("DROP TABLE IF EXISTS temp.retention_valid_times")
        db.execute("DROP TABLE IF EXISTS temp.retention_fresh_valid_times")
        raise
    return _TimestampCache()


def _validate_current_timestamps(db, timestamp_cache, timings=None):
    """Fresh global scan in SQLite; Python only validates previously unseen strings."""
    if not isinstance(timestamp_cache, _TimestampCache):
        raise RetentionError("timestamp cache was not prepared")
    for table in SPECS:
        if timestamp_cache.indexed:
            # Current schema + current invalid membership, protected by the same
            # writer transaction as DELETE; no mutable validity certificate.
            if timestamp_guards.invalid_exists(db, table):
                raise RetentionError("unsupported received_at at apply; refusing deletes")
            continue
        if timestamp_cache.native:
            # Native fixed-format/calendar validation removes sort/cache probes,
            # not the fresh global scan. Every current row is checked under the
            # caller's writer lock, including unrelated/unapproved identities.
            with _measure_phase(timings if timings is not None else {}, "timestamp_"+table):
                if db.execute(f"SELECT 1 FROM {table} WHERE NOT retention_raw_time_valid_v1(received_at) LIMIT 1").fetchone():
                    raise RetentionError("unsupported received_at at apply; refusing deletes")
            continue
        # Ordered set difference lets SQLite merge covering-index streams instead
        # of performing a fresh B-tree lookup for every known timestamp. Binary
        # collation is explicit: case-distinct malformed evidence must not match.
        cursor = db.execute(f"""SELECT received_at COLLATE BINARY FROM {table}
          EXCEPT SELECT value COLLATE BINARY FROM temp.retention_valid_times ORDER BY 1""")
        try:
            for (value,) in cursor:
                try:
                    canonical_time(value)
                except RetentionError:
                    raise RetentionError("unsupported received_at at apply; refusing deletes") from None
                db.execute("INSERT OR IGNORE INTO temp.retention_fresh_valid_times VALUES(?)", (value,))
        finally:
            cursor.close()
        # Do not mutate an input of the active EXCEPT cursor. Newly validated
        # strings become reusable only after that fresh statement is exhausted.
        db.execute("INSERT OR IGNORE INTO temp.retention_valid_times SELECT value FROM temp.retention_fresh_valid_times")
        db.execute("DELETE FROM temp.retention_fresh_valid_times")


def _scope_manifest_ranges(dataset, evidence, approved):
    """Static original manifests that can contain an approved identity.

    The full ORIGINAL bounds are kept, never clipped to candidate bounds. Fresh
    range counts must still include late/unapproved/newer rows that can invalidate
    the archive evidence. No current-local existence or eligibility is cached.
    """
    keys = sorted((identity[0],) if dataset == "observations" else
                  (canonical_time(identity[2]), identity[0], identity[1])
                  for identity in approved)
    return [(lo, hi, count) for lo, hi, count in evidence.parsed[dataset][0]
            if bisect_left(keys, lo) < bisect_right(keys, hi)]


def _observation_covering_index(db):
    # Reuse the deployed covering index, whose leaves include the INTEGER PRIMARY
    # KEY id. Avoid payload-table lookups for id bounds. No index is created. A
    # missing index falls back to ordinary SQL (e.g. minimal test databases).
    name = "observations_market_kind_received"
    if any(row[1] == name for row in db.execute("PRAGMA index_list(observations)")):
        if "received_at" in {row[2] for row in db.execute(f"PRAGMA index_info({name})")}:
            return name
    return None


def _stream_delete_sql(db):
    # Reuse the full existing archive cursor to verify all three exact identity
    # fields from its covering leaves. PK(source,event_id) lacks received_at.
    name="stream_events_archive_cursor"
    full=any(row[1]==name and not row[4] for row in db.execute('PRAGMA index_list(stream_events)'))
    hint=""
    if full and [row[2] for row in db.execute(f'PRAGMA index_info({name})')]==['received_at','source','event_id']:
        hint=f" INDEXED BY {name}"
    return f"DELETE FROM stream_events{hint} WHERE source=? AND event_id=? AND received_at=?"


def _warm_stream_pages(db, batch_size):
    """Read-only page warming hint, NEVER a safety/eligibility decision.

    Values are discarded. Main PK/table pages are read without a writer lock;
    SQLite refreshes them normally and all authorization checks/selection run
    again after BEGIN IMMEDIATE. A stale hint can only waste work, never expand
    the approved deletion scope or authorize a changed row.
    """
    if db.in_transaction:raise RetentionError("page warming requires unlocked connection")
    hints=db.execute("""SELECT source,event_id FROM temp.retention_pending_stream_events
        ORDER BY stamp,source,event_id,received_at LIMIT ?""",(batch_size,)).fetchall()
    for source,event_id in hints:
        db.execute('SELECT received_at FROM stream_events WHERE source=? AND event_id=?',
                   (source,event_id)).fetchone()


def _prepare_pending(db, dataset, identities):
    name = "retention_pending_" + dataset
    db.execute(f"DROP TABLE IF EXISTS temp.{name}")
    if dataset == "observations":
        db.execute(f"CREATE TEMP TABLE {name}(id INTEGER PRIMARY KEY)")
        db.executemany(f"INSERT INTO temp.{name} VALUES(?)", sorted((key[0],) for key in identities))
    else:
        db.execute(f"""CREATE TEMP TABLE {name}(stamp TEXT,source TEXT,event_id TEXT,received_at TEXT,
          PRIMARY KEY(stamp,source,event_id,received_at)) WITHOUT ROWID""")
        db.executemany(f"INSERT INTO temp.{name} VALUES(?,?,?,?)",
                       sorted((canonical_time(key[2]),key[0],key[1],key[2]) for key in identities))
    db.commit()


class _ValidationSnapshot:
    """Current facts are queried under the same writer lock as exact DELETE.

    No Python materialization/sort of the manifest envelope. Original range
    counts include all current rows, including unapproved/late/newer identities.
    """
    def __init__(self, db, timestamp_cache, dataset, ranges, observation_index=None, phase_timings=None):
        self.db, self.dataset, self.ranges = db, dataset, ranges
        _validate_current_timestamps(db, timestamp_cache, phase_timings)

    def __getattr__(self, name):
        return getattr(self.db, name)

    def range_count(self, lo, hi):
        if self.dataset == "stream_events":
            return _stream_range_count_validated(self.db, lo, hi)
        where, params = _between(SPECS[self.dataset], lo, hi)
        return _count(self.db, SPECS[self.dataset], where, params)

    def select(self, dataset, intervals, cutoff, protected, pending, limit):
        if dataset != self.dataset:
            raise RetentionError("validation snapshot dataset changed")
        for lo, hi in intervals:
            if dataset == "observations":
                refs = ""
                if self.db.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name='prediction_context_links'").fetchone():
                    refs = """ AND NOT EXISTS (SELECT 1 FROM prediction_context_links AS refs
                              WHERE refs.outcome_observation_id=raw.id)"""
                query = f"""SELECT raw.id FROM temp.retention_pending_observations AS p
                  CROSS JOIN observations AS raw ON raw.id=p.id
                  WHERE p.id>=? AND p.id<=? AND {TIME_KEY}<? AND raw.id<? {refs}
                  ORDER BY p.id LIMIT ?"""
                params = (lo[0],hi[0],cutoff,protected,limit)
            else:
                query = """SELECT raw.source,raw.event_id,raw.received_at
                  FROM temp.retention_pending_stream_events AS p
                  CROSS JOIN stream_events AS raw ON raw.source=p.source AND raw.event_id=p.event_id
                  WHERE (p.stamp,p.source,p.event_id)>=(?,?,?)
                    AND (p.stamp,p.source,p.event_id)<=(?,?,?) AND p.stamp<?
                    AND raw.received_at=p.received_at
                  ORDER BY p.stamp,p.source,p.event_id,p.received_at LIMIT ?"""
                params = (*lo,*hi,cutoff,limit)
            selected = [tuple(row) for row in self.db.execute(query, params)]
            if selected:
                return selected
        return []


def _usable_intervals(db, dataset, manifests, bucket):
    if isinstance(db, _ValidationSnapshot) and isinstance(manifests, _PreparedManifests):
        if manifests.bucket != bucket:
            raise RetentionError("prepared manifest bucket changed")
        valid, original_rejected, considered = manifests.parsed[dataset]
        rejected, intervals = dict(original_rejected), []
        if dataset != db.dataset:
            raise RetentionError("validation snapshot dataset changed")
        for lo, hi, event_count in db.ranges:
            # Count ALL current local identities in each original range, including
            # late rows outside approved scope. A late row can invalidate coverage.
            if db.range_count(lo, hi) > event_count:
                reason = "local_rows_exceed_manifest"
                rejected[reason] = rejected.get(reason, 0) + 1
            else:
                intervals.append((lo, hi))
        return _merge(intervals), {"considered": considered, "usable": len(intervals),
                                   "rejected": rejected}
    spec = SPECS[dataset]
    intervals, rejected = [], {}

    def reject(reason):
        rejected[reason] = rejected.get(reason, 0) + 1

    considered = 0
    for manifest in manifests:
        if manifest.get("source") != spec.source:
            continue
        considered += 1
        try:
            lo, hi = _manifest_interval(dataset, manifest, bucket)
        except ValueError as exc:
            reject(str(exc))
            continue
        where, params = _between(spec, lo, hi)
        # Local rows may only shrink after archiving; extra rows inside the range
        # mean something was never archived, so the whole manifest is untrusted.
        if _count(db, spec, where, params) > manifest["event_count"]:
            reject("local_rows_exceed_manifest")
            continue
        intervals.append((lo, hi))
    return _merge(intervals), {"considered": considered, "usable": len(intervals),
                               "rejected": rejected}


def _protected_id(db, dataset):
    # observations.id is not AUTOINCREMENT: emptying the table would let new rows
    # reuse archived IDs, so the highest ID is always kept as the sequence anchor.
    if dataset != "observations":
        return None
    return db.execute("SELECT MAX(id) FROM observations").fetchone()[0]


def _unreferenced_observations(db):
    if not db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='prediction_context_links'"
    ).fetchone():
        return "1"
    return """id NOT IN (SELECT outcome_observation_id FROM prediction_context_links
                         WHERE outcome_observation_id IS NOT NULL)"""


def _eligible_clause(db, dataset, spec, interval, cutoff, protected):
    where, params = _between(spec, *interval)
    where += f" AND {TIME_KEY}<?"
    params = (*params, cutoff)
    if protected is not None:
        where += " AND id<?"
        params = (*params, protected)
    if dataset == "observations":
        where += " AND " + _unreferenced_observations(db)
    return where, params


def _earliest_not_eligible(db, spec, intervals, cutoff, protected, dataset):
    gaps, previous = [], None
    for lo, hi in intervals:
        gaps.append((previous, lo))
        previous = hi
    gaps.append((previous, None))
    candidates = []
    for after, before in gaps:
        where, params = f"{TIME_KEY}<?", [cutoff]
        if after is not None:
            where += f" AND {spec.key_sql}>{spec.marker}"
            params += list(after)
            if dataset == "stream_events":
                where += " AND received_at>=?"
                params.append(after[0][:19])
        if before is not None:
            where += f" AND {spec.key_sql}<{spec.marker}"
            params += list(before)
            if dataset == "stream_events":
                where += " AND received_at<?"
                params.append(before[0][:19] + "~")
        row = db.execute(
            f"SELECT MIN({TIME_KEY}) FROM {spec.table} WHERE {where}", params
        ).fetchone()[0]
        if row:
            candidates.append(row)
    if protected is not None:
        row = db.execute(
            f"SELECT {TIME_KEY} FROM observations WHERE id=?", (protected,)
        ).fetchone()
        if row and row[0] < cutoff:
            candidates.append(row[0])
    if dataset == "observations":
        row = db.execute(
            f"SELECT MIN({TIME_KEY}) FROM observations WHERE NOT ("
            + _unreferenced_observations(db) + ")"
        ).fetchone()[0]
        if row:
            candidates.append(row)
    recent = db.execute(
        f"SELECT MIN({TIME_KEY}) FROM {spec.table} WHERE {TIME_KEY}>=?", (cutoff,)
    ).fetchone()[0]
    if recent:
        candidates.append(recent)
    return min(candidates) if candidates else None


def _dataset_plan(db, dataset, manifests, cutoff, now, bucket):
    spec = SPECS[dataset]
    total = db.execute(f"SELECT COUNT(*) FROM {spec.table}").fetchone()[0]
    oldest, newest = db.execute(
        f"SELECT MIN({TIME_KEY}),MAX({TIME_KEY}) FROM {spec.table}"
    ).fetchone()
    report = {
        "total_rows": total,
        "oldest_row": oldest,
        "newest_row": newest,
        "blocked": None,
    }
    if _bad_time_format(db, spec.table):
        # Reject unsupported evidence before using normalized SQL comparison keys.
        report.update(blocked="non_canonical_received_at", rows_older_than_cutoff=None,
                      eligible_rows=0, uncovered_or_unverified_old_rows=None,
                      protected_sequence_rows=0, rows_remaining_after_apply=total,
                      manifests={"considered": 0, "usable": 0, "rejected": {}})
        return report, []
    old = _count(db, spec, f"{TIME_KEY}<?", (cutoff,))
    intervals, manifest_stats = _usable_intervals(db, dataset, manifests, bucket)
    protected = _protected_id(db, dataset)
    eligible = 0
    for interval in intervals:
        where, params = _eligible_clause(db, dataset, spec, interval, cutoff, protected)
        eligible += _count(db, spec, where, params)
    referenced_rows = 0
    if dataset == "observations":
        for interval in intervals:
            where, params = _between(spec, *interval)
            where += f" AND {TIME_KEY}<? AND NOT (" + _unreferenced_observations(db) + ")"
            params = (*params, cutoff)
            if protected is not None:
                where += " AND id<?"
                params = (*params, protected)
            referenced_rows += _count(db, spec, where, params)
    protected_rows = 0
    if protected is not None and intervals:
        covered = any(lo[0] <= protected <= hi[0] for lo, hi in intervals)
        old_row = _count(db, spec, f"id=? AND {TIME_KEY}<?", (protected, cutoff))
        protected_rows = 1 if covered and old_row else 0
    uncovered = old - eligible - protected_rows - referenced_rows
    sample = db.execute(
        f"SELECT AVG(length(payload)) FROM (SELECT payload FROM {spec.table} LIMIT 2000)"
    ).fetchone()[0] or 0
    earliest = None
    if uncovered or protected_rows or referenced_rows or eligible:
        earliest = _earliest_not_eligible(
            db, spec, intervals, cutoff, protected, dataset)
    report.update(
        rows_older_than_cutoff=old,
        eligible_rows=eligible,
        uncovered_or_unverified_old_rows=uncovered,
        protected_sequence_rows=protected_rows,
        protected_reference_rows=referenced_rows,
        rows_remaining_after_apply=total - eligible,
        approx_reclaimable_payload_bytes=int(sample * eligible),
        earliest_row_remaining_after_apply=earliest,
        local_window_hours_after_apply=(
            round((now - datetime.fromisoformat(earliest)).total_seconds() / 3600, 2)
            if earliest else None),
        manifests=manifest_stats,
    )
    return report, intervals


def plan_retention(db, manifests, config=None, now=None, bucket="market-raw"):
    """Capture reports and approved identities from one read-only snapshot."""
    owns_transaction = not db.in_transaction
    if owns_transaction:
        db.execute("BEGIN")
    try:
        return _plan_retention(db, list(manifests), config, now, bucket)
    finally:
        if owns_transaction:
            db.rollback()


def _plan_retention(db, manifests, config=None, now=None, bucket="market-raw"):
    """Read-only planning pass; performs no writes."""
    config = config or RetentionConfig()
    now = now or datetime.now(timezone.utc)
    cutoff = retention_cutoff(now, config.hours)
    datasets, intervals, approved = {}, {}, {}
    for dataset in SPECS:
        datasets[dataset], intervals[dataset] = _dataset_plan(
            db, dataset, manifests, cutoff, now, bucket)
        spec = SPECS[dataset]
        columns = "id" if dataset == "observations" else "source,event_id,received_at"
        approved[dataset] = []
        for interval in intervals[dataset]:
            where, params = _eligible_clause(
                db, dataset, spec, interval, cutoff, _protected_id(db, dataset))
            approved[dataset].extend(tuple(row) for row in db.execute(
                f"SELECT {columns} FROM {dataset} WHERE {where}", params))
    return {
        "_approved": approved,
        "_manifests": copy.deepcopy(manifests),
        "_bucket": bucket,
        "mode": "dry-run",
        "cutoff": cutoff,
        "retention_hours": config.hours,
        "datasets": datasets,
        "_intervals": intervals,
        "note": "approx_reclaimable_payload_bytes is row payload only; the SQLite file "
                "does not shrink until a deliberate VACUUM, which retention never runs.",
    }


def public_report(plan):
    return {k: v for k, v in plan.items() if not k.startswith("_")}


class RetentionBudgetError(RetentionError):
    def __init__(self, phase, seconds, committed_rows=0, phase_seconds=None):
        super().__init__("retention writer budget exceeded; subsequent batches stopped")
        self.phase, self.seconds, self.committed_rows = phase, seconds, committed_rows
        self.phase_seconds = phase_seconds or {}


MAX_WRITE_SECONDS = 0.5
TARGET_WRITE_SECONDS = 0.25


@contextmanager
def _measure_phase(timings, name):
    started = time.monotonic()
    try:
        yield
    finally:
        timings[name] = time.monotonic() - started


def apply_retention(db, plan, config, confirm=False):
    """Exact approved deletes with current SQL rechecks and a bounded writer hold.

    Owns its temporary progress handler. External qualification supervisors must
    enforce their overall deadline separately. No network runs in this function.
    """
    if confirm is not True:
        raise RetentionError("apply requires explicit confirmation (--confirm)")
    if not config.enabled:
        raise RetentionError("ENABLE_LOCAL_RETENTION is not true; refusing to delete")
    if db.in_transaction:
        raise RetentionError("apply requires a connection without an active transaction")
    if "_approved" not in plan or "_manifests" not in plan:
        raise RetentionError("plan lacks approved identities and manifest evidence")
    cutoff = canonical_time(plan["cutoff"])
    evidence = _PreparedManifests(plan["_manifests"], plan["_bucket"])
    timestamp_cache = _validated_timestamp_cache(db)
    result = {"mode":"apply", "cutoff":cutoff, "datasets":{}}
    original_cache = db.execute('PRAGMA main.cache_size').fetchone()[0]
    original_temp_cache = db.execute('PRAGMA temp.cache_size').fetchone()[0]
    page_size = db.execute('PRAGMA main.page_size').fetchone()[0]
    cache_bytes = -original_cache*1024 if original_cache<0 else original_cache*page_size
    try:
        # Keep the bounded batch's selected main-index pages resident through
        # DELETE. Connection-local only: never alter collector settings or disk
        # limits. MAIN32MiB + TEMP16MiB targets fit the512MiB worker budget.
        # Larger caller settings are preserved; all exits restore exactly.
        if cache_bytes<32*1024**2:db.execute('PRAGMA main.cache_size=-32768')
        temp_bytes=-original_temp_cache*1024 if original_temp_cache<0 else original_temp_cache*page_size
        if temp_bytes<16*1024**2:db.execute('PRAGMA temp.cache_size=-16384')
        for dataset, spec in SPECS.items():
            approved = {tuple(key) for key in plan["_approved"][dataset]}
            pending = set(approved)
            prepare_started=time.monotonic()
            ranges = _scope_manifest_ranges(dataset, evidence, approved)
            _prepare_pending(db, dataset, approved)
            static_prepare_seconds=time.monotonic()-prepare_started
            deleted = batches = 0
            lock_times = []
            phase_times = []
            observed = {"planned_rows":len(approved), "committed_rows_seen":0,
                        "completed_batches":0, "write_lock_seconds":lock_times,
                        "phase_seconds":phase_times,"static_prepare_seconds":static_prepare_seconds,
                        "unlocked_warm_seconds":[]}
            result["datasets"][dataset] = observed
            while pending:
                if dataset == "stream_events":
                    warm_started=time.monotonic()
                    try:_warm_stream_pages(db,config.batch_size)
                    finally:observed["unlocked_warm_seconds"].append(time.monotonic()-warm_started)
                db.execute("BEGIN IMMEDIATE")
                locked_at = time.monotonic()
                deadline = locked_at + MAX_WRITE_SECONDS
                timings = {}
                db.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
                try:
                    operation = "timestamp_revalidation"
                    with _measure_phase(timings, operation):
                        current = _ValidationSnapshot(db, timestamp_cache, dataset, ranges, phase_timings=timings)
                    operation = "manifest_coverage"
                    with _measure_phase(timings, operation):
                        intervals, _ = _usable_intervals(current, dataset, evidence, plan["_bucket"])
                    operation = "protected_identity_selection"
                    with _measure_phase(timings, operation):
                        protected = _protected_id(db, dataset)
                        selected = current.select(dataset, intervals, cutoff, protected, pending, config.batch_size)
                    if time.monotonic() >= deadline:
                        raise RetentionBudgetError("validation",time.monotonic()-locked_at)
                    if not selected:
                        operation = "commit"
                        with _measure_phase(timings, operation):
                            db.commit()
                        duration = time.monotonic()-locked_at
                        lock_times.append(duration)
                        if duration > MAX_WRITE_SECONDS:
                            raise RetentionBudgetError("empty_commit",duration)
                        break
                    predicate = "id=?" if dataset == "observations" else "source=? AND event_id=? AND received_at=?"
                    before = db.total_changes
                    operation = "exact_delete"
                    with _measure_phase(timings, operation):
                        sql = _stream_delete_sql(db) if dataset == "stream_events" else f"DELETE FROM {dataset} WHERE {predicate}"
                        db.executemany(sql,selected)
                    count = db.total_changes-before
                    if time.monotonic() >= deadline:
                        raise RetentionBudgetError("delete",time.monotonic()-locked_at)
                    operation = "commit"
                    with _measure_phase(timings, operation):
                        db.commit()
                    duration = time.monotonic()-locked_at
                    observed["committed_rows_seen"] += count
                    observed["completed_batches"] += 1
                    lock_times.append(duration)
                    if duration > MAX_WRITE_SECONDS:
                        # This batch committed safely; report it rather than
                        # implying rollback can undo a completed transaction.
                        raise RetentionBudgetError("commit",duration,count)
                except BaseException as error:
                    db.set_progress_handler(None,0)
                    db.rollback()
                    error.retention_failed_operation = operation
                    error.retention_failed_write_seconds = time.monotonic()-locked_at
                    if isinstance(error,sqlite3.OperationalError) and time.monotonic()>=deadline:
                        raise RetentionBudgetError(operation+":sqlite_progress",time.monotonic()-locked_at,phase_seconds=timings) from None
                    if isinstance(error, RetentionBudgetError):
                        error.phase_seconds = timings
                    raise
                finally:
                    phase_times.append(timings)
                    db.set_progress_handler(None,0)
                pending.difference_update(selected)
                # TEMP bookkeeping is outside the main-database writer lock.
                table = "retention_pending_" + dataset
                predicate = "id=?" if dataset == "observations" else "source=? AND event_id=? AND received_at=?"
                db.executemany(f"DELETE FROM temp.{table} WHERE {predicate}",selected)
                db.commit()
                deleted += count
                batches += 1
                if pending:
                    time.sleep(0.1)
            result["datasets"][dataset] = {
                "planned_rows":len(approved), "deleted_rows":deleted,
                "skipped_rows":len(approved)-deleted, "batches":batches,
                "write_lock_seconds":lock_times, "phase_seconds":phase_times,
                "static_prepare_seconds":static_prepare_seconds,
                "unlocked_warm_seconds":observed["unlocked_warm_seconds"],
                "max_write_lock_seconds":max(lock_times,default=0.0)}
        return result
    except BaseException as error:
        # Preserve measured completed work even when the overall supervisor fires.
        # This does not claim that an interrupted commit was rolled back.
        error.retention_progress = result
        raise
    finally:
        db.set_progress_handler(None,0)
        if db.in_transaction:
            db.rollback()
        try:
            for name in ("retention_valid_times","retention_fresh_valid_times","retention_pending_observations","retention_pending_stream_events"):
                db.execute(f"DROP TABLE IF EXISTS temp.{name}")
        finally:
            db.execute(f'PRAGMA main.cache_size={original_cache}')
            db.execute(f'PRAGMA temp.cache_size={original_temp_cache}')


def local_status(db, config, now=None):
    now = now or datetime.now(timezone.utc)
    status = {
        "retention_enabled": config.enabled,
        "retention_hours": config.hours,
        "delete_batch_size": config.batch_size,
        "cutoff": retention_cutoff(now, config.hours),
        "datasets": {},
        "archive_checkpoints_informational": {},
    }
    for dataset, spec in SPECS.items():
        total, oldest, newest = db.execute(
            f"SELECT COUNT(*),MIN({TIME_KEY}),MAX({TIME_KEY}) FROM {spec.table}"
        ).fetchone()
        status["datasets"][dataset] = {
            "total_rows": total, "oldest_row": oldest, "newest_row": newest}
    try:
        for row in db.execute(
            """SELECT dataset,rows_synced,status FROM cloud_sync_state
               WHERE dataset LIKE 'archive:%'"""
        ):
            status["archive_checkpoints_informational"][row[0]] = {
                "rows_synced": row[1], "status": row[2]}
    except sqlite3.OperationalError:
        pass
    return status
