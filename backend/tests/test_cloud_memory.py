import gzip
import json
import os
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from cloud_memory import (
    CloudConfig,
    archive_raw_window,
    build_archive,
    initialize_local_sync,
    sync_structured_once,
)


class FakeCloud:
    def __init__(self):
        self.upserts = []
        self.uploads = []

    def upsert(self, table, rows, on_conflict):
        self.upserts.append((table, rows, on_conflict))
        return len(rows)

    def upload_bytes(self, bucket, object_path, payload, content_type="application/gzip"):
        self.uploads.append((bucket, object_path, payload, content_type))
        return {"bucket": bucket, "object_path": object_path, "bytes": len(payload)}


class CloudMemoryTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript(
            """
            CREATE TABLE markets (
              id TEXT PRIMARY KEY, slug TEXT NOT NULL UNIQUE, duration INTEGER NOT NULL,
              start TEXT NOT NULL, end TEXT NOT NULL, target TEXT, final TEXT, result TEXT,
              status TEXT, index_symbol TEXT, rules TEXT, first_seen TEXT NOT NULL,
              last_seen TEXT NOT NULL, raw_json TEXT NOT NULL
            );
            CREATE TABLE feature_snapshots (
              id INTEGER PRIMARY KEY, market_id TEXT NOT NULL, as_of TEXT NOT NULL,
              version INTEGER NOT NULL, values_json TEXT NOT NULL,
              quality_json TEXT NOT NULL, evidence_json TEXT NOT NULL
            );
            CREATE TABLE predictions (
              id INTEGER PRIMARY KEY, snapshot_id INTEGER NOT NULL, market_id TEXT NOT NULL,
              model_version TEXT NOT NULL, as_of TEXT NOT NULL, created_at TEXT NOT NULL,
              seconds_remaining REAL NOT NULL, probability_up TEXT,
              probability_down TEXT, abstain_reason TEXT,
              assumptions_json TEXT NOT NULL, component_scores TEXT
            );
            CREATE TABLE news_events (
              id INTEGER PRIMARY KEY, source TEXT NOT NULL, source_guid TEXT NOT NULL,
              url TEXT NOT NULL, title TEXT NOT NULL, published_at TEXT,
              first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
              categories_json TEXT NOT NULL, asset_tag TEXT NOT NULL
            );
            CREATE TABLE candles (
              source TEXT NOT NULL, symbol TEXT NOT NULL, granularity INTEGER NOT NULL,
              time INTEGER NOT NULL, low TEXT, high TEXT, open TEXT, close TEXT,
              volume TEXT, first_seen TEXT
            );
            CREATE TABLE observations (
              id INTEGER PRIMARY KEY, market_id TEXT NOT NULL, received_at TEXT NOT NULL,
              source_time TEXT, kind TEXT NOT NULL, payload TEXT NOT NULL
            );
            CREATE TABLE stream_events (
              source TEXT NOT NULL, event_id TEXT NOT NULL, received_at TEXT NOT NULL,
              source_time TEXT NOT NULL, price TEXT NOT NULL, size TEXT, side TEXT,
              payload TEXT NOT NULL, PRIMARY KEY(source,event_id)
            );
            """
        )
        self.db.execute(
            """INSERT INTO markets VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "m1", "btc-test", 900,
                "2026-10-22T12:00:00+00:00", "2026-10-22T12:15:00+00:00",
                "100", "101", "UP", "MARKET_STATUS_RESOLVED", "BRTI", "rules",
                "2026-10-22T12:00:01+00:00", "2026-10-22T12:16:00+00:00",
                json.dumps({"id": "m1"}),
            ),
        )
        self.db.execute(
            """INSERT INTO feature_snapshots VALUES(?,?,?,?,?,?,?)""",
            (
                1, "m1", "2026-10-22T12:10:00+00:00", 1,
                json.dumps({"seconds_remaining": 300, "reference_price_usd": "100.5"}),
                json.dumps({"price": {"status": "fresh"}}),
                json.dumps({"input": 1}),
            ),
        )
        self.db.execute(
            """INSERT INTO predictions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                1, 1, "m1", "gaussian_distance_v1",
                "2026-10-22T12:10:00+00:00", "2026-10-22T12:10:01+00:00",
                300, "0.60", "0.40", None, json.dumps({"model": "test"}),
                json.dumps({"baseline": 0.6}),
            ),
        )
        self.db.execute(
            """INSERT INTO news_events VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                1, "test", "g1", "https://example.com/a", "BTC headline",
                "2026-10-22T11:00:00+00:00", "2026-10-22T11:01:00+00:00",
                "2026-10-22T11:01:00+00:00", json.dumps(["BTC"]), "BTC",
            ),
        )
        self.db.execute(
            """INSERT INTO candles VALUES(?,?,?,?,?,?,?,?,?,?)""",
            ("coinbase", "BTC-USD", 60, 1792670400, "99", "102", "100", "101", "12.5",
             "2026-10-22T12:01:00+00:00"),
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_config_requires_explicit_enable_and_secret(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                CloudConfig.from_env()
        with patch.dict(
            os.environ,
            {
                "ENABLE_SUPABASE_SYNC": "true",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SECRET_KEY": "secret",
                "SUPABASE_SYNC_BATCH_SIZE": "200",
            },
            clear=True,
        ):
            config = CloudConfig.from_env()
            self.assertEqual(config.batch_size, 200)
            self.assertEqual(config.raw_bucket, "market-raw")

    def test_structured_sync_is_bounded_and_checkpointed(self):
        cloud = FakeCloud()
        result = sync_structured_once(self.db, cloud, batch_size=100)
        self.assertEqual(
            result,
            {
                "markets": 1,
                "feature_snapshots": 1,
                "predictions": 1,
                "news_events": 1,
                "candles": 1,
            },
        )
        tables = [item[0] for item in cloud.upserts]
        for table in (
            "markets", "official_outcomes", "feature_snapshots",
            "predictions", "news_events", "candles", "sync_checkpoints",
        ):
            self.assertIn(table, tables)

        prediction = next(
            rows[0] for table, rows, _ in cloud.upserts if table == "predictions"
        )
        self.assertEqual(prediction["source_id"], 1)
        self.assertEqual(prediction["extra_json"]["component_scores"], {"baseline": 0.6})

        second = sync_structured_once(self.db, cloud, batch_size=100)
        self.assertEqual(sum(second.values()), 0)
        state = self.db.execute(
            "SELECT rows_synced,status FROM cloud_sync_state WHERE dataset='predictions'"
        ).fetchone()
        self.assertEqual(state, (1, "ok"))

    def test_archive_is_deterministic_and_records_manifest_after_upload(self):
        payload = {"marketData": {"marketSlug": "btc-test", "bids": [["0.5", "10"]]}}
        self.db.execute(
            """INSERT INTO observations VALUES(?,?,?,?,?,?)""",
            (
                1, "m1", "2026-10-22T12:05:00+00:00",
                "2026-10-22T12:05:00+00:00", "stream_book", json.dumps(payload),
            ),
        )
        self.db.commit()
        cloud = FakeCloud()

        manifest = archive_raw_window(
            self.db,
            cloud,
            "observations",
            "2026-10-22T12:00:00+00:00",
            "2026-10-22T13:00:00+00:00",
        )
        self.assertEqual(manifest["event_count"], 1)
        self.assertEqual(len(cloud.uploads), 1)
        bucket, object_path, compressed, content_type = cloud.uploads[0]
        self.assertEqual(bucket, "market-raw")
        self.assertTrue(object_path.endswith(".jsonl.gz"))
        self.assertEqual(content_type, "application/gzip")
        decoded = gzip.decompress(compressed).decode()
        archived = json.loads(decoded.strip())
        self.assertEqual(archived["row"]["payload"], payload)

        manifest_call = next(
            item for item in cloud.upserts if item[0] == "raw_archives"
        )
        self.assertEqual(manifest_call[1][0]["sha256"], manifest["sha256"])

        raw1, zipped1, hash1 = build_archive("observations", [{"payload": json.dumps(payload)}])
        raw2, zipped2, hash2 = build_archive("observations", [{"payload": json.dumps(payload)}])
        self.assertEqual(raw1, raw2)
        self.assertEqual(zipped1, zipped2)
        self.assertEqual(hash1, hash2)

    def test_local_sync_schema_is_tiny_and_separate_from_raw_data(self):
        initialize_local_sync(self.db)
        columns = [row[1] for row in self.db.execute("PRAGMA table_info(cloud_sync_state)")]
        self.assertIn("last_source_id", columns)
        self.assertIn("last_source_time", columns)
        self.assertIn("last_source_key", columns)


if __name__ == "__main__":
    unittest.main()
