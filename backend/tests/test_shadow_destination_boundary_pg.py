"""Generated two-database qualification of the last archive read vs local commit."""
from contextlib import ExitStack
import hashlib
import unittest

import psycopg
import test_pp_initial_trial_drain as cluster


class DestinationBoundary(unittest.TestCase):
    admin = cluster.InitialSealNative.__dict__["admin"]
    tearDownClass = cluster.InitialSealNative.__dict__["tearDownClass"]

    @classmethod
    def setUpClass(cls):
        cluster.InitialSealNative.setUpClass.__func__(cls)
        with cls.admin("postgres") as db:
            db.execute("CREATE DATABASE archive_fixture")
            db.execute("CREATE ROLE archive_test_reader")
            db.execute("CREATE ROLE archive_test_writer")
        with cls.admin("archive_fixture") as db:
            db.execute("CREATE TABLE archive_bytes(id integer PRIMARY KEY, data bytea NOT NULL)")
            db.execute("GRANT SELECT ON archive_bytes TO archive_test_reader")
            db.execute("GRANT INSERT ON archive_bytes TO archive_test_writer")

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.local = self.stack.enter_context(self.admin())
        self.owner = self.stack.enter_context(self.admin("archive_fixture"))
        self.reader = self.stack.enter_context(self.admin("archive_fixture"))
        self.reader.execute("SET ROLE archive_test_reader")
        self.owner.execute("GRANT SELECT ON archive_bytes TO archive_test_reader")
        self.owner.execute("TRUNCATE archive_bytes")
        self.owner.execute("INSERT INTO archive_bytes VALUES (1, %s)", (b"sealed",))
        self.local.execute("CREATE TEMP TABLE retained_b(id integer PRIMARY KEY)")
        self.local.execute("INSERT INTO retained_b VALUES (1)")

    def digest(self):
        return hashlib.sha256(self.reader.execute(
            "SELECT data FROM archive_bytes WHERE id=1").fetchone()["data"]).digest()

    def test_authenticated_read_does_not_fence_owner_or_privilege_changes(self):
        for action in ("replace", "revoke"):
            with self.subTest(action=action):
                expected = self.digest()
                with self.local.transaction(force_rollback=True):
                    self.local.execute("DELETE FROM retained_b WHERE id=1")
                    # Deterministic interleaving: PP has checked the bytes and staged
                    # removal; the destination owner acts before local COMMIT.
                    if action == "replace":
                        self.owner.execute("UPDATE archive_bytes SET data=%s WHERE id=1",
                                           (b"changed",))
                        self.assertNotEqual(self.digest(), expected)
                    else:
                        self.owner.execute("REVOKE SELECT ON archive_bytes FROM archive_test_reader")
                        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                            self.digest()
                self.assertEqual(self.local.execute(
                    "SELECT count(*) AS n FROM retained_b").fetchone()["n"], 1)

    def test_insert_only_writer_cannot_replace_or_delete_verified_data(self):
        with self.admin("archive_fixture") as writer:
            writer.execute("SET ROLE archive_test_writer")
            writer.execute("INSERT INTO archive_bytes VALUES (2, %s)", (b"next",))
            for sql in ("UPDATE archive_bytes SET data='modified'", "DELETE FROM archive_bytes"):
                with self.subTest(sql=sql), self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    writer.execute(sql)
        self.assertEqual(self.digest(), hashlib.sha256(b"sealed").digest())
