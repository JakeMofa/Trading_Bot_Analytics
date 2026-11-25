"""Publish timings from a completed PP boundary-report CSV to Grafana Cloud."""

import argparse
import base64
import csv
from datetime import datetime
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener


def timestamp(value):
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("Boundary evidence requires timezone-aware timestamps")
    return parsed.timestamp()


def metric_lines(rows, host):
    for row in rows:
        if row["observation_status"] != "complete" or row["identity_status"] != "matched":
            continue
        boundary = timestamp(row["window_start"])
        point = int(boundary) * 10**9
        for path, column in (
            ("rest", "early_rest_first_utc"),
            ("websocket", "websocket_first_utc"),
            ("collector_rest", "canonical_first_utc"),
            ("dashboard_api", "dashboard_first_utc"),
        ):
            if row[column]:
                seconds = timestamp(row[column]) - boundary
                if seconds >= 0:
                    yield f"tradebot_pp_boundary,host={host},path={path} seconds={seconds:.6f} {point}"
        received = row["displayed_quote_receipt_utc"]
        committed = row["displayed_quote_commit_utc"]
        displayed = row["dashboard_first_utc"]
        if received and committed and displayed:
            receipt, commit, api = map(timestamp, (received, committed, displayed))
            if boundary <= receipt <= commit <= api:
                for stage, seconds in (("receipt_to_commit", commit - receipt),
                                       ("commit_to_api", api - commit),
                                       ("receipt_to_api", api - receipt)):
                    yield f"tradebot_pp_quote_pipeline,host={host},stage={stage} seconds={seconds:.6f} {point}"


class RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--host", required=True, choices=("pp", "pp-benchmark"))
    parser.add_argument("--endpoint")
    parser.add_argument("--tenant")
    parser.add_argument("--token-file", type=Path)
    args = parser.parse_args()
    with args.report.open(newline="") as source:
        lines = list(metric_lines(csv.DictReader(source), args.host))
    if not lines:
        parser.exit(1, "No complete, matched observations to publish\n")
    payload = "\n".join(lines) + "\n"
    if not (args.endpoint or args.tenant or args.token_file):
        print(payload, end="")
        return
    if not (args.endpoint and args.tenant and args.token_file and args.tenant.isdecimal()
            and re.fullmatch(r"https://[a-z0-9-]+\.grafana\.net/api/v1/push/influx(?:/write)?",
                             args.endpoint)):
        parser.error("Publishing requires a Grafana Cloud Influx endpoint, tenant and token file")
    token = args.token_file.read_text().strip()
    if not token:
        parser.error("The token file is empty")
    auth = base64.b64encode(f"{args.tenant}:{token}".encode()).decode()
    request = Request(args.endpoint, data=payload.encode(), headers={
        "Authorization": "Basic " + auth, "Content-Type": "text/plain",
    })
    try:
        with build_opener(RejectRedirect).open(request, timeout=10) as response:
            print(f"Grafana accepted {len(lines)} samples (HTTP {response.status})")
    except HTTPError as error:
        parser.exit(1, f"Grafana rejected the samples (HTTP {error.code})\n")


if __name__ == "__main__":
    main()
