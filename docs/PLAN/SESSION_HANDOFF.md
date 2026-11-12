# Tradebot session handoff

Updated November 5, 2026. Use this entry point when resuming in Codex, Claude,
or another coding session. The master roadmap governs project status and
production authorization.

## Resume here — November 11, 2026

Pipeline milestone: four environment entry points are implemented in the
release-control review branch (CI/CD Production and CI/CD Preprod). Existing
exact-source python-tests.yml remains the shared engine. GitHub preprod and
production environments exist; production requires owner approval and main.
No deployment keys or main branch protection were installed. Both runtime
profiles remain NOT QUALIFIED/disabled; no workflow was dispatched. Next work
is PP PostgreSQL/application plus restricted controller qualification, then
scoped secrets/host pins/runner and approved PP deployment. See
ENVIRONMENT_PIPELINE_2026-11-11.md. Exact successor CI pending after push.

Read the newest Current direction block in INTELLIGENCE_REBUILD_PLAN.md and
POSTGRES_PP_TRANSITION_2026-11-11.md first. PostgreSQL is the user's intended
replacement for A/B, qualified in isolated PP before any production decision.
PP host tradebot-preprod-01 now exists: 2 GiB / 60 GB, us-east-2a,
18.119.253.233 (not static), $12/month. Guest boot/restart baseline PASS after
correcting the initial launch-script format. No PostgreSQL application deployment
or migration exists yet. See PREPROD_VM_LAUNCH_2026-11-11.md.
One real collector; PP read-only preview may use production API, and database
tests require isolated writable data. No copies/snapshots or live write scope
are implied. Preserve all existing SQLite implementation and test evidence.

Fresh browser-SSH inventory: deployed d56b4a7; 46.397 GiB available disk,
1,299.80 MiB available RAM; main SQLite 5,323,907,072 bytes, WAL 4,517,712.
Services active, feeds stopped, storage guard limit_reached; retention/paid AI
OFF, cap 5120 MiB. /health ok does not mean collection works. Current operator
SSH /32 added with authorization, prior Lightsail rules/UFW preserved; direct
SSH still timed out, browser SSH worked. No application operation performed.

The user explicitly selected 2 GiB instead of the earlier 4 GiB suggestion.
Next: isolated PP runtime/PostgreSQL/application qualification under that host's
resource limits. No production data copied or extra market collector started.
AWS guidance preference HIGH. Project FREE/ACTIVE; no plan upgrade occurred.
main=production is intended policy, but deploy-tradebot.yml still gates
codex/lightsail-deployment; reconcile/test before any production release.

PR #9 closed/superseded. #11 open/ready; #12–#14 open/draft and unmerged, with
existing code checks passed at the single inspection. Storage/CI/PRT workers
were inactive. No worker restart or merge was requested. Keep current checkout,
AGENTS.md, unrelated 596-line roadmap edits and local data intact. This dated
direction supersedes older A/B resume instructions below. I7/Phase 1.75 OPEN.

## Historical resume pointers — superseded above

LATEST November7: checkpoint4 PASS, superseding BLOCKED entries below.
Frozen source6cf351aaa36a5f09ddb7b61dc554dfe4f80fcd5b,exactLinuxpush42407584696PASS.
Actual post-unlink application archive-history test EXECUTED/PASS;root82/0skips.
See PR9_CHECKPOINT4_LINUX_GATE_2026-11-06.md and evidence/pr9-checkpoint4-6cf351a-linux.json.
Requiredcase4.161s,allocation snapshots1507328/1458176B(notpeak),RSS79112KiB cumulative.
Integrated4000commit/archive/0errors,20cycles,save230ms/heartbeat299ms;scaledonly.
Nexteligible gate:retirement mutation/authorization review and bounded finalreadback
scaling,then finitecore/ledger,5GiBcapacity/outage,legacyverification/cutovercontrols.
No replacement deletionauthority approved;mandatoryfreshreadbackunchanged.
5GiBtarget/24GiBunqualifiedproposal/appliedlegacy5120MiBSTOP remain distinct.
Productionheld,PR9DRAFT,I7/Phase1.75OPEN. PreserveAGENTS/+596roadmap/localdata.

Historical status below retained as evidence,not latest result.


ACTIVE SCOPE: checkpoint4 history AFTER generated local raw retirement.
Storage implementationfrozen d35644c3608c0f086052b5d09276fd938ef0345e.
OwnexactLinuxpush42327631685 FAILbeforeprivilegedapplicationstage;3background
verificationchilderrors(genericArchiveHold),rootretirementtestNOTRUN.
ResultBLOCKED,notreplayFAIL/PASS. See PR9_CHECKPOINT4_LINUX_GATE_2026-11-06.md.
NeedapprovedexistingLinuxexecutionofexactcheckpoint4rootcase+exportSHA/resources,
notanotherunchangedfullrun. Local7run/6PASS/1rootskip doesnotprovepost-unlink.
PlanningwithdrawnextraCIbranchinvestigation;no newdiagnosticcodeadded;noCIbranch
merge/workflowedits. KeepseparateCIownershipandalllaterproductiongatesOPEN.
Allnewerstorage/history/cursor/admission/cryptoedits preserved;noreset/revert.
Productionunchanged/held;preserveAGENTS/+596roadmap/localdata.

Historical entries below remain evidence;this top scope governs resume.


November6 successor439c93b25ec05c04ef710afbfed5600ebd910f35:
PR9_BACKGROUND_VERIFICATION_CHECKPOINT_2026-11-06.md governs latest results.
Baseline13740c7 exactCI42316045831 PASS;successorpushCI42320474396 INPROGRESS
at one valid check,not PASS. Resume via notification/one status,no polling.
Generated fresh-B per-generation/dataset checkpoint4testsPASS;legacy untouched;
old shared-cursor manifests without newprogress HOLD for exact reconciliation.
Separate fullreadback diagnostic12objects/2011B/0.616s,21acks,save85.202ms,
heartbeat175.720ms,phaseRSS24805376B,workspace2553696B;corruption/cancellation
preservefiles.120sphase cap within180sfixture;not runtime/production policy.
434backendPASS/20platformskips,123controlsPASS/3platformskips locally.
CP3replacementauthBLOCKED effectiveimmutableauthority/policycontinuity;finalfresh
readbackunchanged. CP4archivedraw→actualapplicationhistoryreplayBLOCKED;existing
prepare_scope requirescurrentraw. CP5fullintegration/exactLinuxCI andCP6release
BLOCKED.5GiBslots target/24GiBproposal/appliedlegacy5120MiBSTOP distinct.
No cloudpermission/schema/write/productionchanges. PreserveunrelatedAGENTS/+596.

Previous qualified evidence remains below;do not confuse it with successorCI.


Frozen101921ee00d3e89a50d02c61569bd808ed268cec/pushCI42161684724 PASS. Read
PR9_CONTINUOUS_AB_CHECKPOINT_2026-11-05.md for consolidated bounded checkpoint.
428backend/14privilegeskips rootcovered,123controls/0skips,8incrementaltestsPASSroot.
ActualOFF→archive→enable(no collectorrestart)→B/A/B/A PASS,3/1/1progresscycles,
29ackticks,0HTTPtimeouts,onefeatureworker,3reader-held verifiedretirements.
Full225777-input bootstrap109.084s/1023041536Bpeak/RSS134516736B,legacyunchanged;
integrated4000committed/archived/0pending/errors,20pubs,save58.982ms/heartbeat329.957ms.
Opt-in persisted progress bindsraw/catalog/ledger/code,invalidateschanged/expired
proof,NEVER bypassesfinalfresh authenticatedreadback/protectedinputs/drain. Final
catalog notfitting8objects/original30s correctlyHOLDS;5GiBscaleNOTPROVEN.
Default0opt-in flag/retirementOFF/generated-only paths remain. Legacyfullquick/FK
checks preserved;durableactiveFKtable progress/failure/timeout/reaping tested.
ProductionverificationNOTPERFORMED,historical1790sphaseUNKNOWN. No newprodscan.
be6e121/CI42159636989 and4774946/CI42160233749 stayFAIL;normalcycle/stagebarrier
fixespassed;sanitizedfirstsavefailure metadata nowretained(no holdclear/retryincrease).
Resumecontinuouscapacity/controlplan:24GiB ONEaggregateproposal incl2x5GiBslots
(WAL/SHMincluded),core4GiB,working1GiB,TEMP0.5GiB,recovery1GiB,legacy5.000446GiB.
21.500446GiBassigned,2.499554GiBmargin. AllPROPOSED,notimplemented/qualified/applied.
Existing8GiB/64MiB/2MiB/OFF isfinite only;100kledger/corelogical/physical/reference
bounds stopscale. Approved2GiBfixturecannotprove5GiBslot;no largefixture wasrun.
Completelegacyverification andactualproductionpath/fence/identity/manual/aggregate
controls stillopen. Oldscope/expiry notusable. Conditionalprocedure forreview only;
no execution-readycutoverapproval requested. Productiond56b4a7 unchanged/collection
heldnormal5120MiBSTOP,retirement/paidAIOFF. No VM/cloudwrite/restart/install/deletion/
manualWAL/guardincrease. Privateexactselectedrecoveryevidence durableandpreserved.
PR9 conflict-free/DRAFT,I7/Phase1.75/freshness/cloudrecovery/visibility/sustained/
replay/RAGOPEN,RedisDEFERRED. PreserveAGENTS.md/+596roadmap/localdata,secrets.

## Read first and establish ownership

1. Read repository AGENTS.md.
2. Read [authoritative roadmap](INTELLIGENCE_REBUILD_PLAN.md), especially Current
   position and the latest dated entries; do not infer current state from old
   checked boxes further down the document.
3. Read [selected72h A/B policy](RETENTION_72H_AB_POLICY_2026-11-03.md), then
   [Nov3 recovery decision](STORAGE_RECOVERY_DECISION_2026-11-03.md).
4. For architectural changes, read CURRENT_DIRECTION.md and STRATEGIC_PLAN.md;
   reconcile their older text against dated user decisions and the master plan.
5. Verify repository /Users/jake/Documents/Trading_bot_Analytics, branch
   codex/phase1-75-retention-enable, HEAD, working tree and existing staged changes.
   Preserve all unrelated/uncommitted work. Do not create a branch/worktree.
6. Check the current execution owner before writing or operating production.
   Execution chat: [Test256-page checkpoint threshold](codex://threads/01a197ce-eabd-75b0-a991-d76b33c5a96b).
   The title is historical. Check current ownership before resuming the A/B work.
   Planning remains in the originating chat. A new session must take over rather
   than run a second concurrent implementation/production operation.

## November 4 policy clarification

A/B are collection buffers. Switch the active generation by 72 hours or sooner
at its size threshold. While B collects, archive and verify sealed A in the
existing Supabase bucket. Retire A after preserving needed inputs and protected
evidence and draining readers. Repeat in reverse. This supersedes the extra
72-hour local age gate and older sizing/test proposals below. Existing generated
results remain evidence for the policy they exercised. The worker's next task
is updating the retirement predicate, regression tests and overlap budget.

## Where we stopped / active work

Phase 1.75 and I7 remain open. The November 4 policy governs rotation and
retirement. Production collection is held on the legacy SQLite database.

Latest qualified exported candidate: **61e0008c59696168bdaa043fce6b88e5b22f6d19**,
[exact CI41738983997 PASS](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41738983997).
See [exported candidate result](AB72_EXPORTED_CANDIDATE_RESULT_2026-11-03.md).
Do not reset to7ffffb5/ecd8a03 or discard later integration changes.

All resumed items are implemented/tested on the exact export: separate lifecycle/
feature/history workers without collector/raw/retirement authority; ack-filtered
readers and verified protected core history; whole request/checksum/JSON deadlines;
sensitive-file/Git-blob/mode export validation. Runtime feature dispatch uses the
restricted worker factory. Exact-second mixed timestamp comparison was corrected;
new profile requires publication before AND after the simulated market boundary.

Linux exported backend340tests passed;6privilege skips all covered by root17raw
and33application tests with0skips. Exported controls112tests passed/0skips. Rebuilt
manifest matched the tested export exactly. Actual ApplicationStore qualification:
4000new committed,4002archived (includes2legacy backlog rows),0pending,0errors;
20real feature/baseline/ensemble/history jobs and20publications (10eachmarket).
Maximum save240.662ms,heartbeat303.473ms,feature102.500ms,history23.384ms;
40.126s whole operation;53075968B RSS and22375667B sampled whole workspace.
Original170/180s,512MiB/process,2GiB limits preserved; preparation/export included;
Linux process-family unlinked TEMP counted. This is scaled generated hosted-Linux
proof, not production volume/real cloud or live-boundary/freshness acceptance.

Intermediate880181f CI failed before jobs due workflow context scope; no trial ran.
f87fc4e/cc44c3f CI passed their recorded tests, but resource/boundary evidence gaps
were fixed before accepting61e0008. Keep original failures/evidence scope intact.
The new report preserves all corrections and the earlier sidecar fixture mistake.

Production readiness remains NOTPROVEN: actual schema/protected-reference and
production-volume audit/import; real private-cloud auth/RLS/concurrency; qualified
core/rate/burst/WAL/TEMP/recovery capacity; complete verification finish time under
unchanged limits; guarded live path/cutover/old-legacy write prevention and eventual
legacy decommission. Proposed16GiBnormal/21GiBmigration remain UNAPPROVED/unapplied,
review+72h/expiry+96h proposals, no extension of the expired old cap deadline.

Next work must address those exact migration gates. No production approval is
requested until the ONE consolidated procedure is execution-ready. Source61e0008
is the frozen qualified candidate; later evidence-only docs commits are not release
candidates and must not inherit its CI for deployment. No repeated polling,
unchanged qualification, automatic soak or production retry. I7/Phase1.75 OPEN.

## Successor readiness preparation after528e798

See [production readiness](AB72_PRODUCTION_READINESS_2026-11-03.md). Readiness successor
835e5075183231a9f5f4d8541b4f33f85c14eb8d, exactCI41745773184 INPROGRESS at the
single status check (not PASS). Resume via completion notification or one check,
no polling. Later evidence-only docs HEAD is not a release candidate. Fresh bounded
Nov4UTC/Nov3local metadata confirms legacy5323907072B main/45178880B allocatedWAL,
49806835712B filesystemfree;1826markets/18289snapshots/27743predictions/20links to8
observations. Raw/embedded-reference cardinalities remain unqualified. Existing
pinned SSH trust/key reused; no credential read/display or production changes.
Supabase connector metadata matches schema/keys/cursors/private market-raw bucket;
runtime HTTPread/write/concurrency still NOTPROVEN.

Existing maintenance controller now has generated-only transition rehearsal,
never production enablement: failed/ambiguous migration preserves stopped state
and durable new rows, no old-code rollback/restart. Default route unchanged;
512MiBrehearsalreserve/no128MiBexception; preflight included in originalenvelope.
Binding includes main/WALallocation/mtime; same-schema datachange blocks transition.
Importer over-bound preflight visits at most10001rows, never a full rawCOUNTscan.
Generated real ApplicationStore/verifier/control tests and bounded metadata tests
added. Exact successorCI/results are recorded in readiness completion addendum.

Unexecuted stress specification needs proposed40GiBworkspace/48hdeadline plus10GiB
free floor,>=2GiBavailableRAM,512MiB/process,max3processes/oneCPU. Neither measured
host meets prerequisites. Current2GiB/170/180s limits unchanged. No fixed production
ceilings derived:16/21unqualified;stress arithmetic31/36also unqualified. No expired
authority/deadline reused. Remaining streaming importer currently stops at10000rows,
128MiBaudit; actual production old-writer OS isolation/cutover route still missing.
No migration approval requested; one consolidated prerequisite package in report.

## Production: recorded state, not a fresh live audit

Bounded Nov3 checks recorded:
- VM tradebot-analytics-01,3.13.133.25,us-east-2; app /opt/tradebot.
- Runtime d56b4a73ad6f1a10ba2bac928087cd5d85c6a42a.
- API/ensemble/lifecycle services active, but collector running=false and
  storage_guard=limit_reached. The old API incorrectly says aggregate ok.
- Main5077.273MiB,WAL43.079MiB,total5120.353MiB; old guard5120MiB.
- Last recorded Coinbase/Polymarket receipts Nov2 around07:49UTC.
- Retention/paidAI OFF, production cleanup0. Missing events are not assumed backfilled.
- Latest complete maintenance attempt41364015738 failed with TimeoutExpired;
  verification1790.105s, interruption upper bound1790.802s, changed=false,
  recovery_failures=[]. No rollover application checkout or smoke occurred.
- Original deploy helper restored; claimed authority is consumed historical
  evidence. The old bridge review deadline passed; no extension is implied.
- SSH was tested successfully Nov3; no firewall change was needed that day.

No new production authority comes from this handoff. Do not restart collection,
retry the failed workflow or install helpers using expired/consumed bindings.

## Preserve completed work

- d56b4a7: deployed worker containment; did not make feature queries fast.
- fd90458: tested independent rollover/health application, NOT deployed.
- 93161cf /78bcaf0: historical qualified maintenance candidates; later attempt
  failed before application checkout. Do not treat them as current authority.
- b8f065b: verifier partial-result diagnostics, exactCI41702333233 PASS
  (253backend/112control tests); not installed in production by that milestone.
- 966e884: reconciled physical storage recovery NO-GO under old restrictions.
- 6d9edc3: generated retention tracing scope fix, exactCI41361239486 PASS;
  representative split-gate qualification did not start because feeds were stale.
- Earlier cleanup safety/performance evidence remains valuable, but representative
  revised retention and production cleanup are not certified. Preserve previous
  failures under their original policies.
- Price-query/index and publication work remains available; no source-time price
  index installation or fresh-prediction acceptance is claimed by this handoff.

## Next checkpoints: continue, do not redesign

1. Numeric aggregate normal/migration budgets: retained legacy DB, core,indexes,
   both72h generations (approximately144h peak raw),WAL,working/recovery space.
   User permits planning a revised guard; no numeric production value is selected.
   Do not repeat old5GiB feasibility STOP as if resizing is still forbidden.
2. Complete generated A/B/core prototype and correctness tests: unique identities,
   no-lookahead cross-boundary reads, crash-safe single active writer, reader and
   reference protection,72h aging, archive failure/full slots. Simulate time.
3. Qualify capacity/performance on bounded generated fixtures with exact CI.
   Distinguish scaled/local results from representative Linux evidence.
4. Deliver ONE consolidated exact-CI migration/release proposal with concrete
   guard(s), expiry, transition, interruption, verification and recovery behavior.
   Production changes require approval for that concrete procedure.
5. After an approved transition, prove collection,rollover,prediction freshness
   and verified72h retirement. Required sustained-lifecycle evidence remains open.

Short-window growth extrapolates0.76..0.97GiB/day; prior conservative input is
1.65GiB/day. These are NOT a measured full active-day average or segmented growth
bounds. Never hide legacy files or double-count reusable pages as physical space.

## Constraints and working practices

Supabase PostgreSQL stores structured history; private Supabase Storage holds raw
archives. No additional AWS S3 is required. No production copies/snapshots,VACUUM,
manual WAL operations,unverified deletion,durability reduction,infrastructure or
firewall changes,paidAI,trading endpoints or Phase2. No automatic cap extension.
Generated fixtures are allowed, never populated by copying production databases.

All new production guard/migration/deletion/restart operations remain gated on the
consolidated approval. Old one-use128MiB reserve and generated-only timing-policy
approvals are not blanket permission for different production work.

Commit/push completed tested milestones on the existing branch. Never stage
secrets,local DBs,whole-checkout changes or someone else's pending work. Existing
unrelated AGENTS.md and596-line roadmap edits must remain preserved. Planning
performed this documentation-only handoff; execution ownership remains unchanged.

No repeated CI/CD polling or unchanged trial retries. Report checkpoint, result,
exact commit/CI or measured evidence, production changes, blocker,next action and
specific approval needed. Use completion notifications or yield while waiting.

## Context limits

The full1590-page historical transcript reading remains unfinished. Do not claim
all original ChatGPT chats were read. Historical memory/reference documents do
not override current user decisions or the authoritative roadmap. A new session
should not reread the entire transcript to repeat already-recorded investigations.


## November 7 split-review handoff — supersedes PR9 branch ownership below

PR #9 is superseded by dependent draft PRs #11 → #12 → #13 → #14. Do not resume
implementation on the original `codex/phase1-75-retention-enable` branch without
reconciling these successors. Preserve that branch and all its unrelated edits.

- `codex/pr9-storage-foundation`: protocol/recovery foundations.
- `codex/pr9-application-integration`: actual application wiring, default OFF.
- `codex/pr9-archive-history`: archive-backed retrieval and diagnostic verification.
- `codex/pr9-release-controls`: CI/deployment controls and consolidated evidence.

The master roadmap contains links, order, local results and outstanding gates.
Review and merge each dependency before advancing its child; do not merge PR #9
as well. New functional changes belong in a scoped successor/appropriate owned
branch after current review, not a second monolithic PR. Coordinate changes to
shared files and restack children deliberately. Production activation, retirement,
limits and paid AI remain unchanged and require their existing separate gates.
