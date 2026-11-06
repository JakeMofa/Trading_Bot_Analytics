# BTC Intelligence Rebuild Plan

**Branch:** `codex/phase1-75-retention-enable` (working); `codex/lightsail-deployment` (release target)
**Status:** Active implementation plan  
**Primary focus:** Polymarket US BTC 15-minute markets  
**Rule:** Keep the existing working collector/evaluation pipeline, rebuild the intelligence layer in measured phases.

---

## First priority — automatic A/B handoff

The next Phase 1.75 milestone is to qualify the full handoff under representative
load. Generated Linux rotation and outage checks passed, and the live synthetic
probe verified upload and readback in the private Supabase bucket.

- [ ] At 72 hours or the measured size threshold, whichever comes first, seal A
  and have the sole collector durably acknowledge new writes to B. Repeat in
  reverse with a fresh generation ID when B rotates.
- [ ] Verify the dashboard reports B as active and follows fresh persisted data.
  Deterministic calculations must follow the same active generation and preserve
  the inputs needed across the boundary using sealed A or the persistent core.
  Keep the current market, prediction history, and protected evidence available.
- [ ] While B collects, verify the lifecycle worker finishes A's archive in the
  existing private Supabase bucket and checks authenticated readback against the
  exact sealed contents. Free A only after coverage and protected inputs are
  verified and readers have closed. Retirement can follow immediately.
- [ ] Measure normal peak disk use with sealed A, B's growth during verification,
  core, SQLite sidecars, and archive working files. Budget separately for an
  archive outage and for the retained legacy database and recovery reserve
  during cutover. Verify that a blocked archive preserves A and that B stops
  safely if neither slot can be reused within the storage budget.

Keep paid AI off for this rollout. When enabled later, AI should use the same
application data layer for the current market and inputs, with prior reasoning
and positions in persistent storage.

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

**Session resume:** Read [SESSION_HANDOFF.md](SESSION_HANDOFF.md) for ownership, recorded production STOP and the active generated A/B/core checkpoint; it indexes this roadmap and does not replace it.

**Current phase:** Phase 1.75 — Lightsail migration and initial cloud soak
**Current branch:** `codex/phase1-75-retention-enable`; preserve the existing checkout and unrelated edits.
**Next gate:** Production cutover-control and aggregate-allocation qualification.
Frozen generated candidate f7820026e78528dd1c1f4413dc2a62740b2711a7 /CI42135084876 PASS.
Heartbeat<1s,full225777-input ApplicationStore recovery bootstrap,root repeated
rotation/application paths and selected-recovery forward controls PASS generated.
13 backend privilege skips all covered by dedicated root suites;controls121PASS.
See PR9_FULL_BOOTSTRAP_2026-11-05.md for exact evidence and explicit limitations.
Private exact recovery manifest/capsule durable under ignored data/recovery-evidence;
sanitized release attestations committed. Production legacy still lacks13248inputs;
no repair/transfer/cutover approved. Existing manual route/expiry,post-quiescent
binding,complete legacy verification and independent-service/full raw allocation
remain NOT PROVEN;9deployment-base conflicts. Proposed production ceiling unchanged.
PR9 DRAFT;I7/Phase1.75,freshness/cloud recovery/visibility/capacity/sustained/replay
and knowledge/RAG gaps OPEN. Redis deferred;production collection/retention/paidAI
and all running storage limits unchanged.

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

November 5, 2026 user clarification — defer Redis or another query cache until
after the current A/B integration and regression testing. Use measured query and
dashboard latency to identify a specific benefit before selecting a cache.

- [ ] Evaluate caching only for evidenced bottlenecks. Define bounded memory,
  expiry, market/generation invalidation, restart behavior and database fallback.
  Test rotation and market boundaries so cached results preserve source age,
  provenance and truthful stale/unavailable states.

Deferred query-performance evaluation after the current A/B testing milestone:

1. Measure current-price, feature, history and dashboard latency, including worst
   delays, query completion time and feature/input age during rotation/archive.
2. Inspect expensive queries with EXPLAIN QUERY PLAN. Evaluate bounded time/market
   filters, selected columns, deterministic limits and matching indexes. Verify
   equivalent timestamp ties, exact decimals, provenance and missing/stale states.
3. Evaluate incremental rolling calculations, existing LiveState RAM reads and
   reuse of repeated results. Route historical reads to relevant generations
   while preserving cross-boundary completeness and correctness.
4. Consider Redis or another shared cache for remaining measured repeated reads.
   Compare hit rate, expiry/invalidation correctness and aggregate memory demand
   on the 2 GiB VM before selecting an implementation.

This records future evaluation. Current I7 query/freshness requirements remain
part of Phase 1.75 acceptance and require evidence independently of API latency.

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


### November1,2026 — indexed timestamp proof passes; next hotspot is stream deletion

- Indexed3938fb4 exact CI41279502588 PASS. Trial06:10:04UTC at660998 observations/1922598 streams built guards7.471s; preparation64.282s/supervised108.123s. Fresh global timestamp proof measured83.2MICROseconds. All40030eligible observations deleted across41fixture batches (max57.3ms/median33.1ms);1000streams committed, then next stream transaction stopped503.134ms in exact_delete (coverage112.4ms, selection6.3ms, deletion384.2ms before rollback). Committed fixture rows remain recorded; no production rows deleted.
- Collector285saves/285RAM,0errors,maxsave434.8ms/heartbeat446.6ms; production guard failures0. R5/R6 STOP; no trials2/3. Staging cleaned after process/content/hash checks. Fresh06:16:22UTC production stilld56b4a7/samePIDs/zero restarts, both feeds live (health degraded around rollover),5120 guard, paid AI/retention OFF. DB4431720448/WAL18366992bytes/free51423559680bytes.
- Local set-based exact-delete experiments showed no useful gain; not adopted. Keep exact source/event/RAW received_at deletes. Reuse the full existing archive cursor when its current metadata matches(received_at,source,event_id), otherwise safe fallback; no stream-rowid identity or new index in this change.
- Optimize ONLY validated in-transaction stream manifest counts: raw interior seconds counted by existing indexed range; boundary seconds retain the original canonical tuple comparisons. Disjoint union equals full original bounds, including late/unapproved/other-source rows; no candidate clipping or current count caching. Property checks compare300ranges across mixed25/32widths, midnight/month boundaries, fractions and source/event ties with original SQL. Planning outside the validated transaction retains original count logic.
- Bound the retention connection's MAIN page cache to a16MiB working-set target (preserve larger caller setting), restoring exact original on success/failure. Collector timeout/cache, storage ceiling, persistent configuration, WAL/checkpoint settings unchanged. Still within512MiB process limit. Local1.92m WAL fixture: original range median46.3ms vs split8.1ms; per-row default delete9.0ms, covered-cursor11.2ms, covered-cursor+16MiB cache6.2ms. Local warm results are not qualification.
- **213backend tests PASS (two Linux-only skipped),51controls PASS**, diff/benchmark PASS. Need exact CI and three full indexed Linux trials with unchanged1000row/100ms/500ms/180s, memory/disk/health limits. New guard indexes still NOT installed in production; archive/integrity/recovery/cleanup/freshness/lifecycle/soak gates pending.


### November1,2026 — warm pages outside writer; bound static TEMP preparation

- e088ac2 exact CI41281335177 PASS. Trial06:35:01UTC at662540/1928469 built guards8.063s, prepared63.390s, supervised74.772s. All40030observations completed (max199.7ms/median31.7ms); first stream transaction stopped505.094ms: timestamp0.472ms, coverage36.184ms, selection4.143ms, deletion464.178ms before rollback. No stream rows committed. Collector69saves/69RAM,0errors,maxsave532.6ms/heartbeat583.0ms; production guard failures0. R5/R6 STOP; no later trials.
- Next candidate warms the next bounded approved identity pages using read-only main-PK lookups BEFORE acquiring the writer; every value is discarded. Warming is NOT eligibility/scope proof. Under BEGIN IMMEDIATE, fresh guard definitions/membership, full original manifest counts, references/anchor/eligibility and exact-identity selection/deletion still all run independently. A regression mutates raw data after warming and verifies rollback/no deletion.
- Prepare only immutable approved identities in TEMP-primary-key order, rather than unordered set insertion. Set private connection targets MAIN32MiB +TEMP16MiB (preserve larger caller settings, restore exact originals on success/failure);512MiB process limit and collector5s busy timeout unchanged. No persistent/app/storage/WAL settings changed. Local196509-row static preparation1.896s ->0.937s; not Linux qualification.
- Add per-dataset static-preparation and unlocked-warming timing, retaining measured commit/write phases and truthful partial commits. **214backend tests PASS (two Linux-only skipped),51controls PASS**, diff/benchmark PASS. Require exact CI then three complete indexed Linux trials under unchanged1000/100ms/500ms/180s and resource/health limits. No production index/deletion/release/config change; guard installation/other gates remain pending.


## Qualification deadline diagnostics and observed ID profile — November 1, 2026

Candidate b5ef255 / exact CI41282322948 PASS ran at06:49:59UTC with663455 observations/1931647 streams. The supervisor stopped it at177.151s (exit-15); no complete child report survived. This is STOP, not evidence that writer/collector gates passed. No subsequent trials ran. Exact-hash staging cleanup confirmed no fixture process/files remained. At07:00:41UTC production was still d56b4a7, same service PIDs/zero restarts, retention/paid AI OFF and guard5120; Coinbase live, Polymarket marked stale around rollover. No production schema, rows, code, settings or services changed.

Added atomic provisional STOP reports throughout fixture preparation and unlocked apply checkpoints, retaining stage, committed counts and phase timings even if cleanup is killed. Reporting never runs under the main writer lock and cannot certify an incomplete pass. Limits remain500ms/180s/512MiB/2GiB.

Read-only first100/last100 stream-ID shape samples at06:57:43UTC were all Coinbase ASCII digits of length10. This is a bounded sample, not a full-table assertion. Added explicit synthetic ten-digit-ID profile; default variable-width adversarial profile remains available and its failures remain recorded. Cardinality, full deletion workload, strict string identities, safety checks and deadlines are unchanged. Future passing results apply only to the tested profile; unfamiliar production scopes require qualification rather than numeric coercion.

Prepared a pure raw-row recovery verifier: bounded authenticated-readback bytes supplied by caller, checksum/size/count/boundary validation, exact Decimal JSON comparison and byte-exact original raw-column reconstruction in memory. Four tests pass. No cloud readback or production recovery manifest has been completed; R7 remains pending. Local220 backend tests pass (two Linux-only skipped),51 controls pass. R5/R6 STOP; production guard installation, cleanup, freshness release and24h soak remain blocked pending evidence.


## TEMP pending-table scan repaired — November 1, 2026

498284a exact CI41283166554 PASS. Observed-shape trial at07:03:18UTC used664240 observations/1934508 streams. STOP at173.062s from170s work alarm, not a writer overrun: all40030observations committed, max79.63ms;3000streams committed, max42.39ms and108.99ms total stream writer time. Collector737saves/737RAM,0errors,maxsave58.34ms/heartbeat129.54ms; production guard failures0. Full workload did not complete, so R5/R6 remain STOP. No later trials ran.

Incremental reports exposed the precise unbounded operation: outside-writer TEMP bookkeeping deleted by(source,event_id,received_at), omitting the leading stamp of its WITHOUT ROWID primary key. EXPLAIN confirmed a full pending-table scan per identity. Repaired bookkeeping includes canonical stamp plus all three original exact string identity fields; no current eligibility, coverage, cutoff, protected-reference or deletion check changed. Added a per-batch unlocked-bookkeeping timing and checkpoint.

Generated196509-row local comparison: old10removals178.38ms; new1000removals4.76ms. EXPLAIN changes SCAN to SEARCH USING PRIMARY KEY on all four columns. Regression verifies indexed lookup and distinct007/7/70 identities.221local backend/51controls pass (two Linux-only skipped). Exact CI and three full Linux trials required before release/cleanup. The observed10-digit profile remains distinct from adversarial variable-width qualification; no claim that untested shapes are qualified. Production unchanged; full archive/integrity/R7 gates and I7 freshness/rollover remain open.


## R5/R6 qualified on existing Linux VM — November 1, 2026

Exact candidate e0d311edcceb4be15811c55f6f8650484d107930, CI41283537103 PASS. Three complete generated-only trials passed: 101.998s / maxwriter87.44ms; 126.860s / maxwriter79.36ms; 77.612s / maxwriter97.61ms. Each deleted40030 observations and196509 streams at refreshed representative cardinality (664603–665010 observations/1936125–1938116 streams). Actual deployed save→RAM order,150ms save attempts,50ms heartbeat,500ms writer/180s total/512MiB-process/2GiB-fixture limits retained. All actor errors0, saves=RAM; maxsave108.52ms/heartbeat156.76ms; production guard failures0. No rows were deleted from production.

The complete TEMP primary-key repair removed the hidden outside-writer repeated scan. Generated benchmark old10removals178.38ms vsnew1000removals4.76ms; full Linux stream-bookkeeping now completes rather than timing out. Qualification applies to the explicit observed10-digit Coinbase key profile. Variable-width adversarial results remain historical failures; unfamiliar production scopes require qualification, never coercion. Generated payloads are synthetic, not a replica of production bytes. First actual cleanup remains a separately supervised≤1000-row trial.

R5 performance and R6 collector coexistence PASS for this tested profile. R0–R4 accepted historical evidence preserved. R7 exact raw-row recovery/archive readback and fresh full production SQLite verification remain PENDING; R8–R17/I7/Phase1.75 remain OPEN. Old board statements requiring snapshots or claiming no optimization authorization are superseded by the user's subsequent implementation plan; no copies/snapshots were made.

Exact-hash generated staging cleanup verified.07:18:46UTC production remained d56b4a7/same PIDs/zero restarts, bothfeeds live, retention/paidAI OFF,guard5120, DB4469121024/WAL18366992 bytes. This is a recorded sample, not an ongoing-health guarantee. Bridge review due2026-11-02T01:56:47.671426Z remains unchanged.

Prepared the next controls: TEMP exact-full-row recovery guard blocks mutation/unapproved deletes transactionally; its indexes avoid repeating the pending-scan mistake. Prepared explicit operator-only read-only quick/FK audit with30min work+3min recovery reserve, independent bounded/reaped SQLite child, partial-stop recovery, restoration of every stopped writer even after a restart failure, unchanged configuration and measured raw receive gaps. Default is plan-only; no audit/service stop/index installation has run.222local backend/57controls PASS (two Linux-only backend skips); require exact new helper CI, hash-pinned export and safe preflight before supervised production maintenance. No consumed I7 exception reuse.


### Integrity-child interruption containment

6201867 exact CI41284484947 PASS (222 backend plus57controls on Linux). Before production use, the audit helper now owns its read-only child process group directly: timeout or parent interruption terminates/kills/reaps it before service recovery. Added real Linux kill/reap and parent-interruption regressions. Local59controls pass with two Linux-only skips; backend unchanged. Requires new exact helper CI. No production maintenance has run; no live process or service was signalled by these generated/unit tests.


### Bounded private-archive recovery preparation

Added a default-plan-only operator that selects at most1000 raw rows through original full manifest ranges, reads applicable private objects using the existing authenticated download client, verifies checksum/compressed size/count/boundaries, preserves original raw columns and demonstrates in-memory reconstruction. It freezes the48h cutoff and exact approved identities; it never deletes, uploads, enables flags or creates indexes. Fresh eligibility/protected-reference checks remain required in the deletion transaction. Private proof publication is immutable and0600; diagnostic output includes only stage/type/count/hash, never credentials or raw payload.227local backend tests PASS (two Linux-only skips); requires exact CI before any production readback. Production R7 proof remains PENDING.

Supabase docs/changelog verified: private download remains supported; October12 TLS cipher notice does not change the download contract. Official reference: https://supabase.com/docs/reference/python/storage-from-download . No Supabase schema/access-policy change.

Production integrity helper7e5e7d2 CI41284629743 PASS; read-only preflight PASS, then supervised full quick/FK audit started2026-11-01T07:26:19.086790Z. Writer services intentionally paused; recovery reserve3min within30min work budget. This entry records IN_PROGRESS, not a passing audit or currently-live collection claim. No copies/snapshots/deletion/manual WAL operations.


### Full SQLite checks passed; verifier STOP and independent recovery

Production audit7e5e7d2/CI41284629743: quick_check PASS782.745s, foreign_key_check PASS78.092s. The attempt remains STOP: recovery verifier incorrectly indexed MainPID on tradebot-soak.timer, which has no process PID. This was a helper defect, not an observed failed service restart. Do not relabel the original attempt as successful. Corrected timer checks use ActiveState/UnitFileState; regression exercises actual recovery logic with a PID-less timer. Unreaped-child failures now retain PID/manual-recovery status.61local controls PASS (two Linux-only skips); backend227unchanged.

Independent read-only follow-up confirmed all three services active, zero automatic restarts, flagsOFF, guard5120, original appd56b4a7. Twelve5s feed/API samples passed, max39.34ms, both feed timestamps advancing. Monitoring timer active; envmtime2026-11-01T01:56:47.667263Z matches bridge application. API started07:40:41UTC. Persisted Coinbase received gap862.791950s:07:26:19.440384→07:40:42.232334UTC. Observation gap unavailable within bounded256recent rows; no broader scan/backfill claim. No additional restart or repeated integrity scan was used for confirmation.

Full SQLite verification is now evidenced separately from the failed overall maintenance report; independent recovery is PASS. R7 private archive/exact-row proof remains PENDING, no production deletion/guard indexes/application deployment. Evidence: production-integrity-7e5e7d2.jsonl, post-integrity-keyerror-runtime.json, independent-integrity-recovery.jsonl in lifecycle-implementation-20261031. Continue with exact-CI read-only archive recovery preparation, preserving all remaining gates and the existing bridge deadline.


## R7 first bounded recovery scope prepared; isolated retention release qualified

007a439 / CI41285656414 PASS performed authenticated private readback for three applicable observation archives. All size/SHA/count/identity-boundary checks passed;1000 proposed observation rows reconstructed in memory with exact raw columns. Fixed48h cutoff2026-10-30T07:50:12.491770Z. Private0600 proof /opt/tradebot/data/retention-recovery/observations-20261101T075011Z-007a439.json, SHA25645f1a977bc74f10a319970b00c3986670bb634310f5a0fecad27ce45a6a76c91. This is exact raw-delete recovery, not a database snapshot/full disaster-recovery backup. No rows deleted; proof status PREPARED_NOT_APPLIED. R7 PASS applies ONLY to this exact scope; later batches require their own verified proofs and fresh current checks.

Production reference metadata at07:54:48UTC: prediction_context_links rowid upper20, unindexed lookup. No large reference-table bottleneck evidenced; no reference-query/index change made. R5/R6 accepted three-trial profile remains unchanged.

Isolated retention/health candidate c1249503ffe7d4e5cb31e4120c9375d1488ce024 pushed to the existing remote deployment branch, CI41287429837 PASS;214local tests (two Linux-only skips), exact CI tests passed. No app deployment. API health correction plus qualified retention/proof modules only; existing collector/streaming/feature source and configuration unchanged. Scoped regression asserts the exact legacy seconds-format zero-microsecond writer output; deferred writer normalization was excluded rather than importing future feature code. Both legal raw formats remain strictly checked. Working branch/checkout unchanged; stale local deployment branch eaca36c preserved, remote advanced normally fromd56b4a7.

Prepared explicit timestamp-guard installer: requires full SQLite verification evidence plus independent recovered collection, creates only the two reviewed guard indexes in one transaction during supervised maintenance. No price indexes/startup DDL/deletion/config change. Enforces5120MiB physical cap with64MiB commit reserve,512MiB process limit,30min work+3min recovery. Invalid raw timestamps/deadline/storage/schema errors stop and roll back uncommitted DDL; committed late indexes are reported and never blindly dropped. Current schema is recorded after every completed child.68local controls PASS (two Linux-only skips); require exact new CI before use. Receipt-gap baseline now captured after all writers stop, avoiding saves that can arrive between preflight and shutdown.

Next: install timestamp guards only after exact helper CI/fresh preflight, restore/verify collection, then use the exact-CI candidate and protected recovery scope for the first≤1000-row cleanup. Full integrity passed separately from the original maintenance attempt's verifier STOP; independent recovery PASS. No guard index, cleanup, automatic retention, paid AI, freshness release or Phase2 has occurred. Bridge deadline unchanged.


### Timestamp-install attempt STOP before DDL; bounded owner-drain correction

2a1e5b8 CI41287687023 PASS attempted maintenance08:13:33UTC. STOP before its build operation; guard index catalog confirmed empty afterward. Recovery PASS; all three writer services active/zero automatic restarts. No rows deleted. The remaining-descriptor check failed before final paused-baseline capture; its original error omitted PID/reason. Exact past owner is UNKNOWN, not asserted to be monitoring. Current owner inventory shows only expected API/ensemble connections; read-only repeated preflight has no own leaked SQLite descriptors, before or after normal garbage collection.

Corrected control waits for zero descriptors within the SAME10s drain deadline, captures phase/PID/descriptor/access mode on failure, exempts nobody and never signals unknown owners. This addresses short close races without changing the gate. If no final paused baseline was captured, future recovery reports no misleading preflight-derived gap. Original attempt's Coinbase0.5105s/observation81.463531s figures used the preflight baseline and are not certified precise maintenance gaps. Collection-interruption upper bound100.710535s; no second full integrity scan or data operation occurred.

70local controls PASS (two Linux-only skips), backend227unchanged. Exact new CI required before a revised maintenance attempt. R5/R6 and exact R7 scope preserved; timestamp guards/first cleanup/continuous retention/I7 freshness remain pending. No budget, guard ceiling, flags, configuration, infrastructure or branch change.


## Timestamp guards installed; first exact cleanup operator tested

Revised4d6747a / exact CI41289317190 maintenance PASS. Both guard indexes committed in116.327s, both current invalid sets empty. DB+WAL4503465984→4503478272 bytes (+12288); no raw deletion. Writer services restored and advancing feeds verified; automatic retention/paidAI OFF. Measured final-paused-to-first-recovered raw receipt gaps: observations222.349703s, streams222.527555s; upper interruption237.550328s. Original2a attempt remains STOP with unknown past owner. This revised attempt drained immediately (6.16ms), so no claim that a particular prior owner/race was identified.

First-scope operator adds exact full-row recovery protection, runtime denial of structured writes/other-dataset deletes/attachments, discarded full-row page warming outside the writer, and in-memory DELETE identity callbacks. Callbacks do not inflate total_changes and are reconciled against actual committed counts; rollback callbacks are never reported as committed, and late commit overruns remain STOP with committed rows reported. All original current coverage/reference/anchor/global timestamp checks stay inside the500ms core transaction; no mutable safety cache. Post-checks cover every child table referencing the affected raw table; full pre-delete quick/FK evidence remains preserved.

234local backend tests PASS (two Linux-only skips), including late-reference, mutation-after-warm, structured-delete denial and committed-overrun cases;70controls previously PASS. Production first cleanup NOT RUN. Require exact helper/release CI, protect the private R7 artifact hash, then execute only this≤1000-row scope and verify collector/feed/API behavior before any later bounded catch-up. No automatic retention, price indexes, freshness application release, permanent cap promotion or Phase2.

## First authorized production cleanup trial STOP; dense-range coverage fix

Dedicated execution checkpoint November1,2026: c7061f70b20ffe0607f3bf2f07d7a7926b1f810d is pushed; exact CI41310818560 PASS. Isolated deployment candidate7a43fcd0ad58e9d58ee81e6d584a8f7e75fac899 advances only four trial files fromc124950; exact CI41318630094 PASS,221local backend tests (two Linux-only skipped). Candidate code staged separately, application remainsd56b4a7; no app deployment or service restart. Unrelated596-line roadmap edits and AGENTS.md preserved.

User explicitly approved the single≤1000-row recovery-proved observation cleanup after automatic approval review initially rejected deletion under read-only instructions. Initial rejected invocation did not run. Executed trial14:58:47UTC STOP at manifest_coverage:sqlite_progress, writer523.097ms; timestamp proof1.131ms, coverage521.554ms. **Committed0 rows, attempted delete callbacks0.** Immutable private report /opt/tradebot/data/retention-recovery/first-trial-7a43fcd.json SHA2565786c59ede7ae6d8c80969dcf66b28c22d5dd776fd212d1ccbcf0e26a062383b. Original proof hash unchanged; do not overwrite trial evidence or assume any successful cleanup. Allocation page_count1152995→1152997, freelist0→0; no capacity reclaimed.

Preflight61.050s/13samples PASS; post-STOP recovery60.785s/13samples PASS, both feeds advancing, every2s HTTP probe succeeded. Actual flagsOFF, guard5120, three services active/zero automatic restarts, originald56b4a7 preserved. No integrity scan, copies/backups/snapshots, manual WAL, new index or configuration change. Evidence first-trial-{preflight,stop,recovery,range-explain}-7a43fcd.jsonl in existing lifecycle evidence root.

Read-only EXPLAIN identifies payload-table rowid range counts for original ranges195001..198243/count3243,198244..198272/count29,198273..203272/count5000. Each count equals integer range capacity. Revised local coverage proof freshly verifies under the SAME writer transaction that observations.id is the sole INTEGER PRIMARY KEY rowid alias (ordinary table, no PK backing index). Its integer capacity is a conservative upper bound on current rows, including late/unapproved rows; if that bound≤archive count, overcoverage is impossible. Sparse bounds/unknown schemas/stream ranges retain fresh exact counts. No eligibility, full-row recovery, reference, identity, timestamp or writer limit weakened. No current-row count cached, no new schema/index.

239local backend tests PASS(two Linux-only skipped);70controls PASS(two Linux-only skipped), diff PASS. Regression covers DESC/nonalias/composite/WITHOUT ROWID schemas, schema replacement, sparse fallback, late insertion and unchanged stream counts; existing safety suites run native and guard variants. Revised core NOT production-qualified or executed. Next require exact revised working/release CI and reviewed updated operator trial with fresh preflight; do not repeat7a43fcd unchanged. First cleanup, reusable capacity, source-time indexes/freshness rollout, lifecycle-only enablement and24h soak remain outstanding. Bridge review deadline2026-11-02T01:56:47.671426Z unchanged; I7/Phase1.75 OPEN; Phase2 deferred.

## Revised dense-capacity Linux qualification STOP at commit latency

Working cced225 exact CI41319190397 PASS. Isolated8bb9bf9e7c6f66d71d8410c6ea9e33978886a806 exact CI41319318143 PASS;226local backend tests(two Linux-only skipped). Preserved scoped legacy raw-writer regression rather than importing deferred collector/streaming changes. Refreshed indexed rowid upper bounds619941observations/1833440streams; generated qualification691935/2026784, actual deployed streaming SHA95a49c2ac04b6dbb04223e0f363df0a6132bd7b0cc10fda7145a2055bd1efa12.

Trial1 PASS118.225s, maxwriter76.031ms,282collector saves/RAM updates,0errors,maxsave55.440ms/heartbeat97.344ms. Trial2 STOP87.252s at COMMIT692.804ms(writer): timestamp0.068ms,coverage0.078ms,selection1.231ms,delete11.490ms,commit679.865ms. Exactly12000GENERATED observation rows committed before STOP; no generated streams deleted. Collector25saves/RAM,0errors,maxsave53.989ms/heartbeat81.471ms; production-health guard failures0. Trial3 NOT RUN. **No production retry/deletion.** This candidate does not have three passing revised qualification trials; historicale0d R5/R6 accepted profile remains separate evidence, not authorization to ignore this new STOP.

Coverage optimization addresses the original production bottleneck; commit latency is now measured blocker. Periodic~400ms commits were observed before the693ms overrun; cause is not yet certified. No claim that an automatic checkpoint, disk fault or collector contention caused it. Preserve500ms hardwriter,180s overall,100ms handoff,512MiB/2GiB generated limits. No WAL/checkpoint/synchronous setting changes, manual WAL actions, infrastructure or service changes.

Prepared GENERATED-ONLY batch-size diagnostic accepting250/500/1000(default1000), forwarded through the bounded child and recorded in reports. Next diagnostic uses500-row ceiling to reduce per-transaction writes; full workload stays unchanged. Added read-only fixture SQLite settings and bounded16-sample WAL byte telemetry outside writer transactions; no checkpoint or setting mutations. Six harness tests PASS(two Linux-only skipped), compile/diff PASS; exact CI must exercise Linux child forwarding and report fields before another generated trial. Production operator still1000 and unchanged; do not execute it under failed qualification. Evidence dense-capacity-{qualification,scale}-8bb9bf9 in existing lifecycle evidence root. First production cleanup/capacity/freshness/lifecycle/soak and I7/Phase1.75 remain OPEN;5120 review deadline unchanged.

##500-row diagnostic STOP; total production deleted rows remain0

6886672 working exact CI41320056211 PASS; isolated a092bfb51868e8fcfe2abe65b5eeb20ddbf203de exact CI41320086640 PASS, including Linux fixture-supervisor and500-row child forwarding. No application deployment.

First500-row generated diagnostic STOP89.101s during fixture preparation at15:15:36UTC: production Polymarket guard observed stale/last_data15:15:15.483185,age21.008s; Coinbase live/age0.038s, collector running. Retention had not begun, collector actor not started. Trials2/3 not run; no claim this was a500-row performance failure or that fixture load caused source staleness. Separate I7/rollover defect remains OPEN. Evidence smaller-batch-boundary-stop-a092bfb.jsonl.

A new scheduling precondition required90..300s into a15-minute interval,13successful5s/two-second-timeout feed recovery probes, and≥570s before the next boundary. This limits performance evidence to a stable between-boundaries window; it does NOT weaken ongoing health guards or certify rollover. Preflight PASS with691.692s remaining. Recovered-window500-row trial1 STOP83.122s: writer537.332ms,commit525.525ms,delete10.404ms,coverage0.105ms,timestamp0.089ms. Exactly13500GENERATED observation rows committed across27batches before STOP; no generated stream deletion. Collector47saves/RAM,0errors,maxsave43.992ms/heartbeat78.615ms; production-health guard failures0. Trials2/3 not run. Evidence smaller-batch-commit-stop-a092bfb.jsonl.

Read-only fixture settings:journal_mode=wal,synchronous=2(FULL),wal_autocheckpoint=1000,page_size4096. Bounded WAL allocation samples stayed7107032bytes; these sizes do NOT establish that an automatic checkpoint caused the overrun. Neither500nor1000-row revised candidate has three complete passing trials. Do not retry production unchanged, weaken500ms/180s/100ms limits, disable durability, issue manual checkpoints or change journal settings under existing authorization. No new production cleanup, indexes, services, flags or configuration changed; total production deletions remain0.

Next proposed investigation is a GENERATED-ONLY automatic-checkpoint threshold experiment(256pages vs1000), preserving FULL durability and existing safety/resource/health gates. It requires explicit user permission under the handoff's no-manual-WAL restriction; not executed or approved for production. First actual cleanup, reusable capacity, source-time indexes/freshness release, lifecycle-only retention and24h soak remain pending. Full24h soak cannot finish before November1,19:56CST bridge review; no silent extension/permanent promotion. I7/Phase1.75 remain OPEN and Phase2 deferred.

Final recovered runtime60.535s/13samples PASS; actual flagsOFF, guard5120, applicationd56b4a7, all3services active/zero automatic restarts, both feeds advancing, no2sHTTP timeout. Evidence smaller-batch-final-recovery-a092bfb.jsonl.

## Authorized generated-only automatic checkpoint experiment prepared

User explicitly authorized the256-page automatic-checkpoint experiment on generated fixtures only, preserving FULL durability,500ms writer/180s trial limits and unchanged production. This does not authorize production journal changes or manual checkpoints.

Harness option --fixture-autocheckpoint-pages accepts only0(default,unchanged) or256. It applies AFTER generated population/guard build and BEFORE retention planning, only on the private newly generated fixture's exact main connection outside transactions; rejects production/non-generated paths, mismatched/in-memory connections and non-FULL durability. It records before/after SQLite settings and forwards the option through bounded child supervision. No PRAGMA wal_checkpoint, production connection, change to collector/runtime retention or service configuration. Existing500-row trial workload and100ms handoff retained.

Seven local harness tests PASS(two Linux-only skipped), compile/diff PASS. Linux CI must exercise actual tiny indexed256-page trial and report FULL durability/original1000-page setting before a new full generated run. Full-scale experiment not yet executed; prior1000/500-row commit STOP evidence preserved. Runtime remainsd56b4a7, retention/paidAI OFF; total production deletions0. I7/Phase1.75 OPEN; bridge review deadline unchanged.

##256-page generated-only experiment STOP; no production journal change

Explicit user permission covered the256-page automatic threshold on generated fixtures only, keeping FULL durability and existing hard limits. Working4163d5d82e39e7ace7c29ee1d9ece611a1750b3b exact CI41321191617 PASS; isolated84513b06a41db40dbf5a36fcc2018dce47e8c03a exact CI41321221835 PASS, including Linux tiny256-page indexed trial and guard/refusal tests. No application deployment or production setting change.

Fresh stable-window preflight13samples PASS,737.377s before next boundary. Trial1 began2026-11-01T15:32:43.051616Z, generated691935observations/2026784streams with500-row batches and100ms handoff. Fixture retention connection before:WAL/FULL(2)/autocheckpoint1000/page4096; experiment:WAL/FULL(2)/autocheckpoint256/page4096. Actual deployed collector save code remained hash-pinned and unchanged; no manual checkpoint, synchronous weakening, source-cadence change or production database write.

**STOP:** writer502.686ms against500ms; commit495.384ms,delete6.403ms,coverage0.074ms,timestamp0.066ms,selection0.641ms. Late completed commit correctly recorded500rows; cumulative35000GENERATED observation rows committed across70batches. No generated stream deletion. Total108.288s,preparation75.064s,maxRSS101732KiB,peakfixture540945669bytes. Collector217saves/RAM,0errors,maxsave65.974ms/heartbeat95.251ms; production-health guard failures0. Trials2/3 NOT RUN. A near-limit result is not rounded into PASS; no claim this establishes checkpointing as the cause or that256 is production-qualified.

Evidence checkpoint256-commit-stop-84513b0.jsonl in the existing lifecycle evidence root. The bounded supervisor reaped its child and cleaned its generated trial directory normally; parent-directory emptiness is verified separately before removal. Production cleanup total remains0 from the original7a43fcd rollback. Scoped R7 private proof unchanged; current automatic retention/paidAI OFF, appd56b4a7, temporary5120 cap unchanged. I7/freshness/rollover, first successful cleanup, reusable capacity, price indexes, lifecycle-only enablement and24h soak remain OPEN. Bridge review2026-11-02T01:56:47.671426Z unchanged; no silent extension, permanent cap promotion or Phase2.

The authorized256-page experiment is complete and FAILED its performance gate. Preserve this result; do not run unchanged follow-up trials or promote the setting to production. Further work needs an evidenced change in the operation causing the overrun, under the same durability and500ms/180s gates.

Post-experiment runtime verification60.447s/13samples PASS: actual service flagsOFF/paid credentials absent, guard5120, applicationd56b4a7, all3services active with0automatic restarts, both feed timestamps advancing and every2sHTTP probe successful. Evidence checkpoint256-recovery-84513b0.jsonl. Generated parent verified empty and removed; no retained generated fixture.

## Commit versus writer-lock measurement: bounded generated diagnostic complete

Continued from084ca92 with one reduced generated-only strace6.8 diagnostic,12000
observations/12000streams,500-row ceiling, original automatic threshold1000 and
FULL durability. No repeat batch-size/threshold experiment or production change.
Exact fixture build: Python3.12.3, SQLite3.45.1 Ubuntu3.45.1-1ubuntu2.8, modified
sourceID endingccalt1; official matching source archives/checksums and patch series
inspected. Existing timer begins after BEGIN IMMEDIATE returns and ends after
commit returns: includes post-release work, excludes acquisition/wait, and is not
an actual writer-lock metric or strict bound on its entire lifetime.

Trace resolves successful shm byte120 WRITE locks independently of CKPT121,
reader/DMS and database-file locks.48 retention transactions paired with syscall
entry/exit bounds and Python commit markers. Slowest commit220.379ms: release
83.185ms after entry,137.195ms remaining; total WRITE occupancy99.394..99.423ms.
Lock-held WAL sync58.225ms; post-release204DB writes and116.707msDB sync. Collector
acquired the SAME byte120 lock before main commit returned. Delay is evidenced
on both sides in this sample. Tracing overhead is unquantified; reduced scale and
absence of the historical slow commit's trace prevent attributing its495.384ms.
Prior502.686ms STOP remains FAILED; no500ms policy change or production retry.

Reduced harness11.798s;65collector saves/RAM,0errors,maxsave137.707ms/heartbeat
165.329ms; production-guard failures0. Generated work reaped/empty. Post-check
15:57:34UTC collector running/bothfeeds live; no rollover/soak claim. Private raw
trace/analysis/source/checksum evidence saved under lifecycle evidence directory
sqlite-writer-lock-084ca92. Detailed timer/build/source/syscall evidence and limits:
[SQLITE_WRITER_LOCK_DIAGNOSTIC_2026-11-01.md](SQLITE_WRITER_LOCK_DIAGNOSTIC_2026-11-01.md).

Smallest justified next change proposed: companion lock-occupancy/acquisition-wait,
commit-call/current-total and collector-interference metrics, preserving existing
500ms acceptance. No runtime refactor or additional unchanged qualification trial.
Historical overrun attribution remains INCONCLUSIVE; production deleted0,
retention/paidAI OFF, no journal/config/service changes. I7/Phase1.75 OPEN;
freshness/rollover,cleanup/capacity,lifecycle/24h soak pending; Phase2 deferred.
Temporary5120 review2026-11-02T01:56:47.671426Z unchanged; no extension.

## Separate retention diagnostics implemented; one representative investigation pending

Explicit transaction_total_seconds and commit_call_seconds now accompany legacy
write_lock_seconds fields; legacy500ms total gate unchanged. Actual occupancy is
None/unmeasured unless validated offline syscall evidence supplies lock bounds.
Generated collector save/heartbeat/errors are reported independently. Opt-in
private-generated-only marker instrumentation and offline strace parser reject
unrelated lock ranges and incomplete syscall exits; neither is installed in normal
production.91local retention tests PASS(two Linux-only skips); two new parser/privacy
controls PASS. Prior48-pair trace revalidated. One representative generated-only
investigation pending; no matrix/settings experiment. Production unchanged,
retention/paidAI OFF, deleted0; I7/Phase1.75 OPEN, Phase2 deferred, cap deadline
2026-11-02T01:56:47.671426Z unchanged.

## Separate diagnostics complete; representative investigation prerequisite STOP — decision C

Implementationddda7d5 exact CI41325279117 PASS;93local tests PASS(two Linux-only
skips). Transaction/commit durations and collector-interference reports separated;
actual lock occupancy explicitly unmeasured in runtime, available only through
validated opt-in offline generated syscall instrumentation. Legacy500ms gate intact.

One800000observation/2350000stream representative profile prepared, default1000-page
threshold/FULL/500-row ceiling. Initial feed preflight failed; one120s bounded
recovery window could not obtain13consecutive healthy samples. NO generated fixture,
actor,trace or retention transaction started. Independent work-directory checks empty,
trace/report absent.16:19:42UTC single follow-up had bothfeeds live; it does not
satisfy the failed sustained baseline. No further attempt. Prior502.686ms STOP
unchanged; historical dominant delay remains unproven.

DecisionC: stop qualification and review explicit separation of passive-checkpoint
scheduling from deletion commits, retaining FULL durability and existing collector,
storage,workload/memory gates. Proposal only; requires review of no-manual-WAL
boundary, no dependency/VFS/single-writer/buffering redesign bundled. Details and
missing evidence in [RETENTION_DIAGNOSTICS_DECISION_2026-11-01.md](RETENTION_DIAGNOSTICS_DECISION_2026-11-01.md).
Production unchanged,deleted0,retention/paidAI OFF. I7/Phase1.75 OPEN; no Phase2.
Temporary5120 review2026-11-02T01:56:47.671426Z unchanged, no extension.

## Production preflight diagnosis: delayed Polymarket rollover, not a global feed outage

Bounded read-only logs/rowid samples/source timestamps identify deployedrest_loop's
await of185.921sfeature_cycle across16:15UTC, followed by30spause, delaying REST
discovery/RAM rollover. New2037956 first seen16:18:26.153924, firstbook16:18:26.836114
(206.836s late). Ended2038542 repeated exactsource timestamp16:15:15.440365678Z on
six~31s receipts through16:18:22.707881. Coinbase2624events16:13..16:21, maxgap4.909s;
API initialpreflight/all25recoveryprobesHTTP200. No generated load or retention ran.

Polymarket current-market collection genuinely delayed; no evidence of venue-wide
outage. Historical failed-body enum unavailable, but receipt/source/identity
reconstruction identifies the affected path. False-healthy reporting ALSO evidenced:
16:15:30telemetryhealthok whilemarketended; replay saves refreshreceipt-basedlive.
This was not shown to be a false rejection of healthycurrent-marketdata.

Smallest proposed correction: reuse a6958f6's tested independent REST/serialfeature
scheduling and publication guards; do not await featurecompletion beforediscovery.
It fixes rolloverdependency, not slowfeature freshness. Existing ea6e6de stopped-
collectorhealthfix is insufficient here; add expired/mismatched/source-stale health
regressions before claimingtruthfuloverallhealth. No runtimechange or indexbuild
underthisinstruction. Checkpointownership redesign has no bearing on this cause.

Detailed timestamps,evidencebounds,limits and proposedreuse:
[FEED_PREFLIGHT_DIAGNOSIS_2026-11-01.md](FEED_PREFLIGHT_DIAGNOSIS_2026-11-01.md).
EvidenceconsistencychecksPASS; productionunchanged,cleanup0,retention/paidAIOFF.
Retentioncommitissue/500msgate remainseparateandunchanged. I7/Phase1.75OPEN;
Phase2deferred; capreview2026-11-02T01:56:47.671426Z unchanged.

## Independent rollover and truthful health implemented; release controls BLOCK production

Working implementation reuses independent REST/one serial worker/publication guards
froma6958f6; no price-query/version/index/retention changes in this milestone.
New pure aggregate-health reasons check expired/missing market, quote identity,
source timestamp validity/30s freshness/5s future tolerance, features and collector.
Replayed old events with fresh receipts cannot restoreok. Startup feature hydration
uses publication guards; historical data unchanged. API routes/HTTP/fields kept,
add diagnostic_reasons. Status/reasons evaluated together after asynccloudread.

Simulated186s blocked feature spans boundary: discovery and websocket subscription
advance before completion, one worker, oldresultnotpublished. Existing serialworker,
connectionownership,cancellation and publicationtests reused; source/identity/HTTP200
recoveryregressions added.246backend PASS(two Linux-only skips);70controls PASS(two
Linux-only skips). Unixsocket sandbox restriction resolved by permitted test run.
Require exactworking/candidate CI and isolated release-tree suites before release.

Production blocked before any attempt: normal inline livequick/FK checks have no
child deadline inside900sdeployworkflow; historical fullaudit860.837s leaves39.163s,
not180srecovery+deployment. Consumed fixeda7c0989->d56b4a7 exception cannot be reused.
Smallest controlreview: separately budgeted/supervised completeverification phase,
exact release/runtime/database/schema binding and approved freshness/recovery rules;
no implicit skippedchecks or budgetextension. ApplicationrestartAPIonly/code-only
rollback. No newverification scan/helperinstall/dispatch/restart executed.

Details/scope/acceptance: [ROLLOVER_HEALTH_RELEASE_2026-11-01.md](ROLLOVER_HEALTH_RELEASE_2026-11-01.md).
20minute/3cycle/boundary acceptance NOTRUN, milestoneNOTCOMPLETE. Retention remains
blocked independently; no newtrial,cleanup or500msgatechange. Productiondeleted0,
retention/paidAIOFF,guardunchanged. I7/Phase1.75OPEN,Phase2deferred;
capreview2026-11-02T01:56:47.671426Z unchanged.

### Exact CI caught boundary-test synchronization race; corrected before promotion

74bfbe6 CI41328799829 FAILED only new mocked boundarysubscription assertion:100ms
polling did not guarantee REST-thread dispatch on Linux. Replaced polling with
explicit old/new subscription events and bounded waits while solefeatureworker
remainsblocked. No application behavior or production action changed. Require
newexactCI; do not count failedrevision asPASS. First isolatedrelease export169
backend/6controls PASS locally; it is unpromoted and superseded by corrected tests.

### Rollover/health exact-CI candidate qualified; deployment not attempted

Working444ea4bcf4783c79f6daf3f9f1cfc01a6b377a4f exactCI41328969110 PASS.
Initial74bfbe6 CI41328799829 failed a boundary-test polling race; event rendezvous
corrected it without changing application behavior.246backend/70controls localPASS
(two Linux-only skips each); exactLinuxCI exercises thoseplatformcases.

Scopedcandidatefd904582dd51df09c063db954bfa522e7455e613 exactCI41329044967 PASS;
isolated169backend/6controls PASS. Existingdeploymentbranch advanced84513b0->fd90458
normally, previouscandidatehistory preserved; localdeploymentrefeaca36c/checkout
unchanged. Onlyapi.py,streaming.py,newlive_health.py applicationdiff vsdeployed
 d56b4a7; pricequeries,featureversion,indexes,collectorrawformat,retention,dependencies,
units/config/productionhelper excluded. Historicalfeatureevidence unchanged.

ReleaseoutcomeNOTATTEMPTED/RELEASE_CONTROL_BLOCKED. Fullaudit860.837s historical
against900sworkflowcannotleave180srecoveryplusdeploy; inlinechecks unbounded.
Consumedexceptionnotreused. Reviewproposal: separate bounded fullquick/FK child
phase (proposed30minwork+180srecovery), collection/storage guards, readtransaction,
exactrelease/runtime/DB/schema binding and proposed300sfreshness; explicitapproved
one-useevidence consumption bynormalcode-deployjob. No implicitbudgetextension,
newscans/helperinstall/dispatch/restarts. APIonlyrestart/codeonlyrollback whenapproved.

Production20min/3cycle/boundary validationNOTRUN, allcandidateproductiontimings
NOTMEASURED; milestoneOPEN. See [ROLLOVER_HEALTH_RELEASE_2026-11-01.md](ROLLOVER_HEALTH_RELEASE_2026-11-01.md).
Do not resume retention qualification before thisacceptance passes. Retention/paidAI
OFF,deleted0,guardunchanged; no backup/manualWAL/index/Phase2. I7/Phase1.75OPEN;
capreview2026-11-02T01:56:47.671426Z unchanged.

## Bounded complete-verification release controls prepared; production review pending

Prepared a separate guarded verify phase and deploy-verified phase in existing
manualActions workflow/branch/private-runner/forcedhelper/flock. No normal integrity
checks removed: legacy deploy still runs fullquick/FK. Newroute requires root0600
one-use explicitapproval document, exactruntime/release/helper/verifier/smoke/CI
binding, pinnedfd90458applicationblobs. No general integrity bypass or consumedI7
exception. Completequick/FK run in one readtransaction/512MiB Linuxchild, with
boundedtermination/reaping. Source/API/currentmarket/persistence/storage gates
abort unsafeverification; failure cannot publish usableevidence or checkoutcode.

Proposed(notapproved) policy:1800sverificationwork+10sreap/180srecovery under35min
verifyjob;300sone-useproofTTL andoriginalreviewexpiry<=3600s;600scodework+180srecovery
underexisting15mindeployjob. Bind DBpath/device/inode/schema/catalog, serviceidentity
andprotectedconfig. Concurrent DML after verifiedsnapshot is explicitly part of
reviewedreusepolicy, not immutable-content proof. Beforecheckoutrecheckallbindings,
consumeonce; APIonlyrestart, bounded code-onlyrollback evenon interruption/timeout.
Alloriginalsmokeroutes/secretchecks retained; reviewedmode permits only explicit
featuremissing/stale reasons while currentmarket/sourcechecks remain mandatory.

246backendPASS(two Linux-only skips);88controlsPASS(three Linux-only skips),18new
controls. Compile/shell/diffPASS. Isolated controlcandidate/exactCI still required.
Read-only sudo metadata confirms existing forcedhelper wildcardargument supports
newvalidated modes; no permission/key/SSH/config/infrastructure changes. No heavy
prodscan,reviewauthorizationfile,helperinstall,dispatch,apprestart or deletion.

Concrete procedure/policy/template/stopconditions:
[RELEASE_VERIFICATION_REVIEW.md](../../deploy/lightsail/RELEASE_VERIFICATION_REVIEW.md).
Production procedure/budgets/evidence reuse remain explicitly UNAPPROVED. Rollover
acceptance20min/3cycles/boundary NOTRUN; retention/paidAIOFF,productiondataintact,
ceilingunchanged,phase1.75OPEN. No retentionexperiment,manualWAL,index orPhase2;
capreview2026-11-02T01:56:47.671426Z unchanged.

### Final control review: distinguish startup transport readiness from source health

Initialcontroldd9cd6d CI41331354926 PASS; isolatedabf288b CI41331505238 andpush-only
DeployTradebot validation41331505153 PASS. No production phases ran. Final review
added boundedAPIstartup readiness<=180s inside600scodebudget, recordingtransport
failures separately. Only transport startup is polled; onceAPIresponds, collection
health is validated once, with source/identityfailure STOP, not a recoverywindow.
Explicit final work-deadline checks prevent latePASS. No applicationblob/policy
budget changes, no production actions. Require fresh exact CI onfinalcontrolsource.

### Final bounded-verification controls qualified; await production procedure review

Workingbde20f5197222ddd376ef2d6a703d6fe0ba783a6 exactCI41331790634 PASS.
Finalcontrolcandidate2c24ddef0b746945caa228c5c7954b6755ebfe70 on existingdeployment
branch (fd90458->abf288b->2c24dde, noforce/newbranch/worktree). Applicationtree
byte-identicalfd90458; only7control/workflow/test/procedure paths introduced.
ExactPythonCI41331916958 PASS169backend/25controls Linux; validationworkflow
41331917043 waspush-only:validatePASS,verify/deploySKIPPED. Isolatedlocal169/25PASS
(one Linuxskip); working246backend/89controlsPASS(two/three Linuxskips).

Root-review gate defaults disabled: exactrolloverblob/runtime/release/CI and
helper/verifier/smoke hashes, approval_confirmed=true explicitlyrequired, private
one-usereview/evidence. Completequick/FK in consistentreadsnapshot retained; no
normalchecksremoved/generalbypass/consumedI7exception. Bounded ownedchildtermination
and readiness, freshsource/currentmarket/boundedpersistence/storage monitors,
DB/schema/service/config binding, one-useconsumption and APIonly/codeonlyrollback.
Allsmokeroutes retained; onlyspecific featureunavailability maydegradewithoutfail.

Proposed1800sverification+10sreap/180srecovery,35minverifyjob;300sconcurrent-DML
snapshot-evidence reuse;600sdeploy+180srecovery in15minjob remain UNAPPROVED FOR
PRODUCTION. No reviewfilecreated/helperinstalled/heavyscan/workflowdispatch/restart.
Read-onlysudo compatibility booleans only; no credentials/permission/infrachanges.
Concrete reviewprocedure/hashes/exactfuturecommands:
[RELEASE_VERIFICATION_REVIEW.md](../../deploy/lightsail/RELEASE_VERIFICATION_REVIEW.md).

Controlpreparation milestone delivered; productionprocedure review is next.
Rollover20min/3cycle/boundary validation NOTRUN; do not resume retentionexperiments.
Retention/paidAIOFF,productiondeleted0,dataintact,ceilingunchanged; no copy/snapshot,
manualWAL/index/Phase2. I7/Phase1.75OPEN; capreview2026-11-02T01:56:47.671426Z unchanged.

## Revised approval request: smoke-only ending;512MiB storage gate STOP

User revision supersedes20-30minute observation/backgroundsoak: after an approved
deployment run bounded functional API/currentmarket/source/persistence/dashboard/SSE/
service smoke, report andyield. Multi-cycle/real-boundary acceptance NOTPERFORMED;
I7/Phase1.75OPEN. Revision itself explicitly does NOT authorize production operations.

Fresh17:41:57.932247UTC DB+WAL4846731328bytes, headroom497.796814MiB<512MiB:STOP.
Priorcontrol64MiB reserve was inconsistent with required512MiB; restored512MiB
in preparedpolicy.19controltestsPASS(one Linuxskip). Frozen2c24dde helperhashes/CI
cannot qualify revisedpolicy; newcandidate/exactCI/reviewbindings required. No heavy
scan/install/authority/dispatch/restart/cleanup. Ceiling5120/deadlineunchanged.
Storage requires separately reviewed resolution; approval cannot override gate.
Procedure: deploy/lightsail/RELEASE_VERIFICATION_REVIEW.md. No repeatedCIpolling;
report pendingcommit/Actionscheckpoint andyield. Retention/paidAIOFF,deleted0.

## Storage resolution recommendation — deployment remains STOP

Bounded metadata17:48:50.976794UTC: DB4592.007813MiB,WAL32.863342MiB,total4624.871155;
physicalheadroom495.128845MiB,512MiBshortfall16.871155. page_size4096,
page_count1175771,freelist0,auto_vacuumNONE. Filesystemfree50993676288bytes does
not increase the5120MiB applicationceiling. No historicalquery or operation.

Options: wait/normalautomaticcheckpoint mayreuseWAL but guaranteedrecovery0;
normal lastconnectionclose couldreleaseup to32.863342MiB giving527.992188MiB,
only15.992188MiB abovegate before regrowth, and needs separately reviewed writer
interruption/control changes. Not sustainable or authorized here. Removing logs/
fixtures recovers0 toward DB+WAL gate. Archive uploads alone recover0 SQLitepages.
Ordinary archive-proved DELETE cancreate reusablepages but withauto_vacuumNONE
cannot promise physicalfile shrink; per-batch recoveryunknown until measured.
VACUUM/rebuild/copies/guardincrease forbidden, so no compliant guaranteed physical
512MiB restoration exists today. No unchangedtrial or manualWAL action proposed.

One recommended decision: review a512MiB EFFECTIVE-capacity gate counting only
verified reusableSQLitepages alongside physicalheadroom, retaining5120MiB physical
ceiling and512MiB reserve amount. Do not implement/change gate now. This would let
separately qualified, recovery-proved bounded cleanup precede applicationdeployment,
rather than requiring deployment to qualifycleanup. Cleanupqualification must first
address measuredcommit operation under unchanged500ms policy, use existingCI Linux
fixtures and pinneddeployedwriter, and preserve truthful read-only collection guards;
no need to ship freshness/index changes or repeat failed unchangedtrials.
At currentfreelist0 the proposed accounting also FAILS. Instant deficit17690688bytes
requires at least4320verified reusable4096-bytepages (16.875MiB); actual
qualification must additionally cover measuredWAL/regrowth/workload reserves. This
is not an approved cleanupscope or a promised rowcount/reclaimedcapacity.

Correctedpolicy254e619 exactCI41332855253 PASS, one statuscheck; no waitingmonitor
or repeatedpolling needed. Productionunchanged,storageSTOP,noapprovalrequestrepeated.
No cleanup/deploy/install/scan/guardchange/soak. I7/Phase1.75OPEN,flagsOFF;
capreviewdeadlineunchanged. Decisionneeded is capacity-accounting design review,
not deployment approval or authorization to delete.

## Authorized maintenance attempt: controller state machine implementation started

User explicitly authorizes ONE quiescent verification/deployment attempt under
30minverification/10minother/10sreap/3minrecovery and43min10s absoluteinterruption.
No concurrent-write proofreuse. Prepared pure maintenancecontroller with a single
absolute stop-request deadline, combinedother budget, recoveryreservation, physical
512MiB gate, quiescence/identity checks, partialcheckoutrollback and all-service
recovery attempts. Four simulated-host tests cover success, preflight/partialstop,
failedchecks, lowcapacity, partialcheckout/smoke, timeout and recoveryfailures.

Checkpoint1 INCOMPLETE: Linuxhost adapter/manualworkflow integration and exact
maintenance release candidate are NOT qualified yet. This is controller-core CI,
not production authority or a deployable release. Existing oldcandidates remain
ineligible. No productionpreflight/stops/scan/install/dispatch performed. Continue
sameauthorizedattempt afterCI completion; do not ask user to repeatapproval.
No observation/soak; finalsmokeonly. Boundary/multicycleacceptanceNOTPERFORMED.
FlagsOFF,dataintact,guard5120/capdeadlineunchanged,I7/Phase1.75OPEN.

## Authorized maintenance implementation completed locally; freeze exact candidate

Continuation implements Linux maintenanceadapter, one maintenanceoperation in the
existingmanualworkflow(50minouter), fixed2590sfirst-stop interruptiondeadline,
1800sverification/600scombinedother/10sreap/180sreservedrecovery. No reuseconcurrent
proof. Rootmanifest pins release/runtime/CI/helpers and original helperCODE hashes;
preflight beforestop, physical512MiB poststopgate, no DBowners exemptions, owned
completequick/FK child, writersstaystoppedthroughcheckout, bounded functional smoke,
all-service recovery/code-onlyrollback and all-helpercode restoration. Partialmonitor
stop intent recorded; failures remainSTOP/MANUAL. Unreapedchild preventsunsafe
writerrestoration and records manualactions, never signals unknownowners.

246backendPASS(two Linuxskips);102controlsPASS(three Linuxskips). Simulations cover
partialstop,checkfailure,lowspace,timeout,partialcheckout/startup/smoke,rollback/
recovery/helperfailures. StructuredActions summaries/whitelisted sanitizedartifacts
added; no rawlogs/db/credentials published. Appfd90458blobs unchanged.
Freeze controlcandidate and exactCI before production. One maintenanceauthorization
retained, no newapproval needed. No productionstops/install/scan/dispatch yet.
Quiescentcapacity feasibility remains narrow; mustrefresh before installation.
No observation/soak; boundary/multicycleNOTPERFORMED. FlagsOFF,guard/deadline unchanged.

Maintenance smoke correctly applies hard5120MiB ceiling after collection resumes;
512MiB physicalreserve is still mandatory while quiescent before verification.
No accounting substitution/ceiling change. Legacy concurrent-verification route's
512MiB livegate remains unchanged; authorizedmaintenance has its own source/
persistence probe.103controltestsPASS(three Linuxskips), with stage-specificstorage
regression. Receipt gaps explicitly upperbounds from recorded before/after samples.
Applicationblobs unchanged. Freeze revisedcandidate before any production action.

## Checkpoint1 PASS; checkpoint2 read-only capacity STOP before production changes

Frozenmaintenance release93161cf8843cd0264fe9b75d20b2204e979ca062 onexistingdeployment
branch; working2c2528e34c0c66c249d77c5a818c6aba925507b9. ExactPythonCI41336249861 PASS;
validation-only DeployTradebot41336249942 PASS(push, no manualdispatch). App tree
byte-identicalfd90458; corrected512MiB quiescentpolicy included. Isolated169backend/
39controlsPASS locally(one Linuxskip); working246backend/103controlsPASS(two/three
Linuxskips). Completed adapter/workflow, fixed2590s interruption budget, ownedfull
check/reap, all-service recovery, code-onlyrollback/helperrestoration, structured
Actions summaries and whitelist-sanitized artifacts. No newbranch/worktree.

Proceeded under existingone-attempt authorization to checkpoint2 read-onlymetadata
preflight. At2026-11-01T18:22:55.662170Z mainDB4835131392bytes(4611.140625MiB),
WAL34459712bytes(32.863342MiB), actualheadroom475.996033MiB. Even omittingALLWAL,
maximumheadroom508.859375MiB<512MiB by3.140625MiB. Thus ordinary WALclose cannot
establish capacity without shrinking mainfile; no allowed action in this exact
code-only maintenance route can satisfy the physical prerequisite. No accounting
substitution/guardincrease/cleanup/compaction was attempted. Remaining source/API
preflight was not pursued after this decisive capacity failure.

Runtime d56b4a73ad6f1a10ba2bac928087cd5d85c6a42a, trackedclean, API23471/ensemble23478/
lifecycle23474 active,NRestarts0, monitor timeractive; soleAPIowner1,no competing
collectors, flagsOFF, cap5120. Filesystemfree50973425664bytes doesnotoverridecap.
No helperinstalled, authoritycreated, monitor/writerstopped, heavycheck, workflow
maintenance dispatch or appdeployment. Actualcollectioninterruption0. No restoration
needed. Rootone-useattemptwas notconsumed; no automaticsecondpreflight/attempt.

Specific decisionneeded: whether to amend a storage boundary for this exact route.
If512MiB remains mandatory and physical main-file reclamation remains forbidden,
the authorized maintenance cannot run. Do not request the same deployment approval,
repeat qualification/CI polling or expand into another storage redesign. Existing
one-attempt authorization is retained but blocked by the failed technical gate.

FullDBchecks NOTRUN; functional smoke NOTRUN; multi-cycle/real-boundaryacceptance
NOTPERFORMED; I7/Phase1.75OPEN. Retention/paidAIOFF,deleted0,guard/deadlineunchanged.
Privateevidence: lifecycle-implementation-20261031/maintenance-93161cf (metadata
preflight, qualification logs, candidate manifest/checksums; no DB or credentials).
Productiondeploymenthistory/tagging remains after maintenance milestone, not a
reason to modify frozen candidate or advance a blocked release.

## Rotating raw generated-feasibility assessment: checkpoint1 capacity STOP, NO-GO

User requests generated feasibility, production unchanged; preserve93161cf rollout
andcontroller. Header/FK metadata19:13:44UTC shows main4637.539063MiB,WAL32.863342,
headroom449.597595MiB,freelist0,auto_vacuumNONE. EvenwithoutWAL headroom482.460938
fails512MiB. Additivemigration retainingexistingDB alreadyfailsreserve by62.402405MiB
beforeanynewcore/segment/index/WAL/workspace. No allowed productionreclamation or
capacitychange can be presumed. Checkpoint1 STOP applies; no prototype/Linuxtrial
or recoverywindow wasrun. MigrationFAIL, allsteady-state/correctness/performance/
reference/crash/outagefindingsNOTPROVEN; overallNO-GO undercurrentrestrictions.

Capacityformula C+49*(H+I)+boundary/registry+aggregateWAL+working/recovery+512<=5120;
unknownper-object/core/raw/index allocations explicitlyunmeasured. HistoricalwholeDB
rates32.28/41.58MiBperhour andprior70.31assumption extrapolate49h1581.79/2037.24/
3445.31MiB, NOT segmentrates/capacityproof. Archiveoutagegrowth perblockedhour H+I
pluscore/WAL/work unknown; no safeoutageduration claimed. No dbstatpagewalk or
historicalpayloadscan. Direct FKcatalog finds prediction_context_links.
outcome_observation_id->observations.id; JSONmetadata/price references, snapshot
chains, outcomeavailability, manifest/cursor/localid assumptions requireexplicit
crosssegment identities/protected evidence strategy. Detailedreaderinventory and
calculation: [ROTATING_RAW_FEASIBILITY_2026-11-01.md](ROTATING_RAW_FEASIBILITY_2026-11-01.md).

Metadata/arithmeticconsistencyPASS. Productionunchanged,nocopiedDB/delete/scan/
install/restart/upload/newdependency/infra/Phase2. No unchangedqualificationtrial.
Frozenrollover/controller preserved. No productionmigrationauthorization inferred.
DeploymentSTOP,flagsOFF,I7/Phase1.75OPEN,capdeadlineunchanged. Next: separately
review migrationconstraints; no anotherdesign/parametersearch authorized here.

## Retention performance decision: NOT PROVEN, explicit generated-policy proposal

Review finds commit-call latency remainingblocker; no evidenced smallSQLchange.
Validatedtrace has lock-heldWALsync58.225ms andpostreleaseDBsync116.707ms; traced
220.379mscommit vs99.423msWRITEupper. Historical>500mscommit nottraced, cause/dominance
unknown. Previous1000/500/256failures remainSTOP. No newtrial/VMload/recoverywindow.

Current93retentiontestsPASS(two Linuxskips)+2provedoperatortestsPASS; coverage,
protected/late references, durabilitysettings and committedoverrun semantics intact.
Existingreducedtrace23997rows/11.798431s=2033.914rows/s inclsetup/cleanup;65saves/RAM,
0errors,maxsave137.707ms,heartbeat165.329ms. Diagnostic, notproductionqualification.

Propose FORREVIEW generatedqualification split: validatedWRITEupper<=500ms,
commit/total<=1000ms,collector/heartbeat<1000ms/noerrors,fullworkload<=180s,
FULL/defaultjournal/settings/archive/reference/storageguards unchanged.1000is
proposedceiling,notguarantee. Intrusivetracingonlygenerated; no productionoccupancy
claim. Requires explicitapproval, NOTAPPLIED. Production500ms policy staysunchanged;
no relabeloldfailures. One nextaction: decide thisgenerated-onlypolicyproposal.
Details: [RETENTION_PERFORMANCE_DECISION_2026-11-01.md](RETENTION_PERFORMANCE_DECISION_2026-11-01.md).
Capacitygate stays separatelySTOP evenif futureperformancepasses.93161cf preserved,
rotationstopped, flagsOFF,deleted0,deadlineunchanged,Phase1.75OPEN. SharedChatGPTlink
unavailable; no inferredcontents used. No Redis/DuckDB/service/writercoordinator.

## Approved generated-only split qualification instrumentation

User approves only generated qualification: validated WAL WRITE occupancy<=500ms,
total BEGIN-entry through commit-return and commit call<=1000ms, collector save/
heartbeat<1s with zero errors. FULL/default1000-page automatic checkpoint, exact
identities/archive/reference/resource/workload limits unchanged. Production
retention.py unchanged; private generated imported candidate uses1000ms total.

New incremental per-TID strace gates require resolved fixture shm byte120 len1
acquire/release entry/exit brackets,2us rounding reserve and monotonic marker
correlation. Missing/ambiguous evidence NOT PROVEN; each batch checked before next.
Trace logs counted cumulatively against2GiB fixture guard, tracing CPU/RSS/bytes
and parsing time reported; untraced overhead not isolated. No intrusive production
trace. Production guard additionally requires current market and fresh source time.

Local93 retention safety tests PASS(two Linux skips); harness7 PASS(two skips);
new6 tests PASS(one Linux strace integration skip). Exact Linux CI and one existing
800000/2350000-row representative qualification pending; remaining two trials only
if first passes. Prior failures remain failures under original500ms policy. No
production deletion/deployment/settings change; capacitySTOP and Phase1.75OPEN.

## Generated split qualification: implementation PASS, representative NOT PROVEN

User approved generated-only split gates. Exact implementation a18ce3c6a9ab1e8c9321f521d17768c3f39526db
passed CI41359072373:252 backend tests,103 deployment controls; actual Linux strace
integration ran successfully (tiny197-row cleanup, not representative evidence).
Production retention.py and its500ms policy unchanged. New harness independently
bounds validated WAL WRITE syscall occupancy500ms,BEGIN-entry/commit-return1000ms,
commit1000ms and collector delays<1s/noerrors;FULL/default settings/protections and
resource limits preserved. Missing/ambiguous trace fails closed before next batch.

Existing800000/2350000-row,500-row-batch,three-trial fail-fast runner prepared.
Single SSH connection timed out before connecting; no remote code/fixture/load or
preflight started. Trials0/3,committed0; all representative occupancy/transaction/
commit/collector/throughput/overhead measurements unavailable, completionNOTPERFORMED.
No retry/recoverywindow. NOTPROVEN; no performance pass claimed. Previous failures
remain failures under original policy. Next: restore existing approved SSH route
and run pending qualification once; no further policy approval needed.

Evidence/procedure: [RETENTION_SPLIT_QUALIFICATION_2026-11-01.md](RETENTION_SPLIT_QUALIFICATION_2026-11-01.md).
Production unchanged,flagsOFF,deleted0,capacitySTOPseparate,93161cfpreserved,
capdeadlineunchanged,I7/Phase1.75OPEN. No deployment/cleanup/storage-policy authority.

## SSH restored; generated split trial1 runtime FAIL, performance NOT PROVEN

User confirmed restored SSH; pinned access verified22:59:15Z. Five staged files
byte-identical to exact-CI-passed a18ce3c (CI41359072373,252backend/103controls).
Read-only safety refreshed: current matching sources/market, collector running,
helper pinned,strace installed,~1.29GiB available memory,~47.27GiB physical free.
API retention/paidAI false. Production main+WAL headroom317.351501MiB fails512MiB;
capacitySTOP remains separate. Initial safe-start launcher rejected before trial;
bounded interval-edge wait corrected, no workload retry or harness change.

Trial1 started23:01:30.606778Z with800000/2350000rows,500batch,FULL/default1000.
Existing170s work deadline interrupted generate_observations (last progress740000).
No retention or competing actor started. Actual cleanup committed0; occupancy,
transaction/commit,collector delays/heartbeat/errors NOTMEASURED. Work incomplete;
trials2/3 NOTRUN, no retry. Child173.729700s/supervised174.034300s inclcleanup;
peak disk713822456bytes,RSS41172KiB. Tracer57.58CPU seconds,RSS4014080bytes,
trace610562532bytes. No untraced control, elapsed tracing overhead not isolated.
Empty-list0 timing is a sentinel, not measured zero occupancy. RuntimeFAIL and
retentionperformanceNOTPROVEN; prior500ms failures unchanged.

One bounded23:05Z postcheck: sources fresh,current matching unexpired market,
collector running; API routes<2s; servicesactive,reportedrestarts0; flagsOFF.
Disposable generatedDB removed by harness; only generated traces retained. No
production cleanup/deployment/DBcopy/settings/WAL operation. CapacitySTOP,93161cf,
capdeadline unchanged,I7/Phase1.75OPEN; boundary/multi-cycle NOTPERFORMED.

One nextaction: review retention-phase-only tracing, capturing before firstBEGIN
and everybatch with unchanged180s/FULL/resource/gates. Proposed only; no newtrial.
Detailed evidence and trace hashes: [RETENTION_SPLIT_QUALIFICATION_2026-11-01.md](RETENTION_SPLIT_QUALIFICATION_2026-11-01.md).

## Generated trace scope correction: tested locally, Linux CI pending

User authorizes phase-scoped tracing, tiny test then exact CI and representative
fail-fast qualification. Preparation now executes untraced inside original170s
work alarm/180s whole-trial deadline; clocks not reset. Before collector start,
private generated child authorizes only its exact tracerPID via LinuxPR_SET_PTRACER
and requires actual attachment plus captured trace_ready barrier. No general
ptrace permission, package, native extension, production modification or service.
Only fcntl,fdatasync,fsync,writev(marker) traced; no write/pwrite64 payload capture.
Trace hard per-file32MiB limit plus aggregate32MiB monitor, included in existing
2GiB accounting. All previous workload,FULL,default1000 checkpoint,500/1000ms split
limits and collector save-before-RAM ordering preserved. Each batch requires
complete validated shm WRITE syscalls; dead tracer before nextbatch stops.
Preparation/stage durations recorded even if deadline interrupts before retention.

Local46 core retention tests PASS;7 harness tests PASS(two Linux skips),7 lock/phase
tests PASS(one Linux strace skip). Linux tiny conformance test now asserts no
preparation trace, trace-ready before measurement,2complete transactions, no payload
write syscalls, bounded trace and elapsed includes preparation. Exact CI pending;
no representative run before success. Previous deadline failure remainsFAIL and
retentionperformanceNOTPROVEN. Productionunchanged,capacitySTOP,flagsOFF,93161cf
preserved,capdeadline unchanged,I7/Phase1.75OPEN.

## Tiny phase-scope CI correction

241b1ee CI41361117611 correctly blocked representative execution: actual tiny
qualification passed but test incorrectly expected only2commit markers, ignoring
TEMP preparation/bookkeeping commits outside measured BEGIN brackets (6observed).
Corrected assertion counts complete BEGIN-entry/commit-return brackets, still2
with exactly2validated lock intervals, firstmarker trace_ready, no traced fixture
preparation/payload writes. No harness/policy/workload change or representative
trial occurred. Local93retention tests PASS(two Linux skips). New exact CI required.

## Scoped tracing conformance PASS; representative preflight STOP

User-authorized scope correction implemented241b1ee; corrected tiny assertion
6d9edc3e2ba6de31cc3dd8115736314d74c7ece3 exact CI41361239486 PASS:253backend,
103controls. Tiny Linux strace test ran:197exact deletions,2complete validated
lock brackets; preparation untraced/included in total,trace-ready before actor,
no payloadwrite capture. Initial241b1ee CI41361117611 failed only an assertion
counting TEMP commits; no representative trial was run before corrected CI.
Local93retention safety tests PASS(two skips). Six staged files byte-exact6d9edc3.

Generated-only tracing now attaches exact authorized tracerPID after preparation,
before collector; capturesfcntl/sync/writev markers only.32MiB per-file hard cap,
aggregate32MiB monitor and existing2GiB accounting. Original170s work/177s supervisor/
180s total clock includes preparation, no reset. Workload/FULL/default1000checkpoint,
500ms lock/1000ms total+commit,collector<1s/noerrors/ordering unchanged. Stage/prep
elapsed survives timeout. No production retention.py change or new dependency.

After CI, fresh preflight rejected production_market_not_current before any fixture
or trial. One23:17:16.335158Z explanatory snapshot:market2051369 expired23:15Z
(136.335s old),matching expired quote,Polymarket source23:15:34.714391858Z~101.621s
old despite live label/lastreceipt23:17:08.870998Z. Coinbase current,collectorrunning,
API health0.081088s/current0.042213s. No recoverywindow/retry/scan. Newtrials0/3,
cleanup0; all representative lock/commit/collector/throughput/overhead NOTMEASURED,
workloadNOTPERFORMED. No new prep bottleneck claim. Prior runtimeFAIL preserved.

Nextaction: resolve expired-current-market feed precondition before resuming pending
qualification; no bypass or auto retry. Detailed evidence:
[RETENTION_SPLIT_QUALIFICATION_2026-11-01.md](RETENTION_SPLIT_QUALIFICATION_2026-11-01.md).
Productionunchanged,capacitySTOPseparate,flagsuntouched,93161cf preserved,deadline
unchanged,I7/Phase1.75OPEN; multi-cycle/real-boundary acceptance NOTPERFORMED.

## Retention BLOCKED_BY_UNDEPLOYED_ROLLOVER_FIX; one-use reserve proposal

User directs no more VM qualification or known-rollover diagnosis. Preserve
6d9edc3e2ba6de31cc3dd8115736314d74c7ece3/pass CI41361239486 and frozen93161cf.
Retention qualification now BLOCKED_BY_UNDEPLOYED_ROLLOVER_FIX, not pending another
unchanged trial. Prior failures and incomplete performance evidence unchanged.

Propose FORAPPROVAL ONLY: existing quiescent maintenance route's512MiB physical
reserve ->128MiB for ONE release of93161cf's pinned schema-free application blobs.
No global reserve/5120ceiling/accounting change. Complete read-only verification
with writersstopped has no intendedDB/WAL growth, unlike live pinned-WAL scan.
Additional budget64MiB WAL/ordinary-close overlap +23.144531MiB live growth
(20KiB/s,50%margin,790s nonverification/recovery allowance)+32MiB contingency
=119.144531MiB, rounded128. These are existing planning allowances, not measured
worst-case burst proof or a mathematically minimal requirement; explicit operational
risk acceptance needed. No WAL release credited. Last23:05 metadata headroom
314.656189MiB would exceed128 by186.656189MiB but fails512 by197.343811MiB; stale
sample cannot clear present preflight. No new production inspection or experiment.

Amendment NOTAPPROVED/NOTIMPLEMENTED; existing controls/current512gate remain binding,
capacitySTOP. If approved, amend only existing controls, freeze exact successor/helper
hashes/CI preserving appblobs; no newcontroller. Full checks/quiescence/oneattempt/
2590s interruption/180s recovery/manualworkflow/code-onlyrollback unchanged. Fresh
physical check before execution,capdeadline unchanged. No bypass/cleanup/DBcopy/WAL
operation/production change. Explicit approval required before amendment or production.
Review: [ROLLOVER_STORAGE_AMENDMENT_REVIEW_2026-11-01.md](ROLLOVER_STORAGE_AMENDMENT_REVIEW_2026-11-01.md).
FlagsOFF,I7/Phase1.75OPEN; acceptance smokeonly,multi-cycle/boundary NOTPERFORMED.

## Approved128MiB maintenance-only reserve implemented/tested

User explicitly approves one-use128MiB amendment and continuation of existing single
maintenance attempt after exact-CI/freshcapacity/deadline checks. Normal/live512MiB
policy remains unchanged. Existingmaintenancecontroller128boundary and adapter
mainfilefeasibility use sameconstant;5120physicalcap/accounting unchanged.105controls
PASS(three Linux-onlyskips), including127.999STOP,128PASS,511PASS,normal512unchanged,
unchanged1800/600/10/180/2590budgets and rollback/recovery tests. Compile/diff checked.
Freeze successor of93161cf with only5maintenancecode/test/procedure files; pinned
application unchanged. Require exactCI before fresh read-only productionpreflight.
No productioninstall/authority/dispatch/stops/scans yet, no retry or newcontroller.
Retention BLOCKED_BY_UNDEPLOYED_ROLLOVER_FIX; preserve6d9edc3/CI. Capdeadlineunchanged,
flagsOFF,Phase1.75OPEN; smokeonly ifdeployed,multi-cycle/boundaryNOTPERFORMED.

## Maintenance128 successor frozen; exact CI and metadata preflight PASS

Exact successor78bcaf07baac8ba5f26a6c7dd827c35283511f30 parent93161cf onexisting
deploymentbranch; only5maintenancepolicy/test/procedure files differ. Entire
application,normal512MiB verifier and manualworkflow byte-identical93161cf.
Exact PythonCI41362300963/validation-only41362300987 PASS. Isolated169backend
PASS,41controlsPASS(one Linuxskip); working105controlsPASS(three Linuxskips).
No newbranch/worktree;6d9edc3 and old93161cf preserved.

Fresh23:30:00.060612Z read-onlypreflight: main5021351936/WAL34459712bytes,
headroom298.402283MiB>=128; filesystemfree50127618048bytes;8807.361148s before
unchangedreviewdeadline>2590s interruption. d56b4a7 clean,servicesactive/restarts0,
flagsOFF,guard5120,privateAPI,solecollector. Capacity/timePASS forsinglemaintenance
route only,notretention/capacitycleanup PASS. Initial attempt scheduled between
marketboundaries; no sourcepoll/soak/retry. Mandatory capacity/time/source checks
repeat once immediately before helper installation/attempt. No production install,
authority,dispatch or service stop yet at this entry. Continue authorized attempt
without repeatapproval; retain fullverification/budget/recovery/code-onlyrollback.

## Maintenance128 qualified; single dispatch BLOCKED_NO_APPROVED_RUNNER

Frozen78bcaf07baac8ba5f26a6c7dd827c35283511f30 parent93161cf,exactPythonCI41362300963/
validation41362300987 PASS. Only5maintenancepolicy/test/procedurefiles differ; app,
normal512verifier/workflow unchanged.169backend/41isolatedcontrolsPASS;105working
controlsPASS.6d9edc3/passCI preserved. Approved128 onlyone-usequiescent route,
5120physicalcap and1800/600/10/180/2590limits unchanged.

Fresh23:30metadata headroom298.402283MiB/deadline8807sPASS; immediatepreinstall
source/currentmarket/recentpersistence/capacity/timePASS.23:34:24headroom297.621033,
8543.67sbeforereview. Exact5helpers installed with CODE-only originalrecords;
rootone-useauthority created. No DB/configcopy. One initialbetweenboundary start,
no sourcepoll/soak/recoverywindow. Singlemanualworkflow41362768630 dispatched23:34:31.
ValidationPASS;maintenancejob queued,no runner_name,self-hosted/tradebot-private.
Bounded runnerinventory returned no repository-visible runners. No infrachange.
Cancelled23:36:58 with no maintenance steps; no retry/alternate route.

Underexistingdeploylock verifiedunclaimedauthority/unchangedruntime/PIDs. Original
helpercode/modes/hashes restored;neworiginallyabsenthelpers removed CODEonly;
unusedauthority revoked,notconsumed.23:37:23.858797Z oldd56b4a7/API23471/ensemble23478/
lifecycle23474 active/restarts0; actualinterruption0s,writerstops0,productioncleanup0.
Main5024210944/WAL34459712bytes,remainingphysicalheadroom295.675720MiB. Fullverification,
deployment,functionalsmoke,multicycle/realboundary NOTPERFORMED. FlagsOFF,cap5120,
reviewdeadline unchanged,I7/Phase1.75OPEN. No continuingworkflowwaiter/backgroundsoak.

Retention BLOCKED_BY_UNDEPLOYED_ROLLOVER_FIX. Nextprerequisite: restoreavailability
ofexistingapprovedprivate execution route; replacementinfra/route requiresreview.
No repeatedreserveapproval needed; no automaticnewdispatch/qualification. Evidence:
[ROLLOVER_MAINTENANCE128_OUTCOME_2026-11-01.md](ROLLOVER_MAINTENANCE128_OUTCOME_2026-11-01.md).

## RUNNER READY; no automatic retry or helper preparation

User authorizes restoration of existing approved ephemeral operator-Mac runner,
no AWS/firewall change. Prior one-job runners removed/unregistered; restored same
mechanism using officialchecksum-verified osx-arm64v2.338.0 distribution. Token
runtime-only,neverdisplayed/staged. Registration26 ephemeral; listener--once.
GitHubconfirms tradebot-private-operator-20261101-234541 ONLINE,IDLE,busyfalse,
labels self-hosted/macOS/ARM64/tradebot-private. Queue0 before registration,
workflow41362768630 remainscancelled/no retry. No newpersistentdaemon/architecture.

Preserve deploymentHEAD78bcaf07baac8ba5f26a6c7dd827c35283511f30/passCI41362300963,
validation41362300987; no rebuild/reservereview. After readiness confirmation,
23:47:05.997193Z boundedread-onlypreflight: main5031120896/WAL34459712bytes,
headroom289.085876MiB>=128,free50117754880bytes;7781.362182sbefore unchanged
reviewdeadline>2590interruption. d56b4a7clean,samePIDs23471/23478/23474 active/
restarts0,solecollector,privateAPI,flagsOFF,guard5120. Originalhelperhashesmatch.

Userone-useauthorizationretained; noactive/claimedrootmanifest, priorunusedrecord
revoked. Freshboundauthority needed before any newdispatch, within existing scope;
no repeatreserveapproval requested. No helperprepared/authoritycreated/dispatch,
no productionchange, no known-rolloverdiagnosis, scan,cleanup/WAL/DBcopy orsoak.
YieldRUNNERREADY; laterexecutionstillrequiresfreshsource/persistence/capacity/time.
RetentionBLOCKED_BY_UNDEPLOYED_ROLLOVER_FIX,I7/Phase1.75OPEN,deadlineunchanged.
Report: [ROLLOVER_MAINTENANCE128_OUTCOME_2026-11-01.md](ROLLOVER_MAINTENANCE128_OUTCOME_2026-11-01.md).

## Authorized resumed maintenance IN PROGRESS — not a verification/release PASS

User explicitly resumes one maintenance attempt for unchanged78bcaf0/passCI.
Runner26 online/idle/labelsPASS.23:49:16freshmetadata headroom287.417908MiB,
7650.805sbeforeunchangedreview;flagsOFF,guard5120,oldd56b4a7clean/sameservicePIDs.
Fresh exactrelease/CI/helpers/rootauthority created in newprivatecode-record directory,
not reused from revokedattempt. Final23:49:56.404554 binding/capacity/timePASS:
287.417908MiB,7611.267sbeforereview,3477.401sauthorityremaining;runnerstillonlineidle.

Single NEWmanualworkflow41364015738 dispatched23:50:03Z; old41362768630 remainscancelled.
Existingrunner acceptedjob,checkout/exactrevisionCIcheckPASS,controlledmaintenance
step running. One23:53:47.406805 boundedphasecheck:API/ensemble/lifecycle intentionally
inactive/PIDs0,authorityclaimed,ownedfullverificationchild31617 running. No newscan,
healthpollingwindow/soak/retry. No verificationPASS/checkout/smoke claimed yet.
Maintenance1800verification/600other/
10reap/180recovery/2590absoluteinterruption unchanged. This entry isIN_PROGRESS,
notcompletion; awaitexistingcontrollerresult and restorehelpers/revokeauthority.
Retention/paidAIOFF,productioncleanup0,capdeadlineunchanged,I7/Phase1.75OPEN.

## November3 recovery checkpoint — verification FAILED; storage STOP

Supersedes stale IN_PROGRESS/maintenance-running current status. Workflow41364015738
FAILED: retained maintenance report STOP/TimeoutExpired,changedfalse,verification
1790.105331s,interruption1790.801535s,recoveryfailures[],helperrestorationPASS;
completed2026-11-02T00:20:21.653232Z. No application checkout/deployment occurred.
All3services recovered; collector later stopped at5120 physical ceiling. OldAPI
aggregateok is misleading; active systemd services do not prove live collection.

Fresh essentialread-only19:10:27.748539Z Nov3: runtime d56b4a7,API31763/ensemble31767/
lifecycle31771 active/restarts0,collectorfalse,guardlimit_reached,lastfeedsNov2
07:49:38Z. Main5323907072bytes(5077.273438MiB),WAL45171712(43.079102MiB),combined
5120.352539MiB,headroom-0.352539MiB. Page4096,count1299782,freelist0,auto_vacuumNONE,
FULL2,schema57. EvenzeroWAL leavesonly42.726563MiB,85.273438shortof128. Deletion
mayfreepages butcannotbecreditedasphysicalshrink. No recoveryrestart permitted.
Cap-reviewdeadlinePASSED; claimedauthorityhistorical/consumed,notfreshapproval.

BoundedcloudGET8verifiedmanifestmetadata perrawdataset19:13:22Z: observations
ranges1..40000 across8objects;stream8exactcursor manifests; allmetadata states
authenticatedreadback_sha256. No newobjectreadback/proof/deletion authorization;
localarchivecursor671248 isnotcoverageproof. No historyscan/payloadexposure.

Exacthistoricaltimed-outcheck UNKNOWN: oldparentdiscardedchildtimeoutdiagnostics;
retainedreporthasneitheractivechecknorcompletedchecks. Rawjoblognotavailable;
no inferencequickvsFK fromelapsedtime orsequentialorder. Implementednarrowexisting
verifier instrumentation: atomicprivatebounded8KiB phase start/completion/elapsed
partial reports;maintenanceparent records active/completedchecks,termination/reap
outcome evenontimeout/interruption. Completechecks/read-onlybehavior/childownership/
recovery/budgets unchanged.112controltestsPASS(3Linuxskips),including7newgenerated
progress tests;93retention safetytestsPASS(2Linuxskips),compile/diffPASS. Require
exactcommitCI; no newproductionverification. Preserve78bcaf0/6d9edc3/history.

Recoveryprocedure/physicalconstraintreview pending; no reserve/budget/deadline/
500ms change implemented. No servicechanges,heavyproductionscan,DBcopy/snapshot,
VACUUM/manualWAL/deletion/capincrease/deploymentretry/stresstrial. Collectionstays
stopped,retentionOFF,I7/Phase1.75OPEN,rolloverundeployed/featurefreshnessunfinished.

## November3 recovery decision complete: physical prerequisite NO-GO

Checkpoints1/2PASS: stale maintenance-running replaced with failed41364015738/
STOPTimeoutExpired/no deployment/recoveredservices,then storageguardstop. Exact
historicalcheckphase UNKNOWN(oldparentno partial phase). Diagnostic source
b8f065b7202f3f10b6bfb3b1ce1e5213496314f3 exactCI41702333233 PASS:253backend/112controls,
including7newgeneratedphase/timeout/interruption/invalid/atomic/reaping cases.
Partialreportsprivate<=8KiB,whitelisted;completechecks/read-only/ownership/recovery
and original1800/600/10/180/2590policies unchanged. No helperinstalled/scanexecuted.

Essentialbounded19:10Nov3metadata main5077.2734375MiB,WAL43.0791015625MiB,
combined5120.3525390625/headroom-0.3525390625MiB,freelist0/auto_vacuumNONE. Services
active butcollectorNOTRUNNING; sourcefeedsstoppedNov2 07:49Z,oldaggregateokmisleading.
Claimedauthorityconsumedhistorical; reviewdeadlinepassed,noextension. Bounded8cloud
manifests/dataset establish limiteddeclaredcoverage only,notfreshrowreadback/proof.

Checkpoint3BLOCKED with preciseimpossibility: EVENzeroWAL/unchangedmain permits
only42.7265625MiB physicalheadroom; prior128reserve(inapplicableexpiredrollover
approval)short85.2734375MiB BEFORE batchWAL/recovery. Normal512short469.2734375.
Removinglivegrowthfromoldallowances still64WAL+32contingency=96>42.727. Exactscope
WAL/TEMP bound unproven; rowcount/cachesize nothardgrowthbounds. Freeingrows/pages
cannotbecreditedasphysicalshrink; ampleFSdoesnotoverridecap. Currentobserved43.079MiB
WALpeak aloneexceedsoptimistic42.727headroom. No invented16/32reserve orblind60min
verification request. Existinglive-health-onlyoperator andauto-writer-restore
controller also cannot be silently repurposed for collection-stopped recovery.

One decision:KEEP COLLECTION STOPPED;no productionapprovalready undercurrent
boundaries. Detailed requiredorder/proofs/protectedidentity/FK/reusablevsphysical
checks/failurebehavior and exactcodehashes:
[STORAGE_RECOVERY_DECISION_2026-11-03.md](STORAGE_RECOVERY_DECISION_2026-11-03.md).
No productionoperations requested; any futurefeasible policy mustconsolidate
reserve+provenworkingbounds,verificationbudget/absoluteofflinewindow,stoppedhealth/
restoration andfreshauthority. CurrentR<=42.7265625-A necessary,notsufficient.

PRODUCTIONCHANGED:NO;readonlymetadataonly,noservicechanges/restarts/cleanup/scan/
DBcopy/snapshot/VACUUM/manualWAL/capincrease/deploymentretry/stresstrial/newarchitecture.
RetentionOFF,rolloverundeployed/featurefreshnessunfinished,I7/Phase1.75OPEN.


## November 3 decision — 72-hour local retention with A/B raw generations

User selected at least72h local raw retention, A/B rotation on the existing VM,
and continued Supabase archival; separate AWS S3 is not required. This supersedes
48h as the future retention target, not historical findings or production state.
[72h A/B policy](RETENTION_72H_AB_POLICY_2026-11-03.md) specifies persistent core,
two72h raw generations (approximately144h peak raw footprint), verified retirement,
references/crash safety and aggregate guard sizing. Historical short-window growth
extrapolates0.757..0.974GiB/day; conservative planning1.648GiB/day, not measured
24h averages. Planning may revise the former5GiB ceiling; no exact new runtime
ceiling, guard change, restart, migration or deletion is approved by this record.
Next milestone: numeric normal/migration budgets and generated prototype under
this revised design; preserve tested rollover/controller/verifier work. Production
remainsstopped/d56b4a7,flagsOFF,cleanup0; I7/Phase1.75OPEN. No new branch/worktree.


### November 3 session continuity — A/B/core work in progress

Added [session handoff](SESSION_HANDOFF.md) as a compact restart index. Execution
chat01a197ce-eabd-75b0-a991-d76b33c5a96b is active; it reports generated core/A/B
creation and is testing boundary/crash/reference/retirement behavior. Prototype
source/tests/CI edits are uncommitted at this snapshot; no qualification PASS or
production migration is asserted. Next session checks ownership/current Git state
before writing, preserves existing work and continues the selected72h policy.
Production remains the recorded Nov3 storage STOP,d56b4a7; retention/paidAI OFF,
cleanup0,I7/Phase1.75OPEN. This milestone changes documentation only.

## Selected72h A/B/core generated implementation; exact Linux CI pending

Continues2470103, no architecturechange/newbranch/worktree. Added generated-only
Store actuallycreatescore.db and immutableUUIDrawfilesforA/B; uniqueactive/live-slot
indexes,72hreceipt routing,source/Decimal/provenancepreservation,coreintents across
separateWALcommits,restart/dedup/globalIDs,coreprotectedevidence/predictionFKmapping,
boundedcross-generation/no-lookaheadreads. Workerownedcoreconnections,onecollector
rawowner; no queue/fullslotsSTOP. Existing productionfeature/rollover/price/verifier
work preserved, no liveimport/runtime/flagchange.

Hourlyincremental generated archives reuseexistingexactverify_archive/build_manifest;
noSupabaseupload. Sealedretirementstreams<=1000rows/object,checkswholecoverage/
strictnewest>72h/protectedrefs/rootFDdrain beforeunlinkinggeneratedmainonly; ordinary
SQLiteclose, no manualWAL. Crashbeforeunlink requires freshproof; afterunlinkregistry
finalizesidempotently. CIaddsrootLinuxgenerateddescriptor/retirement/interference
andfixed4000rowprofile,metadataartifactonly. No production paths orcredentials.

FirstlocalprofileFAIL dueprofile activationmistiming(Astarted71:59,nominal72event
not72hafteractivation),noB; failurepreserved. Timelinecorrected/tested,notunchanged
retry/thresholdtuning. Correctedpre-freezelocal4000records actuallyA/B/core,
archive4000,6.951842s,maxsave17.392ms/heartbeat125.931ms/inputprojection24.370ms,
rotation1.747ms,RSS49.87MB;errors0. LocalretirementNOTPROVEN(MacfullFDvisibility),
noactualunlink. It isscaled/pre-freeze,norealfeaturecycleor72hcontinuouscoverage.

Preliminarynumericproposal16GiBnormal/21GiBmigration:corecap5GiBderivedwholelegacy
main,144hraw+indexes20KiB/s=9.887695GiB,aggregateWAL130MiB/recovery130MiBempirical
3-roleallowances;2GiBfilesystemwork/10GiBfreefloor. At20:10:19Zboundedstat-only
legacy main5323907072/WAL45171712,FSfree49807454208bytes,projectedfree30480471040
(28.387GiB)>10GiB. NoDBscan/servicechange. Thesecapsarenotmeasuredproduction
core/rate/burst/WALbounds:capacityNOTPROVEN,notold5GiBNO-GO. Temporaryproposal
96hpostcutover/review72h,noautoextension,blockedretirementextra slots0/STOP.

Local271backendtestsPASS(7Linuxskips),112controlsPASS(3skips); generatedunit16
PASS(4Linux-only cases skipped). RequireexactCI(root16inclprofileactualretirement)
beforequalificationclaim. Consolidatedmigrationproposal/evidencebeingprepared;
productionadapter/legacy+actualfeatureequivalence/fullscale capacity/verification
completionremainNOTPROVEN. No prodmigration/delete/restart/guard/deadlinechange,
retention/paidAIOFF,cleanup0,currentstorageSTOP,I7/Phase1.75OPEN.

## A/B prototype refinement: explicit one-pending-intent invariant

Prototypee31fd55 exactCI41711635047 PASS includingactualLinuxrootretirement,
current-writerinterference andfixed4000rowprofile. Finalcrash-contractreview adds
oneDB-enforced pending-intent constraint andexplicitSTOP: a caller catching an
interrupted save cannot submit another event untilthatoneintentrecovers. Noqueue,
policy/resource/performance-threshold change. Newgeneratedtest verifiescaught
failure/backpressure/restart completion.17localprototype testsPASS(4Linux-onlyskips).
Require newexactCI forfinalsource, preservee31qualifiedevidence; noVM/production
workload or unchangedfailedqualification retry. Consolidatedreport underway.

## A/B generated prototype now reuses real feature/baseline engine

Adds boundedRAMinputprojection usingunchangedfeatures.calculate/forecasts.baseline,
not anotherformula/version. Matchinggeneratedexpressionindexes select1price/
metadata candidate perrawgen,coremetadata pin/RESTprice and17candles; avoidswhole
historymaterialization. ExistinglegacyVersion2querysemantics preserved. Core
keepscandles/referenceprices,actualsnapshots/predictions/model+abstentiondetails,
metadataauto-pins and selectedgeneration-qualifiedpriceevidence. Rawintentack and
metadatareference durability shareonecoretransaction;featurecapture usesworkerowned
coreconnection. Protectedrecords remainavailableafterrawretirement.

Newgeneratedflat-history comparisonPASS forrealvalues/quality/evidence withfuture
sourceinputexcluded;realbaseline probabilitynonabstaining,snapshot/predictionand
bothmetadata/priceFKprotected, restartdurable. Fixed4000rowLinuxCIprofile now
measuresactualfeaturecycleandpersistsgeneratedforecasts. No productionadapter
wired/no networkcloudcall; existingSupabaseHTTPmethodcontract/schema reusedagainst
fakeprivateobjects/manifests. Productioncloudstructured-IDmapping/legacyimport/
fullscale/dailygrowthremainNOTPROVEN. No featureversion/productionindex changes.

273localbackendtestsPASS(7Linuxskips),112controlsPASS(3skips);finalexactCIrequired.
Preservee31CI41711635047 and05f invariant/history. No threshold orworkload-size/
resource amendment; firsttimelineFAILpreserved, no unchangedfailedstressretry.
No productionmigration/guardchange/deletion/restart/expiredauthorityreuse.
Consolidated16GiBnormal/21GiBtemporary proposal stillreview-only/NOTPROVEN, not
old5GiBNO-GO. ProductioncollectorSTOP,flagsOFF,I7/Phase1.75OPEN.

## A/B/core working generated qualification complete; production NOT PROVEN

Exactfinalsource02e01436ffab853d4fda20cf0a2be2c3e5628455,
CI41715155473 PASS:273backend,17Linux-root generated lifecycle/profile,112controls.
ActualA/B/core files created; streamedfresharchivecoverage/protectedcoreevidence/
OSFDdrain/actualretirement/newroleUUID/crashrestart/current-writer interference
ran,notjustdesign. Onependingintent enforced,restartafterrealos_exit exactlyonce.
Usesunchangedfeatures.calculate/forecasts.baseline withindexedboundedRAMprojection;
flatgeneratedhistory provesvalues/quality/evidence equivalence andno future-source
input. Corepersistssnapshots,predictions,abstention/model/evidence identity details.
Existingrollover/discovery/serialworker/cancellation/publication controls preserved.

Fixed4000rowLinuxprofile PASS_SCALED:18.128395s,RSS43655168bytes,peakworkspace9668381
bytes,save21.975ms/heartbeat239.292ms/query62.060ms/realfeaturecycle7.617ms,
rotation9.895ms/retirement119.121ms. Archive4000rows/0.312587s=12796.4fixture rows/s,
13cycles/13nonabstainingbaselines,errors0,workcomplete. FULL2; raw/core/index/WAL
sizes inreport/artifact. Simulatedinputage0 isNOTrealmarketfreshness; actuallive
snapshot/publicationage/API/SSE/RESTintegration/sustained72h NOTPROVEN. RootCIproof
notrepresentativeLightsailperformance. InitialtimelinemistakeFAIL preserved, not
relabeled; correctedlocalMacdrainNOTPROVEN preserved. No unchangedfailedstressretry.

Numericreviewproposal16GiBnormal/21GiBtemporarymigration,includingretainedlegacy
5.000344GiB,corecap5GiB,144hraw+index estimate9.887695GiB,130MiBWAL/130MiBrecovery,
2GiBFSworking/10GiBactualfreefloor. Stat-only20:10Zfree49807454208bytes projects
30480471040bytesfree(28.39GiB). Exactformula/testedbudgetcalculator; NOTPROVENfor
actualcore+ledger+protectedgrowth,rawarrival/bursts,fullWAL/TEMP/verify/recovery.
Budgetcaps areproposedbounds,notmeasuredproductioncomponentrequirements. Noindependent
fullA/Ballowances/freepagecredit. Temporaryproposalreview72h/expiry96haftercutover,
noautoextend,blockedretirementextra slots0/STOP. Newdesignsizingnotold5GiBNO-GO.

Consolidatedreviewcontainsidentity/legacy/structuredSupabaseadapter requirements,
forward-onlynewwrites+originallegacyreadhistory,service/quiescence/completechecks,
failure/forwardrecovery/code-vs-data rollback,expiry,smoke andsustainedgates:
[AB72_QUALIFICATION_AND_MIGRATION_REVIEW_2026-11-03.md](AB72_QUALIFICATION_AND_MIGRATION_REVIEW_2026-11-03.md).
CP1NOTPROVEN(arithmeticPASS),CP2/3generatedPASS,CP4PASS_SCALED/fullprodNOTPROVEN,
CP5NOTPROVEN/notproduction-executable untillegacy/app/cloud compatibility and
representativevolume/verificationtiming qualify. Current2GiB/180s qualification
limitsunchanged,cannotclaimtheyprove16GiBenvelope; amendmentneedsreviewbefore
largergeneratedrun. No fabricated newverification budget or executionapproval.
Onepackage,no fragmentedproduction approvals; do not deployprototype.

PRODUCTIONCHANGED:NO. Onlyoneboundedstat-onlyread forcapacity; no service/config/
flag/guard/deadlinechange,migration/delete/DBcopy/snapshot/manualWAL/newinfra/firewall/
paidAI/trading/Phase2. CollectorSTOP,d56b4a7lastverified,retention/paidAIOFF,cleanup0;
I7/Phase1.75OPEN. Preserve78bcaf0,6d9edc3,verifierdiagnostics/pricework and historical
failures. Existingdeploymentbranch untouched byprototype. No newbranch/worktree/chat.
Next:existing-designcompatibility/fullshapequalification,thenONE finalexecution
approval withprovenbudgets; no productionapprovalrequested fromscaled success.


### November 3 — mandatory A/B production safeguards and qualification

User requires comprehensive tests,safeguards,explicit holds andbounded retries
before production use. [A/B production safety gates](AB72_PRODUCTION_SAFETY_GATES.md)
specifies default-disabled routing/retirement,fail-closed placeholders,exact durable
identity/acknowledgement,retry classification/deadlines,archive/reference protection,
capacity andcross-file recovery,real application/legacy/cloud integration andfault
injection. Preserve one-attempt/no-production-retry controls. Generated02e0143
results remainPASS_SCALED;16/21GiB budgets are proposals;productionmigration remains
held. This milestone adds documentation requirements only,not runtime approval.

### AB72 integration safety checkpoint after905f2bf — November3

Added generated-integration authenticated GET adapter with three-attempt maximum,
1s/2s bounded backoff, original deadline accounting, Retry-After deferral and
permanent error holds. No upload/SQLite/maintenance retry added. Seven focused
MockTransport tests use the actual existing SupabaseHTTP request path. Full local
backend280tests/7skips and controls112tests/3skips pass; skips not passes.
See AB72_SAFETY_INTEGRATION_STATUS_2026-11-03.md for each requirement disposition.
HTTPX inactivity timeout is not hard wall termination: transport/production
integration stays NOTPROVEN. Legacy/application/cloud/fullscale/failurematrix
remain open. Production unchanged, collectionSTOP, flagsOFF, migration unauthorized.

### AB72 integrated compatibility candidate after905f2bf/ecd8a03 — November3

Generated-only application adapter now retains legacy raw read-only and migrates
real structured schemas/IDs/direct FK/embedded evidence/cloud cursors into core,
with namespaced protocol tables. Optional actual collector/feature/history and
lifecycle seams/default holds, forward-only write guards and exact archive schema/
checkpoint compatibility are implemented. Hard child supervision covers original
request+retries+body+backoff; conditional upload/manifest ambiguity reconciles
without another write. Generated failure matrix includes actual SQLiteFULL,
permissions, reference/identity holds, concurrency, supervisor drain and process
exits at migration/raw/feature/archive transitions. Source candidate CI pending.
Local final full suite305backend/8skips and112controls/3skips passed; an additional
embedded-reference safety test passed after that run; exact CI must qualify the
complete final tree. Linux root app retirement is unproven locally, never a pass.
Production untouched, collection remains recordedSTOP; both production gates,
retention and paidAI remainOFF. Capacity16/21GiB remains unapproved/unqualified.
Representative volume, actual cloudRLS/auth and production cutover/verification
controls remainNOTPROVEN; passing generated integration cannot authorize migration.

AB72 compatibility candidate follow-up: routed Polymarket save failures now stop
that source immediately without reconnecting; latched REST storage holds degrade
aggregate health explicitly. History holds retain the existing unavailable HTTP
response contract. Focused generated source-stop test asserts the save itself was
attempted, uses no venue keys/network, and passes. Freeze successor source for
exact-commit Linux CI; no production enablement or operations authorized.

AB72 matrix completion: real process exits now cover sealing an existing A while
publishing B, plus Linux-root retirement authorization/normal-close/file-removal
boundaries. Generated disk archive now safely reopens an existing private fixture
for fresh recovery readback; focused reopen and seal-process tests pass. This
corrects a fixture restart limitation, not production archive behavior. Successor
exact-commit CI must run root application/retirement cases; no source-CI substitution,
production mutation, migration approval or capacity-policy change.

AB72 sidecar matrix audit: prototype opens now reject unknown SQLite sidecars,
component symlinks and unexpected component owners before SQLite opens the path.
Focused test passes using never-opened fixture paths. First test version failed
on an existing generated-WAL collision; its error teardown removed that generated
sidecar. This was a test-boundary mistake, not a pass, with no production impact.
The corrected test never replaces/removes SQLite-managed files. Preserve that
failure explicitly. Prior138f455 exactCI41726393093 passed; successor needs its own
exactCI and must not inherit that result. No production operation authorized.

### AB72 integrated compatibility checkpoint — final generated evidence

Frozen source b39c83755608b8065a0099c7d10b3ca8ad0f5800, exact LinuxCI41726968944
https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41726968944 PASS.
Backend311tests OK/6privilege skips, all covered by explicit root17protocol +
24application tests with0skips; deployment/maintenance112tests OK/0skips. Installed
strace tiny harness and Node dashboard test ran. No packages installed for tracing.

Generated compatibility PASS: legacy original IDs/direct+embedded refs/cloud
cursors, actual collector/supervisor/REST/serial features/forecasts/LiveState/history/
ensemble/lifecycle routing, private exact archives/conditional cloud reconciliation,
hard entire-request child deadline, durable handoff/forward recovery and failure
matrix. Root actual file retirement and os._exit retirement recovery passed.
No current failing test waived. Source remains generated-only/default-disabled;
this is not an exported production release or production migration approval.

Retained development failure: first sidecar test collided with a generated WAL;
error teardown removed that generated sidecar. This violated the test boundary;
no production impact. Corrected case uses never-opened fixture paths and passed
its own successor CI. Prior failures remain failures, including old retention gates.

Current4000row component profile PASS_SCALED: zeroerrors,4000archived,13feature/
baselinecycles; maxsave23.833ms/heartbeat227.886ms/query68.696ms/feature12.485ms;
18.317s elapsed. This is protocol/component evidence, not representative full
ApplicationStore/cloud throughput, real72h observation or production freshness.
See AB72_INTEGRATED_COMPATIBILITY_2026-11-03.md for every gate disposition/skips.

Production untouched; deployment branch still78bcaf0, no service/cloud mutation,
DB copy/backup/snapshot, production deletion, capacity/flag/deadline change or
production attempt. Recorded collectionSTOP persists. Capacity16/21GiB remains
unapproved/unqualified. Production-volume audit/migration, actual cloud auth/RLS,
full verification timing and approved cutover/export/recovery remain NOTPROVEN.
Changed-owner/physicalENOSPC/hardware power-loss faults are not certified. No new
approval requested; no automatic soak or retry. I7/Phase1.75 remain OPEN.

### AB72 resumed worker/export candidate — November3

Preserved7ffffb5 HEAD/unrelated edits and all pending integration work. Completed
separate generated lifecycle/feature/history access without collector/raw-write/
retirement authority, durable-ack-only raw views and checksum-verified protected
core history after retirement. Quiescent legacy WAL rows/FKs tested. Transaction
raw leases remain pinned until commit and refresh afterward. Actual active chart
request is supported without increasing the10000-row result guard.

Cloud checksum/JSON processing is inside the original hard deadline. Structured
ambiguity reconciles exact identities; original numeric text and binary cursor
ordering are preserved. Candidate exporter binds selected regular tracked files,
SHA256/Git blobs/modes and rejects sensitive paths/symlinks before blob reads.
No untracked files or local data are included.

Local full backend331tests/9platformskips and controls112tests/3skips passed before
final additional focused cases; new worker,ack,checksum,reconciliation,export,
WAL,transaction,core-history and deadline/boundary cases pass. Exact-commit Linux
CI must run full suites on exported bytes, then one manifest-identical integrated
ApplicationStore4000-record qualification with actual collector/feature/history/
ensemble and separate LifecycleWorker/SupabaseHTTP MockTransport (no real cloud).
It retains170s work/180s whole clock including export preparation,512MiB/process
and2GiB whole-workspace accounting. Candidate qualification pending, not a pass.

No production mutation/deployment/DB copy/manualWAL/guard/flag/deadline change.
Collection remains recordedSTOP; proposed16/21GiB ceilings remain unapplied.
Phase1.75/I7 OPEN; old b39c837/CI41726968944 remains last completed qualification.

### Corrected exported worker candidate

880181f exactCI41735427263 FAIL before execution: jobs=[], no logs/jobs/trial.
The workflow incorrectly used runner context in job defaults. GitHub's contexts
reference permits runner at step working-directory, not jobs.defaults.run.
Moved exported directories to supported step scope; regression test passes.
No qualification was run or retried under that failed workflow.

Actual feature runtime/qualification now uses restricted worker handles, not a
collector-capable connection. Owner release waits for worker handles/opening to
drain. Separate lifecycle/history roles remain without raw/retirement authority.
Corrected local full backend337tests OK/9platformskips; controls112tests OK/3skips
from preceding applicable run; focused workflow/runtime-worker checks pass.
Successor requires its own exact exported full-suite CI and first integrated
4000-record qualification. No previous component profile counts as that result.
Production untouched, capacitySTOP, flagsOFF, no approval/limits/deadline change.

### Integrated qualification resource-accounting successor

f87fc4e exactCI41736469183 PASS: actual exported backend337tests (6root-onlyskips
covered), root17protocol/32application,112controls; first integrated ApplicationStore
qualification PASS_SCALED_INTEGRATED.4000new rows committed,4002archived including
2legacy backlog rows;20real feature/ensemble/history cycles,10publications;0errors;
maxsave188.317ms,heartbeat305.091ms,feature105.345ms,history33.049ms;46.882s elapsed.
That run counted named workspace files and parent unlinkedTEMP, not descendant
unlinkedTEMP. Preserve its measured result/scope; do not call it complete family
TEMP accounting. Successor includes named files plus unique unlinked inodes over
bounded Linux process-family descriptors. Workload,170/180s,512MiB/process and2GiB
limits unchanged; Linux child-TEMP test added (local platform skip, not a pass).

Immutable structured inserts now use ignore-duplicates with readback, so a
concurrent conflicting insertion cannot be overwritten after the pre-read.
Focused race test passes and confirms conflicting remote bytes remain intact.
No production mutation, capacity/flag/authority/deadline change. Successor needs
its own exact exported CI and qualification; no unchanged retry/matrix authorized.

### Exported result review: exact-second rollover defect

cc44c3f exactCI41737929171 PASS: exported backend339/root17protocol/root32app/
controls112 and integrated4000new/4002archived/0pending/0errors. Measured save28.435ms,
heartbeat155.619ms,feature161.259ms,history44.103ms,54.500s,wholeworkspace21969852B.
However20featurecycles produced only10publications. Result review reproduced a
market-identity defect with a tiny fixture: fractional-zero stored timestamps vs
an exact-second nonfractional now used lexical comparisons, retaining expired
market identity at the boundary. Do NOT accept that CI as final rollover proof.

Changed only market identity predicates/order to existing julianday semantics;
no price query,feature version,index,cadence or acceptance-threshold change.
Tiny exact-second regression plus existing186s rollover/truthful-health cases pass.
Integrated qualification now requires publication in BOTH simulated boundary
markets and final current identity; guard rejections record bounded contexts.
Successor must pass its own exact exported CI/qualification; prior runs retained
with actual measured scope, not relabeled final acceptance. Production unchanged.

### Exported ApplicationStore milestone — completed generated qualification

Frozen exact source61e0008c59696168bdaa043fce6b88e5b22f6d19;
https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41738983997 PASS.
Exporter tested selected207source files/2337764bytes; manifestSHA256
c06c92d1313aa30f2c166fcdc2107782a198a7b41c389cf22d97908bcbf35282.
Full suites ran on the export; rebuilt manifest matched before integrated trial.
Linux backend340tests OK/6privilege skips all covered by root17protocol +33app
OK/0skips; controls112 OK/0skips. Node/strace/descendant-TEMP cases actually ran.

Actual ApplicationStore+real collector/LiveState/serialfeature/baseline/ensemble/
history+separateLifecycleWorker/SupabaseHTTP MockTransport:4000newcommitted,
4002archived (4000new+2legacybacklog),0pending,0errors,20completed/published jobs
(10before+10after simulatedboundary),finalmarketafter. Maxsave240.662ms,
heartbeat303.473ms,feature102.500ms,history23.384ms;simulatedpubage0.050s/input0.010s;
40.126s includingprep;RSS53075968B,wholeworkspacepeak22375667B with familyTEMP;
rotation7.554ms/verifiedgeneratedAretirement122.489ms;endtoend99.69newrows/s.
All original170/180s,512MiB/process,2GiB limits preserved. Hosted/scaled/simulated,
not VM/real-network/production freshness/retention split-gate or capacity proof.
No old500ms failures relabeled; no writer-lock occupancy inferred from save time.

Intermediate880181f CI failed before any job/trial (unsupported workflow context).
f87fc4e andcc44c3f measurements retained with missingTEMP/boundary evidence scopes.
Exact-second mixed fractional timestamps retained expired identity; tiny regression
proved/fixed market predicates using existingjulianday semantics, and the final
harness requires publication in BOTH markets. No threshold/pricequery/version/index
or RESTcadence change. Other corrections/failurehistory are retained in the report.

All requested resumed worker/ack-read/deadline/export tasks now implemented/tested.
See AB72_EXPORTED_CANDIDATE_RESULT_2026-11-03.md for eachcheckpoint,measurements,
privateevidence,ONEgatedmigrationprocedure,numericproposals+expiry andexactblockers.
Sessionhandoff and historicalreports point there. Evidence-only docs commit uses
[skip ci] to avoid rerunning an unchanged workload; qualifiedcode remains61e0008.
The docs commit is NOT a release candidate and does not inherit deployment CI.

Production untouched/recordedcollectionSTOP;defaultproductionrouting/retirement,
retention,paidAI remainOFF;cleanup0;deploymentbranch78bcaf0 preserved. No production
migration/deletion/restart/DBcopy/snapshot/VACUUM/manualWAL/infrastructure/guard/
authority/deadline change.16/21GiB proposals remainUNAPPROVED/unapplied. Procedure
NOTEXECUTIONREADY: actualproduction schema/protectedaudit/volume/import and
capacity/rates/WAL/TEMP/recovery,realSupabaseauth/RLS/concurrency,completeverification
finish time (old1790s timeout),guardedcutover/oldlegacywriteprevention/decommission
stillNOTPROVEN. Existing1800verify/600other/10reap/180recovery/2590interruptionlimits
andexpiredcapdeadline not changed/reused. No production approval requested.
Productionmulticycle/realboundary/sustained72h/144hacceptance NOTPERFORMED.
I7/Phase1.75 OPEN;noPhase2. Preserve unrelatedAGENTS+76/roadmap+596 edits.

### November3 — production-readiness preparation after528e798

- Frozen61e0008/CI41738983997 PASS_SCALED_INTEGRATED preserved. No unchanged
  representative trial, architecture restart or production migration.
- Fresh bounded metadata using existing pinnedSSH route:5323907072Bmain,
  45178880BallocatedWAL,49806835712Bfree,1826markets,18289snapshots,27743predictions,
  20directlinks/8targets. Raw count/embeddedreference audit still NOTPROVEN.
- Deployed Supabase read-only schema/conflictkeys/cursors/privatebucket compatible
  within inspected scope; runtime privateHTTP/write/concurrency NOTPROVEN.
- Existing maintenancecontroller generated-only transition mode now preserves
  stopped state/commits and recoversforward; productionpath rejected, defaultmode
  unchanged. Full quick/FK actual generatedadapter checks; metadata/privacy cases.
- Fixed stress proposal and quantified host deficits prepared;40GiBworkspace/48h
  plus10GiBfree and1.5GiBavailableRAM proposed ONLY. Neither currenthost qualifies.
  Current2GiB/170/180s/512MiB limits not changed; no largefixture launched.
- Production ceilings notderived: old16/21unqualified, stronger31/36stress-only
  arithmetic not policy. Currentstreaming/productionguard/cloud/fullverify gates
  remain explicit. No production approval requested. See consolidated readiness
  reportAB72_PRODUCTION_READINESS_2026-11-03.md for prerequisites and evidence.

### November3 — readiness binding and bounded migration preflight correction

- Before successorfreeze, added data-allocation binding in generated operator
  rehearsal: main/WALdevice,inode,length,allocation,mtime plus schemaidentity.
  Same-schema post-verification rowmutation STOPs before transition.
- Generated importer bound now visits at most10001rows and rejects, rather than
  COUNT(*) over arbitrary rawhistory. Original10000rows/128MiBaudit limits remain.
- Local application34tests PASS/2Linuxroot-only skips; new transition6tests PASS;
  controls120tests PASS/3Macplatform skips. Exact successor exportedLinuxCI still
  required;af3d8cb is intermediate preparation, not final migration authorization.
- No productionmutation,limitincrease,largeprofile or livecloudwrite. Consolidated
  readiness report retains resource/cloud/verification/liveguard prerequisites.

### November3 — prerequisite resource family correction before final freeze

- Proposed generated resource package counts collector/feature parent,lifecycle
  worker AND hard-request child:3processes at unchanged512MiB AS each; require
  2GiBavailablehostRAM including512MiBhostreserve, not2processes/1.5GiB.
- ExistingVM totalRAM is below that available-memory floor; service stops cannot
  qualify it. ExistingMac also lacks fullLinuxFD/platformproof and50GiBfree.
-40GiB/48h generatedworkspace policy and syntheticcloud test remain proposals,
  not execution permission. Existing qualificationlimits and production unchanged.

### November3 — consolidated readiness handoff, no production authority

- Frozen readiness successor835e5075183231a9f5f4d8541b4f33f85c14eb8d pushed.
  ExactCI41745773184 INPROGRESS at single check, not PASS. Await completion or
  one statuscheck onresume; no backgroundpoller/soak. Later documentation HEAD
  is not releasecandidate and cannot inherit sourceCI.
- Frozen61e0008/CI41738983997 scaledintegrated acceptance preserved. New controls,
  boundedschema/dataallocation binding and bounded10001row importpreflight tested.
  Local340backend+2workload,34application and120controls PASS with explicit platform
  skips requiring exactLinuxCI; expected successorfullbackend343 not claimed yet.
- Consolidatedreport includes freshmetadata, actualschema/conflictkeys/privatebucket
  andcatalogprivileges; metadata grants do not certify runtime HTTP/writeconcurrency.
- Resourceproposal40GiBworkspace/48h oneattempt +10GiBfreefloor,3processes at512MiB AS,
  >=2GiBavailableRAM/oneCPU. Neithercurrenthost passes. No increasedfixture or
  cloudsyntheticwrite executed. No16/21or31/36GiBproductionpolicy adopted.
- ProductionreadinessNOTPROVEN. Streamingvolume/importaudit,actualcloud,
  completeverificationfinish andproductionlegacywriterOSguard/livebindings remain.
  No productionapproval requested; one prerequisite reviewpackage only. Existing
  deadlineexpired unchanged; collectionstopped/retentionOFF/paidAIOFF/cleanup0.

### November 4 — early A/B switch and verified retirement

- Generated 128 KiB threshold switched from A to B one simulated second after
  activation. A failed archive left A and its manifest state intact. B durably
  acknowledged three writes during the successful readback pause and another
  after removal. An open reader prevented removal. The current price input and
  existing prediction evidence survived in core.
- Peak sampled aggregate file length was 1,110,818 bytes across A, B, core,
  sidecars and generated archive working files. The elapsed time from sealing
  through the injected failure, successful verification, reader drain and
  removal was 0.026 seconds. The macOS fixture substituted the OS descriptor
  probe and exercised real managed reader leases and file removal.
- Budget steady-state overlap as one sealed buffer plus B's growth during
  archive, verification and reader drain. Keep a separate blocked-retirement
  envelope for two occupied slots and bounded ingestion stop. Add retained
  legacy allocation, core and evidence growth, WAL, working files and recovery
  headroom for cutover. The small fixture does not size these production terms
  or qualify the prior 40 GiB / 48-hour workload proposal.
- Production review still needs an application lifecycle wake/drain path and
  Linux descriptor proof. Measure overlap under representative archive latency
  and arrival rates before selecting ceilings or requesting migration approval.

### November 4 — ordered qualification at 1a48805

1. **PASS — Linux generated rotation and retirement.** Exact source
   `1a48805260135a493adf445161079c0e3229f22e`,
   [CI 41953150879](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41953150879).
   The root run passed 18 protocol and 34 application tests. The 128 KiB
   early A → B switch and simulated 72-hour switches exercised a single active
   writer, durable acknowledgements and fresh IDs on B → A reuse. Real
   descriptor checks held retirement for unmanaged readers. Managed leases,
   missing or corrupt archives, and missing protected evidence also held
   retirement. Process exits at preparing, file creation and publish recovered
   the sealed/active pair and the previously acknowledged observation.
   Exit after raw commit replayed the core acknowledgement exactly once.
   Exits at retirement authorization, normal close and file removal recovered
   protected evidence and valid foreign keys. This proves the tested recovery
   protocol across separate WAL databases, not cross-file WAL atomicity.
   The focused Linux fixture sampled 1,238,538 bytes across raw/core/sidecars
   and archive files, with 80.9 ms seal to removal. The separate generated
   integrated regression sampled 22,038,513 workspace bytes and committed
   4,000 new records with 4,002 archived, including legacy backlog.
2. **BLOCKED — real archive.** Prepared one scoped probe using the existing
   Supabase HTTP client and CompatibleCloud wrapper, private market-raw bucket,
   and the exact ab72-readiness/2026-11-03-v1/ namespace and synthetic identities
   in AB72_PRODUCTION_READINESS_2026-11-03.md. Use generation/dataset/digest
   object keys, conditional creation and an authenticated GET on the same
   runtime identity. Compare SHA-256, compressed length, parsed row count,
   generation and first/last source identities. Replay identical bytes and
   reject a conflicting duplicate, then recheck the original object. Inject
   a post-send timeout, denied request and corrupted readback at the client
   boundary. Reconcile ambiguous POST by GET only, and verify failures keep A
   sealed and two occupied slots stop ingestion at the safe boundary. Cap the
   run at 180 seconds and 60 HTTP attempts, two 64 KiB objects and eight
   isolated rows, with at most three attempts for classified transient GETs
   and no blind write retries. Cleanup requires explicit exact-scope authority.
   Next action is approval of these synthetic mutations and a verified binding
   to the intended runtime identity. Historical catalog grants and generated
   transport results do not supply that live proof.
3. **BLOCKED — representative storage limits.** Stopped at checkpoint 2.
   Generated peaks above do not establish archive throughput, outage runway,
   local window, or a production ceiling.
4. **BLOCKED — release rehearsal.** Stopped at checkpoint 2. The tested crash
   recovery above is generated protocol evidence. The ordered cutover gate
   still requires legacy writer fencing, one new writer, forward recovery
   after acknowledgement, and exact-release workflow qualification.

### November 4 — authorized synthetic archive probe BLOCKED

- Source checkpoint 259be01 and Linux baseline 1a48805 (CI 41953150879).
  The single authorized probe stopped during archive runtime identity binding.
  Systemd unit, process UID, working directory and command checks passed.
  The host-side import raised ModuleNotFoundError before the enabled project
  and bucket binding could be reported. The probe assumed the legacy checkout
  shipped the candidate retention_recovery verifier, which is absent from
  the recorded legacy revision d56b4a7.
- Zero HTTP attempts, zero uploads and zero synthetic rows written. No cleanup
  is needed. The authorized attempt ended at the first blocker.
- Next action is to prepare and validate a self-contained candidate verifier
  that runs with the checked lifecycle process identity and its configuration.
  Any new live attempt requires a fresh one-run approval. Disk sizing and
  outage runway follow successful archive qualification.

### November 4 — self-contained archive verifier offline qualification

- Built a deterministic zipapp containing the candidate archive verifier and
  its retention and timestamp guard dependencies. Uses Python standard
  library HTTP and requires bundled import origins. Live mode binds the
  systemd lifecycle PID, start time, command, working directory and UID,
  checks the enabled project and bucket, and drops to the lifecycle user.
- Five tests passed in a Linux container with no external network, a read-only
  filesystem and only the bundle and test runner mounted. Probe subprocesses
  used Python -IS, an empty environment and a temporary working directory.
  Each omitted module and each project, bucket, UID or command mismatch
  produced zero endpoint requests. Loopback also proved exact authenticated
  readback, no overwrite of an existing object and a hold on corrupt readback.
- Bundle SHA-256
  e5be6cf656a2ce761667fb5b3d817aeadd5b53f83ff08b242e57257efd89cfc1.
  Original prefix and limits apply. The probe uses at most three HTTP
  attempts, one object at most 64 KiB, two embedded synthetic records and
  zero structured row writes. Live process binding and Supabase remain
  untested in this offline checkpoint. Review the live command before
  a fresh one-run approval.

### November 4 — archive absence diagnostic

- Matched the failed GET in Storage logs and reproduced HTTP 400 / NoSuchKey / 404 with one read-only request. Zero writes. Exact diagnostic, Linux tests, bundle checksum and proposed command are in [archive probe review](AB72_ARCHIVE_PROBE_REVIEW_2026-11-04.md).

### November 4 — scoped live archive probe PASS

- The approved one-run command from 2fb74af checked the bundle SHA-256
  3ea35c10ebec4bf47eaad305c14d13ea3581b4e6b1f0bb485e969b1d2729bbe5
  and bound to lifecycle PID 31771, the intended project and private
  market-raw bucket before upload. Preflight confirmed HTTP 400 / NoSuchKey
  / embedded 404. Create-only upload and authenticated exact readback
  completed in three HTTP attempts under the 180-second deadline.
- Readback matched 197 bytes, two synthetic records, both identity boundaries
  and SHA-256 a57a281ddb38b00918901d2d253d01898bd2dd83afcdaaefd0998462b47dba1e.
  The single object remains under
  ab72-readiness/2026-11-03-v1/72000000000000000000000000000001/stream_events/
  with that SHA-256 as its .jsonl.gz filename. Zero structured rows written.
- Next measure representative rotation overlap and outage runway in a
  separately scoped qualification. Production cutover and cleanup require
  their own approval.

### November 4 — scaled rotation and outage capacity at 08ce0d9

- One bounded Linux run used exact exported source 08ce0d9, a local
  FileArchive transport, and generated stream/book payload lengths from
  readiness_workload.py. The mix was one observation per 18 events. The
  simulated receipt clock advanced at 20 KiB/s of payload. Each slot used
  a 2 MiB main-plus-WAL trigger. The container had no external network,
  one CPU, 512 MiB memory/AS, 256 MiB writable tmpfs and the original
  170-second work / 180-second process limits. The live archive probe
  remains evidence of runtime access and exact byte readback.
- **Measured normal rotation.** A sealed after 1,710 acknowledgements
  at 2,097,152 main-file bytes, about 32.50 KiB per simulated second
  of gross raw file allocation. The effective active window was 63.013
  simulated seconds. B acknowledged 91 rows during the archive worker
  interval. Seal to verified removal was 0.764 wall seconds with Linux
  descriptor drainage. Sampled aggregate peak was 8,039,382 bytes across
  raw files, core, SQLite sidecars and archive working files. FileArchive
  wrote 781,446 compressed bytes in 1.523 ms and read 1,562,892 bytes in
  1.383 ms including final verification readback. These are local
  transport timings, not Supabase throughput or isolated reader-drain time.
- **Measured outage behavior.** A remained sealed and byte-for-byte intact
  after the injected archive failure. B acknowledged 1,667 rows over
  61.395 simulated seconds of runway. Its next size-triggered switch
  stopped with both slots retained, before a new pending intent. Peak was
  9,768,928 bytes. This exercises the occupied-slot guard, not a claim
  that every possible append stops before a production physical ceiling.
- **Illustrative cutover arithmetic.** Adding the recorded 5,369,085,952-byte
  retained legacy allocation and the proposed 1 GiB recovery reserve
  gives 6,450,867,158 bytes for normal and 6,452,596,704 for outage.
  These totals use tiny fixture peaks and are not proposed limits.
- **Representative capacity BLOCKED.** At the historical planning input
  20 KiB/s, one 72-hour payload window alone is 5,308,416,000 bytes,
  3,160,932,352 bytes above the approved 2 GiB workspace. Two full slots
  alone exceed it by 8,469,348,352 bytes before indexes, core, WAL and
  working files. The previously modeled stress fixture calls for 40 GiB
  workspace plus 10 GiB free floor, at least 2 GiB available Linux host RAM
  with at most three processes at 512 MiB each, and a proposed 48-hour
  deadline. These are qualification proposals, not measured requirements
  or approved limits. The operator filesystem sample was 33,961,353,216
  bytes free, 19,725,737,984 below the proposed 50 GiB start floor.
  The existing 180-second authorization does not cover that run.
  Production archive/readback rates, reader-drain distribution, outage
  runway and effective size-trigger window remain unqualified.

### November 4 — generated full application handoff PASS

Exact candidate `6bbc6590b8d50e9caa0dcb2c309b97f9480dbde6`,
[Linux CI 41963620712](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41963620712).

| Check | Result |
|---|---|
| Early switch and durable saves | PASS. The 256 KiB trigger sealed A and activated fresh B after one simulated second. The real Coinbase save path wrote three distinct, core-acknowledged B ticks, verified through a new reader. |
| Dashboard | PASS. The real status route switched from A to the exact B generation ID and retained it after retirement. The dashboard contract rendered the B buffer label. |
| Deterministic predictions | PASS. Three published baseline cycles for market m before, during and after the handoff, with fresh zero-age price inputs on the simulated clock. |
| Archive and retirement | PASS. The generated lifecycle worker woke on the fixture seal signal and verified archive data while B wrote. Retirement reverified exact coverage. Linux OS descriptor inspection held A while a separate history connection was open and allowed removal after it closed. |
| Protected data | PASS. All three snapshots retained their metadata and price references, outcome observation 90 remained linked, and foreign-key verification was clean. |

The focused run sampled 2,348,936 bytes across generated files. The exact
candidate also passed the bounded 4,000-write integrated regression and
archived 4,002 records including the legacy fixture backlog. The focused
fixture uses scoped collector connections and a generated seal wake and
mock transport. Production lifecycle scheduling, WAN throughput and rollout
remain separate qualification. Prior Linux crash recovery, scaled outage and
live Supabase byte-verification evidence continue to apply within their scopes.

### November 4 — minimum capacity measurement scope

Use the supplied VM sample of 46.38 GiB available disk and 1.25 GiB available
RAM. The prior 40 GiB fixture with a 10 GiB free-space floor is short by
3.62 GiB of disk. The 2 GiB available-memory prerequisite is short by 0.75 GiB.
These gaps apply to the full-window stress proposal.

The smallest evidenced sizing sample uses the existing 2 MiB main-plus-WAL
trigger and observed payload shapes. Run one normal handoff and one outage
case serially on the same Linux host. The earlier profile filled A with
1,710 events and generated about 0.75 MiB of compressed archive data. In
the outage case, run B to its size trigger with A held. In the normal case,
keep collecting while A archives and verifies. Instrument disk samples for
each DB, WAL and SHM, and for the archive and temporary working files.
Measure B's growth, per-object bytes and elapsed upload and readback, and
seal, verification, reader closure and removal timestamps separately.

Proposed small sample bounds are 64 MiB of total workspace, the existing
170-second work / 180-second deadline, and one CPU. The workspace plus
10 GiB free floor needs 10.0625 GiB at start, leaving about 36.32 GiB against the
supplied reading. For a three-process harness, bound collector/feature to
512 MiB AS and lifecycle/request child to 256 MiB AS each, plus 128 MiB
host headroom. The proposed memory preflight is 1.125 GiB available, leaving
0.125 GiB at the sampled reading. Those per-process sublimits and actual
free resources must pass preflight. The 64 MiB budget bounds the probe
and does not predict production workspace use.

The small sample directly measures generated overlap peak, a short-burst
archive/readback rate, reader hold and drain, and safe stop at the sampled
size trigger. Local transport can establish the disk and logic checks.
Real network throughput needs a separately approved synthetic upload scope.
The earlier 197-byte live probe supplies access and byte-verification evidence.

Extrapolate a preliminary window as the smaller of 72 hours and the usable
buffer bytes divided by observed raw-plus-index growth per hour. Estimate
outage runway from B's remaining usable bytes and time at failure, whichever
expires first. For normal overlap add sealed A, B growth over archive and
reader drain, core, WAL/SHM, working files and recovery reserve. For blocked
retirement budget both occupied slots and preserve A. For cutover add the
recorded retained legacy allocation as a separate term. Scaling these samples
to production needs sustained ingest and WAN measurements, core/evidence growth
and WAL peaks, and a bounded reader-drain distribution. Keep the production
ceiling open.

### November 5 — refreshed VM and approved serial capacity sample PASS

- Preflight at 07:26:02 UTC showed 49,801,564,160 bytes free and
  1,317,836 KiB available RAM. Revision d56b4a73ad6f1a10ba2bac928087cd5d85c6a42a.
  API, ensemble and lifecycle active with zero recorded restarts, retention
  and paid AI false and no AI key configured. Collector remained stopped
  at its legacy storage guard.
- One normal and one outage case ran serially from the standalone generated
  bundle SHA-256 2764daa0f08ac0245c8e687ca22d1c51ca66de42cad7e9f4eca637a246305cb7.
  It contains dd22009 protocol/verifier code and the committed capacity
  harness. Linux isolated imports passed before execution. The whole
  collector/archive process used a 256 MiB AS cap, below the proposed
  per-worker limits. Workspace cap was 64 MiB, floor 10 GiB, RAM
  prerequisite 1.125 GiB and outer deadline 180 seconds. Production health
  and service identities were checked about every two seconds during work.
- Normal case sampled 7,895,974 file bytes, with 13 B acknowledgements,
  0.1285 seconds reader close/retirement drain and 0.4215 seconds seal to
  retirement. Local archive wrote 781,446 bytes in 0.01962 seconds and
  read 1,562,892 bytes in 0.001101 seconds including retirement readback.
  This measures local transport. WAN throughput remains a separate gate.
- Outage case sampled 9,764,856 bytes. A's digest remained unchanged.
  B acknowledged 1,667 rows over 61.395 simulated seconds before the
  occupied-slot guard stopped another write with zero pending intents.
  A's active window was 63.013 simulated seconds at the 2 MiB trigger
  and the assumed 20 KiB/s payload clock.
- Both cases, preparation and generated cleanup took 74.197 seconds.
  Peak collector/archive process RSS was 41,590,784 bytes. Short-lived
  systemctl health-check child RSS was not separately measured. File peaks
  are sampled lengths, not continuous physical-allocation high-water proof.
  The code zip was outside the case directory. Adding its 139807
  measured bytes to the larger protocol sample gives 9904663
  observed file bytes including packaged code, below 64 MiB. No budget
  credit comes from reusable pages. No production DB was opened or copied
  by the capacity harness and no real cloud object was created or removed.

### November 5 — collector scheduler and throughput review

- Checkpoint 1 PASS and checkpoint 2 PASS are recorded in the preceding VM
  sample entry. Sample source 4f77aca uses the frozen standalone bundle
  listed there. Later capacity-harness maintenance adds a nonzero failure
  exit code, tested with an offline injected preflight failure. It does
  not authorize another VM sample.
- Checkpoint 3 PASS for the generated adapter integration. Exact candidate
  b44f31073cf191fc9657fe3f438e83c73e725f28,
  [CI 41987961035](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41987961035).
  The prior gap was rotation only at the next raw write. The collector event
  loop now polls the adapter's real age/size rule once per second, including
  idle buffers. The normal collector entrypoint test proves registration.
  Root Linux tests prove early A → B, clean restart retaining B's original
  clock, B → fresh A at 72h, acknowledged-row preservation, safe full-slot
  hold, and recovery at all three timer-switch transition boundaries.
  Existing process-exit tests still cover the underlying durable protocol.
- All exported suites passed:348backend tests,18root protocol tests,
  38root application tests and120controls. Root steps covered the relevant
  privilege skips. The exact exported integrated regression committed4000,
  archived4002, completed20featurecycles and reported0errors. The preceding
  full handoff evidence at6bbc659 remains applicable.
- The production API does not instantiate the A/B adapter yet. The reviewed
  cutover must supply it and bind the separate archive service. The timer
  change qualifies automatic sealing/rotation when the adapter is selected;
  the prior generated archive/readers test supplies its handoff safety
  evidence. It does not install a production archive wake or migration route.
- Checkpoint 4 READY FOR SCOPE REVIEW. Two exact generated gzip objects
  passed checksum, row and identity verification locally. Sizes623236 and
  623307bytes,1024records each, zero structured writes. Proposed one180s
  run,12HTTPattempts,two create-onlyPOSTs and8MiBaggregate body budget.
  Preserve both objects; no cloud cleanup authority requested.
  [Exact keys, checksums, identity binding and measurements](AB72_THROUGHPUT_REVIEW_2026-11-05.md).
- After measured WAN throughput is available, compute seal completion from
  upload plus authenticated readback, final verification recheck, CPU and
  reader drain. B's growth follows the measured physical growth during
  that interval. Full72hour and outage-runway estimates remain
  extrapolations and the production ceiling stays open.

### November 5 — approved two-object Supabase throughput PASS

- Used the exact d1ba17e keys, hashes and existing generated payload bytes.
  Executed bundle SHA-256
  51add9239c48cf8a952389af0fd1e8070a1ddc54987b9363d7bd7fc98ec1e8b3.
  Before each write phase, the bundle bound to the intended enabled lifecycle
  identity, PID31771, project xttdqeimdujweijxcuro and private market-raw bucket.
  Both POSTs were create-only and returned200. Both authenticated readbacks
  matched exact approved bytes, checksums,1024records each and identity boundaries.

| Object checksum | Bytes | Upload seconds | Authenticated body-read seconds | Verification seconds | Verified-readback seconds |
|---|---:|---:|---:|---:|---:|
|28c0282877c75f69fe999b140a056b1778f3f68c17f09b913e945c2c10465c8e|623236|0.735852|0.597421|0.050744|0.648165|
|b306398efaa4dcca11516325ac5fea1844da2e24fa2858a47c58650ded7845df|623307|0.711105|0.863325|0.048882|0.912207|

- Six Supabase attempts plus three local HTTPhealth checks, nine total.
  Upload body1,246,543bytes, Supabase response bodies1,247,197bytes,
  local health bodies10,140bytes, aggregate2,503,880bytes. Zero errors,
  zero structured rows. Probe operation4.401seconds; bundle staging,
  interpreter startup and SSH were additionally enclosed by the original
  180-second outer timeout. No HTTPretry was needed.
- API/ensemble/lifecycle were active before and after with identical
  PIDs31763/31767/31771 and zero recorded restarts. Collector enabled but
  runningfalse, errornull, storage guardlimit_reached before and after.
  Both exact object keys from AB72_THROUGHPUT_REVIEW_2026-11-05.md remain
  under the throughput subprefix. The earlier197byte object is also retained.
- Measured response-header arrival was0.362/0.489seconds on the GETs.
  First body-byte arrival was not separately instrumented. Rates include
  TLS/request latency; two small fresh-key reads do not establish a sustained
  WAN rate or a cold/cache distribution. Verification timed decompression,
  row parsing, identity validation and checksum proof.
- Slower observed upload846,958B/s (0.808MiB/s) and download721,984B/s
  (0.689MiB/s). For an extrapolation use the slower verification slope
  0.050744seconds/623236bytes. The earlier generated2MiB buffer produced
  781446compressed bytes. Its projected upload + initial verified readback
  + final verified retirement recheck + observed0.1285second close/removal
  allowance is about3.34seconds. At the assumed20KiB/s growth this adds
  about68,466bytes to B; using the generated gross raw/index slope of
  32.50KiB/s adds about111,262bytes. Core/WAL growth remains additional.
- A full72hour buffer at the20KiB/s planning input is5,308,416,000raw bytes.
  Reusing the small fixture's compression ratio gives1,978,035,188compressed
  bytes and about8,137seconds (135.6minutes) for the same projected path.
  B's added raw/index demand would be about159MiB at20KiB/s or258MiB at
  the generated32.50KiB/s slope. These are full-window extrapolations.
  The first-GET absence latency, manifest/checkpoint calls, larger-object
  throughput, burst rate, core/evidence growth, WAL peaks, and long-lived
  readers still need allowances or measurements. The observed0.1285seconds
  includes final local verification/removal and is not a worst-case reader
  lease bound. No production storage ceiling is established.

Remaining integration and cutover gates:

- The production API must select the A/B adapter and read factories, rather
  than its current legacy connections. Bind the real lifecycle/ensemble
  processes to core and generations, trigger sealed processing, and drain
  old raw handles automatically. Production retirement stays disabled at
  initial startup pending its own recorded enablement gate.
- Implement and qualify the bounded production-volume legacy import/audit.
  Current generated migration limits10000rows/128MiB cannot certify the
  actual legacy volume. Preserve exact IDs, embedded references and cloud
  cursors and fence the unaware legacy writer at the OS/service level.
- Qualify aggregate capacity including retained legacy, core, both roles,
  WAL/SHM, archive/TEMP and recovery. Bound outages by the active slot's
  remaining size and age, hold sealed data on missing proof, and stop safely
  when neither role is reusable. Sustained-load and full-window estimates
  remain extrapolations.
- Rehearse forward recovery after the first new acknowledgement, complete
  quick/FK verification within a reviewed absolute envelope, and bind exact
  release/export/CI, helper, configuration and database identities to the
  existing manual workflow. Existing2590sinterruption/180srecovery limits
  have not been proven sufficient for complete import and verification.
  Obtain the separately reviewed cutover approval and run its bounded
  API/feed/persistence/dashboard smoke before further production acceptance.

Private evidence contains sanitized result/provenance JSON only at
/Users/jake/Documents/ChatGPT/TradebotAnalytics/evidence/phase175-baseline/lifecycle-implementation-20261031/ab72-throughput-d1ba17e/.

## November 5 — real entrypoint integration candidate (CI pending)

Continued from ec5f396 on the existing working branch; intended PR base is
origin/codex/lightsail-deployment (78bcaf07baac8ba5f26a6c7dd827c35283511f30).
No existing PR was found. Production was not accessed or changed by this milestone.

Implemented default-off A/B routing in API collector/read/dashboard, ensemble
feature and lifecycle entrypoints. Existing independent discovery/serial feature
scheduling is preserved. Sealed generations wake incremental lifecycle archiving;
retirement is separately disabled by default. Durable draining plus cross-process
shared/exclusive reader leases permits idle connection refresh without removing a
reader's file. Exact protected body/checksum is checked against sealed raw twice,
including under the final core write transaction. Missing OS descriptor visibility
still holds retirement. External retained generated legacy files and sidecars enter
the aggregate accounting. Bounded inputs reject records beyond the 1 MiB envelope.

New generated tests exercise actual API startup, lifecycle wire adapter and seal
wake-up, default retirement hold, Linux descriptor drainage, duplicate lifecycle
ownership, process reader leases, restart from draining and changed protected body.
Linux-only cutover test fences an unprivileged legacy writer by ownership/mode,
injects migration failure before acknowledgement and raw-commit exit after a new
acknowledgement, and requires forward recovery with unchanged legacy bytes/FKs.
These are generated permission tests, not approval for production permission changes.

Local backend357 tests PASS (14 skips), controls120 PASS (3 skips), focused runtime
8 PASS (1 skip). Linux root/exported/integrated exact-commit CI remains mandatory;
Mac skips are not passes. A final read-only API ownership adjustment and Linux-only
timing instrumentation are included for CI verification. Existing production-scale
and hardware power-loss limits remain NOT PROVEN.

Release blockers remain explicit: actual legacy volume exceeds the unchanged
10000-row/128 MiB import audit and generated-only path guards; production capacity,
full verification time and retirement privilege are not qualified. The old pinned
application-only manual deploy route cannot ship this scope. No production ceiling,
16/21 GiB proposal, route, retention flag or retirement flag has been approved here.
Next: freeze this source, exact Linux CI, review existing-branch PR and record the
measured result/procedure without presenting those blockers as execution-ready.


### November 5 — first exact Linux result and corrected cutover fixture

Source636166091cac236c881777d7af68382fbc4c0cd9 CI41994499331 FAILED in
Linux generated cutover UID test. Exported backend passed; root raw18/application38/
runtime8 passed, including actual lifecycle drainage. Controls and integrated job
were skipped after the failure, not passed. The test incorrectly assigned old and
new writers the same UID despite a deliberately differently-owned legacy file;
connect correctly refused. Corrected rehearsal separates fenced old unprivileged
UID from root new-operator UID and restores sidecar ownership only before any new
acknowledgement. Production ownership checks remain unchanged. This does not
qualify running production as root. Successor exact CI remains required.

AB72_ENTRYPOINT_CUTOVER_REVIEW_2026-11-05.md records entrypoint/failure mapping,
reused capacity/cloud evidence, concrete cutover/recovery steps and exact blockers.
It is a STOP procedure, not an execution-ready production request. No source-volume,
capacity, deployment-control or retirement-privilege bypass has been introduced.


### November 5 — cutover fault assertion review

Review of the Linux-only rehearsal found that broad RuntimeError handling could
mistake an ownership STOP for the injected pre-commit crash. It now requires the
exact injected fault. After the denied old-UID probe, ordinary SQLite read/close
performs normal last-close cleanup before the new owner audit; no manual checkpoint
or sidecar removal. Main-byte equality is required. This is a changed regression,
not an unchanged qualification retry. Exact successor Linux evidence is pending.

## November 5 — PR9 exact CI and complete Phase1.75 reconciliation

Current integration milestone is **draft PR9**, working→existing deployment branch:
https://github.com/JakeMofa/Trading_Bot_Analytics/pull/9 . Frozen tested source
46f51e5f6501ee03e4021d725659aff2b53e84b5 exactCI41995105891 PASS (checked once):
Linux exported357 backend/10privilege skips, all covered by root18raw/38application/
8runtime/1cutover cases;120controls/zero skips; exact manifest check PASS.
Integrated4000 committed/4002archived/0pending/0errors;20 feature/publication cycles
(10each simulated market). Max save669.047ms/heartbeat749.106ms/feature206.834ms/
history24.237ms;22,162,054B sampled whole workspace/54,063,104B parent RSS/73.465s.
Generated fence/recovery0.8166s before-ack/0.8581s after-ack; this small root-new-UID
fixture does not authorize production root execution or qualify full verification.

Authoritative reconciliation below covers all eight integration/operational areas,
plus historical raw replay and deferred knowledge/RAG. Detailed P1.75.1–11 and
R0–R17 mapping, evidence and next actions:
[PHASE175_RECONCILIATION_2026-11-05.md](PHASE175_RECONCILIATION_2026-11-05.md).
“Satisfied” is limited to the named evidence, never an implicit production PASS.

| Area | Reconciled status / evidence | Next action |
|---|---|---|
|1. Actual application collector/LiveState/feature/baseline/ensemble/history/dashboard routing|Satisfied generated exact46f51e5; still open live production paths/volume|Qualify legacy import and reviewed deployment; current-market feed/persistence/prediction/dashboard smoke|
|2. Legacy identity/reference/evidence/cursor migration|Satisfied small schemas and generated before/after-ack fence; still open full recorded volume|Successor known-count import test, then supported full raw-volume/protected-fanout qualification|
|3. Automatic72h-or-size A/B rotation/archive/readback/drain/retirement|Satisfied scaled Linux timer/A→B→A/freshUUID/ack/crash/reader safety;08ce0d9/ec5f396 private byte access|Representative overlap/outage and actual new lifecycle manifest/checkpoint behavior; separate production retirement approval|
|4. Aggregate capacity, save/heartbeat/feature/query latency and throughput|Still open production ceiling/horizon; e58e3b5 VM normal/outage,46f51e5 scaled and ec5f396 throughput retained|Measure legacy+core+A/B+allWAL/SHM/TEMP/archive/recovery and burst/core growth; qualify finite outage runway; no16/21GiB adoption|
|5. Full verification/cloud recovery/hard deadlines|Satisfied scoped request/body/checksum deadlines and synthetic private readback; still open full recovery and verification timing|Complete source/reference/quick/FK/readback/recovery qualification; identify old1790.105s timeout check, no unchanged30min retry|
|6. Manual deployment scope, permission fence and forward recovery|Satisfied existing-route120controls and generated UID fence; still open full A/B controller/release|After earlier volume/capacity gates, adapt/test existing manual workflow/helpers for exact export/data/UID bindings and bounded interruption/recovery; retirementOFF initially|
|7. I7 independent discovery/market rollover/truthful health/fresh predictions|Satisfied source186s feature/boundary/replayed timestamp/stale/wrong-market guards; still open independent live acceptance and slow feature speed|Approved release, bounded smoke, then separately reviewed real-boundary/current-input freshness acceptance; unavailable slow features not freshness success|
|8. Operational visibility, outage/restart/recovery and sustained operation|Satisfied scoped API/cloud/dashboard telemetry/visible holds; still open live integrated visibility/multiple-cycle/storage stability|Validate active/sealed/backlog/drain/guard reasons and finite-outage recovery; reviewed sustained observation, no automatic soak/repeated restarts|
|Historical raw replay tooling P1.75.11|Still open, not superseded; bounded archive/reconstruction primitives exist, complete research replay does not|Generation-aware authenticated bounded replay, exact provenance/event ordering/no-lookahead/missing coverage and deterministic research tests|
|Knowledge/RAG tables|Still open, explicitly deferred to when RAG begins; not a cutover blocker|Hosted document/chunk/version/provenance/access schema and retrieval tests in its authorized phase; bucket/localFTS is not completion; paidAI/Phase2 remain deferred|

Original P1.75.1/.2 schema/client, .3 structured sync, .4/.5 archive format/private
verification and .6 telemetry retain historical PASS for their original scopes.
P1.75.7/.8 original backfills remain satisfied historical scopes, not complete
coverage of all subsequently collected legacy data. New-layout actual-volume/cloud/
live telemetry gates stay open. P1.75.10 new24h/sustained tuning remains OPEN.
Private backup/knowledge bucket existence is not recovery or RAG implementation.

**48h row deletion reconciliation:** November3 selected layout / November4 policy
clarification supersede old48h row expiry and the extra72h sealed wait.72h is the
maximum ACTIVE buffer age; size may switch sooner and reduce the local window.
Sealing starts archive completion/verification/drain immediately. Retire whole
sealed file only after exact authenticated coverage, protected/current inputs safe
in core, readers/handles drained; never overwrite a held slot. R5/R6 old row-delete
three-trial qualification and R8 row-delete application are superseded mechanisms
for this new layout, NOT retroactive passes. Preserve502.686ms and every old failure
under its original policy. Generated split gates do not change production controls.
R0–R4 historical correctness/baseline evidence retained; R7 recovery/full verification,
R9 post-retirement safety, R10 live health, R11 restart, R12 release, R13 automatic
lifecycle/R14 repeated cycles, R15 storage/R16 guard/R17 completion remain open new-
layout obligations. Backups/snapshots as a method are superseded by the no-copy
restriction; archive recovery/provenance/data preservation remain required.
FULL durability, exact identities, references, safe STOPs, no cloud hot-path writes,
bounded retries/ambiguous-write reconciliation and explicit approval gates survive.

**Importer successor:** explicit generated MigrationBudget retains defaults10000
rows/128MiB; known-count qualification explicitly60000rows with unchanged128MiB,
2GiB workspace/512MiB Linux-process/170s-work/180s-total, including preparation and
cleanup. One stable legacy snapshot covers audit/copy; deadline or changed main/WAL
binding before commit blocks complete publication. Larger row scope is not exposed
in production configuration. Local known-count fixture47907rows/54,710,364audit bytes
preserved1826markets/18289snapshots/27743predictions/20links/eight outcome bodies.
Exact structured hashes/core quick/FK/history passed; import8.624s,verify0.505s,
restart0.489s,total10.848s, sampled allocated161,271,808B/logical161,078,240B/RSS54,427,648B.
These development measurements precede final deadline/source-binding hardening;
exact successor Linux test is required. Initial Row-vs-tuple quick-check assertion
failed and was corrected; it was not evidence of SQLite corruption. No unchanged
large trial or production scan occurred.

**Ordered next gate BLOCKED at full volume:** retained legacy main+WAL+SHM is
5,369,184,256B. Current2,147,483,648B workspace is short3,221,700,608B **before** new
core/maps/indexes/WAL/working/recovery. Unknown full raw/evidence distribution stops
deriving a credible production ceiling or full verification time. Need an explicitly
supported larger generated envelope and eligible host with those additional terms,
not a sparse-file/repeated-tiny-fixture substitute. Old40GiB+10GiBfloor/2GiBRAM
proposal exceeds last VM46.38GiB/~1.257GiB by~3.62GiBdisk/~0.743GiBRAM; no run/
infrastructure/guard change. Per requested order, no new A/B deployment-controller
route is enabled or claimed qualified before importer/capacity/budget gates pass.

Path to Phase1.75 completion: exact successor CI/full PR review → supported full-
volume importer → aggregate normal/outage/migration capacity and complete verification
budget → tested existing manual controls → separately approved cutover/ceilings,
retirementOFF+bounded smoke → separately approved retirement/recovery/visibility →
independent I7 real freshness/rollover and reviewed sustained automatic lifecycle/
storage evidence; research replay remains required and RAG explicitly deferred.
Production remains held; no migration/deletion/restart/guard/manualWAL/copy/VACUUM/
cloud mutation/infrastructure/paidAI/Phase2. No expiry or consumed authority renewed.

The exact successor known-count profile additionally includes28 generated news
rows and validates FTS rebuilding; its source count and measured timing/bytes
come from that new Linux artifact. The local47907-row figures above precede that
addition and final deadline/source-binding checks, and are not substituted for it.
Local final backend361 tests PASS/14 Mac skips; controls120 PASS/3 Mac skips.

## November 5 — retained sealed legacy + fresh-B recovery route

User requested avoiding a full legacy import. Existing UNION reads were compatible,
but startup audited/mapped all legacy raw and used shared raw cursors. Added explicit
fresh-B mode: copy/audit structured history, point-select exact protected/current
inputs into core, retain legacy raw in place, start B with fresh UUID, preserve
single collector and B→A72h-or-size scheduling. New B-only incremental archive
cursors `archive:ab72:{observations,stream_events}` cannot be blocked by legacy
backlog and never advance legacy archive cursors. Legacy is never an eligible raw
registry generation; its retirement remains held. Active-buffer status states
sealed retirement hold and that full legacy verification was not performed by this
bootstrap. Missing/stale source data is not made fresh by copying it.

[Fresh-B recovery review](FRESH_B_RECOVERY_REVIEW_2026-11-05.md) records the exact
compatibility changes, finite guard proposal, startup configuration, verification
policy decision and remaining operator-control prerequisites. The former full-raw-
import prerequisite is superseded ONLY for this retained-legacy recovery path;
legacy full archive/reference/integrity checks remain required before retirement.
No full-import failure is relabeled or full legacy cloud coverage assumed.

New tests: generated20000 unrelated legacy raw rows remain in place; real runtime/
API/dashboard B, cross-legacy+B history, durable saves/current deterministic forecast,
protected outcome/price/metadata preservation, duplicate collector rejection,
independent B archive readback/checkpoint, failed readback holds, restart/mode/guard
binding and72h B→A UUID reuse. Four focused tests PASS locally. Tiny startup/function/
rotation ~0.048..0.052s, sampled aggregate allocated4,390,912B. Local full366 backend
PASS/15 Mac skips and120controls PASS/3 skips; later focused safety changes passed.
Exact Linux source/export CI must qualify the complete final candidate. CI's existing
4000-event ApplicationStore profile now explicitly exercises fresh B (4000new archive
rows, not4002includinglegacy), same limits and no substituted prior metrics.

Fresh Linux UID test uses unprivileged old AND new application UID against a
root-owned nonwritable legacy file under a root-owned sticky parent. The special
reader allowance is read-only/sealed legacy only; ordinary ownership/symlink checks
remain. Main/WAL binding adds UID/mode/device. This avoids requiring a root API and
preserves the old writer fence; before/after-ack crashes must recover forward in CI.

Required **proposal**, not applied: aggregate8GiB /MAX_LOCAL_STORAGE_MB8192, charged
for retained legacy5,369,184,256B +independent2GiB new-layout quota +512MiB recovery
=8,053,538,816B rounded up to8,589,934,592B. Additional core+sidecars cap512MiB,
filesystem floor10GiB, existing2MiB generation trigger. Fresh counters charge max
length/allocated blocks, including all sidecars/unlinked working files. Owner and
workers share bound guards; changing a guard on reopen is refused.8GiB is finite
recovery-only (proposed24h authority), not a permanent72h cap or measured worst-
case production peak. RetirementOFF means both new slots eventually fill and STOP.
No automatic extension/third slot, reduction of reserves, or legacy decommission.

Verified previous candidate7b5e327bd02cc81983e15a7332b3171111ff0dd5 /exactCI41998043241
PASS (once). Known structured fixture47935rows/54,715,760audit bytes; full-import
constructor25.264s/verification0.578s/restart0.556s/whole28.083s, allocated164,331,520B,
RSS46,358,528B. It does not prove new fresh-mode/full physical raw volume. Reuse as
structured compatibility evidence, not a second trial or a fresh host reading.

**Production command remains STOP, not a request to dispatch a nonworking template.**
Current exact pinned manual controller scope/baseline and generated-only production
path holds still reject the integration. Before an executable command can be
approved, review the recovery-only8GiB envelope and the explicit proposed check
scope (complete new core/B +exact targeted legacy bodies/binding, full legacy checks
pending/retirement held), then bind/test that route in the EXISTING manual host/
workflow with non-root UID fence, exact source/data/CI/expiry and forward recovery.
No new controller/service is proposed. Do not silently skip old complete-legacy
verification or invent a dispatch command that the existing controls cannot accept.
Production untouched; guard/flags/old authority/deadline unchanged. PR9 remains
DRAFT and all eight-area/replay/RAG/I7/sustained acceptance obligations stay reconciled
in PHASE175_RECONCILIATION_2026-11-05.md. I7/Phase1.75 remain open.

### Fresh-B exact Linux result and qualification-mode correction

ba7873c5a5b793dbdeb87d45ac31e7472442e353 /exactCI42004431809 PASS exported366backend
(11privilege skips all covered by root18raw/38application/8runtime/2cutover),120controls.
Fresh API/history/prediction/archive/guard tests PASS on Linux. Fresh permission test
actually ran old and new UID unprivileged: root-owned nonwritable legacy held under
sticky root parent; fence→recovery1.184s before-ack /0.736s after-ack, core quick/FK
1.011/1.560ms. Fresh small functional/rotation test81ms,4,390,912B sampled allocation.
No production operation occurred.

Artifact review caught that sudo dropped AB_QUALIFICATION_MODE: the4000-event report
explicitly said **full-import**,4002archives. That scaled profile remains PASS for
full-import only; it is NOT fresh-B qualification. Corrected the supervisor and
child to pass an explicit `--startup-mode fresh-b` argument and added a CI report
scope assertion (fresh-b/4000new archives/legacyHELD), plus a regression checking
privilege-boundary propagation. This is a changed scope diagnostic, not an unchanged
retry. Exact successor CI must qualify fresh4000; no prior metrics substituted.

Production dispatch still STOP at unreviewed verification scope and unmatched manual
controller/path bindings. Proposed8GiB recovery-only envelope is unapplied. Legacy
retirement and I7/Phase1.75 remain open; no expiry/authority extension.

## November 5 — PR9 fail-closed validation and joint qualification candidate

Reused f1729071e054e184504c3909f062a4a170cfe3a0 exactCI42005134684 PASS, confirmed
fresh-b/4000committed+archived/0pending/errors/20publications. Baseline max save120.775ms,
heartbeat305.908ms,feature95.297ms,history25.666ms;49.653s;22,285,660B sampled workspace.
This is not repeated handoff or production-scale acceptance. Candidate completion
is governed by [six-part qualification/cutover review](PR9_QUALIFICATION_REVIEW_2026-11-05.md).

Completed source safeguards: bounded startup schema/user/layout/feature versions,
core quick/FK and logical verification before reactivation; decimal/timestamp/JSON/
source/protected metadata+price comparisons. Atomic full-column raw acknowledgement
SHA receipts include original receive time and payload TEXT. New raw recovery,
application reads, fresh chart/archive and final retirement check those receipts;
derived source keys/UUID/PK/row counts are checked. Missing/malformed/conflicting/
corrupt data holds the affected activation/retirement and preserves files. Layout2
is explicit; older prototype cores without receipts hold, not reset/migrate silently.
Format-aware core write guards also fence older A/B adapters before registry mutation.
No production A/B core has been created. Exact legacy monolithic import stays supported.

Six focused corruption regressions PASS, plus existing conflict/cloud/quota/crash
coverage retained. Added real-process reused-slot exits before/after preparing-file/
active publication and full acknowledged/archive/reference recovery checks. Local
full376backend PASS/17 Mac/platform skips,120controls PASS/3skips, followed by focused
schema/reference guards. Exact Linux/root/export CI must qualify final source.

Joint generated fixture now covers B0→A1→B2→A3 (includes requested A→B→A), actual
collector save/discovery functions, real1s size scheduler, serial feature loop,
real loopback FastAPI/HTTP/SSE/history and isolated lifecycle CLI-builder process
with SupabaseHTTP MockTransport. SSE includes current generation and changes on
rotation without requiring a price event. Measures save/ack interval/heartbeat,
API/SSE/current-price/feature/history and sealed allocation. Synthetic transport,
simulated market boundary/feature wakeups and deliberate input pauses are explicit;
no real venue cadence/window claim. Linux global FD proof is mandatory, not Mac-mocked.

Review found a safe both-slots STOP under cold structured work and moving-active
archive catchup. New sealed/drain token gets one urgent sealed-only archive cycle;
structured work remains due, stable reader holds cannot starve it indefinitely.
Active backlog remains explicitly not caught up; archive_scope=sealed_generations.
No threshold, durability, deadline or storage gate was raised to erase the failure.
Harness thread-ownership/hard-request isolation errors were corrected with a fresh
lifecycle process; Mac diagnostic then correctly stopped at unavailable Linux FD proof.

Qualification cleanup scope corrected: previous elapsed times did not cover fixture
TREE deletion. New actual cleanup follows ordinary closes/owned-child drain and
complete descriptor check inside original180s process-family supervisor; unknown
visibility/open owners retain fixture and fail. Records core logical growth/event,
normal-close main size, receipt count and actual cleanup; no physical-free-page credit.

Operating limits stay separate: recovery-only8GiB aggregate proposal (unapplied),
retained legacy5,369,184,256B +2GiB shared new-layout quota+512MiB reserve,512MiBcore,
64MiB per-slot admission stop,2MiB TEST/early rotation trigger,10GiB FS floor; one
bounded transaction can cross admission thresholds. Initial retirementOFF means
finite two-slot collection then STOP. Continuous lifecycle requires a separately
qualified NEW-generation retirement gate, measured archive/drain<WAL+raw fill time,
core/receipt growth horizon and restart audit time.2MiB is not a72h local-window or
per-slot physical bound; under saturated small writes/WAL it can fill much faster
than the extrapolated63–102s/slot from earlier raw/index slopes. No permanent16/21GiB
ceiling, cap expiry extension or continuous acceptance is claimed.

Redis recorded DEFERRED for later evaluation against measured price/history query
bottlenecks; no Redis/cache/dependency/service/writer coordinator added. PR9 remains
DRAFT. Concrete STOP procedure preserves existing manual workflow/2590s interruption/
180s recovery/10s reap, exact source/data/config/UID/expiry bindings, nonroot legacy
fence, core/selected-input verification and forward recovery after any new ack.
Production path/control scope and targeted-verification policy remain unresolved;
no nonworking production dispatch command is presented as executable. Full actual
structured/selected cardinality (including candle history), per-slot/aggregate/WAL/
core growth, actual verification budget, cloud recovery, I7 and sustained evidence
remain explicit gates. All eight-area/replay/deferredRAG/48h→72h obligations remain
reconciled. No production mutation, cleanup, copy/snapshot/VACUUM/manualWAL/restart/
guard change/cloud write/infrastructure/paidAI/Phase2 occurred.

### Joint CI792e3db: truthful-health fixture failure; corrected market timeline

792e3db6d8d7b54965af3571e0f193f7371261e1 /CI42087680062 FAILED at the joint HTTP
health assertion. Exported validation/backend and root18raw/38application/9runtime/
2cutover passed; reused-slot crash recovery also passed. The joint first handoff/
reader drain/archive/retirement completed, then health correctly returned degraded
for missing Polymarket quote. The fixture accidentally overlapped new m0 and legacy
m in the identical15m interval; current-market selection retained legacy m and RAM
correctly rejected m0 quotes. No application health criterion was relaxed.

Corrected fixture starts new m0 a day AFTER legacy m, asserts quote acceptance and
HTTP market/quote identities/advancing price, and uses one coherent simulated clock
for public feed-age reporting. HTTP maxima/count/timeouts now cover every GET.
This is a changed fixture, not an unchanged qualification retry. The earlier failed
run remains failed, and full4000 successor qualification did not run after that gate.
Source/layout/receipt safeguards are unchanged from792e3db; exact corrected Linux
CI must pass all stages before qualification is claimed. Production unchanged.

### Protected evidence identity review follow-up

Startup now rejects missing required evidence and evidence whose generation, dataset
or row identity differs from its committed event, even when the altered body has a
valid self-checksum. Generated missing-proof/recomputed-hash faults preserve legacy
and raw files and block activation. Focused7 PASS; full local backend377 PASS with17
platform skips, controls120 PASS with3 platform skips. These skips require Linux/root
evidence; local descriptor timing is not production retirement proof. Source changes
require their own exact Linux/export CI;96933e0 joint CI was running at review.
Production and unapplied recovery/continuous budgets remain unchanged.

### PR9 consolidated generated checkpoint —96933e0 PASS;79527a7 exact CI pending

Corrected source96933e099c7648dd996ad197e47ea8f85c09d519 /CI42088519393 PASS all
exported/Linux/root/control/known-count and integrated jobs. Joint B→A→B→A passed
with4 UUIDs,25acknowledged ticks,3readback/reader-hold retirements,59HTTPrequests,
0timeouts/errors,onefeatureworker. Maxsave27.601ms/heartbeat126.567ms/API74.608ms/
SSE163.838ms/price0.929ms/feature29.318ms/history47.132ms;sampledpeak10,420,224B.
Exact fresh4000:4000committed/archived/receipts,0pending/errors,20publications;
save77.795ms/heartbeat256.458ms/feature495.372ms/history197.571ms,peak22,630,293B,
53.150s including fixturetreecleanup. Corelogicalgrowth485.376B/event persists
afterrawretirement;not a capacity credit. Known-count47935rows fixturePASS,
164,548,608Bpeak,34.115stotal,restart2.735s;actualcandles/protectedfanoutunproven.

Successor79527a79f40154ab589d446119be5cd60da65ad9 binds protected evidence to exact
committedgeneration/dataset/row and rejects missingrequiredproof. Local377backend/
120controlsPASS(17/3platformskips),7focusedfaulttestsPASS. ExactCI42089343842 was
in_progress at the one check; no repeated polling/retry. Do not call795 qualified
until its Linux/export jobs pass. PR9 remainsDRAFT. Six-part report records schema/
handoff/crash/concurrency generatedPASS,operatinglimits/productioncontrolsNOTPROVEN.
Full diff166files/+23811/-208 includes historicalwork,not a narrow3file release.
Concrete cutover remainsSTOP: actualstructured/selectedscopeinclcandles, finitecore
ledgerhorizon/expiry, reviewedtargetedverification/capacity and testedmanualscope/
permissionbindings needed. Preserve2590s interruption/180srecovery/10sreap, initial
retirementOFF,forwardrecoveryafterack. No executableoldworkflow substitution.
No productionmutation/cloudwrite/guardchange;I7/Phase1.75OPEN.RedisDEFERRED.

###79527a7 exact CI failure diagnosed: descriptor process-exit race

CI42089343842 FAILED integrated profile at cleanup/accounting with Linux ESRCH
(ProcessLookupError) on /proc/2970/fd/26. It is not a protected-evidence mismatch;
20featurecycles completed,save60.592ms/heartbeat268.659ms before the failed gate.
Exited-process ESRCH is now treated like ENOENT in descriptor accounting/cleanup;
permission-denied and unknown visibility still fail closed. Focused8 testsPASS
(1Linux-onlyskip); injected ESRCH and PermissionError distinguish both outcomes.
Successor exact CI required;795 remainsFAILED. Production untouched.
Actual-input inventory read stopped at SSH trusted-host-pin check; no host key
was accepted implicitly and no production query/mutation ran. Offline work continues.

### PR9 actual source gate: missing protected metadata, not a storage-only blocker

Pinned strict SSH/read-only evidence: seven structured tables125410rows/71927188
bodybytes;58812candles/18692referenceprices;18268distinctmetadata/17924streamrefs
=>at least161602selectedauditrows. Indexed reference check0.41986s found snapshots
1–5 reference ABSENT observations25,28,30,33,36. STOP;no repair/reclassification or
productionmutation. Actual input qualificationFAIL;budget and manual cutover remain
NOTPROVEN/BLOCKED. See PR9_ACTUAL_INPUT_GATE_2026-11-05.md for all exact evidence,
bounded diagnostic failures, numeric finite admission proposals and recovery gate.

Offline: census fails early on missing evidence;selected raw rows now count in audit;
explicit150000-row generated scope within unchanged128MiB/170swork/180stotal/2GiB/
512MiBprocess (defaults unchanged) is still BELOW real161602+ scope,not a pass.
Actual-count/shared-reference fresh-B profile125412rowsPASS24.066s,235360256Bpeak/
52740096BRSS;actualfanoutNOTPROVEN. New100000-event ledger cap stops growth,core
512MiB remains independent;all production flags/limits unchanged. Local382backend/
120controlsPASS with17/3platformskips;focusednewchecksPASS. ExactLinuxCI required.
Smallestnextaction: review exact-archive recovery of missing metadata and complete
missing-reference census;unavailable originals require explicit policy review.
Do not implement a production route that accepts this failed source. PR9DRAFT;
I7/Phase1.75OPEN;old verified rotation/latency evidence preserved;RedisDEFERRED.

23aa5d2398ac499b37807dff24b27fc17653b79b exactCI42094968368 PASS: exited-descriptor
fix qualifies protected-identity successor after795failure. e42d783 adds actual-input
accounting/scope/ledger preparation;final regression explicitly proves selected raw
inputs consume SAME row budget and activation preserves source on overflow(4PASS).
The live absent-protected-metadata failure remains a releaseSTOP;CI cannot erase it.

### Final exact candidatecff60e4 /CI42097085311 PASS;actual input authority gate remains

Frozen cff60e40e69cfa86599fb082c3bce5b3c041757b exactLinuxCI42097085311 PASS both
exported jobs/root/control/manifests. Actual-count/shared-reference profile125422
auditedrows/65697614serializedB,constructor49.546s/restart3.067s,total56.128s,
205860864Bpeak/RSS45531136B. Still NOT actual reference fanout. Fresh4000committed/
archived,0pending/errors,20cycles;save52.106ms/heartbeat271.185ms,22887503Bpeak,
55.497s,RSS56102912B. Source rowcap150000 remains below161602+requiredidentities.

Complete bounded metadata census7.034s:6755of18268requiredIDs absent. Stream
reference census5.981s:6493of17924absent. Existing local pre-retention file (read
only;NO copy created) contains ALL13248missingrows. Selected point verification
2.454s matched metadata market/receipt time/kind and stream source time/exactprice,
0mismatches. Canonical selected bodies30868806B(26297384metadata+4571422stream);
selecteddigest ee2a7f4b4b05135369f7adb01ba92465299fa083bc603c32b4a057911e5364e9.
No production restore/recovery artifact/cloudwrite was made. Matching references
is not independent archive/source-authority verification;do not silently bless a
historical backup or weaken the missing-input requirement. Need review of this
exact recovery source and a verified selected-row recovery capsule/core bootstrap
route before release controls can accept this database. Currentlegacy-only route
FAILS intentionally;new production dispatch is NOT execution-ready.

Fresh read-only stat:retainedDB/WAL/SHM accounted5369184256B;FSavailable49796276224B.
Unapplied8GiB/2GiBnewlayout/512MiBcore/64MiBslots/512MiBrecovery/10GiBfloor and
100000-event ledger cap are finite admission proposals,not sufficient-runway proof.
All I7/cloudrecovery/visibility/sustained/replay/deferredRAG gaps remain OPEN.
PR9DRAFT,productionunchanged. Exactcutoverapproval is not requested while source
authority/input verification fails. Existingmanualcontrol2590/180/10 budgets stay.

### Approved independent historical-source verification and selected staging

User authorized read-only candidate-source verification and isolated selected-row
staging only. No production repair/cutover authority. Independent source:1983184896B,
SHA256 a7edbb886d71d4690d608d915a975fe43c1ff9d194cb1c7dd54fdbbfa90787a6,
user_version0,fullintegrity_check ok/zeroFKviolations,schemaidentity
a88b290dd84c4718226dbffcd9ee7c962860d26a4437f4f07c927be90aed852b,2.910s.
Fresh stopped-legacy dependency manifest binds6755metadata+6493streamrows,6776
snapshot/6745predictionreferences and legacyfileidentity;checksum
8e8473f444983419d60e2004ca2e7c41d89657f6767fe691d36e8e1a5003eb61.

New default-off verifier/stager pins source/dependency hashes,complete integrity/FK,
rawschema/PKs,exactbodies/decimals/time/market/target/reference checks;transactional
selected-stage/app-compatible pinmaps and actual supporting-market schema. Full
application bootstrap/production routing remains disabled/unproven. Seven generated
faulttestsPASS;local390backend/120controlsPASS(17/3platformskips),followed by7PASS
after supportingmarketDDL hardening. ExactLinuxCI and one actual-data exported
qualification stillrequired. Whole170swork/180stotal/2GiB includes existing source,
dependencies/export/staging;512MiB Linuxprocess. No copies of source/database;the
selected-row stagedcore is the explicitly authorized recovery artifact.

66c9c09 first exported actual recovery launch FAILED before verify/stage: missing
build_ab_candidate import path. No selected data staged. Added bundled backend
path plus clean-directory/PYTHONPATH-empty subprocess qualification proving exporter
and actual runtime dependencies are shipped.8focused testsPASS. The first minimal
clean test exposed its own omitted app modules; copying source app modules only
fixed the test package;no dependencies installed or candidate checkout import used.
Corrected exact candidate/export/CI required before actual selected-stage result.

### Selected recovery PASS in isolated stage;production authority unchanged

Exact-export b8786e001c5c3f8757838e4d0c523c72cc3ca1a5 verified/staged all13248rows:
6755metadata/6493stream,0conflicts/unverifiable,6776snapshot/6745predictionproofs,
369real supportingmarkets. Fullsource/stageintegrity andFKPASS,FULLsync2,retry0
changes.5.596s,RSS102940672B,peak2142367108B INCLUDING existing1983184896Bsource/
export/dependencies/allstagefiles:only5116540B below2GiB. Mac actualdata PASS,not
Linuxactual-volume proof;512MiB Linux AS capnotapplied onMac. Selected manifest
canonicalSHA cce959118eb774d8131a8bd60876bcd2f3f16c1a8d90c086621dfe6c1dd1c208;
fileSHA9577e6f53d2150f107eb7fd6914a0dc93ab7d806d52f04a230347332765ff07b. Private
reviewartifacts /private/tmp/generated-ab-recovery-s1r_pa53/;not staged ingit.
Futurestream13248rows/32552271B/SHA01f3ce94b62f3f91690b33e5aa4721de6ac6c22635d91b7c71dea7c0e689061c
computedwithout writing/transferring streambody. No production repair/cutover.

See SELECTED_RECOVERY_REVIEW_2026-11-05.md forexactsource/dependency/selection hashes,
qualificationlimits and concrete STOP productionprocedure. FullAppStore bootstrap/
streamconsumer,actual161602+scope/bytebudget,manualworkflowbindings andnumeric
productionlimits remain unqualified. NinegeneratedfaulttestsPASS includingactual
process exits before/after commit;priorlocal390backend/120controlsPASS(17/3skips).
FinalLinuxCIrequired;toolsbyteidentical to b8786e0,only extra faulttest/docs follow.
Userapprovedcandidateverification/stagingonly;no production useapproval requested
whilefullbootstrap/controlgates fail. All I7/Phase1.75/replay/RAG gaps remain OPEN.

### Selected recovery final checkpoint: dataPASS;exactreleaseCI latencyFAIL

Frozen1547a433590eb6b41c3d93f6018d9d033cb5f21c /CI42121991450 FAILED existing
raw4000 profile:save727.764ms/heartbeat1165.206ms vsunchanged<1sgate,4000archived,
43.474s. No unchanged retry/gate relaxation. raw_generations/qualify_ab/test_raw
modulesbyteidentical to cff60e4;stallcauseNOTPROVEN,not blamed onhostornewrecovery.
Exactexport backend392PASS/13rootprivilegeskips;all9selectedrecoverytestsPASS on
Linux,includingcleanbundle andbefore/aftercommitprocess exits. Rootraw18ran with
1latencyfailure;remainingrootapplication/runtime/cutover/joint,controls/knowncount/
fullintegratedjobsdidNOTcomplete. Priorpassingrotation/latencyevidence retained,
not used to relabel this failure. Local120controlsPASS;currentCIcontrolsNOTRUN.

Actual13248-rowstagePASS used b8786e0tools;verifier/runnerblobsexactlyidentical in
1547a43. Complete source/stageintegrity/FK,allprovenance/refs/exactdecimals/IDs,
0conflicts/unverifiable,retry0changes remain scopedPASS. Aggregate2142367108B
is samplednamed-file accounting inclsource/exports/deps/stage;anonymousTEMPpeak
andactualLinuxvolume remainNOTPROVEN. Only4.88MiBobservedmargin,nofullcapacitypass.
See SELECTED_RECOVERY_REVIEW_2026-11-05.md forexactprivate manifest andproposed
productionprocedure with STOP before source-use/fullbootstrap/manualscopeapproval.
No repair/deployment/capchange/newauthority requested. Nexttechnicalgate:bound the
heartbeatstallcausebefore another qualification;continuefullcapsule/coreconsumer
preparationunderseparatereviewedfull-scopebudgets. Productionunchanged;PR9DRAFT.

### Heartbeat evidence-first correction and durable recovery attestation

Historical1547/CI42121991450FAIL unchanged. Setup precedes oldheartbeat;syncsave/
archiveblock mainloop. Original maxima cannot locate the1.165s window orapportion
CI/IO/contention. MatchedCPython3.12.16source+virtualclockscheduler reproduce1.2s
heartbeat from four0.4s units withsleep(0),noOS contention. Explicit handoff only
to ALREADY-DUE heartbeat reduces virtualmax0.4s with0pacing delay,samework/1sgate.
New boundedphase/ordinal/threadCPU/schedstat/pressure diagnostics retainworstwindows
andcounteroverhead;failureJSON persistedbeforeassertion/uploadalways. No production
instrumentation,SQLitepolicy/thread/batch/resource/gatechange. Threefocusedtiming
checksPASS;local396backend/120controlsPASS(17/3skips),thenfocusedcounterhardening.
Changed4000Linuxprofile inexactCI is required;no unchangedretry/matrix launched.

Exactrecoverymanifest9577e6f53d2150f107eb7fd6914a0dc93ab7d806d52f04a230347332765ff07b
preserved/fsynced inprivateignoreddata/recovery-evidence/selected-2026-11-05-v1/
withdependencies/reports/index. NO databasecopies. Sanitizedtrackedattestation
docs/PLAN/evidence/selected-recovery-2026-11-05.json bindsprivatehashes andactual
verifiedreport,redacts paths/inodes/per-rowIDs/bodies. Source-use/productionauthority
unchanged. See HEARTBEAT_DIAGNOSIS_2026-11-05.md. Fullbootstrap/controlqualification
continues onlyafter exactCI passes;allunrelated edits preserved.

###8bb945a exactCI42126289598 PASS;first gate cleared without changing1s policy

Changedrawprofile4000committed/4000archived,PASS_SCALED,save63.442ms/heartbeat
101.381ms,14.309s,setup12.303ms;heartbeatstarts12.691ms beforefirstsave.269due
timerhandoffs,totalwait17.159ms;4031timedcalls,counteroverhead37.101ms(~0.26%).
Worstwindowmainoverlap101.117/101.381ms,threadCPU98.186ms,chieflyresidualarchive
94.033ms/92.746msCPU;tracecomplete/nottruncated. Currentwindowdominatedbysync
applicationcompute,notfixture_setup. Kernel schedstatsdisabled:ownrunqueuewait
UNKNOWN. Cgroupquota-throttlecounts0,butIOpressureexistsandcountersmayincludeothers.
Historical1.165s windowstillunattributed;oldFAILnotrelabeled. No performancegain
claimacrossdifferentCIhosts. NewexactCIcompletepassedallrequiredjobs.

Sanitizeddurabletiming evidence docs/PLAN/evidence/heartbeat-8bb945a.json;exact
privaterecoverymanifestnowpersistentdata/recovery-evidence/selected-2026-11-05-v1/
(original9577SHAunchanged),withsanitizedgitattestation. NoDBfilescopied. Proceeding
fullgeneratedbootstrap/capsule-consumer/controlqualification underexisting physical/
RAM/time/safetycaps;productionunchanged. Newowned-FD allocationmeasurement and
selectedcapsuleinputcodebeingprepared;notyetqualified/committed.


### November 5 — selected recovery full bootstrap candidate

Heartbeat8bb945a/CI42126289598 PASS preserved. See
[full bootstrap evidence and remaining release gates](PR9_FULL_BOOTSTRAP_2026-11-05.md).
Actual bounded inventory17tables/189576 structured rows requires225777 audited
inputs; explicit generated250000rows/256MiB logical, original2GiB/512MiB/170s/180s
host limits unchanged. First bootstrap FAIL timestamp schema assumption; corrected
field-specific epoch validation. Changed local full bootstrap PASS81.828s,peak
1079271424B,RSS178372608B,all structured exact,13248 selected rows,legacy unchanged,
new ack preserved across restart. Linux/exact candidate qualification PENDING.
Persisted logical core quota/layout3; private exact capsule durable, sanitized
attestation committed; owned Linux family/unlinked TEMP measurement implemented.
Production independent-service allocation, post-quiescent binding, complete legacy
verification and manual scope/identity controls remain NOT PROVEN. No production
command is approved/executable; production held,PR9DRAFT,I7/Phase1.75OPEN.


### November 5 — full bootstrap Linux cleanup prerequisite correction

53d8582/CI42134362083 FAIL: full225777-input bootstrap/reference readback/new-ack
restart completed; final cleanup proof required Linux root but CI launched ordinary
user.155.732s,peak1022902272B,RSS134549504B; failure preserved in sanitized evidence.
Successor uses existing generated-only sudo descriptor mechanism; early preflight
holds before allocation if visibility missing. Focused2PASS. No gate/limits change.
Exact successor CI required. PR9 stillDRAFT;9deployment-base conflicts; manual
production controls/verification/identity/allocation approvals remain held.


### November 5 — frozen selected-recovery full application checkpoint PASS

f7820026e78528dd1c1f4413dc2a62740b2711a7/CI42135084876 PASS exact Linux/export.
Backend413/13privilegeskips all root-covered;controls121/0skips;root descriptor/
UID/crash/reused-slot/joint proof PASS. Full225777-input bootstrap112.185s,peak
1022881792B,RSS134221824B,all17structured exact/13248selected/legacy unchanged/
newack forward recovered. Integrated4000committed+archived/0pending/errors,20
publications,save134.675ms/heartbeat293.014ms,36.964s. Jointrecovered-input
B→A→B→A PASS,save165.5ms/API192.8ms/SSE254.6ms;ackinterval1177.1ms includes
intentionalfixturepauses,individualgapcause/livecadenceNOTPROVEN.
See PR9_FULL_BOOTSTRAP_2026-11-05.md and sanitized evidence. Private exactmanifest
andcapsule durable;source historicalorigin attestation stillNOTPROVEN. Finite
corelogicalquota250k/256MiB qualifiedgenerated only;physical/host/time gates unchanged.
Production manualscope/expiry/post-quiescentbinding/fullverification/independent
service allocation/fullrawcapacity and9mergeconflicts remain open. No approval
request before technical readiness;no production change. PR9DRAFT,I7/Phase1.75OPEN.
