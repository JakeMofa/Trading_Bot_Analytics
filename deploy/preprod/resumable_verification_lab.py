"""Isolated generated-data experiment. No cloud access or partition deletion."""
import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager


class VerificationHold(ValueError):
    """Evidence for a read-only comparison is missing or inconsistent."""


def digest(data):
    return hashlib.sha256(data).hexdigest()


@contextmanager
def locked(db):
    # Serialize the model of the immutable stores and journal for each decision.
    # Production has separate stores and requires independent version guarantees.
    with db:
        db.execute("BEGIN IMMEDIATE")
        yield


def initialize(db):
    db.create_function("lab_sha256", 1, digest, deterministic=True)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS local_payload(
            version TEXT PRIMARY KEY NOT NULL, content BLOB NOT NULL,
            CHECK (version = lab_sha256(content))
        );
        CREATE TABLE IF NOT EXISTS cloud_payload(
            version TEXT PRIMARY KEY NOT NULL, content BLOB NOT NULL,
            CHECK (version = lab_sha256(content))
        );
        CREATE TABLE IF NOT EXISTS local_batch(
            origin TEXT, generation TEXT, batch TEXT, version TEXT NOT NULL,
            PRIMARY KEY(origin,generation,batch)
        );
        CREATE TABLE IF NOT EXISTS cloud_batch(
            origin TEXT, generation TEXT, batch TEXT, version TEXT NOT NULL,
            PRIMARY KEY(origin,generation,batch)
        );
        CREATE TABLE IF NOT EXISTS receipt_v1(
            origin TEXT, generation TEXT, batch TEXT, version TEXT NOT NULL,
            PRIMARY KEY(origin,generation,batch)
        );
        CREATE TABLE IF NOT EXISTS sealed_manifest(
            origin TEXT, generation TEXT, manifest TEXT NOT NULL,
            PRIMARY KEY(origin,generation)
        );
    """)


def stage_batch(db, origin, generation, batch_id, local, archived):
    with locked(db):
        if db.execute("SELECT 1 FROM sealed_manifest WHERE origin=? AND generation=?",
                      (origin, generation)).fetchone():
            raise VerificationHold("generation already sealed")
        for side, data in (("local", local), ("cloud", archived)):
            version = digest(data)
            db.execute(f"INSERT OR IGNORE INTO {side}_payload VALUES (?,?)", (version, data))
            db.execute(f"INSERT INTO {side}_batch VALUES (?,?,?,?)",
                       (origin, generation, batch_id, version))


def inventory(db, table, target):
    return db.execute(f"SELECT batch,version FROM {table} WHERE origin=? AND generation=? "
                      "ORDER BY batch", target).fetchall()


def manifest_hash(target, batches):
    return digest(json.dumps(["lab-v1", *target, batches], separators=(",", ":")).encode())


def seal(db, origin, generation):
    target = (origin, generation)
    with locked(db):
        batches = inventory(db, "local_batch", target)
        if not batches:
            raise VerificationHold("empty generation")
        seal_hash = manifest_hash(target, batches)
        db.execute("INSERT OR IGNORE INTO sealed_manifest VALUES (?,?,?)", (*target, seal_hash))
        if db.execute("SELECT manifest FROM sealed_manifest WHERE origin=? AND generation=?",
                      target).fetchone()[0] != seal_hash:
            raise VerificationHold("local seal changed")
    return seal_hash


def verify_batch(db, origin, generation, batch_id):
    key = (origin, generation, batch_id)
    with locked(db):
        query = " WHERE origin=? AND generation=? AND batch=?"
        local = db.execute("SELECT version FROM local_batch" + query, key).fetchone()
        archived = db.execute("SELECT version FROM cloud_batch" + query, key).fetchone()
        if local is None or archived != local:
            raise VerificationHold("batch version mismatch")
        version = local[0]
        if db.execute("SELECT 1 FROM cloud_payload WHERE version=?", (version,)).fetchone() is None:
            raise VerificationHold("immutable payload missing")
        receipt = db.execute("SELECT version FROM receipt_v1" + query, key).fetchone()
        if receipt == local:
            return False
        source = db.execute("SELECT content FROM local_payload WHERE version=?", (version,)).fetchone()
        archived_bytes = db.execute("SELECT content FROM cloud_payload WHERE version=?",
                                    (version,)).fetchone()
        if source != archived_bytes or digest(archived_bytes[0]) != version:
            raise VerificationHold("payload digest mismatch")
        db.execute("INSERT OR REPLACE INTO receipt_v1 VALUES (?,?,?,?)", (*key, version))
    return True


def coverage(db, target):
    batches = inventory(db, "local_batch", target)
    seal_hash = manifest_hash(target, batches)
    seal_row = db.execute("SELECT manifest FROM sealed_manifest WHERE origin=? AND generation=?",
                          target).fetchone()
    if not batches or seal_row != (seal_hash,):
        raise VerificationHold("sealed local inventory mismatch")
    if inventory(db, "cloud_batch", target) != batches:
        raise VerificationHold("current archive differs from seal")
    missing = db.execute("""
        SELECT 1 FROM cloud_batch c LEFT JOIN cloud_payload p ON p.version=c.version
        LEFT JOIN local_payload l ON l.version=c.version
        WHERE c.origin=? AND c.generation=? AND (p.version IS NULL OR l.version IS NULL) LIMIT 1
    """, target).fetchone()
    if missing:
        raise VerificationHold("immutable payload missing")
    receipts = set(inventory(db, "receipt_v1", target))
    return seal_hash, len(batches), [key for key, version in batches if (key, version) not in receipts]


def verify_step(db, origin, generation, limit, *, seconds=None, clock=time.monotonic):
    if type(limit) is not int or limit < 1:
        raise ValueError("positive batch budget required")
    if seconds is not None and not seconds > 0:
        raise ValueError("positive time budget required")
    deadline = float("inf") if seconds is None else clock() + seconds
    target = (origin, generation)
    with locked(db):
        _, _, pending = coverage(db, target)
    verified_now = 0
    for key in pending[:limit]:
        if clock() >= deadline:
            break
        verified_now += int(verify_batch(db, *target, key))
    with locked(db):
        seal_hash, total, pending = coverage(db, target)
        # A budget that expired during the final read/reconciliation cannot pass.
        expired = clock() >= deadline
        return dict(status="paused" if pending or expired else "complete", verified_now=verified_now,
                    reused=total-len(pending)-verified_now, total=total,
                    seal_sha256=seal_hash, retirement_authorized=False)


if __name__ == "__main__":
    with sqlite3.connect(":memory:") as db:
        initialize(db)
        for i in range(56):
            payload = json.dumps({"page": i}).encode()
            stage_batch(db, "generated", "B", f"page-{i:02}", payload, payload)
        seal(db, "generated", "B")
        for limit in (54, 2):
            print(json.dumps(verify_step(db, "generated", "B", limit)))
