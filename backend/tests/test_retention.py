from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from unittest.mock import patch
import unittest

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import retention

from cloud_memory import (
    CloudConfig,
    SupabaseHTTP,
    archive_raw_batch,
    initialize_local_sync,
)
from retention import (
    RetentionConfig,
    RetentionError,
    apply_retention,
    canonical_time,
    fetch_verified_manifests,
    local_status,
    plan_retention,
    public_report,
)

NOW = datetime(2026, 10, 22, 12, 0, 0, tzinfo=timezone.utc)
CUTOFF_DT = NOW - timedelta(hours=48)
STRUCTURED = ("markets", "feature_snapshots", "predictions", "news_events", "candles")


class FakeCloud:
    def __init__(self):
        self.uploads = {}
        self.manifests = []

    def upsert(self, table, rows, on_conflict):
        if table == "raw_archives":
            self.manifests.extend(dict(row) for row in rows)
        return len(rows)

    def upload_bytes(self, bucket, object_path, payload, content_type="application/gzip"):
        self.uploads[(bucket, object_path)] = payload
        return {}

    def verify_object(self, bucket, object_path, expected_sha256, expected_bytes):
        payload = self.uploads[(bucket, object_path)]
        assert hashlib.sha256(payload).hexdigest() == expected_sha256
        return {"verified_at": "2026-10-22T12:30:00+00:00"}


def ts(dt):
    return dt.isoformat(timespec="microseconds")


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript(
            """
            CREATE TABLE markets (id TEXT PRIMARY KEY, note TEXT);
            CREATE TABLE feature_snapshots (id INTEGER PRIMARY KEY, note TEXT);
            CREATE TABLE predictions (id INTEGER PRIMARY KEY, note TEXT);
            CREATE TABLE news_events (id INTEGER PRIMARY KEY, note TEXT);
            CREATE TABLE candles (time INTEGER, note TEXT);
            CREATE TABLE observations (
              id INTEGER PRIMARY KEY, market_id TEXT NOT NULL, received_at TEXT NOT NULL,
              source_time TEXT, kind TEXT NOT NULL, payload TEXT NOT NULL
            );
            CREATE TABLE stream_events (
              source TEXT NOT NULL, event_id TEXT NOT NULL, received_at TEXT NOT NULL,
              source_time TEXT NOT NULL, price TEXT NOT NULL, size TEXT, side TEXT,
              payload TEXT NOT NULL, PRIMARY KEY(source,event_id)
            );
            CREATE INDEX stream_events_archive_cursor
              ON stream_events(received_at,source,event_id);
            """
        )
        for table in STRUCTURED:
            self.db.execute(f"INSERT INTO {table} VALUES (?,?)", (1, "keep"))
        initialize_local_sync(self.db)
        self.cloud = FakeCloud()
        self.config = RetentionConfig(enabled=True, hours=48, batch_size=5000)

    def tearDown(self):
        self.db.close()

    # observations ids 1..20 are 3+ days old; ids 21..30 are 1 hour old.
    def seed_observations(self):
        for i in range(1, 31):
            when = (CUTOFF_DT - timedelta(days=1) + timedelta(seconds=i)
                    if i <= 20 else NOW - timedelta(hours=1) + timedelta(seconds=i))
            self.db.execute(
                "INSERT INTO observations VALUES(?,?,?,?,?,?)",
                (i, "m1", ts(when), None, "book", json.dumps({"i": i})))
        self.db.commit()

    def add_event(self, source, event_id, when):
        self.db.execute(
            "INSERT INTO stream_events VALUES(?,?,?,?,?,?,?,?)",
            (source, event_id, ts(when), ts(when), "100", "1", "buy", json.dumps({})))
        self.db.commit()

    def archive_all(self, dataset, limit):
        while archive_raw_batch(self.db, self.cloud, dataset, limit=limit):
            pass

    def plan(self, now=NOW, manifests=None):
        manifests = self.cloud.manifests if manifests is None else manifests
        return plan_retention(self.db, manifests, self.config, now)

    def count(self, table):
        return self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def structured_counts(self):
        return {t: self.count(t) for t in STRUCTURED}

    def test_retention_disabled_and_validated_by_default(self):
        self.assertFalse(RetentionConfig().enabled)
        self.assertEqual(RetentionConfig().hours, 48)
        self.assertFalse(RetentionConfig.build("false", "48", "5000").enabled)
        for hours in ("0", "-1", "abc", "99999999"):
            with self.assertRaises(RetentionError):
                RetentionConfig.build("true", hours, "5000")
        for batch in ("0", "50001", "x"):
            with self.assertRaises(RetentionError):
                RetentionConfig.build("true", "48", batch)

    def test_verified_old_observations_are_eligible_and_new_are_kept(self):
        self.seed_observations()
        self.archive_all("observations", 10)
        report = self.plan()["datasets"]["observations"]
        self.assertEqual(report["total_rows"], 30)
        self.assertEqual(report["rows_older_than_cutoff"], 20)
        self.assertEqual(report["eligible_rows"], 20)
        self.assertEqual(report["uncovered_or_unverified_old_rows"], 0)
        self.assertEqual(report["rows_remaining_after_apply"], 10)
        self.assertGreater(report["approx_reclaimable_payload_bytes"], 0)
        self.assertEqual(report["manifests"]["usable"], 3)

    def test_unverified_or_untrusted_manifests_never_make_rows_eligible(self):
        self.seed_observations()
        self.archive_all("observations", 10)
        cases = {
            "unverified": lambda m: m.update(verified_at=None),
            "no_readback_verification": lambda m: m["metadata"].update(verification="none"),
            "bad_checksum": lambda m: m.update(sha256="abc"),
            "wrong_bucket": lambda m: m.update(bucket="other"),
            "missing_source_ids": lambda m: m.update(first_source_id=None),
            "bad_event_count": lambda m: m.update(event_count=0),
        }
        for reason, mutate in cases.items():
            manifests = []
            for manifest in self.cloud.manifests:
                copy = json.loads(json.dumps(manifest))
                mutate(copy)
                manifests.append(copy)
            report = self.plan(manifests=manifests)["datasets"]["observations"]
            self.assertEqual(report["eligible_rows"], 0, reason)
            self.assertEqual(report["uncovered_or_unverified_old_rows"], 20, reason)
            self.assertEqual(report["manifests"]["rejected"], {reason: 3}, reason)

    def test_sync_checkpoint_alone_is_not_proof(self):
        self.seed_observations()
        self.archive_all("observations", 10)
        report = self.plan(manifests=[])["datasets"]["observations"]
        checkpoint = self.db.execute(
            "SELECT rows_synced,status FROM cloud_sync_state WHERE dataset='archive:observations'"
        ).fetchone()
        self.assertEqual(checkpoint, (30, "verified"))
        self.assertEqual(report["eligible_rows"], 0)

    def test_partial_archive_only_makes_covered_ids_eligible(self):
        self.seed_observations()
        archive_raw_batch(self.db, self.cloud, "observations", limit=10)
        report = self.plan()["datasets"]["observations"]
        self.assertEqual(report["eligible_rows"], 10)
        self.assertEqual(report["uncovered_or_unverified_old_rows"], 10)
        apply_retention(self.db, self.plan(), self.config, confirm=True)
        ids = [r[0] for r in self.db.execute("SELECT id FROM observations ORDER BY id")]
        self.assertEqual(ids, list(range(11, 31)))

    def test_manifest_straddling_cutoff_only_deletes_old_rows(self):
        self.seed_observations()
        archive_raw_batch(self.db, self.cloud, "observations", limit=25)
        apply_retention(self.db, self.plan(), self.config, confirm=True)
        ids = [r[0] for r in self.db.execute("SELECT id FROM observations ORDER BY id")]
        self.assertEqual(ids, list(range(21, 31)))

    def test_rows_exceeding_manifest_count_untrust_the_range(self):
        self.seed_observations()
        archive_raw_batch(self.db, self.cloud, "observations", limit=10)
        self.cloud.manifests[0]["event_count"] = 5
        report = self.plan()["datasets"]["observations"]
        self.assertEqual(report["eligible_rows"], 0)
        self.assertEqual(report["manifests"]["rejected"], {"local_rows_exceed_manifest": 1})

    def test_newest_observation_id_is_kept_as_sequence_anchor(self):
        self.seed_observations()
        self.archive_all("observations", 10)
        later = NOW + timedelta(days=10)
        report = self.plan(now=later)["datasets"]["observations"]
        self.assertEqual(report["eligible_rows"], 29)
        self.assertEqual(report["protected_sequence_rows"], 1)
        self.assertEqual(report["uncovered_or_unverified_old_rows"], 0)
        apply_retention(self.db, self.plan(now=later), self.config, confirm=True)
        self.assertEqual(
            [r[0] for r in self.db.execute("SELECT id FROM observations")], [30])

    def test_stream_cursor_boundary_and_duplicate_received_at(self):
        same = CUTOFF_DT - timedelta(days=1)
        for event_id in ("e1", "e2", "e3"):
            self.add_event("coinbase", event_id, same)
        for event_id in ("e4", "e5", "e6"):
            self.add_event("coinbase", event_id, same)
        self.add_event("coinbase", "at-cutoff", CUTOFF_DT)
        self.add_event("coinbase", "recent", NOW - timedelta(hours=1))
        archive_raw_batch(self.db, self.cloud, "stream_events", limit=4)
        report = self.plan()["datasets"]["stream_events"]
        self.assertEqual(report["rows_older_than_cutoff"], 6)
        self.assertEqual(report["eligible_rows"], 4)
        self.assertEqual(report["uncovered_or_unverified_old_rows"], 2)
        apply_retention(self.db, self.plan(), self.config, confirm=True)
        remaining = [r[0] for r in self.db.execute(
            "SELECT event_id FROM stream_events ORDER BY received_at,source,event_id")]
        self.assertEqual(remaining, ["e5", "e6", "at-cutoff", "recent"])

    def test_retention_preserves_observations_linked_to_predictions(self):
        self.seed_observations()
        self.archive_all("observations", 10)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("""CREATE TABLE prediction_context_links (
            id INTEGER PRIMARY KEY,
            outcome_observation_id INTEGER REFERENCES observations(id))""")
        self.db.executemany("INSERT INTO prediction_context_links VALUES (?,?)",
                            [(1, 2), (2, 2), (3, 15), (4, None)])
        self.db.commit()
        plan = self.plan()
        report = plan["datasets"]["observations"]
        self.assertEqual(report["eligible_rows"], 18)
        self.assertEqual(report["protected_reference_rows"], 2)
        self.assertEqual(report["uncovered_or_unverified_old_rows"], 0)
        self.assertEqual(report["earliest_row_remaining_after_apply"],
                         self.db.execute("SELECT received_at FROM observations WHERE id=2").fetchone()[0])
        apply_retention(self.db, plan, self.config, confirm=True)
        self.assertEqual([r[0] for r in self.db.execute("SELECT id FROM observations ORDER BY id")],
                         [2, 15] + list(range(21, 31)))
        self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(self.count("prediction_context_links"), 4)

    def test_reference_added_after_dry_run_is_protected_at_apply(self):
        self.seed_observations()
        self.archive_all("observations", 10)
        plan = self.plan()
        self.db.execute("CREATE TABLE prediction_context_links (outcome_observation_id INTEGER)")
        self.db.execute("INSERT INTO prediction_context_links VALUES (5)")
        self.db.commit()
        apply_retention(self.db, plan, self.config, confirm=True)
        self.assertEqual(self.db.execute("SELECT id FROM observations WHERE id=5").fetchone(), (5,))

    def test_stream_events_unverified_archive_deletes_nothing(self):
        for i in range(6):
            self.add_event("coinbase", f"e{i}", CUTOFF_DT - timedelta(days=2, seconds=i))
        self.archive_all("stream_events", 3)
        for manifest in self.cloud.manifests:
            manifest["verified_at"] = None
        report = self.plan()["datasets"]["stream_events"]
        self.assertEqual(report["eligible_rows"], 0)
        apply_retention(self.db, self.plan(), self.config, confirm=True)
        self.assertEqual(self.count("stream_events"), 6)

    def test_stream_events_late_row_inside_range_untrusts_manifest(self):
        for i in range(4):
            self.add_event("coinbase", f"e{i}", CUTOFF_DT - timedelta(days=2, seconds=i))
        archive_raw_batch(self.db, self.cloud, "stream_events", limit=4)
        self.add_event("coinbase", "late",
                       CUTOFF_DT - timedelta(days=2, seconds=1, microseconds=500000))
        report = self.plan()["datasets"]["stream_events"]
        self.assertEqual(report["eligible_rows"], 0)

    def test_old_plan_skips_range_with_new_unarchived_row(self):
        when = CUTOFF_DT - timedelta(days=2)
        self.add_event("coinbase", "a", when)
        self.add_event("coinbase", "z", when + timedelta(seconds=2))
        self.archive_all("stream_events", 10)
        plan = self.plan()
        self.assertEqual(plan["datasets"]["stream_events"]["eligible_rows"], 2)
        self.add_event("coinbase", "late", when + timedelta(seconds=1))
        fresh = self.plan()["datasets"]["stream_events"]
        self.assertEqual(fresh["eligible_rows"], 0)
        self.assertEqual(fresh["uncovered_or_unverified_old_rows"], 3)
        result = apply_retention(self.db, plan, self.config, confirm=True)
        self.assertEqual(result["datasets"]["stream_events"]["deleted_rows"], 0)
        self.assertEqual(self.count("stream_events"), 3)

    def test_new_identity_cannot_enter_scope_even_with_manifest_count_slack(self):
        when = CUTOFF_DT - timedelta(days=2)
        for name, offset in (("a", 0), ("b", 1), ("z", 2)):
            self.add_event("coinbase", name, when + timedelta(seconds=offset))
        self.archive_all("stream_events", 10)
        self.db.execute("DELETE FROM stream_events WHERE event_id='b'")
        self.db.commit()
        plan = self.plan()
        self.add_event("coinbase", "late", when + timedelta(seconds=1))
        result = apply_retention(self.db, plan, self.config, confirm=True)
        self.assertEqual(result["datasets"]["stream_events"]["deleted_rows"], 2)
        self.assertEqual(self.db.execute("SELECT event_id FROM stream_events").fetchall(), [("late",)])

    def test_separate_writer_blocked_between_validation_and_delete(self):
        self.seed_observations()
        self.archive_all("observations", 10)
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "race.db")
            target = sqlite3.connect(path)
            self.db.backup(target)
            writer = sqlite3.connect(path, timeout=0)
            try:
                plan = plan_retention(target, self.cloud.manifests, self.config, NOW)
                original = retention._usable_intervals
                attempted = []
                def check_locked(db, dataset, manifests, bucket):
                    answer = original(db, dataset, manifests, bucket)
                    if dataset == "observations":
                        with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                            writer.execute("INSERT INTO observations VALUES(99,'m1',?,NULL,'book','{}')", (ts(CUTOFF_DT - timedelta(days=1)),))
                        writer.rollback()
                        attempted.append(True)
                    return answer
                with patch.object(retention, "_usable_intervals", side_effect=check_locked):
                    result = apply_retention(target, plan, RetentionConfig(True, 48, 7), confirm=True)
                self.assertGreater(len(attempted), 1)
                self.assertEqual(result["datasets"]["observations"]["deleted_rows"], 20)
                writer.execute("INSERT INTO observations VALUES(99,'m1',?,NULL,'book','{}')", (ts(CUTOFF_DT - timedelta(days=1)),))
                writer.commit()
                self.assertEqual(target.execute("SELECT COUNT(*) FROM observations WHERE id=99").fetchone()[0], 1)
            finally:
                writer.close()
                target.close()

    def test_non_canonical_timestamp_format_blocks_dataset(self):
        self.seed_observations()
        self.archive_all("observations", 10)
        self.db.execute(
            "INSERT INTO observations VALUES(99,'m1','2026-10-01T00:00:00.123+00:00',NULL,'book','{}')")
        report = self.plan()["datasets"]["observations"]
        self.assertEqual(report["blocked"], "non_canonical_received_at")
        self.assertEqual(report["eligible_rows"], 0)
        with self.assertRaises(RetentionError):
            apply_retention(self.db, self.plan(), self.config, confirm=True)
        self.assertEqual(self.count("observations"), 31)

    def test_dry_run_issues_no_delete_or_write(self):
        self.seed_observations()
        for i in range(5):
            self.add_event("coinbase", f"e{i}", CUTOFF_DT - timedelta(days=2, seconds=i))
        self.archive_all("observations", 10)
        self.archive_all("stream_events", 3)
        seen = []

        def authorizer(action, *_):
            if action in (sqlite3.SQLITE_DELETE, sqlite3.SQLITE_INSERT,
                          sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DROP_TABLE):
                seen.append(action)
            return sqlite3.SQLITE_OK

        before = (self.count("observations"), self.count("stream_events"))
        self.db.set_authorizer(authorizer)
        plan = self.plan()
        local_status(self.db, self.config, NOW)
        self.db.set_authorizer(None)
        self.assertEqual(seen, [])
        self.assertEqual(plan["mode"], "dry-run")
        self.assertEqual(before, (self.count("observations"), self.count("stream_events")))
        self.assertNotIn("_intervals", public_report(plan))
        json.dumps(public_report(plan))

    def test_apply_requires_confirmation_and_enable_flag(self):
        self.seed_observations()
        self.archive_all("observations", 10)
        plan = self.plan()
        with self.assertRaises(RetentionError):
            apply_retention(self.db, plan, self.config)
        with self.assertRaises(RetentionError):
            apply_retention(self.db, plan, self.config, confirm="yes")
        with self.assertRaises(RetentionError):
            apply_retention(self.db, plan, RetentionConfig(enabled=False), confirm=True)
        self.assertEqual(self.count("observations"), 30)

    def test_apply_uses_bounded_batches_and_leaves_structured_tables_alone(self):
        self.seed_observations()
        self.archive_all("observations", 10)
        structured = self.structured_counts()
        config = RetentionConfig(enabled=True, hours=48, batch_size=3)
        plan = plan_retention(self.db, self.cloud.manifests, config, NOW)
        committed_batches = []
        transaction_start = [None]
        def trace(sql):
            if sql == "BEGIN IMMEDIATE":
                transaction_start[0] = self.db.total_changes
            elif sql == "COMMIT" and transaction_start[0] is not None:
                changed = self.db.total_changes - transaction_start[0]
                if changed:
                    committed_batches.append(changed)
                transaction_start[0] = None
        self.db.set_trace_callback(trace)
        try:
            result = apply_retention(self.db, plan, config, confirm=True)
            first_batches = list(committed_batches)
            again = apply_retention(self.db, plan, config, confirm=True)
        finally:
            self.db.set_trace_callback(None)
        self.assertEqual(first_batches, [3, 3, 3, 1, 3, 3, 3, 1])
        self.assertEqual(sum(first_batches), 20)
        self.assertTrue(all(0 < size <= config.batch_size for size in first_batches))
        self.assertEqual(committed_batches, first_batches)
        self.assertEqual(result["datasets"]["observations"]["batches"], len(first_batches))
        self.assertEqual(result["datasets"]["observations"]["skipped_rows"], 0)
        self.assertEqual(again["datasets"]["observations"]["deleted_rows"], 0)
        self.assertEqual(again["datasets"]["observations"]["batches"], 0)
        self.assertEqual(self.db.execute("SELECT id FROM observations ORDER BY id").fetchall(),
                         [(i,) for i in range(21, 31)])
        # 2 manifests with old rows x ceil(10/3)=4 batches each.
        self.assertEqual(result["datasets"]["observations"]["deleted_rows"], 20)
        self.assertEqual(result["datasets"]["observations"]["batches"], 8)
        self.assertEqual(self.count("observations"), 10)
        self.assertEqual(self.structured_counts(), structured)
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM cloud_sync_state").fetchone()[0], 1)

    def test_apply_is_idempotent(self):
        self.seed_observations()
        for i in range(5):
            self.add_event("coinbase", f"e{i}", CUTOFF_DT - timedelta(days=2, seconds=i))
        self.archive_all("observations", 10)
        self.archive_all("stream_events", 2)
        first = apply_retention(self.db, self.plan(), self.config, confirm=True)
        self.assertEqual(first["datasets"]["stream_events"]["deleted_rows"], 5)
        counts = (self.count("observations"), self.count("stream_events"))
        second = apply_retention(self.db, self.plan(), self.config, confirm=True)
        self.assertEqual(second["datasets"]["observations"]["deleted_rows"], 0)
        self.assertEqual(second["datasets"]["stream_events"]["deleted_rows"], 0)
        self.assertEqual(counts, (self.count("observations"), self.count("stream_events")))
        self.assertEqual(counts, (10, 0))

    def test_partial_deletion_resumes_without_losing_coverage(self):
        self.seed_observations()
        archive_raw_batch(self.db, self.cloud, "observations", limit=20)
        self.db.execute("DELETE FROM observations WHERE id<=5")
        self.db.commit()
        report = self.plan()["datasets"]["observations"]
        self.assertEqual(report["eligible_rows"], 15)

    def test_timestamp_contract_and_explicit_timezone_policy(self):
        for raw, expected in (
            ("2026-10-25T21:46:01+00:00", "2026-10-25T21:46:01.000000+00:00"),
            ("2026-10-25T21:46:01.123456+00:00", "2026-10-25T21:46:01.123456+00:00"),
        ):
            self.assertEqual(canonical_time(raw), expected)
        for raw in ("2026-10-17T20:28:26", "junk", "2026-02-30T00:00:00+00:00",
                    "2026-10-17T20:28:26Z", "2026-10-17T20:28:26.1+00:00",
                    "2026-10-17T15:28:26.310944-05:00", "2026-10-17 20:28:26+00:00"):
            with self.subTest(raw=raw), self.assertRaises(RetentionError):
                canonical_time(raw)
        # Internal aware datetime inputs are explicitly converted to UTC.
        self.assertEqual(canonical_time(datetime.fromisoformat("2026-10-17T15:28:26-05:00")),
                         "2026-10-17T20:28:26.000000+00:00")

    def test_exact_seconds_covered_and_cutoff_kept_without_rewriting_evidence(self):
        self.seed_observations()
        for i in range(1, 31):
            self.db.execute("UPDATE observations SET received_at=replace(received_at,'.000000','') WHERE id=?", (i,))
        self.db.execute("UPDATE observations SET received_at=? WHERE id=20", (CUTOFF_DT.isoformat(),))
        self.add_event("coinbase", "old", CUTOFF_DT - timedelta(seconds=1))
        self.add_event("coinbase", "cutoff", CUTOFF_DT)
        self.db.execute("UPDATE stream_events SET received_at=replace(received_at,'.000000','')")
        self.db.commit()
        self.archive_all("observations", 10)
        self.archive_all("stream_events", 10)
        before = self.db.iterdump()
        evidence = list(before)
        manifests = json.dumps(self.cloud.manifests, sort_keys=True)
        plan = self.plan()
        self.assertEqual(plan["datasets"]["observations"]["eligible_rows"], 19)
        self.assertEqual(plan["datasets"]["stream_events"]["eligible_rows"], 1)
        self.assertEqual(list(self.db.iterdump()), evidence)
        self.assertEqual(json.dumps(self.cloud.manifests, sort_keys=True), manifests)
        apply_retention(self.db, plan, self.config, confirm=True)
        self.assertEqual(self.db.execute("SELECT received_at FROM observations WHERE id=20").fetchone()[0], CUTOFF_DT.isoformat())
        self.assertEqual(self.db.execute("SELECT event_id FROM stream_events").fetchall(), [("cutoff",)])

    def test_mixed_width_stream_cursor_orders_timestamp_source_and_event(self):
        same = CUTOFF_DT - timedelta(seconds=1)
        for source, event, when in (("coinbase", "a", same), ("coinbase", "b", same),
                                     ("other", "a", same),
                                     ("coinbase", "fraction", same + timedelta(microseconds=1))):
            self.add_event(source, event, when)
        self.archive_all("stream_events", 10)
        # Historical representations differ but their logical positions do not.
        self.db.execute("UPDATE stream_events SET received_at=replace(received_at,'.000000','') WHERE event_id='a'")
        self.db.commit()
        manifest = self.cloud.manifests[0]
        manifest["ended_at"] = same.isoformat()
        manifest["metadata"]["last_source_key"] = json.dumps(["coinbase", "b"])
        manifest["event_count"] = 2
        plan = self.plan()
        report = plan["datasets"]["stream_events"]
        self.assertEqual(report["eligible_rows"], 2)
        self.assertEqual(report["uncovered_or_unverified_old_rows"], 2)
        apply_retention(self.db, plan, self.config, confirm=True)
        self.assertEqual(set(self.db.execute("SELECT source,event_id FROM stream_events")),
                         {("other", "a"), ("coinbase", "fraction")})

    def test_malformed_timestamp_added_after_plan_fails_before_any_delete(self):
        self.seed_observations()
        self.archive_all("observations", 10)
        plan = self.plan()
        self.db.execute("UPDATE observations SET received_at='2026-99-99T00:00:00.000000+00:00' WHERE id=1")
        self.db.commit()
        with self.assertRaises(RetentionError):
            apply_retention(self.db, plan, self.config, confirm=True)
        self.assertEqual(self.count("observations"), 30)

    def test_shared_writer_preserves_caller_timestamp(self):
        from collector import save_observation
        raw = "2026-09-30T01:20:00Z"
        save_observation(self.db, "m1", raw, "book", {})
        self.assertEqual(self.db.execute("SELECT received_at FROM observations").fetchone()[0], raw)

    def test_live_raw_writers_emit_zero_microseconds(self):
        from unittest.mock import patch
        from streaming import save_coinbase, save_polymarket
        self.db.execute("ALTER TABLE markets ADD COLUMN slug TEXT")
        self.db.execute("UPDATE markets SET slug='m1'")
        with patch("streaming.utcnow", return_value=NOW):
            self.assertTrue(save_polymarket(self.db, {"marketData": {"marketSlug": "m1"}}))
            save_coinbase(self.db, {"type": "ticker", "product_id": "BTC-USD",
                                   "trade_id": 1, "time": NOW.isoformat(), "price": "100"})
        for table in ("observations", "stream_events"):
            self.assertEqual(self.db.execute(f"SELECT received_at FROM {table}").fetchone()[0], ts(NOW))


class ManifestFetchTests(unittest.TestCase):
    def test_select_paginates_and_fetch_filters_verified_manifests(self):
        requests = []
        pages = [[{"object_path": str(i)} for i in range(2)], [{"object_path": "2"}]]

        def handler(request):
            requests.append(request)
            return httpx.Response(200, json=pages[len(requests) - 1])

        cloud = SupabaseHTTP(
            CloudConfig("https://example.supabase.co", "secret"),
            client=httpx.Client(transport=httpx.MockTransport(handler)))
        rows = cloud.select("raw_archives", {"verified_at": "not.is.null"}, page_size=2)
        self.assertEqual(len(rows), 3)
        self.assertEqual(requests[1].url.params["offset"], "2")
        self.assertTrue(all(r.method == "GET" for r in requests))

        requests.clear()
        pages[:] = [[{"object_path": "a"}]]
        manifests = fetch_verified_manifests(cloud, "market-raw")
        self.assertEqual(manifests, [{"object_path": "a"}])
        params = requests[0].url.params
        self.assertEqual(params["verified_at"], "not.is.null")
        self.assertEqual(params["bucket"], "eq.market-raw")

    def test_http_failure_aborts_instead_of_returning_partial_manifests(self):
        cloud = SupabaseHTTP(
            CloudConfig("https://example.supabase.co", "secret"),
            client=httpx.Client(transport=httpx.MockTransport(
                lambda request: httpx.Response(503))))
        with self.assertRaises(httpx.HTTPStatusError):
            fetch_verified_manifests(cloud, "market-raw")


if __name__ == "__main__":
    unittest.main()
