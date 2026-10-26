"""Phase 1.75.9 verified local retention for raw SQLite evidence.

A raw row is eligible for local deletion only when it is older than the
retention cutoff AND lies inside the source range of a verified raw_archives
manifest (verified_at set after authenticated readback + SHA-256). A sync
checkpoint is never trusted on its own. Only `observations` and
`stream_events` are ever touched. Nothing here runs VACUUM, and live
forecasting never imports or depends on this module.
"""
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import copy
import json
import os
import re
import sqlite3
import time


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


def _validated_timestamp_cache(db):
    # Validity is a pure fact about the exact string, not about a row or snapshot.
    # This read is outside the write lock. Changed/new strings are checked again
    # from the fresh transaction snapshot; malformed values always fail closed.
    cache = set()
    for table in SPECS:
        for (value,) in db.execute(f"SELECT received_at FROM {table}"):
            if value not in cache:
                canonical_time(value)
                cache.add(value)
    return cache


class _ValidationSnapshot:
    """Fresh minimal local state, created only under the current writer lock."""
    def __init__(self, db, timestamp_cache):
        self.db = db
        self.records, self.keys = {}, {}
        for dataset in SPECS:
            columns = "id,received_at" if dataset == "observations" else "source,event_id,received_at"
            records = []
            for row in db.execute(f"SELECT {columns} FROM {dataset}"):
                value = row[-1]
                if value not in timestamp_cache:
                    canonical_time(value)
                    timestamp_cache.add(value)
                stamp = value[:19] + ".000000+00:00" if len(value) == 25 else value
                if dataset == "observations":
                    key = (row[0],)
                else:
                    key = (stamp, row[0], row[1])
                records.append((key, value))
            records.sort(key=lambda item: item[0])
            self.records[dataset] = records
            self.keys[dataset] = [item[0] for item in records]

    def __getattr__(self, name):
        return getattr(self.db, name)

    def select(self, dataset, intervals, cutoff, protected, pending, limit):
        references = set()
        if dataset == "observations" and self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='prediction_context_links'"
        ).fetchone():
            references = {r[0] for r in self.db.execute(
                "SELECT outcome_observation_id FROM prediction_context_links "
                "WHERE outcome_observation_id IS NOT NULL")}
        keys, records = self.keys[dataset], self.records[dataset]
        for lo, hi in intervals:
            selected = []
            for i in range(bisect_left(keys, lo), bisect_right(keys, hi)):
                key, value = records[i]
                stamp = value[:19] + ".000000+00:00" if len(value) == 25 else value
                identity = (key[0],) if dataset == "observations" else (key[1], key[2], value)
                if stamp >= cutoff or identity not in pending:
                    continue
                if dataset == "observations" and (
                        (protected is not None and key[0] >= protected) or key[0] in references):
                    continue
                selected.append(identity)
                if len(selected) == limit:
                    break
            # Keep the existing per-interval bounded-batch contract.
            if selected:
                return selected
        return []


def _usable_intervals(db, dataset, manifests, bucket):
    if isinstance(db, _ValidationSnapshot) and isinstance(manifests, _PreparedManifests):
        if manifests.bucket != bucket:
            raise RetentionError("prepared manifest bucket changed")
        valid, original_rejected, considered = manifests.parsed[dataset]
        rejected, intervals = dict(original_rejected), []
        keys = db.keys[dataset]
        for lo, hi, event_count in valid:
            # Count ALL current local identities in each original range, including
            # late rows outside approved scope. A late row can invalidate coverage.
            if bisect_right(keys, hi) - bisect_left(keys, lo) > event_count:
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


def apply_retention(db, plan, config, confirm=False):
    """Delete eligible rows in bounded batches. Needs config flag AND confirm."""
    if confirm is not True:
        raise RetentionError("apply requires explicit confirmation (--confirm)")
    if not config.enabled:
        raise RetentionError("ENABLE_LOCAL_RETENTION is not true; refusing to delete")
    # Never commit a caller's pending writes or inherit a deferred read snapshot.
    if db.in_transaction:
        raise RetentionError("apply requires a connection without an active transaction")
    if "_approved" not in plan or "_manifests" not in plan:
        raise RetentionError("plan lacks approved identities and manifest evidence")
    cutoff = canonical_time(plan["cutoff"])
    evidence = _PreparedManifests(plan["_manifests"], plan["_bucket"])
    timestamp_cache = _validated_timestamp_cache(db)
    result = {"mode": "apply", "cutoff": cutoff, "datasets": {}}
    for dataset, spec in SPECS.items():
        approved = {tuple(key) for key in plan["_approved"][dataset]}
        pending = set(approved)
        deleted = batches = 0
        while pending:
            # All cloud IO precedes apply. Each local recheck and bounded DELETE
            # shares a reserved writer lock; collection can resume after COMMIT.
            db.execute("BEGIN IMMEDIATE")
            try:
                current = _ValidationSnapshot(db, timestamp_cache)
                intervals, _ = _usable_intervals(
                    current, dataset, evidence, plan["_bucket"])
                protected = _protected_id(db, dataset)
                selected = current.select(
                    dataset, intervals, cutoff, protected, pending, config.batch_size)
                if not selected:
                    db.commit()
                    break
                # Exact reviewed identities only, never a broad range predicate.
                predicate = "id=?" if dataset == "observations" else "source=? AND event_id=? AND received_at=?"
                before = db.total_changes
                db.executemany(f"DELETE FROM {dataset} WHERE {predicate}", selected)
                count = db.total_changes - before
                db.commit()
            except BaseException:
                db.rollback()
                raise
            # Release full snapshots outside the writer lock before the next batch.
            current = None
            pending.difference_update(selected)
            deleted += count
            batches += 1
            if pending:
                # Give SQLite busy-handler waiters an unlocked handoff window.
                # This is outside the transaction; every next batch revalidates.
                time.sleep(0.1)
        result["datasets"][dataset] = {
            "planned_rows": len(approved), "deleted_rows": deleted,
            "skipped_rows": len(approved) - deleted, "batches": batches}
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
