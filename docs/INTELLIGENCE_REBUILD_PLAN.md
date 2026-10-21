# BTC Intelligence Rebuild Plan

**Branch:** `codex/intelligence-rebuild-phase0`  
**Status:** Active implementation plan  
**Primary focus:** Polymarket US BTC 15-minute markets  
**Rule:** Keep the existing working collector/evaluation pipeline, rebuild the intelligence layer in measured phases.

---

## How to read this plan

- `[x]` = completed
- `[~]` = in progress
- `[ ]` = not started
- Each phase has a clear goal and definition of done.
- New models stay independent until they prove value on future unseen markets.
- No automated trading is part of this plan.

---

## Current position

**Current phase:** Phase 0 — Stabilize What Exists  
**Current branch:** `codex/intelligence-rebuild-phase0`  
**Next gate:** finish Phase 0 tests, verify baseline is unchanged, then start the Live State Engine.

### Phase 0 progress already implemented on this branch

- [x] Ensemble weights renormalize over available components.
- [x] Baseline and `ensemble_v1` are stored as separate prediction rows.
- [x] Polymarket ensemble input reads saved `bbo`, `book`, or `stream_book` evidence.
- [x] News ensemble input uses `news_events` with timestamp-safe first-seen/publication checks.
- [x] A `NO_EDGE` research state exists around 50/50.
- [x] Model suggestions no longer imply a real SELL position.
- [x] OpenAI is disabled unless `ENABLE_OPENAI_ANALYST=true`.
- [x] OpenAI failure is non-critical to numerical collection/forecasting.
- [ ] Add/finish Phase 0 unit tests.
- [ ] Run the full test suite and compare baseline metrics before/after.
- [~] Make the dashboard visibly label `ensemble_v1` as experimental.

---

## Master roadmap

| Phase | Status | Build | Main result |
|---|---|---|---|
| 0 | [~] | Stabilize current ensemble / AI layer | Current signals become trustworthy enough for research |
| 1 | [ ] | Live State Engine | Current market state lives in RAM instead of repeated DB reads |
| 1.5 | [ ] | FastAPI service layer | One local async API for dashboard, live state, models, Polymarket adapters, and later Supabase |
| 2 | [ ] | Coinbase trade + L2 ingestion | Real microstructure inputs |
| 3 | [ ] | `microstructure_v1` | Independent order-flow/order-book probability |
| 4 | [ ] | Specialist model framework | Every model uses the same output contract |
| 5 | [ ] | Multi-exchange spot inputs | Cross-exchange confirmation |
| 6 | [ ] | Derivatives inputs/model | Funding, OI, liquidations, basis |
| 7 | [ ] | Supabase/Postgres long-term storage | SQLite stays local/fast while history grows safely |
| 8 | [ ] | Retention / archival | Local DB growth becomes controlled |
| 9 | [ ] | `historical_v2` | Rich leakage-safe historical matching |
| 10 | [ ] | `openai_analyst_v1` | AI analyzes compact current market state |
| 11 | [ ] | Dashboard specialist panels | See every model independently |
| 12 | [ ] | Forward evaluation | Measure every specialist on future markets |
| 13 | [ ] | `meta_model_v1` | Learned final probability instead of hand weights |
| 14 | [ ] | Scale only if needed | Redis/ClickHouse/Redpanda/Neo4j only after measured need |

---

# Phase 0 — Stabilize What Exists

## Goal

Fix the current experimental intelligence layer before adding more feeds or models.

## Checklist

- [x] Preserve `gaussian_distance_v1` as the frozen baseline benchmark.
- [x] Fix ensemble missing-weight normalization.
- [x] Do not let unavailable components silently count as neutral/bearish evidence.
- [x] Store `ensemble_v1` separately from the baseline prediction row.
- [x] Fix Polymarket probability extraction to use actual saved `bbo`, `book`, or `stream_book` data.
- [x] Fix the current news-table mismatch and use `news_events`.
- [x] Enforce timestamp-safe news availability using both publication time and first-seen time.
- [x] Add a `NO_EDGE` state instead of forcing UP/DOWN near 50%.
- [x] Remove fake position assumptions from decision logic.
- [x] Make OpenAI explicitly opt-in.
- [x] Ensure AI failure never affects data collection or numerical forecasts.
- [ ] Add unit tests for every change above.
- [~] Keep the current ensemble visibly labeled **experimental**.

## Definition of done

- Baseline evaluation is unchanged.
- Missing model components cannot distort probabilities.
- Experimental ensemble results are reproducible and correctly sourced.
- OpenAI does not run unless explicitly enabled.

---

# Phase 1 — Live State Engine

## Goal

Move the real-time decision path away from repeated DB queries.

## Live state should contain

- [ ] Active market ID / slug.
- [ ] Price to Beat.
- [ ] Market start/end.
- [ ] Seconds remaining.
- [ ] Current BTC price.
- [ ] 5s / 10s / 30s returns.
- [ ] 1m / 3m / 5m / 15m returns.
- [ ] Rolling volatility.
- [ ] Trade flow.
- [ ] Order-book state.
- [ ] Polymarket UP/DOWN state.
- [ ] Derivatives state when available.
- [ ] Feed freshness.
- [ ] Missing-data flags.
- [ ] Reconnect / source-health state.

## Target live path

```text
WebSocket / REST
       ↓
Python RAM
       ↓
feature calculations
       ↓
specialist forecasts
       ↓
dashboard
       ↓
async persistence
```

## Definition of done

- Current predictions can be produced from RAM state.
- SQLite remains evidence/recovery storage.
- Remote storage is not required for a live forecast.

---


# Phase 1.5 — FastAPI Service Layer

## Goal

Add a lightweight local API around the live-state engine so the dashboard and future services do not query SQLite directly for every update.

FastAPI does **not** make Polymarket or Supabase themselves faster. It helps our system by keeping a long-running async process, reusing connections, centralizing caching/state, and avoiding repeated client-side/database work.

## Target role

```text
Polymarket / Exchanges / News
            |
            v
      async collectors
            |
            v
       Live State RAM
            |
            v
          FastAPI
      /state/current
      /forecast/current
      /models/current
      /health
      /history
      /events
            |
      +-----+------+
      |            |
      v            v
 dashboard      local tools

SQLite <---- persistence ---- FastAPI/service process ---- async sync ----> Supabase/Postgres
```

## Checklist

- [ ] Add FastAPI + Uvicorn dependencies.
- [ ] Keep the live state in the same process or a clearly defined shared-state boundary.
- [ ] Add `GET /state/current`.
- [ ] Add `GET /forecast/current`.
- [ ] Add `GET /models/current`.
- [ ] Add `GET /health`.
- [ ] Add bounded/read-only historical endpoints.
- [ ] Add Server-Sent Events or WebSocket endpoint for dashboard live updates.
- [ ] Keep Polymarket/exchange credentials server-side only.
- [ ] Add connection pooling/reuse for future Postgres/Supabase access.
- [ ] Do not route every market tick through Supabase.
- [ ] Add request/response tests and latency measurements.

## Supabase performance rule

For long-term storage, prefer backend-side Postgres/Supabase access with pooled connections and batched writes. FastAPI should return current state from RAM/local cache; it should query Supabase only for historical/research requests or background synchronization.

# Phase 2 — Coinbase Microstructure Inputs

## Goal

Collect the data needed to see buyer/seller pressure below the candle level.

## Checklist

- [ ] Verify Coinbase trade-feed semantics.
- [ ] Add/verify trade stream.
- [ ] Add Level 2 order-book stream.
- [ ] Maintain local current book.
- [ ] Preserve source and receive timestamps.
- [ ] Preserve missing/freshness state.

## Derived features

### Trade flow

- [ ] Buy volume.
- [ ] Sell volume.
- [ ] Signed volume delta.
- [ ] Trade-count imbalance.
- [ ] Trade velocity.
- [ ] Volume acceleration.
- [ ] Large-trade imbalance.

### Order book

- [ ] Best bid.
- [ ] Best ask.
- [ ] Spread.
- [ ] Top-level bid/ask size.
- [ ] Top 5 / top 10 depth.
- [ ] Bid/ask depth imbalance.
- [ ] Microprice.
- [ ] Liquidity wall changes.
- [ ] Replenishment / withdrawal signals.

## Rolling windows

- [ ] 5 seconds.
- [ ] 10 seconds.
- [ ] 30 seconds.
- [ ] 1 minute.
- [ ] 3 minutes.
- [ ] 5 minutes.

---

# Phase 3 — `microstructure_v1`

## Goal

Create the first independent model using real trade-flow/order-book evidence.

## Output contract

```json
{
  "model": "microstructure_v1",
  "probability_up": 0.37,
  "probability_down": 0.63,
  "confidence": 0.71,
  "fresh": true,
  "reasons": [],
  "version": "1.0"
}
```

## Checklist

- [ ] Train/build without changing `gaussian_distance_v1`.
- [ ] Store outputs independently.
- [ ] Evaluate at T-10m / T-5m / T-3m / T-1m.
- [ ] Preserve abstention when inputs are stale/missing.
- [ ] Do not combine into the final forecast yet.

---

# Phase 4 — Specialist Model Framework

## Goal

Make every intelligence layer plug into the same interface.

## Planned specialists

- [ ] `target_time_v1`
- [ ] `momentum_v1`
- [ ] `microstructure_v1`
- [ ] `cross_exchange_v1`
- [ ] `derivatives_v1`
- [ ] `historical_v2`
- [ ] `news_event_v1`
- [ ] `openai_analyst_v1`

## Standard fields

- [ ] model/version
- [ ] probability_up
- [ ] probability_down
- [ ] confidence
- [ ] fresh
- [ ] reasons
- [ ] contradictions
- [ ] risk flags
- [ ] source timestamps
- [ ] missing-data state

---

# Phase 5 — Multi-Exchange Spot Confirmation

## Goal

Determine whether BTC pressure is broad or exchange-specific.

## Candidate sources

- [ ] Coinbase.
- [ ] Binance (after access/terms verification).
- [ ] Kraken (after access/terms verification).

## Features

- [ ] Cross-exchange price divergence.
- [ ] Momentum agreement.
- [ ] Flow agreement.
- [ ] Volume acceleration.
- [ ] Lead/lag behavior.
- [ ] Exchange-specific anomalies.

## Model

- [ ] Build `cross_exchange_v1`.
- [ ] Store/evaluate independently.

---

# Phase 6 — Derivatives Intelligence

## Goal

Measure leverage/positioning pressure that spot data alone cannot see.

## Inputs

- [ ] Funding.
- [ ] Funding change.
- [ ] Open interest.
- [ ] OI change.
- [ ] Long liquidations.
- [ ] Short liquidations.
- [ ] Perpetual/futures basis.
- [ ] Options/skew only later if useful.

## Model

- [ ] Build `derivatives_v1`.
- [ ] Evaluate independently.

---

# Phase 7 — Storage Upgrade: RAM + SQLite + Supabase/Postgres

## Goal

Keep live analysis fast while allowing history to grow for months/years.

## Storage responsibilities

| Layer | Purpose | Examples |
|---|---|---|
| RAM | Live reflexes | current price, current book, rolling windows, current model state |
| SQLite | Local operational store | recent raw data, snapshots, predictions, recovery, sync queue |
| Supabase/Postgres | Long-term memory | markets, features, predictions, model outputs, outcomes, AI analyses, evaluation |

## Important rule

Supabase must **not** be in the critical live prediction path.

Correct:

```text
feed → RAM → prediction → SQLite → async Supabase sync
```

Avoid:

```text
feed → Supabase → query Supabase → prediction
```

## Supabase checklist

- [ ] Design schema.
- [ ] Create sync metadata/queue locally.
- [ ] Idempotent upserts.
- [ ] Stable source IDs.
- [ ] Batch sync.
- [ ] Retry/backoff.
- [ ] Offline-safe operation.
- [ ] Sync health visible in dashboard/ops.
- [ ] Historical backfill from existing SQLite.
- [ ] Verify row counts / checksums before deleting anything locally.

---

# Phase 8 — Retention / Local DB Growth

## Goal

Stop the local DB from growing forever while preserving useful research data.

## Initial retention idea

| Data | Local retention | Long-term |
|---|---|---|
| Raw full order-book events | ~1–3 days initially | normally no |
| Raw trades/ticks | ~7–30 days initially | optional archive |
| 1m candles | keep | yes |
| Derived feature snapshots | keep | yes |
| Markets / targets / outcomes | keep | yes |
| Predictions | keep | yes |
| Specialist outputs | keep | yes |
| AI analyses | keep | yes |
| Evaluation results | keep | yes |
| News/event metadata | keep | yes |

## Safety rules

- [ ] No deletion until cloud sync is verified.
- [ ] No deletion until backups/recovery are tested.
- [ ] Retention must be configurable.
- [ ] Evidence needed for reproducibility must not be deleted.
- [ ] Use compaction/aggregation where appropriate.

---

# Phase 9 — `historical_v2`

## Goal

Compare the current state with prior markets using richer, leakage-safe features.

## Comparable state

- [ ] Distance to target.
- [ ] Time remaining.
- [ ] Momentum.
- [ ] Volatility.
- [ ] Order flow.
- [ ] Book imbalance.
- [ ] Cross-exchange agreement.
- [ ] Derivatives.
- [ ] Polymarket probability.
- [ ] Data quality/regime flags.

## Rules

- [ ] One eligible state per prior resolved market.
- [ ] Comparable relative checkpoint.
- [ ] No future leakage.
- [ ] Outcome must have been knowable only after that prior market ended.
- [ ] Store match provenance.

---

# Phase 10 — `openai_analyst_v1`

## Goal

Make AI analyze the current market rather than mostly comment on one ensemble number.

## AI receives one compact state

```json
{
  "market": {},
  "target_time": {},
  "momentum": {},
  "volatility": {},
  "order_flow": {},
  "order_book": {},
  "cross_exchange": {},
  "derivatives": {},
  "polymarket": {},
  "historical": {},
  "news": [],
  "model_outputs": {},
  "data_health": {}
}
```

## AI output

```json
{
  "up_probability": 0.31,
  "down_probability": 0.69,
  "confidence": 0.74,
  "market_regime": "short_term_bearish",
  "main_drivers": [],
  "contradictions": [],
  "risk_flags": [],
  "summary": ""
}
```

## Trigger policy

- [ ] New market.
- [ ] Material state change.
- [ ] Strong model disagreement.
- [ ] Timely major event.
- [ ] Bounded refresh, roughly 30–60 seconds if useful.
- [ ] Spending/call limit.
- [ ] Fully optional.

---

# Phase 11 — Dashboard Specialist View

## Goal

Make the dashboard explain what every model thinks.

## Example

```text
TARGET / TIME        DOWN 82%
MOMENTUM             DOWN 69%
MICROSTRUCTURE       DOWN 77%
CROSS EXCHANGE       DOWN 68%
DERIVATIVES          DOWN 59%
HISTORICAL           DOWN 66%
OPENAI ANALYST       DOWN 72%
POLYMARKET           DOWN 73%

CONSENSUS:
DOWN

MODELS AGREEING DOWN:
7 / 8

CONTRADICTION:
Derivatives are less bearish.
```

## Add

- [ ] Strongest positive/negative drivers.
- [ ] Contradictions.
- [ ] Risk flags.
- [ ] Feed freshness.
- [ ] Missing signals.
- [ ] NO EDGE.
- [ ] What changed timeline.

---

# Phase 12 — Forward Evaluation

## Goal

Collect enough future evidence to know what actually works.

## Checkpoints

- [ ] T-10m
- [ ] T-5m
- [ ] T-3m
- [ ] T-1m
- [ ] T-30s (optional after stability)

## Metrics

- [ ] Brier score.
- [ ] Log loss.
- [ ] Calibration.
- [ ] Directional accuracy.
- [ ] Coverage / abstention.
- [ ] Confidence buckets.
- [ ] Regime performance.
- [ ] Model disagreement performance.

## Compare against

- [ ] 50/50.
- [ ] `gaussian_distance_v1`.
- [ ] Polymarket.
- [ ] Each specialist.
- [ ] OpenAI.
- [ ] Future meta-model.

---

# Phase 13 — `meta_model_v1`

## Goal

Replace arbitrary hand-weighted ensemble logic with weights learned from forward evidence.

## Candidate first models

- [ ] Logistic regression.
- [ ] XGBoost / LightGBM.

## Rules

- [ ] Chronological train/validation/holdout.
- [ ] Never train on holdout.
- [ ] Every specialist remains inspectable independently.
- [ ] Only promote if it improves out-of-sample metrics.
- [ ] Keep fallback to simpler models if meta-model inputs are stale.

---

# Phase 14 — Scale Only If Needed

Do not add infrastructure because it sounds sophisticated.

Only upgrade when measured need appears:

| Current | Later if needed |
|---|---|
| Python RAM | Redis |
| Direct async/WebSockets | Redpanda/Kafka |
| SQLite + Postgres | ClickHouse for large time-series analytics |
| SQLite/Postgres relationships | Neo4j |
| FTS/structured retrieval | pgvector only if semantic search proves useful |

---

# Final Target System

```text
                         LIVE INPUTS

 Polymarket   Coinbase   Other Spot   Derivatives   News
      |           |           |           |          |
      +-----------+-----------+-----------+----------+
                              |
                              v
                       INGESTION LAYER
                    WebSockets + REST APIs
                              |
                              v
                       LIVE STATE ENGINE
                         Python / RAM
                              |
                              v
                       FEATURE ENGINE
                              |
          +-------------------+-------------------+
          |                   |                   |
          v                   v                   v
      Target/Time        Microstructure       Derivatives
      Momentum           Order Flow           Cross Exchange
      Volatility         Order Book
          |                   |                   |
          +-------------------+-------------------+
                              |
                  +-----------+-----------+
                  v                       v
             Historical v2          OpenAI Analyst
             long-term DB           compact live state
                  |                       |
                  +-----------+-----------+
                              |
                              v
                       SPECIALIST OUTPUTS
                              |
                              v
                         META MODEL
                              |
                              v

                       BTC 15M FORECAST

                       UP      xx%
                       DOWN    xx%
                       CONF    xx%

                              |
                              v
                    STORE + EVALUATE
                              |
                              v
                   OFFICIAL MARKET OUTCOME
                              |
                              v
                      LEARN / RETRAIN
```

---

# Immediate work order

- [x] **P0.1** Fix ensemble weight normalization.
- [x] **P0.2** Keep baseline and ensemble rows separate.
- [x] **P0.3** Fix Polymarket component source.
- [x] **P0.4** Fix news source/schema.
- [x] **P0.5** Add NO_EDGE.
- [x] **P0.6** Make OpenAI explicit opt-in.
- [ ] **P0.7** Add Phase 0 tests.
- [ ] **P1.1** Build Live State Engine.
- [ ] **P1.5.1** Add FastAPI service layer around current state/forecast/health.
- [ ] **P1.5.2** Add SSE/WebSocket live dashboard endpoint.
- [ ] **P2.1** Add/verify Coinbase trades + L2.
- [ ] **P3.1** Build `microstructure_v1`.
- [ ] **P4.1** Add specialist interface.
- [ ] **P5.1** Add second spot exchange.
- [ ] **P6.1** Add derivatives feed.
- [ ] **P7.1** Design Supabase schema.
- [ ] **P7.2** Build async SQLite → Supabase sync.
- [ ] **P8.1** Add retention controls.
- [ ] **P9.1** Build `historical_v2`.
- [ ] **P10.1** Build `openai_analyst_v1`.
- [ ] **P11.1** Add specialist dashboard.
- [ ] **P12.1** Run forward collection/evaluation.
- [ ] **P13.1** Train `meta_model_v1`.
