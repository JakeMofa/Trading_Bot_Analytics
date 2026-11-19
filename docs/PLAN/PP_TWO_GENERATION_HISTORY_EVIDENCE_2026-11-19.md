# Two-generation history evidence — source qualification only

Base: `origin/preprod` `d2ca040bb11b70c1a809e6b056ca7ebb1c6c8d05`.
No host, deployment, cloud, collector, lease, runtime registration, permission,
or retirement operation was performed. Existing captured source times, decimal
strings, calculation references and #185 snapshots are preserved unchanged.

## Implemented evidence path

`deploy/preprod/history_parity_evidence.py` reads an explicit bounded JSON bundle
with exactly two distinct origin/generation scopes. Each scope has collecting,
sealed and retired phases. Each phase retains the complete #185 `ResearchWindow`
response, full existing HTTP history responses and original artifact references.
The manifest shape is demonstrated by
`backend/tests/fixtures/history_parity_two_generations.json` (generated only).

For each phase capture these existing routes without the older dashboard
observer's first-five-items projection:

- `/history/predictions?limit=500`: retain the original HTTP status/body. Match
  every research forecast by actual `items[].id` and all fields exposed by this
  endpoint. Unrelated newer predictions may coexist. Duplicate IDs, missing
  forecasts, changed decimals/timestamps and incorrect origins fail. A full
  500-row page reports incomplete because the endpoint has no pagination.
- `/history/coinbase-chart`: retain the original status/body. A truncated current
  chart reports incomplete; this is current-market data, not a historical
  market query. The evidence report preserves its status rather than claiming
  historical chart parity.
- `/history/context`: retain the original status/body. The actual route returns
  `status=unsupported`, empty outcomes and no linked evidence; this must remain
  honestly reported. It is not an outcome retrieval route.

Capture the reviewed #185 window separately using its existing raw reader and
receipt-verifying revision source. Retain the manifest and exact origin,
generation UUID, market, 15-minute boundaries, predictor cutoff, independent
label cutoff and artifact reference. Compare complete exact research scope,
inputs, saved features, saved forecasts, labels, links and coverage across all
three phases. Only retrieval provenance may change (local to authenticated
archive); it is still preserved in each full capture and its SHA-256. The report
also binds the entire bundle and each semantic research response by SHA-256.
Missing labels return INCOMPLETE; they are never manufactured. JSON floating
numbers are rejected: retain exact API string values and JSON integer counts.

Example offline command (output must not already exist):

```sh
python deploy/preprod/history_parity_evidence.py \
  --input backend/tests/fixtures/history_parity_two_generations.json \
  --output /tmp/history-capture-report.json
```

## Evidence and qualification

Five new tests pass. They execute existing #185 research composition through
collecting/sealed/model-retired states for two separate generated UUIDs and
request the real FastAPI HTTP routes using an explicitly generated backing
store. A committed immutable golden bundle checks the exact original inputs,
references, nanosecond source epochs and decimal strings. Regression cases
change decimals/source epochs/HTTP forecasts, remove rows, duplicate IDs,
remove labels and reject shortened source SHAs, missing phases, duplicate scopes
and float coercion. The CLI creates reports once and opens no connections.

Seven existing research unit tests and fifteen dashboard evidence tests also
pass. Sixteen existing application tests and the dashboard JavaScript contract
test also pass (44 passes total). Three native PG cases **skipped** across the
research/application suites, because this slice had
no explicit disposable `TRADEBOT_TEST_RESEARCH_DSN`. The generated repository's
model retirement is not a native DROP or two physical rotation cycles. The
underlying #185 native results remain prior evidence, not rerun evidence here.
No saved features/forecasts were recalculated. The generated golden test compares every exact decoded field, but projects only
`research.provenance.raw_pages[].sha256` to a hash-count-preserving sentinel:
compressed gzip bytes can differ with Python/zlib/platform builds. Actual capture
and report object hashes remain unchanged and validated; runtime archive checksum
verification is never bypassed. This corrects cross-platform CI golden failures
without normalizing source times, values, links, envelope hashes or raw payloads.

Golden source SHA denotes the
reviewed base contract, not an immutable deployed runtime identity.

Reproduce with FastAPI/httpx and existing backend dependencies installed:

```sh
python -m unittest discover -s backend/tests -p test_history_parity_evidence.py -v
python -m unittest discover -s backend/tests -p test_research_window.py -v
python -m unittest discover -s deploy/preprod/tests -p test_dashboard_evidence.py -v
```

## Live gaps / checkpoint remains open

1. Run two real complete 15-minute market pairs with separately bounded
   seal-to-removal evidence, and independently prove partition retirement,
   reader drainage and archive receipt/readback. This auditor grants no authority
   and does not authenticate captures.
2. #185 reads at most four 500-row raw pages per generation and has no indexed
   market/time subset; retained A's 28,411 raw rows exceed this prototype.
   Supply a separately reviewed bounded indexed reader before a real-window
   claim. Do not alter timestamps or silently select a convenient partial page.
3. `ResearchWindow` supports one generation per window. This slice compares two
   independent scopes, not a cross-generation market merge. A market crossing a
   switch needs a separately qualified merge keyed by origin and UUID.
4. Actual prediction HTTP output does not expose `snapshot_id`; #185 supplies
   the exact forecast→snapshot link. No HTTP snapshot-link claim is made.
5. Current chart reads raw local history and selects the active market. It has
   no archived market selector; after retirement, historical chart preservation
   needs an explicit qualified read path. Context evaluation/outcomes remains
   unsupported. Nonempty prediction history cannot substitute for these gaps.
6. Live official outcomes are currently absent. Wait for genuinely captured
   official labels, retain independent availability cutoffs and report missing
   labels. Exact saved-input parity is separate from deterministic recalculation,
   which remains unimplemented/unqualified here.

The committed generated golden and report qualify the evidence mechanism only.
They do not close checkpoint 3, a real PP trial, model reproducibility or the
30-minute retirement deadline.
