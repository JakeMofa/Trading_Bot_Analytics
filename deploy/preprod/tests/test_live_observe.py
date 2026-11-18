"""Local fake-HTTP tests; no PP tunnel or live market access."""
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import live_observe as observer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "https://example.com/private")
            self.end_headers()
            return
        now = datetime.now(timezone.utc)
        state = {
            "environment": "preprod", "data_mode": "pp_live", "origin_id": "pp-live-pp",
            "collector": {"enabled": True}, "storage_status": "ok",
            "market": {"id": "fixture-market", "end": (now + timedelta(minutes=5)).isoformat()},
            "coinbase": {"event_id": "coinbase-1", "generation_id": "fixture-generation",
                         "source_time": (now - timedelta(seconds=2)).isoformat()},
            "polymarket": {"received_at": (now - timedelta(seconds=2)).isoformat(),
                           "source_time": (now - timedelta(seconds=3)).isoformat()},
            "feature_snapshot": {"snapshot_id": "feature-1", "as_of": (now - timedelta(seconds=2)).isoformat()},
            "forecast": {"prediction_id": "prediction-1"},
            "feeds": {"coinbase_stream": {"status": "fresh"}, "polymarket_rest": {"status": "fresh"}},
        }
        data = {
            "/state/current": state,
            "/health": {"status": "ok"},
            "/history/predictions?limit=5": {"items": [{"prediction_id": "prediction-1"}]},
            "/history/coinbase-chart": {"points": [{"price_usd": "1.000000000000001"}]},
        }
        if self.path == "/events":
            raw = ("data: " + json.dumps(state) + "\n\n").encode()
            content_type = "text/event-stream"
        elif self.path == "/dashboard":
            raw = b"new EventSource('/events')"
            content_type = "text/html"
        elif self.path in data:
            raw = json.dumps(data[self.path]).encode()
            content_type = "application/json"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_args):
        pass


def synthetic_samples(*, boundary=True, bad_health=False):
    start = datetime(2026, 11, 17, 22, 0, tzinfo=timezone.utc)
    first_end = start + timedelta(minutes=15)
    rows = []
    for tick in range(251):
        at = start + timedelta(seconds=tick * 5)
        after = boundary and at >= first_end
        rows.append({
            "at": at.isoformat(), "error": None, "environment": "preprod",
            "data_mode": "pp_live", "origin_id": "pp-live-pp",
            "collector_enabled": True, "health_status": "degraded" if bad_health and tick == 30 else "ok",
            "storage_status": "ok", "market_id": "B" if after else "A",
            "market_end": (first_end + timedelta(minutes=15) if after else first_end).isoformat(),
            "coinbase_event_id": "coinbase-" + str(tick // 2),
            "polymarket_receipt_time": (at - timedelta(seconds=2)).isoformat(),
            "feature_id": "feature-" + str(tick // 20),
            "prediction_id": "prediction-" + str(tick // 20),
            "coinbase_age_seconds": 2, "feature_age_seconds": 4,
            "coinbase_feed_status": "fresh", "polymarket_feed_status": "fresh",
            "state_latency_ms": 22, "health_latency_ms": 15,
        })
    return rows


class LiveObservationTests(unittest.TestCase):
    def test_only_loopback_tunnel_is_accepted(self):
        for url in ("https://127.0.0.1:18000", "http://example.com:18000",
                    "http://user:pass@127.0.0.1:18000", "http://127.0.0.1:18000/path"):
            with self.assertRaises(ValueError):
                observer.checked_base(url)
        self.assertEqual(observer.checked_base("http://127.0.0.1:18000/"),
                         "http://127.0.0.1:18000")

    def test_fake_private_http_samples_and_bounded_contract(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            api = observer.PrivateAPI("http://127.0.0.1:" + str(server.server_port))
            sample = observer.sample_once(api)
            self.assertIsNone(sample["error"])
            self.assertEqual(sample["market_id"], "fixture-market")
            self.assertEqual(sample["price_generation_id"], "fixture-generation")
            self.assertEqual(sample["origin_id"], "pp-live-pp")
            self.assertLess(sample["coinbase_age_seconds"], 30)
            with self.assertRaisesRegex(RuntimeError, "HTTPError"):
                api.get("/redirect")
            check = observer.contract_check(api)
            self.assertIsNone(check["error"])
            for field in ("dashboard_ok", "prediction_history_ok", "chart_ok", "sse_ok"):
                self.assertTrue(check[field])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_pass_requires_real_boundary_cycles_and_sample_coverage(self):
        checks = [{"dashboard_ok": True, "prediction_history_ok": True,
                   "chart_ok": True, "sse_ok": True} for _ in range(22)]
        result = observer.evaluate(synthetic_samples(), checks, 1250)
        self.assertEqual(result["result"], "PASS")
        self.assertTrue(result["real_boundary"])
        self.assertGreaterEqual(result["distinct_feature_cycles"], 3)
        self.assertEqual(observer.evaluate(synthetic_samples(boundary=False), checks, 1250)["result"],
                         "INCOMPLETE")
        self.assertIn("five_second_sample_coverage_incomplete",
                      observer.evaluate(synthetic_samples()[:25], checks, 1250)["missing_evidence"])

    def test_degraded_health_fails_even_with_other_evidence(self):
        checks = [{"dashboard_ok": True, "prediction_history_ok": True,
                   "chart_ok": True, "sse_ok": True} for _ in range(22)]
        result = observer.evaluate(synthetic_samples(bad_health=True), checks, 1250)
        self.assertEqual(result["result"], "FAIL")
        self.assertIn("collector_storage_or_health", result["failures"])


if __name__ == "__main__":
    unittest.main()
