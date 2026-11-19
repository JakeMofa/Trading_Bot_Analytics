import unittest
from datetime import datetime, timedelta, timezone

from deploy.preprod.archive_status_sample import classify_observation


class ArchiveStatusSampleTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 19, 19, tzinfo=timezone.utc)
        self.age = timedelta(minutes=2)
        self.writer = {
            "generation_id": "generated-generation",
            "collector_enabled": False,
            "lease_expires_at": (self.now + timedelta(seconds=5)).isoformat(),
        }
        self.sample = {
            "scope": "pp_live_read_only_resource_sample",
            "origin_id": "pp-live-pp",
            "observed_at_utc": (self.now - self.age).isoformat(),
            "database": {"writer": self.writer},
        }

    def classify(self, sample):
        return classify_observation(sample, now=self.now, max_age=self.age)

    def test_fresh_off_and_leased_are_separate_from_health(self):
        actual = self.classify(self.sample)
        self.assertEqual((actual["observation"], actual["collector"]), ("fresh", "off"))
        self.assertFalse(actual["retirement_authorized"])
        self.writer["collector_enabled"] = True
        self.assertEqual(self.classify(self.sample)["collector"], "leased")
        self.writer["lease_expires_at"] = self.now.isoformat()
        self.assertEqual(self.classify(self.sample)["collector"], "lease_expired")

    def test_stale_report_does_not_describe_the_current_collector(self):
        self.sample["observed_at_utc"] = (self.now - self.age - timedelta(seconds=1)).isoformat()
        actual = self.classify(self.sample)
        self.assertEqual((actual["observation"], actual["collector"]), ("stale", "unknown"))
        self.assertIsNone(actual["generation_id"])

    def test_missing_and_invalid_reports_keep_values_unknown(self):
        self.assertEqual(self.classify(None)["observation"], "missing")
        for origin, observed_at in (
            ("other-origin", self.now.isoformat()),
            ("pp-live-pp", (self.now + timedelta(seconds=1)).isoformat()),
            ("pp-live-pp", "2026-11-19T18:59:59"),
        ):
            with self.subTest(origin=origin, observed_at=observed_at):
                sample = dict(self.sample, origin_id=origin, observed_at_utc=observed_at)
                actual = self.classify(sample)
                self.assertEqual((actual["observation"], actual["collector"]), ("invalid", "unknown"))
                self.assertIsNone(actual["observed_at"])

    def test_missing_writer_and_unverified_lease_are_unknown(self):
        self.writer["collector_enabled"] = True
        self.writer["lease_expires_at"] = None
        self.assertEqual(self.classify(self.sample)["collector"], "unknown")
        self.sample["database"] = None
        self.assertEqual(self.classify(self.sample)["collector"], "unknown")
