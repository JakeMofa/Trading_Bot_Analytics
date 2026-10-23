"""Phase 1.75.9 verified local retention for raw SQLite evidence.

A raw row is eligible for local deletion only when it is older than the
retention cutoff AND lies inside the source range of a verified raw_archives
manifest (verified_at set after authenticated readback + SHA-256). A sync
checkpoint is never trusted on its own. Only `observations` and
`stream_events` are ever touched. Nothing here runs VACUUM, and live
forecasting never imports or depends on this module.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
import re
import sqlite3


DEFAULT_RETENTION_HOURS = 48
DEFAULT_DELETE_BATCH_SIZE = 5000
MANIFEST_COLUMNS = (
    "source,bucket,object_path,sha256,event_count,compressed_bytes,"
    "first_source_id,last_source_id,started_at,ended_at,verified_at,metadata"
)
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
        "stream_events", "coinbase", "(received_at,source,event_id)", "(?,?,?)"
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
    """Local received_at format: UTC, 6-digit microseconds, +00:00."""
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise RetentionError("timestamps must include a timezone")
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")


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
    return (
        f"{spec.key_sql}>={spec.marker} AND {spec.key_sql}<={spec.marker}",
        (*lo, *hi),
    )


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
        lo = (canonical_time(manifest["started_at"]), *first_key)
        hi = (canonical_time(manifest["ended_at"]), *last_key)
    except (TypeError, ValueError, KeyError):
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
    return db.execute(
        f"""SELECT 1 FROM {table}
            WHERE length(received_at)<>32 OR substr(received_at,-6)<>'+00:00'
            LIMIT 1"""
    ).fetchone() is not None


def _count(db, spec, where, params):
    return db.execute(
        f"SELECT COUNT(*) FROM {spec.table} WHERE {where}", params
    ).fetchone()[0]


def _usable_intervals(db, dataset, manifests, bucket):
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
    where += " AND received_at<?"
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
        where, params = "received_at<?", [cutoff]
        if after is not None:
            where += f" AND {spec.key_sql}>{spec.marker}"
            params += list(after)
        if before is not None:
            where += f" AND {spec.key_sql}<{spec.marker}"
            params += list(before)
        row = db.execute(
            f"SELECT MIN(received_at) FROM {spec.table} WHERE {where}", params
        ).fetchone()[0]
        if row:
            candidates.append(row)
    if protected is not None:
        row = db.execute(
            "SELECT received_at FROM observations WHERE id=?", (protected,)
        ).fetchone()
        if row and row[0] < cutoff:
            candidates.append(row[0])
    if dataset == "observations":
        row = db.execute(
            "SELECT MIN(received_at) FROM observations WHERE NOT ("
            + _unreferenced_observations(db) + ")"
        ).fetchone()[0]
        if row:
            candidates.append(row)
    recent = db.execute(
        f"SELECT MIN(received_at) FROM {spec.table} WHERE received_at>=?", (cutoff,)
    ).fetchone()[0]
    if recent:
        candidates.append(recent)
    return min(candidates) if candidates else None


def _dataset_plan(db, dataset, manifests, cutoff, now, bucket):
    spec = SPECS[dataset]
    total = db.execute(f"SELECT COUNT(*) FROM {spec.table}").fetchone()[0]
    oldest, newest = db.execute(
        f"SELECT MIN(received_at),MAX(received_at) FROM {spec.table}"
    ).fetchone()
    report = {
        "total_rows": total,
        "oldest_row": oldest,
        "newest_row": newest,
        "blocked": None,
    }
    if _bad_time_format(db, spec.table):
        # String comparison against the cutoff is only sound for one canonical format.
        report.update(blocked="non_canonical_received_at", rows_older_than_cutoff=None,
                      eligible_rows=0, uncovered_or_unverified_old_rows=None,
                      protected_sequence_rows=0, rows_remaining_after_apply=total,
                      manifests={"considered": 0, "usable": 0, "rejected": {}})
        return report, []
    old = _count(db, spec, "received_at<?", (cutoff,))
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
            where += " AND received_at<? AND NOT (" + _unreferenced_observations(db) + ")"
            params = (*params, cutoff)
            if protected is not None:
                where += " AND id<?"
                params = (*params, protected)
            referenced_rows += _count(db, spec, where, params)
    protected_rows = 0
    if protected is not None and intervals:
        covered = any(lo[0] <= protected <= hi[0] for lo, hi in intervals)
        old_row = _count(db, spec, "id=? AND received_at<?", (protected, cutoff))
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
    """Read-only planning pass; performs no writes."""
    config = config or RetentionConfig()
    now = now or datetime.now(timezone.utc)
    cutoff = retention_cutoff(now, config.hours)
    datasets, intervals = {}, {}
    for dataset in SPECS:
        datasets[dataset], intervals[dataset] = _dataset_plan(
            db, dataset, manifests, cutoff, now, bucket)
    return {
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


def apply_retention(db, plan, config, confirm=False):
    """Delete eligible rows in bounded batches. Needs config flag AND confirm."""
    if confirm is not True:
        raise RetentionError("apply requires explicit confirmation (--confirm)")
    if not config.enabled:
        raise RetentionError("ENABLE_LOCAL_RETENTION is not true; refusing to delete")
    cutoff = plan["cutoff"]
    result = {"mode": "apply", "cutoff": cutoff, "datasets": {}}
    for dataset, intervals in plan["_intervals"].items():
        spec = SPECS[dataset]
        protected = _protected_id(db, dataset)
        deleted = batches = 0
        for interval in intervals:
            where, params = _eligible_clause(db, dataset, spec, interval, cutoff, protected)
            if dataset == "observations":
                sql = f"""DELETE FROM observations WHERE id IN
                          (SELECT id FROM observations WHERE {where}
                           ORDER BY id LIMIT ?)"""
            else:
                sql = f"""DELETE FROM stream_events WHERE (source,event_id) IN
                          (SELECT source,event_id FROM stream_events WHERE {where}
                           ORDER BY received_at,source,event_id LIMIT ?)"""
            while True:
                cursor = db.execute(sql, (*params, config.batch_size))
                db.commit()
                if cursor.rowcount <= 0:
                    break
                deleted += cursor.rowcount
                batches += 1
        result["datasets"][dataset] = {"deleted_rows": deleted, "batches": batches}
    return result


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
            f"SELECT COUNT(*),MIN(received_at),MAX(received_at) FROM {spec.table}"
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
