"""Phase 1.75 cloud persistence primitives.

Live forecasts never depend on this module. It copies structured history to
Supabase Postgres and raw evidence to private Supabase Storage after the live
path has already completed.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import quote
import sqlite3

import httpx


DEFAULT_BATCH_SIZE = 100
RAW_BUCKET = "market-raw"


def enabled(value):
    return str(value).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class CloudConfig:
    url: str
    secret_key: str
    batch_size: int = DEFAULT_BATCH_SIZE
    raw_bucket: str = RAW_BUCKET

    @classmethod
    def from_env(cls, require_enabled=True):
        if require_enabled and not enabled(os.getenv("ENABLE_SUPABASE_SYNC", "false")):
            raise RuntimeError("Supabase sync is disabled; set ENABLE_SUPABASE_SYNC=true explicitly")
        url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
        key = os.getenv("SUPABASE_SECRET_KEY") or ""
        if not url.startswith("https://") or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY are required")
        batch = int(os.getenv("SUPABASE_SYNC_BATCH_SIZE", str(DEFAULT_BATCH_SIZE)))
        if not 1 <= batch <= 1000:
            raise ValueError("SUPABASE_SYNC_BATCH_SIZE must be 1..1000")
        return cls(
            url=url,
            secret_key=key,
            batch_size=batch,
            raw_bucket=os.getenv("SUPABASE_RAW_BUCKET", RAW_BUCKET),
        )


class SupabaseHTTP:
    """Small server-side Supabase client using the existing httpx dependency."""

    def __init__(self, config, client=None, timeout=30):
        self.config = config
        self.client = client or httpx.Client(timeout=timeout)

    def close(self):
        self.client.close()

    def _headers(self, **extra):
        headers = {
            "apikey": self.config.secret_key,
            "Authorization": f"Bearer {self.config.secret_key}",
        }
        headers.update(extra)
        return headers

    def upsert(self, table, rows, on_conflict):
        if not rows:
            return 0
        response = self.client.post(
            f"{self.config.url}/rest/v1/{quote(table, safe='')}",
            params={"on_conflict": on_conflict},
            headers=self._headers(
                **{
                    "Content-Type": "application/json",
                    "Prefer": "resolution=merge-duplicates,return=minimal",
                }
            ),
            json=rows,
        )
        response.raise_for_status()
        return len(rows)

    def upload_bytes(self, bucket, object_path, payload, content_type="application/gzip"):
        response = self.client.post(
            f"{self.config.url}/storage/v1/object/{quote(bucket, safe='')}/{quote(object_path, safe='/')}",
            headers=self._headers(
                **{
                    "Content-Type": content_type,
                    "x-upsert": "true",
                }
            ),
            content=payload,
        )
        response.raise_for_status()
        return {
            "bucket": bucket,
            "object_path": object_path,
            "bytes": len(payload),
        }

    def download_bytes(self, bucket, object_path):
        response = self.client.get(
            f"{self.config.url}/storage/v1/object/authenticated/{quote(bucket, safe='')}/{quote(object_path, safe='/')}",
            headers=self._headers(**{"Cache-Control": "no-store"}),
        )
        response.raise_for_status()
        return response.content

    def verify_object(self, bucket, object_path, expected_sha256, expected_bytes):
        payload = self.download_bytes(bucket, object_path)
        actual_sha256 = hashlib.sha256(payload).hexdigest()
        if len(payload) != expected_bytes:
            raise RuntimeError(
                f"Storage verification size mismatch for {bucket}/{object_path}: "
                f"{len(payload)} != {expected_bytes}"
            )
        if actual_sha256 != expected_sha256:
            raise RuntimeError(
                f"Storage verification checksum mismatch for {bucket}/{object_path}"
            )
        return {
            "bytes": len(payload),
            "sha256": actual_sha256,
            "verified_at": _now(),
        }


LOCAL_STATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS cloud_sync_state (
  dataset TEXT PRIMARY KEY,
  last_source_id INTEGER,
  last_source_time TEXT,
  last_source_key TEXT,
  rows_synced INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'idle',
  detail TEXT,
  updated_at TEXT NOT NULL
);
"""


def initialize_local_sync(db):
    db.execute(LOCAL_STATE_SCHEMA)
    db.commit()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _checkpoint(db, dataset):
    row = db.execute(
        """SELECT last_source_id,last_source_time,last_source_key,rows_synced
           FROM cloud_sync_state WHERE dataset=?""",
        (dataset,),
    ).fetchone()
    return row or (None, None, None, 0)


def _save_checkpoint(db, dataset, source_id=None, source_time=None, source_key=None,
                     rows_added=0, status="ok", detail=None):
    previous = _checkpoint(db, dataset)
    db.execute(
        """INSERT INTO cloud_sync_state(
             dataset,last_source_id,last_source_time,last_source_key,
             rows_synced,status,detail,updated_at)
           VALUES(?,?,?,?,?,?,?,?)
           ON CONFLICT(dataset) DO UPDATE SET
             last_source_id=excluded.last_source_id,
             last_source_time=excluded.last_source_time,
             last_source_key=excluded.last_source_key,
             rows_synced=cloud_sync_state.rows_synced+excluded.rows_synced,
             status=excluded.status,
             detail=excluded.detail,
             updated_at=excluded.updated_at""",
        (
            dataset,
            source_id if source_id is not None else previous[0],
            source_time if source_time is not None else previous[1],
            source_key if source_key is not None else previous[2],
            rows_added,
            status,
            detail,
            _now(),
        ),
    )
    db.commit()


def _json(value, default):
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _number(value):
    if value in (None, ""):
        return None
    return float(value)


def _dict_rows(cursor):
    fields = [item[0] for item in cursor.description]
    return [dict(zip(fields, row)) for row in cursor.fetchall()]


def _table_exists(db, table):
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _market_rows(db, limit):
    _, last_time, last_key, _ = _checkpoint(db, "markets")
    if last_time:
        cursor = db.execute(
            """SELECT * FROM markets
               WHERE julianday(last_seen)>julianday(?)
                  OR (last_seen=? AND id>?)
               ORDER BY julianday(last_seen),id LIMIT ?""",
            (last_time, last_time, last_key or "", limit),
        )
    else:
        cursor = db.execute(
            "SELECT * FROM markets ORDER BY julianday(last_seen),id LIMIT ?",
            (limit,),
        )
    return _dict_rows(cursor)


def _map_market(row):
    return {
        "id": row["id"],
        "slug": row["slug"],
        "duration": row["duration"],
        "start": row["start"],
        "end": row["end"],
        "target": _number(row.get("target")),
        "final": _number(row.get("final")),
        "result": row.get("result"),
        "status": row.get("status"),
        "index_symbol": row.get("index_symbol"),
        "rules": row.get("rules"),
        "first_seen": row["first_seen"],
        "last_seen": row["last_seen"],
        "raw_json": _json(row.get("raw_json"), {}),
        "synced_at": _now(),
    }


def _map_outcome(row):
    if row.get("result") not in ("UP", "DOWN") or row.get("final") in (None, ""):
        return None
    return {
        "market_id": row["id"],
        "final": _number(row["final"]),
        "result": row["result"],
        "confirmed_at": row["last_seen"],
        "source_json": _json(row.get("raw_json"), {}),
        "synced_at": _now(),
    }


def _ensure_markets(db, cloud, market_ids):
    ids = sorted({value for value in market_ids if value})
    if not ids:
        return
    placeholders = ",".join("?" for _ in ids)
    rows = _dict_rows(db.execute(
        f"SELECT * FROM markets WHERE id IN ({placeholders})",
        ids,
    ))
    if len(rows) != len(ids):
        found = {row["id"] for row in rows}
        missing = sorted(set(ids) - found)
        raise RuntimeError(f"Missing local market dependencies: {missing}")
    cloud.upsert("markets", [_map_market(row) for row in rows], "id")
    outcomes = [item for item in (_map_outcome(row) for row in rows) if item]
    if outcomes:
        cloud.upsert("official_outcomes", outcomes, "market_id")


def _ensure_snapshots(db, cloud, snapshot_ids):
    ids = sorted({int(value) for value in snapshot_ids if value is not None})
    if not ids:
        return
    placeholders = ",".join("?" for _ in ids)
    rows = _dict_rows(db.execute(
        f"SELECT * FROM feature_snapshots WHERE id IN ({placeholders})",
        ids,
    ))
    if len(rows) != len(ids):
        found = {row["id"] for row in rows}
        missing = sorted(set(ids) - found)
        raise RuntimeError(f"Missing local snapshot dependencies: {missing}")
    _ensure_markets(db, cloud, [row["market_id"] for row in rows])
    cloud.upsert("feature_snapshots", [_map_snapshot(row) for row in rows], "source_id")


def _id_rows(db, dataset, table, limit):
    last_id, _, _, _ = _checkpoint(db, dataset)
    cursor = db.execute(
        f'SELECT * FROM "{table}" WHERE id>? ORDER BY id LIMIT ?',
        (last_id or 0, limit),
    )
    return _dict_rows(cursor)


def _map_snapshot(row):
    return {
        "source_id": row["id"],
        "market_id": row["market_id"],
        "as_of": row["as_of"],
        "version": row["version"],
        "values_json": _json(row["values_json"], {}),
        "quality_json": _json(row["quality_json"], {}),
        "evidence_json": _json(row["evidence_json"], {}),
        "synced_at": _now(),
    }


PREDICTION_CORE = {
    "id", "snapshot_id", "market_id", "model_version", "as_of", "created_at",
    "seconds_remaining", "probability_up", "probability_down", "abstain_reason",
    "assumptions_json",
}


def _map_prediction(row):
    extra = {}
    for key, value in row.items():
        if key in PREDICTION_CORE:
            continue
        extra[key] = _json(value, value) if key.endswith("_json") or key in (
            "component_scores", "decision_summary"
        ) else value
    return {
        "source_id": row["id"],
        "snapshot_source_id": row["snapshot_id"],
        "market_id": row["market_id"],
        "model_version": row["model_version"],
        "as_of": row["as_of"],
        "created_at": row["created_at"],
        "seconds_remaining": float(row["seconds_remaining"]),
        "probability_up": _number(row.get("probability_up")),
        "probability_down": _number(row.get("probability_down")),
        "abstain_reason": row.get("abstain_reason"),
        "assumptions_json": _json(row.get("assumptions_json"), {}),
        "extra_json": extra,
        "synced_at": _now(),
    }


def _map_news(row):
    return {
        "source_id": row["id"],
        "source": row["source"],
        "source_guid": row["source_guid"],
        "url": row["url"],
        "title": row["title"],
        "published_at": row.get("published_at"),
        "first_seen": row["first_seen"],
        "last_seen": row["last_seen"],
        "categories_json": _json(row.get("categories_json"), []),
        "asset_tag": row["asset_tag"],
        "synced_at": _now(),
    }


def _candle_rows(db, limit):
    last_time, _, _, _ = _checkpoint(db, "candles")
    cursor = db.execute(
        """SELECT source,symbol,granularity,time,low,high,open,close,volume,first_seen
           FROM candles WHERE time>? ORDER BY time LIMIT ?""",
        (last_time or 0, limit),
    )
    return _dict_rows(cursor)


def _map_candle(row):
    return {
        "source": row["source"],
        "symbol": row["symbol"],
        "granularity": row["granularity"],
        "time": row["time"],
        "low": _number(row.get("low")),
        "high": _number(row.get("high")),
        "open": _number(row.get("open")),
        "close": _number(row.get("close")),
        "volume": _number(row.get("volume")),
        "first_seen": row.get("first_seen"),
        "synced_at": _now(),
    }


def _cloud_checkpoint(cloud, dataset, source_id=None, source_time=None,
                      source_key=None, rows_synced=0, status="ok", detail=None):
    cloud.upsert(
        "sync_checkpoints",
        [{
            "dataset": dataset,
            "last_source_id": source_id,
            "last_source_time": source_time,
            "last_source_key": source_key,
            "rows_synced": rows_synced,
            "status": status,
            "detail": detail,
            "updated_at": _now(),
        }],
        "dataset",
    )


def sync_structured_once(db, cloud, batch_size=DEFAULT_BATCH_SIZE):
    """Copy one bounded batch per structured dataset; never reads raw book/tick payloads."""
    initialize_local_sync(db)
    result = {}

    if _table_exists(db, "markets"):
        rows = _market_rows(db, batch_size)
        mapped = [_map_market(row) for row in rows]
        if mapped:
            cloud.upsert("markets", mapped, "id")
            outcomes = [item for item in (_map_outcome(row) for row in rows) if item]
            if outcomes:
                cloud.upsert("official_outcomes", outcomes, "market_id")
            last = rows[-1]
            _save_checkpoint(db, "markets", source_time=last["last_seen"],
                             source_key=last["id"], rows_added=len(rows))
            total_synced = _checkpoint(db, "markets")[3]
            _cloud_checkpoint(cloud, "markets", source_time=last["last_seen"],
                              source_key=last["id"], rows_synced=total_synced)
        result["markets"] = len(rows)

    specs = (
        ("feature_snapshots", "feature_snapshots", _map_snapshot, "source_id"),
        ("predictions", "predictions", _map_prediction, "source_id"),
        ("news_events", "news_events", _map_news, "source_id"),
    )
    for dataset, table, mapper, conflict in specs:
        if not _table_exists(db, table):
            result[dataset] = 0
            continue
        rows = _id_rows(db, dataset, table, batch_size)
        mapped = [mapper(row) for row in rows]
        if mapped:
            if dataset == "feature_snapshots":
                _ensure_markets(db, cloud, [row["market_id"] for row in rows])
            elif dataset == "predictions":
                _ensure_snapshots(db, cloud, [row["snapshot_id"] for row in rows])
            cloud.upsert(table, mapped, conflict)
            last_id = rows[-1]["id"]
            _save_checkpoint(db, dataset, source_id=last_id, rows_added=len(rows))
            total_synced = _checkpoint(db, dataset)[3]
            _cloud_checkpoint(cloud, dataset, source_id=last_id, rows_synced=total_synced)
        result[dataset] = len(rows)

    if _table_exists(db, "candles"):
        rows = _candle_rows(db, batch_size)
        mapped = [_map_candle(row) for row in rows]
        if mapped:
            cloud.upsert("candles", mapped, "source,symbol,granularity,time")
            last_time = rows[-1]["time"]
            _save_checkpoint(db, "candles", source_id=last_time, rows_added=len(rows))
            total_synced = _checkpoint(db, "candles")[3]
            _cloud_checkpoint(cloud, "candles", source_id=last_time, rows_synced=total_synced)
        result["candles"] = len(rows)

    return result


def _archive_rows(db, dataset, start, end):
    if dataset == "observations":
        cursor = db.execute(
            """SELECT id,market_id,received_at,source_time,kind,payload
               FROM observations
               WHERE julianday(received_at)>=julianday(?)
                 AND julianday(received_at)<julianday(?)
               ORDER BY julianday(received_at),id""",
            (start, end),
        )
    elif dataset == "stream_events":
        cursor = db.execute(
            """SELECT rowid AS source_rowid,source,event_id,received_at,source_time,
                      price,size,side,payload
               FROM stream_events
               WHERE julianday(received_at)>=julianday(?)
                 AND julianday(received_at)<julianday(?)
               ORDER BY julianday(received_at),rowid""",
            (start, end),
        )
    else:
        raise ValueError("dataset must be observations or stream_events")
    return _dict_rows(cursor)


def build_archive(dataset, rows):
    lines = []
    for row in rows:
        copy = dict(row)
        if "payload" in copy:
            copy["payload"] = _json(copy["payload"], copy["payload"])
        lines.append(json.dumps(
            {"dataset": dataset, "row": copy},
            sort_keys=True,
            separators=(",", ":"),
        ))
    raw = (("\n".join(lines) + "\n") if lines else "").encode()
    compressed = gzip.compress(raw, compresslevel=6, mtime=0)
    return raw, compressed, hashlib.sha256(compressed).hexdigest()


def archive_object_path(dataset, start, end):
    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(timezone.utc)
    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00")).astimezone(timezone.utc)
    source = "polymarket" if dataset == "observations" else "coinbase"
    prefix = start_dt.strftime("%Y/%m/%d/%H")
    name = (
        start_dt.strftime("%Y%m%dT%H%M%SZ")
        + "_"
        + end_dt.strftime("%Y%m%dT%H%M%SZ")
        + ".jsonl.gz"
    )
    return source, f"{source}/{prefix}/{name}"


def _stream_cursor_key(row):
    return json.dumps([row["source"], row["event_id"]], separators=(",", ":"))


def _raw_batch_rows(db, dataset, limit):
    checkpoint_name = f"archive:{dataset}"
    last_id, last_time, last_key, _ = _checkpoint(db, checkpoint_name)
    if dataset == "observations":
        cursor = db.execute(
            """SELECT id AS source_id,id,market_id,received_at,source_time,kind,payload
               FROM observations WHERE id>? ORDER BY id LIMIT ?""",
            (last_id or 0, limit),
        )
        return _dict_rows(cursor)
    if dataset != "stream_events":
        raise ValueError("dataset must be observations or stream_events")

    # stream_events has a composite primary key but no stable INTEGER PRIMARY KEY.
    # Never checkpoint SQLite rowid: VACUUM may renumber rowids. This index makes
    # the durable (received_at,source,event_id) cursor efficient for backfill and
    # later rolling retention.
    db.execute(
        """CREATE INDEX IF NOT EXISTS stream_events_archive_cursor
           ON stream_events(received_at,source,event_id)"""
    )
    db.commit()
    if last_time and last_key:
        source, event_id = _json(last_key, [None, None])
        if source is None or event_id is None:
            raise RuntimeError("Invalid stream_events archive checkpoint key")
        cursor = db.execute(
            """SELECT source,event_id,received_at,source_time,price,size,side,payload
               FROM stream_events
               WHERE received_at>?
                  OR (received_at=? AND source>?)
                  OR (received_at=? AND source=? AND event_id>?)
               ORDER BY received_at,source,event_id LIMIT ?""",
            (last_time, last_time, source, last_time, source, event_id, limit),
        )
    else:
        cursor = db.execute(
            """SELECT source,event_id,received_at,source_time,price,size,side,payload
               FROM stream_events
               ORDER BY received_at,source,event_id LIMIT ?""",
            (limit,),
        )
    return _dict_rows(cursor)


def archive_batch_object_path(dataset, rows):
    first = rows[0]
    last = rows[-1]
    started = datetime.fromisoformat(
        first["received_at"].replace("Z", "+00:00")
    ).astimezone(timezone.utc)
    source = "polymarket" if dataset == "observations" else "coinbase"
    prefix = started.strftime("%Y/%m/%d/%H")
    if dataset == "observations":
        suffix = f"{first['source_id']}_{last['source_id']}"
    else:
        key_material = (
            _stream_cursor_key(first) + "|" + _stream_cursor_key(last)
        ).encode()
        suffix = hashlib.sha256(key_material).hexdigest()[:16]
    name = f"{dataset}_{suffix}.jsonl.gz"
    return source, f"{source}/{prefix}/{name}"


def archive_raw_batch(db, cloud, dataset, limit=5000, bucket=RAW_BUCKET):
    if not 1 <= limit <= 50000:
        raise ValueError("raw archive batch limit must be 1..50000")
    initialize_local_sync(db)
    checkpoint_name = f"archive:{dataset}"
    rows = _raw_batch_rows(db, dataset, limit)
    if not rows:
        return None

    raw, compressed, digest = build_archive(dataset, rows)
    source, object_path = archive_batch_object_path(dataset, rows)
    cloud.upload_bytes(bucket, object_path, compressed, "application/gzip")
    verification = cloud.verify_object(
        bucket, object_path, digest, len(compressed)
    )
    first, last = rows[0], rows[-1]
    first_source_id = first.get("source_id")
    last_source_id = last.get("source_id")
    first_source_key = (
        None if dataset == "observations" else _stream_cursor_key(first)
    )
    last_source_key = (
        None if dataset == "observations" else _stream_cursor_key(last)
    )
    manifest = {
        "source": source,
        "market_id": None,
        "started_at": first["received_at"],
        "ended_at": last["received_at"],
        "bucket": bucket,
        "object_path": object_path,
        "compression": "gzip",
        "content_type": "application/jsonl",
        "sha256": digest,
        "event_count": len(rows),
        "uncompressed_bytes": len(raw),
        "compressed_bytes": len(compressed),
        "first_source_id": first_source_id,
        "last_source_id": last_source_id,
        "verified_at": verification["verified_at"],
        "metadata": {
            "dataset": dataset,
            "format": "jsonl",
            "gzip_mtime": 0,
            "verification": "authenticated_readback_sha256",
            "first_source_key": first_source_key,
            "last_source_key": last_source_key,
        },
    }
    cloud.upsert("raw_archives", [manifest], "bucket,object_path")
    _save_checkpoint(
        db,
        checkpoint_name,
        source_id=last_source_id,
        source_time=last["received_at"],
        source_key=last_source_key,
        rows_added=len(rows),
        status="verified",
        detail=object_path,
    )
    total_synced = _checkpoint(db, checkpoint_name)[3]
    _cloud_checkpoint(
        cloud,
        checkpoint_name,
        source_id=last_source_id,
        source_time=last["received_at"],
        source_key=last_source_key,
        rows_synced=total_synced,
        status="verified",
        detail=object_path,
    )
    return manifest


def archive_raw_backfill(db, cloud, dataset, max_batches=24, batch_size=5000,
                         bucket=RAW_BUCKET):
    if not 1 <= max_batches <= 10000:
        raise ValueError("max_batches must be 1..10000")
    total_events = 0
    batches = []
    for _ in range(max_batches):
        manifest = archive_raw_batch(
            db, cloud, dataset, limit=batch_size, bucket=bucket
        )
        if manifest is None:
            break
        batches.append(manifest)
        total_events += manifest["event_count"]
        if manifest["event_count"] < batch_size:
            break
    last_id, last_time, _, rows_synced = _checkpoint(
        db, f"archive:{dataset}"
    )
    return {
        "dataset": dataset,
        "batches": len(batches),
        "events_archived_this_run": total_events,
        "events_archived_total": rows_synced,
        "last_source_id": last_id,
        "last_source_time": last_time,
        "caught_up": len(batches) == 0 or batches[-1]["event_count"] < batch_size,
    }


def archive_raw_window(db, cloud, dataset, start, end, bucket=RAW_BUCKET):
    """Upload one deterministic raw window and then record its manifest."""
    rows = _archive_rows(db, dataset, start, end)
    if not rows:
        return None
    raw, compressed, digest = build_archive(dataset, rows)
    source, object_path = archive_object_path(dataset, start, end)
    cloud.upload_bytes(bucket, object_path, compressed, "application/gzip")
    verification = cloud.verify_object(
        bucket, object_path, digest, len(compressed)
    )
    manifest = {
        "source": source,
        "market_id": None,
        "started_at": start,
        "ended_at": end,
        "bucket": bucket,
        "object_path": object_path,
        "compression": "gzip",
        "content_type": "application/jsonl",
        "sha256": digest,
        "event_count": len(rows),
        "uncompressed_bytes": len(raw),
        "compressed_bytes": len(compressed),
        "verified_at": verification["verified_at"],
        "metadata": {
            "dataset": dataset,
            "format": "jsonl",
            "gzip_mtime": 0,
            "verification": "authenticated_readback_sha256",
        },
    }
    cloud.upsert("raw_archives", [manifest], "bucket,object_path")
    return manifest


def open_local(path):
    db = sqlite3.connect(Path(path))
    return db
