# Phase 1.75 requirement reconciliation — November 5, 2026

PR #9 is the **current integration milestone**, not the production release or
Phase1.75 completion. Working/deployment branches remain unchanged. This dated
reconciliation governs interpretation of older checked boxes; it preserves their
original evidence rather than rewriting historical failures or authorizations.

## Exact tested baseline and successor

[46f51e5f6501ee03e4021d725659aff2b53e84b5](https://github.com/JakeMofa/Trading_Bot_Analytics/commit/46f51e5f6501ee03e4021d725659aff2b53e84b5)
[CI41995105891 PASS](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41995105891)
was checked once on resumption. Exported Linux357 backend tests passed/10 privilege
skips; dedicated root raw18/application38/runtime8/cutover1 passed without skips.
All ten privilege cases ran in the root steps. Controls120 passed/zero skips.
Manifest revalidation passed after both suites and integrated qualification.

Exact exported ApplicationStore4000-event result:4000 committed,4002 archived
(includes2 legacy backlog),0 pending/errors;20 real feature/forecast/ensemble/history
cycles and20 publications,10 each simulated boundary market. Save max669.047ms,
heartbeat749.106ms, feature206.834ms, history24.237ms, simulated input age10ms and
publication age50ms. Sampled whole workspace22,162,054B, parent RSS54,063,104B,
whole elapsed73.465s. Retirement149.699ms, rotation7.581ms. Same2GiB/512MiB-process/
170s-work/180s-total gates; not venue cadence, sustained live load, hardware power
loss or representative production-scale proof. Process-family TEMP accounting
includes unlinked files; RSS is not simultaneous whole-family memory highwater.

Generated fence→recovery0.8166s before-ack and0.8581s after-ack; small core quick/FK
checks1.340/1.703ms. New operator runs as root in this generated permission test;
old UID is unprivileged. This does NOT approve production root execution or prove
its full verification/interruption budget. Legacy bytes and references survived.
Earlier6361660 CI41994499331 failed the initial UID fixture; it stays failed.

Successor importer work is pending its exact Linux CI. Default production routing,
retirement, import path/volume guards and paid-AI holds remain. No production or
live-cloud operation occurred during this milestone.

## Eight integration and operational areas

“satisfied” is scoped to the evidence stated. Every production acceptance still
open is stated separately; source tests cannot certify a deployment.

| Area | Disposition | Supporting evidence | Next required action |
|---|---|---|---|
|1. Application routing: collector, LiveState, feature/baseline, ensemble/history, dashboard|Satisfied **generated integration**; still open production|46f51e5 exact export/CI and4000-event actual ApplicationStore path; runtime tests select default-off API/lifecycle factories; cross-generation ack-filtered views|Qualify real paths/volume and approved release; smoke current-market feeds/history/predictions/dashboard/SSE|
|2. Legacy IDs, embedded evidence, prediction/outcome links, archive cursors and import|Satisfied small generated schemas; still open recorded full volume|b39c837/61e0008 compatibility,46f51e5 permission/forward recovery; successor structured-cardinality profile below|Complete raw-volume and embedded-reference distribution qualification under an explicitly supported fixture scope; preserve all decimals/timestamps/provenance|
|3. 72h-or-size rotation, sealed archive, protected inputs and retirement|Satisfied scaled Linux safeguards; still open production lifecycle|b44f310/d1ba17e scheduler;46f51e5 root tests A→B→A/fresh UUIDs/crashes/leases/draining/protected body checks;08ce0d9/ec5f396 live byte probes|Representative overlap/outage and reader limits, actual cloud manifest/checkpoint compatibility, separate retirement gate after cutover|
|4. Aggregate capacity, collection interference and throughput|Still open production|2MiB VM normal/outage sample and46f51e5 scaled metrics; ec5f396 two-object throughput; full-window rates explicitly extrapolated|Measure retained legacy+core/A/B+all WAL/SHM/TEMP/archive/recovery peaks, burst/sustained rates and blocked-slot runway; derive ceilings/expiry before approval|
|5. Complete verification, Supabase/cloud recovery and deadlines|Satisfied scoped request deadline/idempotency/byte verification; still open full recovery/budget|CompatibleCloud/SupabaseHTTP tests, live exact synthetic object readback; prior1790.105s production verify timeout and unknown active check retained|Qualify full quick/FK/reference/content verification and restore/replay from verified cloud evidence within one reviewed absolute budget; no unchanged30min scan|
|6. Manual release controls, identity/permission fence and forward recovery|Satisfied generated fence and existing-route control tests; still open A/B release|46f51e5 generated separate UID fence/crash recovery,120 controls; old manual route pins narrower scope|After importer/capacity/verification pass, adapt existing workflow/helper to full exact export, authorized service/path/UID plan and forward-only recovery after ack; test partial stops, reaping, smoke and rollback failures|
|7. I7 discovery/rollover, truthful health and fresh predictions|Satisfied source regressions/containment; still open independent live acceptance and speed|93161cf rollover application preserved;46f51e5 default-off integrated source tests slow186s feature boundary, source timestamp replay, wrong/expired market and old-result rejection; deployed d56b4a7 containment predates fix|Approved release plus bounded functional checks; independently evidence real market rollover and genuinely fresh inputs/results. Fast API or unavailable slow features is not freshness PASS|
|8. Operational visibility, outages/restarts and sustained operation|Satisfied existing scoped telemetry; still open sustained A/B acceptance|/health,/cloud/status,/system/status/dashboard fields, visible storage/full-slot/archive holds and recovery tests; historical Oct25 runtime evidence|Expose/test migration/active+sealed/backlog/reader/guard reasons and observed resource growth in live route; reviewed sustained multiple-cycle/boundary/outage/restart evidence. No automatic soak or repeated restarts|

## Original Phase 1.75 checklist and research obligations

| Requirement | Disposition | Evidence and next action |
|---|---|---|
|P1.75.1 cloud schema/RLS, P1.75.2 opt-in client/config|Satisfied original deployment; still open A/B runtime full write coverage|Historical schema/RLS inspection and deployed client; exact live probe proves lifecycle identity/project/private bucket and bytes only, not every new upsert/reconciliation path. Keep secrets server-side and new routing defaultOFF|
|P1.75.3 structured sync/dependency order/stable IDs/checkpoints|Satisfied existing implementation; still open actual-volume A/B cutover|Original backfill plus generated actual wire adapter and stable IDs; verify new structured/import/cursor equality before production|
|P1.75.4 deterministic gzip JSONL, P1.75.5 private upload/authenticated checksum/size/count/identity verification|Satisfied original path and exact synthetic probes|08ce0d9/ec5f396 bounded live objects; complete generation coverage/readback under real new runtime and sustained sizes still open|
|P1.75.6 sync/archive health/API/dashboard visibility|Satisfied original deployed fields; still open integrated live acceptance|Existing lifecycle status and new default-off active generation/holds; independently validate truthful reporting after approved cutover|
|P1.75.7 original structured backfill, P1.75.8 original raw archive backfill|Satisfied historical scopes, not blanket proof for present legacy|Old exact counts/manifests remain evidence. Audit later collected legacy history and every reference/cursor; do not infer full coverage from a checkpoint|
|P1.75.9 48-hour row-deletion retention and .9b lifecycle scheduling|Superseded **mechanism only** by selected A/B policy; safety obligations remain open for new layout|See mapping below. Keep old module/tests/old failures and disabled flags; do not run old deletion to enable migration|
|P1.75.10 new24-hour run/tuning; bounded storage, outage behavior and multiple cycles|Still open|No post-cutover sustained A/B evidence. Short generated fixtures, existing original-runtime samples and one-time cloud probes do not satisfy this. Any observation session requires its own reviewed scope; no background soak is authorized|
|P1.75.11 historical raw replay/research/model validation tooling|Still open; **not superseded**|archive_reads.py plus retention_recovery.py prove bounded private readback/exact reconstruction primitives, not a user-facing resumable research replay tool. Implement generation-aware bounded selection, checksum/provenance, deterministic event-time ordering, missing coverage and no-lookahead replay tests against recorded schemas|
|Knowledge/RAG tables for trading/reference material|Still open, **deferred to when RAG begins**, not a cutover blocker and not “done”|Private knowledge bucket and existing local knowledge/FTS schema do not implement hosted document/chunk/embedding/retrieval/version/provenance tables. Define/apply their schema and access/retention tests in the authorized RAG phase; no paid AI or Phase2 introduced here|
|Postgres research queries, recoverable raw evidence, optional backup bucket|Satisfied original structured-query path; cloud recovery/replay still open|A bucket's existence is not a recovery drill. New database copies/snapshots/restore are forbidden; qualify recovery using exact verified archive evidence and preserve committed new writes|
|Live hot path independent of remote services|Satisfied source separation; still open finite-outage live acceptance|Lifecycle process owns cloud I/O. Two slots provide finite runway only; missing cloud proof must preserve sealed data and stop at the safe boundary. No promise of indefinite cloud-outage collection|

## Explicit replacement of older 48-hour row cleanup gates

The November3 selected layout and November4 clarification in
RETENTION_72H_AB_POLICY_2026-11-03.md supersede the old nominal48-hour local raw
expiry and the initial extra72-hour sealed hold. **72 hours is the maximum active
buffer age**, not a guaranteed minimum local-history window. Size may switch early.
Sealing starts archive completion/verification and reader drainage immediately;
retire as soon as all gates pass. B collects while A is verified. Core retains
required inputs, outcomes, prediction histories and protected evidence. The next
slot cannot be overwritten while unverified/held. No automatic legacy cleanup.

| Old requirement / board gates | Current disposition and replacement |
|---|---|
|R0–R4 old correctness/archive/candidate/baseline/qualification DB evidence|Satisfied historical scope preserved. Not fresh authority or proof for new source/layout. New exact export, schemas/identities/FULL and content/FK/reference checks remain mandatory|
|R5/R6 old three-trial row-delete performance/coexistence|Superseded as a prerequisite for **A/B file retirement**, which has different operations. Original502.686ms and other failures remain failures under their original policy. New representative collection/rotation/archive/retirement interference and workload completion remain open. Generated split500ms validated lock/1000ms total+commit policy remains limited to that old qualification harness; no production timer/gate silently changed|
|48-hour eligibility, row-range DELETE, last observation anchor / rowid assumptions|Superseded for new buffers by maximum72h-or-size switch, unique generation UUIDs and persistent global identity maps. Never reuse legacy IDs or lose evidence links. Legacy retained raw is untouched and any eventual decommission needs its own exact coverage/approval|
|R7 fresh recovery point, complete archive readback and full verification|Still open current-layout cloud recovery and complete quiescent verification. Superseded only the prohibited database-copy/snapshot method; no “backup bucket exists” substitution|
|R8 first production retention / R9 post-delete safety|Superseded row-delete step by separately approved first whole sealed-generation retirement, after exact coverage, protected core bodies and reader/FD drainage; post-retirement correctness/recovery still open|
|R10 live engine health, R11 restart/recovery, R12 deployment|Still open production A/B equivalents, plus I7 freshness/rollover. Small generated source passes do not close these|
|R13 continuous retention / R14 multiple lifecycle cycles|Superseded wording by automatic alternating A/B lifecycle; still open repeated live archive→verify→drain→retire cycles, slot reuse and bounded outage/recovery acceptance|
|R15 storage stability / R16 permanent guard / R17 phase completion|Still open. Derive physical normal overlap and blocked-outage/cutover budgets with finite horizon/expiry.16/21GiB proposals and expired5120MiB bridge are not permanent policy. No extension. Close phase only with all remaining safety/acceptance evidence|

All preservation constraints survive the mechanism change: FULL durability,
acknowledgement/reconciliation across non-atomic DB files, exact archive bodies and
identities, protected/late references, provenance, bounded classified cloud retries,
ambiguous-write reconciliation, no network inside writer transactions, no partial
verification success, one collector/serial feature worker, default holds and safe
STOPs. No backups/copies/snapshots, VACUUM, manual WAL action, deletion, production
migration/restart/guard increase, infrastructure, paid AI or Phase2 is authorized.

## Importer checkpoint, resource shortfall and release order

The successor adds an explicit **generated-only** MigrationBudget argument. Default
10000 rows/128MiB remains. The named known-count test allows60000 rows but keeps
128MiB audited bytes,2GiB aggregate workspace,512MiB Linux address space,170s work/
180s absolute supervisor including preparation/verification/cleanup. Preflight needs
2GiB plus10GiB filesystem floor and1.125GiB available RAM. No production env flag or
path bypass selects the larger row scope. SQL progress checks and pre-commit checks
share the original deadline. A stable legacy read transaction covers audit and copy;
changed main/WAL binding before commit blocks migration. Timed-out/unfenced import
cannot publish a complete marker; root/current permissions remain guarded.

Local generated fixture exactly1826 markets,18289 snapshots,27743 predictions,
20links/eight distinct protected outcomes; sparse raw IDs/decimal payloads/cursors
preserved.47907 total source rows/54,710,364 audited bytes. Exact per-table hashes,
core quick/FK and application history passed. Constructor8.624s, full verification
0.505s, restart audit0.489s;10.848s including preparation/cleanup. Sampled logical
peak161,078,240B/allocated161,271,808B, parent RSS54,427,648B. This is known structured
cardinality, NOT production raw cardinality, raw bytes, evidence fanout or page/I/O
layout. Initial run failed a Row-vs-tuple result assertion; corrected normalization
passed. Do not label the initial run a storage-corruption finding or a pass.
Successor source changes and Linux hard-envelope proof require exact CI.

**Full legacy-volume gate remains BLOCKED.** Recorded retained legacy is
5,369,085,952B main+WAL plus98,304B SHM =5,369,184,256B. Against2,147,483,648B workspace,
the legacy term alone is short **3,221,700,608B**, before any new core, sidecars,
audit maps, source export, working or recovery space. Replacing those bytes with
an empty/sparse file, virtual payload generator or repeated tiny fixture would not
qualify the recorded physical/I/O workload. Actual raw/embedded-reference counts
and distributions remain incompletely known, so a full-volume numeric working
budget and completion time cannot honestly be derived from this small count test.

Next prerequisite is an explicitly supported larger generated fixture envelope
containing that legacy allocation **plus** core/map/index/WAL/working/recovery terms
and an eligible Linux host, with a concrete finite workload and absolute budget.
No larger run or repeated production scan was made. The older40GiB+10GiB floor/
2GiB RAM proposal exceeds the last VM reading46.38GiB/~1.257GiB by approximately
3.62GiB disk and0.743GiB RAM; those requirements are unqualified proposals, not
permission to provision or silently lower them. No production normal/migration
ceiling or verification/interruption budget is derived here.

Order remaining: (1) exact successor CI/count-profile and full PR review,
(2) supported full-volume importer/coverage/resources qualification,
(3) measured normal/outage/retained-legacy capacity and full verification time,
(4) adapt/test existing manual controller for exact scope, source/data/UID bindings,
complete checks, one-use authorization/reaping and forward recovery,
(5) consolidated reviewed cutover/ceiling approval, initial retirementOFF and bounded
smoke, (6) separate retirement enablement/recovery/visibility acceptance,
(7) independently reviewed I7 fresh real-boundary and sustained multiple-cycle/storage
acceptance, plus research replay obligation; knowledge/RAG remains explicitly deferred.
PR stays draft. No production approval requested while earlier prerequisites fail.

The exact successor known-count profile additionally includes28 generated news
rows and validates FTS rebuilding; its source count and measured timing/bytes
come from that new Linux artifact. The local47907-row figures above precede that
addition and final deadline/source-binding checks, and are not substituted for it.
Local final backend361 tests PASS/14 Mac skips; controls120 PASS/3 Mac skips.
