# BTC Intelligence

Read-only Polymarket US BTC collector, currently focused on 15-minute markets. No orders, account credentials or OpenAI calls. The basic collector uses the Python standard library; streaming uses the pinned dependencies in `backend/requirements.txt`.

Run from this project folder:

```sh
python3 -m unittest discover -s backend/tests -v
python3 backend/app/collector.py --backfill-hours 24
python3 backend/app/collector.py --cycles 10 --interval 30
```

The default duration is 15 minutes. Hourly collection is deferred; saved hourly records remain intact. Explicit `--duration 1h` or `--duration both` options retain support for later use.

The default database is `data/btc_intelligence.db`. Each invocation is bounded and exits; nothing starts automatically. Errors are recorded in `runs` and printed. Historical candles come from Coinbase and are predictive reference data, not BRTI settlement prices. Coverage reports expose missing candles.

The basic collector polls market metadata and quotes every 30 seconds by default. The streaming command receives live Coinbase updates. Versioned feature snapshots are saved during streaming; forecasts, UI, FTS5/traversal and OpenAI analysis are later milestones. Restart discovery after a boundary has been observed; uninterrupted rollover still needs verification.

Official terms determine each interval, not `startDate`/`endDate`. The collector selects `assetPriceTerms.windowStart/windowEnd`, preserves exact decimal target strings and only labels outcomes from resolved market terms. First-seen timestamps record late capture. Previous expired markets reconcile independently while the next active market is discovered.

See `docs/DATA_ACCESS_FINDINGS.md` and `docs/STRATEGIC_PLAN.md`.

## Streaming milestone

Install once:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python -m unittest discover -s backend/tests -v
```

Run a bounded one-minute collection or explicitly collect until Ctrl+C:

```sh
.venv/bin/python backend/app/streaming.py --seconds 60
.venv/bin/python backend/app/streaming.py --seconds 0
```

Public Coinbase BTC ticker events stream continuously and are deduplicated by trade ID. Each event preserves source and receive timestamps, price, size and source-provided side; side must not yet be interpreted as aggressive buying/selling pressure. Connection failures reconnect with capped exponential delay and resubscribe. Feed state distinguishes connecting, awaiting data, live, stale, disconnected, disabled and stopped. REST remains at 30-second intervals for market discovery, quotes and pending settlement; transient HTTP errors and 429 responses have bounded backoff. No order routes are implemented.

Polymarket WebSocket requires `POLYMARKET_KEY_ID` and `POLYMARKET_SECRET_KEY` environment variables. Set them locally using your secret manager/shell; never paste them into chat or commit them. `.env.example` lists names but is not automatically loaded. Without keys, that stream is explicitly disabled while public REST continues. The authenticated adapter signs each handshake and reopens its market subscription on rollover. Its live protocol remains unverified until credentials are configured.

Data remains local and ignored by Git. Ctrl+C closes the streams; shutdown may wait for an in-flight REST request. Raw streaming retention is not yet automatic: monitor database size before unattended multi-day runs. Nothing starts on boot or keeps running after a bounded command exits.

## Milestone commits

The user requested a tested commit and push for each completed milestone. See `docs/MILESTONES.md` for progress and outstanding verification.

## Feature snapshots

Every streaming REST cycle saves a `feature_snapshots` row for the active 15-minute market when its metadata was already observed. The row contains exact decimal target distance, time remaining, completed-candle returns, realized volatility, volume, input IDs/times, and explicit missing/freshness flags. Calculations use only records received by the snapshot time; the snapshot also records the candle inputs it used. Existing candle rows from before this schema change have unknown first-seen times and become eligible for new snapshots only after they are refreshed. The Coinbase reference price is a predictive input, never the Polymarket settlement price.

The supervisor refreshes the last 20 completed Coinbase one-minute candles at startup and approximately once per minute in one bounded public request. A one-minute candle delay is labeled `lagging`; older/missing windows leave dependent fields null. Quote and candle refresh failures are recorded in `runs`. A late start does not claim earlier Polymarket book coverage. Inspect recent rows with `sqlite3 data/btc_intelligence.db 'SELECT market_id,as_of,values_json,quality_json FROM feature_snapshots ORDER BY id DESC LIMIT 3;'`.

## Baseline forecasts and evaluation

The streaming supervisor now saves one `predictions` row per feature snapshot, including abstentions when a required input is stale or missing. `gaussian_distance_v1` is an **untrained, uncalibrated proxy**: it combines the Coinbase reference price, Polymarket target, time remaining and recent one-minute return volatility under a zero-drift normal log-return assumption. Polymarket settles with BRTI, so this probability is not a verified trading edge or a buy/sell instruction. The model stores its assumptions and source snapshot; forecasts are only issued while their market is live.

Inspect market-grouped evaluation after confirmed outcomes arrive:

```sh
.venv/bin/python backend/app/forecasts.py --report
```

The report selects at most one forecast per market near each of T-10m, T-5m and T-1m (within 30 seconds). It compares Brier score, log loss and directional accuracy with a 50/50 baseline, shows calibration counts, and reports abstentions. Chronological 60/20/20 blocks appear only once a checkpoint has at least 30 distinct confirmed markets. Until then, scores are preliminary and the report says when there are no paired results. More live sessions are needed before drawing any accuracy conclusion.

## Audit a bounded collection run

Use the read-only audit command during or after a run:

```sh
.venv/bin/python backend/app/audit.py --since 2026-10-01T01:53:00Z
```

Add `--until <UTC ISO timestamp>` to freeze the reporting window. The report counts distinct 15-minute market windows, rollovers, confirmed results by the window end, complete/missing/stale snapshots, forecast abstentions, source failures, large snapshot gaps, and SQLite integrity. It excludes old contracts that were only revisited for delayed resolution. It does not score probabilities; run `forecasts.py --report` for the confirmed-outcome evaluation. The audit opens SQLite in read-only mode and does not alter the live collector.

## Retrospective history (separate from live evidence)

Completed Coinbase BTC/USD minute candles can be filled quickly in bounded public requests:

```sh
.venv/bin/python backend/app/collector.py --backfill-hours 8 --cycles 1
```

Past Polymarket US 15-minute targets, confirmed results, and book-derived Yes/No **display-price history** are fetched separately:

```sh
.venv/bin/python backend/app/historical.py --hours 8
.venv/bin/python backend/app/historical.py --hours 8 --end 2026-10-01T02:00:00Z
```

The second form selects an older UTC chunk; each run is capped at eight hours and reports missing intervals and endpoint failures. The first verified chunk found 32/32 resolved markets and saved 512 display-price points. Price history is not a record of every trade or full order-book depth. Retrospective rows retain their retrieval time; they cannot be used to claim that a forecast was made before the outcome. Continue the live collector to measure real rollover, feed health and genuinely forward forecasts.
