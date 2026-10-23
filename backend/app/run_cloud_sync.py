"""Run Phase 1.75 Supabase structured sync and raw archive jobs."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path

from cloud_memory import (
    CloudConfig,
    SupabaseHTTP,
    archive_raw_backfill,
    archive_raw_window,
    open_local,
    sync_structured_once,
)


def load_local_env():
    path = Path(__file__).resolve().parents[2] / ".env"
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        os.environ.setdefault(name, value)


def _utc(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("archive timestamps must include a timezone")
    return dt.astimezone(timezone.utc).isoformat()


def run_structured(db, cloud, batch_size, backfill):
    total = {}
    while True:
        current = sync_structured_once(db, cloud, batch_size)
        for key, value in current.items():
            total[key] = total.get(key, 0) + value
        print("structured batch:", current, flush=True)
        if not backfill or not any(current.values()):
            return total


def main():
    load_local_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=os.getenv("SQLITE_DB_PATH", "data/btc_intelligence.db"))
    sub = parser.add_subparsers(dest="command", required=True)

    structured = sub.add_parser("structured", help="Sync structured SQLite history to Postgres")
    structured.add_argument("--backfill", action="store_true",
                            help="Continue bounded batches until all current structured rows are copied")
    structured.add_argument("--batch-size", type=int)

    archive = sub.add_parser("archive", help="Archive one raw time window to Supabase Storage")
    archive.add_argument("--dataset", choices=("observations", "stream_events"), required=True)
    archive.add_argument("--start", required=True, help="Inclusive ISO-8601 timestamp")
    archive.add_argument("--end", required=True, help="Exclusive ISO-8601 timestamp")
    archive.add_argument("--bucket", default=os.getenv("SUPABASE_RAW_BUCKET", "market-raw"))

    raw_backfill = sub.add_parser(
        "raw-backfill",
        help="Archive raw evidence in resumable source-ID batches without deleting local rows",
    )
    raw_backfill.add_argument(
        "--dataset", choices=("observations", "stream_events"), required=True
    )
    raw_backfill.add_argument("--batch-size", type=int, default=5000)
    raw_backfill.add_argument("--max-batches", type=int, default=24)
    raw_backfill.add_argument(
        "--bucket", default=os.getenv("SUPABASE_RAW_BUCKET", "market-raw")
    )

    args = parser.parse_args()
    config = CloudConfig.from_env(require_enabled=True)
    cloud = SupabaseHTTP(config)
    db = open_local(args.db)
    try:
        if args.command == "structured":
            batch_size = args.batch_size or config.batch_size
            if not 1 <= batch_size <= 1000:
                parser.error("batch size must be 1..1000")
            print("structured total:", run_structured(db, cloud, batch_size, args.backfill), flush=True)
        elif args.command == "archive":
            start, end = _utc(args.start), _utc(args.end)
            if start >= end:
                parser.error("archive start must be before end")
            result = archive_raw_window(
                db, cloud, args.dataset, start, end, bucket=args.bucket
            )
            print("archive:", result or "no rows in window", flush=True)
        else:
            if not 1 <= args.batch_size <= 50000:
                parser.error("raw batch size must be 1..50000")
            if not 1 <= args.max_batches <= 10000:
                parser.error("max batches must be 1..10000")
            result = archive_raw_backfill(
                db,
                cloud,
                args.dataset,
                max_batches=args.max_batches,
                batch_size=args.batch_size,
                bucket=args.bucket,
            )
            print("raw backfill:", result, flush=True)
    finally:
        db.close()
        cloud.close()


if __name__ == "__main__":
    main()
