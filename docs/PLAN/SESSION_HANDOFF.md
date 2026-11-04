# Tradebot session handoff

Recorded November 3, 2026. This file is a compact restart index and evidence
snapshot, not another roadmap or new production authorization. Update it when
ownership/checkpoint changes; stale entries must be reconciled with Git and the
master roadmap before action.

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
   It is actively working as of this snapshot. The title is historical: its task
   is now the72h A/B/core prototype, NOT another checkpoint-threshold experiment.
   Planning remains in the originating chat. A new session must take over rather
   than run a second concurrent implementation/production operation.

## Where we stopped / active work

Phase1.75 / I7 remain OPEN. User selected at least72hours local raw retention,
A/B raw generations plus persistent structured core,with existing Supabase
archives. Selection/policy commit2470103 replaces48h as the future target;
production has not migrated or enabled retention.

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
