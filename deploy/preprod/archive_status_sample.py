"""Classify a PP resource observation without granting archive authority."""
from datetime import datetime, timedelta


def _aware_datetime(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.utcoffset() is not None else None


def classify_observation(sample, *, now, max_age, origin_id="pp-live-pp"):
    """Preserve the difference between report freshness and collector activity."""
    if now.utcoffset() is None or max_age <= timedelta(0):
        raise ValueError("a timezone-aware clock and positive age budget are required")

    result = {
        "origin_id": origin_id,
        "observation": "missing",
        "observed_at": None,
        "collector": "unknown",
        "generation_id": None,
        "retirement_authorized": False,
    }
    if sample is None:
        return result

    result["observation"] = "invalid"
    if not isinstance(sample, dict) or sample.get("scope") != "pp_live_read_only_resource_sample":
        return result
    if sample.get("origin_id") != origin_id:
        return result
    observed_at = _aware_datetime(sample.get("observed_at_utc"))
    if observed_at is None or observed_at > now:
        return result

    result["observed_at"] = observed_at.isoformat()
    result["observation"] = "stale"
    if now - observed_at > max_age:
        return result

    result["observation"] = "fresh"
    database = sample.get("database")
    writer = database.get("writer") if isinstance(database, dict) else None
    if not isinstance(writer, dict):
        return result

    generation_id = writer.get("generation_id")
    if isinstance(generation_id, str) and generation_id:
        result["generation_id"] = generation_id
    enabled = writer.get("collector_enabled")
    if enabled is False:
        result["collector"] = "off"
    elif enabled is True:
        lease = _aware_datetime(writer.get("lease_expires_at"))
        if lease is not None:
            result["collector"] = "leased" if lease > now else "lease_expired"
    return result
