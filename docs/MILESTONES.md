# BTC Intelligence: live plan and status

Updated September 30, 2026. This is the short progress tracker. [STRATEGIC_PLAN.md](STRATEGIC_PLAN.md) holds the architecture and longer roadmap; the original handoff files are historical references.

## Goal

Build a local, read-only analysis system for Polymarket US BTC Up/Down markets. The current implementation focuses on 15-minute markets. Save source data, calculate reproducible signals, make measured forecasts, and compare them with confirmed outcomes. Add 1-hour support after the 15-minute path is reliable. Trading execution is deferred.

## Progress

- [x] **Milestone 1 — Data access and SQLite collector.** Discover the active 15-minute market and exact target, store Polymarket observations and Coinbase candles, join mid-session, reconcile delayed outcomes. Tests passed; pushed as `05ce7f4`.
- [x] **Milestone 2 — Live BTC streaming.** Save Coinbase ticker events with source times and deduplication; reconnect with backoff; keep public Polymarket REST discovery and settlement checks. A 25-second live test saved 102 ticker events; 16 tests passed; pushed as `e9fdd73`.
- [ ] **Milestone 3 — Deterministic features.** Save feature snapshots linked to a market: distance from Price to Beat, seconds remaining, recent returns, volatility, and volume. Include source time, freshness, and missing-data flags. Reproduce values from saved inputs and test late joins and stale feeds. **Next.**
- [ ] **Milestone 4 — Baseline forecasts and evaluation.** Save versioned probabilities and compare them with confirmed outcomes using chronological splits, Brier score and calibration. Keep 15-minute market outcomes as the unit of evaluation.
- [ ] **Milestone 5 — More history and signals.** Extend bounded candle backfill toward 30 days; add historical case matching and verified order-flow/book data. Measure whether each signal improves results.
- [ ] **Milestone 6 — News and OpenAI.** Ingest and deduplicate sourced events; send small, timestamp-safe context to OpenAI selectively; store its output separately and measure its contribution. Paid calls require configured API access and a spending limit.
- [ ] **Milestone 7 — Text and traversal memory.** Use SQLite FTS5 for news/explanations and relationship rows linking predictions to snapshots, events and outcomes. Numeric similarity remains feature-based.
- [ ] **Milestone 8 — Dashboard and 1-hour expansion.** Display market state, source health, forecasts, explanations and evaluation; apply the verified pipeline to 1-hour markets and measure them separately.

Each milestone is committed and pushed only after its relevant checks pass. Keep the code and this tracker synchronized.

## What the database contains today

The local `data/btc_intelligence.db` stores market records, Polymarket observations, one-minute Coinbase candles, streamed Coinbase ticker events, feed health, and confirmed results. During the last verified run, the database contained 1,440 one-minute candles and two confirmed 15-minute outcomes. The collector runs only when invoked; it is not a background service.

## Open verification

- A continuous run spanning a real 15-minute boundary is still needed; restart-based discovery across a boundary has been observed.
- The optional Polymarket market WebSocket requires locally configured API keys and has not been live-tested. Public REST access works without login.
- Long-running storage retention and recovery after prolonged outages have not been measured.
- The feature, forecast, news, FTS5, traversal, and dashboard layers do not exist yet.

## Decisions and evidence

- **Start with 15-minute markets.** The user chose this order; saved 1-hour data remains intact for later work.
- **Keep settlement separate from exchange prices.** Polymarket's BRTI result determines the label; Coinbase BTC/USD is a predictive reference feed.
- **Use one SQLite database initially.** It already stores the numerical evidence; relationship and FTS5 tables will join it when those layers are built.
- **Separate public and authenticated access.** Public Polymarket REST feeds the current collector. Its market WebSocket requires API-key authentication according to official documentation, so it remains optional.
- **Commit each milestone.** The user requested GitHub commits and pushes after tested milestones.

## Run and validate

From the project root, run `.venv/bin/python -m unittest discover -s backend/tests -v`, then `.venv/bin/python backend/app/streaming.py --seconds 60` for a bounded live check. See [README.md](../README.md) for setup. Inspect SQLite `feed_health` and `runs` before declaring a live feed healthy.
