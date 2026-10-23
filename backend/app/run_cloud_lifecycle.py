"""Cloud lifecycle worker CLI: structured sync, raw archive and verified retention."""
import argparse
import json
import os
import signal
import threading

from cloud_lifecycle import (
    LifecycleConfig,
    LifecycleError,
    LifecycleWorker,
    lifecycle_lock,
    read_lifecycle_status,
)
from cloud_memory import CloudConfig, SupabaseHTTP
from retention import RetentionConfig, RetentionError
from run_cloud_sync import load_local_env


def build_worker(db_path, should_stop=None):
    config = LifecycleConfig.from_env()
    config.require_enabled(
        os.getenv("ENABLE_SUPABASE_SYNC", "false").strip().lower() in ("1", "true", "yes", "on"))
    retention = RetentionConfig.from_env()
    bucket = os.getenv("SUPABASE_RAW_BUCKET", "market-raw")
    return LifecycleWorker(
        db_path, config, retention,
        cloud_factory=lambda: SupabaseHTTP(CloudConfig.from_env(require_enabled=True)),
        bucket=bucket, should_stop=should_stop)


def main():
    load_local_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=os.getenv("SQLITE_DB_PATH", "data/btc_intelligence.db"))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="Read-only local lifecycle state; no Supabase needed")
    sub.add_parser("once", help="Run one bounded cycle of every stage, then exit")
    sub.add_parser("run", help="Run continuously until SIGTERM or SIGINT")
    args = parser.parse_args()

    if args.command == "status":
        print(json.dumps(read_lifecycle_status(args.db), indent=2))
        return
    stop = threading.Event()
    try:
        worker = build_worker(args.db, should_stop=stop.is_set)
        with lifecycle_lock(args.db):
            if args.command == "once":
                result = worker.run_cycle(force=True)
                print(json.dumps(result, indent=2))
                if result["errors"]:
                    raise SystemExit(1)
                return
            for sig in (signal.SIGTERM, signal.SIGINT):
                signal.signal(sig, lambda *_: stop.set())
            worker.run_forever(stop)
    except (LifecycleError, RetentionError) as exc:
        raise SystemExit(f"cloud lifecycle refused: {exc}")


if __name__ == "__main__":
    main()
