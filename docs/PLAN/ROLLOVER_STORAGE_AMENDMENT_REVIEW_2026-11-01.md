# One-use rollover release storage amendment — for approval only

Retention qualification status: **BLOCKED_BY_UNDEPLOYED_ROLLOVER_FIX**.
Preserve scoped harness6d9edc3e2ba6de31cc3dd8115736314d74c7ece3 and its
[passing CI41361239486](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41361239486).
No more VM qualification attempts or diagnosis of the known rollover defect.
The qualification failure history remains unchanged.

## Smallest proposed policy change

For ONE quiescent maintenance release of the existing schema-free rollover/health
application, replace the512MiB physical reserve prerequisite with **128MiB**.
Keep the5120MiB DB+WAL ceiling and its physical accounting unchanged. Apply only
to the existing maintenance route, at both its main-file feasibility precheck and
actual post-stop DB+WAL gate. The normal/live verification route retains512MiB.
Do not substitute free pages or filesystem space for physical DB+WAL headroom.

The existing frozen release is93161cf8843cd0264fe9b75d20b2204e979ca062,
[Python CI41336249861](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41336249861),
[validation41336249942](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41336249942).
Its application blobs remain pinned tofd90458: onlyapi.py,streaming.py and
live_health.py differ from deployed d56b4a7. No feature/price query, index, schema,
dependency, retention, units or configuration changes. Preserve93161cf and6d9edc3;
if approved, the amended existing controls need a separately frozen successor SHA,
matching manifest/helper hashes and exact CI before execution. The old consumed
exception is unusable. No new controller or verification bypass is proposed.

## Actual demand versus blanket reserve

| Phase | Storage implication |
|---|---|
| Complete quick_check/FK verification |Existing verifier opens mode=ro,query_only,one read transaction. All existing writers stay stopped. No intended DB/WAL writes, no concurrent writer accumulating pinned WAL, no DB copy or index build.512MiB process address-space limit is RAM, not a disk allocation.|
| Ordinary last-connection close |May checkpoint and extend the main file before ordinary WAL release. Do not assume WAL disappears or credit its current32.863342MiB as recovered space. Allow overlap explicitly; no manual WAL operation.|
| Code checkout/helper records |Code and bounded records use filesystem space, not a database-sized allocation. Existing filesystem free-space gate stays; free disk does not enlarge the DB+WAL ceiling.|
| Restart, smoke and code rollback/recovery |Normal writes resume and can grow DB/WAL. Reserve for this interval; verification itself does not create the live-scan WAL-growth exposure. No database restoration.|

Thus512MiB is not an intrinsic measured requirement of this schema-free quiescent
operation. It is an existing blanket policy prerequisite and remains binding until
explicitly amended. A zero-reserve proposal would ignore close/recovery growth.

Proposed128MiB operation budget, using already recorded planning allowances:

- **64MiB additional WAL/ordinary-close overlap allowance**, beyond whatever WAL
  allocation the fresh physical measurement already counts. The observed WAL was
  32.863342MiB. This is an allowance, not guaranteed WAL reclamation.
- **23.144531MiB growth allowance:** prior20KiB/s planning rate, with50% margin,
  over790seconds (600s other work+180s recovery+10s reap). Full verification stays
  quiescent; its1800s is not incorrectly counted as concurrent ingestion time.
- **32MiB contingency**, reusing the prior storage planning allowance.

Total119.144531MiB, rounded upward to128MiB (8.855469MiB additional margin).
The20KiB/s rate and allowances come from the existing October26 bridge planning
(roadmap), not a new benchmark. Earlier observed whole-database physical/logical
rates were32.2814/41.5764MiB/hour. **No measured worst-case burst bound exists.**
128MiB is an evidence-informed operational reserve proposed for explicit risk
acceptance, not a proven mathematical minimum or guarantee against arbitrary
bursts. Existing physical ceiling, stop/recovery controls and bounded budgets
remain mandatory. No larger workload, background soak or live heavy scan is added.
Pre-install/setup collection is not free: refresh the physical gate immediately
before the approved attempt; stale arithmetic cannot authorize execution.

## Existing measurements, not a fresh capacity PASS

Latest recorded physical metadata at23:05Z:

| Item | Bytes /MiB |
|---|---|
| Main file |5004308480bytes /4772.480469MiB|
| WAL |34459712bytes /32.863342MiB|
| Main+WAL |4805.343811MiB|
| Physical headroom below5120 |314.656189MiB|
| Shortfall against existing512 reserve |197.343811MiB: current policy STOP|
| Headroom beyond proposed128 reserve |186.656189MiB at that sample only|

No fresh production inspection or scan was run for this proposal. Continued writes
make this sample stale for execution. The historical50GB filesystem-free figures
are not capacity credit. No claim is made that the amendment alone clears present
preflight, integrity, recovery, deadline or acceptance gates.

## Unchanged release controls and decision

Use the existing manual workflow and quiescent controller only. Preserve1800s full
verification,600s combined other work,10s reap,180s recovery and2590s absolute
interruption from first stop, with50minute enclosing workflow. Existing service
pause/restore, ownership drain, complete quick/FK checks and exact database/schema/
runtime/release/helper/configuration binding remain. No concurrent-write proof
reuse, consumed exception, deadline extension or automatic retry. Preserve existing
service recovery and code-only rollback; never restore database contents.

The one-use policy must expire on completion/failure and remain subject to the
unchanged cap-review deadline2026-11-02T01:56:47.671426Z and enough remaining time
for the approved interruption budget. Normal512MiB policy is not globally lowered.
A post-release pass means bounded functional smoke only, then report/yield;
multi-cycle and real-boundary acceptance remain NOT PERFORMED unless evidenced.
Retention, capacity cleanup and paid AI remain OFF; I7/Phase1.75 stay OPEN.

**Decision requested:** approve the one-use128MiB physical reserve, replacing512MiB
only for this exact application and existing quiescent maintenance route, with
5120MiB ceiling and all other limits unchanged. This document implements nothing
and grants no production authority. The amendment and production action require
explicit user approval; no helper installation, heavy verification or dispatch
occurs while approval is absent.

This breaks the dependency by allowing the collection-continuity fix to be
released before cleanup qualification; it does not clear retention/capacity. Only
after the fix and truthful health are independently validated should pending
qualification resume. No new architecture, controller or experiment is needed.

## User approval and implementation scope

The user explicitly approved this one-use128MiB amendment and continuation of the
previously authorized single maintenance attempt after tested successor/exact CI,
fresh capacity and unchanged deadline checks. Normal512MiB route remains binding.
No repeat approval is required for that scope. Only maintenance reserve constants,
its precheck, boundary tests and procedure change; physical5120 accounting and all
budgets remain unchanged. Production execution evidence must be recorded separately.

Successor78bcaf0/exact CI PASS. The single maintenance dispatch was blocked by an
unavailable approved runner and cancelled before any maintenance steps. Temporary
helpers restored,unused authority revoked. No deployment/interruption; remaining
headroom295.675720MiB at23:37:23Z. See
[ROLLOVER_MAINTENANCE128_OUTCOME_2026-11-01.md](ROLLOVER_MAINTENANCE128_OUTCOME_2026-11-01.md).
No automatic retry or repeat reserve approval; runtime/cap/flags/deadline unchanged.
