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
            _cloud_checkpoint(cloud, "markets", source_time=last["last_seen"],
                              source_key=last["id"], rows_synced=len(rows))
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
            cloud.upsert(table, mapped, conflict)
            last_id = rows[-1]["id"]
            _save_checkpoint(db, dataset, source_id=last_id, rows_added=len(rows))
            _cloud_checkpoint(cloud, dataset, source_id=last_id, rows_synced=len(rows))
        result[dataset] = len(rows)

    if _table_exists(db, "candles"):
        rows = _candle_rows(db, batch_size)
        mapped = [_map_candle(row) for row in rows]
        if mapped:
            cloud.upsert("candles", mapped, "source,symbol,granularity,time")
            last_time = rows[-1]["time"]
            _save_checkpoint(db, "candles", source_id=last_time, rows_added=len(rows))
            _cloud_checkpoint(cloud, "candles", source_id=last_time, rows_synced=len(rows))
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


def archive_raw_window(db, cloud, dataset, start, end, bucket=RAW_BUCKET):
    """Upload one deterministic raw window and then record its manifest."""
    rows = _archive_rows(db, dataset, start, end)
    if not rows:
        return None
    raw, compressed, digest = build_archive(dataset, rows)
    source, object_path = archive_object_path(dataset, start, end)
    cloud.upload_bytes(bucket, object_path, compressed, "application/gzip")
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
        "verified_at": None,
        "metadata": {"dataset": dataset, "format": "jsonl", "gzip_mtime": 0},
    }
    cloud.upsert("raw_archives", [manifest], "bucket,object_path")
    return manifest


def open_local(path):
    db = sqlite3.connect(Path(path))
    return db
