# BTC Intelligence Rebuild Plan

**Branch:** `codex/phase1-75-retention-enable` (working); `codex/lightsail-deployment` (release target)
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

**Current phase:** Phase 1.75 — Lightsail migration and initial cloud soak
**Current branch:** `codex/phase1-75-retention-enable`; preserve the existing checkout and unrelated edits.
**Next gate:** Indexed invalid-timestamp guard candidate prepared: fresh transactional global proof without repeated raw scans. Local210backend/51controls pass; require exact CI and three indexed Linux trials. R5/R6 STOP until qualification; no production guard indexes or cleanup. Last verified production d56b4a7/live/5120; bridge review due2026-11-02T01:56:47.671426Z. Retention/paid AI OFF; I7/Phase1.75 OPEN.

### October 23, 2026 migration preflight

- [x] Verified integration commit `2766234`; preserved unrelated local changes and historical backups. No changes to `main`.
- [x] Baseline suite: 134 tests passed. The local socket test needs sandbox network permission; its first restricted run failed, then passed without code changes.
- [x] Stopped the Mac ensemble and FastAPI/collector before checkpointing. Ensemble ignored SIGINT; standard SIGTERM stopped it. No forced SIGKILL.
- [x] Found ten pre-existing foreign-key violations in `prediction_context_links`, caused by eight outcome observations removed during earlier retention. Restored exactly those eight rows from the read-only `data/backups/pre_retention_phase1_75.db`; preserved a separate pre-repair SQLite copy under ignored local deployment data.
- [x] Fixed retention to preserve outcome observations referenced by prediction history, including references added after a dry-run. Two regression tests added; **136 tests passed**. No production retention was enabled or run.
- [x] Production SQLite: integrity `ok`, zero foreign-key violations, WAL checkpoint `(0,0,0)`, 227,508,224 bytes (~217 MiB), zero WAL bytes after shutdown. Preserved source counts/checkpoint evidence locally.
- [~] AWS access verified; selected Region from local profile is `us-east-2`. Project is on the active Free plan. AWS returned the $12/month `small_3_0` bundle (2 vCPU, 2 GiB RAM, 60 GB SSD); Ubuntu 24.04 instance and attached static IP provisioned. SSH restricted to the operator's current /32; API is not publicly exposed.
- [x] VM dependencies installed and all **136 tests passed on Ubuntu/Python 3.12**. Transferred DB SHA-256, integrity, foreign keys and recorded table counts match the stopped Mac copy. Git bundle transfer avoids putting GitHub credentials on the VM.
- [x] All three non-root systemd services active; service preflight rejects unsafe soak flags and OpenAI credentials. VM config contains only required Polymarket/Supabase credentials. FastAPI is the sole collector; no standalone collector or new feed is started.
- [x] `/health` is `ok`; Coinbase and Polymarket are `live`; active 15-minute market and current numerical forecast present. Only expected `trade_flow` / `btc_order_book` fields are missing. Experimental ensemble remains a separate persisted model process; at this deployment revision `/models/current` exposes only the RAM baseline. The Phase 1.5 feature branch adds persisted ensemble exposure before its separate manual deployment.
- [x] First VM lifecycle cycle synced 1,478 structured rows, archived 15,420 new observations and 80,590 new Coinbase events with authenticated readback verification. Both archive checkpoints advanced; retention status `disabled`, no deletion recorded. Historical AI suggestion count remains 1,277.
- [x] Added validated systemd units/runbook and a VM-side five-minute read-only metrics timer. Its JSONL ring is capped at 288 snapshots (~24 hours), independent of the Mac. Initial archive catch-up sample used ~612 MB host RAM, ~3.0 GB disk, and ~177 MB combined app-service memory; transient sampled CPU reached 62% during catch-up. These are initial samples, not 24-hour sizing conclusions.
- [x] First-boot cloud-init's SSH reload failed because `ssh.service` was not yet active. Explicitly started the service after `sshd -t`; operator-only UFW and Lightsail firewall rules are active. This is a resolved initialization warning, not an application failure.
- [x] Reboot recovery verified: three services automatically active, both feeds live, new 22:30 UTC market followed, fresh RAM forecast, SQLite integrity `ok`, zero foreign-key violations, no application errors or unplanned restarts. Mac collector remains stopped and its DB checksum is unchanged since cutover.
- [x] Independent readback from the VM verified compressed byte count, SHA-256 and JSONL event count for the newest archive from each feed; 297 manifests verified / zero unverified at the first check.
- [x] Deployment performance diagnosis found repeated outcome scans for every historical snapshot when a market's raw metadata is no longer local. Experimental ensemble's first VM calculation took ~157 seconds. `match_cases` now caches missing-evidence lookups per market **within each call only**; later calls still see newly available evidence. Timestamp rules, fixed-scale scores and one-case-per-market behavior are unchanged. **137 local tests pass**, including query-count and later-outcome regression coverage.
- [x] Missing-evidence caching passed **137 tests on Linux** and reduced VM matching to 9.07 seconds. On the stopped Mac DB, old/new complete results were identical; outcome lookups fell from 6,553 to 386 and elapsed time from 94.94 to 5.97 seconds.
- [x] Query-plan inspection then found no observation index. Added an idempotent `(market_id,kind,received_at)` index; a legacy-DB regression checks preserved raw rows, exact target decimals and foreign keys. **138 local tests passed**. Matching an indexed copy of the production DB took 0.038 seconds; the production Mac DB and historical backups were not altered by benchmarking.
- [x] Final indexed version `66bed20` passed **138 tests on Ubuntu/Python 3.12**. VM matching took **0.0786 seconds**; integrity stayed `ok` with zero foreign-key violations. Indexed/unindexed complete results also matched on the stopped production Mac data. Ensemble forecasts are now fresh, with the latest sampled host CPU at 1% after indexing.
- [x] Final 22:38 UTC / 5:38 p.m. CDT snapshot: all three services active, zero automatic restarts/errors; ~480 MiB host RAM used out of ~1,906 MiB, ~2.79 GiB disk used out of ~57.08 GiB, SQLite ~225 MiB and WAL ~18.2 MiB. Verified archive checkpoints and structured sync continue advancing. See `LIGHTSAIL_DEPLOYMENT_2026-10-23.md` for the deployment report.
- [x] Final access/storage check: 299 verified manifests / zero unverified; API listens only on `127.0.0.1:8000`; effective SSH password authentication/root login both disabled; private configuration mode 600. Static IP remains attached and only operator-/32 SSH is allowed.
- [ ] Review a full 24-hour run of the final version (no earlier than October 24 after ~5:38 p.m. America/Chicago). Five-minute bounded VM snapshots are active. Do not enable retention or Phase 2 based only on the initial smoke test.

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
| 1.5 | [x] | FastAPI service layer | Dashboard, LiveState SSE, System monitoring and ensemble exposure deployed/verified on Lightsail; controlled manual CD passed October 25 |
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

**Status: PRODUCTION VERIFIED — October 25, 2026. Feature integrated into the deployment branch, exact-revision CI and manually dispatched CD passed, all four dashboard tabs verified over private SSH access. OpenAI and retention remain OFF.**

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
- Deferred outside Phase 1.5: connection pooling/reuse when direct Postgres access is introduced; current background writes are unchanged.
- [x] Do not route every market tick through Supabase.
- [x] Add request/response tests and latency measurements.

### Current Phase 1.5 evidence

- [x] `run_api.py` starts one local service process and loads the ignored project `.env`.
- [x] FastAPI owns the same `LiveState` object passed into the collectors.
- [x] `/state/current`, `/forecast/current`, core `/health`, and baseline models read RAM state. `/models/current` adds a bounded query-only read of the existing separately persisted `ensemble_v1`; it never changes the RAM baseline or starts another process.
- [x] `/history/predictions` is bounded to 1–500 rows and opens SQLite query-only.
- [x] `/events` provides a Server-Sent Events stream when the RAM state changes.
- [x] Response-time instrumentation is emitted as `X-Process-Time-Ms`.
- [x] Full local backend suite: **156 passed, 0 failed, 0 skipped** with OpenAI, Supabase sync and retention disabled. The existing Python 3.12 GitHub workflow covers main, codex/** and pull requests; Node.js 22 runs the shipped dashboard contract test. Feature, PR, merge and deployed-revision CI passed; production evidence is recorded below.
- [x] Real live API/feed/rollover/reboot smoke evidence is already recorded in the October 23 Lightsail deployment above (138 Linux tests on the indexed version). This supersedes starting another collector on the stopped Mac database. That historical evidence predates the new UI; the separate October 25 production evidence below verifies this dashboard. The Phase 1.75 soak review remains separate.
- [x] FastAPI serves `/dashboard`; Market/Models/History/System navigation retains the useful market, forecast, Coinbase chart, quote, evaluation, outcome, headline and evidence panels. `/events` supplies live RAM updates; `/state/current` is initial/fallback only. No browser SQLite reads or separate feed relay remain in the production path.
- [~] Cloud sync work has moved to Phase 1.75; no remote DB is in the hot path.

### Phase 1.5 closeout evidence — October 25, 2026

- `codex/phase1-5-dashboard-monitoring` starts at `1eceb8098f21136692230e11fc6d711290e74298`. Unrelated local changes (including AGENTS.md and `.env copy`) are excluded.
- New read-only routes: `/dashboard`, `/dashboard/plan`, `/system/status`, `/system/history`, `/history/context`, `/history/coinbase-chart`. The last two reuse existing saved evaluation/context and bounded chart queries; they are slower history reads, never a live source or a collector.
- `/state/current` and `/events` add server time and the existing deterministic RAM baseline estimate. `/forecast/current` stays unchanged. `/models/current` preserves existing model keys and adds the latest valid `ensemble_v1` with forecast/market provenance, age, experimental label and current-market match. Prior-market/stale ensemble decisions are excluded from the live panel. Forecast methodology and model process ownership are unchanged.
- `/system/status` shows API/collector, timestamped service states/restart counts, current feed ages/cumulative reconnects, CPU/RAM/disk/uptime where available, DB/WAL sizes, OFF flags and existing local cloud lifecycle/checkpoints. CPU/services come from the latest five-minute sample and are marked stale after 15 minutes. Cheap Linux RAM/uptime and filesystem disk/DB sizes are read on request. No subprocess, remote service call or full environment dump is used.
- `/system/history?limit=288` reads a bounded tail (16 MiB maximum, 256 KiB maximum accepted line, 1–288 returned samples) from `SYSTEM_TELEMETRY_PATH` or `cloud-soak.jsonl` alongside SQLite. It ignores malformed rows and projects only approved metrics. Missing data stays unavailable. Charts use actual recorded CPU/RAM/disk/DB/WAL/feed/reconnect/prediction/cloud/checkpoint measurements; missing measurements and time gaps are not filled. Reconnects are labeled cumulative, so no unreliable window delta is invented. Archive object counts are not present locally and remain explicitly unavailable; existing dataset verification/checkpoints are shown.
- Cloud degradation remains separate from core live health, including corrupt/unreadable local telemetry. Free-form cloud error details and source keys are returned as null rather than exposing private diagnostics. Monitoring, history and ensemble reads run outside the async event loop with read-only connections; historical SQL has a one-second progress budget.
- Tests cover dashboard assets, actual FastAPI-to-JavaScript rendering/SSE updates, live endpoints, missing/corrupt telemetry, bounds, safe projection, DB/WAL sizes, disabled flags and valid/invalid persisted ensembles. Browser preview used isolated synthetic fixtures with collectors disabled and verified all four pages plus recorded history charts. No live Mac collector or real cloud write was needed.
- `dashboard.py --once` remains a diagnostic helper; its server launcher is retired and directs users to FastAPI. The Lightsail units, localhost binding, firewall and sole FastAPI collector ownership are unchanged. The existing runbook explains SSH-tunnel dashboard access and intentional manual deployment. The original feature-branch closeout did not deploy production. The subsequent authorized deployment is recorded below; retention/OpenAI enablement, Phase 2/L2, trading and new monitoring products remain excluded.

### Phase 1.5 verified production deployment — October 25, 2026

Production cutover: **5:19 p.m. America/Chicago (22:19 UTC)**. All checks below
refer to the existing Lightsail VM and private SSH tunnel, not synthetic fixtures.

- [x] Pre-merge feature HEAD `55057b7ae425db51aba785d0669058f902d3afa7`; exactly two intended commits/ten files relative to deployment base. Local suite: **156 passed, 0 failed, 0 skipped**. [PR #8](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/8) targeted `codex/lightsail-deployment` and merged after PR CI passed. Merge SHA: `1646079dda2bd3c7368c1e75eccb1980bcc139f1`; [merged-revision CI passed](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/40237436577).
- [x] `OLD_REVISION=1eceb8098f21136692230e11fc6d711290e74298`; **AWS runtime `NEW_REVISION=a7c098900f8310367fc262a1b837c369bb63dc56`** in `/opt/tradebot`. [Exact runtime revision CI passed](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/40239185198): 156 backend tests, no failures/skips. Six additional CD-control tests passed on that revision.
- [x] Controlled `.github/workflows/deploy-tradebot.yml`: production job requires manual `workflow_dispatch`, approved deployment branch, full current SHA and successful exact-SHA CI. Pushes validate controls only. [Manual CD run 40239236113 succeeded](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/40239236113). No automatic production-on-push/merge or main deployment was added.
- [x] With explicit user approval, configured the dedicated forced-command `tradebot-deploy` SSH account/key, root-owned helper and scoped sudo. An arbitrary shell command was rejected. Four repository Actions Secrets are configured: `TRADEBOT_SSH_HOST`, `TRADEBOT_SSH_USER`, `TRADEBOT_SSH_KEY`, `TRADEBOT_SSH_KNOWN_HOSTS`. App credentials remain only in the protected VM `.env`. A checksum-verified ephemeral operator-Mac runner used the existing SSH /32 and unregistered after its job; no runner remains registered. Another manual deployment needs a trusted `tradebot-private` runner online. No firewall/default-branch change was needed; dispatch works through the API/CLI.
- [x] Preflight recorded active/enabled API, ensemble, lifecycle and soak timer; core endpoints/SSE, fresh feeds and cloud lifecycle passed. SQLite `quick_check=ok`, zero foreign-key violations. Protected `.env` hash/owner/mode 600 remained unchanged. No schema/dependency changes were needed; data, archives, production environment and systemd protections were preserved.
- [x] Only `tradebot-api` restarted for the final release. FastAPI remains the sole collector; no Mac collector/ensemble is running. API PID `42366`; ensemble `29843` and lifecycle `29840` retained their original PIDs. All services/timer active/enabled, application automatic restart counts zero. API still binds only to `127.0.0.1:8000`; SSH restrictions unchanged.
- [x] Automatic and independent follow-up smoke passed: `/health` (`ok`, collector running), `/state/current`, `/forecast/current`, `/models/current`, `/cloud/status`, `/system/status`, `/system/history`, `/dashboard` (HTML), `/events` (actual SSE data frame). Additional prediction/context/Coinbase-chart history routes passed. Response scans found no configured credential values; private cloud details/source keys remain redacted. Cloud health remains separate from the live engine.
- [x] Browser validation at `http://127.0.0.1:8000/dashboard` over the private tunnel: Market live BTC changes, exact price-to-beat, moving countdown, UP/DOWN quotes, forecast, Coinbase SVG chart and feed freshness; Models RAM baseline plus persisted experimental ensemble with market/time provenance; History 100 persisted predictions, evaluation, saved headlines/outcomes/context; System host/API/collector/services, real resources, DB/WAL, cumulative reconnects, OFF flags, lifecycle and charts from **288 actual telemetry samples**. Prior-market ensembles remain excluded from live decisions; API reported current ensemble match true and age ~4.2 seconds. Historical news/context remains visibly dated; no news-ingestion scope was added.
- [x] At 22:19:49 UTC: Coinbase age **0.106 s**, Polymarket **0.065 s**, both live; SQLite **1,954,680,832 bytes**, WAL **44,899,792 bytes**; disk free **56,033,255,424 bytes**. SQLite remains below the unchanged 2,048 MiB collection guard; retention stays OFF. CPU/service history is timestamped rather than presented as a continuous measurement; unavailable archive object counts/source-ID fields remain unavailable.
- [x] Cloud status `ok`, lifecycle running/last cycle `ok`, no lifecycle error. During this task verified archives advanced by **3,335 observations / 11,883 stream events**; structured sync advanced by **32 feature rows / 62 prediction rows / 22 candles / 33 markets**. Both archive dataset statuses are `verified`. This is operational deployment evidence, not a replacement for the separate Phase 1.75 soak/retention safety review.
- [x] Logs inspected: five future-market book HTTP-404 notices occurred **before** cutover; live quotes subsequently recovered. Final post-cutover check: **180 journal entries, zero warning-or-higher entries, zero application error matches**. Live engine remained responsive during historical dashboard reads.
- [x] Rollback path is recorded root-only in `/opt/tradebot/data/deployments/`. First CD attempt started the UI and passed all endpoints but a timer-property checker `KeyError` incorrectly caused rollback; old revision and all legacy smoke checks recovered. Fixed timer handling and limited automatic rollback to material assertion/command failures; internal checker errors now fail for manual verification. A second attempt stopped before checkout on a transient baseline request timeout; bounded retries and endpoint-specific safe diagnostics were added. Six tests cover material-failure rollback/recheck, nonmaterial checker behavior, timer fields, preflight failure, branch/event guards and wrong bundle refs. The final CD run passed; no destructive repair or data deletion was attempted.
- [x] `main` remains `b01d3236a705eb74d85ba3df8b1a98411b4a5723`; unrelated local files and `.env copy` remain excluded. No secrets committed, OpenAI credentials absent on VM, OpenAI/retention OFF in all three process environments. No Phase 2/L2, automated trading, RDS/S3 or external monitoring product was added.

**Phase 1.5 production gate: PASS.** Existing roadmap updated only after successful
AWS CD, independent smoke, service/log checks and four-tab browser verification.
The next checkpoint is deliberate retention validation/enablement; it was not
started here. Phase 2 remains deferred. Later evidence/runbook-only commits may
be ahead of the recorded runtime SHA; do not confuse them with an AWS redeploy.

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
- [x] **P1.75.4** Verified retention tooling and one-time production purge/compaction complete; automatic retention remains disabled for the initial AWS soak. October 23 integrity repair preserves referenced outcome evidence.
- [~] **P1.75.5** Deploy the current numerical/API/lifecycle stack to Lightsail and validate 24/7 operation before Phase 2.
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


## Phase 1.75 retention enablement — STOPPED October 25, 2026

**NOT COMPLETE. No retention apply, continuous enablement, restart or deployment
was performed during this attempt.** Dedicated branch
`codex/phase1-75-retention-enable` starts at deployment HEAD
`eaca36c2b453c9e78f4c157a91b76aac398bedf0`. Production independently reports
`a7c098900f8310367fc262a1b837c369bb63dc56`; the intervening commit is documentation
only. Baseline deployment-branch CI run `40239979619` passed.

Verified evidence:

- Backend: 156 passed, 0 failed, 0 skipped; deployment controls: 6 passed,
  0 failed, 0 skipped. The initial sandbox run had one worker/socket startup
  failure; the unchanged full suite passed with the required local permissions.
- Production API, ensemble, lifecycle and soak timer active/enabled; API private
  at `127.0.0.1:8000`, collector running, feeds fresh, zero recorded service
  restarts. OpenAI OFF and retention OFF.
- Baseline captured starting `2026-10-25T22:42:23.680290+00:00`: SQLite
  1,969,627,136 bytes; WAL 44,899,792 bytes; integrity `ok`; zero FK violations.
  Database plus WAL leaves approximately 126.8 MiB below the unchanged 2,048 MiB
  guard. This is current headroom, not proof of a safe steady-state 48h window.
- Cloud inventory: observations 98 verified manifests / 379,498 archived events;
  stream_events 391 verified manifests / 1,813,141 archived events; zero
  unverified manifests. Earliest, near-cutoff and latest objects from each
  dataset (six total) passed authenticated readback, compressed-byte/SHA-256,
  decompressed event count, dataset/source/path and first/last range checks.
  Inventory and spot checks do not constitute completed candidate coverage proof.
- Query-only dry-run at cutoff `2026-10-23T22:48:12.749982+00:00` reported BOTH
  datasets blocked as `non_canonical_received_at`, zero eligible rows and zero
  database changes. Counts: observations 183,306; stream_events 652,795.
  An independent range calculation found 16,506 old observation candidates,
  eight protected old observations, and 87,411 old stream-event candidates;
  these are diagnostic counts, NOT approved deletion bounds.
- Follow-up read-only format inspection found exactly one 25-character timestamp
  in each raw table: observations `2026-10-25T21:46:01+00:00` and stream_events
  `2026-10-25T19:44:19+00:00`. All other inspected timestamps were 32 characters.
  Existing retention requires UTC with six-digit microseconds. Raw writers use
  default `datetime.isoformat()`, which omits the fraction at exactly zero
  microseconds. No raw rows or archive metadata were changed.

**BLOCKER:** existing retention refuses the actual timestamp formats, so dry-run
candidate review and apply authorization gates are unresolved.
**OWNER:** AI / WORK for diagnosis and a reviewed remedy; USER / OPERATOR for
resolution of this explicit stop before any production change or data rewrite.
**STOP CONDITION:** surprising/unexplained dry-run count mismatch, subsequently
explained by the fail-closed timestamp-format block; checkpoint 9/10 cannot pass.
**REQUIRED NEXT ACTION:** resolve timestamp compatibility with a reviewed,
archive/cursor-safe approach; do not disable the format check or rewrite evidence
to force eligibility. Then rerun coverage/dry-run, establish a verified backup,
and pass all remaining apply/recovery/continuous-retention/CI/CD gates.

Evidence is preserved locally under ignored
`data/deploy/lightsail/phase1-75-20261025/`. Backup/recovery point was not created
or verified; apply, restart/recovery, continuous retention, multiple retention
cycles and storage stability are unperformed. No code/config change, secrets,
main change, guard change, VACUUM, public exposure or Phase 2 work was included.


### Timestamp continuation — local test STOP, October 25, 2026

Feature branch remains `codex/phase1-75-retention-enable` at
`e22866fd116fade0300504338638eda68b14cc46`; changes are uncommitted.
Read-only production check at `2026-10-25T23:14:57.825910+00:00` confirmed
runtime `a7c098900f8310367fc262a1b837c369bb63dc56`, healthy collector/feeds,
active API/ensemble/lifecycle with zero service restarts, and OpenAI/retention OFF.
SQLite 1,988,763,648 bytes plus WAL 44,899,792 bytes leaves about 108.6 MiB
below the unchanged 2,048 MiB guard; steady-state working-set safety is unproven.

Local draft changes add explicit microseconds at raw write boundaries, strict
UTC second/six-fraction parsing, semantic date validation, and canonical SQL
comparison keys with indexed raw stream envelopes. Observation identity remains
ID/range based; stream identity remains timestamp/source/event_id. No historical
production row, archive object or manifest was changed. No production write,
restart, apply or deployment occurred.

Dedicated retention: 26 passed, 0 failed, 0 skipped. Full backend: 159 passed,
1 failed, 0 skipped (160 total). Deployment controls: 6 passed, 0 failed,
0 skipped. Full-suite failure:
`test_cases.CaseTests.test_known_outcome_only_one_snapshot_per_market` expects
`2026-09-30T01:20:00Z` but gets `2026-09-30T01:20:00.000000+00:00` because
shared observation-writer normalization changes a supplied timestamp's spelling.
The explicit user STOP-on-test-failure gate was honored. Do not weaken the test;
review the writer boundary and historical-case response compatibility before
resuming. Local logs are `/tmp/tradebot-backend-tests.log`,
`/tmp/tradebot-retention-tests.log`, and `/tmp/tradebot-cd-tests.log`.

No commit/push/CI/PR or deployment was attempted. Fresh coverage/dry-run,
independent reconciliation, backup, apply, integrity/FKs, restart/recovery,
continuous retention, real cycles, storage stability and working-set headroom
remain NOT REACHED. Phase 1.75 remains NOT COMPLETE. Stop before Phase 2.


### Writer-boundary resume — stream safety STOP, October 25, 2026

Start/end committed HEAD: `e22866fd116fade0300504338638eda68b14cc46` on
`codex/phase1-75-retention-enable`. Uncommitted retention/parser/comparison
changes were preserved. Removed normalization from shared `save_observation`;
live collector discovery/quote/resolution and Polymarket WebSocket receive times
now explicitly emit six microseconds. Coinbase stream emission retains the draft
six-microsecond fix. Historical-case test expectation is unchanged.

Focused results: retention 27/27, streaming 12/12, collector 10/10, historical
cases 3/3. `test_known_outcome_only_one_snapshot_per_market` PASS. Added separate
shared-writer preservation, live WebSocket/Coinbase and live REST regression
coverage. Full backend and deployment-control reruns NOT REACHED due to the
following mandatory stream-safety STOP.

In-memory reproduction (no production access): archive two old stream events,
plan retention (2 eligible), insert a third late event inside the archived cursor
interval, then apply the original plan. Fresh planning rejects the manifest with
`local_rows_exceed_manifest` and reports 0 eligible / 3 uncovered; apply using the
original plan instead deletes 3, including the unarchived late event. Apply trusts
previously approved intervals without revalidating archive coverage after planning.
Logical cursor remains timestamp/source/event_id, but stream deletion safety FAILS.

BLOCKER: unarchived late stream evidence can be deleted between plan and apply.
OWNER: retention implementation. STOP CONDITION: unverified evidence would be
deleted / stream safety not established. REQUIRED NEXT ACTION: authorized repair
of apply-time coverage validation and concurrency protection, with regression for
a late row arriving after planning, before rerunning all required gates. Do not
work around this STOP or enable retention.

No commit/push/CI/PR, production read/write, backup, retention apply, restart or
deployment occurred in this resume. Production historical rows, archive objects
and manifests were NOT modified. Production OpenAI/retention OFF is the supplied
baseline, not freshly verified. Fresh coverage/cutoff/dry-run/reconciliation,
backup/recovery, integrity/FKs, live engine, deployment, continuous retention,
multiple cycles, storage stability/headroom remain NOT REACHED. Phase 1.75 NOT
COMPLETE. Stop before Phase 2.


### Import-error resume — focused retention gate STOP, October 25, 2026

**PHASE 1.75 — NOT COMPLETE.** Verified branch
`codex/phase1-75-retention-enable` and committed HEAD
`e22866fd116fade0300504338638eda68b14cc46`. Preserved existing uncommitted
work. Moved only `import retention` below the test module's app-path setup;
no test assertions were changed.

Reviewed the unverified implementation before testing: planning captures approved
identities in a read snapshot; apply intersects those identities with fresh local
manifest coverage, newest observation anchor and prediction-reference protections
inside each bounded `BEGIN IMMEDIATE` transaction. Apply does not use stale
`plan['_intervals']` as final authority. This review does not establish completion.

Focused retention gate: **30 executed, 29 passed, 1 failed, 0 skipped**.
Late-row-after-plan, manifest-count-slack, separate-writer lock and late-reference
regressions passed. Mandatory gate failed in
`test_apply_uses_bounded_batches_and_leaves_structured_tables_alone`,
`backend/tests/test_retention.py:405`: expected observation batch count 8,
actual 7 (`AssertionError: 7 != 8`). Evidence:
`/tmp/tradebot-phase175-retention-resume.log`.

**BLOCKER:** focused bounded-batch safety regression fails.
**OWNER:** retention implementation / this worker.
**STOP CONDITION:** any mandatory safety/test gate failure.
**REQUIRED NEXT ACTION:** obtain authorization to investigate the batch-count
mismatch and repair the implementation without weakening safety tests, then
restart the focused gate and remaining gates in order.

Stopped after this gate. No further suites, commit/push, feature CI, production
access, retention apply, backup, service restart, deployment or continuous
retention occurred. Production baseline was not freshly revalidated. Every
remaining original Phase 1.75 gate is pending; stop before Phase 2.


### Bounded-batch repair — full backend gate STOP, October 25, 2026

**PHASE 1.75 — NOT COMPLETE.** Branch/committed HEAD verified unchanged:
`codex/phase1-75-retention-enable`,
`e22866fd116fade0300504338638eda68b14cc46`.

Reproduced the authorized known batch-count failure in isolation (expected 8,
actual 7). Root cause: candidate selection crossed disjoint archive interval
boundaries, packing 20 rows into ceil(20/3)=7 batches instead of preserving the
committed per-interval contract (two intervals, each ceil(10/3)=4). Repaired
selection to commit a nonempty partial interval batch before moving to another
interval. Kept fresh coverage/protection validation inside every BEGIN IMMEDIATE,
approved identity intersection and exact deletion predicates. Original expected
batch count remains 8; no assertions were weakened or removed.

Strengthened the existing regression with SQLite transaction tracing: committed
changes are [3,3,3,1,3,3,3,1], sum 20, no batch exceeds 3, reported batch count
matches actual committed delete batches, exact remaining IDs are 21..30, and
re-applying the same approved plan commits no additional deletes/batches.

Gate evidence:
- Focused retention/concurrency: 30 passed, 0 failed, 0 skipped
  (`/tmp/tradebot-phase175-retention-repaired.log`).
- Streaming: 12 passed; collector: 10 passed; historical: 3 passed; no failures
  or skips (`/tmp/tradebot-phase175-streaming.log`,
  `/tmp/tradebot-phase175-collector.log`, `/tmp/tradebot-phase175-historical.log`).
- Full backend: 165 executed, 164 passed, 1 failed, 0 skipped
  (`/tmp/tradebot-phase175-backend.log`).

**BLOCKER:** `test_lock_release_after_crash_and_controlled_restart`
(`backend/tests/test_operations.py:80`) fails with
`AssertionError: Worker failed to start`.
**OWNER:** operations worker startup/recovery test path; root cause uninvestigated.
**STOP CONDITION:** any mandatory test/safety gate failure.
**REQUIRED NEXT ACTION:** authorize investigation of the worker-startup failure,
repair its cause without weakening tests, and restart required validation gates.

Stopped at the full backend gate. Deployment-control tests, final diff review,
commit/push, feature CI and every production/retention/recovery/deployment gate
remain pending. No production access or writes, backup, retention apply, restart,
deployment, continuous enablement or Phase 2 occurred. Existing unrelated local
changes remain preserved; no commit was made.


### Operations startup investigation — local gates passed, October 25, 2026

Isolated the known operations failure with unchanged code and tests. The worker
command uses the active Python interpreter, injects the absolute app module path,
and supplies a unique temporary database identity. It successfully imports
operations and takes the per-database flock, then exits immediately at
`asyncio.start_unix_server` / `socket.bind` with
`PermissionError: [Errno 1] Operation not permitted`. The earlier full-suite log
contains the same traceback. No retention module is imported by this minimal
worker. It does not open SQLite, read retention flags or run deletion transactions.
This is a local execution-sandbox socket restriction, not an established code
regression, stale PID/lock or startup timeout. No timeout, sleep, readiness
condition, assertion or operations implementation was changed.

With local Unix socket access allowed, the unchanged isolated crash/restart test
passed (including duplicate-lock rejection, kernel lock release after SIGKILL,
same-identity restart and acknowledged controlled shutdown). Unique temp paths
exclude old database identities; a stale socket after crash is unlinked by the
existing control-server startup. The readiness deadline stayed at five seconds.
The entire operations module passed 5/5 and full backend passed **165/165,
0 failures, 0 skips**, with OpenAI, sync and retention disabled. Deployment
controls subsequently passed **6/6, 0 failures, 0 skips**.

Evidence: `/tmp/tradebot-phase175-operations-isolated.log` (sandbox diagnosis),
`/tmp/tradebot-phase175-operations-isolated-unrestricted.log`,
`/tmp/tradebot-phase175-operations-module.log`,
`/tmp/tradebot-phase175-backend-unrestricted.log`,
`/tmp/tradebot-phase175-deployment-controls.log`.

Reviewed accumulated application/test diff: strict accepted UTC timestamp widths,
writer-boundary canonical emission while shared historical writer preserves input,
approved identity capture in a single snapshot, fresh coverage and references
under each BEGIN IMMEDIATE, exact identity deletes, per-interval bounded batches
and committed-delete accounting. Existing/new regressions pass, including eight
observation batches and same-plan safe re-apply. Diff whitespace check passed.
Only intended application/tests and this checklist are eligible for the feature
commit; unrelated AGENTS.md and untracked local files/secrets remain excluded.

**PHASE 1.75 remains NOT COMPLETE.** Local test/diff gates passed; commit/push,
exact-revision feature CI and all remaining production coverage/reconciliation,
backup/apply/integrity/live-engine/recovery/CD/continuous-cycle/storage gates
remain required. No production action has been taken in this investigation.

### October 30, 2026 — I7-only release prepared; live verification STOP

- [x] Preserved the current feature checkout and all pre-existing local edits. Historical context pack and index saved in `docs/PROJECT_CONTEXT.md` (`9876eb9`); full exports remain local-only and Git-ignored. All six compact files read; full transcript review unfinished. No failed reviewers restarted or Tradebot paid OpenAI calls made.
- [x] Isolated only the worker containment from `b809efc` onto the existing deployment branch as `d56b4a73ad6f1a10ba2bac928087cd5d85c6a42a`. No new branch/worktree. Retention/collector timestamp changes excluded. Exported-source validation: **159 backend + 6 deployment tests PASS**, compilation PASS; exact-revision CI run `41138048640` PASS.
- [~] Manual controlled CD run `41138249460` passed workflow and SHA/CI gates, then remained in full SQLite preflight verification before checkout. During 85 five-second live samples, 148/170 probes timed out and observed feature age reached **331.25 seconds**. The verification reader was in disk wait; this does not individually attribute all added lag to that reader.
- [x] Stopped safely before checkout: cancelled the workflow, verified old production SHA and absence of a new checkout record, terminated only this attempt's verification Python process (9199), confirmed exit, and removed the one-job runner after automatic unregistration. No application service was signaled/restarted. No deployment/rollback, retention, guard change, VACUUM/WAL manipulation, schema/index change, AWS/network change or Phase 2.
- [ ] **I7 remains OPEN; worker fix NOT DEPLOYED.** Fresh production stays `a7c0989`; API/ensemble/lifecycle PIDs 2273/849/843, active, zero automatic restarts. Process OpenAI/retention OFF, guard4096 MiB. The final 13 samples through 17:38:13 America/Chicago still timed out; no recovery PASS. Final DB3,996,729,344 bytes, WAL9,805,632 bytes, diskfree51,865,370,624 bytes.
- **BLOCKER / OWNER:** full live SQLite verification cannot yet be completed safely alongside the blocking feature scan / controlled-release preflight path. Preserve complete structural/FK gates; do not retry the same heavy scan or force a release.
- **NEXT:** prepare/review a bounded verification and release procedure that protects collection and preserves rollback and complete SQLite checks. Then deploy the tested I7-only revision and validate multiple cycles, API/feed responsiveness, feature age, I/O, collector coexistence and WAL growth. Retention R5/R6 remains STOP; Phase 1.75 unfinished; Phase 2 deferred.
- Evidence and precise limits: `I7_RELEASE_ATTEMPT_2026-10-30.md`; local `evidence/phase175-baseline/i7-only-release-20261030/`. Broader architecture discussion remains deferred until the Phase 2 boundary per the user's current direction.

### October 30, 2026 — bounded I7 maintenance continuation prepared

- [x] Implemented `deploy/lightsail/i7_maintenance.py` and its reviewed-scope runbook `deploy/lightsail/I7_MAINTENANCE.md` on the existing feature branch. Plan-only by default; fixed old runtime `a7c0989` and I7-only application candidate `d56b4a7`. No normal CD/forced-command helper change, new branch/worktree or production operation.
- [x] **26 local deployment/maintenance tests PASS**, compilation and diff checks PASS. Real SQLite fixtures verify complete checks and FK/corruption refusal without file mutation. Tests also cover owner aliases, WAL preservation, child timeout/reaping, restart configuration masking, failed-check non-deployment, partial-stop restoration and code rollback. GitHub CI now includes all deployment/maintenance tests alongside backend tests.
- [ ] Proposed supervised window: 20-minute work budget plus five-minute recovery reserve; intentional collection gap requires operator approval. Stop monitor, wait for a responsive API stop window, stop API/lifecycle/ensemble, prove no SQLite owners/nonempty WAL, create and readback-verify a root-private copy on the same VM, then complete quick/FK checks in bounded read-only child processes before checkout. No Mac DB copy, retention, manual WAL operation, schema/index change, guard increase, credentials/network/AWS resource change or Phase 2.
- [ ] Fresh exact-SHA CI must pass for application and helper before execution. The helper accepts a trusted operator acknowledgment; it does not independently query GitHub. On failure, restore prior code/services without overwriting collected DB data; report unproven API recovery honestly. New-code success is only `deployed_pending_I7_validation`.
- **Current position unchanged:** I7 OPEN, worker fix undeployed; full live verification STOP preserved. Retention R5/R6 STOP; Phase 1.75 unfinished. See `I7_RELEASE_ATTEMPT_2026-10-30.md` for evidence and the bounded continuation. No new production measurement is claimed by this preparation.

### October 30, 2026 — authorized no-copy I7 exact-release exception

- [x] User rejected database copies/snapshots and selected a scoped code-only release exception. Copy-based maintenance runbook is withdrawn and its execute CLI disabled. The replacement operational procedure is `deploy/lightsail/I7_SCOPED_RELEASE.md`; this document remains the single roadmap.
- [x] Prepared temporary protected deployment-helper controls for exact old `a7c098900f8310367fc262a1b837c369bb63dc56` -> application `d56b4a73ad6f1a10ba2bac928087cd5d85c6a42a`, exact six-file scope, bundle/ancestry and one-use root-owned exact-CI acknowledgment. Full quick/FK checks explicitly `NOT_PERFORMED_SCOPED_I7_EXCEPTION`; bounded five-second metadata child is readiness only. Normal release verification unchanged.
- [x] Local validation: 182 backend + 33 deployment/control tests PASS, compile/diff checks PASS. Existing socket test required local socket access. Tested refusal, real metadata-only SQLite fixtures, child timeout/reaping, partial checkout, restart/smoke/deadline recovery and failed rollback reporting.
- [ ] Require exact helper CI, freshly verify application CI/branch, temporarily install verified helper through existing pinned operator SSH, dispatch existing Actions workflow once, restart only API, restore protected helper afterward. Work600s + recovery180s inside Actions900s; no automatic retry.
- [ ] Observe >=20 minutes and >=3 completed feature cycles (max30 minutes). Record five-second/two-second-timeout API/feed probes, timestamps, feature/input age, rollover, service stability, persistence and resource/storage evidence. Snapshot target30s; input-price rule30s. Containment and freshness reported separately; I7 remains OPEN until evidence passes.
- Retention/paid OpenAI OFF; guard4096; no DB copy/snapshot, full live scan, WAL manipulation, migration/index, infrastructure/network change or Phase2. Full quick/FK audit remains outstanding before retention.

### October 30, 2026 — I7 worker deployed; API containment observed, freshness FAIL

- [x] Implemented and published no-copy exact-release controls (`c2304eb`); local182 backend +33 deployment/control tests and exact helper CI41159551744 PASS. Candidate`d56b4a7` exact CI41138048640 reverified. User explicitly authorized execution; no new branch/worktree.
- [x] Manual Actions41159675569 succeeded once: production now`d56b4a73ad6f1a10ba2bac928087cd5d85c6a42a`. Five-second metadata readiness and all12 existing smoke routes/SSE/dashboard PASS. Full quick/FK audit explicitly **NOT_PERFORMED_SCOPED_I7_EXCEPTION**; remains required before retention.
- [x] API only restarted(PID2273->10915); ensemble849/lifecycle843/monitor retained. Existing systemd60s stop policy killed the unresponsive old API, followed by~85s startup/hydration; stop-request-to-listener~146s. No extra kill or WAL command. Missing source events not assumed backfilled. Original protected helper hash restored, authorization consumed/absent; ephemeral runner unregistered and removed.
- [x] Completed 20.85min post-release observation, 11 cycles, 498 probes: **0 failures/0 timeouts**, max0.075s. 2 extension samples lacked probes due unmatched journal reads, disclosed. Cycle duration83.576–86.720s; new snapshot age84.084–204.277s vs30s target **FAIL**. Polymarket stale around rollover; observed first new market~51s late. Follow-up next rollover at02:46:49UTC had new market/live feeds but missing features and degraded health.
- [ ] **I7 OPEN:** sampled API stall containment passes; full freshness/rollover requirements do not. EXPLAIN-only inspection confirms source-filtered stream sort and REST-price table scan/sort. Synthetic in-memory expression-index feasibility passed5 cases, but tie behavior, build I/O/lock budget and writer overhead are unqualified. No production index/schema change.
- **NEXT:** separately review/test the smallest source-time lookup optimization with preserved as-of, exact-decimal, provenance and stale/missing semantics; include rollover/discovery latency. Retention R5/R6 STOP and remaining Phase1.75 gates pending. Full quick/FK audit outstanding. OpenAI/retention OFF, guard4096; no DB copy/snapshot, retention, VACUUM, manual WAL, infrastructure/network change or Phase2.
- Evidence: `I7_PRODUCTION_VALIDATION_2026-10-30.md`; local`evidence/phase175-baseline/i7-scoped-release-20261030/`.

### October 31, 2026 — I7 freshness/rollover local implementation

- [x] Implemented local feature version2 with explicit per-source timestamp tie ordering (stream TEXT key ASC; REST numeric ID ASC), preserving received/source cutoff, Decimal values, provenance and stale/missing behavior. Explicit transaction-only index preparation refuses conflicting definitions; never invoked on startup.
- [x] Feature work now has an independent serial loop with15s pause after completion; REST/source request cadence unchanged. No feature overlap/backlog. Expired, changed-market, future and >30s-old results cannot be newly published to RAM; cancelled workers drain before teardown, including repeated cancellation. Already-published snapshots still expose their original as_of as they age; not a full RAM freshness redesign.
- [x] **189 backend +33 deployment/control tests PASS**, compile/diff checks PASS. New regressions cover indexed/unindexed equivalence, actual stream NOT NULL schema, timestamp offsets/ties, late/future/stale/missing inputs, concurrent REST progress, cadence, publication fences, cancellation draining, transaction requirements and wrong-definition refusal.
- [x] Synthetic100k/1m rows per price table measured build time, page growth and warm lookup speed; another writer received SQLITE_BUSY during the schema transaction and resumed afterward. This is generated data, no DB copy/snapshot, and is **not production qualification**. Details: `I7_FRESHNESS_LOCAL_2026-10-31.md`; local`evidence/phase175-baseline/i7-freshness-local-20261031/`.
- [ ] **NOT DEPLOYED.** No production reads/changes in this milestone; last verified runtime remains`d56b4a7`. Qualify current guard headroom, combined index/WAL/build/ongoing storage growth and increased snapshot cadence, bounded writer interruption, abort/recovery and required verification before any production CREATE INDEX or release. Do not deploy scheduler alone expecting fast results; its age gate rejects slow completions. Do not reuse prior consumed release exception.
- I7 OPEN, full quick/FK audit outstanding, retention R5/R6 STOP, paid AI/retention OFF, guard4096 unchanged; no infrastructure/network changes or Phase2.

### October 31, 2026 — fresh capacity STOP supersedes healthy checkpoint

- [x] Fresh read-only evidence at`2026-11-01T00:32:04.840498+00:00` (2026-10-31T19:32:04.840498-05:00 Chicago): production still`d56b4a7`, clean checkout, original API/ensemble/lifecycle PIDs10915/849/843 active and zero automatic restarts; collector **STOPPED**, feeds stopped since~04:24AM October31 Chicago; storage_guard`limit_reached`. HTTP/SSE/dashboard respond with retained state, not live evidence.
- [x] DB4278059008 +WAL17431752 = 4096.499214MiB against4096MiB, headroom-523464bytes. Filesystem still48.038GiB free. Header-only five-second SQLite child found0 free pages, auto_vacuum NONE; deleting rows alone must not be assumed to shrink allocated guard usage. No full integrity/FK scan.
- [x] Implemented local read-only readiness assessment with no execute mode; current result STOP for collector/feed/guard/capacity and unqualified build budget. Prepared health correction: clean collector exit or guard reach now degrades cached-RAM health. **Not deployed.**
- [x] **191 backend +40 deployment/control tests PASS**, compile/diff PASS. Existing branch and unrelated edits preserved. See `I7_CAPACITY_STOP_2026-10-31.md`; local`evidence/phase175-baseline/i7-capacity-stop-20261031/`.
- [ ] **NEXT / blocker:** a reviewed capacity recovery operation under user constraints, before index installation, release or restart. Do not bypass/increase guard, delete/rewrite WAL, run retention/VACUUM, create DB copies/snapshots or replace DB as a workaround. R5/R6 remains STOP. Synthetic index work remains unqualified for production. No source collection resumed.
- I7 OPEN; freshness/rollover code remains local-only, full quick/FK audit outstanding, paid AI/retention OFF, guard4096, Phase1.75 unfinished; Phase2 deferred.

### October31,2026 — user authorized end-to-end lifecycle implementation

- User approved a temporary **5120MiB** bridge,48h raw retention, controlled production cleanup only after safety gates, and5120 as permanent ceiling only after measured stability. This explicitly supersedes the earlier4096-only restriction for this operation; no further automatic guard increases. No DB copies/snapshots, VACUUM, manual WAL, new infrastructure, paid AI or Phase2.
- [x] Prepared exact-runtime operator bridge helper and bridge-aware readiness. One4096->5120 config setting, unchanged application`d56b4a7`, API-only restart, >=10GiB disk free / >=512MiB proposed headroom,5min continuous feed/current-market/API observation,10min work +3min recovery,24h review deadline. No retained .env backup or credentials in evidence. **51 deployment/control tests PASS**, compile/diff PASS.
- [ ] Exact helper CI, then authorized bridge execution and measured restoration. Until execution evidence, production remains guard-stopped at4096; do not claim resumed collection.
- [ ] Narrow retention SQL/temp-key optimization with all current transaction safety checks; target250ms/max500ms writer transactions,1000row initial batches/100ms handoff; three full Linux generated-fixture trials<=180s each with actual deployed collector ordering,150ms saves/50ms heartbeat, zero errors and maxsave/heartbeat<1s. Limits2GiB fixture disk/512MiB per process; stop on production interference. R5/R6 remain STOP until proof.
- [ ] Fresh archive/readback and full SQLite quick/FK verification before deletion; R7 archive-backed exact-raw-row recovery manifest and in-memory reconstruction, not a fullDB backup. First production cleanup<=1000rows with identity/protected/FK/collector verification; no broad purge. Maintenance30min +3min recovery.
- [ ] Qualified index installation and isolated freshness/health release; >=20min,>=3cycles and market boundary,<=30s snapshot age, zero2s API timeouts. No reuse of prior deployment exception.
- [ ] Retention enabled only in lifecycle after gates, leaving API/ensemble OFF. Role-specific preflight/service change required because existing command forcesOFF. Hourly archive/retention initially; same-cycle verified archives required.24h soak before permanent5120 ceiling / Phase1.75 closeout.

### October31,2026 — collection restored; SQL retention candidate prepared

- [x] Authorized **5120MiB bridge ACTIVE**, application unchanged`d56b4a7`. Exact helper`8187465` CI41263032555 passed and export/VM SHA matched. Guard-only config change, API-only restart~0.393s(PID17165), ensemble849/lifecycle843/monitor unchanged; zero automatic restarts. No DB copy/config backup, no retention/index/application release.
- [x] Passed5continuous minutes after existing rollover reset (114 samples total), live feeds/current market/API/dashboard/SSE. Review due`2026-11-02T01:56:47.671426+00:00` UTC (2026-11-01T19:56:47.671426-06:00 Chicago);5120 not permanent until24h measured stability. Paid AI/retention remainOFF.
- [x] Prepared SQL/TEMP retention optimization retaining all fresh writer-transaction safety checks. Deadline500ms/target250ms, accurate post-commit overrun reporting; temp bookkeeping outside writer,100ms handoff.44existing retention safety tests and2new deadline tests pass.
- [x] Full local **194 backend tests PASS,1Linux-only self-test skipped;51 deployment/control tests PASS**, compile/diff PASS. Generated Linux harness prepared with180s/trial,512MiB/process and2GiB fixture/TEMP cap; production health guard, actual deployed collector save/RAM ordering and exact helper hash.
- [ ] Require exact candidate CI, then three complete Linux generated-fixture trials. R5/R6 remains STOP until those pass; stop on any failed bound/interference. No production cleanup or archive/audit gates bypassed. See `LIFECYCLE_48H_EXECUTION_2026-10-31.md`; local`evidence/phase175-baseline/lifecycle-implementation-20261031/`.

### October31,2026 — first Linux retention qualification STOP; local merge candidate

- Exact candidate`1c714e4` CI41264132465 passed195 backend/51 controls, including tiny Linux harness self-test. Actual isolated Linux profile647089 observations/1867728 stream rows used real deployed save helper SHA95a49c2ac04b6dbb04223e0f363df0a6132bd7b0cc10fda7145a2055bd1efa12.
- **R5/R6 remains STOP:** first generated trial aborted at writer deadline0.500101783s (`sqlite_progress`),0committed rows. Full trial48.289s, peak generated disk466999157bytes, maxRSS100380KiB; fixture collector95saves/95RAM updates,0errors, maxsave0.431038s, maxheartbeat0.451962s. Production guard recorded0interference errors; generated directory empty after cleanup. No production retention/index/release or additional trials of this failed candidate.
- Prepared local ordered SQL timestamp-set merge candidate (replacing per-value B-tree probes), preserving current global validation under the writer lock, explicit binary collation and separate staging of newly valid strings until merge cursor closes. Same250ms target/500ms deadline; no relaxed proof or extended budget. Add operation-phase attribution. Local synthetic1m indexed membership check0.285s vsorderedmerge0.092s, not a Linux qualification PASS. New exact CI and fresh qualification required.
- Collection remains restored under temporary5120 bridge; do not disable or enlarge it because fixture qualification failed.24h review deadline unchanged.


### October31,2026 — revised Linux qualification STOP; production follow-up live

- Revised timestamp-merge/profile candidate`2753c4a` passed exact CI41265091345 (196backend/51controls). Second generated profile647996 observations/1871555 stream rows stopped after40.725s during fixture generation: production health guard recorded RuntimeError. Retention apply had not begun; merge writer performance remains unqualified. Old diagnostics did not retain the precise feed/collector condition, so causation is unresolved. Trials2/3 not run; no further stress retries.
- Follow-up02:33:46UTC: unchanged`d56b4a7`, API17165/ensemble849/lifecycle843 active with zero automatic restarts, guard5120, paid AI/retention OFF, both feeds live. DB4300345344/WAL18160992bytes; diskfree51556388864bytes. Feature snapshot still stale. Subsequent read-only baseline02:37:53–02:39:23UTC:19/19 samples passed, collector running and both feeds fresh/live. This90s sample does not explain or invalidate the earlier safety STOP.
- Both isolated staging directories and generated fixtures removed after checking processes, directory contents and code hashes. No production DB copied/deleted/replaced, index installed, retention enabled or application release performed.
- Added typed, sanitized guard diagnostics (reason/feed timestamp/status/age), fixture-stage attribution and regression coverage. **197 local backend tests PASS (one Linux-only self-test skipped),51controls PASS**, diff check PASS. No deadline or resource limit weakened. R5/R6 remains STOP; next work is precise guard-condition diagnosis and then three qualified trials, not production cleanup. Bridge review deadline unchanged; I7/Phase1.75 OPEN.


### October31,2026 — bounded diagnosis before another qualification

- Existing API journal02:29:30–02:33:00UTC confirms feature work but has no historical feed-transition log identifying the prior guard failure. Do not infer its cause. Fresh03:50:21UTC runtime remains clean d56b4a7, original PIDs/zero restarts, both feeds live, guard5120, paid AI/retention OFF; DB4346855424/WAL18160992bytes.
- Prepared explicitly bounded one-trial diagnostic mode, with unchanged default three trials, resource/write/health limits and synthetic-only isolation. One pass cannot clear R5/R6. Trial records now include start UTC; precise sanitized health failure/stage diagnostics already tested.197backend tests (one Linux-only skipped)/51controls pass locally; exact CI required before VM use. No cleanup/index/application release authorized by these test results alone.


### October31,2026 — measured retention blocker: global timestamp revalidation

- Exact diagnostic candidate44cb0ec CI41270810424 PASS. One generated-only Linux trial at652932 observations/1890841 stream rows began2026-11-01T03:52:10.489725Z. Preparation92.368s; trial118.760s; peakfixture482989381bytes/maxRSS102216KiB, within approved overall resource limits.
- **R5/R6 STOP:** retention apply reached `timestamp_revalidation:sqlite_progress`, writer duration0.511735474s vs500ms maximum. Failing transaction committed0rows. Fixture collector170saves/170RAM updates,0errors, maxsave0.532594s/maxheartbeat0.561937s. Production guard recorded **no failures**. This identifies the current writer bottleneck; it does not retrospectively identify the previous unrecorded health condition. No trials2/3 or automatic retries.
- Local generated200k-observation/600k-stream EXPLAIN shows observations covering-index scan plus TEMP ORDER BY B-tree, stream covering-index scan and validity-cache merge. Three warm repetitions: shared merge~0.196–0.202s total; separate-cache merge~0.183–0.194s; separate-cache probes~0.607–0.640s. These are local warm-cache diagnostics, not Linux qualification. Cache partitioning alone shows no supported margin at actual scale; do not claim it fixes the500ms gate or weaken current-global validation. No speculative retention algorithm change shipped.
- VM fixture staging removed after checking expected code hashes, empty generated directory and absent fixture process.03:55:23UTC post-test: same d56b4a7/PIDs17165/849/843, zero automatic restarts, both feeds live, guard5120, paid AI/retention OFF. DB4350054400/WAL18160992bytes, free51506302976bytes; guard headroom~954.1MiB. No production DELETE/index/service/config change in this diagnosis.
- **Next gate:** a reviewed replacement for the measured global timestamp revalidation cost that preserves fresh in-transaction proof, followed by three full Linux qualification passes under unchanged limits. Existing candidate is unqualified; no further whole-fixture retry without an evidenced algorithm change. Full audit/archive/recovery/cleanup/freshness/lifecycle/soak gates remain blocked. Temporary bridge review deadline unchanged2026-11-02T01:56:47.671426Z. I7 and Phase1.75 OPEN; no Phase2.


### October31,2026 — approved indexed-NOT-IN candidate rejected locally

- Fresh read-only preflight2026-11-01T04:16:29UTC: production d56b4a7 clean, API17165/ensemble849/lifecycle843 active with zero automatic restarts, guard5120, paid AI/retention OFF, feeds live. DB4362436608/WAL18160992bytes; free51493785600bytes. Indexed MAX(rowid) upper bounds585752/1715411 sized generated profile654328 observations/1896953 stream rows. No historical production scan or write.
- Implemented the approved observation candidate locally: optional existing covering index, binary indexed NOT IN against TEMP validity facts, explicit NULL detection, unknown-only deduplication/staging; stream merge unchanged. Focused correctness tests passed.
- **Rejected before Linux qualification:** generated scale benchmark with97market/3kind groups and the harness's old/recent timestamp overlap measured observation median **1.652084s candidate vs0.332051s existing merge (~5x slower)** over3repetitions. Stream query unchanged (medians0.389064/0.374931s). Initial disjoint-timestamp benchmark also rejected it (1.617995vs0.346658s). Eliminating sort traded it for expensive indexed lookups; tiny planning benchmark did not generalize. These local warm-cache timings are not production timings or qualification.
- Restored the existing runtime merge query. Retained candidate only in generated-only reproducible `backend/benchmark_retention_timestamps.py`; it accepts row counts, never an existing DB path. No unchanged VM trial or production deployment attempted.
- Added per-writer-transaction timing for timestamp revalidation, manifest coverage, protected selection, deletion and commit; expose partial timings on budget exceptions/harness results. Added NULL/case/calendar/optional-index and unknown-dedup/cache regression coverage. **199backend tests PASS (one Linux-only skipped),51controls PASS**, benchmark tiny-run and diff PASS. No safety or time limit weakened.
- **R5/R6 STOP under the approved failure rule:** no compliant replacement has been demonstrated. The unresolved constraint is fresh global timestamp proof on both raw tables in every<=500ms writer transaction at current scale. A replacement must demonstrate a different access strategy/proof implementation, not another unchanged trial; no assertion that all possible implementations are impossible. No archive/readback/audit/recovery/cleanup/index/freshness/lifecycle/soak gates advanced. I7/Phase1.75 OPEN;5120 review deadline unchanged2026-11-02T01:56:47.671426Z.


### October31,2026 — bounded TEMP-cache alternative also rejected locally

- Follow-up generated-only comparison explicitly set TEMP cache2000KiB vs131072KiB (128MiB), with the same654328/1896953 profile and no production configuration changes. Cached NOT IN observation runs0.547290/0.560505/0.537571s, median0.547290s; stream merge median0.342729s. Existing merge medians0.313319/0.329028s. Even the cached observation check alone exceeds500ms locally; this is not sufficient evidence for a Linux trial. No runtime cache tuning or candidate query retained.
- Reproducible standalone benchmark now includes both bounded cache settings. Candidate diagnostics milestone6ef8ce2 exact CI41272687425 PASS (199local backend/51controls; Linux-only test skipped locally). Local tiny benchmark verifies all three variants. Evidence `timestamp-temp-cache-local.json` preserves all repetitions. R5/R6 STOP and production gates unchanged; no compliant implementation demonstrated and no assertion of general impossibility.


### October31,2026 — native strict timestamp proof candidate prepared

- New access strategy retains a fresh global scan of both raw tables in every writer transaction but validates exact raw timestamp bytes directly in a small C SQLite scalar function. No sorting, validity-cache B-tree probes, Python callback per row, or cached row/eligibility facts. Strict25/32-byte UTC formats, ASCII digits, Gregorian calendar/leap years, hour/minute/second bounds, NULL/BLOB rejection match the Python contract. Existing coverage/reference/anchor/exact-identity delete checks and250ms target/500ms deadline unchanged.
- Prototype generated654328/1896953 local checks measured native observation median~51.6ms and stream~146.0ms (sum~197.6ms), versus merge medians~314.8/334.9ms. Local warm-cache evidence is not Linux qualification. Native/Python parser equivalence includes16701 initial cases plus malformed-character mutations in retained tests. Existing retention safety suite also runs through native mode.
- Prepared source/binary SHA-pinned artifact loader; invalid/incomplete artifact fails closed. Missing optional artifact retains the safety-equivalent portable path and its unchanged deadline. Extension loading disabled immediately after trusted load; scalar marked DIRECTONLY. No schema, data, public API or application-config change. Build only on local/CI hosts; production has no compiler/headers and receives no package install. CI publishes an exact-commit Linux artifact, verified before isolated VM use. No compile/download on application startup.
- **203 backend tests PASS (one Linux-only skipped),51controls PASS**, tiny verified-native benchmark and diff PASS. Require exact-commit CI/artifact, then native-required Linux qualification on generated fixtures. R5/R6 stays STOP until three full passes under existing180s/512MiB/2GiB, collector and production-health limits. No production release/cleanup/index/retention enablement in this milestone.


### November1,2026 — native trial reached apply; total-budget STOP and bounded follow-up

- Candidatea3e1593 exact CI41273629417 PASS; native artifact13070079047 verified (source2b39ba8167896c0e370f2c50f944a1fa23147af8d3f27c3c8e43faae81f43495, binary1a7e9b8b8402e6e9cc1dda269459795dc457e04f0c8fa8b2e8326e3803d4333b). No compiler/header/package install on VM.
- First native-required Linux trial began2026-11-01T04:45:59.129643Z after old-code rollover delay cleared. Generated656041 observations/1904238 streams. Preparation71.8419s; apply reached the170s work deadline and cleanup brought total to186.8597s, beyond180s. **R5/R6 STOP**; no trials2/3. No RetentionBudgetError or production-health failure reported, but incomplete partial lock metrics mean this is not proof all writer durations passed. Fixture collector726saves/726RAM,0errors, maxsave331.7ms/maxheartbeat382.2ms; peakfixture486200645bytes/maxRSS138160KiB.
- Staging/generated files removed only after process/content/hash checks. Fresh05:29:52UTC production remains clean d56b4a7, PIDs17165/849/843 and zero restarts, both feeds live, guard5120, retention/paid AI OFF. DB4405575680/WAL18366992bytes, free51450019840bytes. No production release/index/deletion/config change.
- Follow-up candidate uses the same verified native proof during read-only planning (removing Python parsing per raw row), and groups GENERATED SETUP inserts into20000 rows per commit. Generated cardinality/identities/indexes unchanged; actual retention stays1000-row batches/100ms handoff/500ms hard writer cap, actual collector5s busy timeout unchanged.
- Added partial transaction/phase evidence on overall interruption and a separate fixture-process-group supervisor.170s soft work + cleanup must fit180s total; supervisor starts termination at177s with bounded TERM/KILL/reap. Explicit STOP/retained fixture if reaping fails; never unlink active fixture or report it cleaned.4MiB of the2GiB fixture allowance reserved for supervisor metadata/artifact overhead; memory512MiB/process unchanged. No manual WAL operation: automatic close behavior remains intact.
- **205 backend tests PASS (two Linux-only skipped),51controls PASS**, diff PASS. Linux CI must exercise real process termination/reaping and tiny three-trial supervision before another full native-required trial. Exact CI/artifact required; this is a materially changed candidate, not an unchanged retry. Bridge review due2026-11-02T01:56:47.671426Z remains unchanged; I7/Phase1.75 OPEN.


### November1,2026 — phase attribution narrows native writer overrun; pure prefix candidate

- Follow-up71402ec exact CI41277408489 PASS, artifact13072290252 verified. Generated658953/1914798 profile started05:35:04.737792UTC. Setup fell to50.3823s; supervised total54.2323s. R5/R6 STOP after7fixture commits: one1000-row commit finished at0.502769427s. Accurate partial evidence records7000fixture rows committed; no database rollback is claimed for that completed commit. Production deletion count remains0.
- Failing transaction phases: observations0.133619s, streams0.330733s, combined timestamp0.464398s, coverage0.003466s, selection0.001754s, delete0.008756s, commit0.024297s. Collector14saves/14RAM,0errors, maxsave0.432769s/heartbeat0.483783s; production guard failures0; peakfixture489052781bytes/RSS99272KiB. No trials2/3.
- Cleaned verified stage/fixtures after process/hash checks. Fresh05:38:38UTC production d56b4a7, samePIDs/zero restarts, both feeds live, guard5120, paid AI/retention OFF. DB4410212352/WAL18366992bytes, free51445329920bytes. No production release/index/deletion/config change.
- New candidate keeps a single24-byte connection-local positive cache for exact19-byte calendar prefixes. Complete raw length, fraction digits and UTC suffix are still checked on EVERY row; a cache hit only reuses pure calendar validity, never current row/reference/count/eligibility facts. Source hash pin changes with reviewed C; SQLite frees cache on function replacement/connection close. Full fresh global checks unchanged.
- Strengthened generated fixture: old timestamps span12h within72–60h age; recent timestamps span46h within47–1h age, instead of adjacent microseconds. Original eligible population and exact identity boundaries preserved; assert planned eligible counts equal40030 observations/196509 streams (or scaled tiny profile), preventing a timestamp-range mistake from silently reducing workload. Retention remains1000rows/100ms, hard500ms/180s and resource caps unchanged.
- Local day-scale654328/1896953 O2-prototype native checks: observation median46.1ms, stream124.5ms (total170.6ms); this is not a matched production comparison or Linux qualification. **206backend tests PASS (two Linux-only skipped),51controls PASS**, diff PASS. Final build uses portable O3 without fast-math or architecture-specific flags; full safety/equivalence tests pass. Require exact CI/new source-pinned artifact before another guarded qualification; all later gates remain blocked.


### November1,2026 — indexed global-validity proof replaces repeated full scans

- Prefix candidate829d257 exact CI41278263026 PASS; generated659812/1918076 trial started05:49:56UTC. Three fixture commits3000rows completed (median314.7ms/max485.1ms), then fresh timestamp proof reached500.149ms (observations201.9ms/streams298.1ms), rolled back that transaction and stopped. Preparation63.182s, supervised65.978s; collector8saves/8RAM,0errors, maxsave439.8ms/heartbeat488.7ms; production guard failures0. No trials2/3.
- Cleaned verified fixture/stage.05:53:56UTC production unchanged d56b4a7/PIDs17165/849/843, zero restarts, live feeds,5120 guard, paid AI/retention OFF; DB4418834432/WAL18366992bytes/free51436580864bytes. No production index or deletion.
- New strategy uses TWO ordinary additive partial indexes containing exactly INVALID received_at rows, with a strict SQLite-built-in-only predicate equivalent to raw Python parsing. SQLite maintains membership transactionally for all writers, including old code and foreign connections. Each deletion transaction freshly verifies exact index definitions and probes invalid membership in BOTH raw tables under its writer lock. No cached current counts/references/eligibility, no stale certificate, no scope broadening. Invalid data is preserved and blocks deletion; dropping/replacing a guard fails closed.
- Predicate handles UTF-8 byte length, NULL/BLOB, ASCII digit patterns, Gregorian/leap calendar, valid clock fields, only25/32-byte +00:00 forms. Byte length avoids TEXT-length's embedded-NUL trap. Tests compare16895cases, NOCASE columns, foreign-writer mutations and full existing retention safety cases. Install requires caller-owned explicit transaction and UTF-8; never invoked at startup. No native binary/compiler dependency for indexed runtime.
- Local generated day-scale654328/1896953 benchmark: two guards built4.085s, added8192bytes; full definition+empty-invalid probes median~26.4us observations/~19.2us streams. This is not Linux qualification or a production build-time guarantee. **210backend tests PASS (two Linux-only skipped),51controls PASS**, diff PASS. Qualification adds explicit guard-build timing, indexed-engine requirement and verifies full expected deletions, in addition to unchanged1000row/100ms/500ms/180s and resource/feed limits.
- **Production ordering implication (not yet executed):** guards are a prerequisite to indexed retention and would be explicitly installed during supervised maintenance AFTER R5/R6 and full archive/integrity/recovery gates, BEFORE first cleanup. Source-time feature indexes still follow qualified cleanup/capacity. Keep this scope visible; no silent startup migration or consumed release-exception reuse. All production schema changes remain pending tested operator controls and fresh readiness. R5/R6 STOP until three passing indexed trials; I7/Phase1.75 OPEN.
