# AB72 exported ApplicationStore checkpoint — November 3, 2026

Subsequent readiness preparation: [AB72_PRODUCTION_READINESS_2026-11-03.md](AB72_PRODUCTION_READINESS_2026-11-03.md).
This frozen61e0008 acceptance remains intact; readiness successor835e507 has its
own CI41745773184, still in progress at the recorded single check, not inherited
from this baseline. Production readiness remains NOTPROVEN.

Frozen successor: `61e0008c59696168bdaa043fce6b88e5b22f6d19`.
**Result: PASS_SCALED_INTEGRATED for generated exported compatibility.**
[Exact CI41738983997 PASS](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41738983997).
Production migration/readiness remains NOT PROVEN; no production approval follows.
This report supplements the earlier compatibility report and is the restart index
for the resumed worker/export work. Production remains STOP.

## Scope and checkpoints

| Checkpoint | Final disposition | Evidence / limit |
|---|---|---|
|Legacy IDs, direct/embedded references, cursors and exact provenance|PASS generated|Actual legacy schema, sparse IDs, original snapshot/prediction IDs, outcome-observation FKs, stable composite tick keys, existing cursors; quiescent committed legacy WAL rows also tested. Unknown references/schema stop. Production-volume audit remains NOT PROVEN.|
|Independent worker access and actual application routing|PASS generated exact-export|Explicit lifecycle/feature/history workers never acquire collector lock or raw/retirement capability. Runtime feature factory uses restricted handles. Reads exclude raw until core ack; transactions pin bindings until commit; protected copied records remain checksum-verified inputs after retirement.|
|Cloud request/processing deadline and archive/checkpoint compatibility|PASS generated wire tests|Original deadline covers requests, all attempts/backoff/body/JSON/checksum processing. Late child killed/reaped. Conditional immutable inserts and ambiguous response reconciliation; exact NUMERIC text and original probability provenance preserved. Actual Supabase RLS/authentication remains NOT PROVEN.|
|Failure/recovery matrix|PASS generated scope|Crash/restart points, partial migration/rotation, duplicate/conflicting identity, corruption/outage, open readers, protected references, SQLiteFULL/quota and read-only/I/O failures, forward-only guards. Hardware power loss and actual host ENOSPC remain NOT PROVEN.|
|Exact exported candidate and integrated workload|PASS_SCALED_INTEGRATED|Exporter validates exact SHA/Git blobs/SHA256/modes/file set and rejects sensitive paths/symlinks before blob reads. Full suites run on exported bytes; identical manifest rebuilt after test success before4000-record integrated qualification.|
|Production migration and acceptance|NOT PROVEN / NOT EXECUTION READY|No live path enablement/controller/approved budgets, production-scale capacity, real private-cloud permission or verification completion evidence. No approval requested.|

The design remains persistent structured core plus two72h raw generations and
existing Supabase structured history/private archives. There is one aggregate
budget for legacy/core/A/B/allWAL; no per-file full-cap allowance or free-page
physical credit. All production routing and retirement stay default-disabled.
The implementation still refuses production paths: this checkpoint is not an
operator migration route or permission to bypass those path guards.

## Implemented corrections since b39c837

- Confirmed the interrupted exporter/cloud/separate-worker/ack-read tests. Full
  local source337tests and controls112tests passed at the recorded stages; final
  source has additional focused/CI cases. Platform skips are recorded below.
- `ApplicationWorker` supports existing separate lifecycle/feature/history roles
  without collector ownership. Collector methods reject those roles before even
  structured market metadata can be written. Real runtime feature dispatch now
  uses this restricted factory and drains handles before owner release.
- Application raw views join committed core intents only. An OS/process failure
  after raw commit before acknowledgement cannot publish that row through a
  feature/history/lifecycle reader. Core-ack recovery later exposes it exactly once.
- Transactions retain pinned generation bindings until commit, then refresh.
  Queries after retirement route copied, checksum-verified protected inputs from
  core. A corrupt copy raises an unavailable/error state, never a default value.
- Checksum and JSON response processing moved inside the killable request child.
  HTTPX inactivity timeout is not presented as a hard deadline. The original
  monotonic deadline spans attempts/read/backoff/processing, with no1ms extension
  after expiry. Whole qualification includes export/fixture preparation under the
  unchanged170s work/180s process-family envelope.
- Structured ambiguous writes reconcile exact remote identity before ack. Immutable
  inserts ignore duplicate keys and compare authenticated readback, preventing a
  concurrent conflicting insert from being overwritten. Mutable market/outcome/
  checkpoint behavior still requires actual-cloud concurrency/RLS review.
- Structured NUMERIC values are encoded from original exact decimal text; raw
  JSON/provenance is retained. Existing double-precision prediction fields keep
  their native schema, with original local values retained in extra_json.source_exact.
- The exact source exporter reads selected tracked blobs, not local edits/data;
  it creates no checkout/worktree/branch. Sensitive DB/env/key/credential paths,
  symlinks, altered modes/files/bytes and forged manifest-vs-Git identity fail.
  Source export is not a database copy or production operator bundle.

PostgREST filter values use quoted JSON-compatible strings per its official
[URL grammar](https://docs.postgrest.org/en/v16/references/api/url_grammar.html).
CI directory contexts are scoped to steps per GitHub's
[context availability reference](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts).

## Qualification and retained intermediate results

No unchanged performance trial, batch/checkpoint matrix or production VM trial
was run. Each successor addresses a specific observed or missing proof:

1. `880181f`, CI41735427263 FAIL before execution, jobs=[]: unsupported runner
   context in job defaults. No suite or qualification ran. Corrected to supported
   step context and added a regression test. This is not a timing failure/pass.
2. `f87fc4e`, CI41736469183 PASS: exported337backend/17rootprotocol/32rootapp/
   112control tests; integrated4000new commits/4002archives/0errors,46.882s,
   save188.317ms/heartbeat305.091ms. Whole-disk counter omitted descendant
   unlinked TEMP. Retain that functional result with its resource-evidence limit.
3. `cc44c3f`, CI41737929171 PASS: exported339backend/17rootprotocol/32rootapp/
   112controls; complete process-family TEMP accounting. Integrated4000new commits,
   4002archives,0pending,0errors,54.500s; maxsave28.435ms/heartbeat155.619ms;
   feature161.259ms/history44.103ms;52215808B RSS/21969852B sampled workspace.
   Result review found only10of20cycles published: exact-second market lookup
   used lexical comparisons on mixed fractional/nonfractional timestamps. That
   CI is insufficient final rollover acceptance despite its passing old harness.
4. Final61e0008 changes market time comparisons to existing julianday semantics,
   with no price-query/version/index/cadence change. A tiny exact-second fixture
   reproduces the former expired identity; the corrected identity/subscription
   lookup and186s scheduling/health tests pass. The qualification now requires
   publication in BOTH simulated markets and the final correct current identity.
   Previous measurements are not relabeled as final acceptance.

The separate original component4000-row profile is still a regression test, but
its numbers are not substituted for the integrated ApplicationStore workload.
The latter executes real collector saves, LiveState publication, one serial
feature/baseline/ensemble/chart worker, an independently spawned LifecycleWorker,
actual SupabaseHTTP wire format via private file-backed MockTransport, verified
archives and Linux-root retirement. No venue or real Supabase traffic occurs.

Limits:512MiB Linux AS per process (inherited by children);170s work/180s whole
operation including exact export rebuild and fixture preparation;2GiB whole
workspace including exported code, legacy/core/A/B/WAL/SHM, generated objects,
TEMP and report allowance. Linux accounting includes unique unlinked inodes over
bounded process-family FDs. Observed peak is sampled, not a future arbitrary-input
storage bound. No resource/production guard or deadline was increased.

## Capacity and one gated migration procedure

The normal16GiB / migration21GiB values remain UNAPPROVED proposals. Basis is
recorded November3metadata and a20KiB/s planning rate, not newly measured live
arrival/burst or production core growth. No production measurement was repeated.

| Proposed budget component | Bytes / rule |
|---|---:|
|Normal aggregate ceiling|17179869184 (16GiB)|
|Temporary migration aggregate ceiling|22548578304 (21GiB)|
|Retained legacy main+WAL, recorded|5369078784|
|Core budget cap (not measured new-core demand)|5368709120|
|144h raw+index planning estimate|10616832000|
|Aggregate WAL allowance, empirical|136314880|
|Recovery-growth allowance, empirical|136314880|
|Separate archive/TEMP filesystem allowance, unqualified|2147483648|
|Filesystem-free floor at projected peak|10737418240 (10GiB)|
|Recorded free / projected free under proposal|49807454208 /30480471040|
|Temporary review / expiry|cutover+72h / cutover+96h; no automatic extension|

The filesystem arithmetic fits the recorded sample. Actual-rate/index/core-ledger/
WAL/TEMP/recovery bounds and present physical headroom are NOT PROVEN. Legacy
remains fully counted until separately verified decommission. Two full/unretirable
slots or a failed guard mean STOP, no third slot, overwrite or unlimited outage.

This is ONE procedure for eventual consolidated review, not executable authority:

1. Pin the integrated release/export/CI and all helper hashes. Freeze exact
   source/schema/database/archive identities. Fresh authority must bind the
   complete AB scope; the old rollover-only reserve amendment and consumed or
   expired authority cannot be reused. Reject flags/partial settings by default.
2. Fresh bounded read-only preflight binds physical allocation/free space and
   source database identity. Keep collection stopped. Establish which other
   writers/readers exist and require the reviewed quiescent stop/drain procedure.
   Check aggregate limits and filesystem working/free-space budgets separately.
3. Complete applicable legacy integrity and FK checks in a bounded child with
   phase progress/reaping. Bind fresh evidence to the exact unchanged DB+WAL,
   schema, release and operation. Do not use immutable mode to ignore a live WAL.
   An incomplete/timed-out check is STOP, not reusable proof.
4. Run the reviewed streaming structured/ID/reference import into core, retaining
   legacy raw read-only. Preserve all IDs/cursors/protected evidence; audit every
   reference and exact row identity. No raw clone, A->B transfer or DB backup.
   Current generated importer deliberately refuses production paths/volume;
   production-sized import/verification is still a missing release prerequisite.
5. Verify complete core/generation integrity, exact schema/identity mapping and
   original cloud evidence dependencies. Bind each existing service/connection to
   the new layout. A reviewed operator control must prevent the old binary from
   writing the retained legacy file; new-core write guards alone do not enforce
   filesystem protection of the old monolith. This cutover control is unqualified.
6. Only under consolidated approval apply the reviewed aggregate16/21GiB ceilings,
   expiry and filesystem-floor controls, then start the sole collector/current A,
   one serial feature worker and existing separate lifecycle/ensemble roles.
   Enablement is currently unavailable on production paths, not an implicit bypass.
7. Keep raw generation retirement OFF until the approved route freshly proves
   strict72h newest-receipt age, complete exact authenticated archive coverage,
   protected evidence in core, unchanged identities and drained reader/FD proof.
   Legacy decommission needs its own complete coverage/reference/handle proof;
   current code does not implement legacy-file retirement. Do not assume a16GiB
   steady-state cap is reached while the old file remains.
8. Run one bounded functional smoke: API/current market/source freshness,
   advancing persistence, feature guards, dashboard/SSE and service stability.
   Restore temporary helpers, revoke remaining authority, report actual elapsed
   interruption/remaining allocation, and yield. No background soak/retry.

Verification/interruption budget remains a blocking measured fact, not an invented
number. The existing maintenance limits are verify1800s,
other work600s, separate reap reserve10s, recovery180s, absolute interruption2590s. They are preserved as
constraints, not renewed authority for AB. Prior production verification timed out
at1790.105s with its exact internal check unknown. No evidence establishes that
complete legacy+new-layout verification/import/smoke fits those limits. Allocating
more time or excluding phases would require explicit consolidated review; neither
has been implemented. The old cap-review deadline remains expired.

Recovery rule: before new durable AB writes, code rollback is allowed only with
proved original compatibility. After any new durable writes, freeze writes,
preserve legacy/core/registry/all generations and recover forward using the
reviewed adapter. Never restore database contents or silently resume the old
monolithic writer. Partial migration never publishes a complete marker. Missing
capacity/archive/reference/identity/platform evidence keeps collection stopped.

## Approval and remaining gates

No production approval is requested: the procedure is NOT EXECUTION READY.
Missing facts/controls are precise: production-volume streaming import and full
verification completion budget; qualified actual core/rate/burst/WAL/TEMP/recovery
capacity; actual private Supabase auth/RLS/schema/concurrency behavior; a guarded
production path and exact exported operator cutover/recovery route, including old
legacy write prevention and eventual legacy decommission. The current generated
qualification cannot supply these production facts within its2GiB fixture limit.

Production unchanged. Retention/paidAI and production routing/retirement stay OFF;
recorded collection/capacity STOP, cleanup0, no restart/deployment/deletion/DB copy/
manualWAL/infrastructure change. Previous development failures and the earlier
sidecar test-boundary mistake remain recorded in the preceding report. Physical
power loss/real host ENOSPC/changed-owner attacks are not certified. Production
multi-cycle/real-boundary/sustained lifecycle acceptance remains NOT PERFORMED.
I7 and Phase1.75 stay OPEN; no Phase2 work.

## Final exact exported evidence

Both CI jobs passed for61e0008c59696168bdaa043fce6b88e5b22f6d19. The first job
exported the exact tracked source and ran all applicable suites there; the second
rebuilt that exact commit and compared its manifest byte-for-byte before the
integrated workload. Candidate integrity was verified again after each stage.
No local uncommitted source, environment files, databases or credentials entered
that export.

- Backend340tests, OK,6privilege skips. Those4raw and2application cases all ran
  in the explicit Linux-root steps:17protocol tests and33application tests,
  both OK with0skips. Installed-strace and Node contract cases ran. No unexecuted
  Linux/platform skip is counted as a pass. The new descendant-TEMP test ran.
- Deployment/maintenance112tests, OK,0skips, against the exported tree.
- Integrated qualification: actual ApplicationStore path, all4000new rows committed,
  0pending,4002verified/archived rows (4000new+2prior legacy backlog rows),0errors.
  The earlier legacy cursor's41st observation remains retained/protected; this
  fixture does not certify complete original legacy archive/decommission coverage.
-20completed feature/baseline/ensemble/history cycles;20published,10before and
  10after the simulated boundary,0rejected in this successful workload. Separate
  stale/expired/wrong-market tests still exercise rejection. Final RAM current
  market identity is after/after. No expired prior identity is accepted at the
  exact-second test boundary.
- Two actual separate lifecycle cycles; the first truthfully reported its stream
  backlog not caught-up while collection advanced. The final cycle caught up both
  datasets. Retention remained disabled in both; no row-cleanup operation ran.
- Sealed A was retired only after fresh archive/reference/handle proof. B and core
  retained. Original outcome-observation reference90 and protected snapshot inputs
  survived; checksum-verified copied history remains usable after file retirement.

| Integrated generated measurement | Observed |
|---|---:|
|Maximum collector save through return|240.662ms|
|Maximum heartbeat gap|303.473ms|
|Maximum real feature/baseline/ensemble/history job|102.500ms|
|Maximum actual history/chart query|23.384ms|
|Maximum published snapshot age, simulated clock|0.050s|
|Maximum sampled input age, simulated clock|0.010s|
|Preparation included in original clock|0.910s|
|Whole operation including preparation|40.126s|
|End-to-end new-record throughput, all work included|99.69rows/s|
|Rotation / retirement|7.554ms /122.489ms|
|Sampled whole workspace, report allowance included|22375667bytes|
|Parent RSS,512MiB AS inherited by children|53075968bytes|

The counters include exported source/manifest, generated legacy/core/A/B/all WAL/
SHM, private mock cloud objects and ordinary/unlinked TEMP over the process family.
No trace payload log or source DB copy is involved. No claim of exact writer-lock
occupancy is made from save return time. This is not a production retention
split-gate qualification and does not relabel prior500ms-policy failures.

Observed pre-retirement main allocations: legacy159744B,core2031616B,A2318336B,
B2318336B. Sampled WAL peaks: core4511432B,A4144752B,B4140632B,legacy0B in this
profile. The separate focused quiescent-WAL test covers nonempty committed legacy
WAL. These small values do not qualify a production WAL ceiling or core growth.

Runtime SQLite3.45.1/source-id
`2024-01-30 16:01:20 e876e51a0ed5c5b3126f52e532044363a014bc594cfefa87ffb5b82257ccalt1`.
This is hosted-Linux qualification, not a measurement of the stopped production VM.
Simulated age/boundary/throughput is not real-feed freshness, live API latency or
Supabase network throughput. No production multi-cycle,real-boundary or sustained
72h/144h acceptance was performed.

Export manifest:207source files,2337764bytes; SHA256
`c06c92d1313aa30f2c166fcdc2107782a198a7b41c389cf22d97908bcbf35282`.

Private sanitized evidence (logs, manifests, JSON only; no DB files):
`/Users/jake/Documents/ChatGPT/TradebotAnalytics/evidence/phase175-baseline/lifecycle-implementation-20261031/ab72-exported-61e0008/`.

The final evidence-only documentation commit does not replace this frozen source
candidate. It is explicitly not a production release. No further unchanged test
or qualification run is required to record these completed results.
