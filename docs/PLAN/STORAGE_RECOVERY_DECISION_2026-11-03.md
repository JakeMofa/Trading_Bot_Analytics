# Storage recovery: verified constraint and reviewed sequence — November 3

**Decision: NO-GO under the current restrictions. Keep collection stopped.**
This is the requested precise-impossibility outcome, not a production deletion
approval or an untested claim that a smaller reserve would make recovery safe.
Checkpoint1 reconciled; checkpoint2 diagnostic implementation tested; checkpoint3
production procedure blocked by physical capacity before a scan or DELETE.

## Reconciled outcome

Workflow41364015738 failed. The retained root report records STOP/TimeoutExpired,
changed=false,verification1790.105331s,interruption1790.801535s,recovery_failures=[],
helper_restoration=PASS,completed2026-11-02T00:20:21.653232Z. No application checkout
occurred. The writers recovered; collection later stopped at its storage ceiling.
The claimed authority is consumed historical evidence, never fresh authorization.
The2026-11-02T01:56:47.671426Z cap-review deadline has passed; no extension/permanent
capacity approval is inferred. Frozen78bcaf0/6d9edc3 and their evidence are preserved.
Rollover/health fix remains undeployed; feature freshness and Phase1.75 remain open.

Current bounded read at2026-11-03T19:10:27.748539Z:

| Item | Observed |
|---|---|
| Runtime |d56b4a73ad6f1a10ba2bac928087cd5d85c6a42a|
| API/ensemble/lifecycle |active,PIDs31763/31767/31771,NRestarts0|
| Collector |running=false; storage_guard=limit_reached|
| Feed last receipts |Nov2 07:49:38.997593Z Coinbase /07:49:38.396881Z Polymarket|
| Aggregate old health |ok,incorrectly; not evidence of collection|
| Main |5323907072bytes =5077.2734375MiB|
| WAL |45171712bytes =43.0791015625MiB|
| SHM |98304bytes,reported separately; existing guard counts main+WAL|
| Main+WAL /headroom |5120.3525390625MiB /-0.3525390625MiB|
| SQLite geometry |4096-byte pages,1299782pages,freelist0,auto_vacuumNONE,schema57|
| Durability |WAL,FULL(2)|
| Filesystem free |49807597568bytes; not additional DB+WAL guard capacity|
| Authority |no active manifest; claimed file remains,consumed|

Only bounded header/catalog/oldest16-row metadata, local16-cursor metadata and one
health request were used. No historical payload scan, service change, restart,
full integrity check, checkpoint, database copy, deletion or cloud mutation.
Active systemd services and responsive retained-state APIs must not be called
healthy collection. Do not repeatedly restart any service to test recovery.

## Exact timeout phase: unknown; observability corrected without a new scan

The retained report has neither active check nor completed checks. The old child
ran quick_check then foreign_key_check but emitted results only at completion or
caught exception. Parent communicate(timeout=work) could time out before the child
emitted its exception; reaping discarded that output. Elapsed1790s does not prove
which check was active. The completed workflow metadata confirms failure; its
raw maintenance-job log is unavailable. No new scan was run to guess the cause.

The existing verifier now atomically persists a private <=8192-byte partial report:
identity/check start, check completion, elapsed,active check,completed checks and
typed failure. There are no raw rows, credentials or arbitrary error messages.
The existing maintenance parent records total elapsed, termination/reaping outcome,
return code and whitelisted partial state on timeout or interruption. Partial data
is diagnostic, never verification authority; only complete successful checks pass.
The child remains read-only and owned/reaped before recovery. Budgets and policies
are unchanged; no helper was installed in production.

Generated tests cover success/unchanged DB bytes, first-check timeout, second-check
timeout with first PASS preserved, invalid FK result, atomic-publication failure,
truncated/stale partials, parent interruption, incomplete/invalid child results and
real owned-child termination/reaping. Local112 controls PASS(3Linux skips),93
retention safety tests PASS(2Linux skips). Exact commit/CI evidence follows below.

## Archive coverage: bounded evidence, not permission to delete

Two bounded authenticated metadata GETs returned at most8verified manifests per
raw dataset at19:13:22Z. Observation manifests cover declared ID ranges1..40000;
each has event_count,compressed size,SHA256,verified_at and metadata verification
`authenticated_readback_sha256`. Compressed objects are689579..1088988bytes.
The8stream manifests have exact received-time/source/event-id cursor metadata;
their returned time span beginsSep30 and reachesOct1 04:04:28Z. No claim of complete
historical coverage or continuous coverage across all those cursor intervals.

Eight oldest sampled local observation IDs lie in the fetched ranges. They are
NOT asserted eligible: protected outcome references and the highest-ID anchor
must survive. Later sampled IDs198243+ are outside this bounded manifest set.
Local archive cursors (including observations671248) are not deletion proof.
No fresh archive object was downloaded, no raw-row proof was made and no scope
is approved. Fresh authenticated object readback, exact SHA/count/boundary checking
and raw reconstruction are still mandatory for each future selected scope.

## Physical working-space calculation — decisive STOP

Let M be main-file bytes, W existing WAL, A additional peak WAL for the exact
batch and recovery, and R the required physical reserve. The existing accounting
requires M+W+A+R<=5120MiB. TEMP/proof/code filesystem space is separate and cannot
be subtracted from M+W. Reusable pages are also separate, never headroom credit.

Current M+W already exceeds5120 by0.3525390625MiB: there is no present write room.
All writers/readers would first need to drain under explicit approval. Ordinary
last-connection close is allowed in a future approved sequence, but WAL release
is not guaranteed and may involve ordinary checkpoint overlap. No manual WAL
operation or assumption that WAL is absent is permitted.

Even grant the best possible case for this calculation: W=0 and no main growth.
Then Hmax=5120-5077.2734375=**42.7265625MiB**. The main logical page count times4096
already equals the physical main file; freelist is0. With auto_vacuumNONE, exact
row deletion creates reusable database space, not a demonstrated file shrink.

- Even applying the prior128MiB reserve (which was approved only for an expired,
  pinned rollover release, not this recovery), the irreducible shortfall is
  **128-42.7265625=85.2734375MiB**, BEFORE any additional WAL or recovery working
  allocation. At the normal512MiB verification reserve it is469.2734375MiB.
- Existing128MiB planning used64MiB WAL/close allowance and32MiB contingency plus
  live growth. Removing live ingestion while quiescent still leaves96MiB of those
  allowances,53.2734375MiB above the optimistic physical headroom. This does not
  certify96 as a new recovery policy; it shows that simply removing ingestion
  does not make the old planning allowances fit.
- A new first-batch-specific peak A has NOT been measured or bounded for a fresh
  exact scope. Row count<=1000, a32MiB main cache and16MiB TEMP cache are not hard
  WAL/disk bounds. Earlier generated WAL measurements are not this production
  scope's bound. It would be unsafe to invent an8/16/32MiB requirement to fit.
- At current observed WAL high-water43.0791015625MiB, even an unchanged main file
  and unlimited reusable pages would leave -0.3525390625MiB physical headroom.
  This does not prove every restart repeats that peak; it proves a restart PASS
  cannot be inferred from freeing rows or a transient zero-WAL sample.

Therefore even a ZERO-row batch cannot satisfy a128MiB prerequisite. No choice of
eligible rows makes A negative. Keeping that reserve would require at least
85.2734375MiB physical main reclamation or equivalent ceiling change, plus actual
working demand. Main-file compaction/replacement and capacity increase are forbidden;
none is proposed. This mathematical conflict is independent of unknown batch size,
archive coverage and verification duration. It is sufficient to stop now.

The existing process512MiB RAM limit,64MiB proof-file limit,64MiB compressed archive
limit and256MiB decompression bound remain. A future exact scope also needs an
explicit TEMP/filesystem bound; TEMP cache size is not that bound. No unapproved
scratch allowance is silently applied. Plenty of filesystem space cannot resolve
the logical physical guard conflict.

## Required operation order if a separately feasible recovery is reviewed

This sequence documents the existing-code reuse and stop points. It is NOT an
execute authorization and does not bypass the preceding STOP.

1. Record old revision,sole collector,flagsOFF,service/monitor prior states and all
   physical allocation/identity. Quiesce API,ensemble,lifecycle and the active soak
   timer/oneshot as the existing maintenance route does. Require all DB/WAL/SHM
   owners drained; signal no unknown owner. No checkout or deployment retry.
2. Remeasure actual M/W/free pages and require a physically feasible reviewed
   write+recovery reserve. STOP before verification or deletion if it does not
   pass. This step cannot currently pass even its optimistic bound.
3. Complete quick_check and foreign_key_check in one read-only transaction, all
   writers quiescent, using the instrumented owned verifier. Both fully consumed,
   exact database/schema/old-runtime/helper identity binding. No stale partial
   PASS reuse. Historical earlier860.837s audit and current1790s timeout do not
   establish a current completion bound or which check needs more time. No justified
   finite completion guarantee is available; do not repeat30minutes unchanged or
   claim an arbitrary60minute doubling is sufficient. Any different work budget,
   absolute offline window and recovery reserve need ONE explicit approval.
4. Use existing retention_recovery.prepare_scope for <=1000eligible raw rows and
   ONLY applicable verified manifests. Freshly download/authenticate exact objects;
   verify compressed size/SHA256/event count/full boundaries, reconstruct originals
   with exact decimals and preserve a root-private immutable raw-scope proof/hash.
   This is exact raw evidence, not a database backup. Never stage that private proof.
5. Reuse retention_trial.apply_proved_scope and existing retention.apply_retention:
   FKON,FULL,existing timestamp guards,no fallback scan; BEGIN IMMEDIATE rechecks
   current48h cutoff,manifest coverage,exact identities,late prediction-context
   references and observation maximum-ID anchor. TEMP BEFORE DELETE scope guards
   compare full original column values; authorizer denies unrelated main writes.
   Existing production500ms total-duration gate REMAINS IN FORCE. Generated split
   approval is not a production waiver. A late committed failure is reported as
   committed,never relabelled rolled back or automatically retried.
6. Reconcile actual committed identities with AFTER DELETE callbacks, counts,
   subset-of-proof and identity hash; assert deleted keys absent and protected
   evidence/anchor preserved. Run existing affected-table FK verification. On any
   ambiguity STOP and report committed counts. Code rollback cannot restore rows;
   row recovery uses only the separately reviewed exact archive-backed method,
   not a DB restore and not implicit permission to reinsert data.
7. Separately measure freelist_count*page_size and physical main+WAL. A zero
   freelist gain is not a reusable-page PASS; partial leaf free space is not a
   proven global capacity budget. Require enough demonstrated reusable capacity
   AND physical WAL/recovery headroom for a reviewed restoration window.
8. Only after all gates pass may an explicitly approved restoration start the sole
   collector once,then bounded current-source/current-market/advancing persistence
   and service/API checks. No polling soak or repeated restart. Any failure leaves
   collection stopped; I7/Phase1.75 and freshness remain unfinished.

The existing preparation/apply CLIs require healthy live collection; they cannot
be used unmodified in this offline case. A maintenance-only quiescence guard would
need explicit review, not disabling health silently. The existing deployment
controller also automatically restores prior active writers after verification
failure. That is not an approved storage-recovery behavior: ordinary WAL close
could lower the guard enough for an API restart to start collection before both
capacity gates pass. Keep writers stopped on a failed storage recovery; use any
reserved recovery time to reap children,record status and restore only controls
that cannot resume collection. No such production timing/restoration-policy change
has been implemented. No new controller is proposed.

## One decision; no unsafe production approval request

**Keep collection stopped: recovery is not executable under the present physical
capacity constraints.** Do not authorize another scan or first DELETE hoping it
will create physical headroom. No production operations or changed policy values
are requested by this milestone. The expiry is not extended;128 is not repurposed;
normal512 and500ms policies remain as they were.

A future consolidated approval would have to state ALL actual values together:
physically feasible reserve+proven first-scope WAL/TEMP/recovery bounds; a justified
complete-verification budget/absolute offline window; stopped-collection guards
and failure restoration; fresh authority replacing expired/consumed records; and
separate reusable/physical conditions for restoring collection. The necessary
reserve inequality is R<=42.7265625-A MiB in the optimistic zero-WAL case, not128.
A smaller numeric reserve alone is not evidence that A or future WAL peaks fit.
Those facts are unavailable and current prohibited reclamation/capacity changes
cannot be silently selected. Accordingly there is no safe execution-ready approval
question to ask today. This is a quantified constraint outcome, not an unexplained
BLOCKED, new architecture proposal or unchanged production experiment.

PRODUCTION CHANGED: NO. Essential bounded reads only. Services/collection/flags,
capacity and authorizations untouched. Claimed historical authority retained as
consumed evidence. No restart,cleanup,deployment retry,heavy scan,copy/snapshot,
VACUUM,manualWAL,guard increase,paidAI orPhase2.

## Frozen tested diagnostic source and checkpoint report

Exact source `b8f065b7202f3f10b6bfb3b1ce1e5213496314f3`,
[CI41702333233 PASS](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41702333233):
253backend tests and112control tests. Real generated timeout/reaping tests ran.
No changed code after this CI; documentation below records the completed decision.
This is working-branch diagnostic source, not a new deployment candidate.

| File at exact source | SHA256 |
|---|---|
|deploy/lightsail/release_verification.py|bff1677d250855b7973aeeb3f6554f7b743b68cc06c3e656ab2f688b9e14de4a|
|deploy/lightsail/maintenance_host.py|5687e31a2104af19f637fb32603e723bfb427b723c1e8d5c48902747c4994471|
|deploy/lightsail/test_verification_progress.py|a3a5d4c0d894abb9c2bb7cb3dba4766f1de0dd369bb6a91e73c7d4915cbd2c45|
|backend/app/retention.py|006431d87008d267bc39ecf7341ac41a6a028e0fa85289f2cb62e792e99b6eaf|
|backend/app/retention_trial.py|9beca6178f2ff2e32888f8b800d5b2ccd7881f584f08939a7040394e5abf8fc3|
|backend/app/retention_recovery.py|6a0212eb97ec14853e900cb431e8999b4f9c925829f0fba48ae050dbfc5b6c15|
|backend/prepare_retention_recovery.py|1c1abf0d5e8f954f77e9daea173dc750128e28e510b84433bfc0505aa0c2c55d|
|backend/run_proved_retention_trial.py|6770630fadd9bb692daa28ea1f79a36b4c4b9e5cdf021ac6e54524146d301e0d|

Existing policy constants remain1800s verification,10s reap,600s other,180s
recovery and2590s absolute interruption. The failed parent's actual SQL work cap
was1790s. These are code values, NOT fresh authorization after the passed review
deadline. No new work budget, reserve, deadline or500ms exception is proposed or
implemented. Maximum production interruption authorized by this preparation:0s.
An execution maximum cannot be honestly supplied for an unapproved, physically
blocked recovery; do not relabel the old maintenance window as a new one.

CHECKPOINT:1record reconciliation and2verifier diagnostics.
RESULT:PASS (historical exact timeout phase remains UNKNOWN).
EVIDENCE:retained STOP report,bounded Nov3 metadata,new7tests,exactCI above.
PRODUCTION CHANGED:NO.
EXACT REMAINING CONSTRAINT:checkpoint3requires physical reserve/WAL/recovery room;
evenbestcase42.726563MiB cannotmeet128MiB,letalone normal512MiB; exactscopewrite
bound/verificationcompletionbudget/offline restoration authority not established.
NEXT ACTION:keepcollectionstopped; resolve this quantified policy feasibility
before any production approval, scan, DELETE or restart.
APPROVAL NEEDED:no execution-ready approval is safe under the current boundaries.
No prohibited reclamation/capacity change or guessed timing/reserve is requested.
