# BTC Intelligence Rebuild Plan

## Active execution plan — November 12, 2026

**Phase 1.75 / I7 remain OPEN. This is the only authoritative roadmap.**
The checkpoints below implement the selected PostgreSQL direction within Phase
1.75; they are not new product phases. README documents operation; handoff points
here. Dated reports and the older sections below preserve evidence, not current
instructions. Passing generated SQLite A/B tests does not qualify PostgreSQL.

### Current verified checkpoint

- PR #14 is merged into `main` at `cf86a19`. PR #15 aligns its reviewed
  CI/CD/docs into `preprod` at `15475f7`. PR #15 CI 43338705231 passed.
- The original dirty checkout stays on `codex/phase1-75-retention-enable` at
  `0204901`; unrelated changes and the uncommitted roadmap history are preserved.
  New foundation changes are prepared from the reviewed `main` tree, not merged
  wholesale from the superseded SQLite application branch.
- Existing PP: `tradebot-preprod-01`, us-east-2a, 2 vCPU / 2 GiB / 60 GB.
  Existing production: `tradebot-analytics-01`, same region/resources. No third
  instance. Production remains the separately deployed legacy SQLite release
  `d56b4a7` by last recorded inspection, not the application on current `main`.
- **CP0 branch alignment PASS; CP1 foundation implementation/qualification in
  progress.** A successful database container will not imply app/CD readiness.
- Production is untouched by this milestone. No new production health/collection
  claim is inferred from GitHub CI. Last recorded collection was storage-held;
  retention and paid AI were OFF.

### Fixed architecture and policy

Each VM eventually runs an independent Compose deployment: API/collector/RAM
LiveState, calculation worker, lifecycle/history worker, and PostgreSQL on a
persistent volume. Database migrations are an explicit command, never normal
application startup. PP and production have independent credentials, volumes,
networks and environment identities with the same versioned business schema.

| PP mode | Source | Collector policy |
| --- | --- | --- |
| Production preview | Restricted authenticated production API/SSE | PP collector OFF; PP API/dashboard ON |
| Isolated development | Generated or approved replay/subset in PP PostgreSQL | Real collector OFF |
| Bounded live qualification | Official feeds writing only PP data | PP temporarily owns sole real collector after production fencing |

Before production takes collection ownership, stop and fence PP collection so
it cannot automatically restart; keep PP API running. A storage-guard pause is
not a writer fence. Cross-host preview uses qualified private networking or an
approved tunnel and a restricted API identity. Docker bridge networks do not
span hosts. Never share database volumes or expose PostgreSQL publicly. Preview
credentials cannot call administrative or collector controls.

Local databases are `tradebot_pp` and `tradebot_prod`:

| Schema | Contract |
| --- | --- |
| `raw` | Observations/events partitioned by unique A/B generation |
| `core` | Markets, candles, current prices, features, predictions, outcomes, protected evidence |
| `ops` | Versioned migrations, ownership, health, durable outbox/checkpoints, bounded deduplication |
| `archive` | Generation state, exact coverage, manifests, verification, retirement records |

Preserve stable origin-aware identities, exact financial decimals, original
source timestamp strings, receipt/availability times and provenance. A duplicate
identity succeeds only if its content matches. Raw retirement cannot cascade
into protected evidence/predictions. PostgreSQL timestamp precision alone must
not replace the original source timestamp representation.

**A collects → switch to B → seal A → upload and verify required A data →
preserve references/history → drain readers → retire A locally → repeat.**
Rotation occurs at 72 hours or a qualified size threshold. There is no additional
72-hour wait after sealing and no guaranteed minimum 72-hour local window when
size triggers first. PostgreSQL partition retirement reclaims that relation's
storage; measure aggregate disk/WAL/temporary/log/image usage separately. Archive
failure, uncertain coverage or evidence changes preserve local data. Normal
PostgreSQL locking/maintenance still require measured interference limits.

### Supabase, hot reads and history

Selected cloud contract: additive **private `history_v2`** structured tables,
protected evidence, coverage and origin/generation checkpoints. Preserve all
existing public tables and objects. Raw remains compressed objects in private
Supabase Storage. The cloud migration is NOT applied by foundation initialization.
Same database engine does not provide automatic sync or format compatibility.

| Query | Path |
| --- | --- |
| Current dashboard / SSE | RAM LiveState |
| Recent calculations / bounded history | Indexed local PostgreSQL |
| Older structured history | Explicit historical retrieval from Supabase |
| Exact archived evidence | Catalog → authenticated download → verification → decode/replay |
| Future AI | Bounded retrieval tools returning data plus provenance |

Remote retrieval stays off the live forecasting path. Never replace a missing
live price with an old cloud price. Distinguish stale, missing and failed
retrieval. Preserve existing API contracts where possible; add truthful
source/as-of time, environment/data mode, archive coverage and retention holds.
Redis is deferred unless a measured bottleneck supports a reconstructible cache.
It cannot replace durable persistence or archive verification.

### Delivery checkpoints and evidence

Each completed milestone has a tested commit, small PR to `preprod`, applicable
CI and one consolidated outcome. Qualified default-off pieces may merge without
waiting for every Phase 1.75 gate. `main` is the intended production release
branch; production CD is manual and requires exact main-artifact PP evidence.
The obsolete `codex/lightsail-deployment` route is not the new release path.

| CP | Work | Completion gate / current state |
| --- | --- | --- |
| 0 | Consolidate plan, align reviewed main workflows/docs to PP | PR #15 merged; no SQLite A/B bulk merge; current plan/handoff consolidation included in foundation PR |
| 1 | PP Docker/PostgreSQL/developer foundation | Official Ubuntu Docker repo; pinned `postgres:17.12-bookworm`; isolated network, persistent volume, restricted roles, secrets, health; generated persistence/recreation and README commands. **In progress** |
| 2 | Versioned local database and `history_v2` contract | Empty/repeat/upgrade, wrong-environment, decimals/timestamps/identity/reference regressions; no cloud DDL until CP6 |
| 3 | PostgreSQL app and dashboard | Adapter, indexed current-price and bounded history, calculations, actual API/SSE, independent discovery/serial calculation, runnable application image |
| 4 | A/B lifecycle and historical retrieval | Atomic switch/seal, durable structured outbox, bounded archives/readback, history after real generated partition retirement; preserve on failure |
| 5 | CD Preprod | Qualified restricted host controller/deploy identity/host pin/credentials/runner; migration/app/image CI; manual PP deploy and recovery evidence; no flag-only enablement |
| 6 | Actual Supabase compatibility | Separately reviewed additive private `history_v2` DDL/grants; bounded isolated writes/readback; exact values/conflicts/checkpoints/replay; mutation-authority qualification |
| 7 | PP live/capacity/recovery | Explicit prod fencing; bounded sole-collector PP run; API/SSE/persistence/features/rollover/archive; normal/outage growth, core/outbox, legacy import/recovery; PP collector disabled afterward |
| 8 | Exact production candidate | Reviewed small PRs assembled on main; exact image/version tested in PP; executable cutover/recovery with measured operating limits |
| 9 | Approved production cutover | Fence old writer; verify/import committed history/delta; single PG collector; bounded smoke; measured interruption; retirement initially OFF |
| 10 | Lifecycle and Phase 1.75 acceptance | Separately verify first sealed generation then enable retirement; bounded automated sustained evidence across cycles/boundaries; independent legacy retirement gate |

Cutover, first sealed-generation verification and retirement enablement are
separate checkpoints. Do not assume a 72-hour seal fits inside cutover. After
new PostgreSQL acknowledgements, recovery must preserve them; restarting the old
SQLite writer blindly is prohibited. Legacy SQLite is retained until its own
archive, exact reference/retrieval and reader-drain checks pass.

### Budgets, regression matrix and acceptance

Foundation: generated smoke data ≤64 MiB, PostgreSQL container 512 MiB RAM,
128 MiB shared buffers and bounded connections. Full durability/autovacuum stay
ON. Fresh resource preflight before installation: ≥10 GiB free filesystem and
≥1 GiB available RAM. These foundation prerequisites are not a production sizing
claim. Installer work bounded to 10 minutes; database up to 6 minutes; smoke to
3 minutes. Generated CI owns only its isolated project/volume. Operator failure
preserves the PP data volume; no automatic deletion/rollback of database contents.

Required subsequent regressions:
- Wrong schema/version/environment; malformed timestamps/decimals; duplicate and
  conflicting identities; missing/broken protected references.
- A→B→A with concurrent/late events, crashes/restarts, one writer, exact durable
  acknowledgements and forward recovery.
- Archive outage/ambiguous upload/corruption/cancellation, failed retirement,
  reader drainage, final authenticated readback and mutation-authority continuity.
- Actual dashboard/API/SSE parity/reconnect, stale feeds, market boundaries,
  history after retirement and deterministic calculations.
- Deployment failures before/after migration; fencing; actual storage/WAL/temp,
  logs/images/RAM and outstanding sync/backlog accounting.

Retain zero two-second API timeouts, save/heartbeat delays below one second,
feature/input ages within 30 seconds and timely rollover. Small fixtures prove
only their correctness scope. Representative work proves capacity/performance.
The old 5 GiB slot target and 24 GiB transition estimate are not applied PG
limits. Larger qualification packages need explicit resource/time bounds.

Paid AI, trading, hourly work, new infrastructure, database copies/snapshots,
manual WAL/VACUUM shortcuts and Phase 2 remain outside this implementation.

Implementation references: [Docker Ubuntu installation](https://docs.docker.com/engine/install/ubuntu/),
[official PostgreSQL image](https://hub.docker.com/_/postgres),
[PostgreSQL 17 resource settings](https://www.postgresql.org/docs/17/runtime-config-resource.html).
Historical detailed storage evidence is preserved in the
[archived stacked roadmap](https://github.com/JakeMofa/Trading_Bot_Analytics/blob/archive/pr14-stacked-2026-11-12/docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md).

---

## Historical product phases — dated baseline, not current checkpoint

The sections below retain the original roadmap. Their phase/branch and SQLite
statements are superseded where they conflict with the active programme above.
They do not authorize new work or declare current production state.

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
