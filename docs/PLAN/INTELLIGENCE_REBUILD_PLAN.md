## Active master plan — PP rotation, usable history, and archive performance

November 19, 2026. Scope is read-only collection and deterministic analysis for
Polymarket US BTC 15-minute markets. Release operations and application
research run in parallel. Keep the live calculation on the VM, with one
collector and visible freshness and coverage. Keep production and PP origins
separate. One-hour collection, trading and paid AI remain deferred.

Prepare the deterministic history probe from step 4 before either retirement
in step 3. Save its exact input IDs, values and recalculated output against
retained data, then repeat the same query after each partition drop.

| Step | Work and current evidence | Acceptance |
| --- | --- | --- |
| 1. Restore PP release and preserve both generations | PP20 stopped at a generated smoke-queue cap. [#177](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/177) merged the generated-storage fix. [#181](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/181) merged the fenced PP21 forward recovery source. PP21 host recovery, [normal deployment](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44562705669) and the independent retention snapshot passed. A and B still hold 28,411 and 9,784 raw rows. All 42,133 live acknowledgements matched, pending records and outcome counts remained zero, and collection stayed off. | The release operator proves the intended image and schema, preserves A/B identities and counts, and passes smoke and normal deployment acceptance. |
| 2. Finish exact readback and measure the bottlenecks | The indexed PP20 audit held after 62 of 63 structured pages ([#178](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/178)). A read-only PP21 diagnostic using exact qualified [#180](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/180) transport bytes now passed all 57 raw objects / 28,411 rows and all 63 structured pages / 31,162 rows: core 214.390169 s of 240 s, with 25.609910 s remaining; attached-container interval 219.458 s. The scoped first 500-row read passed in 2.163305 s, and retained before/after fingerprints matched. This is diagnostic readback qualification, not a normal deployment, live-continuity trial or retirement authorization. [Exact evidence and limits](PP21_CANONICAL_RETAINED_AUDIT_2026-11-19.md). | Same first page remains under four seconds. Full protected, receipt, revision, projection and raw-object verification passes all scoped pages within 240 seconds with measured margin and the existing request/byte budgets. Record restricted-reader proof. A read-only replay cannot authorize DROP or qualify collection continuity. |
| 3. Prove a full A → B → fresh A trial | PP18 observed the first switch and archived A's 28,411 raw rows, but B stopped after 20m32s and A remained attached. Obtain fresh release-owned authority for another trial. | Collect two full 15-minute markets in each outgoing generation. While the successor keeps writing, verify and retire the exact outgoing partition within the existing 30-minute seal window. Repeat for B with a fresh A generation. Bind each run to a fresh seal and its permit. Verify continued successor writes, forecast freshness or explicit abstention, and retrieval of both retired UUIDs. Keep shared core history and deduplication intact. |
| 4. Make history usable by deterministic calculations across rotation | The offline `88c59ac` prototype composes one reviewed market/generation before and after a generated partition drop. It returns saved snapshots and predictions and separate labels in the generated case. [#185](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/185) corrects the protected outcome wrapper to actual `Store.ingest`; its native ingestion-to-retirement regression and eight research tests pass. This source prototype does not recompute deterministic features. PP's raw API is generation-specific, its saved prediction endpoint reads local PostgreSQL, and its history-context endpoint still marks linked prior cases unsupported. | A bounded market/time query merges retained and retired generations by origin and generation UUID. Use the same availability cutoff, global ordering and event deduplication on both paths. Prove identical input IDs, exact values, links and recalculated deterministic features across an A/B boundary before and after retirement. Required missing generations or manifests fail explicitly. Report capture gaps. Qualify real PP and production scopes separately. |
| 5. Rebuild dashboard research and evaluate deterministic signals first | Use the actual legacy contracts below as a behavior reference. Build chronological comparisons from verified 15-minute windows and versioned feature/prediction evidence. | Test the actual PP browser at rollover before and after retirement. It distinguishes saved forecast, current estimate, matched historical cases, official outcomes and explicit gaps. Training/evaluation splits by market and time. Optional AI explanation stays a separate contract with paid calls disabled. |

### Checkpoint 3 continuation — November 19, 2026

A fresh read-only PP21 inventory confirmed historic live A is verified and still
attached with 28,411 rows, live B is collecting-disabled with its 9,784 rows,
and the writer is OFF with no session or unused authority. All 42,133
acknowledgements remain recorded with no pending entries. A's original 30-minute
seal deadline expired. Neither re-enabling B nor reusing A's earlier permit
starts a fresh A-first trial. Preserve both partitions. A fresh start with its
own qualified scope, or separately approved historical maintenance followed by
a fresh A admission, is required before a live dispatch.

The two-leg candidate binds an exact initial A UUID and an explicit PP-only
finite session. Keep the existing normal 4,560-second ceiling. For this trial
only, a 6,600-second session admits within the final minute before an official
15-minute boundary: 60 seconds before A, 1,800 seconds of A markets, up to 900
seconds for B's first full market, 1,800 seconds of B markets, and 1,800
seconds to finish B's archive and retirement. The remaining 240 seconds cover
scheduling overhead. Actual source delays can still exhaust the lease. Each
seal keeps its own original 30-minute deadline and exact verified-retirement
authority. Hold if a target slot is occupied or safety evidence is incomplete.

The same collector session must keep writing through A → B → fresh A. A late
discovery or missing first quote waits for the next normal poll, and unavailable
data remains visible as such. Check the exact writer and its write advancement,
plus the dashboard and history, around both swaps and both retirement commits.
Record the observed outcomes from the live trial separately from fixture and
read-only verifier results. The isolated PostgreSQL control run passed all eight
selected cases on the combined source, including native two-switch persistence,
the occupied-slot hold, both permit-bound removals and second-leg readback
rejections. The switch fixture simulates the first retirement, and the
permit fixture uses generated archive transport. Live PP remains OFF. Follow
the [two-leg configuration](PP_SEAMLESS_CYCLE_SOURCE_2026-11-19.md) and
[before-and-after dashboard capture](PP_HTTP_HISTORY_CAPTURE_2026-11-19.md)
only after exact CI, a qualified fresh start, matching release controls, two
current archive freeze windows and a fresh production-fence check.

### Legacy dashboard contracts to carry forward

- Review the actual production legacy FastAPI source at `d56b4a7`, separately
  from the older standalone SQLite dashboard. The shipped browser consumes
  RAM state and the `/events` stream for the live Gaussian estimate. It requests
  saved prediction rows from `/history/predictions` and SQLite-backed outcomes,
  evaluation, news and linked cases from `/history/context`. A user needs to be
  able to distinguish a saved Gaussian/ensemble row, a live estimate and
  retrospective context. The older `/api/status` server remains useful as a
  reference for saved ensemble preference and Gaussian fallback.
  [Legacy FastAPI endpoints](https://github.com/JakeMofa/Trading_Bot_Analytics/blob/d56b4a7/backend/app/api.py#L221)
  · [Legacy SQLite query contract](https://github.com/JakeMofa/Trading_Bot_Analytics/blob/d56b4a7/backend/app/dashboard.py)
- Legacy prior cases, forecasts and confirmed outcomes have provenance and
  time semantics worth preserving. Retrospective links are evidence of a
  later association. Preserve the explicit calculation-input links as
  a distinct record. A market-wide latest decision override and latest linked
  context can refer to a different snapshot. PP needs atomic hydration of
  market, feature, forecast and chart state through rollover. It currently
  exposes a Gaussian saved forecast and live estimate, local prediction history
  and unsupported prior-case context. The outcomes schema and ingestion support
  exist. Routine official delayed-outcome reconciliation for live PP still
  needs its own evidence. Classify a forecast without a known outcome as
  awaiting a label rather than manufacturing one.
- The deployed legacy ensemble worker computes deterministic predictions and
  has a separately gated advisor. At `d56b4a7` the worker passes market and
  snapshot IDs in a short summary, plus ensemble probability and components,
  then can write `ai_suggestions`. The optional history argument is unused by
  that worker. The standalone legacy variant that queries up to 200 same-market
  prediction rows is a separate source path. The shipped browser does not
  invoke the advisor, and the FastAPI payload omits the `ai_suggestion` and
  `forecast_15m` fields the browser probes. The deployed service definitions
  explicitly disable OpenAI. Keep paid AI off.
  If later authorized, make the explanation optional and bind it to the
  exact forecast input and model version.
  [Deployed legacy advisor worker](https://github.com/JakeMofa/Trading_Bot_Analytics/blob/d56b4a7/backend/app/run_ensemble_agent.py#L47)
  · [Legacy browser field probes](https://github.com/JakeMofa/Trading_Bot_Analytics/blob/d56b4a7/backend/app/dashboard.html#L478)

For this audit, 25 legacy dashboard tests passed against the exact
`d56b4a7` source with the advisor disabled. Six generated `88c59ac` research
tests passed in this review. Its native test requires a disposable DSN and was
skipped in this rerun. These are source and fixture results. They do not
establish live PP or production dashboard parity.

### Points that matter for the Supabase and PostgreSQL work

- Raw events remain exact compressed files in private Storage with the local
  sealed manifest and hash. Private Supabase PostgreSQL holds structured
  records, receipts and revision envelopes. For research, decode verified
  objects into an isolated queryable workspace. For live calculations, use
  local inputs. Coinbase remains reference data. Official Polymarket US labels
  are separate, with availability and confirmation times.
- A research cutoff uses actual arrival and availability, including the link
  proving when a feature was published. Preserve source timestamps and saved
  IDs, never substitute latest state for point-in-time inputs, and apply a
  separate cutoff to official outcome labels. Legacy saved-history responses omit
  snapshot and evidence links. Carry those in PP instead of inferring saved
  provenance from an old UI label. The initial prototype is
  single-generation, explicitly reviewed coverage and bounded by four raw
  pages and 50 structured revisions. The next proof requires a true
  multi-generation merge and indexed market/time selection or an equivalent
  bounded archive catalog.
- Archive and query tuning continues alongside dashboard parity. Binary results
  reduced protocol bytes in a native fixture, while the matched PP text/binary
  pages showed no elapsed win. [#180](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/180)
  reuses already-checked canonical bytes and saved 71–75 ms per generated
  page. It still needs a matched PP measurement and full-audit margin.
  An isolated local query study found a matching raw cursor index cut the
  generated 57-page sweep from 4.416 s to 0.740 s with identical row/page
  hashes. The same sweep on the full local schema fell from 4.613 s to
  0.761 s with identical hashes. The index added about 4% bulk-insert time
  and 15% WAL in the generated write trial. The tested outbox index did not
  show a material improvement. Profile the actual PP raw plan and local
  inventory separately. If PP reproduces the raw scan, qualify a sealed-child
  index to keep its write cost off the active generation.
  [Local retention query study](PP_LOCAL_RETENTION_QUERY_STUDY_2026-11-19.md)
  Keep the 50-row sync write configuration
  until separate 75-row throughput and exact acknowledgement evidence.
- The audit timing report and independent raw restore tooling in
  [#179](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/179) are qualified
  on generated data. The reader-export-to-offline-restore path covered 57
  objects / 28,411 rows with the primary path unavailable, and rejected a missing
  restored object. A separately controlled live backup destination, an actual
  independent PP copy/restore and Grafana integration remain separate. No extra
  PP data copy or service activation is required by this roadmap entry.

## November 19 UTC — offline A/B/fresh-A admission planning

A source-only planner validates exact official quarter-hour pairs, distinct
A/B/fresh-A generation UUIDs, both unchanged 30-minute seal deadlines and the
existing 4560-second lease cap. Six tests pass. The earliest aligned full-window
schedule needs validity past 5400 seconds; mid-market alignment can increase the
shortfall. The current market-pair profile never rotates B, so every plan remains
HOLD even when shorter proposed readback reserves fit. No route/profile/lease/
guard/retirement policy or runtime operation changed. A separately reviewed
explicit OFF/re-admission and exact-B continuation is required to rehearse the
second leg without extending the cap. [Evidence and continuation scope](PP_REHEARSAL_ADMISSION_2026-11-19.md).

## November 19 UTC — canonical exact-read byte reuse source candidate

A narrow source candidate reuses the exact expected serialization and canonical/
receipt-validated original envelopes for the existing full byte comparison and
size charge. It preserves the original receipt, origin, checkpoint, newer
revision, current projection, read-only and deadline checks. Matched generated
PG17 proof with text results/fresh connections/indexed latest measured full
500-row reads at 292.919→218.404 ms (G=0) and 290.744→219.630 ms (G=1), with 32
successful full reads and 22 matched corruption/scope guards. This is source
qualification only; no PP/prod host, deployment, cloud or runtime change.
Native timing does not establish PP's needed full-audit reserve. Exact-source CI,
matched PP first-page comparison and actual full-audit margin remain unqualified.
[Decision, reproducible harness and evidence](PP_READBACK_CANONICAL_BYTE_REUSE_2026-11-19.md)

## November 19 UTC — source-only PP snapshot binding and chart coverage fix

An independent parity audit reproduced a PostgreSQL read-committed hydration
race: a calculation committed between the feature and forecast SELECTs, yielding
different snapshot IDs. A separate regression showed a newer feature without a
forecast borrowing an older forecast. The candidate reads the latest feature
and its exact saved forecast in one statement, retaining null/abstaining results
and exact decimal decoding. It also makes the chart display the server's
`truncated` warning when the bounded query omits earlier ticks.

All 23 focused native PostgreSQL 17.2/application/SSE/dashboard tests passed with
restricted app/lifecycle logins and no skips; the full backend run passed 342
tests with 54 environment-dependent skips. A generated 10,001-pair warm-query
comparison used existing indexes, with 0.089 ms median / 0.271 ms p95 for the
linked read versus 0.222 / 0.363 ms for the old two reads. These local timings do
not establish PP runtime latency. [Reproduction and limitations](PP_HYDRATION_CONSISTENCY_2026-11-19.md).

This source-only fix was staged during the PP21 freeze; source integration
follows its explicit unlock. No schema, release, host, cloud, collection or AI
activation changed. Official outcome
reconciliation, deterministic replay, evaluation/context/case retrieval and
ensemble/AI migration remain separate application parity work.

## November 19 UTC — source-only point-in-time outcome proof correction

The bounded research prototype's initial flat outcome fixture did not match
`Store.ingest`/`_protect` wrappers. An actual ingestion regression reproduces
the failure on `88c59ac`. The source-only correction binds wrapped data and
provenance to the protected evidence and checks event identity/result/exact
final value. Eight tests pass without skips on disposable local PostgreSQL
17.2, including independent outcome cutoffs and identical application labels
before sealing and after generated raw partition DROP/authenticated archive
readback. [Scope and limitations](PP_POINT_IN_TIME_RESEARCH_PROTOTYPE_2026-11-19.md).
No API wiring, PP/production release, cloud/host operations, real collector,
paid AI, retirement authority or merge is included. Real outcome reconciliation,
whole-market coverage and application historical parity remain open.

## PP19 retained A audit, November 19 UTC

PP19 `5efc4bb` passed [exact source CI](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44502994609)
and [preprod deployment](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44504027993).
[Live-profile entry](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44504441451)
failed at the 1 GiB available-memory floor on the 2 GiB VM. After confirming durable OFF and an empty pending outbox, the operator
stopped the PP calculation and lifecycle services already covered by the recovery operation. The original headroom guard passed and
[generated service restoration](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44504872224) succeeded.
Collection remained off. A separate read-only audit used the exact image, existing local reader, GET-only raw archive identity and
read-only structured transactions. Reusable history sessions were enabled only in that one-shot container.

**Raw A passed. Structured A remains on hold.** All 57 archived objects (3,623,081 compressed bytes) were authenticated, decoded
and compared with retained A. Inventory took 16.875 s, raw read/decode 25.946 s and local comparison 18.803 s. The first
500-row structured page returned `archive_unavailable` during projection verification. The page took 4.712 s; its latest-receipt
phase took 2.051 s and exact revision reads took 1.143 s. The underlying SQLSTATE was unavailable. The audit ended after 67.510 s
(72.558 s including container startup and exit), with 172.490 s remaining, 60 logical requests and 4,428,956 logical bytes charged.
The overall deadline, request and byte caps did not exhaust. These timings do not establish the cause of the earlier PP18 HOLD.

At 10:24:57 UTC A remained attached with 28,411 rows, B retained 9,784 rows, the PP outbox held 42,133 acknowledged structured
rows and zero pending. The collector was durably OFF with no session. Audit container and staged credentials were removed.
The outstanding qualification is exact structured receipt, revision and projection verification across all 63 pages under the
existing per-page limits. Reproduce the first page and compare the latest-receipt query plan before scheduling a new bounded audit.
The original 30-minute verdict remains failed; a future audit cannot authorize deletion or establish concurrent B collection.
[Sanitized timing and reconciliation](evidence/pp19-retained-a-readback-2026-11-19.json)

## November 19 UTC — PP18 observed switch, retained A, early B stop

PP18 pinned source `74a850bc` observed A→B, and raw A verification covered
28,411 rows / 57 chunks in **498.625812s** after 08:30:04.617214 seal. Full final
verification returned **HOLD `archive_limit`**; A stayed attached, with no
retirement. The 247.855136s ticket→container-die interval includes startup and
finalization; the exhausted dimension and dominant phase are not established.

The required 30-minute B run **FAILED**: durable OFF 08:50:36.853109 after
`ownership.lease_lost` and lifecycle-role connection saturation, only
**20m32.235895s** after A seal. B retained 9,784 raw rows. Post-OFF drain completed
with A 31,162/B 10,971 structured ACKs, zero pending, both workers OFF and final
DB sample 08:56:09.912353. No B archive/retirement success is claimed.

Independent 690-payload audit reports publication integrity **PASS** and strict
numeric switch continuity **INCOMPLETE**. First post-bracket sample lacked
forecasts; saved/live numeric recovered 08:30:25.738910. Truthful stale-reference
abstentions, UI age suppression, rollover empty charts and  91.281s observer gap
remain explicit. API sampled latency and DB/WAL counters do not prove continuous
feed freshness or CPU/RSS/headroom; only preflight disk-free was measured.

[Full qualified observation](PP18_COMBINED_OBSERVATION_2026-11-19.md) ·
[Sanitized combined evidence](evidence/pp18-combined-observation-2026-11-19.json).
Next gates are lifecycle connection-budget/lease continuity and bounded full-path
verification qualification. No legacy/prod, trading, deployment, setting or
retirement authority follows from this docs-only milestone.

## November 19 UTC — measured cold-readback followup, documentation only

PR #164 merged at `a4e39d1` after exact green. Additional research remains separate:
no further source, profile, permission, host or live-operation change. The hosted
read-only EXPLAIN for a retained 500-ID scope uses the existing receipt/revision
primary keys; cumulative SQL timings mix page sizes and are not full-path latency.
Runtime-role SET ROLE was denied, so the plan is explicitly connector-role only.

An isolated native PG17.2/psycopg3.2.13 benchmark completed 36 matched 500-row
reads, 12 negative checks and two exact deployed-query codec probes under the
unchanged four-second cap. Narrow binary result format reduced measured
revision PostgreSQL stream bytes by 48% and full structured readback by 32%,
including a B-replacement case. This is not a PP speedup or full-retirement proof.
The fixture was stopped. No new application implementation was added.

The release-supplied 2.499–3.393s rich-page timings imply 187.425–254.475s for 75
pages against 240s before raw/local work. Reserve remains unknown. Recommend a
separately qualified four-call full-path text/binary PP probe bounded to 25s,
then consider reuse only after explicit retirement-path wiring/qualification.
Release ownership, all checks/deadlines and VM-local live predictions remain.

[Concise recommendation and exact probe](PP_READBACK_BENCHMARK_HANDOFF_2026-11-19.md) ·
[Native benchmark](COLD_READBACK_PERFORMANCE_2026-11-19.md) ·
[Hosted baseline](evidence/hosted-readback-baseline-2026-11-19.json)

## November 19 UTC — hosted candidate reconciled with PP18 source

The cold-history candidate was reviewed against preprod `7338c057`, preserving
both the hosted research and Coinbase timing evidence. Default API construction
registers no structured-history route; the optional reader remains unconfigured.
No workflow, cloud setting, deployment or pinned PP18 runtime changed.

The reconciled backend passed **372 tests, 46 explicit skips**. A fresh disposable
local PostgreSQL 17 fixture passed **75 combined cold-reader/shared history
transport tests, three unrelated fixture skips**, including exact envelope
readback and receipt metadata bounds; its owned server was stopped. These local
checks do not qualify hosted credentials, live activation or sustained headroom.
Exact source CI remains a separate merge gate.

## November 19 UTC — cold-history edge-case review and bounded dispatch

After reconciling preprod `74a850b` (including the separate rollover fix), the
full pinned backend passed **365 run, 319 passed, 46 explicit fixture/platform
skips**. All qualified cold-component file hashes remain unchanged. This merge
preserves both workstreams and performs no live rollout.

The source-only candidate in PR #164 passed [exact-source Linux CI](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44480584156)
at `5a44c7f`, including backend, dependency, controls, PP foundation and PostgreSQL
lifecycle jobs. It closes three reproduced edge cases:
receipt metadata is budgeted and suppressed in SQL before transfer, the page
clock includes manifest/validation/copy work with remaining-budget handoff, and
API admission happens before a dedicated cold worker receives work. HTTP
cancellation cannot release the slot while the source is still active; shutdown
and rejected submissions have cleanup coverage. Live/local endpoints use their
existing worker path. Source default remains OFF and no runtime injects the route.

Full pinned backend: **362 run, 316 passed, 46 explicit platform/fixture skips**.
Separate native PostgreSQL17 qualification: **75 run, 72 passed, 3 unrelated
app-fixture skips**, including 13 generic history/import/reuse tests and six
cold-source tests. Native proof corrupted each of five receipt text fields to
1MiB and tested aggregate overflow across two rows; over-budget fields and
envelopes returned NULL before client transfer. Temporary databases were stopped.
The 256KiB envelope and 256KiB receipt-text budgets are separate; fixed row,
protocol and TLS overhead are additional. No hosted-role or PP/prod qualification
follows from generated tests. [Source/test evidence](COLD_STRUCTURED_HISTORY_CANDIDATE_2026-11-19.md).

The user-requested deeper read-only navigation is complete within the defined
project/catalog scope: all 31 integration overviews and 31 linked public docs,
plus private database details, safe Auth/template pages, Storage/Realtime,
observability/advisors and project settings. Secret, personal-data, mutation,
setup and recursive-global-doc boundaries are explicit. The browser observes
Grafana as a third installed integration; this research made no installation.
The specific function advisor finding was classified using read-only metadata
and official PostgreSQL source, without invoking or changing the function.
Four unindexed-history-FK suggestions call for query-plan review, not blind DDL.
The release chat received scope, findings and tested-source progress and
continues its rollover/archive work separately. No live cloud, collector or
retirement action was performed here.

[Deep navigation and 31-card assessment](SUPABASE_DEEP_NAVIGATION_2026-11-19.md) ·
[Prioritized next uses and advisory nuance](SUPABASE_NEXT_STEPS_2026-11-19.md) ·
[Function metadata](evidence/supabase-function-advisory-2026-11-19.json).

## November 19 UTC — hosted Supabase integration investigation and local candidate

Parallel research combines PR #157's dashboard audit, PR #155's actual PP
receipt-read measurements, PR #159's default-off generated reuse qualification,
current hosted read-only SQL and official product documentation. The existing
uncommitted cold-history prototype was found and its six offline tests rerun
successfully; its original worktree remains intact. Reuse this design for the
structured-history application gap rather than start another archive engine.

At 06:52:08 UTC exact read-only SQL counted 5,268 PP receipts and 400 immutable
revision payloads; concurrent release-owned backfill can change these counts.
All twelve private history tables had RLS, with zero replication slots. No
separate structured-reader SQL role was observed. At 06:52:35 UTC raw catalog
metadata counted 980 objects/339,576,344 bytes, not verified object contents.
These snapshots establish neither complete backfill nor production qualification.

Current official Pipelines FAQ (updated November 16) lists public-alpha
BigQuery/ClickHouse/DuckLake/Snowflake, superseding the older private-alpha,
BigQuery-only result returned by documentation search and repeated in the prior
prototype research. Project entitlement still needs independent verification.
Managed analytics does not replace the existing receipt-bound archive contract.

Decision: keep live RAM/local PostgreSQL on each VM, private background structured
history and authenticated raw Storage. Build one default-off bounded structured
cold-reader candidate with a separately scoped SELECT-only identity, trusted
manifest selection and explicit coverage. The local candidate ran 65 affected tests: 51 passed and 14 existing
full-application/history fixture skips, including four native PostgreSQL17
cold-reader tests. Its optional API hook accepts server-registered queries,
requires scope-bound continuation and limits concurrent reads. The route is
absent by default; no runtime profile injects it. Hosted grants, deployment, real payload comparison,
production support and raw disaster-recovery proof remain OPEN. The release chat
continues to own collection, backfill, deployment and retirement; this milestone
performs no cloud writes or live control actions. No merge/deploy is implied.

[Candidate and validation](COLD_STRUCTURED_HISTORY_CANDIDATE_2026-11-19.md) ·
[Measured investigation](HOSTED_SUPABASE_INVESTIGATION_2026-11-19.md) ·
[17-capability matrix](SUPABASE_INTEGRATION_MATRIX_2026-11-19.md) ·
[Browser coverage](SUPABASE_BROWSER_CAPABILITIES_2026-11-19.md) ·
[Timestamped evidence](evidence/hosted-supabase-investigation-2026-11-19.json)

## November 19 UTC — offline Coinbase delay diagnosis and timing candidate

The07:10:14pp.17 sample had40.960s source→application-dequeue delay and only0.671s
receipt→API delay. Event IDs advanced during the incident;515rawprices drained
across40.498receipt-seconds but15.529source-seconds. Serial sink backpressure is
supported as an inference, not a proven attribution to local DB vs upstream/TCP.
A reconnect or packet loss is not established by the later trade-ID jump.

A separate defaultOFF `TRADEBOT_PP_COINBASE_TIMING=true` candidate adds bounded
parser-ingress/dequeue/actual-worker-save timing and fixed reconnect diagnostics.
It preserves every received raw tick, original timestamps, durable ordering and
existing reconnect limits. Seven focused tests plus344backendrun/40explicit skips
passed; actual loopback fragmentation/heartbeat/slow-save coverage passed.
No release, live connection or market endpoint changed. Exact source Linux CI and
any future enabled-run evidence remain separate requirements.

[Diagnosis, official references and measurement contract](PP_COINBASE_TIMING_DIAGNOSIS_2026-11-19.md)
and [captured offline evidence](evidence/pp17-coinbase-lag-0710-offline-2026-11-19.json).

## November 19 UTC — genuine new pp.17 immutable capture verified

During the authorized live trial, an independent read-only check compared the
first50acknowledged PP rows beyond the historical cutoff12789: IDs13595–13644,
created07:06:09.098333–07:06:13.193928UTC. All50original envelopes matched cloud
receipt-backed canonical bodies exactly (60,800batch bytes,
SHA256`a793c776d58dbdf8bc235ebfc4fdbf2b06819cf987a3a8ec7cc63804c17b626c`).
The sample includes32current-price revisions,17candles and1market. The actual
recurring worker was running with revision captureTRUE and session reuseOFF on
exact pp.17 source1c753c6/image6f76adb3. Collector/session wereON and new committed
outbox IDs advanced14503→14511during the comparison. This verifies that original
new price revisions remain recoverable while later writes continue.

The check used one authenticated cloud read and changed no cloud/local data,
ACK or cursor. Owned-oneoff/credential staging cleanup passed and its controller
lock was released. Historical5268/5268recovery plus this new-write sample now
satisfy the structured-envelope checkpoint. This sample covers input/market
revisions; whole-generation raw archival/retirement, forecast freshness and
sustained sync headroom remain separate live-trial gates.

[Exact new capture, types, identities, hash and concurrent progress](evidence/pp17-new-live-envelope-capture-2026-11-19.json).

## November 19 UTC — actual pp.17 retained-A envelopes fully recovered

On exact pp.17 `1c753c6`, generated CD44474562747 and ready-off44474879676 passed.
Fresh PP inspection confirmed A UUID`2f5ab434-14c0-4a61-8b8e-145c9a05f0e6`,
collectorOFF/no session,5268acknowledged/0pending rows, IDs7314–12789. Local-only
inventory bound5268canonical envelopes across106pages/8,309,756batch-encoded bytes
and streamSHA256`ca1c43921214fb97de475dff132d2194aae6398332a55ecc29b59bda436d4431`.

The exact-scope receipt-backed repair **PASSED** in207.372s/212cloud operations;
every appended envelope received independent authenticated readback. It changed
no localACK or projection and issued no retirement authority. A separate complete
application readback then downloaded and compared **5268/5268** original envelopes
in82.600s/106new cloud operations. Independent SQL additionally hashed all8,304,382
canonical stored-envelope bytes (newline-delimited stream), matching the local
SHA exactly, with0missing/changed receipts. The difference from batch bytes is
array/separator overhead, not missing evidence.

Both bound root operations exited successfully after owned-oneoff and temporary
credential cleanup; the controller lock was released. The release owner then
began its separately authorized live trial. No post-trial OFF snapshot is claimed.
The repair used the initial default fresh-connection pp.17 transport; optional
reuse is merged as a separate default-OFF source candidate and is not deployed. Raw A remains local:
structured recovery alone proves neither raw archive recovery nor safe retirement.
Genuine new-write capture validation follows actual live acknowledgements.

[Exact release, scope, readbacks and independent whole-body hash evidence](evidence/pp17-exact-envelope-backfill-2026-11-19.json).

## November 19 UTC — hosted history research and cold structured page candidate

The original research used older hosted Pipelines documentation. The expanded
review above supersedes its BigQuery-only/private-alpha statement: the current
FAQ lists four public-alpha destinations with organization-dependent access.
This remains outbound analytics, not the local-PG → private history_v2 verified
envelope/receipt import. WAL/replica identity, replay and lifecycle-delete semantics
need separate qualification. No replication slot, RPC, Data API exposure, grant,
S3 key, paid feature or cloud setting changed.

The actual application gap is an explicit structured cold-read contract:
raw.events archive pages and local prediction history exist, but immutable
structured revision reads are only a lower transport operation. A small local
prototype now pages independently reviewed exact IDs/hashes, one PP origin/
generation/entity/market, at most 50 records/256 KiB/four seconds. It preserves
original decimals/timestamps/NULLs and revisions; missing/corrupt/unavailable
rows fail, and page coverage never implies complete market history or retirement
authority. No API wiring, live credential use or production support is added.

[Research, executable/test contract, product choices and freeze limits](HOSTED_HISTORY_INTEGRATION_2026-11-19.md)
records remaining reader-grant/discovery/manifest/browser/performance gaps.
Generated two-page tests passed; this is an offline candidate, not runtime
acceptance. PP/production hot reads and durable outbox/receipt/ACK gates stay
unchanged. Privileged service/operator/Studio/SQL/Storage owners remain possible
mutation paths; full holder inventory and human freeze attestation are OPEN.
Do not infer an administrator freeze from narrow reader RLS or dashboard settings.
The release owner unlocked source-only merges for PRs 157–160 while the
installed pp17 runtime stays pinned; runtime/cloud controls remain frozen.

## November 19 UTC — independent dashboard evidence acceptance candidate

A local offline evidence audit now distinguishes current-market numerical saved
forecasts/live estimates, truthful abstentions, unavailable output and stale or
unbound output. Existing `live_observe.py` counts distinct prediction IDs and a
nonempty history list; those checks alone do not prove any numerical forecast,
market binding or fresh model input. This supplementary audit requires original
state fields and reports integrity separately from numerical acceptance. An
honest abstention can pass integrity while numerical evidence stays INCOMPLETE.

[Executable and evidence contract](PP_DASHBOARD_EVIDENCE_2026-11-19.md) documents
UTC source/input/feature ages, exact snapshot binding, the dashboard's 10-second
live-tick limit and before/after writer-generation observation brackets. Missing
richer payloads cannot be reconstructed from ID-only observer reports. A later
actual-run audit exposed small cross-host clock offsets: input/forecast ages now
use API generated_at, while operator-minus-server deltas remain separately
disclosed and out-of-band delivery/clock qualification stays incomplete. No rendered
browser display, raw archive correctness or retirement authority is implied.

The separately authorized temporary local conductor records allowlisted fields
from its existing API responses only, with latency/source SHA/UTC/monotonic time;
it adds no API requests or host configuration. Its pure wrapper was compiled and
tested for one inner request/one captured record without running the conductor.
The committed helper remains offline and the deployed observer/runtime are
unchanged. Generated fixture tests cover stale/prior-market forecasts, honest
abstain, missing evidence and exact decimal preservation. Real combined-trial
acceptance remains OPEN until run evidence is processed; preserve the pp17
runtime release freeze. The release owner unlocked source-only merges for
PRs 157–160; this candidate does not promote or alter the installed runtime.

## November 19 UTC — Supabase dashboard audit, observation only

Completed a read-only page-by-page dashboard inspection covering database schema,
functions/triggers/types/extensions/indexes/publications/policies/migrations,
storage and signing metadata, Auth settings, services, metrics/logs and integrations.
[Sanitized coverage, baselines and limitations](evidence/supabase-dashboard-audit-2026-11-19.json)
records which pages actually loaded; it contains no keys, DSNs or user identities.
No project configuration, data, credentials, deployment or paid feature changed.

**Decision:** retain local RAM/indexed PostgreSQL hot reads and explicit background
Supabase history/raw retrieval. The last-day overview showed CPU 2%, disk 21%,
IO balance 99%, peak 8/60 connections; recent raw HTTP examples took 893–972 ms while
legacy public SQL means rounded to 0–1 ms. These are different windows/workloads,
not a PP throughput benchmark, but reinforce measuring connection setup,
round trips and exact receipt/object verification before adding services.
Current connection reuse evidence below remains the actual bounded PP comparison.

**Followups remain OPEN, with no changes during the pp17 freeze:**

- Review Data API automatic new-table exposure (ON) and the single exposed
  function; current tables 0/22 exposed and history_v2 explicitly unexposed.
  Preserve RLS, scoped roles and exact reader permissions.
- Compatibility-review database SSL enforcement (OFF) and network access
  (all IPs). Auth signup is ON, email confirmation ON, anonymous signin OFF;
  Captcha and leaked-password checks OFF. Review machine-token renewal and
  security hardening independently, without breaking the qualified worker.
- Investigate 1.19 GB memory commitment flagged Severe versus 395.83 MB usage on
  Nano. The UI offers Micro/1 GB as a same-price Free Upgrade; this is a capacity
  option requiring review, not proof of a network-speed fix or permission to
  resize. No replicas or additional compute services are justified yet.
- Verify raw-object recovery separately: seven daily physical DB backups are
  visible, but Supabase explicitly excludes Storage objects. A database restore
  is not a raw archive recovery proof.
- Classify error/warning rates against deliberate permission tests. Record PP
  phase latency, rows/bytes/page, request count, reconnects/retries and exact
  receipt/hash correctness for any optimization. Keep deadlines/retirement gates.

Cron/Queues/Webhooks are not installed; Edge Functions and publication tables
are empty. New Compute is inaccessible private alpha; Analytics/Vectors show
empty private-alpha screens. Log drain cards display Additional $60. None was
activated. Database IOPS/throughput/connection/disk panels failed to load;
Data API last-hour metrics had no data. Catalog searches for dbt/stack/event
returned no results, which is a UI coverage limit, not a universal capability
claim. Full Auth subpages, restore/PITR and secret material are outside this audit.
This docs-only milestone does not close PP qualification or authorize promotion;
The release owner subsequently unlocked source-only merges for PRs 157–160;
runtime/controller/cloud mutation restrictions remain in force.

## November 19 UTC — default-OFF PP history session reuse candidate

A separate source candidate recognizes only explicit
`TRADEBOT_PP_REUSE_HISTORY_SESSION=true` for the restricted recurring PP worker.
No Compose profile, controller, release flag or deployed pp.17 transport changes.
The absent flag preserves the current fresh-connection path; malformed flags HOLD.
The opt-in owns one physical session, admits no simultaneous checkout or waiting
queue, revalidates private DSN/TLS/role bindings on every borrow, and leaves all
transport identity checks and four-second request caps intact. Each import and
fresh readback uses a distinct committed transaction. No old transaction or
snapshot survives checkout. Errors, unfinished transactions and deadline expiry
discard the session without ACK/retry; ordinary receipt reconciliation remains
responsible for ambiguous commit recovery. Valid password rotation reconnects;
unsafe bindings HOLD. Idle30s/lifetime300s eligibility bounds require
reconnection on the next checkout; shutdown closes the single retained session. No new dependency or cloud privilege is added.

Generated PostgreSQL17 full-path comparison includes local selection, projection/
receipt/envelope commit, separate authenticated readback, localACK and exact
100-envelope/checkpoint comparison for each arm (two50-row pages). At100ms per
observable SQL wait and200ms connection setup, cold took5.447s (18.36ACK/s,
four physical sessions) and reuse4.837s (20.67ACK/s, one session). Both completed
four distinct committed transactions and100 exact ACKs/envelopes. Fault injection
proves precommit rollback, lost commit response, wrong-role rejection, discard/
reconnect and idempotent receipt recovery without premature ACK or duplicate
checkpoint counting. Ten session unit tests and the existing binding/service
checks and all13 native history/transport tests passed; full local pinned backend
331 run/40 explicit platform/environment skips passed. Exact Linux CI and any future PP activation/full-path measurement
remain required. This is separate from the actual PP receipt-read comparison;
its40.17% read-only improvement is not a measured full-sync improvement.

[Generated full-path evidence](evidence/pp-session-reuse-full-path-generated-2026-11-19.json).
No host action, PP/cloud write or preprod merge was performed by this candidate;
initial pp.17 evidence and retained-A backfill continue on the default path.

## November 19 UTC — PP controller bound for revision capture and sealed-window verification

Combined source `3adbc3a` passed exact CI 44472117753. The old PP session closed with collection OFF. An installation check and dedicated deployment identity confirmed the installed controller SHA-256 `a72679fde847b69ab7e84671e34b3bdc0464791d3ddf16502adc37a12511f7fe`. The PP deployment profile now references that proof. The combined application release, repair of 5,268 historical structured envelopes, live switch and verified retirement remain distinct qualification steps. [Controller identity evidence](evidence/pp-controller-identity-2026-11-19-a72679fd.json)

## November 19 UTC — PP archive reader qualified with real private Storage

The dedicated history reader used the pp.16 image and four scoped credential files, then authenticated and verified a 64,139-byte PP object against its SHA-256. The private bucket hid an existing foreign-origin key and returned an empty listing. It rejected upload and replacement. A move and a batch delete left the 74-byte synthetic witness at its original key with its original checksum and version. The writer and reader have separate identities. PP retained the witness and its earlier benchmark objects. The operator installed the four reader credentials and root-owned proof before binding the reader to a release. Application retrieval following actual PP partition retirement remains a separate gate. [HTTP and catalog evidence](evidence/pp-storage-reader-qualification-2026-11-19.json)

## November 19 UTC — actual PP connection reuse comparison, read path only

A bounded PP-only test used the restricted history identity to read the same50
already acknowledged A receipts (IDs7314–7363) in four alternating cold/reused
pairs. It ran on pp.16 source8b31c36, while collection and recurring workers
were OFF. Every operation used a separate read-only transaction with the existing
four-second cap, identity checks, and prepared statements disabled in both arms.
Each result matched all50 local receipt hashes and exactly18,000 canonical
metadata bytes, SHA256 `8603b9c455a7b89460b6eb2c2bebf80f99ea3f711396ca0812fe0088e9dd7b28`.

Cold requests averaged632.35ms:324.41ms connection setup and306.58ms transaction/
receipt readback. Reused requests averaged378.34ms including their first physical
connection setup, a40.17% elapsed reduction. The three already-warm reused reads
averaged288.20ms, a54.42% reduction against the cold mean. The read transaction
itself averaged287.07ms when warm; connection reuse removed setup rather than
eliminating receipt verification. Five physical connections served eight separate
transactions. Interface RX/TX counters include TLS/authentication/protocol traffic,
not merely the18,000-byte canonical result.

This is a small actual remote **receipt-metadata read** comparison, not full
sync/import throughput, envelope-payload recovery, localACK capacity, or concurrent
collector performance. No cloud table, outbox, ACK, checkpoint, raw generation,
released transport or policy changed. The owned oneoff and staged local credential
were removed and the controller lock released before the release owner's window.
Complete exact source/byte identities, timings, metadata and scope are preserved in
[evidence](evidence/pp-read-connection-comparison-2026-11-19.json).

## November 19 UTC — archived-history reader access inventory

Live read-only inspection found **zero** Supabase Auth users tagged as the PP archived-history reader, **zero** matching reader Storage policies, and **one** distinct archive writer. On deployed pp.16 the four reader credential files, root proof and release authority marker were absent. The running API had zero reader mounts and no archive writer credential. The collector remained OFF. Fresh generated PostgreSQL 17 tests proved the reviewed policy restricts reads to the PP origin and denies list/insert/update/delete even with a deliberately permissive secondary policy. Actual reader HTTP permission and post-retirement application history remain unqualified.

The existing Admin Auth helper now supports `--purpose history-reader`, emitting a separately named private credential stage and verifying the reader role in the creation response. Fourteen generated provisioning tests passed. Actual provisioning requires a dedicated confirmed machine Auth identity, its two-UID reviewed private Storage policy, an independent authenticated GET and mutation-denial proof, and a marker bound to the exact deployed SHA/image. No identity, policy, live data or running service changed during this inventory. [Operator procedure](../../deploy/preprod/PP_ARCHIVE_IDENTITY_PROVISION.md)

## November 19 UTC — exact PP revision backfill and persistent capture candidate

The restricted structured profile explicitly opts into immutable revision capture
with `TRADEBOT_PP_RETAIN_REVISIONS=true`. Both recurring and one-shot imports
retain receipt-bound canonical envelope bytes atomically; authenticated readback
now also verifies those committed bytes before local ACK. Missing opt-in keeps
the adapter default OFF; malformed opt-in fails closed. The API, collector and
ordinary lifecycle profile receive no additional credentials or cloud flags.

`python -m postgres.pp_revision_backfill --generation-id UUID --through-id ID`
provides a local-only inventory of already acknowledged PP envelopes. Its exact
count and SHA256 must be reviewed before a separate `--execute --expected-count N
--expected-sha256 SHA` invocation, with explicit
`TRADEBOT_PP_REVISION_BACKFILL=true` and capture opt-in. It requires the existing
restricted lifecycle/history mounts and PP one-shot identity, never admin keys.
The reviewed upper ID is mandatory; newer local rows are outside the repair.
Each <=50-row/256KiB page checks existing exact receipts, appends original bytes,
then independently reads and matches every envelope. Whole-scope limits are
10,000 rows, 512 pages, 64MiB of envelopes and 1,800 seconds; each cloud operation
retains its four-second deadline. No local ACK, projection, checkpoint, raw or
retirement mutation occurs. Partial cloud commits remain retained; reconciliation
and idempotent replay use the same reviewed count/digest, with no guessed cursor.

Source qualification includes a generated 5,268-row/106-page repair, corruption,
changed scope, outage/partial-commit replay, deadline, local acknowledgement and
origin guards. Isolated PostgreSQL17 exercised receipt-bound multi-page replay,
exact original decimal bytes and unchanged current projection/checkpoint. Three
native PostgreSQL17 tests passed; generated25-row authenticated readback with
100ms round trips took0.853s including committed envelope verification (import
1.516s), not live pooler performance. Local pinned-backend suite314 tests passed
with36 explicit environment/platform skips; deployment controls190 passed with5
platform skips. Full exact-source CI/release and the real bounded backfill/capture measurements remain
required. No host/cloud operation was performed by this source milestone; cloud
migration state is recorded separately by the operator. Safe live removal and
complete A/B verification within30minutes remain independent open gates.

## November 19 UTC — measured PP → Supabase raw transfer passed

Ten synthetic objects matched the ten compressed chunk sizes measured from the 4,845 retained A events. Uploading 620,549 bytes took **5.105 seconds**, immediate authenticated byte-for-byte readback took **8.612 seconds**, and a second authenticated readback took **0.450 seconds**. Total elapsed inside the probe was **14.564 seconds** across 31 requests, including machine authentication. A separate private catalog query matched all ten keys and lengths. The test objects remain in their isolated synthetic generation.

PP stayed on pp.16 with its collector OFF and no pending structured records. The benchmark used the existing PP Storage identity and ordinary egress. The one-shot container was removed. These measurements qualify transport for this fixture’s size. The actual raw generation has not been sealed or retired. A real two-market run still needs simultaneous dashboard/prediction freshness, new structured arrivals and acknowledgements using the 50-row service, raw archival and A’s complete retirement/replay evidence. Historical revisions and retirement authorization have separate gates.

[Exact scope](evidence/pp-raw-transfer-scope-2026-11-19.json) · [Per-object timings and reconciliation](evidence/pp16-raw-transfer-result-2026-11-19.json)

## November 19 UTC — 50-row recurring synchronization deployed on PP

Release `v0.2.0-pp.16` runs on PP at `8b31c369d8576bc829805e8764d0b2a3a23dbb44`. [Exact CI](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44462245847), [publication](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44464395647), [manual deployment](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44464522646) and [ready-off transition](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44464821715) passed. The deployed API/SSE and schema smoke used generated data. A separate read-only PP query confirmed no collector session, zero pending PP structured records and no collision with the proposed synthetic Storage generation. The reserved cloud prefix contained zero objects. The temporary private runner deregistered.

The existing 5,268 structured records were verified on pp.15. The installed 50-row change requires fresh runtime evidence when new records arrive. Representative raw PUT/GET timing and the combined live collector / prediction / dashboard / archive run remain open. [Deployment and bounded preflight evidence](evidence/pp16-ready-off-2026-11-19.json)

## November 19, 2026 UTC — recurring structured drain clears all retained A rows

On PP release `v0.2.0-pp.15`, the installed recurring worker acknowledged **5,243 A records across 210 pages in 431.490 seconds (12.15/s)**. The slowest page took 2.677 seconds. The run ended with zero retries, zero holds and zero pending records. The operator stopped the idle worker and confirmed it was OFF. Independent Supabase and PP queries matched all 5,268 origin/generation-scoped outbox IDs and content hashes, including 25 acknowledged by the preceding probe. The structured checkpoint reached ID 12789.

The most recent retained live interval created 3,738 outbox records in 282.031 seconds (13.25/s). The measured 25-record worker drained slower than that arrival rate. Collection remained OFF for the transfer, so concurrent headroom remains open.

With the collector OFF, a read-only pass packed A’s 4,845 raw events into 10 chunks totaling 620,549 compressed bytes in 5.299 seconds. Each chunk held 47,101–66,029 bytes. These bytes stayed in memory on PP. The available live raw worker accepts only sealed generations, and the synthetic Storage probe has a much smaller fixed payload. Representative raw upload/readback time and full seal-to-retirement time remain open. The A/B switch and deletion were held.

[Measured page durations, raw sizes and reconciled digest](evidence/pp15-recurring-drain-2026-11-19.json)

## November 19, 2026 UTC — real PP structured page verified in Supabase

Release `v0.2.0-pp.15` from `7175fc60fbb4d06caa8fb47f41221d34783d3d23` passed [exact CI](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44441802100), [publication](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44442308753), [PP CD](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44442439908) and [ready-off](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44442754589). API/SSE and schema smoke passed on generated data. The authorized structured probe then used real retained PP records while collection was OFF.

- All 25 records (IDs 7314–7338) passed authenticated projection and receipt readback. PP acknowledged exactly those IDs. Its pending count fell from 5,268 to 5,243. An independent Supabase query found 25 distinct receipts for the exact origin and generation, previously zero, and checkpoint 7338.
- Docker process elapsed time was 5.954 seconds (4.20 records/s). End-to-end controller time, including SSH and container management, was 9.265 seconds (2.70 records/s). These timings cover one cold invocation. Sustained drain throughput and headroom over live arrivals still need measurement with the persistent worker.
- The raw A generation remained local. PP has yet to demonstrate the complete seal, raw upload, fresh verification, protected history, reader drainage and authorized retirement within 30 minutes while B persists new writes. The collector and retirement remained OFF throughout this probe. The preceding pp.14 failed attempt remains recorded.

[Exact page, timings and release evidence](evidence/pp15-structured-page-2026-11-19.json)

## November 18, 2026 — PP transaction-budget pipeline candidate (source only)

- pp.14 failed its first real 25-row page with PostgreSQL SQLSTATE `25P04`
  (`transaction_timeout`); the `idle in transaction` command tag does not make
  this an idle-session timeout. No cloud receipts committed and no local ACKs
  advanced. The unchanged four-second request cap remains in force.
- Candidate transport batches advisory entity locks, pipelines distinct initial
  projection reads and FK-ordered writes, and pipelines authenticated projection
  readback. Repeated mutable keys advance through checked prior revisions in
  memory. Receipts/checkpoints remain one atomic transaction; exact immutable
  revision payload retention remains explicitly opt-in and its migration is not
  applied by this source change. Ambiguous-commit replay still verifies exact
  receipts, rather than treating the previous exception as proof of rollback.
- Disposable native PostgreSQL 17 qualification: nine applicable transport tests
  and thirteen envelope/connection tests passed. A generated 25-row page matching
  the real type mix (12 candles, 12 revisions of one current-price key, one
  market; 14 projection keys) passed with 100ms per round trip/pipeline boundary
  and 200ms per connection. With exact revision retention enabled, import took
  about 1.53s across 12 observable waits, followed by exact readback and recovery
  of all 25 immutable envelopes. A separate FK-dependent page imported in about
  1.10s/10 waits and read back in about 0.54s/5 waits. These are generated timings,
  not a live pooler performance claim; protocol handshakes are not individually
  counted. The supplied history-only cluster lacks local ops tables, so the
  local generation/ACK test remains for the full isolated CI environment.
- Remaining gates: exact-source full CI, newly qualified candidate, bounded real
  page import/readback/local ACK evidence, then sustained verified-and-ACKed
  throughput exceeding the observed arrival rate. A page PASS alone establishes
  neither catch-up capacity nor continuous archive operation. No cloud retry,
  host deployment, live retirement, or production action is authorized by this
  entry; live retirement remains disabled.

# BTC Intelligence Rebuild Plan

## November 19 — PP revision authority and exact retirement source

At 05:38:37 UTC the reviewed additive Supabase migration
`20261119020000_pp_structured_revision_payloads.sql` was applied, SHA-256
`a29766873eb0ffe8c7e33522931ae0c6eb1a41dbb7dffc96122b4403c1b98d92`.
The new table had zero envelopes, two PP-origin RLS policies and a PP login
with SELECT/INSERT only. No ordinary anonymous, authenticated or service-role
table grants were present. All 5,268 PP receipts remained. Existing receipts
need exact local-envelope backfill and verified reconstruction.

The local PostgreSQL migration `0003_pp_retirement_authority.sql` adds an
owner-issued ticket for one PP A or B generation. Local migration, issuance,
deployment and actual retirement are separate. The proposed operator sequence:

1. Verify the exact released image, restricted history-reader identity,
   recovery of the reviewed archive through that reader, protected references,
   fresh seal, active collector and its opposite slot. Check the local inventory
   fits the deadlines. Record the reader evidence SHA-256.
2. An authorized operator must establish a change freeze covering **all**
   privileged Supabase policy/object/database mutations through local commit,
   record its scope, responsible privileged actors, expiry and SHA-256, and
   explicitly accept the trust boundary. This is a procedural control for
   trusted administrators; a service key or project owner can bypass ordinary
   Storage RLS. Hold if an actor or path is uncovered or a policy change is due.
3. With the PP migration role, use `deploy/preprod/issue_pp_retirement.sql` via
   `psql -X -qAt -v sealed=... -v collecting=... -v seal_hash=... -v row_count=...
   -v release_sha=... -v policy_epoch_hash=... -v history_reader_proof=...
   -v freeze_started_at=... -v freeze_ends_at=... -f ...`.
   Send its sole result directly into a private, mode-0400, one-shot file.
   Bind that file at `/run/secrets/pp_retirement_ticket` only in the exact
   release's supervised one-shot container. Supply explicit ISO timestamps with timezone for the attested freeze, at most 295 seconds long. The ticket expires at the earliest of the attested end and the standard two-minute limit. The two-market profile uses the earliest of the attested end, issuance plus 295 seconds, and the original seal plus 30 minutes. Missing, expired or future freezes yield no ticket.
4. With the existing PP verification flags and exact four target arguments,
   enable `TRADEBOT_PP_EXACT_RETIREMENT=true`, bind the verified release and
   evidence digests via `TRADEBOT_PP_VERIFIED_SOURCE`,
   `TRADEBOT_PP_POLICY_EPOCH_SHA256`, and
   `TRADEBOT_PP_HISTORY_READER_PROOF_SHA256`, and pass
   `--retire-with-pp-permit` to `python -m postgres.pp_retirement_verify`.
   No API or recurring worker exposes this operation. The generation and
   manifests stay locked locally through complete fresh reads, new opposite-slot
   commits, a final reference/reader check, a 5 ms DDL lock wait and commit.
   The transaction consumes the ticket, records retirement and drops the exact
   registered child. An exception before commit rolls all three changes back.
5. After any ambiguous process/connection result, check the exact child,
   generation state and ticket consumption from the migration identity before
   considering any retry. Revoke an unused ticket via its exact ID on failure,
   remove the one-shot mount, release the change freeze, then verify API history,
   predictions, active B persistence and available disk against the same target.

No live permit or local DROP has been issued. The 30-minute seal-to-removal
target still requires actual PP evidence. Production remains outside this route.

## November 19 — bounded two-market final verification profile

Default PP and production archive/readback limits remain in force for ordinary
cycles. The PP operator can select `--two-market-window` with
`TRADEBOT_PP_TWO_MARKET_READBACK=true` for one reviewed seal and its actual
B successor. This mode uses 192 budgeted calls, 128 MiB cumulative compressed
raw and decoded structured envelopes, 500 rows per page, 2 MiB per raw object,
4 MiB per decoded page, four seconds per remote operation and **240 seconds
maximum final work**. The earlier of the work deadline and the persisted
database seal time plus 30 minutes stops work. Startup alignment, archive
delays and time already spent in B cannot reset the seal clock. Local manifest
and generation locks, complete authenticated readback, evidence, reader
drainage and B persistence checks still apply. Generic limits remain 24
calls/16 MiB/20 seconds. Full PP runtime and cloud timing are outstanding.

Sizing includes the original 4,845 raw and 5,268 structured records plus up to
45 minutes of A (startup alignment plus two complete markets). The measured
804 raw rows/minute and 13.25 structured rows/second project to 41,025 raw
and 41,043 structured, about 83 objects and 83 structured pages at 500 per
call plus machine authentication. Read-only measurement on PP found
8,309,661 canonical bytes across all 5,268 structured records and 11 pages.
The largest 500-row page was 842,854 bytes (about 1,577 bytes/row overall). A linear extrapolation gives
roughly 65 MB structured plus 5.25 MB compressed raw before newer projection
envelopes or a larger workload. Every actual sealed generation still requires
its own local inventory. These bounds cover a qualification attempt, not a
production sizing claim. The earlier ten-object synthetic transfer measured
14.564 seconds for upload plus two verified reads; this does not measure
full-window cloud, database or filesystem performance.

The generated native PostgreSQL 17 peak scenario prepared and re-read 41,025
raw rows and 41,043 structured records using the isolated in-memory archive.
It charged 166 read calls and 65,689,621 bytes while B committed 83 writes on
separate database connections. Preparation, archival, inventory and fresh
readback together took 36.39 seconds locally. An expired 30-minute window
issued zero further cloud calls and retained A. The generated fixture omits
real network delays and uses synthetic structured revisions. No PP drop or
budget change was applied by this work.

Run inventory first. After the exact scope passes, a qualified operator may
pass `-v window_profile=two_markets` to the existing ticket issuer. This
ticket lasts at most 295 seconds within the existing five-minute SQL maximum
and expires by the seal deadline. Standard issuance remains two minutes.
Inventory never issues a ticket. If commit acknowledgment arrives after the
deadline, record the confirmed committed result as late and fail the timing
criterion. Keep A on any precommit failure.

## Current PP checkpoint — November 18, 2026

### pp.14 deployment and real structured history result — November 19 UTC

PP deployed **v0.2.0-pp.14** at `1a46b80` and entered ready-off. Its collector stayed
OFF. [Exact CI](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44437167348) · [Publication](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44437594161) · [PP CD](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44437722926) · [Ready-off](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44438049908)

The one-use `history_v2` proof **FAILED** on real outbox IDs 7314–7338. The page
contains twelve candle identities, twelve price revisions sharing one identity and one
market. Supabase logged SQLSTATE `25P04`, FATAL, command tag `idle in transaction`
at 01:37:24.196 UTC for the restricted writer role. Session start was reported at
01:37:20 UTC with one-second precision. The log did not identify the last completed SQL
statement. The owned probe exited 1 and was removed. The local backlog remained 5,268,
local acknowledgements remained zero and independent cloud reads found zero matching
receipts both before and after. The pp.12 failure remains recorded separately.

Hold the live test while the exact structured page cannot complete inside its existing
transaction budget. Diagnose the verified page shape and sequential network round trips,
qualify a changed transaction path with exact-content and atomic-rollback checks, and
reconcile the exact identities before a reviewed successor attempt. No raw upload,
switch, retirement or production mutation occurred during this checkpoint.
[Sanitized evidence](evidence/pp14-structured-page-2026-11-19.json)

### Optional archived-history reader for PP

The API uses its existing local application login for read-only history queries. For explicit
archived-history requests it can mount four separate `history_reader_*` credential files.
The PP API remains UID 10001. Reader files are individually owned by 10001 with mode 0400
under the existing root-managed runtime-secret directory. The API receives no lifecycle,
structured database, archive-uploader, admin or service key. Ordinary dashboard and prediction
queries continue using the local data path.

Activation requires a distinct Supabase Auth UID with authenticated role and administrator-set
`tradebot_role=pp_storage_history_reader`, `tradebot_origin=pp-live-pp`. Review the private
Storage policies in `supabase/review/pp_history_reader_policies.sql.in` before applying them
for that UID and the exact existing uploader UID. Verify scoped authenticated GET, denial of
listing, wrong origin, upload, replacement, move and deletion, and uploader independence
through the real restricted HTTP identities before activation. Keep the sanitized proof.
The generated SQL fixture deliberately grants broad authenticated rights and verifies the
reader-specific restrictive policies still deny mutation, listing and off-origin read.

The exact release's PP operator can then bind the proof in root-owned mode 0400
`/etc/tradebot/pp-runtime/history_reader_authority.json` with precisely these fields:
`source_sha`, `image_id`, `scope=pp_raw_get_only`, `reader_uid`, and `policy_proof_sha256`.
The accompanying root-owned mode 0400 `history_reader_proof.json` contains exactly
`project_ref`, `bucket=market-raw`, `origin_id=pp-live-pp`, `reader_uid`,
`effective_role=authenticated`, `authenticated_get=pass` and the ordered denied operations
`wrong_origin, list, upload, replace, move, delete`. The controller checks its exact hash
and fields. Presence selects the optional API-only Compose overlay on entry to the live profile.
A missing marker leaves cloud history disabled. A stale or unsafe marker blocks the transition.
A subsequent release needs its own binding. Roll back through the existing leave-to-generated
transition and remove the marker before another unqualified activation.

The role/policy fixture and rendered profile are generated checks. Live reader provisioning,
HTTP rights, actual archived history after removal, privileged mutation fencing and
one-generation retirement retain separate gates. This profile does not enable removal.

### Archive history API integration candidate

The API can explicitly configure a bounded historical reader with
`TRADEBOT_PP_ARCHIVE_HISTORY=true` under the exact PP live origin. It admits
one historical request at a time, validates generation origin and creates a
generation-scoped Storage reader only for retired raw. Local reads use the
existing database credential in read-only transactions. Returned archive data
passes the existing checksum/identity decoder. Cloud failures return unavailable
through the actual history endpoint.

The new factory and API tests passed locally with the pinned backend requirements
(22 application/history tests, two platform skips). Runtime Storage mounts and
actual post-retirement retrieval remain qualification gates. This source slice
does not activate the option on PP. The running collector reads RAM/local
PostgreSQL independently of explicit historical requests.


The private PP deployment identity verified installed controller `86ba11c5a23b` from source `886e6ba740` for the revised structured transfer. The pp.14 application and exact-page timeout remain recorded separately. Source qualification alone leaves collection and retirement OFF. [PP controller identity run 44441240976](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44441240976)

### Recoverable structured revisions in private Supabase history

The proposed additive migration `20261119020000_pp_structured_revision_payloads.sql`
preserves the canonical UTF-8 envelope bytes for each exact
(origin, generation, outbox ID). An insert must match the envelope SHA-256 on
its existing receipt. The restricted PP role may append and read its own origin.
Rolling the live projection forward leaves earlier exact decimal strings, source
times and provenance recoverable. Generated PostgreSQL tests exercise old
receipt backfill, retries, payload corruption, limited retrieval, isolation and
forbidden mutation. A stored receipt alone still cannot reconstruct its input.

The opt-in importer writes projections, receipts and envelopes in one database
transaction. A bounded backfill needs exact locally retained envelopes and
existing matching cloud receipts; missing or conflicting evidence stops the
operation. Retrieval by IDs authenticates the connection and recomputes hashes
from returned bytes. The migration has not been applied to Supabase, runtime
capture is OFF, old receipts have not been backfilled and production is
unchanged. Measure the additional bytes before promotion. The privileged
archive-mutation gate for local removal remains independent.

### PP and production captures of the same venue event

**Implemented.** Archive, receipt and checkpoint identities include origin and
generation. If PP and production observe the same tick, both captures keep
their source and receipt timestamps, provenance and archive identities. Stored
capture identity alone does not establish overlap between the two feeds.

**Planned.** A common Supabase dataset view may count an event once when its
venue, feed and stable venue event ID identify the same event and its exact
source content agrees. Keep links to every original capture and its observation
time. Preserve both payloads and flag the conflict when the same venue identity
has different source content. Missing stable venue IDs leave overlap unresolved.
Keep environment-specific prediction IDs, calculation results and local capture
IDs independently addressable. This checkpoint adds no canonical-event schema
or cross-origin deduplication to the archive writer.

### PP retirement readback of prices that advance in B

The PP diagnostic compares every requested sealed structured envelope against
its original local record and receipt. In the same PostgreSQL read-only
repeatable-read transaction it checks the generation checkpoint, locates the
highest outbox ID per affected entity across this origin, verifies any newer
revision and its own generation checkpoint, and compares the current projection
to that authenticated revision. Missing immutable payloads, ambiguous IDs,
changed projections, deadline expiry and insufficient read budget preserve A.
The collector can continue writing B during the read. The generated PostgreSQL
17 regression fetched A's historical price after B advanced the projected
price and rejected both a corrupted projection and a missing newer envelope.

The PP operator confirmed at 02:19:42 UTC on November 19 that the cloud
revision payload table was absent. Runtime capture, migration and exact
receipt-bound backfill have separate qualification. The last measured A had
4,845 raw rows and a peak of 804 rows in a UTC minute. The recurring archive
worker handles up to 500 rows per object with 128 manifests. The final proof
currently has 24 requests, 16 MiB and 20 seconds for all raw and structured
reads combined. A two-market run at that peak would put about 28,965 rows in
A, requiring at least 58 raw reads alone. A 30-minute deadline and the ability
to retire a live A remain unqualified. The diagnostic grants no deletion
authority. The hosted privileged-mutation boundary still requires a decision.

Use the same exact-target PP diagnostic with `--inventory-only` to compute a
local preflight without contacting either cloud transport. It reports manifest
bytes, per-object limits, exact local outbox pages when feasible, minimum
request/envelope bytes and the conditional allowance for newer B revisions.
An impossible minimum returns HOLD before any request. Both the inventory and
actual readback share the existing time budget. No estimate certifies latency,
wire-protocol overhead or remote immutability. The November 19 actual A
inventory reported 4,845 raw rows packed into ten objects (620,549 compressed
bytes) and 5,268 structured records. That is at least 21 read calls at 500
records per page plus the initial PP machine authentication (22 budgeted calls). The forthcoming A seal may have different coverage. The
native CI case uses those row counts with generated values, exercises 10 B
commits during fresh A raw reads and keeps the local A relation.

### Exact sealed PP readback and local retirement

The one-shot source command `python -m postgres.pp_retirement_verify --sealed UUID
--collecting UUID --seal-hash SHA256 --count ROWS` uses the bounded, PP-only
archive probe credential mounts and requires the extra explicit
`TRADEBOT_PP_RETIREMENT_READBACK=true` opt-in. Supply reviewed identities from
the local retirement report. The command rechecks sealed local contents against
fresh authenticated object reads, pages through acknowledged structured outbox
records for exact authenticated receipt/projection comparisons, checks protected
references and readers, and requires committed rows to advance in the named
opposite slot during the same verification. Its single operation uses the
existing bounded request/byte/time policy. A changed projection, transport
timeout, request exhaustion, or missing proof keeps local data. It issues no
deletion token. Cloud execution and full-window performance are outstanding.

The isolated generated retirement exercise spans multiple structured pages,
rejects changed targets, missing later-page receipts, and real unleased SQL
readers, and rehearses failure after the physical DROP before commit. Local
partition removal and retired state commit atomically; a rolled-back DROP
preserves raw A, and durable B rows survive. The code bounds DDL lock waits
to 5 ms to avoid queuing behind an unmanaged reader during B collection.
The actual PP command retains the local generation. Privileged service keys
bypass Storage RLS, and the hosted S3 compatibility documentation excludes
immutable Object Lock. A final read immediately before local commit cannot prove
the remote object remained immutable in the intervening interval. A reviewed
enforceable mutation fence or an explicitly revised authority policy and the
supported live archive-history path are required before enabling real removal.
[Supabase Storage RLS](https://supabase.com/docs/guides/storage/security/access-control)
and [S3 compatibility](https://supabase.com/docs/guides/storage/s3/compatibility).

### Sealed PP retirement decision

After the exact A → B switch, start with the UUID of sealed A. The read-only diagnostic
`python -m postgres.pp_retirement_report <sealed-generation-uuid>` runs inside the
deployed PP lifecycle container using its existing lifecycle DSN. It binds A's stored
authenticated readback receipts to its SHA-256 catalog and checks raw row count, pending
structured history, protected outbox references, current reader leases and two separate
committed B samples. A query timeout, incomplete coverage or missing evidence reports HOLD.
An unchanged B count in the two-second sample means advancement was unobserved in that
sample. This command makes no cloud calls and grants no retirement authorization.

**Decision for live PP:** retain sealed A through this checkpoint. Before an explicit
one-generation retirement can be authorized, demonstrate fresh authenticated verification
of all exact raw objects and protected structured receipts, reconstruction through the
history API, an enforceable cloud mutation fence through local removal, and exclusive
reader drainage. Bind removal to the exact generation, manifest digest and collector's
other active slot in a single crash-safe transaction. Recheck mutable state inside it;
on lost proof or a failed check keep A. Qualify interrupted execution and post-removal
archived-history access on isolated data. The live implementation still enforces
generated-only retirement. Release/deployment of the diagnostic alone never changes it.

`preprod` source `2e38ecdf693fed194960fc8fd67286854decb221`
passed exact CI 44422595480 and was published as `v0.2.0-pp.12` in
run 44423143306. Manual PP CD
[44423321845](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44423321845)
**PASSED** in generated-only scope. PP application services run the exact
release; PostgreSQL and the private API/dashboard are healthy. A separate
one-use [mode transition 44423758592](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44423758592)
entered `PP_LIVE_READY_OFF`: the PP collector is **OFF**. Raw archival,
retirement, paid AI and production changes remain **OFF / not performed**.

The first exact-generation, 25-row `history_v2` structured probe consumed its
single-use authorization and **FAILED**. Supabase logged SQLSTATE `25P04`,
terminating the restricted PP session for transaction timeout about four
seconds after authentication. Read-only reconciliation found **zero** matching
`pp-live-pp` cloud receipts/projections/checkpoints and **zero** local outbox
ACKs from the selected 25 rows. The precise slow SQL operation is not yet
identified. Do not retry the unchanged probe or claim cloud sync PASS. Improve
round-trip efficiency and sanitized phase diagnostics, then qualify an exact
successor before a separately bounded cloud attempt.

The one-use permit protects this first probe; it is **not** the intended
continuous sync policy. A default-OFF finite drain exists in source, but has
no deployed schedule or service route. The last observed `pp-live-pp` pending
backlog was 5,268 rows. The previous bounded live session added about 13.3
rows/second, so sustained ACK throughput and outage runway must be measured
before another long live run. Separately, the PP release inventory currently
counts **all** outbox rows per origin against 10,000, including ACKed rows;
ACK does not free that lifetime release bound. Any bounded-ledger solution
must preserve verified evidence for protected references and release recovery.

PR #131 prepares a default-off, root-controlled recurring service for the second checkpoint.
It selects sealed generations first, sends a page at a time, acknowledges
after authenticated readback and backs off after a cloud outage. The root installer starts, stops and inspects the exact worker using the
reviewed probe network and mounts. A durable owner record fences CD and mode
transitions until the operator proves the worker stopped. Release, host
installation and sustained throughput qualification are pending.

### November 19 UTC — synthetic Storage transfer scope before live rotation

The measured active PP generation packed to 10 chunks totaling 620,549 bytes. The prior PP Storage proof contains a single 126-byte object. The reviewed raw worker requires a sealed generation. Prepare an independent PP transport measurement with 10 clearly synthetic gzip objects matching all measured chunk sizes, using the deployed restricted PP writer and the existing PP network. The operator script’s default prints the exact scope offline.

The single execution may perform up to **31 requests in 60 seconds**, with four-second request deadlines. This includes machine authentication, 10 create-only uploads, 10 immediate authenticated reads and 10 final authenticated reads. Expected body transfer is 620,549 bytes up and 1,241,098 bytes down. Existing keys, unexpected HTTP responses, oversized or different bytes, deadline expiry and additional calls stop the operation. Partial uploads stay retained for reconciliation. The operator must bind the exact tested script, PP host/image, four existing Storage credential files, empty synthetic namespace and confirmed collector-OFF state. No SQL credential is mounted and the probe cannot record local manifests or retire a partition. Its results qualify transport for this footprint only. The 30-minute seal-to-retirement measurement remains a separate live checkpoint.

[Reviewed keys, sizes, source hash and execution scope](evidence/pp-raw-transfer-scope-2026-11-19.json)

### November 19 UTC — qualified recurring page comparison on isolated PostgreSQL

The real PP 25-row worker cleared its backlog at 12.15 acknowledgements/s versus 13.25 arrivals/s during the latest retained live interval. The source candidate selects 50 rows for the recurring worker. The one-shot operator probe remains capped at 25. Requests remain serial with a four-second deadline each, two authenticated operations per page, 256 KiB decoded per page and the existing 100 ms unlocked handoff. Oversize pages are bounded by the existing byte-aware query.

On an isolated PostgreSQL 17 database, generated cases covered mixed candles/price revisions, one mutable price key and distinct candle keys. The fixture added 100 ms per SQL round trip or pipeline boundary and 200 ms per remote connection. All 600 rows were verified remotely and acknowledged locally. Each case includes local page reads, authenticated readback, exact revision payload retention, local ACK and the unlocked handoff. On 25-row pages the cases sustained 10.47–10.51 rows/s. On 50-row pages they sustained 15.95–18.45 rows/s. Slowest 50-row upload was 2.463 s, authenticated readback 0.800 s and full page 3.348 s. Production pooler performance, the behavior of future page shapes and sustained overlap with a collecting B remain unqualified. PP's deployed release and its real collector stay held at the recorded baseline.

[Generated comparison and bounds](evidence/pp-structured-recurring-50-generated-2026-11-19.json)

### PP release inventory implementation

The release controller now fingerprints the complete outbox, including payloads,
ACK timestamps and protected-reference identities. It checks the 10,000 pending
rows per origin admission bound independently. For raw and core it fingerprints
all previously reviewed identity/hash columns across the full table. SHA-256
pages keep the inner aggregate small. Read-only preflight exercises the scans
before stopping services. The same evidence is compared under the writer fence
and during recovery. Server statements have a 19-second timeout within the
existing 20-second command budget. Cost still grows with history, and eventual
compaction of independently verified evidence remains a separate storage task.

Generated PostgreSQL 17 exercised 10,103 lifetime rows, including 10,100 ACKed
rows. Mutations above the old boundary changed the raw and outbox fingerprints.
A 10,003-pending fixture stopped admission and inventory. Local controller suite
ran 180 tests with four platform skips. PP runtime deployment and representative
scan timing remain open.

### Two-market PP window qualification candidate

For the explicit PP qualification overlay, A begins its **observation** at the next
complete official BTC 15-minute interval after collector enable. Its earlier
partial data remains part of the sealed raw generation and its archive. Verify
two consecutive exact market IDs and 900-second boundaries with on-time Polymarket
source/receipt evidence in A; switch on the first lifecycle tick after both end.
The operator observer independently checks continuity and freshness. B's 30-minute
observation starts at its actual atomic switch. Keep the verified A until a separate
retirement qualification passes. The normal 72-hour rotation policy still applies
outside this PP test overlay.

The exact ON permit may request up to 4,560 seconds on PP (up to 15 minutes
of alignment, two 30-minute observations and one minute for sampling). ON remains
bounded by the durable PostgreSQL lease and the supervisor. OFF survives restart.
Use controls from a reviewed PP workflow revision that accepts this duration.
For the two-market PP profile, the existing host reserve of 10 GiB free is
checked on the **PostgreSQL data filesystem** at admission and each live
lifecycle tick. The switch itself uses observed market boundaries. A low or
unavailable sample disables the writer lease durably and preserves both slots.
The controller binds the actual Docker volume and read-only mounts before ON;
each worker reads fresh kernel filesystem statistics without reading a secret.
The archived generation, receipt and occupied-slot safety rules still apply.
A historical fixture-size hold remains recorded and requires review.

### PP window qualification measurements

At 00:56:57 UTC on November 19, a pinned read-only PP sample found the
collector OFF, A at 4,845 rows and 9,109,504 bytes, database 60,430,003
bytes, 56,779,476,992 filesystem bytes free, and 1,192,636,416 bytes of
available RAM. Allocated WAL was 33,554,432 bytes. WAL written was
170,415,907 bytes since November 13 at 00:57:11 UTC (whole cluster).
Core relations occupied 14,114,816 bytes including 3,620,864 of indexes;
ops 27,787,264 including 6,569,984 of indexes; raw 9,437,184 including
2,547,712 of indexes; archive 155,648 including 114,688 of indexes.
These are current sizes. Matched live-period samples with the same WAL
stats reset are required for WAL write rate and per-schema/index growth.

An offline estimate uses the November 17 live interval (282 seconds, 3,456
new rows, 6,397,952 additional raw relation bytes and 15,859,712 additional
database bytes). Allow 2,730 seconds of A growth including startup alignment
and the switch poll and 1,860 seconds of B including sampling. The projection
is **71,047,125 bytes for A** and **42,199,258 additional bytes for B**.
Database growth over 4,560 seconds projects to 256,454,918 bytes. The
projected A has 38,303 rows and needs at least 77 of the allowed 128 manifests
at 500 rows per chunk. The actual decoded-byte bound can require more.
A faster feed, large payloads, long readers, transient WAL retention, temp
files, cumulative outbox and upload stalls must be measured during the run.

On November 18 CST the pinned PP operator verified major/minor device 66305
on the host data volume, host lifecycle bind, and their corresponding
container mounts, each reporting 56,779,345,920 free bytes where measured.
The candidate worker sampler independently read 56,779,321,344 free bytes
from the existing read-only mount. This profile has no per-relation size cap.
Observe raw/total growth, free bytes, memory, WAL, live performance and
archive progress. A tested generated relation over 32 MiB exercises the
timer with sufficient space. A low, missing or stale sample keeps PP OFF
until a fresh authorized admission and adequate free space are verified.
The sampler interval permits concurrent growth between measurements.
For recovery explicitly stop collection, verify durable OFF and return to
the qualified generated profile; retain local files and all committed rows.
Production retains its own policy. Subsequent deployment and live acceptance
are recorded separately from these source qualification measurements.

### PP execution sequence

**Resume at step 1.** Receipt batching in PR #130 passed Linux CI at
`a879bc4`. With 34 ms of injected delay per SQL call, 25 rows took 2.921 s
to write (84 calls) and 1.087 s to read back (31 calls). Each operation passed
its four-second limit. Together they yield about 6.2 rows/s before local ACK
or scheduling. At the previously observed 13.3 rows/s arrival rate, a worker
processing one page at a time needs a full 25-row cycle under 1.88 s just
to keep pace. Use actual PP timings to decide what to optimize.
[Source CI](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44425953701)
and [PR CI](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44425963901).

| Step | Work and pass condition | If it fails |
| --- | --- | --- |
| 1. Verify one real page | Review #130, release its exact tested successor on PP with matching controller and profile, and keep the collector OFF. Select 25 pending PP identities. Record connect, write, fresh readback and local ACK timings. Pass when those exact 25 cloud receipts, final values, generation checkpoint and local ACKs agree within the existing budgets. | Reconcile committed receipts against local ACKs first. For another timeout, capture sanitized phase, statement category, elapsed time and query count. Group independent projection reads or pipeline independent writes if network waits dominate. Inspect the specific query plan or lock wait if server time dominates. Reproduce the failed phase before another cloud attempt. |
| 2. Prove recurring sync | Run the existing bounded drain under a supervised PP lifecycle worker. Each cycle reads back committed history before marking local rows synced. Give sealed generations priority. Drain the recorded backlog, verify restart and safe retries with backoff, and measure full-cycle ACK rate, oldest pending age and outage headroom. Require measured spare throughput over observed arrivals and a shrinking backlog during catch-up. | Keep pending rows durable. Investigate the measured slow phase and repeat that test. A single successful page establishes correctness only. |
| 3. Qualify the release inventory | In parallel with step 2, fix the deployment inventory that counts synced rows toward its 10,000-row limit. Test with more than 10,000 lifetime rows, including protected and pending records. Prove release and recovery still detect missing or changed evidence. For continuous operation, qualify bounded storage for synced evidence, including exact recovery and reference checks. | Preserve original rows until their replacement evidence passes. Before starting a long trial, verify that its projected growth leaves the deployment and recovery paths usable. |
| 4. Exercise the real A/B flow | Prepare the sealed-generation archive route and exercise corruption, outage and reader-hold cases on generated data first. After a capacity decision, observe two full consecutive official 15-minute intervals in A, switch to B, and observe B for 30 minutes from the actual switch. Allow startup alignment within the exact bounded lease. While B acknowledges live writes, upload sealed A's raw objects to private Storage, download them with the runtime identity, and match checksum, count and identities to the manifest. Record B's writes during verification, dashboard generation, query latency, zero two-second API timeouts, sub-second save/heartbeat delays and feature/input ages within 30 s. Report each observed switch. | On an archive error retain A and record B's remaining runway. On a feed or rollover error retain the evidence and report the affected interval. Finish the trial with PP collection durably OFF. |
| 5. Qualify retirement | After verified archive coverage, prove protected references, archived history/replay, reader drainage and protection against archive mutation through removal. At the separate retirement gate, retire the eligible PP partition and verify safe slot reuse and actual disk/WAL usage. | Keep the partition. Production cutover, first production archive verification and retirement enablement retain their separate Phase 1.75 gates. |

PostgreSQL applies the timeout to the whole transaction. Psycopg can send
independent statements together to reduce network waits. PostgreSQL supports
retiring a partition as a unit, with locking requirements that the PP trial
must measure. These mechanisms address different stages of the plan.
[Transaction limits](https://www.postgresql.org/docs/17/runtime-config-client.html#GUC-TRANSACTION-TIMEOUT),
[Psycopg pipeline behavior](https://www.psycopg.org/psycopg3/docs/advanced/pipeline.html),
[partition maintenance](https://www.postgresql.org/docs/17/ddl-partitioning.html#DDL-PARTITIONING-MAINTENANCE).

### Measured PP raw archive capacity

Bounded read-only PP inventory on November 19 UTC found slot A collecting,
4,845 raw rows and 9,109,504 allocated partition bytes. Nonempty minutes
peaked at 804 raw rows/minute. A 30–45 minute interval at that observed peak
would add 24,120–36,180 raw rows. Treat this as a scenario and record actual
counts at switch. The existing 25-row page and 128-manifest diagnostic can
cover at most 3,200 rows including existing data. The current A already exceeds
that bound. PR #132 makes this an early hold and exercises durable two-page
resume, corrupt/failed readback, and B commits during each readback in CI.

The opt-in `postgres.pp_sealed_archive --execute` entrypoint and
`runtime.sealed-archive.compose.yaml` overlay select sealed PP generations and
resume durable manifest progress. Each cycle reads at most 500 raw rows and
4 MiB decoded, verifies the restricted Storage readback, and yields between
pages. Transient Storage failures back off up to 60 seconds. The worker waits
for structured evidence to sync first. Synthetic payloads at 4,845 and 36,180
rows passed in 10 and 73 pages respectively with an injected readback failure.
The 128-manifest limit still applies, so the 64,000-row maximum is lower for
large payloads. A bounded read-only PP inventory of the actual A rows, ordered as the archive
worker reads them, found ten 500-row-or-smaller pages, largest conservative
page size 1,720,208 bytes and largest single-row allowance 11,860 bytes. These
fit the 4 MiB decoded budget. Measure compressed sizes and throughput during
the PP run. Root operator commands `sealed-archive-start/status/stop` use a
distinct ownership record, exact image, private Storage credentials and the
staged lifecycle DSN. The archive container mounts no history login. Deploy and
mode transitions require both workers stopped. The recurring raw and structured workers
use independent origin locks, so slow Storage readback leaves the structured
worker free to ACK. The diagnostic that can perform both operations takes
both locks. Stop waits for the owned
container to exit and preserves its fence if cleanup cannot be confirmed.

For larger generations, resume from the last verified manifest using the
indexed generation and manifest sequence, fetch exactly one bounded raw page,
then atomically advance its cursor after create-only upload and authenticated
readback. Stream ordered manifest pages for final coverage validation under
a repeatable snapshot, preserving the existing seal digest format. Include
history retrieval in the pagination change. Qualify with at least the observed
4,845-row shape and a 36,180-row generated burst, independently measuring
archive throughput against B growth and available disk. Exercise page 129,
crash after upload, corrupt readback, and generation identity on restart.
The prepared live host profile marker stays in ready_off even while an
operator lease runs. Prove B's actual continued collection with advancing
persisted event IDs during A verification. Keep retirement at its separate
authorization gate.

Earlier PP releases bounded ON to 1,800 seconds. The two-market qualification
uses the explicitly authorized time budget above. Both
the application and the SQL retirement function restrict partition removal
to generated qualification data. Successful real archive readback keeps A
local. If B reaches its next switch while A occupies the other slot, collection
stops. Continuous live reuse requires separate reviewed PP retirement covering
committed structured history, raw replay, protected references, reader drainage,
remote mutation authority and recovery, plus a durable collector ownership
policy for sessions beyond 30 minutes.

## Current PP release checkpoint — November 18, 2026 CST

**PP PostgreSQL live collection and Supabase runtime sync remain OPEN.**
PRs [#124](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/124)–[#126](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/126)
merged into `preprod`; their merge-commit CI passed
[44413475851](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44413475851),
[44416354874](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44416354874), and
[44417550120](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44417550120), respectively.
The pp.11 release source was `56e4de51ecaddbe4873945629ee2c24cccb3b6a3`.
Candidate [`v0.2.0-pp.11`](https://github.com/JakeMofa/Trading_Bot_Analytics/releases/tag/v0.2.0-pp.11)
was published in [run 44418143697](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44418143697)
with artifact SHA-256 `0be732be355ee9716d518219c34015855d564f69b299fe6fffaf0b55239d4a90`.
The successor controller SHA-256
`acec846b8876df991026c0437b971d525beef398ff43afa6f7a8e01ac5b80a7d`
was installed; [identity run 44418190583](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44418190583)
passed.

Manual [PP CD 44418602445](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44418602445)
**FAILED before authority consumption**. Source extraction and read-only
preflight passed, but the deployment target profile still expected the old
controller hash `c3fac37cb56945ad74d41188b8e22013a199fe8d656b87be4f4154676d3c9479`;
the installed controller is `acec846b…`. No candidate journal was created.
The unused permit was revoked. The prior four application containers and
PostgreSQL remained healthy; the API returned HTTP 200. No PP application
rollout, collection restart, cloud sync, local retirement, or production change
occurred. GitHub's Node 20 and `ubuntu-latest` notices were warnings, not the
deployment failure. [PR #128](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/128)
subsequently fixed the exact PP controller binding and sanitized future
failure codes; it merged as `f09987c5d4c408bc61ae619bbf8e276d279fe5f4`
with [CI 44421342321](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44421342321)
PASS. [PR #129](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/129)
separately pinned Node 24 Actions and Ubuntu 24.04; it merged as
`2d0a449c9c393b50ba9ccd45e41cb4f326259b70` with
[CI 44421906498](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44421906498)
PASS. Neither merge retried pp.11
or deployed PP. A new exact candidate, controller/profile binding and manual
release remain to be qualified.

## CI runtime annotation correction — November 18, 2026

The failed PP CD run 44418602445 had a deployment-control error and separate
GitHub runner warnings: old pinned actions targeted Node.js 20, and
`ubuntu-latest` was moving from Ubuntu 24.04 to 26.04. PR #129 uses reviewed
Node.js 24 action commits and explicit `ubuntu-24.04` for hosted jobs; the
private PP runner selector remains unchanged. The action versions require
runner 2.327.1 or later, and the observed PP ephemeral runner was 2.338.2.
Local actionlint and pin regressions passed. This is CI maintenance, not the
fix for pp.11's failed controller binding, and creates no database or host
change.

### Earlier pp.10 checkpoint

Small, default-OFF source milestones [#117](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/117)–[#123](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/123)
merged into `preprod`. Their exact merge-commit CI passed: #117
[44241469067](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44241469067),
#118 [44241991946](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44241991946),
#119 [44243636850](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44243636850),
#120 [44406648903](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44406648903),
#121 [44409060049](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44409060049),
#122 [44409967915](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44409967915),
and #123 [44411764423](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44411764423).
The `preprod` tip at that checkpoint was `01c726a6ada7031c7e4681988b03caf392153e58`.
The combined PP controller SHA-256
`c3fac37cb56945ad74d41188b8e22013a199fe8d656b87be4f4154676d3c9479`
was installed and its dedicated-identity
[run 44407788335](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44407788335)
passed. This verifies controller identity, not application or cloud acceptance.

Candidate `v0.2.0-pp.10` was published in
[run 44410565795](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44410565795).
The one manual [PP CD 44411133302](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44411133302)
**FAILED** after its GitHub preflight passed. Its migrate-stage inventory
incorrectly applied a 10,000-row bound to the whole `ops.outbox`: the two
isolated origins held 12,779 rows together (7,511 generated and 5,268
`pp-live-pp`), although each origin was below its own 10,000-row bound.
Controller recovery was unproven. A subsequent bounded manual restoration
returned the four application services to the exact prior image
`sha256:8b3912fd131fec1e6987a7d8cf4242896fbe62f64472aa4600612ca6c7778566`.
Docker timestamps show the PP API stopped at 22:25:29.713719463 UTC and
restarted at 22:31:11.439103596 UTC, an approximately **341.725-second PP
API interruption**. API, dashboard and state returned HTTP 200 afterward;
PostgreSQL remained healthy, and the collector is OFF. No production service
was interrupted. The per-origin inventory correction later merged in #125,
but is **not deployed**. The failed release remains failed despite manual recovery.

PR #122 prepared a fail-closed PP Storage Auth installer; #123 corrected its
publishable-key newline check after the first credential installation stopped
before writing any destination files. Neither merge enables cloud sync. No
PP structured `history_v2` runtime write/readback, sealed-generation raw
archive, local retirement, paid AI, or production PostgreSQL cutover has passed.
The five gates in the next section remain the execution order; dated sections
below preserve earlier evidence.

## PP live convergence checkpoint — November 17 CST / November 18 UTC

**Current result: PP live and Supabase runtime sync are not yet accepted.**
The PP PostgreSQL application and dashboard run. Two bounded live sessions
persisted actual feed data but failed before market-boundary/rotation
acceptance; PP was restored to generated mode with its collector OFF. The
private `history_v2` schema, exact PP grants and restricted login passed
catalog and rolled-back connection checks, but the runtime importer has not
written structured PP rows. A 126-byte private Storage object passed synthetic
upload and authenticated readback; no sealed PP generation has been archived.
PR #115 corrected the PP one-shot credential mount and merged as `6d9fe3e`;
exact merge [CI 44239876261](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44239876261)
passed. That controller and image are still **not installed on PP**.

The last live trial increased pending `pp-live-pp` outbox rows from 1,530 to
5,268 in 282 seconds, about 13.3 net rows/second. With the unchanged 10,000
row cap, the recorded 4,732-row headroom would last roughly six minutes at
that rate. This is a planning estimate, not a qualified future rate. The
25-row/20-second one-shot probe proves only a bounded cloud path; it cannot
support a 20–30 minute live run or clear the backlog by itself. Do not raise
the cap merely to make a trial last longer.

Follow the [current PP execution sequence](#pp-execution-sequence) at the top of this roadmap. The measurements above are its historical baseline.

No paid AI, trading, production deployment, PP retirement or automatic cloud
sync follows from passing an earlier gate. Record one result per gate; a
failed gate keeps its specific next action rather than rerunning an unchanged
trial. Older sections below are dated evidence where they describe superseded
cross-VM collector fencing or a completed candidate as still pending.

## CP6 exact PP structured-origin binding candidate — November 17 CST / November 18 UTC

The next default-OFF code slice narrows the active and sealed structured
workers and private PostgreSQL transport to exactly `pp-live-pp`. The previous
`pp-live-*` constructor rule could admit a wrong PP origin despite the live
`history_v2` policies allowing only `pp-live-pp`. Generated PostgreSQL tests
substitute unique isolated origins in their test process; runtime constructors
retain the exact origin.

`PPHistoryConnectionFactory` reads a private mounted DSN and a separately
mounted CA. It requires the reviewed session-pooler host, project-scoped role,
database, TLS `verify-full`, one pinned Supabase Root 2021 CA certificate,
private file metadata and a bounded connect budget. It rejects extra libpq
parameters, changed bindings and insufficient time before opening a
connection; late connections are closed. Exceptions omit credentials.
The factory is not constructed by a deployed service. The current PP host
holds root-owned secret and CA files **outside** its containers. Local focused
tests passed; exact Linux CI and isolated PostgreSQL cases remain release
gates. No cloud writes, service mount, collector, retirement or production
change is authorized by this candidate. The next independently reviewed slice
must prove an actual bounded PP importer write/readback and outbox ACK while
keeping local retirement OFF.

## CP6 private structured receipt grant candidate — November 17 CST / November 18 UTC

**Historical candidate:** the later bounded operator connection check enabled
the restricted role's LOGIN and passed a rolled-back PP receipt transaction;
see the current CP6 login checkpoint below. The NOLOGIN state and proposed
steps in this section describe the earlier grant-only review.

A generated-only candidate extends the already applied `tradebot_pp_history`
NOLOGIN role with `SELECT`/`INSERT` on `history_v2.structured_receipts`
and exact `origin_id = 'pp-live-pp'` RLS policies. The migration fails if PR
#92's receipt table is absent, its columns/RLS differ, the role has a login or
unreviewed membership, or the role has table privileges on an existing
`public` relation. A read-only cloud catalog check found only the expected
inbound `postgres` ADMIN membership (`INHERIT`/`SET` false), zero accessible
public relations and no receipt table. The candidate does not set a password,
enable LOGIN, grant UPDATE/DELETE, apply cloud DDL, or enable
sync/retirement. A disposable PostgreSQL 17 test passed the PP insert/read and
wrong-origin, mutation, row-lock and public-table denials. PR #92 merged as
`ac32805` with advisory serialization and no row locks on immutable tables or
receipts. The grant qualification applies the reviewed receipt table once
before the grant migration and generated transport test.
The later operator-only connection gate must verify the exact
[Supabase session pooler endpoint](https://supabase.com/docs/guides/database/connecting-to-postgres)
and TLS certificate, set a fresh password with interactive
`psql \password tradebot_pp_history`, and enable LOGIN only after a fresh
role/grant inventory. A credential never belongs in this migration, Git,
shell arguments or logs. Failure closes the role with `NOLOGIN PASSWORD NULL`
while sync stays OFF. Credential creation, TLS/host reachability, actual cloud
readback and the 5,268/10,000 PP outbox drain remain separate gates. The
candidate is not an archive acceptance or retirement authority.

## Active CP6 execution — PP archive identity and private Storage

**Current state, November 18 UTC:** PR #100 supplied the exact-origin
`market-raw` policy template; #104 bound it to the dedicated PP Auth identity,
and #108 amended its authenticated readback operation. Both reviewed policy
transactions were applied to Supabase. A bounded synthetic create-only upload
and later reconcile-only authenticated readback **passed**; the object remains
private and retained. The renewable-token adapter merged as PR #103; complete
PP runtime archival qualification remains open. The structured `history_v2`
role is separate from Storage HTTP. Its earlier NOLOGIN state was superseded
by the bounded PP database login check below; no application service uses
that connection yet. The existing public
Supabase tables contain historical rows; private `history_v2` remains empty.
PP collection, cloud sync, retirement and paid AI were OFF at the last
observed host checkpoint; the cloud probes did not alter that host state.
Production remains unchanged.

This is one bounded sequence with independent small PRs and exact CI:

1. **Operator-only identity provisioning:** Use Supabase Auth Admin API with a
   privileged key held only in a private operator secret file. Create one
   dedicated PP project Auth identity with a generated credential, report only
   its UID and sanitized outcome, and stop on an existing/conflicting identity
   or ambiguous response. No invitation or human dashboard password is used.
2. **Renewable runtime bearer:** Replace the fixed-token-only PP Storage path
   with bounded sign-in/refresh for that identity. Keep the publishable API key
   separate; never install a service-role/admin key on PP. Expiry, revocation,
   timeout, restart and concurrent archive calls must fail closed without
   deleting raw data or exposing credentials.
3. **Exact UID binding:** Render PR #100's reviewed policy only for the
   independently verified PP UID and exact `pp-live-pp` object namespace.
   Confirm private bucket, zero unexpected policies and operation semantics.
   Apply one reviewed migration, then prove a bounded synthetic create-only
   upload, fresh authenticated readback, and denials for wrong UID, bucket,
   origin, listing, overwrite and deletion. Keep all test objects retained for
   evidence unless a separate cleanup scope is reviewed.
4. **PP integration:** Merge the qualified structured-sync/drain changes,
   add the narrowly required `history_v2` receipt grants and cloud connection
   binding, and first drain the measured 5,268/10,000 pending PP outbox without
   collector interference. Then release the exact PP artifact and observe a
   bounded live A→B seal/archive/readback cycle. Do not infer 72-hour capacity
   from a short size-trigger test. Keep local retirement OFF until its separate
   mutation-authority, reference, reader-drain and recovery gates pass.

The first three coding parts have separate evidence below; bounded synthetic
Storage readback now passes. Generated policy denials and one live public
denial do not establish every cross-identity live denial. A passing policy
fixture or synthetic object alone is not full archive acceptance. No
production deployment or Phase 2 work follows from this scope.

### PP Auth refresh-token compatibility — November 18 UTC

A bounded live Auth sign-in returned HTTP 200 with the reviewed identity and
restricted access-token claims. Two adapter compatibility gaps were found:
the opaque refresh token was **12 characters**, while PR #103 required at
least 20; and the Auth response could be gzip encoded, while the adapter
parsed raw compressed bytes as JSON. A separate bounded diagnostic with
`Accept-Encoding: identity` returned uncompressed, valid JSON. The token
value is not recorded. Either gap can prevent the adapter from accepting an
otherwise valid response; the earlier failure is **not** attributed to just
one. These are client-validation defects, not evidence of failed Storage
permission or archive verification. A narrow default-OFF successor removes
the guessed refresh-token lower bound and requests identity encoding, while
strictly bounding and decoding unexpected gzip responses. Generated
sign-in/rotation, compression and failure regressions are the next gate;
fresh authenticated Storage readback and local-retirement HOLD remain
unchanged. No production change follows from this correction.

### PP raw Storage first live probe and readback amendment — November 18 UTC

The first private `market-raw` policy migration is recorded as ledger
`20261118031950` (`pp_market_raw_storage_auth_20261118`), rendered SQL SHA-256
`560e472b8997092961beaaca93c0a2fcb1af36bca853c59c24e8a651f19f3ac5`.
It binds dedicated Auth UID `600b06fc-f121-4a96-a21c-6278b0f38be6` and
the exact `pp-live-pp` origin. Live inventory found two policies, zero mutation
grants and a private bucket. One create-only probe POST returned HTTP 200 and
left a 126-byte synthetic object. Its authenticated GET returned HTTP 400
`NoSuchKey`; remote bytes were **NOT VERIFIED at that first attempt**. Read-only
Storage logs recorded `storage.object.upload` for POST and legacy
`object.get_authenticated_info` for GET, while the installed readback policy
permits only `storage.object.get_authenticated`. The exact object row, UID,
bucket and PP prefix matched. This supports a narrow operation-name amendment;
it does not establish a successful readback.

The successor candidate extends only the authenticated readback policy to
those two operation names. It requires a fresh SHA-256 of the existing two
catalog policies, exact UID/metadata, private bucket and the retained object
before one transactional `ALTER POLICY`. A reconcile-only probe reconstructs
the same key, 126 bytes and SHA-256 locally, then performs authenticated GET
and public-denial GET with **zero POST**. The candidate has generated tests;
at that candidate checkpoint no live policy amendment or second probe had run.
Local retirement remained OFF; PP collection and production were unchanged by
the candidate. See
[readback amendment review](PP_STORAGE_LEGACY_READBACK_REVIEW_2026-11-17.md).

**Bounded PP Storage readback PASS (November 18 UTC):** PR
[#108](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/108) merged as
`83f6a41` after exact-source [push CI 44232805427](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44232805427)
and [PR CI 44232810997](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44232810997)
passed. The catalog-bound patch SHA-256 was
`2527e7642139bb8a04d50a50baf34b1cc5a4cfd261596e380330ddd5283b1d22`;
it was applied as migration `pp_market_raw_legacy_readback_20261118`, ledger
`20261118035125`. Post-checks found the same two exact-UID upload/read
policies and zero mutation grants. A reconcile-only probe of the retained
126-byte synthetic object used **three HTTP attempts, zero POST**, matched
SHA-256 `5589f047e23adedca048ccadb7351f5d6eefb82b55314fdb3676d4a01096b7bf`
and both records, denied public retrieval, and retained the object. Storage
logs showed authenticated legacy info and authenticated object GET returning
200, while anonymous legacy info returned 400. The ephemeral bearer was
removed. This clears only the **bounded synthetic private Storage readback**
gate. Structured `history_v2` write/readback, full sealed-generation archival,
privileged mutation protection, local retirement and production remain OPEN;
retirement is OFF. See [readback outcome](PP_STORAGE_LEGACY_READBACK_REVIEW_2026-11-17.md).

### CP6 private structured receipt foundation — November 18 UTC

Default-OFF code [PR #92](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/92)
merged into `preprod` as `ac32805`; the scoped receipt-grant
[PR #106](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/106) merged
as `ddc5d29`; sealed-generation runtime-safety
[PR #97](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/97) merged as
`0efb3dc`. The reviewed additive migrations
`structured_receipts_v2_20261118` and
`pp_structured_receipt_grants_20261118` were applied through the Supabase
connector. Post-check: private `history_v2.structured_receipts` exists with
**zero rows**; `tradebot_pp_history` had **NOLOGIN** at this grant-only
checkpoint and had only SELECT/INSERT on that table. Exactly one `pp-live-pp`
SELECT policy and one INSERT policy exist; UPDATE/DELETE grants are absent, and
anon/authenticated/service-role SELECT is denied. This is a permission
foundation, **not** cloud runtime structured write/readback,
outbox acknowledgement or sustained archive result. Runtime sync, local
retirement and production remain OPEN; retirement is OFF.

### CP6 bounded PP structured-history login — November 18 UTC

After the grant-only checkpoint, the selected operator procedure enabled
`tradebot_pp_history` LOGIN with a random SCRAM credential. The exact Supabase
session-pooler endpoint and Root 2021 CA were obtained from the project
dashboard. From the existing PP VM over its pinned operator connection, the
PostgreSQL container established a TLS `verify-full` session as that role.
The root-owned PP connection file (mode 0600) and CA file (mode 0644) are
staged outside the containers; no service mount or cloud sync was enabled.

A bounded transaction read an empty `history_v2.structured_receipts`, inserted
and read one exact `pp-live-pp` receipt, rejected a wrong-origin insert, then
rolled back. Final cloud post-check confirmed **zero persisted rows**, LOGIN
enabled, SELECT/INSERT true, UPDATE/DELETE false, and exactly two receipt
policies. The temporary PP test credential file and local credential copies
were removed. Existing PP API, calculation, lifecycle, operator and PostgreSQL
containers remained running.

This proves the restricted **operator connection and transaction**, not the
application path. Runtime sync is **NO-GO** until the exact-origin constructor,
service wiring, actual importer/write/readback, and bounded backlog handling
are qualified. Archival acceptance, local retirement and production remain
OPEN; retirement and paid AI remain OFF.

**CP6 one-shot mount candidate (November 18 UTC):** A separate PP-only Compose
profile and root controller route prepare a bounded diagnostic without changing
normal generated CD or mounting cloud credentials on persistent services.
The profile is default OFF; dry-run preflight sends no cloud requests, and an
exact-page execute requires its own one-use root permit. A short-lived root
0600 copy of the PP lifecycle credential is staged in `/run` only for this
capability-free one-shot container and removed on every result path. Local
deployment controls passed 116 tests with one platform skip. The controller is **not
installed**, the new image is **not deployed**, and no probe ran. Exact Linux
CI, reviewed PP controller replacement, dry-run host preflight and separately
bounded cloud execution remain gates. [Mount review](CP6_PP_STRUCTURED_ONE_SHOT_MOUNT_REVIEW_2026-11-18.md).

## Current CP6 cloud-permission checkpoint — November 17 CST / November 18 UTC

The following role checkpoint predates the receipt migrations above; its
draft/unmerged references are historical and superseded by the current CP6
foundation result.
Scoped PP private-history role [PR #98](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/98)
merged to `preprod` as `2c6ffd2`; exact source `6d44201` passed
[push CI 44221712030](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44221712030)
and [PR CI 44221718737](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44221718737).
The reviewed SQL was applied to the connected Supabase project as migration
`20261118021900` (`pp_history_v2_role_20261118`). Readback verified a
NOLOGIN/NOINHERIT/NOBYPASSRLS role, 21 exact `pp-live-pp` policies, nine
SELECT/INSERT tables and three UPDATE tables. DELETE, `coverage`, and
anon/authenticated/service-role schema access remain denied. The existing
private `history_v2` tables still contain zero rows. This is a permission
foundation, **not** runtime enablement: no PP cloud login, Storage identity,
structured receipt grant, host credential, live cloud write or retirement
was enabled. See [the reviewed scope and remaining gates](CP6_PP_HISTORY_ROLE_REVIEW_2026-11-17.md).

CP7 code-only PRs #93, #95 and #96 have merged into `preprod` after exact CI;
the bounded Coinbase reconnect and generated-profile leave changes are **not
deployed** to PP. The last observed PP collector state remains generated/OFF
after the failed diagnostic live trial; its 5,268/10,000 pending outbox is a
separate long-session gate. CP6 PR #92 merged code-only as `ac32805`; its
default-OFF active structured sync remains runtime NO-GO. PR #97's sealed
generation drainage remains unmerged. Live A→B rotation, raw Storage
archival/readback, and local
retirement remain unproven. Production remains unchanged; I7 and Phase 1.75
remain OPEN.

## PP leave readiness candidate — November 17 CST / November 18 UTC

After the pp.9 diagnostic trial, first leave-to-generated failed with a generic
entrypoint code after service recreation; later generated API/operator checks
and one bounded permit-free recovery leave passed. The exact failed subcheck
is unknown. A small offline candidate now waits only for transient API/operator
loopback unavailability within the original 180-second leave budget, reports
fixed post-recreation failure stages, and leaves durable OFF plus the `leaving`
journal fail-closed. Generated regressions pass locally; Linux CI and any PP
controller release remain separate. See the
[leave review](PP_LEAVE_READINESS_REVIEW_2026-11-17.md). No live collection,
cloud sync, retirement or production operation follows from this candidate.

## Current CP7 result — diagnostic PP live release and trial, November 17 CST / November 18 UTC

**FAIL; PP recovered to generated mode, collector OFF.** Exact `preprod`
source `437d0a4` passed [CI 44214616202](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44214616202),
immutable candidate `v0.2.0-pp.9` passed
[publish workflow 44215401524](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44215401524),
and [manual PP CD 44216017150](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44216017150)
passed generated-mode acceptance. The bounded PP live session then stopped
after about 282 seconds with private code `coinbase_stream.unexpected`,
captured before OFF and profile restart. The exact WebSocket exception is
unknown. During 53 ON samples, API had zero errors (maximum successful latency
190.6 ms), but Coinbase input age reached 33.145 seconds near failure. Only
one market ID was seen; no boundary, A/B switch, cloud archive or retirement
was qualified. Raw A grew from 1,389 to 4,845 rows, and pending local outbox
from 1,530 to 5,268 (below the unchanged 10,000 cap).

Explicit OFF passed. The first generated-profile leave failed after service
recreation; its exact post-recreation subcheck was not logged. The existing
bounded permit-free recovery leave passed, and the journal records
`generated_restored`. All application services run the exact image with zero
automatic restarts; API reports generated mode and collector OFF; PostgreSQL
was not recreated. Ten API transport errors occurred during the two profile
recreations, none during ON or the intervening OFF period. The failed first
leave and failed trial remain failures. [Full sanitized evidence and limits](PP_LIVE_DIAGNOSTIC_TRIAL_2026-11-17.md).

**Next CP7 action:** classify Coinbase WebSocket exceptions into specific
sanitized codes and fix the generated-profile readiness race offline before
any new live attempt. Keep the PP size trigger and outbox cap unchanged until
separately qualified. Production, cloud sync, retirement and paid AI remain
unchanged/OFF. I7 and Phase 1.75 remain OPEN.

## CP7 Coinbase reconnect candidate — November 17, 2026

An isolated, default-off successor to PR #93 retries only classified Coinbase
WebSocket closure, transport and timeout failures, with 1/2/4-second backoff,
three reconnects per 60 seconds and 12 reconnects per bounded session. Storage
and ownership holds, invalid data and handshake/protocol failures remain
fail-closed; no ticks are synthesized or backfilled. The 42 affected local
tests pass, including cancellation, replay and sanitized diagnostics. Exact
Linux CI and any PP release remain separate. This does **not** explain the
historical `coinbase_stream.unexpected` PP failure. Outbox headroom and
structured drain remain independent PP live-run gates. See the
[candidate scope](CP7_COINBASE_RECONNECT_CANDIDATE_2026-11-17.md).

## Legacy collector control CI correction — November 17 CST / November 18 UTC

PR #83 successor [push CI 44213027544](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44213027544)
found a separate legacy SQLite collector-control race: after a test kills a
collector, its UNIX socket path survives. A new owner could acquire the lock
before removing that stale path, making startup appear ready while a stop
request receives connection refused. The isolated correction removes the
stale socket immediately under the new owner's exclusive lock. Six focused
legacy tests pass, including a stale-path regression. [Push CI 44213423636](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44213423636)
and [PR CI 44213449046](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44213449046)
passed; PR #90 merged to `preprod`. PP deployment remains a separate gate.
This does not change PostgreSQL storage,
Supabase permissions or retirement state.

## Current CP7 result — first PP live session, November 17 CST / November 18 UTC

**FAIL; PP is restored to generated mode with its collector OFF.** The first
PP live session persisted data from 00:42:34 to 00:45:13 UTC. It committed
1,360 Coinbase and 29 Polymarket US raw events, 28 feature snapshots and 28
predictions in PP PostgreSQL. Discovery advanced from market `2633366` to
`2637773` at the 00:45 boundary, then Polymarket became missing and Coinbase
became stale. The session durably stopped 13 seconds after the boundary.
The current operator discarded the exact source exception, so the cause is
**unknown**. The 20-minute freshness/rollover observation did not complete.

An explicit OFF and generated-profile restoration passed. The live A generation
and all 1,389 raw rows remain in PP PostgreSQL. A bounded post-recovery sample
measured 43,267,763 database bytes, 2,711,552 A-relation bytes, 33,554,432
allocated WAL bytes, 56,830,771,200 free filesystem bytes and 1,202,831,360
available RAM bytes. These are one short-session measurements, not a 72-hour
capacity result. Cloud sync and retirement stayed OFF; 1,530 pending PP outbox
rows are local. The default pending-outbox cap is 10,000 rows; whether a
20-minute cloud-OFF trial fits that cap is unqualified and must be measured.
Production and paid AI were not changed. See the dated
[first-trial evidence](PP_LIVE_FIRST_TRIAL_2026-11-17.md).

The [READY_OFF workflow](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44209122389)
is **FAILED** although its host artifact recorded `PP_LIVE_READY_OFF`: the
reporter overwrote its PASS gate before returning exit code 1. [PR #85](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/85)
merged a future reporting fix; it does not retroactively pass that run. Initial OFF
also failed on the uninitialized PP live origin; explicit empty-A bootstrap
then allowed verified OFF. Source/task failure codes in [PR #88](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/88)
and clean-start OFF in [PR #89](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/89)
have passed source qualification and merged to `preprod`; neither is deployed
to PP. The original source failure remains unknown.

**Next CP7 checkpoint:** release the qualified diagnostics and clean-start OFF
controls to PP, then run one new bounded PP-only trial with outbox-cap and
resource observation. A qualified size trigger, A/B switch, Supabase
verification and local retirement are separate later gates. I7 and Phase 1.75
remain OPEN.

The intended size-triggered 30–45 minute PP A→B qualification has **not run**:
the first live session ended after 159 seconds, before any switch. A→B with
archive readback requires a qualified size trigger and cloud path. B→A slot
reuse additionally requires separately qualified retirement authorization,
which remains OFF. The production policy stays 72 hours or qualified size.

**CP7 read-only resource observer candidate (November 17):** A separate PP
host script now takes bounded read-only samples of the PP live origin's writer
generation, up to 10,001 raw records per active generation, relation/database
bytes, WAL segment allocation, free disk and available RAM. Counts at the cap
are lower bounds. Generated tests passed; PP host execution and exact CI are
separate evidence. This observer never enables collection, cloud sync or
retirement and cannot establish a qualified size trigger by itself.

## CP7 bounded PP live API observer — November 17, 2026

The local-only deploy/preprod/live_observe.py candidate samples the private
PP API through a caller-supplied loopback tunnel and cannot enable/disable
collection. It records a bounded 25-minute session at five-second cadence,
checks dashboard/history/SSE at one-minute cadence, and reports PASS, FAIL or
INCOMPLETE against API latency, feed freshness, input/feature age, distinct
calculation/prediction IDs and a real market boundary. The report excludes
prices, credentials and response bodies. Fake-HTTP and pure-result tests pass
locally; exact Linux CI and any actual PP observation remain separate gates.
See deploy/preprod/LIVE_OBSERVATION.md. Raw-row acknowledgements, disk/WAL
growth, Supabase archive/retirement and 72-hour operation require independent
evidence.

## CP7 generated market-boundary smoke candidate — November 17, 2026

An isolated candidate combines the PP supervisor, Polymarket cycle and operator
session across a simulated 15-minute boundary. Generated missing-market and
404/429/timeout/invalid faults assert independent Coinbase progress, no old
quote replay, fixed private failure codes, durable OFF and no automatic ON.
The adjacent 34 local tests passed. Exact source `448cd1f` passed
[push CI 44217282644](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44217282644)
and [PR CI 44217319889](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44217319889);
the isolated PostgreSQL logs confirm both new smoke methods ran. This does not
identify the first PP live session's lost exception or qualify live A→B.
See [bounded smoke scope](CP7_BOUNDARY_SMOKE_2026-11-17.md).

The subsequent PP diagnostic checkpoint reported `coinbase_stream.unexpected`
before the market boundary, leaving the WebSocket exception subtype unknown.
A default-OFF successor to draft PR #93 classifies pinned `websockets==15.0.1`
closure, handshake status, protocol and transport failures into fixed private
codes. Generated fake-socket tests verify durable OFF and no payload/URL text;
35 affected local tests passed. No runtime reconnect, PP release or live
continuity result follows from this candidate. Exact successor CI is pending.

## CP6 structured import preparation — November 17, 2026

An isolated, default-off preparation now pins all eight structured cloud row
shapes to the applied private `history_v2` migration and resolves the local
`snapshot_evidence` hashless-cloud-row mapping by validating its deterministic
edge hash before omission. Generated tests check exact decimal and source-time
readback, origin-aware identities, duplicate payload conflicts and monotonic
market/current-price revision classification. The existing batch import still
holds conflicting revisions. No cloud write, outbox acknowledgement, grant,
policy or retirement authorization occurred. Runtime grants remain absent;
atomic mutable revision plus checkpoint writes and privileged mutation fencing
remain separate CP6 gates. See
[preparation evidence](CP6_STRUCTURED_IMPORT_PREPARATION_2026-11-17.md).

PR #83's refreshed [exact CI 44212187026](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44212187026)
**FAILED** in generated PostgreSQL acceptance. It seeded a price before a
15-minute boundary and queried the current-market chart after rollover; the
correct empty chart tripped the fixture assertion. The structured envelope
diff does not change that query. A bounded generated-only acceptance fix
requires the new market's exact price to appear after reseeding; an empty or
wrong-price chart still fails. Successor exact CI is required before merge.

## CP6 active structured sync preparation — November 17 CST / November 18 UTC

Draft [PR #92](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/92)
prepares a default-OFF active-generation structured importer with ordered
mutable revisions, atomic per-revision cloud receipts/checkpoints, and fresh
readback before local outbox acknowledgement. Its additive private receipt
migration is **unapplied**, with no runtime grants. Source `02dad1a` passed
local 32 focused tests, exact [push CI 44216336523](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44216336523)
and [PR CI 44216373853](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44216373853),
including actual isolated PostgreSQL. PP/Supabase runtime, narrow identity,
sustained throughput and capacity remain **NOT QUALIFIED**. No cap, service or
retirement setting changed. See the dated [CP6 evidence](CP6_ACTIVE_STRUCTURED_SYNC_PREPARATION_2026-11-17.md).

Review follow-up `e302689` passed 33 local focused tests and exact
[push CI 44218348328](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44218348328)
and [PR CI 44218357150](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44218357150).
Fresh readback now requires an exact mutable projection; a newer-looking
unreceipted cloud value cannot ACK local evidence. Active B sync also holds
while any other same-origin generation has pending outbox rows, preventing
B from overtaking unsynced A. Sealed-A drainage and cross-worker ordering
remain **NO-GO for runtime**; PR #92 merged code-only as `ac32805`.

Stacked [PR #97](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/97)
implements a default-OFF sealed A structured drain while B collects. A
same-origin PostgreSQL session lock spans import, fresh readback and local ACK;
cloud import/readback and local ACK transactions use PostgreSQL 17 whole-
transaction timeouts within the cycle budget. Source `8f4d498` passed 36
local focused tests and exact
[push CI 44221644336](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44221644336)
and [PR CI 44221649679](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44221649679),
including isolated generated PostgreSQL. This **does not enable PP cloud
sync**: actual PP-only role/grants, live readback, runtime scheduling,
connection-timeout binding and sustained backlog/outage capacity still need
proof. The 10,000-row cap and retirement OFF remain unchanged. See
[CP6 drainage evidence](CP6_STRUCTURED_DRAIN_2026-11-17.md).

## CP7 PP generated release and live-controller binding — November 17, 2026

Exact `preprod` source `9dbeec6` passed push CI
[44193279239](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44193279239)
and was published as immutable candidate `v0.2.0-pp.8` by
[44193897155](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44193897155).
One-use generated-mode CD
[44194501783](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44194501783)
passed. Host readback matched the source and image, all five PP containers were
running, and the API reported `generated` with collector OFF. The temporary
private runner deregistered.

The reviewed PP live-controller zipapp was built twice byte-identically and
installed at SHA-256 `bdb11511039365990249846d1e5a521228255530db000a25181ad260f7aebee7`.
The prior controller code remains present. Dedicated forced-command identity
run [44195257281](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44195257281)
returned `IDENTITY_PASS` for that exact hash; host API readback remained
generated/OFF. The binding is recorded in
`docs/PLAN/evidence/pp-live-controller-binding-2026-11-17.json`.
At this earlier checkpoint, READY_OFF had not been entered and no PP live feed
session had run. Cloud
sync, retirement, paid AI and trading remain OFF. A separate one-use enter and
session ON authority is required for the bounded first PP collector/query trial.

At 22:49 UTC, a bounded read-only production `/health` check returned HTTP 200
but reported collector `enabled=true`, `running=false`, Coinbase and Polymarket
streams `stopped`, and storage guard `limit_reached`. This is a fresh service
status sample, not a full persistence or feature audit. No production operation
was performed. PP as an outage standby and cross-origin gap reconciliation are
**future** resilience work, not this trial's acceptance gate.

## CP7 occupied-slot fail-closed preparation — November 17, 2026

The PP-live lifecycle candidate now commits `other_slot_not_retired` and a
durable collector OFF in the same writer-row transaction. A held B generation
cannot receive new PP acknowledgements or accept a new ON lease; the lifecycle
worker exits with a held result. An isolated PostgreSQL test covers A→B
acknowledgements, occupied-slot OFF across repository restart, refused new
writes/ON, failed mock archive preserving sealed A, and partition/database/WAL
measurements. Generated-origin behavior is unchanged; cloud sync and retirement
stay OFF.
Exact PR CI [44191643671](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44191643671)
then passed all six jobs. Its isolated PostgreSQL 17 case recorded two
acknowledgements with zero gaps, 81,920 bytes allocated in each A/B partition,
70,264 WAL bytes generated and 10,950,323 database bytes. It verified durable
OFF after restart, refused a new ON lease and preserved sealed A after failed
mock archive. These are tiny fixture measurements; deployed PP remains untested.

**Numeric PP trial trigger blocked:** the generated 24-tick qualification
measured 81,920/114,688 bytes across A/B and 143,224 WAL bytes. PP's recorded
resource snapshot had 21 generated raw rows, 57.08 GB free disk, 1.32 GB
available RAM and 32 MiB WAL. These do not measure live feed cadence,
core/dedup/outbox growth, WAL amplification or source throttling over a bounded
session. No safe PP size threshold or guaranteed switch within 1,800 seconds
can be derived from them. The live Compose profile sets no size trigger; a
bounded, measured PP live baseline must precede a separate reviewed threshold
and one-switch trial. A 30-minute trial cannot prove 72-hour rotation, cloud
archive, partition retirement or sustained lifecycle acceptance.

## CP7 isolated PP live query parity candidate — November 17, 2026

An isolated PostgreSQL 17 test now uses known normalized Polymarket US
15-minute market/BBO and Coinbase ticker/candle events under a disposable PP
live origin and finite ON lease. It checks current price source ordering,
complete candle inputs, exact decimal values and provenance, BBO observation
versus last-price-sample time, feature/prediction evidence, ordered local
history and bounded chart output. The running API's hydration, health,
dashboard contract and SSE payload are checked against those committed rows,
with source-age expiry and next-market isolation asserted separately. The
PostgreSQL chart now excludes source timestamps ahead of the query clock and
uses deterministic tie ordering; history and hydration tie ordering are
explicit. This follows the SQLite dashboard's evidence and freshness meaning
without copying its SQL or unsupported ensemble fields. Exact Linux push CI
[44191706794](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44191706794)
passed all required jobs; its isolated PostgreSQL 17 application lifecycle
suite ran 99 tests with no skips, including the PP live query case. A real PP
feed session, source cadence and rollover observation remain OPEN. No PP host,
production, Supabase, trading or paid AI operation is part of this candidate.

## CP6 PP full archive-flow distinction — November 17, 2026

The user's requested functional PP proof is a bounded A→B switch followed by
sealed-A structured sync to private `history_v2`, create-only raw upload to
private Supabase Storage, exact authenticated readback, protected-reference and
reader checks, then separately authorized local partition retirement while B
continues writing. No extra 72-hour wait follows sealing. The first <=30-minute
PP live collector/query session is a **different checkpoint**: cloud sync and
retirement stay OFF, and no PP live size threshold is qualified yet. Neither A
nor B is assigned a 30-minute rotation timer.

Fresh read-only Supabase inventory found ten `history_v2` tables but no runtime
grants or policies; `market-raw` is private with no Storage object policies.
The existing Storage adapter cannot sync structured rows, and the SQL
retirement function rejects non-generated origins. A default-off origin-bound
raw/structured transport with generated HTTP and isolated PostgreSQL tests is
under qualification. Exact source `84b0488` passed
[Linux CI 44194237939](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44194237939),
including the isolated PostgreSQL 17 A→B/B-write/mock readback case with no
skip. The transport cannot authorize retirement or prove live Supabase access;
PR #79 remains draft and is excluded from the first PP collector/query
release. See the dated
[CP6 PP archive-flow review](CP6_PP_ARCHIVE_FLOW_REVIEW_2026-11-17.md) for the
minimal remaining cloud and mutation-authority gates. No cloud or PP runtime
state changed through this read-only review.
PP and production may collect concurrently into distinct databases and origins.
As a future option, PP archives may preserve evidence during production gaps,
but a later explicit
source-ID/content-hash reconciliation must retain both originals and conflicts;
no automatic PP→production history or training merge or failover is authorized.
This is not a gate for the current PP live collector trial.


## CP7 PP live host-control candidate — November 17, 2026

A candidate extends the PP forced-command controller with one-use, exact
source/artifact/controller/image authority to enter the reviewed live profile
in durable OFF state. A root-owned persistent transition journal permits
separate authenticated OFF and generated-profile restoration after the enter
permit is consumed, including when operator HTTP is unavailable. A separate
one-use session permit binds that journal and caps ON at 1–1800 seconds; the
host command reads the private token without returning it. The manual PP
workflow uses the existing pinned key, host pin and private runner, requires a
published source and successful generated PP deployment before entering, and
records sanitized results. Local PP control tests and workflow lint pass.
The host enter path has a 600-second work budget and a fresh 180-second
recovery budget; a failed entry cannot report success after restoration.
This is source preparation only: the new controller is not installed, no PP
live profile or feed session has run, and production is unchanged. Exact push
CI, installed-hash qualification, one-use host authorization and the bounded
real-market trial remain open.

## CP7 isolated size-switch qualification candidate — November 17, 2026

A generated-origin, isolated-PostgreSQL test now measures an A→B switch while
two live-shaped ticker writers run. It checks every committed acknowledgement
against raw rows, first/second partition allocation and WAL growth, the
occupied-slot hold, and the PostgreSQL-backed API's current price generation
and dashboard data binding. The fixture derives its tiny trigger from its own
partition allocation; it is **mechanism evidence, not a qualified PP capacity
threshold**. The dashboard does not separately label the active writer
generation. Cloud sync and retirement remain OFF. Exact Linux PostgreSQL CI
and any deployed PP observation are still separate gates; no PP service,
production database, or Supabase state changes in this candidate.
The first isolated CI run caught a concurrent A→B lookup race in the joined
writer/generation read. The candidate now locks the writer pointer before a
fresh generation lookup for both ingest and calculation. Exact PR CI
[44189046509](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44189046509)
passed all jobs. Its isolated PostgreSQL 17 run recorded 24 distinct
acknowledgements, zero acknowledgement gaps, six writes to A and 18 to B,
an occupied-slot hold, 81,920/114,688 byte A/B partition allocations and
143,224 WAL bytes generated during the fixture. API current price referenced
B and the dashboard consumed that state; the dashboard still has no separate
active-writer generation label. This qualifies the generated size-switch
mechanism only. A PP runtime threshold, deployed live rotation, cloud archive,
retirement and sustained acceptance remain OPEN.

## CP7 PP live observation and OFF calculation corrections — November 17, 2026

Candidate source separates a Polymarket US REST BBO's local observation time
from the `lastPriceSample.ts` timestamp, which is not a book update time. Each
successful poll is retained as a distinct raw observation, including when the
book content has not changed. The API selects and ages the most recently
received BBO; the source sample timestamp remains exact and may be missing.
The dashboard labels the REST bid/ask and its observation age accordingly.
PP live calculation commits now require a valid ON lease before and after
their transaction, so a durable OFF cannot be followed by a new calculation
acknowledgement. Generated-mode calculation remains available. Local generated
tests cover old/missing sample times, repeated polls and quote ordering. The
isolated PostgreSQL test covers BBO hydration and calculation ON→OFF; exact
Linux CI and real-market PP observation remain open. This candidate does not
activate a collector or change PP/production hosts.

## CP7 PP host mode-transition core — November 17, 2026

The candidate `LiveTransition` component validates the normalized live Compose
overlay against the exact generated profile, checks the currently running
PostgreSQL and generated services, stops/recreates only the four application
services into PP live mode, and requires both private host API/operator routes
to report the PP live origin with a durable OFF lease. It **does not** call ON.
On leave, a bounded lifecycle-role one-off stops the collector through the
writer-row lock and independently reads back OFF before restoring generated
services. The same OFF check precedes generated restoration after a failed
entry; an unproven OFF leaves the transition held. PostgreSQL, its volume,
cloud flags and retirement are never changed by this component. Local
deployment-control tests pass, including failed start and unproven-OFF paths.

This component is **not yet installed or executable on PP**. A separate trusted
root entrypoint must bind the exact CI-passed source, image, host and one-use
authority, expose bounded ON/OFF without disclosing the operator token, and
prove recovery after interruption. Only then can a reviewed generated-only
release be switched to live mode for the real-market trial. A short trial still
cannot prove archive/retirement or 72-hour rotation; those remain separate
gates.

## CP7 independent PP live OFF recovery path — November 17, 2026

The private operator API is the normal ON/OFF route, but it may be unreachable
during a container transition. The candidate adds explicit lifecycle-role
`--stop-collector` and `--collector-status` commands for the PP live origin.
They cannot run in generated/replay mode or together with bootstrap/rotation;
they use the existing file-mounted lifecycle credential, report only bounded
state fields and never enable a collector. The intended host recovery action
can use the one-off lifecycle container to prove durable OFF even when the
operator HTTP process is unavailable. Local lifecycle tests pass. This command
alone does not install a host transition, start feeds, or alter PP/production.
The opt-in operator also revokes any stored ON lease at startup and verifies
durable OFF before creating a new session. A container restart therefore cannot
inherit the previous process's live authority. Local role/runtime tests pass;
the host restart and isolated PostgreSQL checks still need exact CI and PP
qualification.

## CP7 truthful PP live dashboard and health — November 17, 2026

Before activation, review found `Settings.public()` and the dashboard label
always claimed the real collector was OFF, even when a PP live lease could be
enabled. The candidate now polls the durable PP database lease into RAM once
per second. Live mode initially reports **unavailable**, reports OFF or ON only
from that lease, and never infers process liveness from it. The live health
result degrades when the lease is OFF or unknown. `/health`, `/system/status`,
API/SSE snapshots and the dashboard label use the same state; a database read
failure returns unavailable rather than stale healthy data. Generated mode
still reports OFF. Focused local application tests pass. Exact Linux CI,
release and real-market observation remain open; PP and production are
unchanged by this source candidate.

## CP7 database-wide PP collector lease correction — November 17, 2026

Review of the live trial found that an origin-row lease alone could admit a
second `pp-live-*` origin in the same PP database. The candidate serializes
live admission with a transaction-scoped PostgreSQL advisory lock and rejects
another active PP-live lease. An isolated PostgreSQL test starts two competing
origins and requires exactly one winner, then proves the other can start only
after durable OFF. A separate test covers acknowledged writes and lease
continuity across A→B, with the occupied-slot hold preserving B writes.
These tests require isolated Linux PostgreSQL CI; the Mac run skips without
test DSNs. No PP runtime, cloud, retirement or production state changed.

## CP7 PP live profile preparation — November 17, 2026

PR #68 merged the opt-in operator/session source after exact CI passed. A
separate `runtime.live.compose.yaml` now describes the four existing PP
application processes reading/writing only `pp-live-pp`: API, serial
calculation, lifecycle rotation and private operator. The operator alone gets
the additional app-role DSN and live-control opt-in; collector activation still
requires its authenticated bounded ON request and a durable lease. The normal
generated-only CD profile remains unchanged and rejects this overlay.

The normalized live profile is compared field-for-field with the qualified OFF
profile. Only the reviewed origin/mode, lifecycle opt-in, and operator app-role
mount/flag may differ. The local real Docker Compose render and 65 PP control
tests passed, with one existing platform skip. This is **source qualification,
not a PP release**: no host switch controller, live API acceptance, actual feed
run, Supabase archive, partition retirement or production action has occurred.
Next qualify a separately bounded PP-only host transition and recovery path,
then observe live collection across a real market boundary with cloud sync and
retirement OFF. The selected 72-hour-or-qualified-size policy remains; no
short interval is substituted for it.

## CP7 opt-in live operator runtime source — November 17, 2026

Candidate source connects the private operator's optional ON route to the
existing PP lease and bounded read-only source supervisor. It requires explicit
`TRADEBOT_PP_LIVE_CONTROL=true`, a separate mounted app-role DSN, the existing
lifecycle role and a PP origin. Startup validates both roles and schema; the
operator requests durable OFF on shutdown. Without the opt-in and secret mount,
the deployed operator still returns 404 for ON. Generated runtime/API/session
tests pass locally. The deployed PP Compose profile and CD controller do **not**
yet permit the new mount/flag; no live PP run or archive is claimed. Exact CI,
host qualification and live observation remain open.

## CP7 private ON API seam — November 17, 2026

Candidate code adds an authenticated `/collector/on` route **only when** a
qualified session controller is injected into the separate PP operator API.
The current runtime injects none, so deployed PP continues returning 404 for
ON. The route reports request acceptance, not a durable ON claim; status reads
the database flag independently. Generated API/session tests pass locally.
Runtime source/credential binding, process recovery, exact CI, deployment and
the live market observation remain open. No production or PP service changed.

## CP7 live rotation preparation — November 17, 2026

The generated-only lifecycle worker previously rejected `pp_live`, so live
collection could not exercise the 72-hour-or-qualified-size A/B switch. The
candidate adds an explicit PP-live lifecycle mode with distinct origin and
opt-in; collector, cloud sync and retirement flags remain OFF in that worker.
Focused generated configuration tests pass. This is code preparation only:
the PP Compose service still runs generated mode, and no live process, ON
control, cloud archive or production change is included. The live session and
rolling-window observation remain unperformed.

## CP7 local session-control component — November 17, 2026

The first implementation slice adds an **unwired** one-task PP operator session
controller. Generated tests verify duplicate start rejection, bounded duration,
explicit OFF, failed-session hold and refusal to restart after unproven OFF.
It has no ON route, host process binding, live credentials or source startup.
Focused local tests pass; exact Linux CI and runtime integration remain required.
This component does not change deployed PP or production and does not qualify
live collection. Continue with the private host-bound control and tests before
the bounded PP live trial. The selected dashboard/cloud/experiment data paths
below remain unchanged.

## PP dashboard and data-mode clarification — November 17, 2026

**User-selected workflow:** PP normally previews production through a
restricted, read-only production API/SSE route. Its own collector is OFF in
preview. For a bounded PostgreSQL integration test, the operator switches PP
to `pp_live`: its own read-only feed clients write only to PP PostgreSQL and
the PP dashboard reads that PP API. After the test, the operator drains and
turns PP collection OFF, confirms OFF survives restart, and switches the
dashboard back to production preview. Production collection need not pause for
this test. Preview is not a shared database connection or Docker network.

| Data path | Selected purpose | Deployed state |
| --- | --- | --- |
| Production API → PP preview | Normal PP dashboard view of production, with source/as-of labels and unavailable state on failure | **Not implemented**; PP dashboard currently shows generated PP data |
| PP collector → `tradebot_pp` | Bounded live ingestion, PostgreSQL queries, calculations and 72-hour-or-qualified-size generation qualification | Lease/schema deployed; collector process and ON path **not implemented** |
| Separate PP experiment database | Generated/replayed subsets and schema/query experiments without contaminating PP live or production history | **Not created**; current PP has one `tradebot_pp` database with generated-origin records |
| PP → Supabase | Environment-isolated structured history and verified raw archives | `history_v2` schema exists, but PP cloud runtime grants, writes/readback and retirement are **not enabled** |

Before any PP cloud write, choose and test a PP-only identity and namespace
(separate project or strictly isolated schema/object prefix) with explicit
origin/generation keys and production-query exclusion. Never let PP-generated
or duplicate live observations enter production training/evaluation as
independent evidence. Cloud write acknowledgement is distinct from verified
archive readback; no local generation is retired until coverage, checksum,
references and retrieval pass. A failed cloud cycle retains local data and
reports backlog. The live PP trial may proceed with cloud sync and retirement
OFF, but that trial cannot claim a working 72-hour archive/retirement lifecycle.

Audit the actual production and Supabase collection intervals before making
claims about missing history. Any period with no collection has an evidence gap:
later candles or market summaries may support labeled backfill, but they cannot
recreate unobserved tick/order-book events. Preserve the gap in coverage and
exclude it from algorithms that require complete live observations. Current
production collection state is **not freshly verified by this plan update**;
the last recorded legacy state was storage-held. Do not infer active production
collection from a running API service.

## CP7 collector ownership correction — November 17, 2026

The earlier cross-VM **sole real collector** rule was overbroad. PP and
production have separate databases, credentials, origin IDs and application
processes. They may independently consume the same read-only Coinbase and
Polymarket US market feeds while writing only to their own stores. A PP live
test does **not** require stopping or changing production. This supersedes the
cross-VM fence wording in older CP7 sections below and in dated handoffs.
It does not authorize any production operation.

The enforceable ownership rule is **one active PP collector session per PP
origin/database**. Its authenticated operator control must bind the PP host,
origin, active generation, session ID and expiring database lease; start no
second PP process, acknowledge OFF after draining on stop, and remain OFF after
restart unless explicitly re-enabled. PP and production must never share a
database connection, volume, credentials, outbox or archive checkpoint.
Combined source traffic needs bounded cadence, reconnect backoff and observation
of 429/throttling or subscription rejection; a source limit failure stops the
PP trial and preserves truthful stale/unavailable state. Coinbase documents
[account-level WebSocket subscription limits](https://help.coinbase.com/en/exchange/managing-my-account/market-data-connections);
the [Polymarket US data guide](https://docs.polymarket.us/data-guide/overview)
describes read-only REST/gRPC access. Neither document proves an unlimited
two-VM allowance for the exact PP request profile. Measure it during the trial.

**Revised CP7 execution order:** (1) finish a private PP ON/OFF host process
controller using the deployed lease and existing bounded source supervisor;
qualify unauthorized/repeated ON, expiry, crash, restart, in-flight writes and
confirmed OFF. (2) Verify distinct PP-only identity and PostgreSQL destination,
source cadence and resource bounds; leave Supabase sync, retirement, paid AI
and trading OFF. (3) Run one bounded PP live session while leaving production
untouched. Require advancing Coinbase and Polymarket US 15-minute records,
correct generation/market, dashboard/API/SSE, a real market boundary, no
two-second API timeouts, save/heartbeat below one second, and input/feature
ages within 30 seconds; record rate responses and disk/WAL growth. (4) Turn PP
OFF, confirm no new acknowledgements or automatic restart, and report PASS,
FAIL or INCOMPLETE against each measure. A qualified size trigger may test a
generation switch separately; archive verification still precedes retirement.
Production PostgreSQL cutover remains a later, separately controlled gate:
**then** fence the old production writer before the new production writer starts.

Current code remains default-OFF and has no PP ON endpoint or host process
controller. The pp.7 generated-only deployment passed; a live PP run has not
occurred. CP6 cloud archival and Phase 1.75/I7 acceptance remain open.

## CP7 generated-only PP lease release — November 17, 2026

The exact `preprod` source `4eea47b` passed
[CI 44166604082](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44166604082),
was published as immutable
[`v0.2.0-pp.7`](https://github.com/JakeMofa/Trading_Bot_Analytics/releases/tag/v0.2.0-pp.7),
and passed manual [CD 44167381155](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44167381155).
The deployment artifact SHA-256 was
`4b159a18fdd2142549e80f48263d41c7de9b598a4c9080a49c62c26a4e5bb768`;
the actual PP image ID was `sha256:2144186e6df0041a45dc5c54268046825a0a729b3fd6ed7f776411e5fa5e1d12`.
The workflow reported PASS for migration, schema, data correctness, API, SSE,
operator control, recovery, collector ownership, disabled flags, freshness and
market identity. The PP host postflight found five services running, the API
healthy, no remaining one-use authority and no registered temporary runner.
[Sanitized deployment evidence](evidence/pp7-generated-lease-deployment-2026-11-17.json).

This release applies lease migration 0002 and matching application code in
**generated-only** mode. PP live collection, cloud sync, local retirement and
paid AI remain OFF. The previously published pp.6 package was not deployed:
merging the documentation checkpoint advanced the branch head before dispatch,
so its unused permit was revoked. The older pp.6 paragraph below is historical;
the pp.7 result above is the current PP runtime state. Production is unchanged.
Next: qualify the host ON/OFF path and durable cross-VM sole-collector fence
before any bounded PP live run. I7 and Phase 1.75 remain OPEN.

## CP7 PP collector lease checkpoint — November 17, 2026

PR [#60](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/60) merged
the explicit PostgreSQL collector-lease migration and default-OFF, lifecycle-only
lease enforcement into `preprod` at `e849794`. Exact source CI
[44163202311](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44163202311)
and merge CI [44163745406](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44163745406)
passed. Earlier candidate failures from stale migration-count assertions remain
failures; they were corrected before the passing source. The lease rejects
expired sessions before acknowledgement and does not expose a collector ON route.

The immutable generated-only release candidate
[`v0.2.0-pp.6`](https://github.com/JakeMofa/Trading_Bot_Analytics/releases/tag/v0.2.0-pp.6)
was published by [run 44164383015](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44164383015)
for exact source `e849794`; artifact SHA-256 is
`6888e78fb23d5b60190bf1671977d408593f7d5523b968b03c9715558d2b6352`.
Read-only PP preflight matched the installed controller hash and found no unused
one-use authority. GitHub listed **no available private runner**, so no
authorization was created and no CD was dispatched. PP still runs the previous
generated-only `v0.2.0-pp.5`; schema migration 0002 is **not applied** there.
Production and PP runtime settings were not changed by this checkpoint. Restore
the previously approved ephemeral private runner, then perform the exact manual
PP release with its one-use authority and bounded smoke checks. Cross-VM
collector fencing and a host ON/OFF controller remain prerequisites to live PP
collection; CP6 cloud archival and retirement remain OFF. I7 and Phase 1.75
remain OPEN.

## Branch archive — November 17, 2026

The repository now retains four active GitHub branches: `main`, `preprod`,
`codex/lightsail-deployment` (still required by the legacy production workflow),
and `codex/phase1-75-retention-enable` (the preserved dirty original checkout and
an existing release-summary link). Forty inactive remote branch names were
removed after their exact tips were pushed to `refs/archive/2026-11-17/` and
verified. Thirty-six inactive local branches and four clean worktrees were
removed. The original dirty checkout and its files were not changed. The
[branch archive manifest](evidence/branch-archive-2026-11-17.json) records every
tip and restoration path. Archive refs preserve history; they are not active
release branches. No production or PP service changed during this cleanup.

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
- **PP private loopback access PASS in generated-only scope.** Exact source
  `b50861d` passed [CI 43765914993](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/43765914993),
  published as `v0.2.0-pp.3`, and passed [CD 43766281486](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/43766281486).
  The host `127.0.0.1:8000` route and operator SSH tunnel returned HTTP 200 for
  dashboard, state, health, history and SSE. Four PP services remained running;
  live collector, retirement and paid AI stayed OFF. [Evidence](evidence/pp-loopback-acceptance-2026-11-15.json).
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

**CP6 read-only review (November 15):** The confirmed Supabase project still has
ten existing public history tables and no `history_v2` tables. The migration-list
tool errored; a catalog query counted two migrations but did not verify contents. Security
advisors identified pre-existing public RLS/no-policy notices and a callable
public security-definer function; neither was changed. A generated CI gate now
exercises the private contract, privacy and exact timestamp behavior. Cloud DDL,
grants, synthetic writes/readback and mutation protection remain OPEN. See
[CP6 review](CP6_SUPABASE_CONTRACT_REVIEW_2026-11-15.md).

**Preprod CI follow-up (November 15):** Merge commit `90d24c4` failed generated
controller smoke after the first API acceptance; downstream `CI Preprod` also
failed. No database migration or production deployment follows from that failed
run. The exact child substage was not captured. A bounded generated-market
boundary correction and sanitized phase diagnostics are under qualification;
see [failure review](PP_CI_BOUNDARY_FAILURE_2026-11-15.md). Do not treat the
earlier PR PASS as a passing preprod merge gate.

**CP6 schema-only candidate:** A named additive private migration is prepared
under `supabase/migrations/20261116050000_history_v2_private.sql` for separate
review. It grants no runtime role; CI applies that exact file to disposable
PostgreSQL and checks contract parity. Cloud application, later narrow grants,
client behavior and authenticated archive readback remain separate open gates.

**CP6 cloud schema installation (November 15 CST):** Exact source merge
`589bb97` passed [CI 43807662623](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/43807662623).
The reviewed migration was applied to Supabase as
`history_v2_private_20261116` (ledger `20261116050522`). Post-checks found ten
empty private RLS tables, zero anon/authenticated/service-role access, and the
same ten public tables. No cloud records or Storage objects were written, no
application was deployed, and retirement remains OFF. The schema-only subgate
is PASS; CP6 is OPEN for narrow permissions, bounded runtime write/readback,
generation checkpoints, raw archive readback and mutation authority. See
[sanitized evidence](evidence/cp6-history-v2-schema-2026-11-16.json).

**CP6 Storage transport candidate:** A default-off, project/bucket-bound
create-only raw-object adapter now has generated HTTP tests for exact
authenticated readback, identical versus conflicting duplicate objects,
ambiguous upload failure, bounded responses, invalid keys and private credential
files. It cannot perform structured sync or authorize retirement and is not
wired into PP services. Live Storage permissions, isolated cloud write/readback
and mutation authority remain open; passing mock tests do not clear them.

**CP6 credential correction:** The default-off Storage adapter now requires a
separate project API key and bearer access token, held in separate private files.
This permits a future RLS-scoped runtime identity. A service-role key or S3
access key bypasses Storage RLS and cannot establish runtime mutation limits;
no such credential is wired into PP. A scoped authenticated identity, reviewed
Storage policies, actual deny tests and privileged-mutation fencing remain
required before any cloud-enabled runtime or retirement gate.

**CP6 PP cloud binding preflight (November 17):** A separate offline module
checks exact `preprod`/`pp_live`/`pp-live-pp`, six distinct private file paths
for the Storage publishable key, dedicated Auth machine identity, independent
structured DSN and local lifecycle DSN, and OFF sync/retirement/paid-AI flags.
It checks file metadata without reading values and always returns STOP; it
does not mount a service or start cloud I/O. The structured role is still
NOLOGIN, PR #92's receipt table migration is unapplied, PR #97's worker is
unmerged, and live Storage and direct PostgreSQL authority/network gates remain
open. PR #92's importer now uses advisory serialization without row locks on
immutable tables or receipts; narrow receipt grants are separately qualified
in PR #106 and remain unapplied. See
[binding preflight review](PP_CLOUD_BINDING_PREFLIGHT_2026-11-17.md).

**CP6 structured-import preparation:** A separate, offline envelope validator
now recognizes only the eight versioned structured datasets, binds origin and
generation, compares exact primary identities/content hashes and orders FK
parents before dependents. It rejects conflicting revisions within one batch.
This is pre-import validation only; mutable projection ordering, narrow cloud
grants, actual writes/readback and durable acknowledgement remain open.

**CP6 PP SQL role candidate (November 17):** A separate small PR prepares a
NOLOGIN, exact-`pp-live-pp` `history_v2` role migration and isolated PostgreSQL
permission/denial tests. It does not grant Storage HTTP access, include PR #92's
unapplied receipt table, apply cloud SQL, enable runtime sync or authorize raw
retirement. Receipt grants, a dedicated Storage bearer and exact operation
policies, PP network/TLS/deadline qualification, and privileged mutation
protection remain separate gates. See
[role review](CP6_PP_HISTORY_ROLE_REVIEW_2026-11-17.md).

**CP6 PP Storage policy review (November 17):** A separate non-applied SQL
template outside `supabase/migrations` proposes exact PP Auth-user, bucket,
object-path and operation policies for create-only raw upload and authenticated
GET. A generated PostgreSQL fixture exercises allowed upload/readback and
denials for other identity, origin, bucket, key, list, copy, signed upload,
move, update, delete and anon access. The dedicated Auth user UUID does not
exist in this candidate; template preflight fails while unfilled. Live Storage
HTTP, token lifecycle, privileged mutation authority and retirement remain
OPEN. See [Storage policy review](CP6_PP_STORAGE_POLICY_REVIEW_2026-11-17.md).

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
| Bounded live qualification | Official feeds writing only PP data | One leased PP collector for its own database; production untouched |

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
| `pp_live` | PP API backed by PP PostgreSQL | ON only while PP holds its local collector lease | Official read-only feed observations and predictions are persisted in PP; no production writes |
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
connector, PP-only writer lease and bounded
resource preflight. `pp_live → isolated` stops intake, drains/acknowledges in
flight writes, persists collector OFF, checks processes/ownership after restart
and keeps PP history queryable. `isolated → production_preview` requires the
restricted production API route and a confirmed PP collector fence. Preview
failure reports production unavailable and does not substitute PP values.
Returning to `isolated` restores PP test views without starting collection.
The later approved production cutover independently fences the old production
writer before starting the new production writer. Mode changes and failed
attempts are recorded with actor, time, previous/new mode and local lease
result, excluding credentials.

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
The first exact push CI found an intentional old-controller hash pin in the
release-control test. The candidate test now verifies that it is uninstalled,
while the target profile remains bound to the separately evidenced installed
controller; deployment cannot silently treat the candidate as qualified.
The existing profile is not updated by this source PR. Successor source CI and
the staged host-controller qualification remain separate gates.

**2026-11-13 feed-contract slice (offline candidate):** Pure translators for
Coinbase Exchange BTC-USD ticker and Polymarket US BTC 15-minute market metadata
produce origin-distinct `pp_live` PostgreSQL events. They preserve original
source time, exact price text, raw payload, market identity and reference versus
settlement provenance; malformed decimal/time/window inputs fail closed. Two
focused offline tests pass. This slice does not open feeds, write PP PostgreSQL,
adapt books/candles, or authorize live collection. Those remain checkpoint 7
work requiring integrated queries, fencing and bounded PP acceptance.

**2026-11-13 PP host attempt:** PR #26 merged as `62d2944`; exact merge CI
43548036543 passed. The candidate controller `d66518ce...` was installed
briefly on the verified PP host and returned `IDENTITY_PASS` through the root
operator route. The dedicated CD key was unavailable locally, so its required
forced-command identity check was **not completed**. The previous controller
`56de886e...` was restored with no authorization or deployment dispatch.
Four PP containers remained healthy with their prior uptime; generated-mode
application source stayed `a7f7cd0`. This does **not** close stable-loopback
acceptance, change the target profile, or qualify a manual PP release. A
sanitized outcome is in
[pp-loopback-controller-attempt-2026-11-13.json](evidence/pp-loopback-controller-attempt-2026-11-13.json).

**2026-11-15 dedicated identity check (candidate):** A separate, manually
dispatched `preprod` workflow uses only the existing private runner and PP
environment credentials to call the controller's fixed `identity-v1` command.
It requires the exact installed bundle hash and records a sanitized read-only
response. Local tests and workflow validation passed. The check has not run on
PP: the approved private runner is currently unavailable. Passing this check
is required before updating the target-profile hash or deploying the loopback
release; it does not itself qualify the runtime, change the database, or enable
live collection.

**2026-11-15 PP controller binding:** The manual identity workflow was registered
from `main` by PR #30. The official ephemeral runner was checksum-verified and
used once. After a verified PP host preflight, the reviewed controller bundle
`d66518ce...` was installed without changing the database. The dedicated-key
identity run [43765449362](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/43765449362)
returned `IDENTITY_PASS` for the exact hash, then the runner deregistered.
The running PP application remains the prior generated-only release; no deploy
authority or release has been created. The updated target binding is recorded
in [sanitized evidence](evidence/pp-loopback-controller-binding-2026-11-15.json).
Its old foundation-row count is explicitly historical because an unauthenticated
PostgreSQL read was rejected. Exact profile CI, manual release and loopback
acceptance remain separate gates.

**2026-11-15 PP loopback release outcome:** PR #31 bound the verified controller
to the PP target; exact merge CI 43765914993 passed. Manual source publication
43766161257 created `v0.2.0-pp.3` for that commit. One-use CD 43766281486
passed its migration/application, schema, data, API, SSE, recovery and disabled-
flag checks. An independent operator tunnel to the host loopback route returned
HTTP 200 for dashboard, current state, health, prediction/chart/context history
and SSE; the SSE content type was correct. Maximum observed tunnel HTTP latency
was 201.7 ms across these bounded probes. Docker events show the acceptance
API restart took 354 ms from stop to start; overall collection interruption was
not measured because no continuous probe covered the initial switchover. The
one-use authority is gone and the ephemeral runner deregistered. This closes
the **private PP access sub-checkpoint**, not CP6, live PP collection, I7 or
Phase 1.75. [Sanitized result](evidence/pp-loopback-acceptance-2026-11-15.json).

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

Before enabling that connector, verify PP's own collector is OFF, its lease is
unclaimed and its database destination is PP-only. Leave production unchanged.
Run one bounded PP live window. Verify persisted feed acknowledgements,
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

**CP7 write-fence preparation:** A future `pp_live` ingest now checks the
locked `ops.writer_state.collector_enabled` value before any raw write. The
existing provenance-mode check still runs before database access. Generated
tests show disabled/mismatched live input is rejected before persistence.
Operator control, cross-VM sole-collector fencing and PP live activation are
still unimplemented; this check alone does not enable collection.

**CP7 stop-path preparation:** The lifecycle role now has an idempotent
`disable_collector` transaction. It locks the same writer-state row used by
ingestion, waits for in-flight holders, then durably turns the flag OFF and
advances the writer epoch. Generated PostgreSQL CI must prove the lock handoff.
There is deliberately no enable operation or operator API yet; PP live mode
still requires cross-VM fencing and reviewed authorization.

**CP7 source-client preparation:** Default-off read-only Coinbase ticker and
official-US Polymarket 15-minute discovery clients now have generated wire
tests for exact value/provenance preservation, current-market selection,
ambiguous identity and bounded failure. These clients do not own a collector
fence, write PostgreSQL, or enable PP live mode. Actual endpoint availability,
sole-collector operation and market-boundary acceptance remain open.

**CP7 read-only wire correction (November 16):** A bounded direct US endpoint
probe found an active BTC 15-minute market and a BBO response. The market list
uses HTTP compression, so discovery now bounds decoded bytes. Translators store
raw JSON as text for the PostgreSQL `raw_payload` column, keep source decimal
strings exact, and map BBO bid/ask prices without calling them calibrated
probabilities. Its available `lastPriceSample.ts` is labeled as a sample time,
not a book-update time. One bounded live read returned market/quote data; it
did not ingest, qualify sustained freshness, or establish collector ownership.

**CP7 default-off ingestion bridge (November 16):** The official read-only
source clients now have a narrow async bridge to `Store.ingest`. It requires
`preprod`, `pp_live`, and a distinct `pp-live-` origin before invoking a source;
each Coinbase ticker is acknowledged before the next is processed. Independent
Polymarket discovery persists the selected market before requesting its
matching BBO. A missing current market is not replaced with an old identity;
durable write holds and source failures propagate. Network-free tests cover
ordering, stop boundaries, mode/origin rejection and failed acknowledgements.
This is a code-only, default-off slice: the deployed Settings still rejects
`pp_live`, no process starts this bridge, and no operator enable/ownership
control exists. Integrated PostgreSQL, market-boundary and PP live evidence
remain CP7 gates.

**CP7 generated database handoff qualification (candidate):** A focused Linux
integration case simulates the collector flag only inside the disposable CI
PostgreSQL database. It checks that the default-OFF writer rejects the bridge,
then that market, matching quote and Coinbase price are acknowledged and read
through the actual indexed application queries, and finally that the durable
OFF transaction rejects further writes. This is test-only activation; it
neither supplies production fencing nor starts a PP service. Exact-source Linux
CI is required before calling this checkpoint PASS.

**CP7 operator-control code candidate:** A separately instantiated private
FastAPI surface exposes authenticated status and durable OFF for one fixed
`pp-live-` origin. It uses the lifecycle role's existing stop transaction;
unauthenticated calls do not touch the repository, errors reveal no database
details, and it reports process liveness as unknown rather than inferring it
from the durable flag. ON, mode changes, cloud controls, docs and public API
mounting are absent. This surface is not in the PP Compose deployment, has no
runtime token/role binding, and is not a live activation route. Host-side
binding, operator identity, production fence, process drainage/restart proof
and exact CI remain required before PP collector activation.

**CP7 prepared-OFF mode candidate:** The PP application configuration accepts
`pp_live` only with a distinct `pp-live-` origin, while environment startup
still rejects `TRADEBOT_COLLECTOR_ENABLED=true`. Its public status reports the
collector OFF. Generated/replay modes reject live origins, and production
preview remains unavailable. The existing Compose profile and release
controller still require generated mode; this code cannot activate collection
or change the deployed PP mode. Exact CI and a separate reviewed mode/runtime
release remain required.

**CP7 closed-candle input candidate:** A bounded Coinbase Exchange REST read
requests only the 17 completed one-minute buckets needed by the current
calculation window. It bounds the decoded response, rejects duplicate or
inconsistent OHLC rows, keeps exact decimal text and bucket-start provenance,
and omits missing intervals rather than filling them. The ingestion bridge
acknowledges each returned candle through PostgreSQL. Coinbase's
[official contract](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles)
warns that historical intervals may be absent and should not be polled
frequently. Poll cadence, end-to-end features and PP live performance remain
unqualified; no runtime starts this client or schedules requests.

**CP7 supervised-session candidate:** A bounded coordinator runs Coinbase
streaming, Polymarket discovery/BBO and low-frequency closed-candle reads as
independent tasks. Before opening any source and at one-second intervals it
requires both a caller-supplied ownership proof and the durable PostgreSQL
collector flag. Any lost proof, source failure or session deadline cancels all
tasks and invokes a required durable-OFF callback; a failed OFF acknowledgement
is reported as a hold. No automatic retry hides stale inputs. The flag is also
rechecked by each ingest transaction. Network-free concurrent tests and a
generated Linux database readback case cover these mechanics. This code has
**no process entry point, actual host lease, service binding or ON operation**.
Host control must supply the real lifecycle-role OFF callback and verify
process exit; those bindings remain open gates.

**CP7 dedicated operator runtime candidate:** The private status/OFF API can
now be constructed as a separate process with the lifecycle PostgreSQL role
and a file-mounted bearer token. Startup rejects the wrong environment/origin,
inline credentials, unsafe secret files, enabled paid/cloud/collector flags,
wrong database role or schema drift before serving. It has no ON route and is
**not present in PP Compose or the installed deployment controller**. Generated
tests cover fail-closed startup and unauthorized requests. The next release
control review must provision the token, bind only PP host loopback, verify
resource fit and process identity, and leave collection OFF. It cannot be used
as a production fence or activation authority by itself.

**CP7 host-bound operator candidate (November 16):** A reviewed PP Compose
overlay prepares a separate 127.0.0.1:8001 status/OFF service with a
root-provisioned token and lifecycle role. The generated-only controller
checks its exact network, secrets, disabled flags, process binding and
authenticated default-OFF response. This is source qualification only; the
installed PP controller and runtime have not changed. There is no ON route,
live source coordinator or cross-VM collector fence. Real collection and
retirement remain held pending their separate gates.

**PP provisioning preflight correction (November 16/17):** After PR #52 merged
as `a11d922` with exact preprod CI 44022560772 PASS, the existing PP host was
read through its pinned SSH route. Four prior containers remained active; no
release authority or operator token existed. The reviewed explicit token
provisioner stopped before writing because its foundation preflight required
`application_installed=false`, while the correctly deployed PP marker says
`true`. The follow-up code permits that marker only for explicit runtime-role
provisioning; foundation setup retains its original guard. PP services and
database were not changed. The new operator bundle is hash-verified in
root-owned staging but not installed. Exact successor CI and host rerun remain
required before any manual PP release.

**PP operator controller binding (November 17):** PR #53 merged as `989f461`;
exact preprod CI 44024202007 passed. The explicit PP runtime preparation
created only the missing operator token with UID 10001 and mode 0400. The
hash-verified controller `416f7326...` was installed, with prior helper code
retained. Dedicated-key identity workflow 44024832718 passed for that exact
hash; its temporary runner was removed. The four prior containers remained
running, no one-use authority exists, and the operator service has not started.
The [sanitized host binding](evidence/pp-operator-controller-binding-2026-11-17.json)
supports the separate deployment-profile PR. Manual PP release and its
functional acceptance remain open; live collection stays OFF.

**PP operator release attempt (November 17):** PR #54 merged as `6ff5393`;
exact preprod CI 44025449813 and version publication 44025817543 passed.
Manual CD 44026013400 **failed** after the PP controller completed its own
generated smoke and recorded PASS. The GitHub acceptance validator still
expected the older check set and rejected the added `operator_control` check
as `controller acceptance incomplete`. The single-use authority was consumed.
Actual PP now runs API, calculation, lifecycle, operator and PostgreSQL
containers; private API `/health` returned 200, unauthenticated operator
status returned 401, and authenticated status reported the distinct PP origin
with collection OFF. This is a partial deployment outcome, not a successful
release or I7 acceptance. The narrow successor keeps the PP operator check
mandatory and retains the production check set separately. No automatic retry;
new exact CI, version and one-use authority are required for a second attempt.

**PP operator release accepted (November 17):** PR #55 corrected the
environment-specific acceptance set and merged as `e907022`. Exact preprod CI
44026918955 passed; version `v0.2.0-pp.5` published in 44027242158. The
separate manual CD 44027443677 **passed** its generated-only API, SSE, schema,
data, disabled-flag, recovery and operator-control checks. A fresh private
host read found API health 200, dashboard source `generated`, distinct
`pp-live-pp` operator status with collection OFF, five running PP services and
no remaining one-use authority. The temporary runner removed itself. The
earlier failed attempt stays failed. Actual collection interruption was not
separately measured; PP live market and archival acceptance were not run.
[Sanitized release evidence](evidence/pp-operator-release-2026-11-17.json).
Next CP7 gates are an enforceable cross-VM sole-collector fence and an
authenticated, bounded ON/OFF session control before any PP live collection.

**CP7 offline activation orchestration candidate (November 17):** A separate,
unwired session function checks ownership before and after durable enable,
runs the existing bounded supervisor, and requires durable OFF on every exit.
Generated tests cover rejected ownership, ambiguous enable, ownership loss,
source failure, cancellation and unproven OFF. This does not provide a
qualified ownership proof, a durable enable implementation, an ON API or a
host process controller. PP and production remain unchanged; live collection
is still blocked on those controls and the cross-VM fence.

**CP7 expiring PP writer lease candidate (November 17):** Explicit migration
`0002_collector_lease.sql` adds a finite session/expiry to the durable PP
writer flag. A lifecycle-role method can set a 1–1800 second lease only for a
matching collecting generation; live ingestion checks the lease and rechecks
before acknowledgement. Expired leases read as OFF, reject writes, and require
an explicit idempotent OFF transaction to clear. The private status route
reports expiry but still has no ON route or process-liveness claim. Local
generated tests pass; Linux PostgreSQL migration/integration and exact CI are
pending. This code is not deployed to PP and does not prove or replace the
production fence, host process controller, CP6 cloud gate or retirement hold.
The first exact CI on `609713f` failed because generated schema tests hardcoded
version 1 and reused migration number 2 for their synthetic upgrade. The
successor makes those expectations follow the actual migration count; that
failure remains recorded until the successor passes Linux integration.
Successor `a9fd4bb` still failed on three remaining version-1 assertions in
the generated catalog tests. Those assertions are corrected in the next
candidate; neither failed CI run qualifies this migration.
CP6 cloud permissions/readback still gate retirement. Production is unchanged.

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

### PP live workflow dispatch choice correction, November 19 UTC

The first ON submission for pp.17 received GitHub HTTP 422 before a workflow was created. The operation choice used bare YAML `on` and `off`. Both background workers stopped and PP confirmed the collector OFF. A dedicated regression now requires four quoted string choices in the manual workflow. The installed PP controller and application image are independently bound to pp.17. The dispatch failure provides no live-collection evidence.

### PP.17 live collector stopped at a market boundary, November 19 UTC

CD run 44474562747 and READY_OFF 44474879676 qualified image `6f76adb3…`. The hosted repair and independent readback matched all 5,268 initial PP envelopes. Live ON 44476959330 then collected from the official feeds, published forecasts and independently verified 50 new hosted envelopes. At 07:15:34 UTC, with more than an hour left on the lease, the private operator reported `polymarket_bbo.invalid_or_unavailable` as discovery entered the 07:15 market. The collector had stopped itself before the observer sent OFF. Both background workers stopped. A retained all 11,041 raw rows, 11,989 structured rows were acknowledged, and none remained pending. A did not seal, B did not start, and no raw partition retired. At 07:10:14 the Coinbase input measured 41.492 seconds old, and the app truthfully abstained. [Session evidence](evidence/pp17-live-boundary-stop-2026-11-19.json)

A read of the same market's official `/book` endpoint exposed a reproducible parser defect: the fallback returns `bids[].px`, `offers[].px` and `transactTime`, while the collector expected a flat BBO response. The rejected live body was never stored, so the precise wire variant remains unknown. The successor parses both formats, records the book's exchange transaction time distinctly, and allows the next scheduled discovery following a matching empty book or a double 404. Invalid identities, prices, timestamps and oversized responses still stop collection with a specific diagnostic. A concurrent regression kept Coinbase writing through two missing-book responses before the first new-market quote. Both official endpoints subsequently passed a read-only translation for market 2680845. Full PP handoff, archive and retirement remain open.

The PP quote poll waits until its next scheduled cycle after an empty book, missing route, timeout, connection error, 429 or 5xx. A supervised regression exercises all six with a continuing Coinbase write and verifies that the first new-market quote is saved under its own identity. Authentication, malformed data, identity mismatch and write failures still stop the session.

## PP collector control under lifecycle connection pressure

PP18 exposed connection contention during archival and lease monitoring. The source correction checks the exact collector session and database expiry with the PP application role in a read-only transaction. Each recurring worker reuses its advisory-lock connection for short local transactions and releases transaction locks before remote I/O. The PP controller can release an owned worker of the same build to reprove a failed durable OFF within its original deadline. An isolated PG17 fixture filled all three lifecycle connections, rejected a fourth, preserved ownership checks, detected genuine expiry, and proved durable OFF after freeing one connection. The PP deployment and sustained B run require separate evidence.

### PP.18 retirement diagnosis and default-off session reuse, November 19 UTC

PP18 completed A→B and remote raw archival, but final fresh proof returned HOLD
`archive_limit` around 240 seconds and retained A. That trial did not satisfy the
original seal-plus-30-minute retirement condition. Standalone inventory took
20.009 seconds for 63 structured pages/57 raw objects; the final attempt has no
phase trace sufficient to attribute the timeout precisely.

A source-only successor adds bounded sanitized phase accounting to fresh proof
and a separate exact default-off retirement session reuse flag. The existing
240s/128MiB/192-request caps, short per-page read-only transactions, identity and
revision/projection checks, fail/discard behavior, and seal deadline remain.
Three matched isolated full-worker readback pairs preserve exact raw/A/newer-B
bytes and logical charges while reducing two physical opens to one; injected
setup latency produces 0.478–0.497s reused versus 0.689–0.713s cold. Those local
results establish correctness under reuse, not a hosted end-to-end timing pass.
No deployment, permit retry, deletion, binary codec, policy or clock change is
included. [Qualification and limitations](PP_RETIREMENT_PHASE_REUSE_2026-11-19.md).

### Retained A read-only replay candidate, November 19 UTC

An expired sealed A cannot use the two-market destructive verifier for a new
240-second timing measurement without correctly hitting the original seal
window. A separate finite read-only audit candidate preserves that behavior,
uses the existing reader role and one local snapshot/ACCESS SHARE lock, and
reuses the actual raw/local/rich structured proof under unchanged operation
caps. It records the original deadline separately and always denies retirement
and original-trial authority. Startup verifies existing SELECT grants locally
and remotely; no grants or host/deployment changes are included. The planned
exact PP18 replay is 57 raw objects + 63 structured pages, 28,411 raw / 31,162
structured rows, with 122 minimum logical requests including authenticated
permission preflight. Hosted timing remains unmeasured pending released source
and sealed's coordinated host window. [Candidate scope and native controls](PP_RETAINED_ARCHIVE_AUDIT_2026-11-19.md).

## PP19 controller identity

The dedicated PP deploy identity verified the release controller built from `414e3c232ba54d61bc4a71e8315fd3d1b1e620e3` in [run 44502043684](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44502043684). The previously installed controller is retained for recovery. This proof qualifies the controller binding. PP19 application deployment and the read-only audit of retained A still require their own results.

### PP.19 latest-receipt tail diagnosis and guarded candidate, November 19 UTC

The read-only retained-A audit verified all 57 raw objects, then held on its
first 500 structured page after 4.711504s. Latest-receipt lookup took 2.050960s;
cycle time remained 172.490s. Independent actual plans scan 42,133 receipts for
73 keys and spill sorts. Separate runtime-role cumulative statistics show a
1950.347ms server maximum, supporting a genuine metadata-query tail without
attributing one individual statement to that audit.

The source candidate keeps rank default and adds an exact audit-only opt-in
for tie-preserving lateral probes plus a hash/exact-identity index. Startup and
per-page ABI validation reject absent/wrong/invalid indexes; the per-page check
is fused into the existing checkpoint query, adding no wait or SQL statement.
Generated 42k/250k metadata probes avoid sort spills and match rank semantics;
modeled full rich pages improve only slightly at 42k and more at 250k. Receipt
write WAL and index storage increase. No hosted DDL, flag activation, grant,
auth/cap/clock change or retroactive trial pass is included. [Evidence and
standalone concurrent migration/rollback gates](PP_RECEIPT_LATEST_INDEX_2026-11-19.md).

### PP.20 hosted index and generated deployment smoke, 2026-11-19

The authorized concurrent index build on hosted structured receipts completed.
A new read-only connection verified its exact index definition and its ready,
valid and live flags. It occupies 4,087,808 bytes. The standalone operation
left the Supabase migration ledger untouched. Reconcile that version against
the existing index before any future bulk migration.

Release `v0.2.0-pp.20` at `b7b4c9f` passed source and preprod CI. CD
passed its migration and schema checks, then stopped during generated
acceptance. The shared `generated-pp` test origin had 9,997 pending
structured records. Two generated markets and one candle reached the 10,000
admission limit before the smoke could query the dashboard. The smoke process
exited with a generic child error. The count, last three committed rows and
the application's admission rule independently establish why the next new
candle is blocked. The separate `pp-live-pp` origin had 42,133 acknowledged
records, zero pending and collection OFF. Recovery stopped the candidate and
preserved PostgreSQL, including 28,411 sealed A rows and 9,784 B rows.

The generated test origin needs a bounded lifecycle across repeated releases.
The indexed 500-row readback timing and the retained-A verification outcome
remain open. Preserve the original expired trial verdict and the generated
records until their disposition is tested.
[CD run](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44510969827)
and [sanitized measurements](evidence/pp20-index-and-smoke-2026-11-19.json).

### PP20 indexed retained archive replay

The exact PP20 candidate image ran in an isolated read-only container while the
failed deployment's application services were stopped and the collector was OFF.
The candidate remained fenced from normal operation. The installed Supabase
index passed its definition and validity checks before the replay.

- The first 500-record read completed in **2.729 seconds**. The same page took
  **4.712 seconds** on PP19. Latest-receipt selection fell from **2.051 seconds**
  to **0.134 seconds**.
- All **57 raw objects** matched the retained partition and **62 of 63** structured
  pages completed. The final checkout held with **0.392 seconds** remaining in
  the 240-second operation, at **122 requests** and **53,777,944 logical bytes**.
  The whole replay held. The original seal deadline stayed expired and local
  retirement remained unauthorized.
- Exact revision reads accounted for **71.052 seconds** across the completed
  pages. Measure receipt and revision transfer and canonical validation separately
  before selecting a further optimization. Keep the per-page and whole-operation
  limits.

[Sanitized replay evidence](evidence/pp20-indexed-retained-audit-2026-11-19.json)

### Generated smoke pending-capacity candidate, November 19 UTC

PP20 exposed a persistent generated backlog: 9,997→10,000 pending rows under
`generated-pp` blocked the next candle before API smoke, independently of the
42,133 acknowledged/zero-pending live rows. The source candidate gives generated
smoke an append-only local PostgreSQL envelope destination, committed bytes and
independent authenticated READ ONLY exact readback before genuine source ACK.
Existing source/raw data and the 10,000 pending cap remain. Generated bootstrap
must prove 128 admission slots before service start, acceptance checks before
seeding, and periodic generated cycles consume pending work under fixed cycle
and storage limits. Live mode/probes do not enable this capability; no cloud
receipt or raw-retirement authority is produced. Source/schema/profile/native
qualification passed; no host/cloud/apply action occurred. Fenced-runtime
forward bootstrap stays a separate reviewed operator task. [Storage scope,
constraints, faults and retained-data proof](PP_GENERATED_STORAGE_CAPACITY_2026-11-19.md).


### Generated smoke controller inventory correction, November 19 UTC

PR #177 full Linux CI exposed an additional controller inventory fault after
migration: the application role correctly lacks SELECT on generated storage.
The inventory now uses the existing reader credential for that table in the
same bounded READ ONLY query shape; migration preservation/recovery comparisons
and runtime grants stay unchanged. Targeted controls cover clean/upgrade table
presence and authenticated reader selection. A local Ubuntu nested-Docker
diagnostic reproduced the exact permission failure, with its disk-gate
substitution explicitly excluded from qualification. Exact-source hosted CI
and the separate PP fenced-runtime task remain required.
[Diagnosis, scope and limitations](PP_GENERATED_STORAGE_CAPACITY_2026-11-19.md).

The corrected controller passed both clean-volume and existing-schema local
nested-Linux diagnostics at `4158ff2` under the documented disk-gate limitation.
Hosted follow-up found the lifetime-inventory SQL fixture also needed the reader
hook; it now exercises the actual reader login and READ ONLY transaction while
retaining its temporary outbox fixture. Exact-source hosted qualification is
rerun; this does not change runtime source or grants.

### Repeated PP rotation and application replay acceptance

Run A across two complete 15-minute markets, then B across two complete
15-minute markets. Verify and retire sealed A while B writes. Then switch to a
fresh A generation and verify and retire sealed B while fresh A writes. Each
sealed generation has its own 30-minute seal-to-removal deadline. The one-switch
PP18 rehearsal did not implement the second leg. The second-leg test must prove
that its bounded session covers both market pairs and final verification.

After retirement, replay one bounded 15-minute research window through the
application's historical read path. Match the exact captured input identities
and values, saved features, forecasts and official outcome labels across
active, sealed and retired generations. Key provenance by origin and
generation UUID. Exclude inputs unavailable at the forecast cutoff and join
later official outcomes only as labels. Check exact input and feature parity
against the same window before retirement and report gaps or duplicates.
Archive integrity and application replay each require their own evidence.

### PP21 controller identity and fenced forward procedure, November 19 UTC

Read-only PP inspection confirms the preserved PP20 stopped profile, exact 10,000
pending generated rows, 42,133 acknowledged live rows, both collectors OFF, and
unchanged live A 28,411/B 9,784 raw rows. The exact 0219819 code-only controller
transfer installed 9a7b with previous 1e10 retained and no DB/authority change.
Dedicated identity run 44557716430 passed. The qualified profile now binds 9a7b.
A separate source candidate supplies a one-use, PP20-state-pinned forward
bootstrap: unchanged migration inventory, migration4, genuine generated storage
readback/ACK/headroom, full smoke and failure fencing, with separate operator
receipts that cannot replace normal CD. Ledger 4 is a forward compatibility
boundary; no old-image or DB rollback, A/B deletion, cloud action, live ON or
renewed expired-trial authority is included. Actual reader SQL/native controls
pass; host migration/bootstrap and normal exact-source CD remain pending.
[Procedure, compatibility and gates](PP21_FENCED_FORWARD_BOOTSTRAP_2026-11-19.md).

### PP21 generated recovery and normal deployment completed, November 19 UTC

Exact release `v0.2.0-pp.21` at `c1da8d6` passed merged-source Linux/controller
CI 44560442424, CI Preprod 44561420990 and create-only publication 44561555039.
The actual PP20-state-pinned operator preflight and separately authorized
forward bootstrap passed, applying migration4 and genuine generated-local
storage/readback/ACKs with no DB restore. Separate normal CD 44562705669 then
passed all checks; final image is `880c013e…`, controller 9a7b. The operator
receipt remained explicitly outside normal CD acceptance.

Independent post-CD reader fingerprints matched all 38,510 original raw rows,
all 10,000 original generated source bodies (only permitted genuine ACK metadata
excluded), all 42,133 live rows/ACKs and live core/A-B/writer metadata. Live A
remains 28,411 raw rows, B 9,784; outcomes honestly remain 0. Generated snapshot:
10,416 total/6,834 pending/3,166 free admission slots, 3,582 stored envelopes,
zero ACKs without exact source-equivalent stored envelopes and valid byte hash.
Both collectors remain OFF/session NULL. Existing history-reader eligibility is
bound to the final exact source/image without changed credentials/grants.
This closes generated recovery/deployment, not a new real collector session,
30-minute observation, cloud/index change, raw deletion or original expired A
trial/retirement pass. Schema 4 compatibility and preserving all genuine ACKs
remain mandatory. Source freeze released only after these proofs.
[Completed procedure and exact sanitized receipts](PP21_FENCED_FORWARD_BOOTSTRAP_2026-11-19.md).

### November 19 — source-only point-in-time application parity prototype

Added an unregistered offline composition for one reviewed 15-minute market
window, preserving captured Polymarket inputs and exact saved feature/forecast
links across collecting, sealed and retired raw generations. Snapshot publication
availability requires independently reviewed protected calculation-input evidence;
`as_of` alone is insufficient. Delayed/future inputs are excluded or rejected and
official outcomes remain separate labels under their own cutoff. Seven generated
tests pass, including actual native PG17 partition retirement plus independent
local history_v2 receipt/envelope readback; 29 relevant existing tests pass.
No cloud/host/runtime/API/retirement activation occurred. Single-generation and
reviewed-manifest bounds do not establish full historical coverage or runtime
application parity. [Evidence, interfaces and remaining gates](PP_POINT_IN_TIME_RESEARCH_PROTOTYPE_2026-11-19.md).


### PP21 complete retained-A read-only verification, November 19 UTC

A one-off diagnostic used the immutable deployed PP21 image and the exact
CI-qualified canonical-byte-reuse transport from source `308bfcf`. All 60
backend files were checked against that source before imports/database use;
only the reviewed transport differed from the regular PP21 image. The normal
services stayed on PP21; generated services remained running and collection
remained OFF. No normal deployment, DDL/index change, permit, detach/drop,
live ON, paid AI or cloud data write occurred.

All 57 raw objects / 28,411 rows and all 63 structured pages / 31,162 rows
verified. Core work took 214.390169 s with 25.609910 s remaining under its
240-second budget; the attached-container interval was 219.458 s. The first
scoped 500-row read (73 distinct projection keys) took 2.163305 s under four
seconds. The largest structured-readback phase was 3.547267 s. The audit charged
122 requests and 53,779,250 logical bytes; nested phase totals overlap and are
not additive elapsed times.

Independent before/after fingerprints matched A/B raw data and generation
metadata, A's 31,162 outbox rows including acknowledgement state, all 57 A
manifests, live writer state and zero outcomes. The diagnostic container exited
zero and was removed. The original seal deadline was already expired;
`original_trial_satisfied=false` and `retirement_authorized=false` remain
unchanged. A fresh full A→B→fresh-A trial and deterministic history parity are
still required. Prior PP19/PP20 holds remain historical evidence, and this
single result does not establish a causal whole-audit speedup percentage.
[Source, operator receipt and qualification boundaries](PP21_CANONICAL_RETAINED_AUDIT_2026-11-19.md).


### November 19 UTC — source-only delayed-discovery continuity correction

Transient Polymarket US discovery GET failures previously escaped the market
cycle and stopped all feeds even though matching empty discovery and quote
unavailability already waited for the next scheduled poll. Discovery 404, 429,
5xx, timeout and transport failures now wait for that same bounded cadence.
No source event, timestamp or replacement identity is synthesized. Authentication,
malformed/ambiguous/incomplete discovery, invalid quotes, write rejection and
ownership/lease failures remain fatal. Existing deadlines and retry cadence stay
unchanged; temporary source delay never grants storage or retirement authority.

A generated fake-clock supervisor regression uses the actual httpx source clients
across a quarter-hour boundary: old-only listing, 429, 503, timeout, transport
error, double-404 quote routes, empty matching BBO and first exact new-market
quote. Eight normalized Coinbase ticks persist during the gap; the old market
is never queried again and original quote sample times remain intact. The live
source/supervisor/ingest/fence suites pass 39 tests (one native PostgreSQL query
test skipped without its disposable DSNs); Coinbase reconnect/timing suites pass
14. Store already reads the locked writer generation per event and ownership
checks bind the session/lease, so the collector itself caches no active UUID.
Native two-switch rotation and runtime/controller qualification remain separate.
No host/deployment, real collector, cloud or paid AI action occurred.

### November 19 — two-generation offline history evidence contract

Added an offline capture-parity auditor for two exact origin/generation UUID
windows, reusing #185 `ResearchWindow` and the actual dashboard HTTP history
contracts. Five generated tests retain immutable golden collecting/sealed/retired
captures and reject changed exact values/times, duplicate/missing forecasts,
wrong bindings and float coercion. Seven existing research unit tests and fifteen
dashboard evidence tests pass; native PG research skips without an explicit
isolated DSN. This is model retirement with an explicitly generated HTTP store,
not a new native/drop/live two-rotation qualification. No host/cloud/deployment,
collector/lease change, API registration or feature recalculation occurred.
Actual chart remains current/local raw only; context outcomes unsupported;
prediction HTTP omits snapshot IDs. #185's 2,000-row scan cannot cover real
retained A; indexed bounded reading, cross-generation merge where needed, live
labels and recalculation remain gates. Checkpoint 3 stays OPEN.
[Evidence shape, qualification and live gaps](PP_TWO_GENERATION_HISTORY_EVIDENCE_2026-11-19.md).


### November 19 UTC — source-only symmetric exact retirement readback

The two-market verifier previously hardcoded sealed A and collecting B despite
its exact UUID targets and underlying SQL retirement authority already supporting
opposite slots. It now accepts A→B or B→fresh-A only when both slots are valid
and the collecting generation's actual start exactly matches the sealed
generation's actual seal. The two-market permit issuer now checks that same
handoff timestamp. Standard-profile behavior, all request/byte/time limits, each
30-minute seal deadline, admin freeze, one-use exact ticket and environment gates
remain. Migration 0003 and every applied migration checksum are unchanged; the
privileged function already checks opposite slots and exact UUIDs. Profile
windows remain enforced by the existing issuer/verifier layer rather than a new
database authority or migration.

Eleven generated/native controls pass without skips on a fresh disposable local
PostgreSQL 17 fixture with restricted migrator, lifecycle and app logins. Actual
psql issuance and privileged removal succeed first for A while B commits, then
for B while a distinct fresh A commits, consuming two distinct tickets. Wrong
handoff time rejects issuance and verification; an original-A target and used
first ticket cannot authorize B. Separate both-leg raw/structured readback
rejects unavailable raw, corrupt structured records and expired seal windows.
Existing reader drain, protected evidence, rollback, forged checkpoint and permit
reuse tests also pass. Generated transports represent remote archives; these
results are not hosted cloud readback, real-market capture or PP retirement
evidence. No host/deployment, cloud, grants or schema action occurred.

### November 19 — executable read-only HTTP history capture (source only)

Added a loopback-only GET evidence client for exact two-UUID retained/retired
history pairs, with immutable UUID bindings as each becomes known. It uses the
existing `/history/archive/{uuid}` route for both attached sealed/verified rows
and authenticated retired archive rows; no restricted-DB fallback is needed.
Full original HTTP bytes/hashes, exact rows/predictions, state and initial SSE,
UTC/monotonic timings and explicit missing-data gaps are retained under bounded
request/page/byte/deadline limits. Nine network-free tests pass; real host/tunnel,
cloud, permissions and retirement operations were not performed. Current chart
and unsupported context limitations remain open. Existing old verified A plus
disabled collecting B cannot become a fresh A-first trial while both slots stay
occupied; source fences rather than relabeling or retrospectively passing A.
[Executable procedure, source constraints and qualification](PP_HTTP_HISTORY_CAPTURE_2026-11-19.md).


### November 19 UTC — source-only stopped historical B drain candidate

The user requested preserving/draining old PP21 A/B to Supabase before a fresh
trial. Old B remains collecting-disabled, which correctly excludes it from raw
sealed archival. A default-off exact-old-origin local maintenance command now
seals reviewed B only under global admission and worker/writer locks, binding
its UUID/count/epoch and a fresh operation/source receipt. It leaves the writer
pointing to sealed B, creates no successor, changes no A seal, and grants no
retirement or original-trial authority. Identical retry preserves its original
maintenance seal; normal writer activation then rejects the sealed state.

Twenty generated/native tests pass without skips on disposable local PostgreSQL
17.2. Genuine Store capture and an in-flight write prove the OFF/count barrier;
wrong scope/count/epoch, enabled/other collectors and journal rollback preserve
data. Existing bounded structured/raw workers reject corrupt/unavailable
readback, then archive/verify successfully without removal. Retained A metadata
and catalog, raw/core/dedup/source-body evidence remain exact. Hosted release,
actual cloud drain/readback and independently scoped fresh trial remain pending.
No schema/grant/host/cloud operation occurred. [Finite route and limitations](PP_HISTORICAL_DRAIN_SOURCE_2026-11-19.md).

### November 19 — exact fresh-trial cloud authority candidate (source only)

Prepared an additive review-only cloud scope for exact
`pp-live-pp-trial-20261119-01`: separate structured writer/reader NOLOGIN roles,
new independent Storage Auth identities and exact origin-hashed raw path. Existing
old-origin identities/policies/data stay unchanged. Explicit adapter arguments
pin trial DSN role/app name, JWT admin metadata, raw prefix and read-only verifier
behavior; no environment prefix widens cloud access. Six unit controls and six
owned disposable native PG17 tests pass, including genuine immutable receipt/
envelope readback through a separate read-only role. No cloud inventory/mutation,
Auth provisioning, secret deployment, host action or collector activation occurred.
Service wiring, fresh grant/catalog review, actual new identities/secrets, bounded
live API denials/readback and separate old A/B disposition remain prerequisites.
[Policy artifacts, exact dependencies and reversible deployment](PP_TRIAL_CLOUD_ORIGIN_2026-11-19.md).

### November 19 — source-only exact trial host preparation

The host-control candidate binds the one exact trial origin and initial-A UUID
into existing enter/ON authority. Permit-bound enter stops generated services,
prepares an exact OFF A under the shared database admission fence, preserves
historic A/B, then proves the trial API/operator OFF. Permit-free leave/OFF never
prepares. Native restricted-role allocation and host/profile/authority fixture
checks pass. Trial ON and legacy cloud sidecars remain explicitly held until
separate exact trial writer/reader credentials and cloud readiness proofs are
integrated; no deployment or host/cloud action is claimed. See
[scope and evidence](PP_TRIAL_HOST_PREPARATION_2026-11-19.md).
