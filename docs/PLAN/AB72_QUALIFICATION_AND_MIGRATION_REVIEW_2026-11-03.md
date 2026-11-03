# 72-hour A/B/core generated qualification and consolidated release review

This implements selected policy2470103. It supersedes the old5GiB-only planning
NO-GO; it does not change production. **Overall production qualification: NOT PROVEN.**
The deliverable includes working generated files/code/tests, not just a design.
This is the single review package; it is not permission to migrate or restart.

## Exact scope and reproducible generated operations

Source/CI/measurements are frozen in the completion section below. Code:
`backend/prototype/raw_generations.py`, `feature_inputs.py`, `qualify_ab.py`,
`capacity.py`; generated tests test_raw_generations/test_ab_feature_inputs/
test_ab_capacity. No live collector/API/lifecycle module imports the prototype.
Preserved application/price/index/verifier code is reused or left unchanged,
including features.VERSION2,forecasts.baseline and rollover/publication controls.
No new branch/worktree/chat,AWS service,queue or writer-coordinator service.

```
.venv/bin/python -m unittest discover -s backend/tests -p test_raw_generations.py
.venv/bin/python -m unittest discover -s backend/tests -p test_ab_feature_inputs.py
.venv/bin/python -m unittest discover -s backend/tests -p test_ab_capacity.py
# One fixed4000-row qualification, not a batch/settings matrix:
.venv/bin/python backend/prototype/qualify_ab.py
```

These commands operate only on private owned generated-ab-* fixtures. CLI uses
170s work/180s total,512MiB Linux address space,2GiB aggregate generated workspace;
Mac RSS is measured separately. Source indexed query/feature gate30s and save/
heartbeat<1s/noerrors unchanged. FULL WAL with no manual checkpoint/truncation.
There is no production execute mode in this prototype.

## Implemented A/B/core protocol

- core.db persists registry,monotonic global event identities/intents,markets,
  candles,RESTprices,outcomes,real feature snapshots/predictions,model/abstention
  details,archive manifests and copied protected evidence. The persistent identity
  ledger and copied metadata/price evidence are part of core capacity, not free.
- Two slots A/B use fresh UUID filenames. At mostoneactive and onelivegeneration
  per role are DB unique constraints. New receipts go to the active generation;
  at72h the next write prepares/publishes a fresh other role. Original source
  timestamps,exact decimal text,payload number text and provenance remain.
  There is no A-to-B copy. Source-late events route by current receipt, not source
  time. Receipt regressions are explicitly rejected,not inserted into sealed data.
- Core preparing state->file initialized->atomic core publish active/sealed.
  Per-event coreintent->raw FULLcommit->coreack. One pending intent maximum is
  enforced by a partial unique index; another event is refused until recovery.
  There is no claim of atomic transactions across different WAL databases.
- Restart finishes preparing generations and exact pending intents idempotently.
  A surviving retiring file requires fresh proof before unlink. A missing file
  with durable retiring state finalizes retired. Unknown/orphan sidecars stop.
  All fault points and a real os._exit after raw commit are tested.
- Readers span A+B and fail explicitly on query bounds. Price/metadata projection
  uses the existing feature SQL with matching generated expression indexes, one
  candidate per generation,core RESTprice/metadata pin and17candles. Calculation
  uses a query-only RAM database and the real unchanged feature/baseline engine.
  A flat-history fixture,including future-source records,has identical feature
  values,quality and evidence IDs. Generation IDs are added to persisted evidence.
- Exactlyonecollector thread may insert raw/handoff. Feature/lifecycle workers use
  their own SQLite connections. The fixed profile has one feature executor and
  awaits its prior job; no accumulated queue. Core prediction+copied evidence is
  one coretransaction. Existing186s discovery/serial-worker/cancellation and30s
  publication tests remain in the backend suite; no production routing inferred.

## Archive and retirement safety

Initially hourly:archive completed receipt-hours in batches<=1000. Generated
MemoryArchive/FileArchive fixtures implement the existing private-object and
raw_archives upsert contract. This performs no real Supabase network operation.
No AWS S3 infrastructure. Archive encoding preserves original JSON number text;
existing retention_recovery.verify_archive/build_manifest check authenticated-
channel fixture readback,SHA256,size,count,full boundaries and exact reconstruction.
Real Supabase authentication/schema/RLS integration is not claimed by a fixture.

Retirement requires sealed/nonactive,newestreceipt strictlyolder72h,fresh readback
of every applicable object,exact local row/registry/coverage counts,nonoverlapping
manifest intervals and all protected records available/checksummed in core. Final
reference check and retiring authorization share a core writertransaction. Readers
and OS file descriptors must be drained. Linux root visibility is required for
complete OS proof; unknown visibility fails closed. Ordinary metadata connection
close lets SQLite handle sidecars; no separate WAL/SHM deletion or manual pragma.
Only generated closed main files are unlinked. Core evidence/references persist.

Tests refuse archive outage,corrupt/missing object/coverage,wrong generation,
active/too-young generation,open managed/unmanaged readers and missing protected
records. Tests exercise retirement while current-generation writes proceed and
role reuse with a new UUID. Blocked generations are retained. At the next boundary,
if both slots remain occupied,ingestion STOPs before accepting another intent.
No third slot,automatic overwrite,unbounded backlog or unlimited outage claim.
A large fresh archive readback near reuse can itself take time:normal sustained
continuity at production volume remains a required measurement,not a scaled PASS.

## Numeric capacity proposal — arithmetic fits; production sizing NOT PROVEN

Bounded stat-only VM observation2026-11-03T20:10:19.451695Z:
legacy main5323907072bytes,WAL45171712bytes,total5369078784bytes;
filesystemfree49807454208bytes,total61285326848bytes. No payload scan/service change.

| Component | Preliminary allowance and basis |
|---|---|
| Core,its indexes,ledger and protected evidence |5GiB cap,derived by rounding measured entirelegacy main up toGiB; NOT a measured current/future production core requirement|
| Two72h raw generations including indexes |10616832000bytes=9.8876953125GiB at20KiB/s for144h,NOT72h|
| Aggregate WAL core+A+B |130MiB,roundup3*max(observedlegacyWAL,scaledpeakWAL); empirical allowance,NOT a worst-case bound|
| Rotation/restart/recovery allowance |130MiB,roundup3*max(observedlegacyWAL,scaledwholefixture peak); empirical allowance,NOT proven fullscale recovery demand|
| Retained legacy during transition |5369078784bytes=5.0003442764GiB; no deletion/shrink/free-page credit|
| Archive/TEMP/private proof working space |2GiB filesystem allowance,using existing generated workspace ceiling; fullscale peak unmeasured,not a declaration that TEMP caches cap disk|
| Actual remaining filesystem free floor |10GiB required under projected peak|

Proposed ONE aggregate DB+WAL ceiling,rounded upward only after these terms:
**NORMAL16GiB=17179869184bytes**;
**TEMPORARY MIGRATION21GiB=22548578304bytes**.
Do not apply either allowance separately to A and B. Count all retained/staged
physical DB/WAL files,including interrupted transition files. Report SHM/TEMP/
archives separately against filesystem work+reserve. Reusable pages are never
physical headroom. Prototype's2GiB guard remains unchanged; proposed16/21 not applied.

Projected filesystemfree after max migration allocation and2GiBworking:
49807454208-(22548578304-5369078784)-2147483648=30480471040bytes,
about28.39GiB,above10GiB. This is filesystem arithmetic PASS under those proposed
caps,not a representative core/rate/WAL/TEMP qualification PASS. Recompute before
any approval/execution using then-current actual files; no stale capacity pass.

The20KiB/s input is an old whole-DB planning estimate,not measured daily raw/index
arrival or worstcase burst. The short-window0.76..0.97GiB/day extrapolations and
1.65GiB/day planning input remain labelled estimates. Generated saturation write
throughput is not a production arrival rate. Fullsize current core+new ledger,
actual input shapes/cardinalities/daily growth,WAL/TEMP and restart peaks remain
explicit NOT PROVEN. A core quota can eventually stop ingestion; no unqualified
claim of indefinitely bounded structured/identity history or safe pruning.

Delayed-retirement allowance is bounded by TWO slots; no extra generation beyond
those is budgeted/created. If the inactive role cannot retire,STOP at the boundary.
Alerts/early warning are needed in the future adapter,not a promise of arbitrary
cloud outage continuity. The proposed temporary ceiling would be reviewed at
cutover+72h and expire at cutover+96h. No automatic extension or forced file
retirement; if legacy cannot safely retire and normal allowance does not fit,
collection remains STOP. These are proposed values,not production authority or
an extension of the expired November2 cap-review deadline.

## Consolidated migration/release sequence and unresolved execution gates

This is one review sequence. **It is not yet execution-ready**:a production
legacy/app/cloud adapter has not been qualified,so no false production entrypoint
or deployment SHA is supplied. Prototype source SHA/CI is not a live release.

1. Bind fresh one-use authority to a fully integrated qualified release,helpers,
   runtime/database/schema identities,complete inventories,capacity caps/expiry
   and explicit work/recovery limits. Discard no expired/consumed evidence; the
   old cap-review deadline passed and is not revived by this policy.
2. Preflight actual filesystem≥10GiB after all peak work,onecollector,flagsOFF,
   stopped-collection status,source/runtime/schema,retained legacy/WAL and every
   core/A/B/staging allocation. Capture prior states of API,ensemble,lifecycle,
   soak timer/oneshot. Only after approval quiesce known writers/monitor and drain
   handles. No unknown process signaling,backup/snapshot,VACUUM or manual WAL.
3. Complete full quick_check and foreign_key_check for every applicable file with
   owned children and the preserved atomic progress diagnostics. The old legacy
   scan timed out1790s and its phase was not recorded. A new completion budget
   cannot be certified from4000-row fixtures. Existing1800verification/600other/
   10reap/180recovery/2590absolute limits are not silently expanded; an evidenced
   amendment,if necessary,must be part of ONE final approval. No unchanged heavy
   production retry is authorized. Max production interruption authorized now:0.
4. Proposed transition is forward-only newwrites:retain the ORIGINAL legacy file
   as read-only transitional history; do not clone it or copy all A into B. A
   bounded logical structured import must preserve every market/prediction/outcome,
   archive cursor and required evidence,with stable ID mappings. NewA starts new
   receipts; legacy+A cover the retained window until B exists. This transitional
   reader adapter and logical import are NOT IMPLEMENTED/qualified in this prototype.
   Keeping legacy during transition is included in21GiB,not hidden in core.
5. Existing direct prediction_context_links.outcome_observation_id FK must resolve
   to preserved core evidence,not an inaccessible raw table. Seed observation,
   snapshot and prediction identity namespaces above legacy maxima or retain exact
   old IDs; never reinterpret localIDs. Embedded metadata_observation_id,price
   input_id,prior_snapshot_id,evidence_json and Supabase source-ID/cursor formats
   require a qualified old-to-new mapping. Prototype demonstrates global event
   IDs/coreevidence FKs/generation refs but does NOT convert a production schema.
   Its core market/prediction representation is not a drop-in legacy SQL schema.
6. Deploy only that integrated runtime with tested independent rollover/health,
   one serial feature worker and worker-owned connections; reuse prepared price/
   index work after qualification. Actual REST/WebSocket/lifecycle paths currently
   still use the legacy DB. Their live routing/Supabase structured-ID/upsert adapter
   remains a mandatory gate. No config/unit/migration change is implicit here.
7. Failure before cutover:reapowned children,leave originaldata intact and collection
   stopped;restore only controls that cannot resume collection unsafely. After
   durable new writes:code rollback CANNOT undo those records or safely resume an
   unaware monolithic writer. Preserve all generations/registry/intents,STOP writes
   and recover forward via the qualified adapter. Never restore DB contents or
   silently drop committed records. Any actual service restoration/rollback timing
   requires explicit bounded policy in the single final authorization.
8. Retire legacy only after structured/evidence import verified,its newest raw
   receipt strictlyolder72h,applicable archivesfreshlyverified and all ownersdrained.
   Old file remains in aggregate accounting until a separately approved retirement
   actually occurs. On fullslots/unknownrefs/archivefailure preserve files/STOP.
9. After safe cutover do one bounded functional smoke:API/currentmarket/source
   freshness/advancingRAM andpersistence,realfeature/model evidence,pubage/market
   guards,dashboard/SSE,services/flags/aggregatephysical allocation. Restoretemporary
   helpers/revokeauthority,report actual interruption andremainingcapacity,yield.
   No automatic retry/background soak. Later sustained72h rotation,144h capacity,
   archive outage and real-boundary/feature freshness requirements stay outstanding.

One final production approval must contain exact integrated SHA+CI,all numeric
caps/expiry and measured timings/maximum interruption,recovery/failure states,
identity/archive protections and smoke/sustained-validation gates TOGETHER.
**No production approval is requested on the current scaled prototype.**
The current blocker is unqualified production integration/fullscale evidence,
not the former5GiB planning prohibition. No alternate architecture is proposed.

## Frozen qualification evidence and result

Exact prototype source **02e01436ffab853d4fda20cf0a2be2c3e5628455**;
[CI41715155473 PASS](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41715155473).
273backend tests,17Linux-root generated lifecycle/profile tests and112deployment
controls passed. The raw-file retirement,unmanaged-handle refusal,crash-role reuse,
current-writer interference and4000-row profile actually ran under Linux root.
This is hosted Linux evidence,not representative Lightsail/production evidence.
The dependency and fixture shapes/scale differ; no production benchmark was run.

| Fixed Linux generated measurement | Observed |
|---|---:|
|Records /archives completed|4000 /4000|
|Real feature cycles /nonabstaining baseline predictions|13 /13|
|Maximum save duration|21.975ms|
|Maximum heartbeat delay|239.292ms|
|Maximum bounded rolling-input query|62.060ms|
|Maximum real feature+baseline+corecapture cycle|7.617ms|
|Sampled source age in simulated clock|0.0s|
|Rotation /retirement|9.895 /119.121ms|
|Archive work /local fixture throughput|0.312587s /12796.4rows/s|
|Whole profile /RSS|18.128395s /43655168bytes|
|Peak fixture disk including WAL/SHM/objects|9668381bytes|
|Errors /workload complete|0 /True|

| Core/raw physical/index allocation | Main bytes | Index bytes (included in main) |
|---|---:|---:|
|core.db|1392640|520192|
|raw-4f72058660e54fbb8dd49a90cf514a86.db|2002944|434176|
|raw-a150fe371d814b1cadaf13dd7f38ce39.db|1994752|425984|

Per-file sampled WAL peaks: `{"core.db-wal": 4148872, "raw-4f72058660e54fbb8dd49a90cf514a86.db-wal": 119512, "raw-a150fe371d814b1cadaf13dd7f38ce39.db-wal": 98912}`.
All sampled SQLite connections were FULL(2). Peak bytes are sampled,not a hard
maximum for arbitrary inputs. Archive objects were generated/local/highly
compressible512-byte payload fixtures; throughput is not Supabase network speed.
Query/feature numbers include actual existing formulas; snapshot/publication age
under real source/receipt clocks,live discovery/API/SSE and full production data
remain NOT PROVEN. Simulated source age0 is not real market freshness. The separate
concurrent-retirement test passed save<1s; its exactmaximum was not retained.
Queue0 andoneoutstandingworker are policy bounds; a DB unique constraint limits
durable pending intents to1. No backpressure data is silently queued.

The profile actuallycreated core.db plus A and B at:
- A: `/tmp/generated-ab-a7d3f1ah/raw-4f72058660e54fbb8dd49a90cf514a86.db` (sealed before retirement).
- B: `/tmp/generated-ab-a7d3f1ah/raw-a150fe371d814b1cadaf13dd7f38ce39.db` (active before retirement).
- Core: `/tmp/generated-ab-a7d3f1ah/core.db`. A was safely retired; B and core retained.

Initial localprofile FAIL is preserved:its clockfirstactivatedA at71:59 rather
than0,so the nominal72event was not a rotation. Timelinefixed/unit-tested; no
threshold change or unchanged retry. Correctedpre-freezeMac componentprofile
createdA/B/core but returnedNOTPROVEN for fullOSdrain,retainingallfiles. Final
Linux source adds realfeaturecapture and is the authoritative measurement above.

Capacity recomputed from finalprofile remains16GiBnormal/21GiBmigration; projected
free30480471040bytes. **Checkpoint1 NOTPROVEN**,filesystemarithmeticPASS.
**Checkpoints2/3 PASS for generated protocol/correctness/safety**.
**Checkpoint4 PASS_SCALED**,realproduction freshness/representativeness NOTPROVEN.
**Checkpoint5 NOTPROVEN /not production-executable** untillegacy/app/cloud schema
adapters,representative core/rate/burst/WAL/TEMP/recovery and completeverification
finish time arequalified. Current2GiB fixturelimit cannot itself prove the proposed
16GiB envelope; any larger generatedresource qualification needs explicit review,
not a silent limitraise. This is a remaining gate,not evidence againstA/B design.

No actualproductionguard/configuration/deletion/DBcopy/snapshot/restart/manualWAL/
service/firewall/AWS/paidAI operation. Productioncollector remainsstopped under
lastverifiedd56b4a7,retention/paidAIOFF,cleanup0. I7/Phase1.75OPEN. Multi-cycle
andreal-boundaryproductionacceptance NOTPERFORMED; no automatic soak scheduled.

Private sanitizedmetrics/source manifest (no DB or credentials):
`/Users/jake/Documents/ChatGPT/TradebotAnalytics/evidence/phase175-baseline/lifecycle-implementation-20261031/ab72-prototype-02e0143/`.

One next milestone is the existing-design production compatibility and
representative qualification gate,then a single consolidated execution approval.
Do not deploy the prototype,approve uncertain budgets as proven or reopen the
architecture selection. This report is the one review package,no approval
fragments or production execution request.

| Prototype source | SHA256 |
|---|---|
|backend/prototype/raw_generations.py|d1a7b87c9c0d47ae25992d7b7223d42478867e65c9bc4ba1cf86e379020bae28|
|backend/prototype/feature_inputs.py|769406d686ead516f6aeed637678a5df4be40dca3af4807a3528c0ee0a107048|
|backend/prototype/qualify_ab.py|d1e31da00d643e74cac778f75d6395149c1848ce6d15fdd5a556e3a4c8d36de0|
|backend/prototype/capacity.py|5269b6b2836294e2205e498352f9b9a4d22e41ecbecce112d6bbd564b2bf9fb1|
|.github/workflows/python-tests.yml|145534ea90a7ec0a82df884a1e1bf7744fa011ea36fdf94be5a2f171bc148f1d|
