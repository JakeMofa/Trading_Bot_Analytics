"""Cloud lifecycle worker CLI: structured sync, raw archive and verified retention."""
import argparse
import json
import os
import signal
import threading
from pathlib import Path
from datetime import datetime, timezone

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
    from storage_runtime import configured_runtime
    runtime = configured_runtime()
    if not runtime:
        return LifecycleWorker(
            db_path, config, retention,
            cloud_factory=lambda: SupabaseHTTP(CloudConfig.from_env(require_enabled=True)),
            bucket=bucket, should_stop=should_stop)
    if Path(db_path).resolve()!=runtime.legacy.resolve():
        raise LifecycleError('A/B lifecycle legacy path mismatch')
    runtime.open('lifecycle')
    from dataclasses import replace
    from compatible_cloud import CompatibleCloud
    import time
    deadline = [None]

    def cloud_factory():
        deadline[0] = time.monotonic()+30
        return CompatibleCloud(SupabaseHTTP(CloudConfig.from_env(require_enabled=True)),deadline[0])

    def finish():
        if not runtime.retirement:
            return {'status':'disabled'}
        # This is the original archive operation deadline, never reset after
        # an ambiguous request or for the final verification readback.
        if deadline[0] is None or time.monotonic()>=deadline[0]:
            return {'status':'held','reason':'archive operation deadline'}
        cloud = CompatibleCloud(SupabaseHTTP(CloudConfig.from_env(require_enabled=True)),deadline[0])
        try:
            return runtime.retire_verified(cloud,datetime.now(timezone.utc))
        finally:
            cloud.close()

    worker = LifecycleWorker(
        runtime.database,replace(config,raw_batch_size=min(config.raw_batch_size,1000)),retention,
        cloud_factory,bucket=bucket,should_stop=should_stop,
        connection_factory=runtime.connection,after_archive=finish)
    worker.storage_runtime = runtime
    return worker


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
        with lifecycle_lock(worker.db_path):
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
    finally:
        runtime = getattr(locals().get('worker'),'storage_runtime',None)
        if runtime:
            runtime.close()


if __name__ == "__main__":
    main()
