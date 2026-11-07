# Selected recovery full application bootstrap — November 5

Current release review: [cutover decision and procedure](PR9_CUTOVER_READINESS_2026-11-05.md).
Source4bc3699/pushCI42144544730 PASS;deployment conflicts resolved;production
NO-GO pending recovery verification policy and matching controls/aggregate peak
qualification. Earlier scoped evidence and unfinished Phase1.75 gates below remain.


Heartbeat source8bb945a / exact Linux CI42126289598 PASS is preserved. The
historical1547a43 heartbeat failure remains FAIL; its individual host scheduling
and disk contributions cannot be recovered from its missing timeline.

## Implemented scope

Explicit three-file/hash-bound selected recovery capsule; immutable selected
bodies, exact manifest membership, conflict rejection, physical legacy binding,
transactional core proof, protected read fingerprints, sparse-ID reservation,
worker/history access and default production holds. No source database was copied.
Exact private manifest and qualification files are fsynced under ignored
`data/recovery-evidence/selected-2026-11-05-v1/`; committed sanitized attestation
is `evidence/selected-recovery-2026-11-05.json`. Selected JSONL was exported from
the already verified isolated stage and independently loaded by the capsule:
32,552,271 bytes, SHA256
`01f3ce94b62f3f91690b33e5aa4721de6ac6c22635d91b7c71dea7c0e689061c`.
No payloads, per-row identities, machine bindings or credentials are committed.

Complete bounded read-only legacy inventory found17 structured tables/189,576
rows,90,150,112 canonical array bytes; required metadata18268 +stream17924 +8
outcomes +1current-only price =>225777 audited inputs. The earlier150k and200k
estimates were insufficient. Explicit GENERATED qualification ceilings are now
250000 rows/256MiB logical bytes; defaults remain10000/60000 rows and128MiB.
Original2GiB workspace,512MiB Linux address space,170s work/180s total remain.
These are not production guard approvals.

Core layout3 (not feature/model version) adds a persisted logical admission
budget and atomic INSERT/UPDATE/DELETE quota triggers. Old layout2 activation
and writers hold. Fresh-B proposed core ceilings:250000 rows/256MiB logical,
512MiB physical including core WAL; raw ledger100000;64MiB/slot and2GiB new layout
remain separate. No automatic pruning or live production expansion. The finite
remaining logical allowance is NOT a qualified duration or continuous-operation
policy. Allocation sampler deduplicates inode length/blocks, includes all owned
regular FDs and unlinked TEMP, traverses Linux children of every thread, and
holds on incomplete visibility. Sampled peaks are not kernel quotas and do not
cover independent systemd service processes.

## Local bounded evidence

First full bootstrap FAIL32.629s: validator incorrectly assumed all source_time
fields were ISO text; actual historical_market_prices schema requires INTEGER
epoch seconds. Field-specific typed validation and malformed regressions fix this;
no timestamp normalization or original failure relabeling.

One changed full bootstrap PASS81.828s including preparation16.757s/cleanup.
225777 inputs/179671813 audit bytes; all17 structured tables compared exactly;
6755 metadata+6493 stream recovered;6776 snapshot/6745 prediction dependencies.
Core207852 rows/168200760 logical bytes; remaining42148 rows/100234696 bytes.
Constructor51.361s, restart6.084s, after-new-ack restart6.130s; new acknowledgement
229700 preserved. Legacy unchanged. Peak sampled allocation1079271424 bytes,
RSS178372608 bytes. macOS self-FD measurement only; Linux and complete real raw
volume NOT PROVEN by this run. See committed development JSON. Full source raw
volume is deliberately absent, not credited as free capacity.

Backend410 PASS/18 platform-or-privilege skips before final extra capsule test;
final capsule suite9 PASS. Controls120 PASS/3 privilege skips plus revised
fresh-B transition7 PASS, including selected recovery startup, B active/history,
pre/post-ack failures and forward reopen. Root Linux/exact export CI required.
Joint collector/scheduler/dashboard/SSE/prediction/rotation fixture now starts
with selected recovered inputs; it must pass Linux, no substitute component run.

## Remaining release gates and executable order (STOP)

1. Freeze successor exact source/export and require full exact Linux CI, including
   full-volume structured/fanout bootstrap, root descriptor/crash/joint proofs.
2. Keep legacy and all collector/ensemble/lifecycle writers stopped. Rehearse and
   review OS identity/permissions fence for all actual roles before any activation.
   Existing generated controller preserves2590s interruption/180s recovery/10s
   reaping and rejects production paths; old rollover scope/expiry cannot be reused.
3. Fresh post-quiescent identity is mandatory: normal last-close SQLite recovery
   may change main/WAL allocation, so the pre-stop capsule physical binding must
   HOLD. A reviewed fresh logical dependency proof/binding procedure is still
   required; never ignore a mismatch or invoke manual checkpoints.
4. Complete production legacy integrity verification budget is unresolved: prior
   1800s timeout cannot be silently replaced by targeted checks or rerun unchanged.
   Independent service TEMP/FD visibility, actual retained legacy/core/raw/WAL,
   recovery reserve and current physical headroom require complete accounting.
5. Production adapter allowlist/manual workflow still rejects this scope. Do not
   dispatch the old deployment command with a new SHA. After these gates, present
   one exact root/identity/hash/expiry/budget-bound command for separate approval.
6. Initial retirement OFF. After possible new acknowledgement, STOP all roles,
   preserve all files and recover forward using the identical capsule/core; never
   resume legacy writes or restore database contents. Generated control rehearsal
   proves committed-row preservation, not physical power-loss production proof.

Production capacity8GiB aggregate and any cutover/guard changes remain proposals.
No transfer, production repair, restart, migration, retirement or cloud write.
I7 fresh inputs/live rollover, cloud recovery, visibility, real-boundary/sustained
operation, historical raw replay and deferred knowledge/RAG remain OPEN; Redis
DEFERRED. PR9 remains DRAFT and Phase1.75 OPEN.

## Exact Linux53d8582 failed cleanup prerequisite

[CI42134362083](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/42134362083):
backend/root joint/control steps passed. Full bootstrap completed constructor,
exact structured/reference readback, both restarts and new229700 acknowledgement,
legacy unchanged, but final generated cleanup proof raised RuntimeError because
`fixture_owners` explicitly requires Linux root and workflow ran unprivileged.
Overall FAIL, not a bootstrap qualification PASS. Total155.732s,preparation23.029s,
constructor115.528s,restarts7.690/7.691s,peak1022902272B,RSS134549504B. No1s gate
or host/time/resource change. Owned family sampling worked; anonymous TEMP peak0
in this run is not evidence that other workloads never use temporary files.

Smallest fix: launch this generated-only qualification with the existing Linux
sudo mechanism already used by root descriptor/joint proofs, preserving exact
source bindings; fail before fixture allocation when Linux root visibility is
unavailable. Two focused preflight tests PASS. Successor exact CI required, no
unchanged retry. Nine existing merge conflicts against deployment78bcaf0 remain
an additional PR readiness gate; no merge or production change attempted.

## Corrected exact Linux bootstrap result

f7820026e78528dd1c1f4413dc2a62740b2711a7 full bootstrap PASS with root descriptor
visibility and completed cleanup:112.185s total,20.217s preparation,79.114s
constructor,5.702/5.683s restarts;225777 audit rows/179671813 bytes. All17 tables
and protected inputs exact,13248 selected rows,0 source changes,new229700 ack
preserved after restart. Peak whole sampled1022881792B,RSS134221824B. Linux
owned-family/all-regular-FD accounting includes unlinked TEMP; observed peak0
for unlinked TEMP here, plus a separate real SQLite disk-sort TEMP unit proves
positive detection. Sampled transients and independent production service owners
remain limitations, not zero-cost assumptions. Core207852rows/168200760logicalB;
42148rows/100234696logicalB spare within the explicitly qualified generated quota.
No production runway is inferred from this finite spare allowance. See
[evidence](evidence/full-bootstrap-linux-f782002.json).

## Frozen integrated checkpoint result

**f7820026e78528dd1c1f4413dc2a62740b2711a7 / [exact Linux CI42135084876 PASS](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/42135084876).**
Both test and integrated-qualification jobs passed. Exported backend413 tests,
13 privilege skips all run in dedicated root raw18/application38/runtime10/
cutover2/joint2 steps, with0 root skips. Controls121 PASS/0skips. Exact export
manifest verified after suites and after integrated workload. No unchanged retry;
53d8582's cleanup prerequisite failure remains FAIL.

| Check | Result/evidence |
|---|---|
|Heartbeat|PASS unchanged<1s: raw291.599ms, integrated293.014ms, joint277.384ms. Small explicit overdue-timer handoff; historical1547 failure unchanged/partial cause unknown|
|Selected recovery evidence|PASS original13248-row verification/stage preserved; exact private manifest/report/capsule durable and sanitized attestation committed|
|Full ApplicationStore bootstrap|PASS generated recorded counts/fanout112.185s,all17 tables exact,225777inputs,new ack229700 survived restart,legacy unchanged|
|Application integration/rotation|PASS generated recovered-input B→A→B→A,24 acknowledged ticks,correct dashboard/SSE generation/history/features,one feature worker,3 readback+reader holds,0 HTTP timeouts|
|Concurrent performance|PASS existing save/heartbeat/HTTP/history gates: joint save165.500ms,API192.769ms,SSE254.641ms,price2.806ms,feature30.841ms,history192.772ms. Scheduler→SSE883.842ms. Ack interval1177.149ms includes intentional fixture pauses; individual worst-gap attribution NOT PROVEN, not reclassified as save latency or live cadence acceptance|
|4000-event actual exported adapter|PASS4000committed/archived,0pending/errors,20cycles/publications,save134.675ms,heartbeat293.014ms,36.964s,whole workspace22884779B,RSS55230464B,cleanup complete|
|Finite core admission|PASS generated207852rows/168200760logicalB initial;250000/256MiB hard logical ceilings plus512MiB physical core/100000-event ledger. Remaining42148rows/100234696logicalB;continuous production runway NOT PROVEN|
|Allocation|PASS Linux owned-family/all regular FD/unlinked TEMP detection and generated bounded peak1022881792B/RSS134221824B. Full retained raw volume, independent systemd owners, unobserved transient peaks and production aggregate ceiling NOT PROVEN|
|Cutover controls|PASS generated selected-recovery transition,UID fence,partial-stop/error and pre/post-ack forward recovery tests;production scope/permissions/expiry/full verification/post-quiescent binding still BLOCKED|

[Sanitized integrated metrics](evidence/integrated-f782002.json). Prior qualified
recovery, rotation, cloud probe/throughput and latency evidence is reused only
within its stated scope. No real market boundary/multi-cycle production acceptance,
production scan, transfer, repair, migration or restart occurred. No new release
approval requested while technical prerequisites remain unresolved. The next
release-control work must resolve the post-quiescent legacy binding/full verification
policy and independent-service allocation before presenting one executable exact
cutover proposal. Existing manual command remains unusable;9deployment-base merge
conflicts also require reviewed resolution/exact CI before PR9 can leave draft.
