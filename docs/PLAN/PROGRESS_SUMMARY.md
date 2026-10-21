# BTC Intelligence — progress summary

Prepared October 7, 2026 from project docs and commit history. Live evidence below was recorded October 1–2; these are not fresh counts of today's database or confirmation that collection is running now.

We have built a local, read-only collection and analysis system for **Polymarket US BTC 15-minute markets**. It saves evidence, calculates signals, produces experimental forecasts, evaluates confirmed outcomes, and displays a live dashboard. Predictive skill and a trading edge remain unproven.

## What is completed

| Area | What we have built |
| --- | --- |
| Market discovery | Active 15-minute contract discovery, exact targets and official session boundaries, rollover, mid-session joining, and delayed-outcome reconciliation. |
| Storage | SQLite evidence for markets, quotes/books, candles/ticks, features, forecasts, results, history, feed health, and headlines. Exact decimals, provenance, timestamps, and missing data are preserved. |
| Live feeds | Coinbase BTC/USD streaming with deduplication/reconnects; public Polymarket US REST; authenticated read-only Polymarket US market-data WebSocket. |
| Calculations | Target distance, time remaining, 1/5/15-minute returns, realized volatility, volume, freshness flags, and links to source evidence. |
| Forecast baseline | Versioned, untrained and uncalibrated price/time/volatility probability proxy; saves forecasts or abstains when required inputs are unavailable. |
| Evaluation | Market-grouped T-10m/T-5m/T-1m checkpoints, Brier score, log loss, calibration, accuracy, 50/50 comparison, and chronological score blocks. |
| Dashboard | Current market, Coinbase chart and target line, direct UP/DOWN quotes, tick-updated experimental estimate, saved forecasts, feed ages, outcomes, news, and context links. |
| Operations | Controlled start/stop/restart, duplicate-collector prevention, configurable 2 GiB database-plus-WAL stop ceiling, validated online backup, and recovery into a separate database. |

Coinbase is a predictive reference. Polymarket's BRTI-based confirmed outcomes supply official labels; the Coinbase chart does not reproduce the BRTI chart.

## Recorded results

- **Live run:** 33 observed markets, 32 consecutive rollovers, no missing internal market starts, 923 complete snapshots, and 923 forecasts with no abstentions. There were 32 confirmed outcomes by the window end and one 150-second snapshot gap during an accepted restart.
- **Coinbase history:** 43,200/43,200 completed one-minute candles in the 30-day backfill.
- **Polymarket history:** 90/90 chunks scanned, 795 resolved markets and 12,694 display-price points saved. Of 2,880 expected intervals, 2,065 precede the earliest returned market and 20 are unavailable within the returned range. This is not full historical trade or book data.
- **Preliminary evaluation:** 31/33/32 distinct markets at T-10m/T-5m/T-1m; baseline Brier scores 0.208/0.131/0.003 versus 0.25 for 50/50. The small sample does not establish future accuracy or profitability.
- **Operations validation:** 67 tests passed on October 2. Live backup and recovered copies each preserved 850 markets, 241,726 stream events, 1,587 snapshots, 1,580 predictions, and 28 news events. Integrity and foreign-key checks passed.

## What is partly built

- **Historical matching:** timestamp-safe retrieval chooses one eligible case per prior resolved market. Its initial retrospective probability comparison performed worse than the price baseline; it is not part of the live forecast.
- **News:** CoinDesk RSS collection, deduplication, BTC tagging, and publication/first-seen timestamps exist. The recorded poll was bounded, and delays were too large to claim a timely 15-minute signal.
- **Memory:** FTS5 headline search and typed evidence links exist. Retrospective context links do not mean the baseline used news or cases.
- **Dashboard additions:** existing uncommitted edits add a “Plan & progress” dialog reading the milestone checklist. These are separate from committed milestones and were not validated for this summary.

## What remains

1. Improve and measure news timeliness before testing its forecast contribution.
2. Investigate historical availability gaps and compare signals on later distinct markets, reserving holdout data.
3. Verify additional exchange, trade/book, and optional derivatives inputs; measure incremental value.
4. Configure API access and a spending cap before OpenAI calls; store and evaluate independent analysis outputs.
5. Train/calibrate models when enough independent labels exist, then evaluate an ensemble.
6. Improve 15-minute quality displays and investigate licensed BRTI access; validate hourly support later.
7. Define retention, scheduled backups, and persistent deployment when authorized.

Buying/selling, account changes, paid AI calls, and hourly collection remain deferred. Collection depends on the local Mac staying awake; no boot service or separate server is installed. The storage ceiling stops collection without deleting evidence. No additional eight-hour soak is planned.

## Project references

- [README](../README.md): setup and commands.
- [MILESTONES](MILESTONES.md): live checklist, detailed evidence, decisions, and next work.
- [STRATEGIC_PLAN](STRATEGIC_PLAN.md): architecture and longer roadmap.
- [PLAN_CROSSWALK](PLAN_CROSSWALK.md): original handoff mapped to current implementation.
- [DATA_ACCESS_FINDINGS](DATA_ACCESS_FINDINGS.md): verified sources and unsupported fields.

The milestone checklist remains the live implementation tracker.
