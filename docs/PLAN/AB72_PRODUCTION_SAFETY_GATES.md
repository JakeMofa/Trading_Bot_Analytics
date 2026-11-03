# A/B72 production safety and test gates

User requested comprehensive tests, safeguards, holds and retry behavior on
November3,2026. These are implementation/qualification requirements linked from
the authoritative INTELLIGENCE_REBUILD_PLAN.md, not additional production authority.
Current source02e0143/CI41715155473 passed generated tests and scaled workload;
legacy/app/cloud compatibility and representative production capacity remain open.

## Default holds and honest status

- Production remains held at the recorded storage STOP. A/B routing and retirement
  must each have an explicit enablement gate, disabled by default until the reviewed
  release activates them. Runtime preflight rejects inconsistent partial settings.
- Prototype modules reject production paths,symlinks,unexpected owners and path
  escapes. Live adapters may access production only through their reviewed path
  allowlist and approval-bound operator procedure, never a prototype bypass.
- Unimplemented paths fail explicitly. No placeholder success,synthetic market
  data,default zero measurements or fabricated predictions may enter live outputs.
  Health reports missing/stale/blocked state with a reason. API responsiveness and
  systemd active are insufficient evidence of collection or prediction health.
- No phase enters deletion/retirement after an incomplete verification,identity
  mismatch,unknown reference,unavailable archive or insufficient capacity.

## Durable writes and handoff

- Exactlyonecollector owner andoneactive raw generation; reject concurrent owners
  and conflicting registry state. An individual connection belongs to its worker.
- Distinguish received,queued,raw-committed,core-acknowledged and published. A memory
  enqueue is not durable acknowledgement. Recovery reconciles exact intent/raw/core
  state before accepting new work. Pending storage has explicit bounds/backpressure.
- Global IDs and source deduplication remain stable across legacy/A/B/core. A replay
  with identical evidence is idempotent; an identical key with different contents
  is a conflict and stops that operation. Exact decimals/timestamps/provenance survive.
- Test every transition before/after core intent,raw commit,core acknowledgement,
  preparing-file creation,active publication,seal,archive confirmation andretirement.
  Recover forward after durable new writes; an old monolithic binary must never
  silently resume writes into an incompatible layout.
- Retain FULL durability. Process-kill tests are not physical power-loss proof.
  Explicitly report hardware/power-loss qualification limits; do not overstate them.

## Bounded retries: operation-specific, not a global retry loop

- Retry only classified transient failures on operations with proven idempotency.
  Maximum3total attempts per logical operation,backoff1s then2s with<=250ms jitter,
  always inside the existing operation/phase deadline. Do not reset budgets.
- Honor a server Retry-After only if it fits the remaining deadline; otherwise
  return deferred/blocked. Persistent failures trigger a visible hold/backoff
  state instead of repeated network requests or unbounded queue growth.
- Private archive GET retries may handle transient connection errors,429 and5xx.
  Authentication/authorization failures,checksum/count/boundary mismatch,changed
  object content and malformed data are STOP conditions,not blind retries.
- Archive uploads/upserts require deterministic identities and content comparison:
  never overwrite conflicting evidence,advance cursors early or publish a verified
  manifest before authenticated readback succeeds. An ambiguous response is first
  reconciled with remote state; it does not authorize a second distinct write.
- SQLite busy handling retains the existing collector5s timeout. Do not stack a
  new retry loop on it or extend acceptance limits. Retry only an explicitly
  rolled-back/idempotent operation within the original budget. Ambiguous/late
  commit requires identity/state reconciliation before replay; report committed
  rows accurately. Corruption,I/O errors and constraint failures fail closed.
- Production maintenance,workflow dispatch,migration,raw deletion andfile retirement
  do NOT inherit network retries. Preserve one-attempt authority and existing no-
  automatic-retry policy. A fresh operation needs its applicable reviewed controls.

## Archive, reference and capacity safeguards

- Archive outside writer transactions in bounded chunks. Preserve existing private
  Supabase download/checksum/size/count/identity verification and immutable evidence.
  MemoryArchive passing tests does not certify real authentication,API/schema/RLS.
- Before retirement prove strict72h newest-receipt age,sealed/nonactive state,
  complete exact archive coverage,fresh object readback,protected evidence in core,
  identity mapping and drained readers/FDs. Unknown visibility or new references
  block retirement. Never unlink active DB files or separately delete WAL/SHM.
- Count core,A,B,legacy/staged files andallWAL against ONE DB budget. Filesystem
  working files/free-space reserve are additional checks. No per-file full allowance,
  free-page physical credit,unmeasured burst guarantee or automatic cap extension.
- Proposed16GiB normal/21GiB migration remain unapproved proposals. Validate actual
  core ledger/evidence growth,indexes,WAL/TEMP peaks andarchive/reader blockage.
  Check both DB ceilings and filesystem free space before writes andcutover.
- Full slots or cloud outage preserve unverified data andexpose STOP before the
  bound is exceeded. Test that an unavailable nextslot never erases retained data.

## Required layered tests and evidence

| Layer | Required scenarios and expected result |
|---|---|
|Unit/safety|Exact decimals,timestamp ties/future events,receipt boundaries,deduplication andID conflicts; reject unsafe input without partial publication.|
|Real application integration|Actual collector,LiveState,feature/baseline,ensemble/history/lifecycle paths against generated legacy+A/B/core; equivalent inputs/results/provenance andtruthful degradation.|
|Legacy compatibility|Direct outcome-observation FK,embedded evidence IDs,archive cursor/source IDs,snapshot/prediction relationships; reversible identity audit andzero missing protected evidence.|
|Archive failure injection|Timeout,429,5xx,401/403,corrupt/truncated/wrong object,ambiguous upload,duplicate manifest; bounded retries only where safe,otherwise hold,no deletion/cursor advance.|
|Concurrency|Collector during archive/read/rotation,simultaneous readers,competing owner,pending intent andlate reference; no overlapping active owner,lost acknowledgement orunsafe retirement.|
|Crash/recovery|Real process exits at durable transition points; deterministic forward recovery,committed data preserved andno duplicate publication.|
|Storage/I/O|Full disk/quota,lowheadroom,WAL/TEMP pressure,permission failure,missing file,symlink andunknown sidecars; fail closed andreport recoverable state.|
|Operator controls|Partial stop/checkout,startup/verification timeout,child reaping,smoke failure,helper restoration androllback failure; bounded recovery andaccurate failed status.|
|Performance|Bounded generated workload at declared scale; collect save/heartbeat/query/feature age,throughput andallocation. Noerrors,<1s save/heartbeat and<=30s input/snapshot age; existing gates remain.|
|CI and release|Test actual exported release tree andexactSHA onLinux,including relevant platform cases; sourceCI alone cannot qualify a different release.|

Run applicable full backend anddeployment/maintenance suites once after relevant
changes,plus focused new failure-injection tests. Do not count skips as passes or
re-run unchanged suites without a reason. Record commands,platform,counts,skips,
sourceSHA,CI links andtest scale. No production rows/database copies are test fixtures.
Use new generated fixtures with legacy schema; real cloud mutation is not implicit
in integration tests. Read-only cloud checks must preserve credential privacy.

## Final cutover gate and reporting

One consolidated review must bind exact release/CI,helpers,source/schema/database
identities,numeric normal/migration ceilings+expiry,full-verification budget,
interruption/recovery controls andapproved operations. There is no production
permission from this document or passing prototype tests.

Before new writes,rollback may restore oldcode only if original data compatibility
is proven. After newdurablewrites,freeze writes,preserve registry/allgenerations and
recover forward with the reviewed adapter. Never describe code rollback as data
rollback. Keep collection stopped on unsafe recovery rather than auto-restarting.

Report each gate PASS/FAIL/NOTPROVEN with evidence. List unresolved compatibility,
scale,cloud andpower-loss gaps explicitly. Production andphase completion require
actual measured evidence; CI/scaled fixtures alone do not closeI7/Phase1.75.
No automatic background soak,repeatedCIpolling orunchangedproductiontrial.
