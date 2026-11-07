# Retention performance decision — existing implementation and evidence

**Result: NOT PROVEN.** No evidenced small SQL/delete change explains or fixes the
representative commit overrun. Recommend reviewing a generated-qualification
acceptance-policy split, not weakening archive/reference checks or deploying an
unmeasured I/O change. Current500ms policy remains exactly in force.

The shared ChatGPT URL was attempted but unavailable through the browser tool;
this assessment uses repository code and preserved local evidence only.

## What is established

Current apply_retention performs current timestamp/manifest coverage, protected
identity selection and exact deletes within the same BEGIN IMMEDIATE. Deletion
is followed by FULL durable commit, unlocked TEMP bookkeeping and100ms handoff.
The post-BEGIN timer includes commit return, not the full kernel WRITE-lock
lifetime; BEGIN acquisition/wait is excluded. Completed overrun commits are
reported as committed, followed by STOP, never claimed rolled back.

Representative failed profiles retained their500ms STOP:

| Profile | Post-BEGIN total | Commit call | Measured collector interference |
|---|---:|---:|---|
| Revised1000-row profile |692.804ms|679.865ms|0errors;maxsave53.989ms;heartbeat81.471ms|
|500-row recovered-window profile |537.332ms|525.525ms|0errors;maxsave43.992ms;heartbeat78.615ms|
|Authorized256-page/500-row experiment |502.686ms|495.384ms|0errors;maxsave65.974ms;heartbeat95.251ms|

The latest example's timestamp/coverage/selection/delete phases total about7.2ms.
The measured blocker is commit-call latency, not the previously fixed coverage
scan. Changing safety predicates or repeating batch/threshold searches does not
address an established remaining SQL bottleneck.

Validated reduced Linux trace (SQLite3.45.1 Ubuntu3.45.1-1ubuntu2.8, WAL/FULL,
default1000-page threshold): slowest commit220.379ms, total WRITE occupancy
99.394..99.423ms, WRITE release83.185ms after commit entry,137.195ms remaining
afterward. WAL fdatasync58.225ms occurred while locked; DB fdatasync116.707ms and
204DB writes occurred after release. The collector acquired the same shm byte120
WRITE lock before retention commit returned. Another commit had158.082ms after
release including126.007ms DB sync. This establishes both lock-held durability
and post-release checkpoint work in the traced sample. It does not establish
which dominated the historical >500ms failures. Timing overhead was unquantified.

Source/timing/syscall references:
[SQLITE_WRITER_LOCK_DIAGNOSTIC_2026-11-01.md](SQLITE_WRITER_LOCK_DIAGNOSTIC_2026-11-01.md).
Automatic checkpointing uses SQLite's post-release hook, but FULL commit WAL sync
still occurs before release. No manual checkpoint or durability change is proposed.

## Missing causal evidence

No trace captured an actually slow representative failing commit. Therefore the
historical excess cannot be apportioned between lock-held WAL sync, post-release
checkpoint DB writes/sync, scheduling and tracing overhead. Low max collector
latency alone cannot locate the lock release: a collector may not contend at the
worst instant. No root-cause claim about disk faults or checkpoint dominance.

There is no completed new representative VM qualification. Earlier representative
instrumentation was stopped by sustained feed preflight before a fixture started;
that is historical evidence, not a claim about current VM health. No new VM load,
recovery window or unchanged qualification was run in this milestone. A reduced
traced fixture is diagnostic evidence, not production latency qualification.

## Explicit policy proposal for review, not applied

Smallest supported direction: separate lock occupancy from post-release operation
latency **initially in generated qualification only**:

1. Every batch's validated syscall WRITE-occupancy upper bracket <=500ms.
2. Post-BEGIN-through-commit-return total AND commit-call <=1000ms, retaining
   the existing180s whole-workload limit, work/cleanup supervisor bounds, process/
   fixture limits and100ms handoff.1000ms is a proposed engineering ceiling,
   not an observed SQLite upper bound or proof every workload will complete.
3. Collector save delay and heartbeat each <1000ms, zero errors, actual deployed
   save-before-RAM order, advancing persistence/RAM and complete expected cleanup.
4. WAL/FULL and unchanged default journal/checkpoint settings. Preserve exact
   archive/recovery eligibility, coverage/reference/current timestamp checks,
   integrity/FK results and all existing storage protections.
5. A tracing-overrun or incomplete/ambiguous lock interval is NOT a pass. Retain
   untraced total/commit/collector measurements separately. Intrusive tracing
   stays out of ordinary production. Never fill occupancy from a Python flag.

This addresses a demonstrated measurement conflation: post-release checkpoint
work need not occupy WRITE, yet fails the existing total-duration budget. It
would permit testing whether useful cleanup can finish without unacceptable
collection interference. It is conditional: representative lock-held sync may
still fail500ms, or checkpoint work may fail1000ms/completion/collector gates.
It does NOT establish that the historical failure was harmless or resolved.

This proposal changes qualification acceptance and therefore requires explicit
user approval before implementation or use. Old failures remain failures. The
production500ms total gate remains unchanged; generated qualification would not
by itself authorize a production policy change or cleanup. There is currently
no nonintrusive per-commit production WRITE measurement. Raising a production
total ceiling could allow a longer lock-held stall than500ms; that separate
tradeoff must not be concealed as merely renaming metrics.

No speculative checkpoint owner, writer coordinator, new service, native VFS or
smaller-batch change is justified by current causal evidence. No such change was
implemented. If representative lock-held FULL sync dominates, the split alone
will fail its500ms occupancy requirement, requiring a new evidenced decision.

## Safety regression and measured throughput

Current unchanged retention safety suite93tests PASS(two Linux-only skips) plus
proved-retention operator2tests PASS. Coverage includes archive size/count/hash/
identity and missing coverage refusal, sparse/dense range semantics, protected and
late references, mutations after warming, exact identities/decimals, rollback and
accurate committed-row overrun reporting. Harness controls retain FULL durability
and reject incompatible experimental connections/settings. Unit tests do not
prove bounded filesystem sync latency; the real trace records WAL/FULL(2) settings.
No production archive scope beyond its prepared exact proof is newly certified.

Preserved reduced trace workload:11998observation +11999stream rows deleted =
23997generated rows, supervised11.798431s including setup/cleanup, approximately
2033.914rows/s end-to-end.48retention batches. Collector65saves/65RAM updates,
0errors,maxsave137.707ms,heartbeat165.329ms. Legacy total maximum236.473ms and
observed occupancy upper maximum99.423ms. These are **scaled traced measurements**,
not sustained representative throughput or a safe catch-up rate. No new throughput
claim is inferred from a failed run's partial committed count.

Evidence: existing sqlite-writer-lock-084ca92/trace, stdout.jsonl and analysis.json;
new local regression logs in retention-performance-decision-20261101 under the
existing lifecycle evidence root. No local DB or raw data is committed.

## One next action

Review/approve or reject the above **generated-only split-gate qualification policy**.
If approved, one specifically instrumented representative workload must establish
where the actual long commit occurs, with independent collector/throughput metrics;
no matrix or unchanged batch/checkpoint experiment. This is not permission to
change the production gate, deploy, delete or retry unsafe VM preflights.

Capacity stays a separate STOP: a performance pass cannot provide physical512MiB
headroom, shrink the legacy DB or authorize cleanup. Preserve93161cf and stopped
rotation work. Retention/paidAI OFF,productiondeleted0,storageceilings/deadline
unchanged; I7/Phase1.75 OPEN, no Phase2.
