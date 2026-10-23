from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import cloud_lifecycle
from cloud_lifecycle import (
    LifecycleConfig,
    LifecycleError,
    LifecycleLockError,
    LifecycleWorker,
    lifecycle_lock,
    read_lifecycle_status,
    safe_error,
)
from retention import RetentionConfig

NOW = datetime.now(timezone.utc)
OLD = NOW - timedelta(days=5)
SECRET = "sb_secret_TOPSECRET"


class FakeCloud:
    def __init__(self, fail_upload=False, fail_verify=False, fail_all=None):
        self.uploads = {}
        self.manifests = []
        self.fail_upload = fail_upload
        self.fail_verify = fail_verify
        self.fail_all = fail_all
        self.closed = False

    def _maybe_fail(self):
        if self.fail_all:
            raise self.fail_all

    def upsert(self, table, rows, on_conflict):
        self._maybe_fail()
        if table == "raw_archives":
            self.manifests.extend(dict(row) for row in rows)
        return len(rows)

    def select(self, table, params, page_size=1000):
        self._maybe_fail()
        return list(self.manifests)

    def upload_bytes(self, bucket, object_path, payload, content_type="application/gzip"):
        self._maybe_fail()
        if self.fail_upload:
            request = httpx.Request("POST", "https://x.supabase.co/?apikey=" + SECRET)
            raise httpx.HTTPStatusError(
                f"boom {SECRET}", request=request, response=httpx.Response(503, request=request))
        self.uploads[(bucket, object_path)] = payload
        return {}

    def verify_object(self, bucket, object_path, expected_sha256, expected_bytes):
        if self.fail_verify:
            raise RuntimeError(f"verification mismatch {SECRET}")
        assert hashlib.sha256(self.uploads[(bucket, object_path)]).hexdigest() == expected_sha256
        return {"verified_at": NOW.isoformat()}

    def close(self):
        self.closed = True


def ts(dt):
    return dt.isoformat(timespec="microseconds")


def make_config(**overrides):
    values = dict(enabled=True, structured_interval=60, raw_archive_interval=3600,
                  retention_interval=3600, raw_batch_size=5, raw_max_batches=2,
                  structured_max_batches=3)
    values.update(overrides)
    return LifecycleConfig(**values)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = str(Path(self.folder.name) / "life.db")
        db = sqlite3.connect(self.path)
        db.executescript(
            """
            CREATE TABLE observations (
              id INTEGER PRIMARY KEY, market_id TEXT NOT NULL, received_at TEXT NOT NULL,
              source_time TEXT, kind TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE stream_events (
              source TEXT NOT NULL, event_id TEXT NOT NULL, received_at TEXT NOT NULL,
              source_time TEXT NOT NULL, price TEXT NOT NULL, size TEXT, side TEXT,
              payload TEXT NOT NULL, PRIMARY KEY(source,event_id));
            CREATE INDEX stream_events_archive_cursor
              ON stream_events(received_at,source,event_id);
            CREATE TABLE predictions (id INTEGER PRIMARY KEY, note TEXT);
            """
        )
        for i in range(1, 8):
            db.execute("INSERT INTO observations VALUES(?,?,?,?,?,?)",
                       (i, "m1", ts(OLD + timedelta(seconds=i)), None, "book", json.dumps({"i": i})))
        db.execute("INSERT INTO observations VALUES(?,?,?,?,?,?)",
                   (8, "m1", ts(NOW), None, "book", "{}"))
        for i in range(3):
            when = OLD + timedelta(seconds=i)
            db.execute("INSERT INTO stream_events VALUES(?,?,?,?,?,?,?,?)",
                       ("cb", f"e{i}", ts(when), ts(when), "100", "1", "buy", "{}"))
        db.execute("INSERT INTO predictions VALUES(1,'keep')")
        db.commit()
        db.close()
        self.cloud = FakeCloud()

    def tearDown(self):
        self.folder.cleanup()

    def worker(self, cloud=None, retention=False, config=None, **kwargs):
        cloud = cloud or self.cloud
        return LifecycleWorker(
            self.path, config or make_config(),
            RetentionConfig(enabled=retention, hours=48, batch_size=2),
            cloud_factory=lambda: cloud, **kwargs)

    def count(self, table):
        db = sqlite3.connect(self.path)
        try:
            return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        finally:
            db.close()

    def run_with_structured(self, worker, side_effect=None, force=True):
        with patch.object(cloud_lifecycle, "sync_structured_once",
                          side_effect=side_effect or [{"markets": 0}]) as sync:
            result = worker.run_cycle(force=force)
        return result, sync

    # config / gating
    def test_disabled_by_default_and_ranges_validated(self):
        self.assertFalse(LifecycleConfig.from_env({}).enabled)
        with self.assertRaises(LifecycleError):
            LifecycleConfig.from_env({}).require_enabled(True)
        with self.assertRaises(LifecycleError):
            make_config().require_enabled(False)
        with self.assertRaises(LifecycleError):
            LifecycleConfig.from_env({"CLOUD_RAW_ARCHIVE_BATCH_SIZE": "0"})
        with self.assertRaises(LifecycleError):
            LifecycleConfig.from_env({"CLOUD_STRUCTURED_SYNC_INTERVAL_SECONDS": "abc"})

    def test_once_cli_refuses_without_enable(self):
        import run_cloud_lifecycle
        with patch.dict("os.environ", {"ENABLE_CLOUD_LIFECYCLE": "false",
                                       "ENABLE_SUPABASE_SYNC": "true"}):
            with self.assertRaises(LifecycleError):
                run_cloud_lifecycle.build_worker(self.path)
        with patch.dict("os.environ", {"ENABLE_CLOUD_LIFECYCLE": "true",
                                       "ENABLE_SUPABASE_SYNC": "false"}):
            with self.assertRaises(LifecycleError):
                run_cloud_lifecycle.build_worker(self.path)

    def test_duplicate_lock_rejected(self):
        with lifecycle_lock(self.path):
            self.assertTrue(cloud_lifecycle.worker_process_running(self.path))
            with self.assertRaises(LifecycleLockError):
                with lifecycle_lock(self.path):
                    pass
        self.assertFalse(cloud_lifecycle.worker_process_running(self.path))

    # stages
    def test_structured_sync_is_independent_and_bounded(self):
        worker = self.worker(config=make_config(raw_archive_interval=86400))
        result, sync = self.run_with_structured(
            worker, side_effect=[{"markets": 5}] * 10, force=False)
        self.assertEqual(sync.call_count, 3)
        self.assertEqual(result["structured"], 15)

    def test_structured_failure_does_not_block_archive(self):
        result, _ = self.run_with_structured(
            self.worker(), side_effect=httpx.ConnectError("down " + SECRET))
        self.assertIn("structured", result["errors"])
        self.assertEqual(result["archive"]["observations"]["archived"], 8)

    def test_observations_and_stream_archive_success(self):
        result, _ = self.run_with_structured(self.worker(config=make_config(raw_max_batches=5)))
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["archive"]["observations"], {"archived": 8, "caught_up": True})
        self.assertEqual(result["archive"]["stream_events"], {"archived": 3, "caught_up": True})
        self.assertTrue(self.cloud.closed)
        status = read_lifecycle_status(self.path)
        self.assertEqual(status["last_observations_archive_rows"], 8)
        self.assertEqual(status["last_stream_events_archive_rows"], 3)
        self.assertEqual(status["last_cycle_status"], "ok")

    def test_bounded_raw_batches_stop_early(self):
        worker = self.worker(config=make_config(raw_batch_size=3, raw_max_batches=2))
        result, _ = self.run_with_structured(worker)
        self.assertEqual(result["archive"]["observations"], {"archived": 6, "caught_up": False})

    # failure handling / retention gating
    def test_archive_failure_skips_retention_and_deletes_nothing(self):
        cloud = FakeCloud(fail_upload=True)
        result, _ = self.run_with_structured(self.worker(cloud, retention=True))
        self.assertEqual(result["retention"]["status"], "skipped_archive_not_verified")
        self.assertEqual(self.count("observations"), 8)
        self.assertEqual(self.count("stream_events"), 3)
        self.assertEqual(result["status"], "degraded")

    def test_storage_verification_failure_skips_retention(self):
        cloud = FakeCloud(fail_verify=True)
        result, _ = self.run_with_structured(self.worker(cloud, retention=True))
        self.assertEqual(result["retention"]["status"], "skipped_archive_not_verified")
        self.assertEqual(self.count("observations"), 8)
        self.assertEqual(self.count("stream_events"), 3)

    def test_retention_disabled_deletes_nothing(self):
        result, _ = self.run_with_structured(
            self.worker(config=make_config(raw_max_batches=5), retention=False))
        self.assertEqual(result["retention"], {"status": "disabled", "deleted": 0})
        self.assertEqual(self.count("observations"), 8)
        self.assertEqual(self.count("stream_events"), 3)

    def test_retention_enabled_deletes_only_verified_eligible_rows(self):
        result, _ = self.run_with_structured(
            self.worker(config=make_config(raw_max_batches=5), retention=True))
        self.assertEqual(result["retention"]["status"], "ok")
        # 7 old observations, 3 old events; the recent row and the newest id stay
        self.assertEqual(result["retention"]["deleted"], 10)
        self.assertEqual(self.count("observations"), 1)
        self.assertEqual(self.count("stream_events"), 0)
        self.assertEqual(self.count("predictions"), 1)

    def test_partial_archive_only_deletes_covered_rows(self):
        worker = self.worker(config=make_config(raw_batch_size=3, raw_max_batches=1),
                             retention=True)
        result, _ = self.run_with_structured(worker)
        self.assertLessEqual(self.count("observations"), 8)
        self.assertGreaterEqual(self.count("observations"), 5)

    def test_cloud_exception_survives_reports_and_leaks_no_secret(self):
        cloud = FakeCloud(fail_all=httpx.ConnectError(f"cannot reach {SECRET}"))
        result, _ = self.run_with_structured(self.worker(cloud, retention=True))
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(self.count("observations"), 8)
        status = read_lifecycle_status(self.path)
        self.assertEqual(status["last_error_type"], "ConnectError")
        self.assertNotIn(SECRET, json.dumps(status))
        raw = sqlite3.connect(self.path).execute(
            "SELECT * FROM cloud_lifecycle_state").fetchall()
        self.assertNotIn(SECRET, json.dumps(raw))

    def test_cloud_factory_failure_is_recorded(self):
        def factory():
            raise RuntimeError("SUPABASE_URL missing " + SECRET)
        worker = LifecycleWorker(self.path, make_config(), RetentionConfig(False, 48, 2),
                                 cloud_factory=factory)
        result = worker.run_cycle(force=True)
        self.assertEqual(result["errors"], ["cloud_client"])
        self.assertNotIn(SECRET, json.dumps(read_lifecycle_status(self.path)))

    def test_worker_continues_next_cycle_after_failure(self):
        cloud = FakeCloud(fail_all=httpx.ConnectError("down"))
        worker = self.worker(cloud, config=make_config(raw_max_batches=5))
        first, _ = self.run_with_structured(worker)
        self.assertEqual(first["status"], "degraded")
        cloud.fail_all = None
        second, _ = self.run_with_structured(worker)
        self.assertEqual(second["status"], "ok")
        self.assertEqual(second["archive"]["observations"]["archived"], 8)

    def test_stages_follow_independent_cadences(self):
        clock = [1000.0]
        worker = self.worker(monotonic=lambda: clock[0],
                             config=make_config(raw_max_batches=5))
        self.run_with_structured(worker, force=False)
        clock[0] += 61
        _, sync = self.run_with_structured(worker, force=False)
        self.assertEqual(sync.call_count, 1)
        result, _ = self.run_with_structured(worker, force=False)
        self.assertEqual(result["archive"], {})

    def test_run_forever_marks_stopped(self):
        stop = threading.Event()
        worker = self.worker(config=make_config(raw_max_batches=5))

        def on_cycle(_):
            stop.set()

        with patch.object(cloud_lifecycle, "sync_structured_once", return_value={"markets": 0}):
            worker.run_forever(stop, on_cycle=on_cycle)
        status = read_lifecycle_status(self.path)
        self.assertEqual(status["status"], "stopped")

    # status
    def test_status_is_local_and_flags_stale_worker(self):
        self.assertEqual(read_lifecycle_status(self.path)["status"], "disabled")
        db = sqlite3.connect(self.path)
        cloud_lifecycle.initialize_lifecycle_state(db)
        db.execute("UPDATE cloud_lifecycle_state SET worker_status='running'")
        db.commit()
        db.close()
        status = read_lifecycle_status(self.path)
        self.assertEqual(status["status"], "stale")
        self.assertFalse(status["process_running"])
        self.assertEqual(read_lifecycle_status(str(Path(self.folder.name) / "none.db"))["status"],
                         "no_local_database")

    def test_safe_error_never_includes_message(self):
        kind, detail = safe_error(RuntimeError(SECRET))
        self.assertNotIn(SECRET, f"{kind}{detail}")
        request = httpx.Request("GET", "https://x")
        kind, detail = safe_error(httpx.HTTPStatusError(
            SECRET, request=request, response=httpx.Response(401, request=request)))
        self.assertEqual(detail, "http_401")


if __name__ == "__main__":
    unittest.main()
