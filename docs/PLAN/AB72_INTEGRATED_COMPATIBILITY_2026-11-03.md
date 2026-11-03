# AB72 integrated compatibility checkpoint — November 3, 2026

Frozen candidate: `b39c83755608b8065a0099c7d10b3ca8ad0f5800`.
Exact-commit Linux CI: **PASS**, [run41726968944](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41726968944).
Result: **PASS for the generated compatibility checkpoint**; production readiness
remains **NOT PROVEN**. No current test failure is waived. This report supersedes the
intermediate retry-only disposition for paths actually exercised here. It does
not supersede the 72h policy or grant production permission.

## Implemented layout and routing

`ApplicationStore` operates only in private generated-ab directories, with a
local generated-legacy file. Routing and retirement each default disabled;
retirement without routing is rejected. No production path, environment enablement,
CLI migration or helper-install route was added. Ordinary monolithic operation
keeps its existing connection path. No new service, writer thread, writer queue,
native dependency, production index or price/feature version was introduced.

The native application schema coexists in core with `ab_` protocol tables. Legacy
raw is attached read-only; structured records retain their actual schemas and
original IDs. Source raw is not cloned. TEMP views read protected core observations,
retained legacy raw and pinned A/B files without duplicate observation identities.
Worker connections belong to their creating thread and hold raw reader leases.
Exactly one process owns Store's lock. Existing Store locking serializes ingress
writes, with a 0.5s contention hold and no accumulated record queue. SQLite's5s
busy timeout is unchanged and has no new retry loop.

New IDs reserve every legacy observation ID plus durable legacy stream sequence
identities. Composite source/event IDs, direct outcome FKs, snapshot/prediction
relationships, embedded metadata/price references and cloud cursors are preserved.
Unknown evidence schemas/references block migration. The audit streams schema/row
fingerprints; generated qualification bounds are10000total rows,128MiB encoded
audit input and1MiB/row. These limits are not production-volume qualification.
News external-content FTS is rebuilt from preserved structured rows; unknown
virtual schemas stop. No full database copy/backup/snapshot or raw A->B copy occurs.

Actual collector saves, streaming supervisor/REST worker, feature capture and
forecast worker, LiveState publication, ensemble/case reads, FastAPI dashboard/
history and lifecycle cycle accept explicit generated adapter seams. Features
calculate the unchanged feature version and baseline. Stale publication guards
remain unchanged. A critical raw error latches a runtime hold and stops streaming;
full slots cannot trigger repeated saves or extra REST reference-price writes.
No field is substituted with synthetic successful data when a path is unavailable.

Migration's core transaction publishes its completion marker only with successful
identity/reference checks. Raw intent -> raw commit -> core acknowledgement keeps
the existing forward-recovery protocol. After new writes, a legacy-code rollback
is unsafe: the connection helper refuses the AB marker, and guarded application
tables reject direct legacy SQLite writers without the adapter function. The
supervisor drains worker-owned connections before teardown; Store ownership cannot
be released with application connections outstanding. Committed data is retained.
These guards do not constitute an approved production cutover/recovery procedure.

## Existing Supabase compatibility and hard deadlines

The adapter reuses `SupabaseHTTP` routes/auth-header construction, existing
structured sync, private raw archive format, raw_archives schema and source-ID/
composite checkpoint functions. New generation manifests carry generation identity
inside metadata and generation-prefixed paths; a batch cannot span generations.
Short generation batches do not falsely report caught-up. Raw JSON number text,
exact decimal strings, source time and original payload evidence survive archiving.

Conditional object upload uses x-upsert:false. Existing content must match byte
for byte. Ambiguous POST/409/5xx reconciles remote object identity with a GET,
without another POST. Manifest insertion uses ignore-duplicates and content/
boundary readback comparison. Authentication/conflict/malformed/verification errors
hold. Only safe private GET transient errors retry, at most3total attempts with
1s/2s backoff and at most250ms jitter, inside the original deadline. Retry-After
cannot reset or exceed it. No SQLite, maintenance, migration or retirement retry
was introduced. Remote archive/checkpoint confirmation precedes local advancement.
A crash before local advancement replays deterministic evidence; after advancement,
exact cursor state survives. Structured upserts remain one-attempt operations.

One killable child encloses each entire logical request, retry attempts, body
reads and backoff under the caller's original monotonic phase deadline. Parent
receives bounded nonblocking output and kills/reaps a late child. HTTPX inactivity
timeouts alone are not called hard deadlines. Trickled bodies, exhausted backoff,
late responses and output limits are tested. The child supervisor requires a
single-thread lifecycle process and supports fork; it rejects threaded callers.
This matches the existing separate lifecycle-process model, not collector HTTP.
Kernel child-reaping latency is not a hard-real-time hardware guarantee.

Wire tests use actual SupabaseHTTP with MockTransport and private generated object
files, never live credentials or cloud mutation. They prove generated request/
identity behavior, not actual authentication, schema deployment or RLS permission.
The prior overwrite-capable native cloud client is not certified for AB simply
because it remains available to the unchanged monolithic path.

## Requirement and failure-injection evidence

All PASS labels below are limited to generated scope unless stated otherwise.
Skips are NOT PROVEN until their required platform execution is evidenced.

| Requirement / injected failure | Status | Evidence |
|---|---|---|
|Default routing/retirement holds; partial configuration rejected|PASS generated|test_default_holds_and_legacy_sparse_identity_reference_preservation; Store rejects production paths. No production enable route exists.|
|Missing/stale/mismatched sources and expired market; recovery only on current source time|PASS existing engine + generated integration|test_rollover_health source replay/future/expiry/mismatch/recovery cases; real API health returns degraded with reasons for missing data.|
|No stale/wrong-market publication; discovery independent of serial features|PASS existing engine + generated integration|186-second simulated boundary test; test_actual_feature_worker_and_full_lifecycle_cycle and actual supervisor/drain test. No production real-boundary acceptance performed.|
|Legacy IDs, sparse ID reservation, direct and embedded evidence refs|PASS tested schema|Default identity test; every_direct_legacy_fk test; missing/unknown embedded reference tests; foreign_key_check has no violations. Source bytes/IDs are retained.|
|Real collector/feature/history/ensemble/lifecycle functions|PASS generated|test_actual_collector_features_history_lifecycle_across_ab; actual worker, supervisor, API history/dashboard and REST/feature concurrency cases. No production application adapter launch.|
|Exact original price/metadata feature input equivalence|PASS generated|Legacy flat feature calculation equals routed calculation; existing test_ab_feature_inputs covers source future/lateness and baseline evidence.|
|Duplicate identical evidence vs conflicting replay|PASS generated|Exact observation/stream identities, legacy sparse replay tests, existing test_raw_generations duplicate/conflict tests; conditional cloud duplicate tests.|
|Exactly one collector owner and drained connections|PASS generated|Owner-release/concurrent-owner refusal, wrong-worker checks, actual supervisor draining; existing raw worker tests.|
|Concurrent REST and feature reads/writes, current writer during retirement|PASS generated components|Real REST/feature worker case; existing Linux-root current-writer/retirement test. Representative deployment interference remains unqualified.|
|Concurrent raw readers, late/unknown references, active/young generations|PASS generated exact-CI Linux root|Existing raw protection/reference guard tests; application reader/retirement test passed final Linux root CI. Unknown visibility blocks unlink.|
|GET timeout/429/5xx and retry count/backoff|PASS generated|test_ab_archive_reads; actual-wire transient tests and shared hard deadline.|
|401/403, missing object, wrong/truncated/corrupt readback|PASS generated|Actual-wire auth/truncated/wrong-object cases; existing exact archive checksum/count/scope tests; missing coverage retains raw files.|
|Ambiguous upload/manifest response; duplicate/conflicting manifest|PASS generated|test_ab_cloud_compatibility immutable upload/manifest cases verify exactly one POST, compare remote state and preserve conflicting bytes.|
|Archive upload/verification/manifest/checkpoint failures|PASS generated|test_archive_failures_do_not_advance_checkpoint_or_manifest checks old cursor and zero new local manifest; actual wire/archive checkpoint test retains original source IDs.|
|Hard deadline including body, all retries/backoff and bounded output|PASS tested OS cases|test_ab_hard_deadline kills/reaps trickled response; original deadline passed across all cloud calls; no orphan worker thread.|
|Migration, intent/raw/ack, seal and active publication crash boundaries|PASS generated process tests|Real os._exit matrix; separate seal-existing-A/publish-B process matrix; restart reconciles pending intent and exact references.|
|Feature evidence/snapshot/prediction and archive confirmation/checkpoint crashes|PASS generated process tests|process_crashes_at_feature_and_archive_commit_boundaries checks atomic pins, exact cursor before/after commit and idempotent feature restart.|
|Retirement authorized/normal-close/file-removed process crashes|PASS generated exact-CI Linux root|Real-process root test passed final CI41726968944. Fresh on-disk object readback and surviving core refs checked.|
|SQLite FULL/quota, low allocation headroom, read-only write rejection|PASS generated|Actual max_page_count quota failure, aggregate guard refusal and actual query-only handle failure. No host filesystem was filled.|
|Raw I/O error, missing file, symlink, changed legacy, unknown sidecars|PASS scoped generated tests|Injected OSError before ack leaves one pending intent; source identity changes stop; missing/symlink tests and existing protocol unknown-sidecar cases hold. Not physical disk-failure qualification.|
|Full slots/cloud outage; no overwrite/unbounded backlog|PASS generated|Full-slot latch test, original full-slot/cloud outage tests, one_pending_intent constraint; no third slot or automatic retry.|
|Legacy binary restart after cutover|PASS generated guards|Old collector connect and direct SQLite writes rejected; committed new raw and structured history survive forward reopen.|
|Partial stop/checkout, verification/startup timeout, child reaping, helper/rollback failures|PASS existing control suite / NOT PROVEN AB cutover|Existing112deployment/maintenance tests apply to their routes. No AB production controller/procedure has been installed or qualified.|
|FULL durability|PASS configured / NOT PROVEN physical power loss|FULL remains configured; process exits do not certify power-loss/hardware behavior.|
|Aggregate DB/WAL/TEMP budgets, realistic bursts and blocked archive/reader growth|NOT PROVEN production|Existing generated ceilings unchanged; actual production core growth/throughput/space budget still requires representative qualification.|
|Actual cloud authentication/RLS/schema compatibility|NOT PROVEN|No production or real-cloud mutation authorized/performed. Generated wire compatibility is narrower evidence.|
|Exact exported production release, migration and verification budget|NOT PROVEN|This is a source qualification candidate, not an approved production release/procedure.|

## Validation record and skips

Before the final embedded-reference and additional process-boundary cases, full
local macOS suites passed305backend tests with8skips and112deployment/maintenance
tests with3skips. Focused later cases passed. Final exact-tree Linux CI is required
for the complete candidate; source-only or prior-tree evidence is insufficient.
No unchanged qualification trial or production attempt was rerun. Required full CI suites run on changed candidates, not an unchanged production qualification retry.

Local backend skips: four Linux-root raw retirement/profile cases, application
reader/drain retirement, Linux strace lock instrumentation, and two Linux
qualification supervisor cases. The added process-retirement test also requires
Linux root. Linux root application/protocol steps explicitly run those retirement
cases. Local control skips: Linux process-group kill/reap, parent interruption and
bounded verification child. Node/dashboard test ran locally. CI's strace-dependent
skip must remain explicit if strace is absent; nothing was installed for tracing.

No production database was opened, copied, archived, deleted or changed in this
milestone. No service was restarted, no workflow deployment was dispatched, and
no storage-policy/paid-AI/retention flag was changed. Collection remains at its
recorded storage STOP. Proposed16GiB/21GiB budgets and all production operations
remain unapproved; there is no implicit deadline extension or Phase1.75 closure.

## Remaining release gates

1. Representative volume/shape and complete resource/latency qualification of this
   integrated adapter, within reviewed resources; the2GiB generated ceiling cannot
   certify16/21GiB production bounds.
2. Reviewed actual-cloud authentication/RLS/schema checks; generated MockTransport
   evidence alone does not certify a private Supabase deployment.
3. Production-volume streaming migration/audit and complete verification timing;
   this bounded generated migration deliberately refuses the production volume.
4. An exact exported release and one consolidated cutover/recovery approval with
   identities, numeric capacity/expiry, interruption/recovery and verification
   budgets. No old consumed authority or automatic retry may be reused.
5. Independent production rollover/freshness/lifecycle acceptance remains separate
   and NOT PERFORMED here. I7 and Phase1.75 stay open.

## Retained development failures and scope limits

The first application crash test failed because a standalone child lacked the
application import path; this was corrected. The dashboard test exposed an actual
rowid/UNION incompatibility, corrected with an explicit stable sequence adapter.
Supervisor integration caught a fixture socket argument and aggregate-allocation
shape mismatch, both corrected. Tests were rerun after those changes, not marked
passing retroactively.

The first unknown-sidecar test collided with an already-existing generated WAL.
Its error teardown removed that generated sidecar. This violated the test boundary;
no production data or service was touched. The failed case remains a failure.
The corrected fixture uses never-opened file paths and asserts guards reject
unknown sidecars/symlinks before any SQLite open. It neither replaces nor removes
SQLite-managed files. Final successor b39c837 passed its own exact CI41726968944, including the
corrected test;138f455 evidence was not substituted for that result.

Unknown-sidecar/symlink rejection is now tested before any SQLite open; the owner predicate is implemented
but a changed-owner filesystem fault has not been independently injected here.
Actual host ENOSPC, physical disk faults, adversarial same-user path races and
power loss are not certified by generated quotas, process exits or read-only
handle errors. Full production-volume migration has not been attempted. Legacy
file retirement/decommission remains outside this generated implementation; the
retained legacy file is still included in the unapproved migration budget.

## Final exact-commit results

Frozen source b39c83755608b8065a0099c7d10b3ca8ad0f5800, CI41726968944:

- Linux backend311tests, OK,6skips. All6are privilege-dependent cases run again
  in the explicit root step:4raw descriptor/profile tests and2application
  retirement/drain/process-crash tests. None remains an unexecuted Linux skip.
- Linux root raw protocol17tests, OK,0skips; Linux root application24tests, OK,
  0skips. This includes actual generated-file retirement after fresh archive
  readback, unmanaged/concurrent readers and real process-exit recovery.
- Deployment/maintenance112tests, OK,0skips. Linux process-group interruption,
  child reaping and full verification-controller tests ran. Dashboard Node
  contract and installed-strace tiny harness case ran; no tracing package installed.
- Complete job success is evidenced by the exact head SHA and completed logs.
  Logs and sanitized JSON are retained in local evidence/ab72-compatibility-b39c837.

The retained4000row component profile also passed on this source:18.317s,
0errors, all4000archived,13real feature/baseline cycles, maximum save23.833ms,
heartbeat227.886ms, bounded query68.696ms and feature12.485ms; rotation6.907ms,
retirement115.617ms; peak generated workspace9688405bytes and RSS43483136bytes.
That profile exercises the existing protocol/component path, not a representative
throughput qualification of the new full ApplicationStore/Supabase adapter. Its
simulated zero input age is not live freshness acceptance. It neither clears the
production capacity gate nor replaces old failed retention policies/results.

No code changes remain after this frozen source. This document/roadmap update
records evidence only. New production release/export CI remains a separate gate.
