# BTC Intelligence Rebuild Plan

**Branch:** `codex/cloud-memory-phase1-75`  
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

**Current phase:** Phase 1.75 — Cloud Memory & Data Lifecycle  
**Current branch:** `codex/cloud-lifecycle-phase1-75`  
**Next gate:** review the real-database retention dry-run, then explicitly opt in to the first bounded production purge (`ENABLE_LOCAL_RETENTION=true` plus `apply --confirm`). Collector/API stay stopped until that decision.

### Phase 0 progress already implemented on this branch

- [x] Ensemble weights renormalize over available components.
- [x] Baseline and `ensemble_v1` are stored as separate prediction rows.
- [x] Polymarket ensemble input reads saved `bbo`, `book`, or `stream_book` evidence.
- [x] News ensemble input uses `news_events` with timestamp-safe first-seen/publication checks.
- [x] A `NO_EDGE` research state exists around 50/50.
- [x] Model suggestions no longer imply a real SELL position.
- [x] OpenAI is disabled unless `ENABLE_OPENAI_ANALYST=true`.
- [x] OpenAI failure is non-critical to numerical collection/forecasting.
- [x] Add/finish Phase 0 unit tests.
- [x] Run the full test suite (74 tests passed in GitHub Actions); baseline implementation/evaluation code remained unchanged.
- [x] Make the dashboard visibly label `ensemble_v1` as experimental.

---

## Master roadmap

| Phase | Status | Build | Main result |
|---|---|---|---|
| 0 | [x] | Stabilize current ensemble / AI layer | Current signals become trustworthy enough for research |
| 1 | [x] | Live State Engine | Current market state lives in RAM instead of repeated DB reads |
| 1.5 | [~] | FastAPI service layer | One local async API for dashboard and live-state access; live smoke/dashboard migration remain |
| 1.75 | [~] | Cloud Memory & Data Lifecycle | Postgres for structured history, Storage for compressed raw archives, SQLite as short-term spool |
| 2 | [ ] | Coinbase trade + L2 ingestion | Real microstructure inputs after storage lifecycle is safe |
| 3 | [ ] | `microstructure_v1` | Independent order-flow/order-book probability |
| 4 | [ ] | Specialist model framework | Every model uses the same output contract |
| 5 | [ ] | Multi-exchange spot inputs | Cross-exchange confirmation |
| 6 | [ ] | Derivatives inputs/model | Funding, OI, liquidations, basis |
| 7 | [ ] | Cloud storage maturity | Pooling, indexing, query optimization, cost/usage controls, backup/recovery |
| 8 | [ ] | Retention / archival maturity | Tune retention windows and replay/compaction after measured growth |
| 9 | [ ] | `historical_v2` | Rich leakage-safe historical matching |
| 10 | [ ] | `openai_analyst_v1` | AI analyzes compact current market state |
| 11 | [ ] | Dashboard specialist panels | See every model independently |
| 12 | [ ] | Forward evaluation | Measure every specialist on future markets |
| 13 | [ ] | `meta_model_v1` | Learned final probability instead of hand weights |
| 14 | [ ] | Scale only if needed | Redis/ClickHouse/Redpanda/Neo4j only after measured need |

---

# Phase 0 — Stabilize What Exists

**Status: COMPLETE**

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
- [x] Add unit tests for every change above.
- [x] Keep the current ensemble visibly labeled **experimental**.

## Definition of done

- Baseline evaluation is unchanged.
- Missing model components cannot distort probabilities.
- Experimental ensemble results are reproducible and correctly sourced.
- OpenAI does not run unless explicitly enabled.

---

# Phase 1 — Live State Engine

**Status: COMPLETE**

## Goal

Move the real-time decision path away from repeated DB queries.

## Live state should contain

- [x] Active market ID / slug.
- [x] Price to Beat.
- [x] Market start/end.
- [x] Seconds remaining.
- [x] Current BTC price.
- [x] 5s / 10s / 30s returns.
- [x] 1m / 3m / 5m / 15m returns.
- [x] Rolling volatility.
- [x] Trade-flow state slot + missing-data flag; Phase 2 supplies the live feed/features.
- [x] BTC order-book state slot + missing-data flag; Phase 2 supplies L2 data.
- [x] Polymarket UP/DOWN state.
- [x] Derivatives state when available.
- [x] Feed freshness.
- [x] Missing-data flags.
- [x] Reconnect / source-health state.

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

- [x] Current predictions can be produced from RAM state.
- [x] SQLite remains evidence/recovery storage.
- [x] Remote storage is not required for a live forecast.
- [x] Mid-interval process restart can hydrate active market, recent BTC ticks, feature snapshot, Polymarket quote, feed health, and baseline state from SQLite.
- [x] Coinbase and Polymarket streaming updates feed RAM directly while SQLite remains evidence storage.

---


# Phase 1.5 — FastAPI Service Layer

**Status: IN PROGRESS**

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

- [x] Add FastAPI + Uvicorn dependencies.
- [x] Keep the live state in the same process or a clearly defined shared-state boundary.
- [x] Add `GET /state/current`.
- [x] Add `GET /forecast/current`.
- [x] Add `GET /models/current`.
- [x] Add `GET /health`.
- [x] Add bounded/read-only historical endpoints.
- [x] Add Server-Sent Events or WebSocket endpoint for dashboard live updates.
- [x] Keep Polymarket/exchange credentials server-side only.
- [ ] Add connection pooling/reuse only when direct Postgres access is introduced; Phase 1.75 starts with bounded asynchronous cloud writes.
- [x] Do not route every market tick through Supabase.
- [x] Add request/response tests and latency measurements.

### Current Phase 1.5 evidence

- [x] `run_api.py` starts one local service process and loads the ignored project `.env`.
- [x] FastAPI owns the same `LiveState` object passed into the collectors.
- [x] `/state/current`, `/forecast/current`, `/models/current`, and `/health` read RAM state.
- [x] `/history/predictions` is bounded to 1–500 rows and opens SQLite query-only.
- [x] `/events` provides a Server-Sent Events stream when the RAM state changes.
- [x] Response-time instrumentation is emitted as `X-Process-Time-Ms`.
- [x] GitHub Actions passes 85 tests including FastAPI request/history tests.
- [ ] Perform a real local live smoke test with the user's current database and credentials.
- [ ] Migrate the legacy dashboard's high-frequency live panels to the new endpoints.
- [~] Cloud sync work has moved to Phase 1.75; no remote DB is in the hot path.

## Supabase performance rule

For long-term storage, prefer backend-side Postgres/Supabase access with pooled connections and batched writes. FastAPI should return current state from RAM/local cache; it should query Supabase only for historical/research requests or background synchronization.


# Phase 1.75 — Cloud Memory & Data Lifecycle

**Status: IN PROGRESS**

## Why this moved forward

The real SQLite inspection showed that database growth is dominated by raw high-frequency evidence, not by forecasts or feature history:

- `observations` (primarily Polymarket full book snapshots) is the largest storage consumer.
- `stream_events` (primarily Coinbase stream evidence) is the second-largest storage consumer.
- Feature snapshots, predictions, markets, outcomes, candles, and evaluation data are comparatively small.
- A larger local machine would postpone the storage limit but would not solve indefinite growth.

The architecture therefore changes before Coinbase L2 is added: the bot computes locally from RAM, keeps SQLite as a bounded hot/recovery spool, stores structured long-term intelligence in Supabase Postgres, and stores compressed raw feed archives in private Supabase Storage.

## Target architecture

```text
Coinbase / Polymarket / future feeds
                 |
                 v
             LiveState RAM
                 |
          features + models
                 |
                 v
              forecast
                 |
        +--------+---------+
        |                  |
        v                  v
     FastAPI          local SQLite
   dashboard/API      hot/recovery spool
                           |
                    async persistence
                    +------+------+
                    |             |
                    v             v
          Supabase Postgres   Supabase Storage
          structured history  compressed raw archive
```

## Storage responsibilities

| Layer | Responsibility |
|---|---|
| RAM | Current market, rolling windows, current books/quotes, current specialist/model state |
| SQLite | Recent raw evidence, restart/recovery state, upload backlog/checkpoints |
| Supabase Postgres | Markets, outcomes, feature snapshots, predictions, model outputs, evaluations, historical summaries, news/event metadata, knowledge metadata/chunks |
| Supabase Storage | Compressed Coinbase/Polymarket raw archives, future L2 archives, trading/reference documents, optional verified backups |

## Hard rules

- [x] Supabase is never required to produce a live forecast.
- [x] The hot path remains `feed → RAM → features/models → forecast`.
- [x] Cloud writes are isolated from the forecast path and run through a separate bounded lifecycle worker; they never run in the forecast hot path.
- [x] No local raw deletion occurs until the corresponding cloud archive is verified.
- [x] Archive verification uses authenticated readback, compressed-byte count, SHA-256, event count, and a verified manifest.
- [x] Structured cloud writes use stable source IDs/upserts and local/cloud checkpoints; raw archive object paths are deterministic and manifests upsert by bucket/path.
- [x] Secrets stay server-side only.
- [x] Storage buckets used by the bot are private.
- [x] Raw feed archives are deterministic gzip-compressed JSONL before upload.
- [x] Structured history remains queryable without opening raw archives.

## Initial Supabase Postgres tables

- [x] `markets`
- [x] `official_outcomes`
- [x] `feature_snapshots`
- [x] `predictions`
- [x] `model_outputs`
- [x] `evaluation_metrics`
- [x] `news_events`
- [x] `sync_checkpoints`
- [x] `raw_archives`
- [ ] Knowledge tables for trading/reference material when RAG work begins.

## Initial private Storage buckets

- [x] `market-raw` — compressed raw Coinbase/Polymarket/future L2 archives.
- [x] `knowledge` — trading/reference documents.
- [x] `backups` — optional verified SQLite/database backups.

## Implementation order

- [x] P1.75.1 Design and create cloud schema; hosted migration applied and RLS verified.
- [x] P1.75.2 Add server-side Supabase client/config validation with explicit opt-in.
- [x] P1.75.3 Add idempotent structured batch sync with dependency-safe backfill/checkpoints.
- [x] P1.75.4 Add deterministic gzip JSONL raw archive writer.
- [x] P1.75.5 Add private Storage upload + authenticated readback/checksum verification + manifest.
- [x] P1.75.6 Add sync/archive health telemetry to FastAPI (`/cloud/status` and separate cloud status inside `/health`); dashboard presentation can follow with the broader Phase 1.5 migration.
- [x] P1.75.7 Backfill existing SQLite structured history: executed against the real database and independently verified in Supabase (markets 1,164; feature_snapshots 6,776; predictions 6,745; news_events 28; candles 48,812).
- [x] P1.75.8 Archive existing raw history and verify it: 198,243 Polymarket observations and 1,168,729 Coinbase stream events archived; 274 raw archive objects verified by authenticated readback + SHA-256, 0 unverified.
- [x] P1.75.9 Verified local retention (`backend/app/retention.py`, `run_retention.py`): implemented, tested, and applied once to the production database after full cloud verification; **disabled by default for normal runtime until the lifecycle worker is enabled.**
  - Eligibility = `received_at` older than `LOCAL_RAW_RETENTION_HOURS` (default 48) AND inside the source range of a verified `raw_archives` manifest (`verified_at` set, authenticated-readback metadata, SHA-256 present, matching bucket/dataset). Sync checkpoints are never trusted.
  - `observations` use manifest ID ranges; `stream_events` use the `(received_at, source, event_id)` cursor range, never `rowid`. Both are separate.
  - A manifest is rejected if local rows inside its range exceed its `event_count`; a dataset is blocked if any `received_at` is not canonical UTC microsecond format.
  - The highest `observations.id` is always kept: the table has no AUTOINCREMENT, so emptying it would reuse archived IDs.
  - Only `observations` and `stream_events` are touched; structured tables, `cloud_sync_state` and outcomes are never deleted. Retention itself never runs VACUUM. The one-time production compaction was performed separately with `VACUUM INTO`, verified before the database-path swap.
  - CLI: `run_retention.py status` (local only), `dry-run` (default, read-only connection), `apply --confirm` (also requires `ENABLE_LOCAL_RETENTION=true`); bounded `RETENTION_DELETE_BATCH_SIZE` batches; idempotent and restart-safe. Manifests are read from Supabase for dry-run/apply only; the live path never calls this module.
  - Evidence: 20 retention tests (112 total at that milestone) cover disabled-by-default, invalid hours, unverified/untrusted manifests, partial coverage, cutoff boundary, duplicate `received_at`, batching, dry-run writes nothing, confirmation gate, structured tables untouched, idempotence.
  - Production evidence: dry-run used all 274 verified manifests with 0 rejected; controlled apply deleted 198,242 archived observations and 1,168,729 archived stream events, retained the newest observation ID anchor, preserved all structured counts/checkpoints, and passed integrity checks. A verified `VACUUM INTO` compaction reduced the production SQLite file from ~1.9 GB to ~48 MB; both pre-retention and pre-compaction safety copies were retained.
- [x] P1.75.9b Cloud lifecycle worker (`backend/app/cloud_lifecycle.py`, `run_cloud_lifecycle.py`): implemented and tested; disabled by default.
  - Separate process from FastAPI/collector; per-DB `flock`; independent cadences for structured sync, observations/stream_events archive and retention; bounded catch-up per cycle; `busy_timeout`, short transactions, no network inside a write transaction; no VACUUM.
  - Retention only when `ENABLE_LOCAL_RETENTION=true` and the **same cycle** actually ran the raw archive stage successfully; a successful prior cycle cannot authorize a later retention-only cycle. Any archive/cloud failure skips deletion. Telemetry in `cloud_lifecycle_state` (sanitized type/HTTP code only), exposed in `GET /cloud/status`; `/health` unaffected.
  - Topology: FastAPI owns collector + live state; lifecycle worker owns cloud copy/archive/retention; ensemble agent is the experimental model process.
  - Real `once` evidence: production SQLite integrity stayed `ok`; structured sync moved 0 rows, both raw datasets were already caught up, retention remained disabled, and lifecycle status returned `idle` with no errors.
  - Review hardening: no-due cycles do not create a Supabase client, failed cloud attempts advance their due timestamps instead of tight-loop retrying, and two regression tests enforce same-cycle retention authorization.
  - Remaining gap: production restart order (API, lifecycle worker, ensemble agent), then a measured 24-hour run before removing the redundant PRECOMPACT copy.
- [ ] P1.75.10 Measure a new 24-hour run and tune retention.
- [ ] P1.75.11 Add historical raw replay tooling for research/model validation.

## Initial retention target

These are starting points, not permanent rules:

| Data | Local target | Long-term destination |
|---|---|---|
| Full raw Polymarket books | ~48h | compressed Supabase Storage |
| Raw Coinbase stream events | ~48h initially | compressed Supabase Storage |
| Future Coinbase L2 | ~24–48h | compressed Supabase Storage |
| Candles | longer/local as useful | Supabase Postgres |
| Feature snapshots | longer/local as useful | Supabase Postgres |
| Predictions/model outputs | longer/local as useful | Supabase Postgres |
| Markets/outcomes/evaluation | keep (small) | Supabase Postgres |

## Definition of done

- Continuous collection can run without unbounded local disk growth.
- A Supabase outage does not stop live forecasting.
- Structured historical research can query Postgres directly.
- Raw historical evidence remains recoverable/replayable from Storage.
- Existing SQLite history is verified in cloud before any cleanup.
- Storage/sync health is observable and tested.

---

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

# Phase 7 — Cloud Storage Maturity

## Goal

Optimize the Phase 1.75 cloud foundation only after real usage data exists: pooling/direct Postgres where justified, indexes, cost controls, backup/recovery, and larger-scale analytical access.

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

## Maturity checklist

- [ ] Measure Postgres query/write load before introducing direct connection pooling.
- [ ] Add/adjust indexes from observed query plans.
- [ ] Add cloud usage/cost telemetry and alerts.
- [ ] Validate backup/restore and disaster-recovery procedures.
- [ ] Tune archive partitioning/format for replay and research workloads.
- [ ] Revisit larger analytical stores only if Postgres/object-storage workflows become a measured bottleneck.

---

# Phase 8 — Retention / Archive Maturity

## Goal

Stop the local DB from growing forever while preserving useful research data.

## Initial retention idea

| Data | Local retention | Long-term |
|---|---|---|
| Raw full order-book events | ~48h initial target | compressed Supabase Storage |
| Raw trades/ticks | ~48h initial target | compressed Supabase Storage |
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
- [x] **P0.7** Add Phase 0 tests.
- [x] **P1.1** Build Live State Engine.
- [x] **P1.5.1** Add FastAPI service layer around current state/forecast/health.
- [x] **P1.5.2** Add SSE/WebSocket live dashboard endpoint.
- [x] **P1.75.1** Design/create Supabase structured-history schema and private Storage buckets.
- [x] **P1.75.2** Build bounded structured sync + compressed raw archive writer with checksum verification.
- [x] **P1.75.3** Backfill/verify current SQLite history in cloud — real run complete and verified.
- [~] **P1.75.4** Enable local retention only after verified cloud copies — tooling implemented (P1.75.9); production purge pending explicit opt-in.
- [ ] **P2.1** Add/verify Coinbase trades + L2.
- [ ] **P3.1** Build `microstructure_v1`.
- [ ] **P4.1** Add specialist interface.
- [ ] **P5.1** Add second spot exchange.
- [ ] **P6.1** Add derivatives feed.
- [ ] **P7.1** Mature cloud storage performance/cost/recovery.
- [ ] **P8.1** Tune retention/archive/replay using measured growth.
- [ ] **P9.1** Build `historical_v2`.
- [ ] **P10.1** Build `openai_analyst_v1`.
- [ ] **P11.1** Add specialist dashboard.
- [ ] **P12.1** Run forward collection/evaluation.
- [ ] **P13.1** Train `meta_model_v1`.
