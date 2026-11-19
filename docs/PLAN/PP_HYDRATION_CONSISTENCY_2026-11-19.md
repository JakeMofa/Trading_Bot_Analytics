# PP saved forecast hydration consistency

Source-only candidate based on preprod
`c1da8d688dd8e9b860c473c965feb9099435ef97`. Keep unmerged during the PP21
change freeze. No schema, release, host, cloud or collection action is included.

## Reproduced behavior

`Store.hydrate()` previously selected the latest feature and latest prediction
in independent statements under PostgreSQL's default read-committed isolation.
A native test executed the feature read, committed a second real calculation
through an independent writer connection, then allowed hydration to continue.
The old code returned the first snapshot with the second prediction. A second
case inserted a newer feature without a prediction and observed hydration borrow
the older forecast. Both cases failed on the base source and pass with this fix.

The schema already enforces the prediction's composite foreign key to
`(origin_id,snapshot_id,market_id,as_of)`. One SQL statement now selects the latest
feature and uses a lateral left join for that exact snapshot's prediction. This
uses one statement snapshot without changing connection isolation or acquiring
writer locks. Latest-feature ordering and deterministic prediction-ID ordering
remain explicit. A latest feature without a prediction returns null, and a saved
abstention retains null probabilities and its reason. Native numeric columns
still pass through the existing lossless decimal conversion.

The API hydration consumer and SSE contract are unchanged. The RAM test verifies
that the resulting published snapshot and forecast retain the same snapshot ID;
existing API, real HTTP/SSE reconnect, expiry and rollover tests also pass. Live
tick estimates deliberately remain separate from the saved evaluation record.

The chart endpoint returns `truncated`, but its summary looked for
`sample_limited`. The JavaScript regression executes the actual chart-summary
function against capped, complete and empty response shapes. It fails with the
base dashboard and passes with the corrected property.

## Validation

- Three new native hydration regressions: interleaved committed publication,
  newer feature without prediction, and empty/abstaining forecast states. Exact
  Coinbase decimal text and subsequent reads of the newly committed pair are
  also checked.
- One JavaScript execution regression for the chart coverage warning.
- Disposable local PostgreSQL 17.2, foundation and all business migrations,
  restricted `tradebot_app`/`tradebot_lifecycle` logins: all 23 tests in
  `test_postgres_hydration_consistency`, `test_postgres_application`,
  `test_postgres_live_query_parity`, and `test_postgres_dashboard_contract` passed
  with no skips. No external feed or existing database was used.
- Full backend discovery: 396 tests, 342 passed and 54 environment-dependent
  skips. Native runs above separately exercise the affected database cases.
- `git diff --check` passed.

Reproduce with disposable, migrated local PostgreSQL and
`TRADEBOT_TEST_APP_DSN`, `TRADEBOT_TEST_LIFECYCLE_DSN`, and `TRADEBOT_TEST_DSN`
pointing to its restricted logins:

```sh
PYTHONPATH=backend:backend/tests python -m unittest \
  test_postgres_hydration_consistency test_postgres_application \
  test_postgres_live_query_parity test_postgres_dashboard_contract -v
```

The chart execution test requires Node.js. Missing DSNs or Node produce explicit
skips rather than invented validation. Existing generated PostgreSQL CI discovers
these `test_postgres*.py` cases and rejects skipped integration qualification.

## Local query cost and limits

A generated fixture contained 10,001 feature/prediction pairs for one market.
Fifty warmed samples used a single Unix-socket connection, excluding connection
setup, price/quote reads, API work and network latency. The old two-SELECT path
measured 0.222 ms median, 0.363 ms p95, 0.580 ms maximum. The linked SELECT
measured 0.089 ms median, 0.271 ms p95, 0.297 ms maximum.

`EXPLAIN (ANALYZE, BUFFERS)` reported 0.799 ms planning and 0.105 ms execution.
The feature scan used the existing
`feature_snapshots_origin_id_market_id_as_of_version_key` index (two rows),
followed by incremental sort/limit. The prediction scan used
`predictions_origin_id_snapshot_id_model_version_key` (one row), followed by
sort/limit. No index or migration is introduced. These observations are fixture
evidence, not a PP runtime performance guarantee.

The change guarantees the saved feature/prediction pair, not a single atomic
snapshot of price, quote, market discovery and all dashboard history. It does not
establish historical replay, publication-time retrieval, official outcome
reconciliation, calibration, ensemble migration or AI support. Those remain
separate parity gates.
