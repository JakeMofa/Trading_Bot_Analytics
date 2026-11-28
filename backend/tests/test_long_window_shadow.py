"""Long-window protocol on two disposable PG17 databases; no deploy or removal."""

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import secrets
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "backend/tests"), str(ROOT / "deploy/preprod")]
from postgres.archive_codec import ArchiveIntegrityError, ArchiveLimits, encoded, sha256
from postgres.connection import connect
from postgres.lifecycle import ArchiveWorker, LifecycleHold, LifecycleRepository
from postgres.outbox_packing import envelope
from postgres_lifecycle_fixtures import ImmutableMemoryTransport
import test_pp_initial_trial_drain as native
import test_postgres_lifecycle_integration as lifecycle
from long_window_shadow import Inventory, INITIAL, extend, verify

SCHEMA = """
CREATE SCHEMA qualification;
CREATE TABLE qualification.inventory(
    origin text,generation text,version bigint NOT NULL,pages int NOT NULL,
    digest text NOT NULL,archive_id uuid NOT NULL,policy_epoch text NOT NULL,
    PRIMARY KEY(origin,generation));
CREATE TABLE qualification.pages(
    origin text,generation text,ordinal int,kind text NOT NULL,bytes bytea NOT NULL,
    PRIMARY KEY(origin,generation,ordinal),
    FOREIGN KEY(origin,generation) REFERENCES qualification.inventory(origin,generation));
CREATE FUNCTION qualification.invalidate_inventory() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- Even replacing an already checked page invalidates this version.
    UPDATE qualification.inventory SET version=version+1
        WHERE (origin,generation) IN ((OLD.origin,OLD.generation),(NEW.origin,NEW.generation));
    RETURN NULL;
END $$;
CREATE TRIGGER invalidate_inventory AFTER INSERT OR UPDATE OR DELETE ON qualification.pages
    FOR EACH ROW EXECUTE FUNCTION qualification.invalidate_inventory();
"""
INVALIDATE_SOURCE = """
CREATE FUNCTION qualification.invalidate_source() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    UPDATE qualification.inventory SET version=version+1
        WHERE (origin,generation) IN ((OLD.origin_id,OLD.generation_id),(NEW.origin_id,NEW.generation_id));
    RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION qualification.invalidate_source() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION qualification.invalidate_source() TO tradebot_owner;
"""
JOURNAL = """CREATE TABLE qualification.progress(scope text PRIMARY KEY,ordinal int NOT NULL,
       chain text NOT NULL,proof text NOT NULL)"""


class LongWindowQualification(unittest.TestCase):
    admin = native.InitialSealNative.__dict__["admin"]
    tearDownClass = native.InitialSealNative.__dict__["tearDownClass"]
    insert = lifecycle.PostgreSQLLifecycleIntegration.insert
    remote_name = "tradebot_shadow_archive"

    @classmethod
    def setUpClass(cls):
        native.InitialSealNative.setUpClass.__func__(cls)
        with cls.admin("postgres") as db:
            db.execute("CREATE DATABASE tradebot_shadow_archive")
            db.execute("CREATE ROLE shadow_page_reader LOGIN")
        for database in ("tradebot_pp", cls.remote_name):
            with cls.admin(database) as db:
                db.execute(SCHEMA)
                db.execute("GRANT USAGE ON SCHEMA qualification TO shadow_page_reader")
                db.execute(
                    "GRANT SELECT ON qualification.inventory,qualification.pages TO shadow_page_reader"
                )
                if database == "tradebot_pp":
                    db.execute(JOURNAL)
                    db.execute(INVALIDATE_SOURCE)
                    for relation in ("ops.outbox", "raw.events", "archive.manifests"):
                        db.execute(
                            "CREATE TRIGGER shadow_source_revision AFTER INSERT OR UPDATE OR DELETE ON "
                            + relation
                            + " FOR EACH ROW EXECUTE FUNCTION qualification.invalidate_source()"
                        )
                    db.execute(
                        "GRANT USAGE ON SCHEMA qualification TO tradebot_lifecycle,tradebot_reader"
                    )
                    db.execute(
                        "GRANT SELECT ON qualification.inventory,qualification.pages TO tradebot_lifecycle,tradebot_reader"
                    )
                    db.execute(
                        "GRANT SELECT,INSERT,UPDATE ON qualification.progress TO tradebot_lifecycle"
                    )

    def setUp(self):
        self.key = secrets.token_bytes(32)
        self.origin = "generated-shadow-" + uuid.uuid4().hex
        self.repo = LifecycleRepository(lambda: connect(self.lifecycle_dsn))
        self.app_factory = lambda: connect(self.app_dsn)
        a = self.repo.bootstrap(self.origin, datetime.now(timezone.utc) - timedelta(hours=73))[
            "generation_id"
        ]
        self.insert(1)
        with self.app_factory() as db:
            db.execute(
                """INSERT INTO ops.outbox
                (origin_id,generation_id,entity_type,entity_id,content_hash,payload,created_at)
                SELECT %s,%s,'fixture',n::text,repeat('1',64),jsonb_build_object('n',n),now()
                FROM generate_series(1,194) n""",
                (self.origin, a),
            )
        b = self.repo.switch_if_due(self.origin)["generation_id"]
        fixture = ImmutableMemoryTransport()
        self.assertEqual(
            ArchiveWorker(self.repo, fixture, ArchiveLimits()).archive_cycle(a)["status"], "archived"
        )
        gen = self.repo.generation(a)
        # Build this fixture's sealed compilation from the real retained outbox
        # and the raw manifest object. Its mutable admin surface models version
        # invalidation. No hosted service promises this aggregate seal today.
        entries = [("raw", next(iter(fixture.objects.values())))]
        with self.admin() as db:
            rows = db.execute(
                "SELECT * FROM ops.outbox WHERE origin_id=%s AND generation_id=%s ORDER BY id",
                (self.origin, a),
            ).fetchall()
            self.assertTrue(all(row["acknowledged_at"] is not None for row in rows))
        entries.extend(("structured", encoded([envelope(r)])) for r in rows)
        digest = INITIAL
        for n, (k, data) in enumerate(entries, 1):
            digest = extend(digest, n, k, data)
        aid = str(uuid.uuid4())
        epoch = sha256(encoded(["fixture authorized reader", aid]))
        for database in ("tradebot_pp", self.remote_name):
            with self.admin(database) as db, db.transaction():
                db.execute(
                    "INSERT INTO qualification.inventory VALUES(%s,%s,0,%s,%s,%s,%s)",
                    (self.origin, a, len(entries), digest, aid, epoch),
                )
                db.cursor().executemany(
                    "INSERT INTO qualification.pages VALUES(%s,%s,%s,%s,%s)",
                    [(self.origin, a, n, k, data) for n, (k, data) in enumerate(entries, 1)],
                )
        self.target = Inventory(
            self.origin,
            a,
            b,
            gen["seal_hash"],
            gen["seal_count"],
            len(entries),
            digest,
            len(entries),
            len(entries),
            aid,
            epoch,
            "shadow_page_reader",
            datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        self.source = lambda: self.db("tradebot_reader", "tradebot_pp")
        self.archive = lambda: self.db("shadow_page_reader", self.remote_name)
        self.journal = lambda: self.db("tradebot_lifecycle", "tradebot_pp")

    def db(self, user, database):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(
            host=str(self.socket), user=user, dbname=database, row_factory=dict_row, autocommit=True
        )

    def read(self, budget, **options):
        return verify(
            self.source,
            options.pop("archive", self.archive),
            self.journal,
            options.pop("target", self.target),
            key=self.key,
            max_pages=budget,
            **options,
        )

    def test_195_pages_resume_concurrent_successor_and_no_long_partition_lock(self):
        reads = []

        @contextmanager
        def observe():
            if not reads:
                # The page lease is durable, but no local row lock spans the
                # authenticated destination read. A separate successor commits.
                self.insert(2)
                with self.admin() as db, db.transaction():
                    row = db.execute(
                        """SELECT count(*) AS n FROM archive.reader_leases WHERE origin_id=%s
                      AND generation_id=%s AND expires_at>clock_timestamp()""",
                        (self.origin, self.target.sealed),
                    ).fetchone()
                    self.assertEqual(row["n"], 1)
                    db.execute(
                        "SELECT FROM archive.generations WHERE origin_id=%s AND generation_id=%s FOR UPDATE NOWAIT",
                        (self.origin, self.target.sealed),
                    )
            with self.archive() as db:
                reads.append(db.info.backend_pid)
                yield db

        snapshots = []
        for batch in (54, 64, 64, 13):
            snapshots.append(self.read(batch, archive=observe))
        self.assertEqual([r["cursor"] for r in snapshots], [54, 118, 182, 195])
        self.assertEqual([r["pages_checked"] for r in snapshots], [54, 64, 64, 13])
        self.assertEqual([r["status"] for r in snapshots], ["shadow_paused"] * 3 + ["shadow_complete"])
        self.assertFalse(any(r["retirement_authorized"] for r in snapshots))
        self.assertEqual(len(reads), 196)  # one authenticated read per page and a fresh terminal reread
        self.assertEqual(len(set(reads)), 196)
        with self.admin() as db:
            for g in (self.target.sealed, self.target.successor):
                self.assertEqual(
                    db.execute(
                        "SELECT count(*) AS n FROM raw.events WHERE generation_id=%s", (g,)
                    ).fetchone()["n"],
                    1,
                )
            self.assertEqual(
                db.execute(
                    "SELECT count(*) AS n FROM archive.reader_leases WHERE origin_id=%s", (self.origin,)
                ).fetchone()["n"],
                0,
            )
        self.assertEqual(self.read(1)["pages_checked"], 0)

        with self.admin(self.remote_name) as owner:
            owner.execute("REVOKE SELECT ON qualification.pages FROM shadow_page_reader")
            try:
                with self.assertRaisesRegex(LifecycleHold, "privileges"):
                    self.read(1)
            finally:
                owner.execute("GRANT SELECT ON qualification.pages TO shadow_page_reader")

    def test_interrupted_page_keeps_previous_cursor_and_releases_lease(self):
        from unittest.mock import patch
        import long_window_shadow as protocol

        self.assertEqual(self.read(2)["cursor"], 2)
        durable = protocol.checkpoint

        def crash_after_staging(*args):
            durable(*args)
            raise RuntimeError("fixture process interrupted before commit")

        with patch.object(protocol, "checkpoint", crash_after_staging):
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                self.read(1)
        with self.admin() as db:
            self.assertEqual(
                db.execute(
                    "SELECT ordinal FROM qualification.progress WHERE scope=%s", (self.target.scope,)
                ).fetchone()["ordinal"],
                2,
            )
            self.assertEqual(
                db.execute(
                    "SELECT count(*) AS n FROM archive.reader_leases WHERE origin_id=%s", (self.origin,)
                ).fetchone()["n"],
                0,
            )
        self.assertEqual(self.read(1)["cursor"], 3)

    def test_rejects_early_page_replacement_origin_expiry_tampered_cursor_and_revocation(self):
        import psycopg

        self.assertEqual(self.read(2)["cursor"], 2)
        with self.admin() as db, db.transaction():
            db.execute(
                "SELECT FROM archive.generations WHERE generation_id=%s FOR UPDATE", (self.target.sealed,)
            )
            with self.assertRaisesRegex(LifecycleHold, "sealed origin"):
                self.read(1, target=replace(self.target, origin="generated-shadow-other"))
        with self.assertRaisesRegex(LifecycleHold, "expired"):
            self.read(
                1, target=replace(self.target, expires=datetime.now(timezone.utc) - timedelta(seconds=1))
            )
        with self.admin(self.remote_name) as db:
            db.execute("GRANT UPDATE ON qualification.pages TO shadow_page_reader")
            try:
                with self.assertRaisesRegex(LifecycleHold, "privileges"):
                    self.read(1)
            finally:
                db.execute("REVOKE UPDATE ON qualification.pages FROM shadow_page_reader")
            db.execute("REVOKE SELECT ON qualification.pages FROM shadow_page_reader")
            try:
                with self.assertRaises((LifecycleHold, psycopg.errors.InsufficientPrivilege)):
                    self.read(1)
            finally:
                db.execute("GRANT SELECT ON qualification.pages TO shadow_page_reader")
        with self.admin() as db:
            row = db.execute(
                "SELECT proof FROM qualification.progress WHERE scope=%s", (self.target.scope,)
            ).fetchone()
            db.execute(
                "UPDATE qualification.progress SET proof=%s WHERE scope=%s", ("0" * 64, self.target.scope)
            )
            with self.assertRaisesRegex(ArchiveIntegrityError, "signed"):
                self.read(1)
            db.execute(
                "UPDATE qualification.progress SET proof=%s WHERE scope=%s",
                (row["proof"], self.target.scope),
            )
            db.execute(
                "UPDATE qualification.inventory SET digest=%s WHERE origin=%s", ("9" * 64, self.origin)
            )
            with self.assertRaisesRegex(ArchiveIntegrityError, "inventory"):
                self.read(1)
            db.execute(
                "UPDATE qualification.inventory SET digest=%s WHERE origin=%s",
                (self.target.digest, self.origin),
            )
        with self.admin() as db:
            db.execute(
                "UPDATE ops.outbox SET payload=payload||'{\"test_change\":true}'::jsonb WHERE id=(SELECT min(id) FROM ops.outbox WHERE origin_id=%s)",
                (self.origin,),
            )
            with self.assertRaisesRegex(ArchiveIntegrityError, "version"):
                self.read(1)
            # Restore the source pin only inside this disposable negative test
            # so the independent destination-version rejection can be exercised.
            db.execute(
                "UPDATE qualification.inventory SET version=%s WHERE origin=%s",
                (self.target.source_version, self.origin),
            )
        with self.admin(self.remote_name) as db:
            db.execute(
                "UPDATE qualification.pages SET bytes='changed' WHERE origin=%s AND ordinal=1",
                (self.origin,),
            )
            with self.assertRaisesRegex(ArchiveIntegrityError, "version"):
                self.read(1)
        self.assertEqual(self.repo.generation(self.target.sealed)["state"], "verified")
