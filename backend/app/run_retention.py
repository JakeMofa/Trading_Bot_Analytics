"""Verified local retention CLI. Dry-run is the default; apply needs two opt-ins."""
import argparse
from datetime import datetime, timezone
import json
import os
import sqlite3

from cloud_memory import CloudConfig, SupabaseHTTP
from retention import (
    RetentionConfig,
    RetentionError,
    apply_retention,
    fetch_verified_manifests,
    local_status,
    plan_retention,
    public_report,
)
from run_cloud_sync import load_local_env


def open_readonly(path):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    db.execute("PRAGMA query_only=ON")
    return db


def open_writable(path):
    db = sqlite3.connect(path, timeout=60)
    db.execute("PRAGMA busy_timeout=60000")
    return db


def main():
    load_local_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=os.getenv("SQLITE_DB_PATH", "data/btc_intelligence.db"))
    parser.add_argument("--hours", type=int, help="Override LOCAL_RAW_RETENTION_HOURS")
    parser.add_argument("--batch-size", type=int, help="Override RETENTION_DELETE_BATCH_SIZE")
    parser.add_argument("--bucket", default=os.getenv("SUPABASE_RAW_BUCKET", "market-raw"))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="Local-only retention state; no cloud access, no writes")
    sub.add_parser("dry-run", help="Report what would be deleted; performs no writes")
    apply = sub.add_parser("apply", help="Delete verified-archived rows past the cutoff")
    apply.add_argument("--confirm", action="store_true",
                       help="Required acknowledgement; also needs ENABLE_LOCAL_RETENTION=true")
    args = parser.parse_args()

    try:
        base = RetentionConfig.from_env()
        config = RetentionConfig.build(
            base.enabled, args.hours or base.hours, args.batch_size or base.batch_size)
        if args.command == "status":
            db = open_readonly(args.db)
            try:
                print(json.dumps(local_status(db, config), indent=2))
            finally:
                db.close()
            return
        if args.command == "apply" and not (args.confirm and config.enabled):
            raise RetentionError(
                "apply needs --confirm and ENABLE_LOCAL_RETENTION=true; nothing was deleted")
        cloud = SupabaseHTTP(CloudConfig.from_env(require_enabled=True))
        try:
            manifests = fetch_verified_manifests(cloud, args.bucket)
        finally:
            cloud.close()
        now = datetime.now(timezone.utc)
        if args.command == "dry-run":
            db = open_readonly(args.db)
            try:
                plan = plan_retention(db, manifests, config, now, args.bucket)
            finally:
                db.close()
            print(json.dumps(public_report(plan), indent=2))
            return
        db = open_writable(args.db)
        try:
            plan = plan_retention(db, manifests, config, now, args.bucket)
            print(json.dumps(public_report(plan), indent=2), flush=True)
            result = apply_retention(db, plan, config, confirm=True)
        finally:
            db.close()
        print(json.dumps(result, indent=2))
    except RetentionError as exc:
        raise SystemExit(f"retention refused: {exc}")


if __name__ == "__main__":
    main()
