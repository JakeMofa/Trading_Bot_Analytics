# 72-hour local retention and A/B raw-storage policy

Decision recorded November 3, 2026 from the user's request. This is the selected
replacement storage design and retention target, not a deployed implementation.
INTELLIGENCE_REBUILD_PLAN.md remains the authoritative roadmap. Historical48h
reports remain unchanged. No production setting, service, schema or data changed.

## Selected layout and retention

- Retain at least72hours of successfully collected raw data locally, measured by
  original local receipt time in UTC. This supersedes the initial48hour target
  for the future implementation; it does not backfill missing collection.
- Use two rotating raw generations A/B on the existing VM, plus a persistent
  structured core. A/B are raw-storage roles, not two interchangeable copies of
  the entire application database. Markets, predictions, outcomes, archive
  manifests and required protected evidence remain durable across rotations.
- A raw generation accepts new events for72hours from activation. Route events
  by receipt time; preserve source timestamps, exact decimals and provenance.
  Switch new writes to the other prepared generation; do not copy the old DB.
- Readers must span both generations when their lookback crosses the boundary.
  Source-time queries need matching indexes; RAM state is not complete durable
  history. Preserve the tested independent discovery/feature scheduling fixes.
- Do not retire a sealed generation until its newest receipt is strictly older
  than72hours, its applicable Supabase archives are freshly verified, all reader
  handles are drained and every protected reference/evidence dependency is safe.
  Thus two72hour generations require capacity for approximately144hours of raw
  data, not merely72. Boundary delay, late writes and blocked retirement add to
  the demand. Exact72hour instants do not justify early deletion.
- A/B are generation roles with unique generation IDs. Never overwrite a retained
  or unverified file. If the next role is not safely reusable, preserve data,
  report the blocker and stop ingestion before exhausting its explicit budget.
  Two slots cannot guarantee continuous collection through an arbitrary outage.
- Archive incrementally in the existing lifecycle service, initially hourly;
  finish and verify sealed generations without waiting another72hours to upload.
  Retain Supabase PostgreSQL for structured history and private Supabase Storage
  for raw archives. Do not introduce separate AWS S3 infrastructure.

## Growth evidence: extrapolations, not a measured daily average

Source: existing capacity-profile.jsonl / CAPACITY_BRIDGE_RESULT.md, five samples
across80.154464s on October26. Main+WAL physical growth9402.65B/s; estimated logical
page growth12110B/s; prior conservative planning input20KiB/s. Whole-database
rates include other tables and cannot establish raw-generation/index/core rates.

| Basis | GiB/day |72hours GiB|144hours GiB|
|---|---:|---:|---:|
|Observed short-window physical rate|0.757|2.270|4.540|
|Estimated short-window logical rate|0.974|2.923|5.847|
|Prior conservative planning input20KiB/s|1.648|4.944|9.888|

Do not label these as a current24hour average, a burst bound, compressed archive
size or measured segmented capacity. A complete active-collection day has not
been established by this assessment. Exclude stopped-collection periods from
future ingestion-rate averages; report their missing coverage separately.

## Aggregate storage-guard policy

The user permits revising the guard for the selected72h A/B design. This replaces
"never consider a higher ceiling" as a planning constraint, but supplies no
specific production value and authorizes no immediate guard/restart operation.
The expired5120MiB bridge is not automatically extended or promoted permanent.

- Count physical allocated lengths of legacy DB retained during migration, core,
  all active/sealed/staged raw DBs and every associated WAL. Report SHM and archive/
  TEMP files separately in the filesystem working budget. Never apply a full
  allowance independently to A and B or hide retained legacy storage.
- Size steady state as core+indexes +144h raw/index generation demand + bounded
  boundary/blocked-retirement allowance + aggregate peak WAL + recovery reserve.
  For migration, add every retained legacy/staging allocation and measured peak
  transition working demand; do not assume old data is removed or compacted.
- Use the larger of the20KiB/s historical planning input and measured active-load
  raw/index rate for preliminary generation budgeting. Keep its extrapolated
  nature explicit. Derive core, WAL, burst/retirement and recovery terms from
  bounded measurements/generated qualification, not an unexplained new number.
- Round the resulting aggregate ceiling upward to the next whole GiB only after
  all terms are specified. Preserve at least10GiB actual filesystem-free reserve
  under projected peak use, including non-DB temporary/archive files. If it
  cannot fit, report the quantified deficit rather than deploying optimistically.
- A steady-state reserve must support the evidenced WAL/rotation/recovery work
  and at least512MiB physical DB+WAL headroom; add any larger measured requirement.
  Reusable internal pages are useful capacity but not physical-headroom credit.
- Record one exact proposed normal ceiling and, if needed, a separate temporary
  migration ceiling with numeric expiry/review and transition criteria. Obtain
  approval for that concrete production procedure before changing runtime.
  No automatic increase/extension. Budget alerts warn early; hard guards remain.

At the20KiB/s planning input, A/B raw growth alone is about9.89GiB before core,
new indexes, WAL and reserve. Therefore neither5GiB nor an unmeasured6GiB/8GiB
replacement is established sufficient. This is a budget calculation, not a claim
that the current database produces1.65GiB every day or that a final ceiling is set.

## Integrity, handoff and prediction requirements

- Existing observation IDs/reference assumptions require explicit adaptation.
  Preserve stable generation+identity provenance; never reinterpret local IDs.
  SQLite cannot enforce foreign keys across schemas. Generated tests must prove
  protected outcome observations and prediction evidence remain reconstructable.
- A/B handoff needs a recoverable registry: precisely one active write generation,
  crash-safe/idempotent transitions and duplicate detection. WAL transactions in
  different databases do not provide a global atomic commit; design recovery
  around that fact rather than assuming an atomic multi-file swap.
- Never copy/unlink active DB/WAL files as a shortcut. Retirement requires closed
  handles, verified archives and approved deletion controls. FULL durability and
  exact decimals remain mandatory. No VACUUM/manual WAL operation is introduced.
- Keep serial features and independent market discovery. Require functional
  equivalence on boundary queries, no lookahead, source/input ages<=30s and
  snapshot age<=30s in representative performance qualification. A/B alone is
  not a prediction speed fix; keep the prepared query/index work available.

## Implementation checkpoints and current production

1. Produce numeric steady/migration budgets and the exact proposed guard(s).
   Do not repeat the old5GiB feasibility STOP as the new decision: changed sizing
   is selected, while actual production changes remain gated on concrete values.
2. Build generated-only A/B/core prototype; test boundary reads, identities,
   references, full-slot/archive failure, restart/crash transitions and retirement.
3. Qualify read/write/rotation/archiving workload and total storage on bounded
   generated fixtures; existing resource limits and split-gate authorizations
   are not silently changed. Missing scale evidence is NOT PROVEN.
4. Present one tested exact-CI migration/release procedure with explicit budgets,
   code/data recovery, guard expiry and complete-verification requirements.
   No production migration or deletion is authorized by this policy document.
5. Restore collection only after safe transition; validate rollover, prediction
   freshness and verified72h retirement. No automatic monitoring/soak is started.
   Required sustained-lifecycle evidence remains outstanding before phase closure.

Current recorded production remainsd56b4a7; collector stopped at5120MiB guard,
retention/paidAI OFF, production cleanup0. Existing rollover candidate and verifier
fixes are preserved. I7/Phase1.75 stay OPEN. No runtime code changed by this milestone.

References: https://www.sqlite.org/wal.html ;
https://www.sqlite.org/lang_attach.html ;
https://www.sqlite.org/foreignkeys.html#limits_and_unsupported_features .
