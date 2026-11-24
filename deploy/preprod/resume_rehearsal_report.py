"""Offline acceptance report for the second PP rehearsal leg. Never grants a permit.

The release owner saves resume-2.json from the native verifier with the sealed
and collecting UUIDs, origin_id, seal_hash, source_sha, interruption and restart
timestamps, plus structured_pages_reused and structured_pages_checked. Shadow
journals do not supply that authoritative receipt. All other inputs use the
existing release observer filenames. A partial bundle is safe to inspect.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path


def stamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("timezone required")
    return result


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def assess(directory):
    names = {
        "attempt": "attempt-2.json", "resume": "resume-2.json",
        "retire": "retire-2.json", "inventory": "inventory-2.json",
        "before": "history-recompute-retained-2.json",
        "after": "history-recompute-retired-2.json",
        "original_before": "preserved05-before.json", "original_after": "preserved05-after.json",
    }
    missing = [file for file in [*names.values(), "live-db.jsonl"]
               if not (directory / file).is_file()]
    if missing:
        failure = directory / "retire-2-failure.json"
        return {"status": "pending", "missing": missing,
                "prior_failure_receipt_present": failure.is_file(), "retirement_authorized": False}
    try:
        receipts = {k: json.loads((directory / f).read_text()) for k, f in names.items()}
        with (directory / "live-db.jsonl").open() as source:
            result = evaluate(receipts, (json.loads(line) for line in source if line.strip()))
        return {"status": "pass", **result, "retirement_authorized": False}
    except (ValueError, KeyError, TypeError, IndexError, OSError) as exc:
        return {"status": "hold", "reason": str(exc), "retirement_authorized": False}


def evaluate(receipts, snapshots):
    attempt, resume, retire = (receipts[k] for k in ("attempt", "resume", "retire"))
    before, after = receipts["before"], receipts["after"]
    inv = receipts["inventory"]["inventory"]
    origin, sealed, fresh = before["origin_id"], attempt["sealed"], attempt["collecting"]
    require(bool(origin and fresh and sealed and fresh != sealed), "scope")
    require(resume["status"] == "native_resume_verified", "native resume receipt")
    for key in ("source_sha", "seal_hash", "sealed", "collecting"):
        require(attempt[key] and attempt[key] == resume[key], "resume binding " + key)
    require(resume["origin_id"] == origin, "resume origin")
    require((retire["sealed"], retire["collecting"], retire["manifest_digest"]) ==
            (sealed, fresh, attempt["seal_hash"]), "retirement binding")
    require(retire["status"] == "retired_pp" and retire["retirement_authorized"] is True
            and retire["operation_deadline_met"] is True and retire["seal_deadline_met"] is True,
            "native retirement receipt")
    require(0 < retire["phase_accounting"]["elapsed_seconds"] <= 240, "operation budget")
    inventory_receipt = receipts["inventory"]
    require((inventory_receipt["sealed"], inventory_receipt["collecting"],
             inventory_receipt["status"]) == (sealed, fresh, "inventory_only"), "inventory binding")
    pages = inv["structured_pages_examined"]
    require(inv["structured_inventory_complete"] is True and pages > 2 and
            resume["structured_pages_reused"] == pages - 2 and
            resume["structured_pages_checked"] == 2, "two-page restart coverage")
    require(retire["structured_count"] == inv["structured_rows"] and
            retire["objects_read"] == inv["raw_objects"] and
            retire["raw_count"] == attempt["row_count"], "archive coverage")
    for receipt, stage in ((before, "retained"), (after, "retired")):
        require((receipt["origin_id"], receipt["generation_id"], receipt["source_sha"],
                 receipt["phase"], receipt["status"]) ==
                (origin, sealed, attempt["source_sha"], stage, "exact_history_recompute_verified"),
                "history replay binding")
        require(receipt["historical_replay"]["verified"] is True, "history replay")
    provenance = after["archive_provenance"]
    require((provenance["origin_id"], provenance["generation_id"], provenance["state"],
             provenance["tier"]) == (origin, sealed, "retired", "authenticated_archive"),
            "post-removal archive provenance")
    required_parity = {"historical_recompute_hash", "quote_normalized_hash", "raw_input_hash",
                       "raw_input_id", "snapshot_id", "prediction_id"}
    require(required_parity <= before["parity"].keys() and
            all(before["parity"][key] for key in required_parity) and
            before["parity"] == after["parity"], "replay parity")
    original = receipts["original_before"]
    require(original == receipts["original_after"], "original trial05 fingerprint changed")
    preserved = [g for g in original["generations"] if g["slot"] == "A" and
                 g["origin_id"] == "pp-live-pp-trial-20261119-05" and
                 g["generation_id"] == "c7fbfa88-f3b8-40a3-83fa-c01912220570"]
    require(len(preserved) == 1 and preserved[0]["attached"] is True and
            preserved[0]["raw"]["sha256"] and preserved[0]["outbox"]["sha256"],
            "original trial05 A missing")
    start, stop, restart = map(stamp, (attempt["started_at"], resume["interrupted_at"],
                                      resume["resumed_at"]))
    require(start < stop < restart, "interruption chronology")
    counts = [[], [], []]
    session = None
    removed = None
    previous_time = None
    previous_count = None
    for row in snapshots:
        observed = stamp(row["at_utc"])
        if observed < start:
            continue
        require(previous_time is None or observed > previous_time, "observer order")
        previous_time = observed
        require(row.get("origin_id") == origin and "generations" in row, "observer gap")
        writer, admission = row["writer"], row["admission"]
        require(writer["collector_enabled"] is True and writer["generation_id"] == fresh and
                writer["collector_session_id"] == admission["session_id"] and
                admission["initial_a"] != fresh, "fresh A collector")
        session = session or writer["collector_session_id"]
        require(session and writer["collector_session_id"] == session, "collector restarted")
        by_id = {g["generation_id"]: g for g in row["generations"]}
        old, new = by_id[sealed], by_id[fresh]
        require(old["slot"] == "B" and new["slot"] == "A" and new["state"] == "collecting",
                "slot binding")
        count = new["polymarket_quotes"]["rows"]
        require(type(count) is int and count >= 0 and
                (previous_count is None or count >= previous_count), "quote counter")
        previous_count = count
        if old["state"] == "retired":
            removed = stamp(old["retired_at"])
            require(restart < removed <= observed and old["relation_exists"] is False and
                    old["partition_attached"] is False, "physical retirement")
            break
        require(old["partition_attached"] is True and old["relation_exists"] is True,
                "premature removal")
        if observed < stop:
            counts[0].append(count)
        elif stop < observed < restart:
            counts[1].append(count)
        elif observed > restart:
            counts[2].append((observed, count))
    require(removed is not None, "missing physical removal")
    counts[2] = [c for t, c in counts[2] if restart < t < removed]
    require(all(len(c) >= 2 and c[-1] > c[0] for c in counts),
            "insufficient fresh A quote observations across interruption")
    return {"sealed_b": sealed, "fresh_a": fresh, "collector_session": session,
            "quotes_before_interruption": counts[0][-1] - counts[0][0],
            "quotes_while_verifier_paused": counts[1][-1] - counts[1][0],
            "quotes_during_resumed_verification": counts[2][-1] - counts[2][0],
            "retired_at": removed.isoformat()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    report = assess(parser.parse_args().directory)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["status"] == "pass" else 1)
