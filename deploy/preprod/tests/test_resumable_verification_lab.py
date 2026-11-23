import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from deploy.preprod import resumable_verification_lab as lab


class ResumeLabTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "generated.sqlite3"
        self.connect()
        self.addCleanup(lambda: self.db.close())
        self.target = ("fixture", "B")

    def connect(self):
        self.db = sqlite3.connect(self.path)
        lab.initialize(self.db)

    def stage(self, i):
        content = f"generated payload {i}".encode()
        lab.stage_batch(self.db, *self.target, f"page-{i:03}", content, content)

    def fixture(self):
        for i in range(56):
            self.stage(i)
        return lab.seal(self.db, *self.target)

    def test_stopped_after_54_and_reopened_matches_uninterrupted(self):
        self.fixture()
        uninterrupted = lab.verify_step(self.db, *self.target, 56)
        with self.db:
            self.db.execute("DELETE FROM receipt_v1")
        self.assertEqual(lab.verify_step(self.db, *self.target, 54)["status"], "paused")
        self.db.close()
        self.connect()
        done = lab.verify_step(self.db, *self.target, 2)
        self.assertEqual((done["status"], done["reused"], done["verified_now"]), ("complete", 54, 2))
        self.assertEqual(done["seal_sha256"], uninterrupted["seal_sha256"])
        self.assertFalse(done["retirement_authorized"])

    def test_elapsed_budget_after_last_batch_requires_new_reconciliation(self):
        self.stage(0)
        lab.seal(self.db, *self.target)
        clock = iter([0, 1, 5]).__next__
        result = lab.verify_step(self.db, *self.target, 1, seconds=5, clock=clock)
        self.assertEqual((result["status"], result["verified_now"]), ("paused", 1))
        done = lab.verify_step(self.db, *self.target, 1)
        self.assertEqual((done["status"], done["reused"]), ("complete", 1))

    def test_killed_process_keeps_committed_pages_only(self):
        self.fixture()
        child = """
import os, sqlite3, sys
from deploy.preprod import resumable_verification_lab as lab
db = sqlite3.connect(sys.argv[1])
lab.initialize(db)
lab.verify_step(db, 'fixture', 'B', 54)
db.execute("BEGIN IMMEDIATE")
db.execute("DELETE FROM receipt_v1")
os._exit(17)
"""
        result = subprocess.run([sys.executable, "-c", child, str(self.path)],
                                cwd=Path(__file__).resolve().parents[3], timeout=30)
        self.assertEqual(result.returncode, 17)
        resumed = lab.verify_step(self.db, *self.target, 2)
        self.assertEqual((resumed["status"], resumed["reused"], resumed["verified_now"]),
                         ("complete", 54, 2))

    def test_changed_or_missing_previously_verified_version_blocks_resume(self):
        self.fixture()
        lab.verify_step(self.db, *self.target, 54)
        with self.db:
            self.db.execute("UPDATE cloud_batch SET version='new-version' WHERE batch='page-000'")
        with self.assertRaisesRegex(lab.VerificationHold, "archive differs"):
            lab.verify_step(self.db, *self.target, 56)
        with self.db:
            self.db.execute("DELETE FROM cloud_batch WHERE batch='page-000'")
        with self.assertRaisesRegex(lab.VerificationHold, "archive differs"):
            lab.verify_step(self.db, *self.target, 56)

    def test_immutable_content_and_seal_hold(self):
        self.fixture()
        lab.verify_step(self.db, *self.target, 54)
        with self.assertRaises(sqlite3.IntegrityError), self.db:
            self.db.execute("UPDATE cloud_payload SET content=X'00'")
        with self.db:
            self.db.execute("DELETE FROM local_batch WHERE batch='page-001'")
        with self.assertRaisesRegex(lab.VerificationHold, "local inventory mismatch"):
            lab.verify_step(self.db, *self.target, 2)

    def test_preseal_checkpoints_and_distinct_generation(self):
        self.stage(0)
        self.assertTrue(lab.verify_batch(self.db, *self.target, "page-000"))
        self.stage(1)
        lab.seal(self.db, *self.target)
        final = lab.verify_step(self.db, *self.target, 1)
        self.assertEqual((final["reused"], final["verified_now"], final["status"]), (1, 1, "complete"))
        self.target = ("fixture", "fresh-A")
        self.stage(0)
        lab.seal(self.db, *self.target)
        self.assertEqual(lab.verify_step(self.db, *self.target, 1)["reused"], 0)
