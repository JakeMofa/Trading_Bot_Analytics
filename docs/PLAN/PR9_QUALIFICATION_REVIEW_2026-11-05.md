# PR9 six-part qualification and cutover review — November 5

Production remains held. This is qualification/release preparation, not deployment,
retirement enablement, a guard change or Phase1.75 completion. Redis is deferred:
evaluate it later against measured current-price/history bottlenecks; no Redis
service, dependency, cache or writer coordinator is introduced here.

## Baseline and scope

Frozen f1729071e054e184504c3909f062a4a170cfe3a0,
[exactCI42005134684 PASS](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/42005134684),
is confirmed fresh-B mode:4000 committed/4000archived,0pending/errors,20publications;
max save120.775ms,heartbeat305.908ms,feature95.297ms,history25.666ms;
22,285,660B sampled workspace,49.653s. It covers a simulated boundary and one switch,
not the repeated live joint qualification below. No earlier full-import result is
substituted. Existing cloud byte/throughput probes are reused for their exact scope.

Current candidate includes fail-closed validation, full acknowledgement receipts,
sealed-handoff priority and a joint real local HTTP/SSE/collector/prediction/lifecycle
fixture. Exact source/export/Linux CI is required; completion results will be added
without claiming skipped Mac descriptor cases passed. Local376 backend tests passed
(17 Mac/platform skips),120controls passed(3 skips), followed by focused regressions.

## Six-part evidence and remaining gates

| Requirement | Current implementation/evidence | Qualification disposition |
|---|---|---|
|1. Schema/data correctness|Layout2, SQLite user_version0, known feature versions1/2; raw columns/PK/UUID validation; bounded core quick/FK/logical checks; exact decimal/timestamp/JSON/provenance and protected-reference checks; six fault regressions|Local PASS at generated scale; exact successor Linux required. Full unrelated legacy integrity/archive remains held|
|2. Complete repeated handoff|Joint fresh B0→A1→B2→A3 includes requested A→B→A. Actual collector save/discovery functions, buffer scheduler, serial feature loop, real loopback FastAPI/SSE, history and separate real lifecycle CLI-builder/wire adapter; active generation emitted in SSE|New Linux root joint fixture required; synthetic feed transport and simulated clock, not live venue/cadence proof|
|3. Every acknowledged write/recovery|Full-column receipt SHA in same core transaction as acknowledgement; exact recovery audit of both owned raw files; read/archive/retirement proof; existing process crash matrix plus reused-slot process exits at planned/file-created/published boundaries; reader leases + authenticated archive readback before removal|Local corruption/ownership regressions PASS; root crash/reuse/joint proof pending CI. Physical power loss NOT PROVEN|
|4. Concurrent delays|Same4000-event exported qualification plus joint local HTTP/SSE during archive/rotation; save, heartbeat, raw ack intervals, API/SSE/current-price/feature/history timing; explicit deadlines and source-size/clock limitations|Baseline above retained. New maxima/artifacts must pass before review ready. No invented baseline for previously unmeasured API/SSE/price lookup|
|5. Operating limits|Recovery-only8GiB proposal,2GiB aggregate new layout,512MiB core,64MiB per-slot admission stop,2MiB rotation trigger,512MiB recovery reserve,10GiB filesystem floor; initial retirementOFF|Numeric recovery proposal UNAPPLIED; permanent continuous ceiling/runway remains NOT PROVEN. Core/receipt growth must be measured and expiry/horizon selected|
|6. Full review/CI/procedure|Existing working/deployment branches, draft PR9, exact export/byte verification, full backend/control/root tests; concrete STOP procedure below|No production-ready claim until exact tests and operating/verification/control prerequisites pass. Existing narrow manual route/path holds still reject A/B production|

## Validation and recovery changes

- Structured/protected legacy rows are validated before activation: malformed or
  nonfinite decimal text, invalid/timezone-free timestamps, malformed/nonfinite JSON,
  missing references, market/metadata/price provenance conflicts and unsupported
  versions STOP. Exact strings/decimals are preserved, not normalized to floats.
- Core quick/FK checks and bounded logical/reference verification run on startup.
  Existing complete cores are checked before initializers can touch them. Protected
  copies compare against exact legacy point reads; required new evidence matches
  the acknowledgement hash. Verification uses the original migration deadline.
- Each raw acknowledgement stores SHA256 of all original columns, including receipt
  timestamp/payload TEXT, atomically with committed status in persistent core.
  Recovery verifies all acknowledged rows and raw counts/headers before new writes;
  raw read/archive paths check receipts. Derived stream source keys must match
  source time. Missing/changed rows or receipts hold activation/retirement and files.
- Layout2 is explicit. Prototype layout1 cores are NOT silently upgraded or reset:
  missing receipts/unsupported version hold the files. No production A/B core exists
  in the recorded runtime. New format-aware write guards also reject an older A/B
  adapter that knows only the previous writer flag. Forward recovery after new writes
  must use the qualified layout2 source; never fall back to a layout1/monolithic writer.
- Retiring generations require exact archive membership, current receipt proof,
  protected bodies, fresh authenticated readback, shared/exclusive process leases
  and complete Linux FD visibility. Unknown visibility preserves the raw file.

Fault regressions inject malformed/missing protected legacy, wrong source/schema/
feature/layout versions, core body tampering, invalid decimal/provenance, changed
new raw price/receipt/source key, deleted acknowledged row, wrong generation UUID,
corrupt receipt even with a verified archive, and old-adapter write attempts. Existing
conflicting identity/cloud corruption/timeout/ambiguous write/quota/crash cases remain.
All are generated fixtures; no production DB copies or data mutations are used.

## Handoff-priority finding and correction

The first joint diagnostic exposed a safe STOP with both tiny slots retained.
Cold structured work and then catch-up against a moving active generation delayed
final sealed retirement. No storage or timing gate was raised. A newly observed
seal/drain token now defers structured sync for one cycle (it stays due) and scopes
that urgent archive cycle to sealed generations. Stable held readers do not starve
structured work indefinitely. Active backlog is explicitly reported not caught up;
`archive_scope=sealed_generations` is not a claim that active archives are complete.
After urgent retirement, normal incremental active archiving/structured work resumes.

The harness first accidentally shared a lifecycle connection across threads, then
hit the intentional single-thread hard-request guard. Both fixture errors were
corrected by spawning a separate lifecycle process owning its SQLite/cloud state.
Mac diagnostic then reached its expected “Linux descriptor proof unavailable” hold;
that is not a retirement PASS. Linux CI must prove the complete joint path.

Qualification review also found that older elapsed times covered closing handles
but not deleting the generated fixture tree. The new4000 profile includes normal
close, process/worker drain and actual generated-tree cleanup in its original180s
supervisor budget. Prior cleanup coverage is NOT retroactively claimed. It records
initial/final logical core pages, post-normal-close main size, receipt count and
bytes/event growth; logical pages never count as physical free-space credit.

## Measurement interpretation and gates

Joint fixture: one source producer at150ms wall cadence, synthetic real save/discovery
functions, a simulated15-minute boundary, actual1s rotation checks, and feature
wakeups representing elapsed logical15s. It does not prove REST15/30s venue request
cadence, WAN behavior or a real multi-day collection window. Network is loopback API
and SupabaseHTTP MockTransport only. Brief intentional feed pauses let the size
scheduler act; raw acknowledgement intervals include those pauses and are not
misreported as unplanned collector stalls. Use save and heartbeat maxima separately.

Thresholds remain: save/heartbeat<1s andzero errors; real HTTP/SSE observation<2s;
API history1s query budget; feature/publication and price-input freshness≤30s with
5s future tolerance. No separate historical price-query gate is invented; record
its measured max and compare future regressions. The previous profile had no API/
SSE metrics, so no ratio to a nonexistent baseline. Tracing/commit timing is not
writer-lock occupancy; no intrusive tracing is used here. Fixed170s work/180s total,
2GiB generated workspace and512MiB Linux process limits remain. The process family
is API/collector+threads, isolated lifecycle, and its one hard-request child.

## Recovery configuration versus continuous operation

Fresh-B starts with legacy5,369,184,256B (recorded main/WAL/SHM; remeasure), no full
raw import and retained legacy retirement held. Proposed guard arithmetic remains
legacy +2GiB new-layout quota +512MiB reserve =8,053,538,816B, rounded to8GiB. Charge
max(length,allocated blocks) for legacy/core/A/B/all sidecars/TEMP/unlinked files.
Core512MiB and each owned generation64MiB have independent admission stops. The
2MiB threshold is a rotation trigger, NOT an exact physical per-slot maximum;
SQLite/one bounded transaction may overshoot. Measure peak and overrun margin;
64MiB is a safety admission ceiling, not a promised byte-perfect kernel quota.
The filesystem floor is10GiB; there is no usable-page physical-space credit.

With initial retirementOFF, both new slots can fill and collection must STOP.
At assumed20KiB/s raw growth,2MiB represents102.4s/slot; at measured small-fixture
32.5KiB/s raw/index slope about63s. Two empty slots suggest126–205s before allowing
for core/WAL/bursts and actual seal overshoot. These are extrapolations, not guaranteed
runway or real source rates. The joint saturation fixture may grow WAL faster.
No automatic restart/threshold/guard change is allowed to extend that window.

Continuous A/B needs a separate verified-new-generation retirement gate, measured
archive/readback/drain turnaround below replacement-buffer capacity, worst outage
and reader bounds, persistent core/receipt growth, supported restart audit duration
and a finite planning horizon/expiry. The receipt ledger and prediction/evidence
history persist after raw retirement; bounded raw files alone do not make core
bounded forever. Proposed8GiB is not permanent16/21GiB policy or a72h guarantee.
72h remains maximum ACTIVE age, or earlier size trigger, with immediate sealed
archive/verification/drain eligibility. Legacy retirement remains separately held.

## Concrete cutover procedure for review (STOP before execution)

1. Freeze exact source/export and passing Linux suites/artifacts; verify complete
   production schema/structured counts/selected-body bounds, source identity and
   fresh host disk/RAM. Bind release/CI/config/helpers/data/layout/UID/expiry and
   one-attempt authority. No old consumed or expired approval is reusable.
2. Review together the recovery-only8GiB/2GiB/512MiB/64MiB limits,24h proposed expiry,
   10GiB floor and verification scope: complete NEW core/B +exact selected legacy
   inputs/references and immutable legacy binding, leaving unrelated legacy full
   integrity/archive/retirement held. Existing complete-legacy policy must not be
   silently replaced. No old1790s full scan is retried unchanged.
3. Use only the existing manual workflow/controller. Its current app-only pins,
   baseline, collector-running prerequisite and generated-only path holds do not
   implement this operation. Adapt/test a narrow fresh-B route, preserving the
   absolute2590s interruption/180s recovery/10s reaping ceiling unless a separately
   reviewed change is justified. Full verification/import timing must fit; do not
   squeeze it past workflow deadlines or add a general bypass.
4. In the approved attempt stop old writers once; prove no writable FDs; preserve
   original permission metadata; fence root-owned nonwritable legacy under a
   root-owned sticky parent. Prove the service UID cannot write/chmod/replace it.
   New core/raw remain private service-owned. No root API or duplicate collector.
5. Prepare layout2 core from structured and exact selected evidence under the
   reviewed budget, verify quick/FK/schema/content/reference proofs and new raw
   identity, preserve legacy unchanged. Missing/unknown/budget overflow STOPs.
6. Deploy exact source and start the existing single API collector/lifecycle/ensemble
   services with fresh-b/8192MiB aggregate/2MiB trigger and retirementOFF/paidAIOFF/
   row-retentionOFF. Do not start a parallel shell collector. Use a bounded functional
   smoke for API/current market/source freshness/persistence/dashboard/SSE/stability.
7. Before any new acknowledgement, old-code/permission recovery requires proof of
   no new committed writes and compatibility. After any new acknowledgement, keep
   the legacy fence; freeze unsafe new writes and recover FORWARD from layout2 core/
   raw receipts/intents using qualified source. No DB contents are restored.
8. Restore temporary helper code and revoke authority. Report actual interruption,
   revision, feed/persistence evidence, full allocation/headroom and missing acceptance.
   No soak or automatic retry. Enable verified NEW generation retirement only via
   a separate recorded gate; legacy retirement awaits its full checks/approval.

There is intentionally no executable production dispatch command here: the existing
controller does not support this full scope yet. Supplying its old command with a
new SHA would fail its gates. The precise remaining release prerequisites are the
reviewed targeted verification policy, complete actual structured/selected scope,
continuous capacity/expiry evidence and tested manual/path/permission bindings.
The user can review this sequence, not approve a fabricated ready command.

All eight-area/48h→72h/replay/deferredRAG reconciliation remains in
PHASE175_RECONCILIATION_2026-11-05.md. No production mutation, cleanup, restart,
backup/copy/snapshot, VACUUM/manual WAL action, guard increase, cloud write,
infrastructure change, paid AI or Phase2 occurred. I7 freshness/rollover, actual
cloud recovery, operational visibility and sustained-operation acceptance remain
open until independent evidence satisfies them.
