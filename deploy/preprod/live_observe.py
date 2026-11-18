"""Read-only, bounded observation of one PP live collector session.

The operator owns ON and OFF. This tool accepts only a caller-supplied loopback
API tunnel, never connects to PostgreSQL, and never changes collector state.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

INTERVAL = 5
CHECK_INTERVAL = 60
TIMEOUT = 2
MAX_BODY = 256 * 1024


def utcnow():
    return datetime.now(timezone.utc)


def iso(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else None


def age(now, value):
    parsed = iso(value)
    return round((now - parsed).total_seconds(), 3) if parsed else None


def nested(row, *keys):
    for key in keys:
        if not isinstance(row, dict):
            return None
        row = row.get(key)
    return row


def checked_base(value):
    parsed = urlsplit(value)
    if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost")
            or parsed.username or parsed.password or parsed.path not in ("", "/")
            or parsed.query or parsed.fragment or parsed.port is None):
        raise ValueError("PP observer requires a plain loopback HTTP tunnel")
    return value.rstrip("/")


class PrivateAPI:
    def __init__(self, base):
        self.base = checked_base(base)
        # A private API redirect must not turn this observer into a remote client.
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, request, fp, code, msg, headers, newurl):
                return None
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def get(self, path, *, stream=False):
        request = Request(self.base + path, headers={"Accept": "text/event-stream" if stream else "application/json"})
        started = time.monotonic()
        try:
            with self.opener.open(request, timeout=TIMEOUT) as response:
                content_type = response.headers.get("Content-Type", "")
                if stream:
                    if "text/event-stream" not in content_type:
                        raise ValueError("SSE content type mismatch")
                    for _ in range(8):
                        line = response.readline(MAX_BODY + 1)
                        if len(line) > MAX_BODY:
                            raise ValueError("SSE frame too large")
                        if line.startswith(b"data: "):
                            frame = json.loads(line[6:])
                            if not isinstance(frame, dict):
                                raise ValueError("SSE frame must be an object")
                            return frame, time.monotonic() - started
                    raise ValueError("SSE frame unavailable")
                body = response.read(MAX_BODY + 1)
                if len(body) > MAX_BODY:
                    raise ValueError("API response too large")
                if path == "/dashboard":
                    return body.decode(), time.monotonic() - started
                parsed = json.loads(body)
                if not isinstance(parsed, dict):
                    raise ValueError("API response must be an object")
                return parsed, time.monotonic() - started
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            # Never persist a response body or request headers in the report.
            raise RuntimeError(type(exc).__name__) from None


def sample_once(api, now=None):
    now = now or utcnow()
    sample = {"at": now.isoformat(), "error": None}
    try:
        state, state_latency = api.get("/state/current")
        health, health_latency = api.get("/health")
        sample.update({
            "state_latency_ms": round(state_latency * 1000, 3),
            "health_latency_ms": round(health_latency * 1000, 3),
            "environment": state.get("environment"),
            "data_mode": state.get("data_mode"),
            "origin_id": state.get("origin_id"),
            "collector_enabled": nested(state, "collector", "enabled"),
            "health_status": health.get("status"),
            "storage_status": state.get("storage_status"),
            "market_id": nested(state, "market", "id"),
            "market_end": nested(state, "market", "end"),
            "price_generation_id": nested(state, "coinbase", "generation_id"),
            "coinbase_event_id": nested(state, "coinbase", "event_id"),
            "coinbase_age_seconds": age(now, nested(state, "coinbase", "source_time")),
            "polymarket_receipt_time": nested(state, "polymarket", "received_at"),
            "polymarket_source_age_seconds": age(now, nested(state, "polymarket", "source_time")),
            "polymarket_receipt_age_seconds": age(now, nested(state, "polymarket", "received_at")),
            "feature_id": nested(state, "feature_snapshot", "snapshot_id"),
            "feature_age_seconds": age(now, nested(state, "feature_snapshot", "as_of")),
            "prediction_id": nested(state, "forecast", "prediction_id"),
            "coinbase_feed_status": nested(state, "feeds", "coinbase_stream", "status"),
            "polymarket_feed_status": (nested(state, "feeds", "polymarket_rest", "status")
                                       or nested(state, "feeds", "polymarket_stream", "status")),
        })
    except RuntimeError as exc:
        sample["error"] = str(exc)
    return sample


def contract_check(api):
    check = {"at": utcnow().isoformat(), "error": None}
    try:
        dashboard, dashboard_latency = api.get("/dashboard")
        predictions, predictions_latency = api.get("/history/predictions?limit=5")
        chart, chart_latency = api.get("/history/coinbase-chart")
        frame, sse_latency = api.get("/events", stream=True)
        check.update({
            "dashboard_ok": "new EventSource('/events')" in dashboard,
            "prediction_history_ok": isinstance(predictions.get("items"), list)
                                     and bool(predictions["items"]),
            "chart_ok": isinstance(chart.get("points"), list) and bool(chart["points"]),
            "sse_ok": frame.get("environment") == "preprod"
                      and frame.get("data_mode") == "pp_live"
                      and frame.get("origin_id") == "pp-live-pp",
            "dashboard_latency_ms": round(dashboard_latency * 1000, 3),
            "history_latency_ms": round(predictions_latency * 1000, 3),
            "chart_latency_ms": round(chart_latency * 1000, 3),
            "sse_latency_ms": round(sse_latency * 1000, 3),
        })
    except RuntimeError as exc:
        check["error"] = str(exc)
    return check


def evaluate(samples, checks, elapsed):
    errors = [row for row in samples if row.get("error")]
    live = [row for row in samples if not row.get("error")
            and row.get("environment") == "preprod"
            and row.get("data_mode") == "pp_live"
            and row.get("origin_id") == "pp-live-pp"]
    after_warmup = [row for row in live if (iso(row["at"]) - iso(samples[0]["at"])).total_seconds() >= 60] if samples else []
    market_ids = list(dict.fromkeys(row.get("market_id") for row in live if row.get("market_id")))
    first_end = iso(next((row.get("market_end") for row in live if row.get("market_id") == (market_ids[0] if market_ids else None)), None))
    boundary = (len(market_ids) >= 2 and first_end is not None
                and any(row.get("market_id") != market_ids[0] and iso(row["at"]) >= first_end
                        for row in live))
    feature_ids = {row["feature_id"] for row in live if row.get("feature_id")}
    prediction_ids = {row["prediction_id"] for row in live if row.get("prediction_id")}
    price_ids = {row["coinbase_event_id"] for row in live if row.get("coinbase_event_id")}
    book_receipts = {row["polymarket_receipt_time"] for row in live
                     if row.get("polymarket_receipt_time")}
    max_latency = max((max(row.get("state_latency_ms", 0), row.get("health_latency_ms", 0))
                       for row in live), default=None)
    max_price_age = max((row["coinbase_age_seconds"] for row in after_warmup
                         if row.get("coinbase_age_seconds") is not None), default=None)
    max_feature_age = max((row["feature_age_seconds"] for row in after_warmup
                           if row.get("feature_age_seconds") is not None), default=None)
    concrete_failures = []
    if errors or any(row.get("error") for row in checks):
        concrete_failures.append("api_or_contract_error")
    if len(live) != len(samples):
        concrete_failures.append("wrong_environment_or_mode")
    if any(row.get("collector_enabled") is not True or row.get("storage_status") != "ok"
           or row.get("health_status") != "ok" for row in after_warmup):
        concrete_failures.append("collector_storage_or_health")
    if any(row.get("coinbase_feed_status") != "fresh" or row.get("polymarket_feed_status") != "fresh"
           for row in after_warmup):
        concrete_failures.append("feed_stale")
    if any(row.get("coinbase_age_seconds") is None or row["coinbase_age_seconds"] > 30
           or row["coinbase_age_seconds"] < -2 or row.get("feature_age_seconds") is None
           or row["feature_age_seconds"] > 30 or row["feature_age_seconds"] < -2
           for row in after_warmup):
        concrete_failures.append("price_or_feature_age")
    if any(max(row.get("state_latency_ms", 0), row.get("health_latency_ms", 0)) >= 2000
           for row in live):
        concrete_failures.append("api_two_second_latency")
    incomplete = []
    if elapsed < 1200 or not after_warmup:
        incomplete.append("observation_under_20_minutes")
    if len(samples) < max(1, int(elapsed / INTERVAL * .9)):
        incomplete.append("five_second_sample_coverage_incomplete")
    if len(checks) < max(1, int(elapsed / CHECK_INTERVAL * .8)):
        incomplete.append("bounded_contract_check_coverage_incomplete")
    if any((iso(right["at"]) - iso(left["at"])).total_seconds() > 10
           for left, right in zip(samples, samples[1:])):
        incomplete.append("sample_gap_over_ten_seconds")
    if len(feature_ids) < 3:
        incomplete.append("fewer_than_three_feature_cycles")
    if len(prediction_ids) < 3:
        incomplete.append("fewer_than_three_predictions")
    if len(price_ids) < 2 or len(book_receipts) < 2:
        incomplete.append("feeds_not_demonstrated_advancing")
    if not boundary:
        incomplete.append("real_market_boundary_not_demonstrated")
    for key in ("dashboard_ok", "prediction_history_ok", "chart_ok", "sse_ok"):
        if not any(row.get(key) is True for row in checks):
            incomplete.append(key + "_not_demonstrated")
    status = "FAIL" if concrete_failures else "INCOMPLETE" if incomplete else "PASS"
    return {
        "result": status, "scope": "pp_live_private_api_observation",
        "elapsed_seconds": round(elapsed, 3), "samples": len(samples),
        "api_errors": len(errors), "max_api_latency_ms": max_latency,
        "market_ids": market_ids, "real_boundary": bool(boundary),
        "distinct_coinbase_events": len(price_ids),
        "distinct_polymarket_receipts": len(book_receipts),
        "distinct_feature_cycles": len(feature_ids),
        "distinct_predictions": len(prediction_ids),
        "max_input_price_age_seconds": max_price_age,
        "max_feature_age_seconds": max_feature_age,
        "failures": concrete_failures, "missing_evidence": incomplete,
        "raw_row_acknowledgement": "NOT_MEASURED_BY_API",
        "disk_wal_growth": "NOT_MEASURED_BY_API",
        "supabase_archive_and_retirement": "NOT_PERFORMED",
    }


def observe(api, seconds, *, clock=time.monotonic, sleeper=time.sleep):
    if not 1 <= seconds <= 1800:
        raise ValueError("observation duration must fit one bounded session")
    start = clock()
    samples, checks = [], []
    next_sample = start
    next_check = start
    while clock() - start < seconds:
        now = clock()
        if now < next_sample:
            sleeper(min(next_sample - now, seconds - (now - start)))
            continue
        samples.append(sample_once(api))
        next_sample += INTERVAL
        if now >= next_check:
            checks.append(contract_check(api))
            next_check += CHECK_INTERVAL
    return samples, checks, evaluate(samples, checks, clock() - start)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Caller-supplied loopback SSH tunnel, e.g. http://127.0.0.1:18000")
    parser.add_argument("--seconds", type=int, default=1500, help="1-1800; PASS requires >=1200")
    parser.add_argument("--output", type=Path, required=True, help="Local sanitized JSON report")
    args = parser.parse_args()
    api = PrivateAPI(args.base_url)
    samples, checks, summary = observe(api, args.seconds)
    report = {"summary": summary, "samples": samples, "checks": checks}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
