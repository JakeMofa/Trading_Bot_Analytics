# PR9 cutover-readiness decision and gated procedure

Current checkpoint: [continuous A/B verification result](PR9_CONTINUOUS_AB_CHECKPOINT_2026-11-05.md).
101921e/pushCI42161684724 PASS bounded generated progress/enablement/repeated
handoff and complete FK-table progress.5GiB target remains provisional;8GiB
recovery profile is not continuous capacity. Production release remains NO-GO.

**Decision: NO-GO for production.** This is release preparation, not authorization.
Production remains on d56b4a7,legacy collection held at its existing storage guard;
API/ensemble/lifecycle services were active at the bounded metadata sample. No
services were changed,SQLite connection opened,data copied,permission changed,
helper installed,cloud write performed or workflow dispatched. Full-window/live
acceptance and Phase1.75 completion are not claimed.

## Completed release preparation

Reuse f782002/CI42135084876 bootstrap/recovery/4000 workload and earlier approved
private-cloud byte/readback/throughput evidence within their original scopes.
Merge864d0b6 has parents d1017fe and deployment78bcaf0. All9conflicts preserve the
qualified working safeguards: current exact-export/root/integrated CI; health
storage-blocked reasons; streaming single-worker/independent discovery,exact
microsecond/timezone comparisons,storage routing; normal512MiB reserve and bounded
smoke; generated-only forward transition; durable verification phase/reaping
observability; dated reports retain their superseding amendments. The sole tree
addition versus d1017fe is deployment's4rollover publication regressions,all PASS.
No existing deployment requirement was discarded to make a conflict disappear.
Deployment78bcaf0 is now an ancestor; no base-branch push/PR merge occurred.

Allocation inspector now takes explicit API/ensemble/lifecycle PID+start-tick+UID
bindings,includes each root's descendants and all regular descriptors (including
unlinked TEMP),deduplicates inode allocation,holds on missing/replaced owners or
incomplete visibility,limits inspection to2s/8192entries/32processes/128threads.
It never reads command lines,environment or payloads. Linux sibling-process test
proves discovery of an independently rooted worker's262144-byte unlinked file,
and holds on PID-reuse identity/exit. This is sampled visibility,not a kernel quota
or a normal-production guard change. No periodic observation/background soak.

Local backend418PASS/19platform skips;controls122PASS/3platform skips. Exact merged
successor Linux CI must cover the Linux sibling/root cases and exact export.

## Measured storage and supported limits

One bounded read-only pinned-SSH metadata sample at2026-11-06T01:27:03Z took0.069s.
Main5323907072B;WAL charged45178880B;SHM98304B;named legacy5369184256B.
All3independent service roots plus observer:5369188352B incl4096B other open file;
no unlinked file observed in this idle sample. Free49795989504B(~46.38GiB),
available RAM1379188736B(~1.28GiB). Sample freshness expires; dispatch requires a
fresh sample. This is not a peak/runtime-overrun proof.

| Limit/term | Evidence/status |
|---|---|
|Generated qualification|2GiB whole workspace,512MiB Linux process address space,170s work/180s including preparation+cleanup;unchanged|
|Full bootstrap|225777 audited inputs/179671813B;17structured tables;13248 recovered inputs;112.185s;peak1022881792B/RSS134221824B;PASS f782002|
|Finite core logical admission|250000rows/256MiB explicit generated;initial207852rows/168200760B;spare42148rows/100234696B;not a live-duration forecast|
|Recovery-only proposed runtime quotas|512MiB core+sidecars,64MiB/slot,100000new-event ledger,2GiB aggregate new layout inclworking/capsule/allsidecars;not continuous acceptance|
|Rotation|72h maximum active age OR2MiB early trigger;retirementOFF initially;filled slots STOP. No promise of72h minimum local window|
|Retained+new2GiB+recovery512MiB|8053542912B including observed other FD;8GiB proposal leaves536391680B(~511.54MiB) margin|
|Filesystem floor|10GiB additional;after allocating fullnew+recovery from sampled free,47111634944B remains;arithmetic fits|
|Old5120MiB guard|479232B below observed charged total;still STOP,unchanged|
|8GiB aggregate/expiry|Still proposal/unapplied. Peak transaction/archive overrun across actual service roles and finite collection runway NOT PROVEN;no automatic24h or cap-deadline extension|
|Maintenance envelope|Existing1800s complete verification,600s other work,10s reap,180s recovery,2590s absolute interruption;unchanged|

All retained bytes count. No freelist/sparse/file-length credit or database shrink
assumption. Quota arithmetic cannot qualify runtime overshoot. The exported4k
scaled per-event growth does not establish production ingest/core growth rates.

## Executable review step (safe now)

From the existing checkout, this command evaluates the committed read-only sample
without contacting production,installing helpers or modifying storage:

```sh
.venv/bin/python deploy/lightsail/ab72_metadata.py --recovery-preflight \
  docs/PLAN/evidence/release-readonly-allocation-2026-11-05.json
```

It returns REVIEW_ONLY_NOT_AUTHORITY,explicit production_authorized=false,
capacity arithmetic and required unresolved gates. Its sample is evidence,not fresh
dispatch authority. Re-run only with a genuinely fresh approved read-only inventory
immediately before any separately reviewed cutover,not repeated polling.

## Cutover procedure: STOP before installation/dispatch

The application refuses production paths and the old manual route is pinned to a
different application scope/baseline/expired November2deadline. **There is no honest
executable production dispatch on this candidate.** Do not use the old maintenance
command with this SHA or rename a production directory to generated-ab-*.

Required execution order after the blockers below are resolved and one separate
cutover approval is recorded:

1. Promote only the reviewed final candidate to the existing deployment branch;
   require its exact deployment-branch push CI,export/file/helper hashes and fresh
   runner/SSH/physical-storage preflight. No production action on PR validation.
2. Claim one private root-owned authority binding full candidate/CI/export,old
   revision,source/capsule/catalog hashes,all3service identities/config/fence,
   exact quotas,verification/recovery ceilings and a newly reviewed absolute UTC
   expiry. Do not reuse/extend the old cap deadline or consumed exception.
3. Pause monitor and all3writer roles once; prove global descriptor drainage.
   Fence old writer UID999 from main/replacement/sidecars,including the parent;
   new core/raw remains private service-owned. Before/after data identities and
   every permission change must be recorded. These production permission changes
   are not authorized by this review.
4. Complete the approved verification policy in its original absolute envelope.
   Under current policy this includes complete legacy quick_check/FK,not just
   protected point reads. Preserve progress/active-check/timing and owned reaping.
   Do not launch the historical1790s operation unchanged to see if it now passes.
5. After quiescence AND the permission fence,refresh exact dependencies/source
   identity;revalidate the unchanged approved13248-row catalog and supporting
   provenance against the independently verified source. Materialize new bounded
   proof/capsule bindings from that evidence. Never ignore old physical-binding
   mismatch after normal last-close/main/WAL or ownership changes.
6. Bootstrap isolated new core/B through the actual application path within the
   supported250k/256MiB logical scope;fully check new core/B/foreign keys/exact
   identities/protected inputs. Include allproof/capsule/working/WAL/TEMP bytes
   under the aggregate guard;no uncharged files outside the guarded roots.
7. Apply only reviewed manual-workflow/systemd runtime bindings;start exactly one
   collector and one serial feature worker;then dependent ensemble/lifecycle.
   FULL remains;retirement/local-retention/paidAI OFF;legacy stays sealed.
8. One bounded functional smoke:API/currentmarket/sourcefreshness,advancing
   persistence,truthful stale/feature-unavailable status,dashboard/SSE,stable
   services. No20–30min window,repeated recovery loops or automatic soak.
9. On any possible new acknowledgement,stop all roles,preserve allfiles/proofs,
   and recover FORWARD from committed core intents/receipts using the same exact
   approved evidence. Never restore data or resume legacy writes. Before first
   new acknowledgement,keep collection stopped on failure. Restore temporary
   helper CODE/monitor only as reviewed and revoke remaining authority.
10. Report actual interruption,revision,feed/persistence/remaining capacity and
    yield. Multi-cycle/real-boundary acceptance NOT PERFORMED unless evidenced.

## Specific remaining blocker / decision

The first policy blocker is **complete legacy verification**. The old1790.105s
attempt timed out;its active check remains unknown. No evidence establishes that
full legacy checks fit the unchanged1800sverification/2590sinterruption envelope.
Current policy cannot silently be replaced by the passing112snew-core bootstrap.
No new heavy production scan is authorized and none ran.

The smallest policy alternative for review is initial fresh-B activation after
complete new-core/B checks and exact selected/protected legacy input verification,
with unrelated legacy raw explicitly unverified/read-only and legacy retirement
held until its complete checks/archive/reference proof pass. This changes the
activation prerequisite only;it does NOT mark legacy healthy/verified or authorize
retirement. It is NOT implemented or approved here. The other option is a separately
reviewed verification strategy/budget that demonstrably fits2590s;simply repeating
the old scan or extending interruption is not an evidence-backed solution.

Production path/UID/fence/manual-scope implementation and aggregate runtime-overrun
qualification must then match that selected policy. Their absence is reported
explicitly,not placeholder success. No production approval request is made while
these technical prerequisites remain unresolved. PR9 stays DRAFT,I7/Phase1.75OPEN;
continuous cloud recovery/visibility/sustained-operation/raw replay/deferredRAG and
independent live freshness/boundary gates remain open. Redis remains deferred.

## Additional confirmed manual-route dependency

Current `maintenance_host.Host.preflight()` requires physical main+WAL<5120MiB,
collector.running=true and `collection_state()` with current market/quote/source
ages[-5,30]s before claiming authority. The measured main+WAL already exceeds the
physical5120MiB ceiling;the starting state is storage-held. Reusing that route
cannot reach verification even if its old expiry were refreshed. Recovery scope
must explicitly accept only the evidenced STORAGE_STOP starting state,without
claiming healthy feeds before restart,and retain mandatory fresh-feed/persistence
post-smoke checks. This is part of the reviewed fresh-B scope,not an implemented
healthy-preflight bypass. All other error states still HOLD.

The PID/start-time binding and visibility limits follow the Linux kernel
[/proc documentation](https://www.kernel.org/doc/html/latest/filesystems/proc.html),
including its warning that numeric PIDs can be reused. Identity is checked before
and after the sampled walk;the test proves changed identity and exited-owner holds.
No atomic-all-FD or kernel-enforced peak claim is made.

## Frozen source and exact Linux result

**4bc3699f05ad86708c5833d99f57c2acb1910764 — [push CI42144544730 PASS](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/42144544730).**
Both test/integrated jobs passed;418backend tests/13privilege skips,all13covered in
root raw18/application38/runtime10/cutover2/joint2 with0root skips;122controls/0skips.
Independent sibling-worker TEMP/PID-reuse/exit test PASS on Linux. Exact export
manifest revalidated after suites and integrated workload. GitHub PR9 mergeable=true,
still draft;production deployment branch remains78bcaf0. This is exact SOURCE push
CI,not promotion,dispatch or passing deployment-branch HEAD authorization.
A separate PR-event run42144550357 used synthetic merge9b31c566;it is NOT substituted
for exact4bc3699 evidence. No job rerun or new VM workload was dispatched.

| Release check | Result |
|---|---|
|9deployment conflicts|PASS merge864d0b6,required behavior retained;4deployment rollover regressions added;GitHub conflict-free|
|Core application/recovery|PASS generated/full recorded fanout155.459s including preparation/cleanup;225777inputs;legacy unchanged;new acknowledgement survives restart;peak1022951424B,RSS134606848B|
|4000event workload|PASS4000committed/archived,0pending/errors,20publications,save66.569ms,heartbeat286.664ms,54.784s|
|Actual API/SSE/scheduler/feature/lifecycle handoff|PASS generated repeated B→A→B→A,one feature worker,3readback/reader holds,0HTTPtimeouts;save44.712ms,heartbeat134.825ms,API83.552ms,SSE180.798ms,price2.069ms,history65.397ms,ackinterval894.470ms|
|Independent-service descriptor measurement|PASS Linux proof and bounded read-only VM sample;not normal-runtime aggregate guard/peak qualification|
|Actual storage-limit qualification|NOT PROVEN:8GiB arithmetic fits,write/working-file overshoot and live runway remain unqualified;no guard approval|
|Post-quiescent binding|BLOCKED:must freshly revalidate exact approved catalog after last-close/fence;cannot reuse pre-fence physical identity|
|Complete legacy verification|BLOCKED:prior1790s timeout/active check unknown,no demonstrated1800/2590s fit,no new scan|
|Production runtime/manual scope|NOT IMPLEMENTED for recovery pending selected policy:generated path holds,old baseline/expiry/ceiling/live-feed initial preflight reject current state|
|Production cutover|NO-GO;no promotion,installation,permission/storage change,restart or dispatch|

[Exact sanitized Linux results](evidence/release-exact-4bc3699.json) and
[merge blob preservation](evidence/release-merge-preservation-2026-11-05.json).
All earlier failures retain their original status. The larger full-bootstrap time
versus f782002 is not attributed to host contention or the sampler without timing
proof;it passes the unchanged deadline and is not a new production-size claim.

**One next decision for preparation:** choose the activation verification policy.
Retaining full legacy verification needs a demonstrably bounded strategy;the
minimal alternative is full verification of new core/B and exact recovered/
protected inputs,with unrelated legacy raw unavailable to live calculation/raw-
history routes until verified,legacy data retained and retirementOFF. Required
legacy structured/prediction history remains preserved in verified core. The
starting-state exception must be limited to evidenced storage STOP,with genuine
fresh feeds/persistence mandatory after startup. This policy is proposed only.
After that decision,finish the matching production path/fence/manual and aggregate
runtime-overrun qualification and present one execution-ready approval package.
No production-cutover approval is requested on this NO-GO packet.
