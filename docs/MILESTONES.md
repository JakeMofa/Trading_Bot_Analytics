# BTC Intelligence: live plan and status

Updated October 1, 2026. This is the short progress tracker. [STRATEGIC_PLAN.md](STRATEGIC_PLAN.md) holds the architecture and longer roadmap; the original handoff files are historical references.

## Goal

Build a local, read-only analysis system for Polymarket US BTC Up/Down markets. The current implementation focuses on 15-minute markets. Save source data, calculate reproducible signals, make measured forecasts, and compare them with confirmed outcomes. Add 1-hour support after the 15-minute path is reliable. Trading execution is deferred.

## Progress

- [x] **Milestone 1 — Data access and SQLite collector.** Discover the active 15-minute market and exact target, store Polymarket observations and Coinbase candles, join mid-session, reconcile delayed outcomes. Tests passed; pushed as `05ce7f4`.
- [x] **Milestone 2 — Live BTC streaming.** Save Coinbase ticker events with source times and deduplication; reconnect with backoff; keep public Polymarket REST discovery and settlement checks. A 25-second live test saved 102 ticker events; 16 tests passed; pushed as `e9fdd73`.
- [x] **Milestone 3 — Deterministic features.** Versioned 15-minute snapshots store exact target distance, remaining seconds, 1/5/15-minute returns, 15-minute realized volatility, 5/15-minute volume, source evidence, freshness and missing flags. Recent completed Coinbase candles refresh in one bounded request about once per minute; a one-minute lag is labeled. Live runs stored consecutive complete snapshots and verified the candle first-seen migration; 24 tests passed.
- [x] **Milestone 4 — Baseline forecasts and evaluation.** An untrained, versioned probability proxy saves live forecasts or abstentions against feature snapshots. The report evaluates one forecast per confirmed 15-minute market at T-10m, T-5m and T-1m, with Brier score, log loss, calibration counts, a 50/50 reference, and chronological splits after 30 distinct markets. A live rollover paired T-5m and T-1m forecasts with one confirmed DOWN outcome; 30 tests passed. This verifies the pipeline, not predictive skill.
- [ ] **Milestone 5 — More history and signals.** **Next.** Extend bounded candle backfill toward 30 days; add historical case matching and verified order-flow/book data. Measure whether each signal improves results.
- [ ] **Milestone 6 — News and OpenAI.** Ingest and deduplicate sourced events; send small, timestamp-safe context to OpenAI selectively; store its output separately and measure its contribution. Paid calls require configured API access and a spending limit.
- [ ] **Milestone 7 — Text and traversal memory.** Use SQLite FTS5 for news/explanations and relationship rows linking predictions to snapshots, events and outcomes. Numeric similarity remains feature-based.
- [ ] **Milestone 8 — Dashboard and 1-hour expansion.** Display market state, source health, forecasts, explanations and evaluation; apply the verified pipeline to 1-hour markets and measure them separately.

Each milestone is committed and pushed only after its relevant checks pass. Keep the code and this tracker synchronized.

## What the database contains today

The local `data/btc_intelligence.db` stores market records, Polymarket observations, one-minute Coinbase candles, streamed Coinbase ticker events, versioned feature snapshots and forecasts, feed health, and confirmed results. The latest inspection found 8 market records, 24 feature snapshots, 17 forecasts, 5 confirmed 15-minute outcomes, and 1 confirmed market paired with forecasts. The collector runs only when invoked; it is not a background service.

## Active multi-market test

An eight-hour bounded, read-only `streaming.py --seconds 28800` run started October 1, 2026 at about 01:53 UTC and is expected to end near 09:53 UTC if the Mac remains awake and the process remains active. Its ignored local log is `data/soak_20261001.log`. The first cycle saved a complete feature snapshot and forecast. After it ends, inspect market rollover, missing/stale coverage, confirmed-result pairing, database integrity and the checkpoint evaluation report. The run's outcome is not yet known.

## Open verification

- One continuous run crossed a real 15-minute boundary: the expired market was reconciled after a brief discovery gap, and collection followed the next active contract. Repeated rollover and prolonged-outage recovery still need measurement.
- The optional Polymarket market WebSocket requires locally configured API keys and has not been live-tested. Public REST access works without login.
- Long-running storage retention and recovery after prolonged outages have not been measured.
- Only one confirmed market has paired forecasts so far. Accuracy and calibration are not established; chronological splits require at least 30 distinct confirmed markets per checkpoint.
- News, FTS5, traversal, and dashboard layers do not exist yet. Feature and forecast coverage depends on fresh public data; snapshots retain missing and lag flags when feeds fall behind. The forecast baseline is untrained and uncalibrated.

## Decisions and evidence

- **Start with 15-minute markets.** The user chose this order; saved 1-hour data remains intact for later work.
- **Keep settlement separate from exchange prices.** Polymarket's BRTI result determines the label; Coinbase BTC/USD is a predictive reference feed.
- **Use one SQLite database initially.** It already stores the numerical evidence; relationship and FTS5 tables will join it when those layers are built.
- **Separate public and authenticated access.** Public Polymarket REST feeds the current collector. Its market WebSocket requires API-key authentication according to official documentation, so it remains optional.
- **Commit each milestone.** The user requested GitHub commits and pushes after tested milestones.

## Run and validate

From the project root, run `.venv/bin/python -m unittest discover -s backend/tests -v`, then `.venv/bin/python backend/app/streaming.py --seconds 60` for a bounded live check. See [README.md](../README.md) for setup. Inspect SQLite `feed_health`, `runs`, `feature_snapshots`, and `predictions` before declaring a live feed healthy.
