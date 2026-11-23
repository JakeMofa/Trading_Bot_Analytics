"""Exercise incremental verification and sealed catch-up on synthetic local data."""
import argparse
import json
import sqlite3
import struct
import tempfile
from contextlib import closing
from pathlib import Path
from time import monotonic

from deploy.preprod.resumable_verification_lab import (
    initialize, seal, stage_batch, verify_batch, verify_step,
)


def simulate(row_count, page_size=500):
    if row_count < 1 or page_size < 1:
        raise ValueError("row_count and page_size must be positive")
    origin = "synthetic-pp"
    generation = "scale-A"
    started = monotonic()
    staged = 0
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "archive.db"
        with closing(sqlite3.connect(path)) as db:
            initialize(db)
            for first in range(0, row_count, page_size):
                end = min(row_count, first + page_size)
                # Ordered IDs and exact integer ticks give each batch distinct bytes.
                data = b"".join(struct.pack(">QQ", i, i % 10001) for i in range(first, end))
                for kind in ("structured", "raw"):
                    batch_id = f"{kind}-{first:012d}"
                    payload = kind.encode() + data
                    stage_batch(db, origin, generation, batch_id, payload, payload)
                    if end < row_count:
                        verify_batch(db, origin, generation, batch_id)
                    staged += 1
            sealing_started = monotonic()
            seal(db, origin, generation)
        with closing(sqlite3.connect(path)) as db:
            result = verify_step(db, origin, generation, limit=2, seconds=240)
        finished = monotonic()
        if (result["status"], result["verified_now"], result["reused"], result["total"]) != (
            "complete", 2, staged - 2, staged
        ):
            raise RuntimeError(f"Unexpected seal reconciliation: {result}")
    return {
        "scope": "Local synthetic row-count exercise with compact 16-byte records, one raw batch per page",
        "structured_rows": row_count, "page_size": page_size, "total_batches": staged,
        "preverified_batches": staged - 2, "verified_after_seal": 2,
        "seal_to_finish_seconds": round(finished - sealing_started, 4),
        "staging_and_incremental_verification_seconds": round(sealing_started - started, 4),
        "result": result,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=72 * 3600 * 14)
    print(json.dumps(simulate(parser.parse_args().rows), indent=2))
