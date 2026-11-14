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
- **CP0 PASS; CP1 foundation PASS within generated scope.** Source `40c2761`
  passed exact push CI [43340827516](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/43340827516)
  and PR CI 43340834244. Existing PP runs Docker 29.9.3, Compose 5.7.1 and pinned
  PostgreSQL 17.12. All 32 rows persisted across recreation; four restricted-role
  checks passed. Smoke 32 KiB, cluster allocation 48,205,824 bytes, sampled memory
  18.13 MiB / 512 MiB; no published port. CI rejected injected column drift.
  [Sanitized evidence](evidence/pp-postgres-foundation-2026-11-12.json).
  CP2–4 generated source and CP5 actual PP application deployment now PASS in
  generated-only scope. See the latest CP5 result below; the failed first
  attempt remains historical evidence, not the current runtime state.
- Production is untouched by this milestone. No new production health/collection
  claim is inferred from GitHub CI. Last recorded collection was storage-held;
  retention and paid AI were OFF.

### Parallel implementation authorized — November 12, 2026

The user authorized CP2–5 as separate feature branches and one consolidation
branch. Base: preprod `3031554`, exact merge CI 43342088466 PASS. This changes
work ownership, not checkpoint acceptance or production authorization.

| Workstream | Feature branch | Owner / scope |
| --- | --- | --- |
| CP2 | `codex/pg-schema` | Schema agent: migrations, checksum/drift contract, exact values/references |
| CP3 | `codex/pg-application` | Application agent: PostgreSQL adapter, calculation/API/SSE/dashboard, app image |
| CP4 | `codex/pg-lifecycle` | Lifecycle agent: switch/seal, outbox/archive/readback, reader drainage, history |
| CP5 | `codex/pg-preprod-deploy` | Coordinator: runtime Compose, restricted PP deployment controls, integrated CI |
| Integration | `codex/feature-postgres-pp` | Coordinator: review, dependency integration, README/master/handoff, PR to preprod |

Workers have isolated code worktrees from the same base. Original dirty checkout
remains untouched. Shared schema/interfaces must be agreed before consumers
implement SQL; schema owns that contract. No worker may silently amend another
worker's ownership or loosen a gate. Component PRs target the integration branch;
CP2 merges before consumers, then CP3/CP4, then CP5 controls after integrated tests.
The consolidated branch targets preprod only. Successful source builds do not
qualify the host controller or authorize live feeds, Supabase DDL/writes,
production changes or retirement. A failing dependency stops its dependent
release stage, while independent offline work may continue.

Each component records tested scope and gaps; no repeated CI polling or unchanged
failed-trial reruns. Manual PP application deployment follows CP5's executable
qualified route with generated data, collector/cloud/retirement OFF. The existing
2 GiB PP VM and 64 MiB generated-data foundation allowance remain the initial
limits; record any additional bounded runtime resource proposal before use.

### CP2–5 generated source integration qualification — historical source checkpoint

Component PRs [#18](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/18)
(schema `77eb698`), [#19](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/19)
(application `cdc7e34`) and [#20](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/20)
(lifecycle `c0b2cc8`) are merged into the integration branch only. The combined
source `751f1f8` passed exact Linux CI
[43346308984](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/43346308984):
16 schema and 35 application/lifecycle tests, **zero PostgreSQL skips**, plus a
built runnable container and actual generated API/SSE acceptance.

The isolated runtime committed 21 generated events, rejected conflicting replay,
preserved exact decimals, published prediction history and served two SSE
connections. Maximum sampled API request 2.995 ms; complete qualification
55.835 seconds; generated relations 1,867,776 bytes, database 10,565,299 bytes,
WAL 16,777,216 bytes. These are tiny generated measurements, not host/capacity or
live-market acceptance. [Sanitized evidence](evidence/postgres-integrated-generated-2026-11-12.json).

Earlier integrated failures remain recorded: `1aa8001`/CI43345696255 rejected
migration-role access before explicit owner activation; `92f25fd`/CI43346090808
passed database suites then failed the malformed Compose tmpfs mount. Both had
specific fixes; no gate was weakened or unchanged failed run retried.

CP4 now proves generated A/B switching, current B writes during A verification,
reader/protected-reference holds, real partition removal and archived API/history
retrieval afterward. Runtime cloud transport and retirement remain OFF. The
private `history_v2` file is a contract only, not applied Supabase DDL.

CP3 is the generated adapter/dashboard/baseline-calculation milestone, not full
production parity: live feeds, production preview, ensemble/news/evaluation and
outcome display remain explicit follow-on work. CP7 must measure capacity,
core/dedup/acknowledged-outbox growth, sole-collector ownership and real rollover.

CP5 [PR #21](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/21) owns the
required combined CI job, runtime Compose and host deployment/recovery controls.
Its source/controller qualification now passes as recorded below; actual host
bindings and manual deployment remain unperformed, so target flags remain disabled. Proposed
normal runtime caps total 1 GiB (PG512/API192/calculation192/lifecycle128 MiB),
with a separate 192 MiB explicit migration container before app startup.
Generated PP smoke evidence cannot authorize production promotion. The existing
PP foundation and production are unchanged by this source milestone. Integration
[PR #17](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/17) remains draft
until its own combined exact CI and review; preprod has not yet received this stack.

### CP5 controller qualification — November 13 UTC

**Final source qualification PASS:** `deb8f0d` passed exact push CI
[43351324325](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/43351324325)
and PR CI 43351333800, including the descendant-cleanup regression and required
Linux-root SSH permissions case. [Final generated evidence](evidence/postgres-controller-final-generated-2026-11-13.json).
PR #21 merged into integration at `87576fd`. All four component PRs #18–#21 are
now integrated; PR #17 is the reviewed route to preprod. Its own exact merged
source CI is still required before that merge. Actual PP helper/identity/runner
installation and the first manual generated deployment remain CP5's next steps.
No host runtime qualification flag, production configuration or cloud permission
changed as part of these merges.

Source `e402a8c` passed exact push CI
[43350188521](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/43350188521)
and PR CI 43350197910. Actual controller stages, API restart, one-use rejection
and forward-preserving recovery passed in 121.842 seconds, with the Linux
permissions test executed as root. Twenty-one generated events were acknowledged;
maximum sampled API request 3.585 ms. [Evidence](evidence/postgres-controller-generated-2026-11-13.json).
This proves the tested generated scope only. Subsequent review identified a
process-group cleanup edge case when a child leader exits before its descendant;
the narrow fix and regression required successor CI before installation.

The Linux controller now exercises the actual pinned PostgreSQL runtime,
explicit migrations, API/SSE smoke, API restart and forward-preserving recovery
in disposable CI. Only CI host identity is substituted. Both deployment target
profiles remain disabled until actual operator/SSH bindings are qualified.

Earlier controller runs are preserved as failures: `9fc68c2` / 43348103458
rejected the newer `ubuntu-latest` host; `a6d35f8` / 43348320613 rejected Compose
config without its inactive migration profile; `699cf20` / 43348745820 rejected
Compose's normalized absolute secret targets. The matching Ubuntu 24.04 runner,
explicit inspection of the migration profile and strictly equivalent secret
paths address those evidenced failures. Full normalized Compose validation was
also exercised locally, not only the individual failed field.

A separate operator review found the root-owned authorized-key files were not
readable by the dedicated SSH identity. Their corrected modes retain root-only
write authority while permitting authentication; Linux effective-UID tests are
required before installation. No VM change resulted from these source fixes.
The final successor result above qualifies the generated controller code;
actual PP host bindings remain a separate requirement. [Generated PP release procedure](../../deploy/preprod/RUNTIME_REVIEW.md)
keeps installation, binding evidence and the first manual deployment separate.

### CP5 actual PP bindings qualified — November 13 UTC

PR #17 merged into preprod at `ed46314` after combined source `687861e` passed
exact push CI 43351856515 and PR CI 43352101956. All four component PRs are
consolidated. The application has **not** been deployed by that merge.

The exact CI-passed `687861e` helper source is installed on the existing PP VM;
its controller SHA-256 is
`56de886e023e65ccabe712e7c4b7022247b6983e51ee72ca983df9ad990b3296`.
The real pinned, dedicated SSH identity passed its exact binding and rejected
arbitrary commands and a wrong hash. Full read-only controller preflight passed
against the actual PP host, Compose configuration, private network, volume and
prepared secret files. This is actual host evidence, not the CI hostname fixture.

The explicit role preparation recreated only PP PostgreSQL to add its lifecycle
secret mount. The same named volume preserved all 32 exact foundation rows;
four restricted roles authenticated. Recreation plus checks took 9.032 seconds;
that is not a measured API interruption because no PP application/collector was
running. No production service or database was touched.

The preprod GitHub environment now holds the dedicated key and verified host pin.
Temporary runner 27 (`tradebot-pp-operator-20261113`) is online/idle and ephemeral,
using the verified official v2.338.2 package on the existing operator computer.
It introduces no VM or AWS resource. The PP target profile may now be enabled
through a tested configuration PR using this evidence; the production target
remains disabled. No one-use deployment authority has been issued yet.

[Sanitized binding evidence](evidence/pp-runtime-binding-2026-11-13.json).
Next: merge the bounded PP profile change, require exact preprod CI, publish a
unique PP candidate, then make the first manual generated-only CD attempt.
Application deployment, acceptance and sustained/live operation remain separate.
No Supabase write/permission, real collection, retirement or paid-AI enablement
is included. CP6–10 and I7/Phase 1.75 remain open.

### CP5 first manual attempt — failed before PP application execution

**Current CP5 status: application deployment INCOMPLETE.** PR #22 merged the
qualified PP binding into preprod `d59cd1e`; its exact CI
[43353905598](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/43353905598)
passed. Candidate [v0.2.0-pp.1](https://github.com/JakeMofa/Trading_Bot_Analytics/releases/tag/v0.2.0-pp.1)
and its immutable GHCR source carrier published successfully in run 43354307493.

Manual [CD run 43354829263](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/43354829263)
passed hosted preflight, then failed at `actions/setup-python` on the existing
Mac operator runner: it attempted to create `/Users/runner` without permission.
The host controller was never invoked: no PP business migration or application
start occurred. This failure is not a database or application-test failure.
The unused root authorization was revoked. Ephemeral runner 27 unregistered and
removed its credential files; no runner remains from this attempt.

Scoped fix `e4b28bb` replaces only the private deployment job's interpreter
installation with a bounded validation and invocation of the existing tested
`/opt/homebrew/bin/python3.12`. Actual command execution, 34 release controls and
actionlint passed locally. Hosted CI setup and production workflow are unchanged.
Require successor exact CI and a small PR into preprod before publishing a new
candidate and issuing fresh authority. No unchanged retry or overwrite of pp.1.
[Sanitized attempt evidence](evidence/pp-first-deployment-failure-2026-11-13.json).

Actual PP currently retains the qualified PostgreSQL foundation, dedicated SSH
controller and restricted roles. The application remains uninstalled. CP6 actual
Supabase, CP7 live/capacity, CP8 exact production candidate, CP9 approved cutover
and CP10 verified lifecycle/acceptance are still open. Production is unchanged.

### CP5 actual application deployment PASS — November 13 UTC

**Current checkpoint: CP0–5 PASS within generated foundation/application scope;
CP6 is next. Phase 1.75 / I7 remain OPEN.** PR #23 fixed only the private
runner's Python setup; source push 43355664176 and PR 43355676753 passed. Its
preprod merge `a7f7cd036fec6956891707d8240f696c0cfb0925` passed exact
[CI 43355993076](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/43355993076).
The failed pp.1 attempt remains failed and preserved above.

Candidate [v0.2.0-pp.2](https://github.com/JakeMofa/Trading_Bot_Analytics/releases/tag/v0.2.0-pp.2)
published in run 43356340605. Manual
[CD 43356521535](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/43356521535)
**PASS**: exact schema/migrations, generated writes/conflicts, private API,
dashboard/history/SSE, source freshness/market identity and API-restart recovery.
The runtime image is `sha256:3a77dd8eccc304d0d762c7a6be0ed4f22cc62ae72efb990a8428c375ce473a84`.
Release/registry source carriers are retained, distinct from this locally built
runnable image; exact production-image promotion remains CP8.

Independent PP postflight confirmed four running containers, zero automatic
restarts, the same `tradebot_pp_pgdata` volume, all 32 exact foundation rows,
21 generated raw events and 21 predictions. Database allocation 10,122,931 bytes,
WAL 33,554,432 bytes; sampled free filesystem 57,080,659,968 bytes and available
RAM 1,324,470,272 bytes. Docker reports 796.1 MB images, 67.84 MB volume and
258 MB build cache (overlapping image/cache accounting must not be blindly summed).
These are tiny-fixture snapshots, not representative performance/capacity proof.

The job ran for 79 seconds. No real collector was running, so real collection
interruption was zero; controlled API-restart interruption was not separately
timed. The one-use authority was consumed; temporary Mac runner 28 unregistered
and removed its credentials. The host marker now records application installed,
preventing foundation-only operations against the migrated application schema.

**Access qualification and limitation:** Docker's internal-only bridge retained
isolation but did not publish the configured host `127.0.0.1:8000` mapping.
Controller smoke proves container-local API, not that host mapping. The initial
host-local probe failed and is not relabelled PASS. The separately tested route
is the existing pinned **operator SSH tunnel to the dynamically resolved API
container IP**. Dashboard 858 ms, current state 80 ms, history 160 ms, initial SSE
received, no two-second timeout; the tunnel was terminated/reaped. Keep the
restricted deployment key non-forwarding. Re-resolve container identity/IP after
recreation. No public port, firewall or additional bridge was enabled.
[Docker internal-network reference](https://docs.docker.com/reference/cli/docker/network/create/#network-internal-mode---internal).

Generated feed ages became stale after the finite smoke stopped, and health
reported that truthfully. Live collector, Supabase sync, retirement and paid AI
remain OFF. PP is not yet production preview; PP/prod databases are not shared.
Production is untouched; its earlier recorded SQLite state is not a fresh audit.
[Sanitized deployment and host evidence](evidence/pp-application-deployment-2026-11-13.json).

**Next:** CP6 reviewed additive private `history_v2` migration/permissions and
bounded actual cloud compatibility, then CP7 sole-collector live/capacity/recovery,
CP8 exact production candidate, CP9 approved cutover, and CP10 first-generation
verification/retirement/sustained acceptance. No cloud mutation or production
cutover is authorized by this generated deployment result.

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

PP needs a **visible, operator-controlled mode switch**. The dashboard and API
report whether they are showing PP live collection, isolated PP test data, or
production preview, including environment, data origin, as-of time and collector
ownership. A private authenticated operator API/control path may start or stop
the PP collector only after checking the durable ownership fence and current
mode; ordinary dashboard/preview credentials are read-only. Stop must drain and
acknowledge the collector, persist OFF across restarts and verify that no PP
writer can restart automatically. A failed switch leaves the previous safe
mode and reports why it was held. The controls must prevent PP collection and
production-preview mode from running together. No public collector switch or
trading endpoint is added.

**PP mode setting and transition contract (selected design, not deployed):**

| Setting | Dashboard/API reads | PP collector | PP database use |
| --- | --- | --- | --- |
| `isolated` | PP API backed by PP PostgreSQL | OFF | Generated/replayed records, or a separately identified test subset; all labelled as test data |
| `pp_live` | PP API backed by PP PostgreSQL | ON only while PP holds the sole-collector fence | Official read-only feed observations and predictions are persisted in PP; no production writes |
| `production_preview` | Restricted, authenticated production API/SSE proxied to PP dashboard | OFF and fenced | PP test database remains available for later work but does not supply current production prices |

The private operator setting changes the **PP dashboard's source** and may
control the **PP collector**; it never switches a database connection to
production. It is not an arbitrary database picker. If new feature experiments
need a subset, provision a separate PP test database or an explicitly isolated
origin/schema with its own migration version and read-only source proof. Do not
silently reuse the live PP origin or copy production credentials. The displayed
mode, environment, origin and last source time must travel with every API/SSE
response so a stale PP value cannot masquerade as production.

Transitions are fail closed. `isolated → pp_live` requires the qualified real
connector, explicit production writer fence, PP ownership lease and bounded
resource preflight. `pp_live → isolated` stops intake, drains/acknowledges in
flight writes, persists collector OFF, checks processes/ownership after restart
and keeps PP history queryable. `isolated → production_preview` requires the
restricted production API route and a confirmed PP collector fence. Preview
failure reports production unavailable and does not substitute PP values.
Returning to `isolated` restores PP test views without starting collection.
The approved production cutover independently verifies PP OFF before production
takes the lease. Mode changes and failed attempts are recorded with actor,
time, previous/new mode and fence result, excluding credentials.

**Implementation order and proof:** (1) private PP API/dashboard access;
(2) PostgreSQL live adapters and migrated queries on generated/replayed fixtures;
(3) persisted mode/collector controls and truthful API/SSE source labels with
transition/crash tests; (4) production writer fence and bounded PP live run;
(5) stop/fence PP collection, confirm it stays OFF across restart; (6) after
production cutover, qualify read-only production preview and isolated test
subset selection. Test each mode through the actual dashboard/API and deny an
unauthorized request, concurrent collector, stale source or failed mode change.

**2026-11-13 implementation checkpoint — stable PP API route (candidate):**
The API alone now joins a dedicated loopback bridge as well as the internal
database network. The release controller requires the configured publication,
Docker's *actual* published binding, and a successful host-side
`127.0.0.1:8000/state/current` check before and after its API restart. Database
and worker services remain internal-only. Compose v5 normalization passed the
controller policy; 60 local PP-control tests passed with one platform skip.
This is code qualification, **not a PP deployment or operator-tunnel PASS**.
Its controller bundle hash, exact CI, host installation and manual PP release
must be qualified before marking checkpoint 1 complete. The live connector,
mode switch, production fence, cloud verification and retirement are still OFF.

Before production takes collection ownership, stop and fence PP collection so
it cannot automatically restart; keep PP API running. A storage-guard pause is
not a writer fence. Cross-host preview uses qualified private networking or an
approved tunnel and a restricted API identity. Docker bridge networks do not
span hosts. Never share database volumes or expose PostgreSQL publicly. Preview
credentials cannot call administrative or collector controls.

**Requested PP live rehearsal, before production cutover:** The deployed PP
PostgreSQL API/dashboard currently serves generated data. Its current settings
reject live collection, and runtime cloud archival/retirement are OFF; this is
not a flag-only activation. Finish and qualify the stable private API access
route, then implement the read-only Coinbase and Polymarket US 15-minute feed
adapters against PP's PostgreSQL event contract. Adapt each necessary live
collector read/write and price/history query from the legacy SQLite application;
do not infer parity from passing generated fixtures or point PP at the legacy
database. Preserve exact source timestamps, decimals, provenance, market
identity, stale/unavailable states and the serial calculation worker.

Before enabling that connector, verify production's *actual* collector state
and establish an explicit, restart-safe production writer fence. Do not treat
the recorded storage-guard hold as that fence. Run one bounded PP live window
with PP as the sole real collector. Verify persisted feed acknowledgements,
current-price and history query results/latency, calculations, dashboard and
SSE advancement, and a real 15-minute market boundary. Measure save/heartbeat
delay, API timeouts, input/feature ages, disk/WAL growth and core/outbox use
against the existing acceptance limits. A failed feed or missing market must
display its actual state. Stop and fence PP collection at the end; verify it
cannot restart automatically while PP's dashboard/API remain available.
The PP dashboard during this rehearsal reads **PP's own PostgreSQL-backed API**;
it must show the same active market, generation and fresh values acknowledged by
the PP collector. Compare new PostgreSQL lookup results with independently
checked source events and the intended legacy SQLite semantics, including
timestamps, exact values and history ordering. Record differences rather than
assuming the two database engines return identical answers.

The A/B PostgreSQL generation switch exists in generated tests, with a
72-hour-or-qualified-size policy. The live rehearsal must verify generation
identity, acknowledgements and dashboard/query continuity across a bounded
switch when a qualified size trigger permits it. Do not wait 72 hours merely
to prove the switch. Upload, authenticated readback, protected-reference and
reader-drain gates remain required before local partition retirement; cloud
failure preserves the sealed generation. No unqualified archive deletion is
enabled by the live connector test.

After PP passes and the exact candidate is released to production, production
runs its **own** Docker services, PostgreSQL volume, API and sole collector.
Production does not read or write the PP database, and its runtime does not
depend on the PP API. In the later production-preview mode, **PP reads
restricted production API/SSE responses** to display production state with its
collector OFF; PP uses its own database for isolated test data. Qualify that
authenticated private API route separately before claiming preview works.
In preview mode PP's dashboard calls the restricted production API/SSE; it is
not a second collector and does not query the production database directly.
Show the production source label and stale/unavailable state clearly. A
production API outage cannot fall back to PP's older test prices as though they
were current production values.

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
| 0 | Consolidate plan, align reviewed main workflows/docs to PP | PR #15 merged; no SQLite A/B bulk merge; one active plan/handoff consolidated in PR #16 |
| 1 | PP Docker/PostgreSQL/developer foundation | Official Ubuntu Docker repo; pinned `postgres:17.12-bookworm`; isolated network, persistent volume, restricted roles, secrets, health; generated persistence/recreation and README commands. **PASS generated/PP foundation; PR #16** |
| 2 | Versioned local database and `history_v2` contract | Version/checksum ledger; empty/repeat/upgrade; schema/constraint/index/grant drift; wrong-environment, decimals/timestamps/identity/reference regressions; no cloud DDL until CP6 |
| 3 | PostgreSQL app and dashboard | Adapter, indexed current-price and bounded history, calculations, actual API/SSE, independent discovery/serial calculation, runnable application image |
| 4 | A/B lifecycle and historical retrieval | Atomic switch/seal, durable structured outbox, bounded archives/readback, history after real generated partition retirement; preserve on failure |
| 5 | CD Preprod | Qualified restricted host controller/deploy identity/host pin/credentials/runner; migration/app/image CI; manual PP deploy and recovery evidence; no flag-only enablement |
| 6 | Actual Supabase compatibility | Separately reviewed additive private `history_v2` DDL/grants; bounded isolated writes/readback; exact values/conflicts/checkpoints/replay; mutation-authority qualification |
| 7 | PP live/capacity/recovery | Implement and test real 15-minute adapters, migrated PostgreSQL queries and a private authenticated PP collector on/off control with durable ownership fencing and visible data mode. Explicitly fence production; bounded sole-collector PP run across a market boundary and qualified A/B switch; compare persisted data, dashboard/API/SSE and query/feature ages and latency; measure normal/outage growth; stop/fence PP collector afterward while its API stays on. Complete legacy import/recovery gates separately. |
| 8 | Exact production candidate | Reviewed small PRs assembled on main; exact image/version tested in PP; executable cutover/recovery with measured operating limits |
| 9 | Approved production cutover | Fence old writer and PP collector; verify/import committed history/delta; start the sole PG collector on production's own database and API; bounded smoke and measured interruption; retirement initially OFF. PP preview of production is a later restricted, read-only API/SSE path. |
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

PP access used the existing operator key and independently pinned host key. The
current operator /32 was added only to PP SSH after fresh rule comparison; the
old /32 and browser SSH alias were retained. No production rule changed.

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
