"""Offline PG17 protocol qualification. No deployment, permit or deletion entry point."""

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hmac
import re
import uuid
from time import monotonic

from postgres.archive_codec import ArchiveIntegrityError, ArchiveLimit, encoded, sha256
from postgres.lifecycle import LifecycleHold

INITIAL = "00" * 32
LEASE_SECONDS = 6
MAX_BYTES = 256 * 1024
HOLDER = "generated-long-window-shadow"


def extend(chain, ordinal, kind, data):
    return sha256(encoded([chain, ordinal, kind, sha256(data)]))


@dataclass(frozen=True)
class Inventory:
    origin: str
    sealed: str
    successor: str
    seal_hash: str
    raw_rows: int
    pages: int
    digest: str
    source_version: int
    archive_version: int
    archive_id: str
    policy_epoch: str
    reader: str
    expires: datetime

    def validate(self):
        if (
            not self.origin.startswith("generated-shadow-")
            or self.sealed == self.successor
            or any(str(uuid.UUID(x)) != x for x in (self.sealed, self.successor, self.archive_id))
            or not all(
                re.fullmatch("[0-9a-f]{64}", x) for x in (self.seal_hash, self.digest, self.policy_epoch)
            )
            or self.raw_rows < 1
            or self.pages < 1
            or self.reader != "shadow_page_reader"
            or self.expires.tzinfo is None
            or self.expires <= datetime.now(timezone.utc)
        ):
            raise LifecycleHold("unavailable or expired offline inventory")

    @property
    def scope(self):
        return sha256(encoded(asdict(self)))


def sign(key, scope, ordinal, chain):
    return hmac.digest(key, encoded([scope, ordinal, chain]), "sha256").hex()


def limits(db, readonly):
    endpoint = Path(db.info.host).resolve()
    if (
        endpoint.name != "socket"
        or not endpoint.parent.name.startswith("initial-trial-seal-")
        or endpoint.parent.parent != Path("/tmp").resolve()
        or db.info.dbname not in ("tradebot_pp", "tradebot_shadow_archive")
    ):
        raise LifecycleHold("disposable PostgreSQL qualification socket required")
    if readonly:
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
    db.execute("SET LOCAL statement_timeout='1200ms'")
    db.execute("SET LOCAL lock_timeout='75ms'")


def generation(db, target, *, lock=False):
    predicate = """SELECT g.state,g.seal_hash,g.seal_count,clock_timestamp()<%s AS fresh
        FROM archive.generations g JOIN archive.generations active
          ON active.origin_id=g.origin_id AND active.generation_id=%s
          AND active.state='collecting' AND active.slot<>g.slot
        JOIN ops.writer_state w ON w.origin_id=g.origin_id AND w.generation_id=active.generation_id
        WHERE g.origin_id=%s AND g.generation_id=%s
          AND EXISTS (SELECT FROM pg_inherits i JOIN pg_class c ON c.oid=i.inhrelid
              WHERE i.inhparent='raw.events'::regclass AND c.relnamespace='raw'::regnamespace
                AND c.relname=g.partition_name
                AND pg_get_expr(c.relpartbound,c.oid)=format('FOR VALUES IN (%%L)',g.generation_id))"""
    row = db.execute(
        predicate + (" FOR UPDATE OF g NOWAIT" if lock else ""),
        (target.expires, target.successor, target.origin, target.sealed),
    ).fetchone()
    if not row or (row["state"], row["seal_hash"], row["seal_count"], row["fresh"]) != (
        "verified",
        target.seal_hash,
        target.raw_rows,
        True,
    ):
        raise LifecycleHold("sealed origin, inventory, successor or expiry changed")


@contextmanager
def page_lease(factory, target):
    identity = str(uuid.uuid4())
    with factory() as db, db.transaction():
        limits(db, False)
        # Exact scoped row lock and FK insert serialize admission with retirement.
        # Release it before querying a page or touching the remote destination.
        generation(db, target, lock=True)
        db.execute(
            """INSERT INTO archive.reader_leases(lease_id,origin_id,generation_id,holder,expires_at)
            VALUES(%s,%s,%s,%s,clock_timestamp()+%s)""",
            (identity, target.origin, target.sealed, HOLDER, timedelta(seconds=LEASE_SECONDS)),
        )
    try:
        yield identity
    finally:
        with factory() as db, db.transaction():
            limits(db, False)
            db.execute(
                """DELETE FROM archive.reader_leases WHERE lease_id=%s AND origin_id=%s
                AND generation_id=%s AND holder=%s""",
                (identity, target.origin, target.sealed, HOLDER),
            )


def live_lease(db, target, lease):
    if not db.execute(
        """SELECT 1 AS present FROM archive.reader_leases WHERE lease_id=%s AND origin_id=%s
            AND generation_id=%s AND holder=%s AND expires_at>clock_timestamp()""",
        (lease, target.origin, target.sealed, HOLDER),
    ).fetchone():
        raise LifecycleHold("page reader lease expired")


def header(db, target, remote=False):
    row = db.execute(
        """SELECT version,pages,digest,archive_id::text,policy_epoch,
            current_database() AS db,session_user AS login,current_user AS role,
            has_table_privilege(current_user,'qualification.pages','SELECT') AS readable,
            (has_table_privilege(current_user,'qualification.pages','INSERT,UPDATE,DELETE,TRUNCATE')
             OR has_table_privilege(current_user,'qualification.inventory','INSERT,UPDATE,DELETE,TRUNCATE')) AS mutable
        FROM qualification.inventory WHERE origin=%s AND generation=%s""",
        (target.origin, target.sealed),
    ).fetchone()
    if not row or (
        row["version"],
        row["pages"],
        row["digest"],
        row["archive_id"],
        row["policy_epoch"],
    ) != (
        target.archive_version if remote else target.source_version,
        target.pages,
        target.digest,
        target.archive_id,
        target.policy_epoch,
    ):
        raise ArchiveIntegrityError("source or archive inventory version or policy epoch changed")
    if remote and (row["db"], row["login"], row["role"], row["readable"], row["mutable"]) != (
        "tradebot_shadow_archive",
        target.reader,
        target.reader,
        True,
        False,
    ):
        raise LifecycleHold("archive reader identity or privileges changed")


def page(db, target, ordinal):
    row = db.execute(
        """SELECT kind,CASE WHEN octet_length(bytes)<=%s THEN bytes END AS bytes
        FROM qualification.pages WHERE origin=%s AND generation=%s AND ordinal=%s""",
        (MAX_BYTES, target.origin, target.sealed, ordinal),
    ).fetchone()
    if not row or row["kind"] not in ("raw", "structured") or row["bytes"] is None:
        raise ArchiveIntegrityError("missing or oversized inventory page")
    return row["kind"], bytes(row["bytes"])


def read_pair(source, archive, target, ordinal, lease):
    with source() as db, db.transaction():
        limits(db, True)
        generation(db, target)
        live_lease(db, target, lease)
        header(db, target)
        local = page(db, target, ordinal)
    with archive() as db, db.transaction():
        limits(db, True)
        header(db, target, remote=True)
        if local != page(db, target, ordinal):
            raise ArchiveIntegrityError("authenticated archive bytes differ")
    return local


def progress(db, target, key):
    row = db.execute(
        "SELECT ordinal,chain,proof FROM qualification.progress WHERE scope=%s", (target.scope,)
    ).fetchone()
    if row is None:
        return 0, INITIAL
    n, chain = row["ordinal"], row["chain"]
    if (
        not 0 <= n <= target.pages
        or not re.fullmatch("[0-9a-f]{64}", chain)
        or not hmac.compare_digest(row["proof"], sign(key, target.scope, n, chain))
    ):
        raise ArchiveIntegrityError("invalid signed verification cursor")
    return n, chain


def checkpoint(db, target, key, old, new):
    n, chain = new
    prior, prior_chain = old
    row = db.execute(
        """INSERT INTO qualification.progress AS p(scope,ordinal,chain,proof)
        VALUES(%s,%s,%s,%s) ON CONFLICT(scope) DO UPDATE SET
        ordinal=EXCLUDED.ordinal,chain=EXCLUDED.chain,proof=EXCLUDED.proof
        WHERE p.ordinal=%s AND p.proof=%s RETURNING ordinal""",
        (
            target.scope,
            n,
            chain,
            sign(key, target.scope, n, chain),
            prior,
            sign(key, target.scope, prior, prior_chain),
        ),
    ).fetchone()
    if not row:
        raise LifecycleHold("concurrent verification advanced journal")


def verify(source, archive, journal, target, *, key, max_pages=16, seconds=20):
    """One bounded invocation. All factories supply private disposable PG17 sockets."""
    target.validate()
    if (
        not isinstance(key, bytes)
        or len(key) < 32
        or type(max_pages) is not int
        or not 1 <= max_pages <= 64
        or not 0 < seconds <= 60
    ):
        raise LifecycleHold("invalid offline verification budget")
    end = monotonic() + seconds
    with journal() as db, db.transaction():
        limits(db, False)
        n, chain = progress(db, target, key)
    initial = n
    for ordinal in range(n + 1, min(n + max_pages, target.pages) + 1):
        if monotonic() >= end:
            raise ArchiveLimit("verification invocation timed out")
        with page_lease(journal, target) as lease:
            kind, data = read_pair(source, archive, target, ordinal, lease)
            next_chain = extend(chain, ordinal, kind, data)
            with journal() as db, db.transaction():
                limits(db, False)
                generation(db, target)
                live_lease(db, target, lease)
                header(db, target)
                if monotonic() >= end:
                    raise ArchiveLimit("verification invocation timed out")
                checkpoint(db, target, key, (n, chain), (ordinal, next_chain))
            n, chain = ordinal, next_chain
    if n == target.pages:
        if not hmac.compare_digest(chain, target.digest):
            raise ArchiveIntegrityError("completed inventory fingerprint differs")
        with page_lease(journal, target) as lease:
            # Fresh authenticated terminal comparison, then a short local lock.
            # Remote privileged change after this check remains possible.
            read_pair(source, archive, target, n, lease)
            with journal() as db, db.transaction():
                limits(db, False)
                generation(db, target, lock=True)
                live_lease(db, target, lease)
                header(db, target)
                if progress(db, target, key) != (n, chain):
                    raise ArchiveIntegrityError("final checkpoint changed")
                if monotonic() >= end:
                    raise ArchiveLimit("verification invocation timed out")
    return dict(
        status="shadow_complete" if n == target.pages else "shadow_paused",
        cursor=n,
        pages_checked=n - initial,
        retirement_authorized=False,
    )
