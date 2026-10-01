# BTC Intelligence: live plan and status

Updated October 1, 2026. This is the short progress tracker. [STRATEGIC_PLAN.md](STRATEGIC_PLAN.md) holds the architecture and longer roadmap. [PLAN_CROSSWALK.md](PLAN_CROSSWALK.md) maps every phase of the original handoff to current implementation; the original documents remain unchanged.

## Goal

Build a local, read-only analysis system for Polymarket US BTC Up/Down markets. The current implementation focuses on 15-minute markets. Save source data, calculate reproducible signals, make measured forecasts, and compare them with confirmed outcomes. Add 1-hour support after the 15-minute path is reliable. Trading execution is deferred.

## Progress

- [x] **Milestone 1 — Data access and SQLite collector.** Discover the active 15-minute market and exact target, store Polymarket observations and Coinbase candles, join mid-session, reconcile delayed outcomes. Tests passed; pushed as `05ce7f4`.
- [x] **Milestone 2 — Live BTC streaming.** Save Coinbase ticker events with source times and deduplication; reconnect with backoff; keep public Polymarket REST discovery and settlement checks. A 25-second live test saved 102 ticker events; 16 tests passed; pushed as `e9fdd73`.
- [x] **Milestone 3 — Deterministic features.** Versioned 15-minute snapshots store exact target distance, remaining seconds, 1/5/15-minute returns, 15-minute realized volatility, 5/15-minute volume, source evidence, freshness and missing flags. Recent completed Coinbase candles refresh in one bounded request about once per minute; a one-minute lag is labeled. Live runs stored consecutive complete snapshots and verified the candle first-seen migration; 24 tests passed.
- [x] **Milestone 4 — Baseline forecasts and evaluation.** An untrained, versioned probability proxy saves live forecasts or abstentions against feature snapshots. The report evaluates one forecast per confirmed 15-minute market at T-10m, T-5m and T-1m, with Brier score, log loss, calibration counts, a 50/50 reference, and chronological splits after 30 distinct markets. A live rollover paired T-5m and T-1m forecasts with one confirmed DOWN outcome; 30 tests passed. This verifies the pipeline, not predictive skill.
- [ ] **Milestone 5 — More history and signals.** **In progress.** Coinbase's 30-day candle backfill stored 43,200/43,200 completed minutes. The 30-day Polymarket US scan completed 90/90 eight-hour chunks: 795/2,880 expected 15-minute intervals had resolved markets, with 12,694 stored book-derived display-price points. The earliest returned market starts September 22 at 15:15 UTC; 2,065 expected intervals precede it, and 20 gaps occur after it. Three transient price-history failures were retried successfully; the checkpoint now reports zero request failures. Timestamp-safe matching selects one live snapshot per prior resolved market and links the observation that established its known outcome. Next: inspect the 20 within-range gaps and measure whether matches improve later-market results. Full historical order books and trades are not represented by display-price history.
- [ ] **Milestone 6 — News and OpenAI.** **News ingestion started.** A read-only CoinDesk RSS collector stores headlines, links, categories, publisher publication times, and local first-seen times. The first pass saved 25 items, 8 tagged BTC; a second pass deduplicated all 25. A six-hour bounded poll checks every ten minutes in a separate local process. Next: inspect feed freshness and coverage, add timestamp-safe event retrieval to analysis, then compare its contribution. OpenAI calls remain deferred pending configured API access and a spending limit.
- [ ] **Milestone 7 — Text and traversal memory.** **In progress.** FTS5 headline search is built. Typed SQLite links now trace a prediction to its snapshot and retrospectively eligible news/prior cases, with source IDs and availability times. These links explicitly do not mean the baseline model used the context. Next: connect real analysis outputs and evaluate whether retrieved evidence adds value.
- [ ] **Milestone 8 — Dashboard and 1-hour expansion.** Display market state, source health, forecasts, explanations and evaluation; apply the verified pipeline to 1-hour markets and measure them separately.

Each milestone is committed and pushed only after its relevant checks pass. Keep the code and this tracker synchronized.

## What the database contains today

The local `data/btc_intelligence.db` stores market records, Polymarket observations, one-minute Coinbase candles, streamed Coinbase ticker events, versioned feature snapshots and forecasts, retrospective market display-price history, feed health, confirmed results, and now sourced news headline references. The 30-day Coinbase backfill reports 43,200 complete minute candles. Live collection and news polling are local processes started by commands; neither is deployed to a separate server or installed as a background service.

## Active multi-market test

An eight-hour bounded, read-only `streaming.py --seconds 28800` run started October 1, 2026 at about 01:53 UTC and is expected to end near 09:53 UTC if the Mac remains awake and the process remains active. Its ignored local log is `data/soak_20261001.log`. The first cycle saved a complete feature snapshot and forecast. A read-only `backend/app/audit.py --since 2026-10-01T01:53:00Z` report is available for coverage, rollover, failures and integrity; its filter excludes older markets visited only for delayed resolution. The report and tests passed while collection continued (32 total tests). After the run ends, inspect the complete audit and checkpoint evaluation report. The run's outcome is not yet known.

A separate resumable `history_batch.py --days 30 --end 2026-10-01T03:00:00Z` run scanned the 30 days before 03:00 UTC on October 1 and has finished. Its ignored log is `data/polymarket_30d_backfill.log`; chunk results are checkpointed in SQLite. The price-history retry completed and SQLite `quick_check` is `ok`. The eight-hour live test still needs the Mac awake.

A separate `news.py --seconds 21600 --interval 600` run began around 03:31 UTC on October 1. Its ignored local log is `data/news_20261001.log`. It needs the Mac awake and is independent of the live market collector.

## Open verification

- One continuous run crossed a real 15-minute boundary: the expired market was reconciled after a brief discovery gap, and collection followed the next active contract. Repeated rollover and prolonged-outage recovery still need measurement.
- The optional Polymarket market WebSocket requires locally configured API keys and has not been live-tested. Public REST access works without login.
- Long-running storage retention and recovery after prolonged outages have not been measured.
- The latest report had eight confirmed markets with forward predictions, with only five to seven eligible at each checkpoint. Accuracy and calibration are not established; chronological splits require at least 30 distinct confirmed markets per checkpoint.
- Historical case matching is exploratory and unevaluated. News ingestion, FTS5 search and eligible-context links exist, but the baseline does not use news or cases. OpenAI analysis and the dashboard do not exist yet. Feature and forecast coverage depends on fresh public data; snapshots retain missing and lag flags when feeds fall behind. The forecast baseline is untrained and uncalibrated.

## Next implementation: news and evidence memory

The first publisher RSS source was verified and ingested. Next measure its freshness and BTC relevance over repeated polls, then link only events observed before a forecast. Add FTS5 search and persisted evidence relationships after the event schema is stable. OpenAI analysis remains a later optional layer; no paid calls have been made. Continue evaluating the numerical baseline and case matching independently while news ingestion runs.

## Decisions and evidence

- **Start with 15-minute markets.** The user chose this order; saved 1-hour data remains intact for later work.
- **Keep settlement separate from exchange prices.** Polymarket's BRTI result determines the label; Coinbase BTC/USD is a predictive reference feed.
- **Use one SQLite database initially.** It already stores the numerical evidence; relationship and FTS5 tables will join it when those layers are built.
- **Separate public and authenticated access.** Public Polymarket REST feeds the current collector. Its market WebSocket requires API-key authentication according to official documentation, so it remains optional.
- **Commit each milestone.** The user requested GitHub commits and pushes after tested milestones.

## Run and validate

From the project root, run `.venv/bin/python -m unittest discover -s backend/tests -v`, then `.venv/bin/python backend/app/streaming.py --seconds 60` for a bounded live check. See [README.md](../README.md) for setup. Inspect SQLite `feed_health`, `runs`, `feature_snapshots`, and `predictions` before declaring a live feed healthy.
