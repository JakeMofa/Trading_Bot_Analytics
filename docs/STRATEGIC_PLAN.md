# BTC Intelligence — Strategic Plan

Prepared September 29, 2026. Status: planning; implementation and order execution have not started.
Project folder: `/Users/jake/Documents/Trading_bot_Analytics/`.

## 1. Objective and scope

Build a local analysis and forecasting application for Polymarket US BTC 15-minute and 1-hour markets. For each active contract, identify the target, track time remaining, compute probabilities, explain the signals, save the evidence, and evaluate against confirmed outcomes. Buy/sell execution is deferred.

The user’s current direction takes precedence over older handoff documents. Those documents remain historical references. Support both durations, share feeds where practical, and evaluate each duration separately. Neither document instructions nor this plan authorize account changes or orders.

## 2. What we know and what remains unverified

Screenshots show completed and active 15-minute markets, Price to Beat, timer, UP/DOWN quotes, and account UI. Go Live can jump several intervals from an old URL to the currently active market. Login in a screenshot does not establish API authentication requirements.

Official Polymarket US documentation describes read-only reference data, quotes, order books, and REST/gRPC interfaces. Specific BTC contract fields, retail versus institutional access, onboarding, costs, target availability, settlement source, and 1-hour discovery are not yet verified through actual API responses. Do not substitute international Polymarket endpoints for Polymarket US.

Coinbase documents historical candles and live streaming. Historical candles may contain gaps, require bounded batches, and cannot reconstruct past order books or exact Polymarket settlements.

## 3. Architecture and responsibility boundaries

External sources → adapters → normalization/data health → shared BTC state and per-market sessions → SQLite evidence → feature calculations → numerical forecasts → optional historical/event retrieval and OpenAI analysis → dashboard and evaluation.

- Source adapters obtain data and handle source-specific reconnects and limits.
- Normalization records source event time and local receive time, units, symbols, and provenance.
- Session management owns market identity, duration, target, lifecycle, and rollover.
- Calculations maintain rolling windows without an LLM.
- Numerical models estimate probabilities; historical matching contributes an independently measurable signal.
- OpenAI interprets compact features, selected examples and events. It is asynchronous and optional; feed collection and basic forecasts continue during API failure.
- Storage preserves evidence, versions, availability and results.
- Retrieval combines numerical similarity, text search and relationship traversal.
- Our FastAPI API serves the dashboard; external APIs belong to ingestion.

An exchange price is a predictive input, not automatically the official settlement value. Equality rules and settlement definitions must be read from each contract’s rules. UP/DOWN displayed quotes are prices, not necessarily complementary calibrated probabilities: store bid/ask/last and the method used to calculate a comparison probability.

## 4. Phase A — Read-only feasibility research (start here)

Deliver `docs/DATA_ACCESS_FINDINGS.md` and sanitized response samples under `research/samples/`. Use small read-only checks rather than build an application.

For each Polymarket duration:
1. Identify the applicable API and onboarding/authentication route.
2. Locate a current live contract and record stable IDs, slug, start/end times, status and outcome identifiers.
3. Retrieve the exact target and document its source, precision and availability time.
4. Read settlement rules, benchmark source, equality behavior and resolution timing.
5. Obtain quotes/order-book samples and identify streaming access.
6. Discover the next active interval from an outdated market reference.
7. Retrieve at least one completed contract’s confirmed outcome.
8. Determine historical coverage and missing fields.
9. Record rate limits, credentials required, costs and usage constraints for the exact route tested.

For one BTC exchange, initially Coinbase as a candidate:
- Fetch a small bounded candle sample, inspect timestamps/schema/gaps.
- Receive a short live trade stream and compare event/receive timestamps.
- Verify streaming health/reconnect approach and historical batch limits.

Record every field as verified, unavailable, or unresolved, with evidence date. Never put credentials, account balances, cookies or private account responses in samples.

Completion gate: enough verified information exists to track a real session and its outcome. A missing exact target or settlement source is a documented blocker for official-contract evaluation, not a reason to invent values. If 1-hour access remains unresolved, report it and keep that work explicit rather than silently claiming support.

## 5. Phase B — Minimum collector and SQLite

Create backend foundations only after Phase A. Build one verified Polymarket connector and one exchange connector. Add discovery, mid-session join, live observations, limited recent backfill and persistent history together.

Session states: discovered, scheduled, active, expired/pending result, resolved; support corrected or unavailable outcomes where applicable. Never wait for old settlement before following the next live contract. Reconcile pending results separately. Startup discovers the currently live market, rather than incrementing an old URL. Feed reconnects are idempotent and deduplicate events where IDs exist.

Store source time, receive time, stale/missing state and capture coverage. Late joining does not imply that missing historical trades or books can be recovered. Missing signals remain missing; they must not appear as neutral or zero.

Completion gate: repeated session rollover, a mid-session start, restart recovery, no duplicate market records, saved confirmed outcome, and honest feed-health status. Use focused tests for session boundaries, delayed resolution and duplicate/reordered events.

## 6. Historical data policy

- Immediate context: fetch the recent 24 hours of available minute candles, then expand in bounded batches toward 30 days.
- Seconds-level momentum/order flow: use live trades or separately verified historical trades; minute candles cannot supply subminute detail.
- 7–30 days: initial recent-regime exploration and numerical comparisons.
- Months/years of candles: optional broader regime and stress testing once the first pipeline is sound.
- Polymarket history: verified targets, quotes and outcomes where obtainable; collect our own detailed session evidence from the beginning.

Exchange-candle simulations are proxy experiments and must be labeled separately from official Polymarket outcomes. Thirty days is an initial collection target, not a guarantee of enough independent data. Multiple snapshots of one market share an outcome. Shared BTC conditions also correlate overlapping 15-minute and 1-hour markets.

Do not delay live collection until a huge download completes. Backfill is resumable, rate-limited and separate from the live path.

## 7. SQLite storage design

Use one local database with schema migrations and stable keys. Keep source identifiers and duration on every market.

| Table | Purpose |
|---|---|
| markets | Source IDs, duration, boundaries, rules reference, target provenance, lifecycle |
| candles | Source/symbol/granularity/time OHLCV; unique identity and gap tracking |
| observations | Timestamped Polymarket quotes and exchange reference observations |
| feature_snapshots | Versioned numeric state, missing flags, source freshness, session linkage |
| predictions | Market, snapshot, probabilities, model version, forecast time/horizon |
| outcomes | Confirmed/corrected settlement and result, source, confirmation time |
| model_outputs | Specialist outputs linked to a prediction and model version |
| events | News/event source, publication/ingestion times, text and deduplication identity |
| ai_analyses | Input references, structured output, model/prompt version, usage, latency, errors |
| relationships | Typed source/target IDs, relation, provenance and creation time |
| ingestion_runs | Checkpoints, backfill coverage, failures and feed health |

Introduce tables when their phase needs them. Avoid storing the same wide feature data twice without a purpose. Use foreign keys for ordinary associations; generic relationships are additional evidence links, not a replacement for integrity constraints.

FTS5 later indexes approved stored text such as headlines, summaries, analyst explanations and failure notes. Numerical matching uses standardized numeric features, not text embeddings. Relationship examples: prediction USED_SNAPSHOT snapshot; analysis CONSIDERED_EVENT event; prediction SIMILAR_TO prior resolved case. Relationships are associations and must not imply causation.

## 8. Phase C — Deterministic features and baseline

Begin with target distance, percentage distance, remaining time, duration, returns, realized volatility and volume. Each feature has defined units, lookback, timestamp semantics and a version. Show coverage and freshness with every forecast.

Establish a simple target/time/volatility baseline before adding ML complexity. Train a logistic model and then compare XGBoost only when labeled coverage supports it. Do not fabricate a trained probability from an untrained model. Abstain or display unavailable when required inputs are stale, absent or incompatible with the settlement source.

Completion gate: reproducible calculations from stored snapshots; predictions saved with complete version/provenance; baseline reports separated by market duration and time remaining.

## 9. Phase D — Evaluation from the first prediction

Do not defer evaluation until after the meta-model. Use chronological train/validation/test periods, group snapshots by market, and ensure overlapping horizons near split boundaries do not leak information. Fit normalizers and similarity indexes using training data only. All retrieved events and examples must have been available at forecast time; require outcomes already known then.

Compare with 50/50, simple target/time forecasts and appropriately defined Polymarket quote baselines. Measure Brier score, log loss, calibration and directional accuracy at predefined remaining-time checkpoints. Report market counts, missing coverage, uncertainty and performance by duration/regime. Thousands of predictions from a handful of intervals are not thousands of independent trials.

Reserve a later holdout period. Use comparisons that remove one added layer at a time. Probability disagreement with market quotes is not itself proof of profitable edge. Execution economics remain future scope.

## 10. Phase E — Add feeds and historical retrieval

Add a second exchange for corroboration, then trades/order flow and synchronized order books. Only add derivatives after endpoint availability and relevant fields are verified. Keep each enhancement measurable; retain the simpler baseline when extra features do not help.

Historical retrieval begins with normalized numerical distance and duration/time/regime filters. Return resolved cases, similarity distances and sample counts. Avoid counting many near-identical snapshots of one past market as independent cases.

Completion gate: source-specific outages do not corrupt other feeds; book synchronization is valid; incremental model comparisons are available.

## 11. Phase F — OpenAI and traversal/text memory

Use the user’s existing API access after model and spending limits are selected. Never embed the key in code or documents. The initial plan makes no paid calls.

Payload: current compact numeric state and quality flags, baseline/specialist outputs, a small set of timestamp-safe historical cases and relevant sourced events. Outputs: structured observations, contradictions, event relevance, risks and concise explanation. Analyst confidence is not assumed to equal calibrated probability.

Calls are event-triggered or infrequent, cached/deduplicated, and limited by configured request/token/spending thresholds. Log usage; monetary estimates require current pricing and should be reconciled with provider billing. Timeouts, rate limits and budget exhaustion leave numerical forecasting operational. Untrusted news is input data, not executable instructions.

Add FTS5 and relationship retrieval here with query/result provenance. Embeddings and a vector database remain optional future experiments.

Completion gate: no paid call on every tick; independently stored quant, analyst and combined outputs; comparison determines whether AI helps. Do not feed analyst judgments into the main forecast before demonstrating a defensible method.

## 12. Phase G — Ensemble and dashboard

Only train a meta-model when component data and evaluation are sufficient. Train stacking on out-of-fold or chronological component outputs, not in-sample predictions. Keep simple weighting/baseline comparisons. Model weights and feature importance are learned/evaluated, not asserted by the architecture.

Dashboard: duration selector or separate session panels; market identity; target; source/reference price; time remaining; probabilities; quote comparison; feed quality; partial capture; explanation; outcome history; calibration. Share ingestion across panels. A small status view can be added earlier for collector inspection; full UI styling comes after reliable data.

Completion gate: forecasts trace to source evidence, dashboard status is honest, both durations have separately reported support and performance.

## 13. Cost and retention strategy

Aim for open-source local software and verified public feeds. Zero-cost access is a target, not an established property of every API. OpenAI is the planned paid exception; premium feeds/cloud infrastructure are excluded unless the user revises scope.

Before choosing raw retention, measure bytes/hour for a sample run. Set configurable project and raw-data budgets below available disk capacity. Preserve targets, outcomes, forecast evidence, model versions and compact analyses. Keep raw books briefly if needed for debugging; archive or delete expired raw data using explicit retention policy. Monitor disk use and backfill progress. Preserve sufficient calculation evidence for reproducibility and record known limits when raw inputs expire.

## 14. Folder plan

```
Trading_bot_Analytics/
  README.md
  AGENTS.md
  .gitignore
  .env.example
  docs/
    reference/                 # Original handoff, screenshots and architecture
    STRATEGIC_PLAN.md
    PROJECT_SPEC.md
    DATA_ACCESS_FINDINGS.md
    DATA_MODEL.md
  research/
    probes/                    # Read-only feasibility checks
    samples/                   # Sanitized responses
  backend/
    app/
      ingestion/               # External APIs/streams
      sessions/
      storage/
      features/
      models/
      retrieval/
      intelligence/
      evaluation/
      api/                     # Our dashboard API
    tests/
  frontend/                    # Later dashboard
  data/                        # Ignored database and capped raw data
  artifacts/                   # Models, evaluation reports and manifests
```

Create folders only as work needs them. This plan does not require generating an empty application skeleton now.

## 15. Where we start and what we do not start

Next task: Phase A — read-only verification of Polymarket US and one BTC exchange. Deliver an evidence matrix of working fields/endpoints, missing fields, costs/authentication, and sample responses. That determines the first collector and database schema.

Do not begin with a vector database, a full dashboard, eight specialist models, automatic retraining, account login automation or order execution. No accuracy promise or implementation deadline is justified before access checks and collection measurements.

The user’s earlier instruction not to build remains in effect. This document is a reviewable strategic plan; research probes and later implementation are separate tasks.

## Sources checked for planning

- Polymarket US read-only data guide: https://docs.polymarket.us/data-guide/overview — documents reference data, market data and REST/gRPC access; does not alone verify the BTC targets or access costs.
- Coinbase Exchange candles: https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles — bounded historical buckets, possible gaps, and recommendation to use live feeds rather than repeatedly poll history.
- SQLite FTS5: https://www.sqlite.org/fts5.html — local full-text indexing/search.

These documentation checks are not completed live endpoint tests.
