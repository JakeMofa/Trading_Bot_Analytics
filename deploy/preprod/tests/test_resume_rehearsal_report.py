import tempfile
import unittest
from pathlib import Path

from deploy.preprod.resume_rehearsal_report import assess, evaluate


def stamp(seconds):
    return f"2026-11-23T00:00:{seconds:02d}+00:00"


def fixture():
    target = dict(source_sha="source", sealed="b", collecting="a2", seal_hash="digest")
    history = dict(origin_id="pp", source_sha="source", generation_id="b",
                   status="exact_history_recompute_verified", historical_replay={"verified": True},
                   parity={k: k for k in ("historical_recompute_hash", "quote_normalized_hash",
                                          "raw_input_hash", "raw_input_id", "snapshot_id", "prediction_id")})
    receipts = dict(
        attempt=dict(target, started_at=stamp(0), row_count=3),
        resume=dict(target, status="native_resume_verified", origin_id="pp", interrupted_at=stamp(12),
                    resumed_at=stamp(32), structured_pages_reused=54, structured_pages_checked=2),
        retire=dict(sealed="b", collecting="a2", manifest_digest="digest", status="retired_pp",
                    retirement_authorized=True, operation_deadline_met=True, seal_deadline_met=True,
                    phase_accounting={"elapsed_seconds": 4.1}, structured_count=27528,
                    objects_read=50, raw_count=3),
        inventory={"sealed": "b", "collecting": "a2", "status": "inventory_only",
                   "inventory": dict(structured_inventory_complete=True, structured_pages_examined=56,
                                     structured_rows=27528, raw_objects=50)},
        before=dict(history, phase="retained"), after=dict(history, phase="retired", archive_provenance=dict(
            origin_id="pp", generation_id="b", state="retired", tier="authenticated_archive")))
    original = {"generations": [dict(slot="A", origin_id="pp-live-pp-trial-20261119-05",
                                    generation_id="c7fbfa88-f3b8-40a3-83fa-c01912220570",
                                    attached=True, raw={"sha256": "raw"}, outbox={"sha256": "outbox"})]}
    receipts.update(original_before=original, original_after=original)
    snapshots = []
    for i in (1, 11, 18, 27, 33, 37, 42):
        removed = i == 42
        snapshots.append(dict(at_utc=stamp(i), origin_id="pp",
            writer=dict(collector_enabled=True, generation_id="a2", collector_session_id="same"),
            admission=dict(initial_a="a1", session_id="same"),
            generations=[
                dict(slot="B", generation_id="b", state="retired" if removed else "verified",
                     relation_exists=not removed, partition_attached=not removed,
                     retired_at=stamp(40) if removed else None),
                dict(slot="A", generation_id="a2", state="collecting", polymarket_quotes={"rows": i})]))
    return receipts, snapshots


class RehearsalReportTest(unittest.TestCase):
    def test_complete(self):
        data, samples = fixture()
        result = evaluate(data, samples)
        self.assertEqual(result["quotes_while_verifier_paused"], 9)
        self.assertEqual(result["retired_at"], stamp(40))

    def test_invalid_receipts_and_observer_gaps(self):
        for key in ("shadow", "replay", "missing_page", "held", "restart", "gapped", "no_quotes",
                    "only_post_removal_growth", "wrong_inventory", "changed_trial05"):
            with self.subTest(key=key):
                data, samples = fixture()
                if key == "shadow":
                    data["resume"]["status"] = "shadow_complete"
                elif key == "replay":
                    data["after"]["parity"] = {"quote_normalized_hash": "different"}
                elif key == "missing_page":
                    data["resume"]["structured_pages_checked"] = 1
                elif key == "held":
                    samples[-1]["generations"][0]["relation_exists"] = True
                elif key == "restart":
                    samples[2]["writer"]["collector_session_id"] = "other"
                elif key == "gapped":
                    samples[2] = dict(at_utc=stamp(18), status="HOLD")
                elif key == "only_post_removal_growth":
                    samples[5]["generations"][1]["polymarket_quotes"]["rows"] = 33
                elif key == "wrong_inventory":
                    data["inventory"]["sealed"] = "wrong"
                elif key == "changed_trial05":
                    data["original_after"] = {"generations": []}
                else:
                    samples[3]["generations"][1]["polymarket_quotes"]["rows"] = 18
                with self.assertRaises(ValueError):
                    evaluate(data, samples)

    def test_missing_receipts(self):
        with tempfile.TemporaryDirectory() as path:
            result = assess(Path(path))
            self.assertEqual(result["status"], "pending")
            self.assertFalse(result["retirement_authorized"])
            self.assertIn("resume-2.json", result["missing"])
