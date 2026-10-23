"""Phase 1.75 cloud lifecycle worker (background path only).

Runs as its own process, never inside the collector, forecast or FastAPI
request path. Each cycle can: copy structured history to Supabase Postgres,
archive raw evidence to verified private Storage objects, and (only when
ENABLE_LOCAL_RETENTION=true) apply the verified retention from retention.py.

Safety rules enforced here:
  * a Supabase failure never stops or slows the collector and never deletes data;
  * retention is skipped for any cycle whose raw archive step did not succeed;
  * telemetry stores only exception type names and HTTP status codes, never
    exception text that could carry headers or credentials;
  * nothing here runs VACUUM.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import time
from datetime import datetime, timezone

import httpx

from cloud_memory import (
    DEFAULT_BATCH_SIZE,
    RAW_BUCKET,
    archive_raw_batch,
    initialize_local_sync,
    sync_structured_once,
)
from retention import (
    RetentionConfig,
    RetentionError,
    apply_retention,
    fetch_verified_manifests,
    plan_retention,
)


RAW_DATASETS = ("observations", "stream_events")
BUSY_TIMEOUT_MS = 30000


class LifecycleError(RuntimeError):
    pass


class LifecycleLockError(LifecycleError):
    pass


def _enabled(value):
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _bounded(name, raw, low, high):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise LifecycleError(f"{name} must be an integer") from None
    if not low <= value <= high:
        raise LifecycleError(f"{name} must be {low}..{high}")
    return value


@dataclass(frozen=True)
class LifecycleConfig:
    enabled: bool = False
    structured_interval: int = 60
    raw_archive_interval: int = 3600
    retention_interval: int = 3600
    raw_batch_size: int = 5000
    raw_max_batches: int = 24
    structured_max_batches: int = 20

    @classmethod
    def from_env(cls, environ=None):
        env = os.environ if environ is None else environ
        get = env.get
        return cls(
            enabled=_enabled(get("ENABLE_CLOUD_LIFECYCLE", "false")),
            structured_interval=_bounded(
                "CLOUD_STRUCTURED_SYNC_INTERVAL_SECONDS",
                get("CLOUD_STRUCTURED_SYNC_INTERVAL_SECONDS", "60"), 15, 86400),
            raw_archive_interval=_bounded(
                "CLOUD_RAW_ARCHIVE_INTERVAL_SECONDS",
                get("CLOUD_RAW_ARCHIVE_INTERVAL_SECONDS", "3600"), 60, 86400),
            retention_interval=_bounded(
                "CLOUD_RETENTION_INTERVAL_SECONDS",
                get("CLOUD_RETENTION_INTERVAL_SECONDS", "3600"), 60, 86400),
            raw_batch_size=_bounded(
                "CLOUD_RAW_ARCHIVE_BATCH_SIZE",
                get("CLOUD_RAW_ARCHIVE_BATCH_SIZE", "5000"), 1, 50000),
            raw_max_batches=_bounded(
                "CLOUD_RAW_ARCHIVE_MAX_BATCHES",
                get("CLOUD_RAW_ARCHIVE_MAX_BATCHES", "24"), 1, 10000),
            structured_max_batches=_bounded(
                "CLOUD_STRUCTURED_MAX_BATCHES",
                get("CLOUD_STRUCTURED_MAX_BATCHES", "20"), 1, 1000),
        )

    def require_enabled(self, supabase_sync_enabled):
        if not self.enabled:
            raise LifecycleError(
                "Cloud lifecycle is disabled; set ENABLE_CLOUD_LIFECYCLE=true explicitly")
        if not supabase_sync_enabled:
            raise LifecycleError(
                "Supabase sync is disabled; set ENABLE_SUPABASE_SYNC=true explicitly")


def _now():
    return datetime.now(timezone.utc).isoformat()


# --- process lock -----------------------------------------------------------

def lock_path_for(database):
    return Path(f"{Path(database).resolve()}.lifecycle.lock")


@contextmanager
def lifecycle_lock(database):
    """Exclusive per-database lock; a second worker fails instead of waiting."""
    path = lock_path_for(database)
    with path.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LifecycleLockError(
                "A cloud lifecycle worker already owns this database") from None
        lock.seek(0)
        lock.truncate()
        lock.write(json.dumps({"pid": os.getpid(), "database": str(Path(database).resolve())}))
        lock.flush()
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def worker_process_running(database):
    """Probe the lock without creating it; True only if another process holds it."""
    path = lock_path_for(database)
    if not path.exists():
        return False
    with path.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(lock, fcntl.LOCK_UN)
    return False


# --- telemetry --------------------------------------------------------------

STATE_COLUMNS = (
    "worker_status", "worker_pid", "started_at",
    "last_cycle_started_at", "last_cycle_finished_at", "last_cycle_status",
    "last_structured_success_at", "last_structured_rows",
    "last_observations_archive_at", "last_observations_archive_rows",
    "observations_archive_caught_up",
    "last_stream_events_archive_at", "last_stream_events_archive_rows",
    "stream_events_archive_caught_up",
    "last_retention_at", "last_retention_status", "last_retention_deleted",
    "last_error_stage", "last_error_type", "last_error_detail", "last_error_at",
)

LIFECYCLE_STATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS cloud_lifecycle_state (
  id INTEGER PRIMARY KEY CHECK(id=1),
  worker_status TEXT NOT NULL DEFAULT 'idle',
  worker_pid INTEGER,
  started_at TEXT,
  last_cycle_started_at TEXT,
  last_cycle_finished_at TEXT,
  last_cycle_status TEXT,
  last_structured_success_at TEXT,
  last_structured_rows INTEGER,
  last_observations_archive_at TEXT,
  last_observations_archive_rows INTEGER,
  observations_archive_caught_up INTEGER,
  last_stream_events_archive_at TEXT,
  last_stream_events_archive_rows INTEGER,
  stream_events_archive_caught_up INTEGER,
  last_retention_at TEXT,
  last_retention_status TEXT,
  last_retention_deleted INTEGER,
  last_error_stage TEXT,
  last_error_type TEXT,
  last_error_detail TEXT,
  last_error_at TEXT,
  updated_at TEXT NOT NULL
);
"""


def initialize_lifecycle_state(db):
    db.execute(LIFECYCLE_STATE_SCHEMA)
    db.execute(
        "INSERT OR IGNORE INTO cloud_lifecycle_state(id,updated_at) VALUES(1,?)", (_now(),))
    db.commit()


def safe_error(exc):
    """Return (type_name, detail) without ever including exception text."""
    detail = None
    if isinstance(exc, httpx.HTTPStatusError):
        detail = f"http_{exc.response.status_code}"
    elif isinstance(exc, httpx.TimeoutException):
        detail = "timeout"
    elif isinstance(exc, httpx.RequestError):
        detail = "network"
    elif isinstance(exc, sqlite3.OperationalError):
        detail = "sqlite_operational"
    return type(exc).__name__, detail


def open_lifecycle_db(path):
    """Short-transaction connection that waits briefly for the collector's writes."""
    db = sqlite3.connect(str(path), timeout=BUSY_TIMEOUT_MS / 1000)
    db.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    return db


def read_lifecycle_status(db_path):
    """Read-only, local-only status. Never touches Supabase."""
    base = {"enabled": _enabled(os.getenv("ENABLE_CLOUD_LIFECYCLE", "false"))}
    if db_path != ":memory:" and not Path(db_path).exists():
        return {**base, "status": "no_local_database", "process_running": False}
    running = db_path != ":memory:" and worker_process_running(db_path)
    uri = f"file:{Path(db_path).resolve()}?mode=ro" if db_path != ":memory:" else db_path
    db = sqlite3.connect(uri, uri=db_path != ":memory:")
    try:
        db.execute("PRAGMA query_only=ON")
        exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='cloud_lifecycle_state'"
        ).fetchone()
        row = db.execute("SELECT * FROM cloud_lifecycle_state WHERE id=1").fetchone() if exists else None
        if row is None:
            return {**base, "status": "not_started" if base["enabled"] else "disabled",
                    "process_running": running}
        names = [item[0] for item in db.execute("SELECT * FROM cloud_lifecycle_state").description]
        state = dict(zip(names, row))
    finally:
        db.close()
    stored = state["worker_status"]
    if stored in ("running", "degraded") and not running:
        status = "stale"
    else:
        status = stored
    result = {**base, "status": status, "process_running": running}
    for column in STATE_COLUMNS:
        if column in state and column != "worker_status":
            result[column] = state[column]
    result["updated_at"] = state["updated_at"]
    return result


# --- worker -----------------------------------------------------------------

class LifecycleWorker:
    def __init__(self, db_path, config, retention, cloud_factory,
                 bucket=RAW_BUCKET, structured_batch_size=DEFAULT_BATCH_SIZE,
                 now_fn=None, monotonic=None, should_stop=None):
        self.db_path = str(db_path)
        self.config = config
        self.retention = retention
        self.cloud_factory = cloud_factory
        self.bucket = bucket
        self.structured_batch_size = structured_batch_size
        self.now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic or time.monotonic
        self.should_stop = should_stop or (lambda: False)
        self.last_archive_ok = None
        self.continuous = False
        self._next_due = {"structured": 0.0, "archive": 0.0, "retention": 0.0}

    # telemetry writes are best effort: a locked state table must not break a cycle
    def _record(self, db, **fields):
        unknown = set(fields) - set(STATE_COLUMNS)
        if unknown:
            raise ValueError(f"unknown lifecycle state columns: {sorted(unknown)}")
        fields["updated_at"] = _now()
        assignments = ",".join(f"{name}=?" for name in fields)
        try:
            db.execute(
                f"UPDATE cloud_lifecycle_state SET {assignments} WHERE id=1",
                tuple(fields.values()))
            db.commit()
        except sqlite3.Error as exc:
            print(f"lifecycle telemetry write failed: {type(exc).__name__}", flush=True)

    def _fail(self, db, stage, exc):
        kind, detail = safe_error(exc)
        print(f"lifecycle {stage} failed: {kind}" + (f" ({detail})" if detail else ""),
              flush=True)
        self._record(db, last_error_stage=stage, last_error_type=kind,
                     last_error_detail=detail, last_error_at=_now())

    def _structured(self, db, cloud):
        total = 0
        for _ in range(self.config.structured_max_batches):
            if self.should_stop():
                break
            batch = sync_structured_once(db, cloud, self.structured_batch_size)
            moved = sum(batch.values())
            total += moved
            if not moved:
                break
        return total

    def _archive_dataset(self, db, cloud, dataset):
        archived, caught_up = 0, False
        for _ in range(self.config.raw_max_batches):
            if self.should_stop():
                return archived, False
            manifest = archive_raw_batch(
                db, cloud, dataset, limit=self.config.raw_batch_size, bucket=self.bucket)
            if manifest is None:
                caught_up = True
                break
            archived += manifest["event_count"]
            if manifest["event_count"] < self.config.raw_batch_size:
                caught_up = True
                break
        return archived, caught_up

    def _retention(self, db, cloud):
        manifests = fetch_verified_manifests(cloud, self.bucket)
        plan = plan_retention(db, manifests, self.retention, self.now_fn(), self.bucket)
        result = apply_retention(db, plan, self.retention, confirm=True)
        return sum(item["deleted_rows"] for item in result["datasets"].values())

    def run_cycle(self, force=False):
        """Run every due stage once. Returns a sanitized result dict."""
        db = open_lifecycle_db(self.db_path)
        result = {"structured": None, "archive": {}, "retention": None, "errors": []}
        try:
            initialize_local_sync(db)
            initialize_lifecycle_state(db)
            started = _now()
            self._record(db, last_cycle_started_at=started, worker_pid=os.getpid())
            now = self.monotonic()
            run_structured = force or now >= self._next_due["structured"]
            run_archive = force or now >= self._next_due["archive"]
            run_retention = force or now >= self._next_due["retention"]
            cloud = None
            try:
                cloud = self.cloud_factory()
                if run_structured:
                    self._next_due["structured"] = now + self.config.structured_interval
                    try:
                        moved = self._structured(db, cloud)
                        result["structured"] = moved
                        self._record(db, last_structured_success_at=_now(),
                                     last_structured_rows=moved)
                    except Exception as exc:
                        result["errors"].append("structured")
                        self._fail(db, "structured", exc)
                if run_archive:
                    self._next_due["archive"] = now + self.config.raw_archive_interval
                    self.last_archive_ok = True
                    for dataset in RAW_DATASETS:
                        try:
                            archived, caught_up = self._archive_dataset(db, cloud, dataset)
                            result["archive"][dataset] = {
                                "archived": archived, "caught_up": caught_up}
                            self._record(db, **{
                                f"last_{dataset}_archive_at": _now(),
                                f"last_{dataset}_archive_rows": archived,
                                f"{dataset}_archive_caught_up": int(caught_up)})
                        except Exception as exc:
                            self.last_archive_ok = False
                            result["errors"].append(f"archive:{dataset}")
                            self._fail(db, f"archive_{dataset}", exc)
                if run_retention:
                    self._next_due["retention"] = now + self.config.retention_interval
                    result["retention"] = self._run_retention_stage(db, cloud, result)
            except Exception as exc:
                result["errors"].append("cloud_client")
                self.last_archive_ok = False
                self._fail(db, "cloud_client", exc)
            finally:
                close = getattr(cloud, "close", None)
                if close:
                    close()
            status = "degraded" if result["errors"] else "ok"
            self._record(db, last_cycle_finished_at=_now(), last_cycle_status=status,
                         worker_status="degraded" if result["errors"] else (
                             "running" if self.continuous else "idle"))
            result["status"] = status
            return result
        finally:
            db.close()

    def _run_retention_stage(self, db, cloud, result):
        if not self.retention.enabled:
            self._record(db, last_retention_status="disabled")
            return {"status": "disabled", "deleted": 0}
        if self.should_stop():
            return {"status": "skipped_stopping", "deleted": 0}
        if self.last_archive_ok is not True:
            self._record(db, last_retention_status="skipped_archive_not_verified")
            return {"status": "skipped_archive_not_verified", "deleted": 0}
        try:
            deleted = self._retention(db, cloud)
        except (RetentionError, Exception) as exc:
            result["errors"].append("retention")
            self._fail(db, "retention", exc)
            self._record(db, last_retention_status="error")
            return {"status": "error", "deleted": 0}
        self._record(db, last_retention_at=_now(), last_retention_status="ok",
                     last_retention_deleted=deleted)
        return {"status": "ok", "deleted": deleted}

    def run_forever(self, stop, poll_seconds=1.0, on_cycle=None):
        """Loop until `stop` (threading.Event) is set; each stage keeps its own cadence."""
        self.continuous = True
        db = open_lifecycle_db(self.db_path)
        try:
            initialize_lifecycle_state(db)
            self._record(db, worker_status="running", worker_pid=os.getpid(),
                         started_at=_now())
        finally:
            db.close()
        try:
            while not stop.is_set():
                try:
                    outcome = self.run_cycle()
                    if on_cycle:
                        on_cycle(outcome)
                except Exception as exc:
                    kind, _ = safe_error(exc)
                    print(f"lifecycle cycle failed: {kind}", flush=True)
                waits = [value - self.monotonic() for value in self._next_due.values()]
                stop.wait(max(poll_seconds, min(min(waits), 30.0)))
        finally:
            db = open_lifecycle_db(self.db_path)
            try:
                initialize_lifecycle_state(db)
                self._record(db, worker_status="stopped", worker_pid=None)
            finally:
                db.close()
