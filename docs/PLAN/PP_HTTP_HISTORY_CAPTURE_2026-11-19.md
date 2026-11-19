# Source-only PP HTTP history capture

`deploy/preprod/capture_history_http.py` is an executable read-only evidence
client. It opens only direct GET requests to a literal loopback IP HTTP endpoint;
use it through an independently established SSH tunnel or on the operator's
local loopback. It never opens SSH, a database, a cloud service, collector or
operator endpoint. This milestone performed no actual host/network capture.

## Existing route, retained and retired

At base `d2ca040bb11b70c1a809e6b056ca7ebb1c6c8d05`, the route is
`/history/archive/{generation_id}`, not `/history/raw`. `RuntimeHistory` binds
origin `pp-live-pp`; `ReadRepository.local_history` locks the raw parent and
reads attached collecting/sealed/verified rows. For a retired generation the
same endpoint lazy-constructs authenticated raw archive retrieval. Therefore no
synthetic retained expectation or restricted DB fixture is necessary here.
The source runtime flag must already be qualified/enabled; a 503 is a capture
failure, never permission to change flags/grants. Never synthesize old timestamps
or silently substitute DB rows when the actual HTTP route is unavailable.

Before-removal captures require **sealed or verified**, attached local data.
Collecting generations are rejected because paging them cannot prove a stable
snapshot. After-removal captures require retired state and authenticated archive
tier. Each page must preserve origin/UUID/dataset/state/seal time and strictly
ordered, nonduplicate `(source,event_id)` identities. Cursor identities and
complete flags are checked; oversized/partial scans fail.

## Local operator procedure (not executed)

Create a local evidence directory outside Git. Bind each actual trial UUID once,
in order, as it becomes known. A first capture may precede the second binding;
its provisional missing-peer gap clears only when offline comparison has both
immutable bindings. A third UUID or replacement binding is rejected.

```sh
python deploy/preprod/capture_history_http.py bind \
  --binding-dir /tmp/pp-history-bindings --ordinal 1 --generation FIRST_UUID
# Bind ordinal 2 by the same command only after its actual UUID is known.
```

With the existing tunnel listening at `127.0.0.1:18080`, capture each bound
ordinal just before removal and again after independently proven removal. Replace
`SOURCE_SHA` with the independently qualified exact application source SHA.
The client records this as operator-declared; the HTTP API does not attest it.

```sh
python deploy/preprod/capture_history_http.py capture \
  --binding-dir /tmp/pp-history-bindings --ordinal 1 --phase retained \
  --base-url http://127.0.0.1:18080 --source-sha SOURCE_SHA \
  --output /tmp/first-retained.json
# Repeat as retired to /tmp/first-retired.json, and both phases for ordinal 2.
python deploy/preprod/capture_history_http.py compare \
  --binding-dir /tmp/pp-history-bindings \
  --captures /tmp/first-retained.json /tmp/first-retired.json \
             /tmp/second-retained.json /tmp/second-retired.json \
  --output /tmp/two-generation-http-parity.json
```

Outputs are create-only. No retries, redirects, proxy environment variables,
credentials, DNS names or public addresses are accepted. Bounds: at most four
seconds for each entire request (absolute socket shutdown also covers slow
headers), 240 seconds overall, 128 raw pages/64,000 rows per generation, 270
requests, 64 MiB received and 64 MiB final JSON. Each request/whole capture keeps
UTC observed/completed timestamps and elapsed monotonic time. Raw bytes are
base64-preserved with SHA-256 separately from parsed JSON; source epochs and
monetary fields must remain finite exact strings, including null/missing values.
The capture contains full `/state/current`, the first complete `/events` SSE
frame, `/history/predictions?limit=500`, `/history/coinbase-chart`,
`/history/context` and all raw pages. This is not continuous SSE or a rendered
browser check. State's server timestamps remain unchanged; local clock
synchronization is not claimed.

Comparison requires exactly two retained/retired pairs, verifies stored response
bytes/hashes against parsed content and compares every raw row exactly. Every
saved prediction in the retained capture must still exist with all exposed
fields exactly equal after removal; unrelated newer predictions may coexist.
The current prediction route lacks pagination, generation filtering and
snapshot IDs. Full 500-row pages are INCOMPLETE; a forecast falling out of the
bounded page is a failure, not proof it was deleted. #185's separate composition
remains the source for snapshot links and reviewed calculation-input evidence.

Missing current market/features/forecast, absent predictions, missing/truncated
chart and unsupported context are explicit gaps. In particular context is
currently unsupported, so complete raw/prediction parity may have separate PASS
results while overall result remains INCOMPLETE. No real official outcome labels
or historical chart availability are fabricated. A failed capture preserves
previous successful responses (and a received HTTP error body) in a FAIL artifact;
partial rows cannot be compared as complete evidence. Exit status is nonzero
for FAIL/INCOMPLETE. Never interpret a nonempty history response as an active
numeric forecast or a retirement authorization.

## Starting from old verified A and disabled collecting B

Source review confirms `bootstrap` reuses collecting B. Rotation into A fails
with `other_slot_not_retired` while old verified A remains attached and
nonretired; the PP writer is fenced OFF. The old A deadline cannot be renewed
or retroactively passed. With both slots occupied there is no honest fresh
A→B→fresh-A start under a simultaneous no-delete/no-copy/no-provision rule.
Keep both preserved and collection OFF until the operator resolves that gate.
A separate old-generation maintenance disposition would need independently
reviewed authority/fresh verification and must never be counted as the original
trial's retirement pass. Even if that separately freed A, resuming existing B
would start B→fresh-A→fresh-B; accepting that equivalent sequence or preparing
an actual fresh-A start requires an explicit trial decision. This client makes
no state change or reset and does not recommend relabeling either UUID.

## Qualification

Nine network-free tests pass using existing FastAPI routes with an explicitly
generated backing repository/transport. The fixture adapts only its generated
origin to the probe's PP allowlist; no actual PP provenance or native partition
DROP is claimed. Cases cover two attached/model-retired UUIDs, exact response
hashes, paging, mismatch/float/cursor guards, immutable bindings, loopback-only
addresses, absolute header shutdown and partial failure receipts. Existing
five offline parity tests and fifteen dashboard evidence tests also pass.
Native PG and real-host/tunnel capture are not run by this source-only task.

```sh
python -m unittest discover -s backend/tests -p test_capture_history_http.py -v
```
