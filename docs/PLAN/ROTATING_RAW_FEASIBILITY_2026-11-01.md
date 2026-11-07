# Rotating raw storage: checkpoint1 STOP and current-limits NO-GO

This is a capacity/dependency assessment, not migration authorization. Working
checkpointc4cea05 and application/maintenance release93161cf remain preserved.
Production deployment remains stopped. No new authoritative roadmap is created.

## Physical capacity and migration constraint

Bounded read-only metadata at2026-11-01T19:13:44.676898UTC:

| Item | Measured allocation |
|---|---:|
| Existing main DB |4637.539063MiB|
| Existing WAL |32.863342MiB|
| Aggregate |4670.402405MiB|
| Headroom below5120MiB ceiling |449.597595MiB|
| Shortfall against retained512MiB prerequisite |62.402405MiB|
| Freelist reusable space |0pages /0MiB|
| Page size /page count |4096 /1187257|
| Automatic vacuum |NONE(0)|

Even omitting the WAL entirely leaves482.460938MiB, below512MiB. Reusable pages
are not counted as physical headroom. Existing file size already exceeds the
4608MiB permitted allocation before adding any new core/segment/working space.
An additive migration preserving the existing DB therefore cannot satisfy the
existing reserve today, even if every additional component were zero bytes.
Forward-only routing does not erase the legacy allocation. Reusing legacy as core
also retains its raw pages; creating a separate core adds allocation. Retirement
of new segments cannot recover the legacy footprint. No allowed physical
reclamation/capacity-change operation is authorized. This is the checkpoint1
STOP condition: do not proceed to prototype/performance or a production workaround.

## Steady-state calculation: explicit unknowns

Let C=core tables+indexes including preserved protected evidence; H=one hour of
raw payload/row allocation; I=matching per-hour indexes; B=registry/file/boundary
allocation; W=aggregate WAL across all open core/segment connections; T=archive/
verification temporary working bytes; R=recovery requirements not already in
those allocations. Required footprint is C+49*(H+I)+B+W+T+R, plus the512MiB physical
reserve, all <=5120MiB. Approximately49hours accounts for the active partial hour
and the sealed segment straddling the strict48hour newest-receipt cutoff. Longer
retention from readers/protected references must be added, not hidden in49hours.

Core and per-index allocations are NOT MEASURED separately. Header metadata gives
only total pages. A dbstat allocation walk would visit the existing database's
pages, not constitute a bounded header lookup; it was not run. No historical raw
payload scan, full copy, sampling payload download or new index measurement was
used. Accordingly C,H,I,B,Wpeak,T,R remain unqualified for the proposed design.
The observed32.86MiB single-WAL allocation is NOT a bound on50concurrent WALs.

Existing whole-database evidence, not raw-only segmented measurements:

| Historical input | Hourly equivalent |49hour extrapolation |
|---|---:|---:|
| Oct26 short-window physical growth9402.65B/s |32.2814MiB|1581.7904MiB|
| Same report approximate logical growth12110B/s |41.5764MiB|2037.2429MiB|
| Prior bridge assumption20KiB/s |70.3125MiB|3445.3125MiB|

Source: existing CAPACITY_BRIDGE_RESULT.md, five samples over80.154s. These are
whole-DB historical extrapolations, NOT segment payload/index rates, long-term
ceilings or full-scale capacity passes. Do not add unknown C/W/T/R and call the
remaining difference safe. Segment boundary/index overhead has not been measured.

During an archive outage, after ordinary48hour retention is reached, each blocked
retirement adds approximately another(H+I)+registry overhead per hour, plus core
and WAL/work growth. An open reader or unpreserved protected reference can have
the same effect. No measured segmented growth/burst bound exists, so no safe
outage duration is justified. No additional outage hours are proven affordable;
that is not a claim that actual tolerance is exactly zero.

Migration peak is at least existing4670.402405MiB + new C + staged segments +
new WAL/index/archive/recovery working space. If legacy remains core, replace new
C with its incremental allocation, not a subtraction of legacy bytes. Either way
the lower bound already fails the retained512MiB reserve. This is a migration
NO-GO independently of the unproven eventual steady state.

## Compatibility and reference inventory

All production table foreign-key catalogs were inspected (schema metadata only).
Exactly one direct raw-table FK was found:
`prediction_context_links.outcome_observation_id -> observations.id`.
No FK targeting stream_events was found. This does not cover application/JSON
references, whose current source paths are:

- features.calculate embeds metadata_observation_id/metadata_received_at and
  price.input_id/source/source_time in feature_snapshots.evidence_json and quality.
  Stream price identity uses source event_id; REST reference price uses local id.
- predictions.snapshot_id references feature_snapshots; forecast/model outputs
  inherit that snapshot's raw evidence rather than a direct observation FK.
- cases.match_cases obtains confirmed outcomes from metadata observations and
  emits outcome_observation_id/outcome_known_at; knowledge persists the FK above
  alongside prior_snapshot_id and prediction_id. Confirmed market results alone
  do not replace the exact observation proving availability at forecast time.
- cloud_memory preserves evidence_json in structured sync, archives observations
  using integer id/source_id, includes stream source_rowid in legacy archive
  envelopes and maintains id/time/key cursors. Retention/recovery proof modules
  depend on those manifests, exact IDs and global rowid/range semantics.

Stable identities must therefore include segment identity (or a separately
assigned global event ID) throughout metadata evidence, protected links, archive
manifests, cloud cursors, tie-breaking and recovery proofs. Restarted local integer
IDs cannot be substituted. SQLite FK enforcement cannot target an arbitrary
external segment; core-protected evidence preservation needs an explicit tested
representation. Pinning whole referenced hours indefinitely would invalidate the
bounded49hour capacity assumption. None of these adaptations is implemented here.

Single-file assumptions in the current application source inventory:
collector (schema/save/discovery), streaming (writers/hydration/worker), features
(price/metadata queries), ensemble (raw payload selection), cases/knowledge
(outcome joins), dashboard/API (history/chart/raw reads), audit/data_quality/
context_eval (evidence inspection), cloud_memory/cloud_lifecycle/run_cloud_sync/
run_cloud_lifecycle (archive/sync/checkpoints), retention/retention_trial/
retention_recovery/timestamp guards (global SQL scopes), system_monitoring
(single-path allocation) and operations (single collector lock/control/status).
The legacy operations backup helper exists but was not invoked. historical
backfill writes shared market/core tables via collector.connect. Raw-data
partitioning is not compatible with these paths merely by changing a filename.

Snapshot/model/case joins currently execute through one SQLite connection.
Historical requests need segment pruning and indexed merge ordering preserving
source-time, receipt cutoff, late events and deterministic timestamp ties.
RAM calculations do not yet prove equivalent outputs across segments or eliminate
cold restart hydration cost. FULL durability alone does not establish rotation
atomicity, archived retirement safety or source freshness under storage pressure.

## Decision and test disposition

CONTINUOUS COLLECTION: NOT PROVEN
PREDICTION CORRECTNESS: NOT PROVEN
PREDICTION PERFORMANCE: NOT PROVEN
STEADY-STATE CAPACITY: NOT PROVEN
ARCHIVE-OUTAGE CAPACITY: NOT PROVEN
REFERENCE SAFETY: NOT PROVEN
CRASH RECOVERY: NOT PROVEN
MIGRATION WITHIN CURRENT LIMITS: FAIL
OVERALL: NO-GO under current limits

Checkpoints2/3 NOT RUN because checkpoint1's migration capacity condition failed.
No generated prototype, Linux workload, recovery window, credentials or upload
was used. This is not evidence that segmented steady state is impossible; it is
not proven, and additive migration cannot meet today's unchanged reserve.

NEXT ACTION: retain deployment STOP. A separately reviewed change to the migration
constraints is required before this could become an executable migration. No new
storage architecture or workaround is authorized by this assessment. Do not repeat
unchanged trials or spend another cycle refining capacity claims from unknowns.

Evidence: existing capacity report; bounded header/FK metadata and static source
inventory, saved outside Git under lifecycle-implementation-20261031/
rotating-raw-feasibility-20261101. Mathematical and metadata consistency checks PASS;
no runtime code changed. Retention/paidAI OFF, data/ceiling/deadline unchanged;
I7/Phase1.75 OPEN, no Phase2. The temporary cap deadline is not extended.
