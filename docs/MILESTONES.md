## Retained B verifier timing passed before the trial07 rollout

The exact `65cfda8` query verified trial06 B in **192.321 seconds** with
**47.679 seconds remaining** under the existing 240-second limit. It read
all **50 raw objects / 24,896 raw events** and **56 structured pages /
27,528 rows**. The end-to-end read-only probe used the exact PP30 image
plus the isolated query and audit code. A catalog check confirmed the
full local index is still absent. The index migration passed exact
[Linux CI](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/45335944573)
and is included in [PR #211](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/211),
merged to `preprod` as `90a10bd`. No PP schema change, local removal,
or live activation occurred in the audit.
[Read-only evidence](PLAN/evidence/pp30-trial06-b-optimized-read-only.json).

Qualify the merged release and apply the index through the PP deployment
procedure with the collector off. Verify the exact installed index and
trial07's independent Storage and history scope before activation. The
post-migration read-only check still needs to meet the same timing gate.
The 30-minute collection windows and original per-seal limits stay fixed.

## Trial07 gate — qualify retained B before another live run

The elapsed candidate passed exact Linux CI. Before admission, qualify the
outbox page change on trial06 retained B with 56 structured pages and 50 raw
objects. The first page starts at the generation's own minimum qualifying
outbox ID; the payload query starts at the first selected ID. The additive
`(generation_id, id)` migration covers acknowledged rows as well as pending
ones. Generated PostgreSQL verified that the new query returns the same
ordered rows and hashes across both filters and byte-limited pages.

The PP audit is read-only and will use the existing catalog. It may establish
query-only performance but cannot prove the index's impact on that host.
Keep the 240-second deadline and require at least 30 seconds of measured
headroom before live trial admission. Preserve trial05 and both retained
trial06 generations. Neither the audit nor this code change authorizes any
retirement.

## November 23, 2026 CST — Trial07 uses two elapsed collection windows

The user clarified that a size trigger would shorten the collection window
as traffic varies. Trial07 therefore measures **30 minutes from durable A
collector admission** and **30 minutes from the actual A-to-B switch**. The
clock uses the persisted database timestamps. Log relation size, raw events,
archive objects and structured pages and bytes at seal. Allocation is evidence
for this trial. Existing disk, occupied-slot, and outbox safeguards still hold
when their own conditions are met.

A keeps its archive and exact protected history through verification while B
collects. Repeat for B with fresh A. Each final verification still has 240
seconds, and each seal-to-removal interval still has a 30-minute deadline.
Each removal needs its own separately announced verification window of at
most 295 seconds. The trial07 confirmation already covers both windows.
Fresh A must persist a Polymarket quote before durable OFF. Then finish its
structured drain, seal it, verify its archive and history, and keep its raw
partition attached.

The prior 32 MiB candidate is isolated in draft
[PR #210](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/210).
It was never deployed. Its [exact check](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/45304028083)
failed because a new permit test skipped inside a phase that rejects skips.
The elapsed candidate's permit test accepts the existing isolated Linux CI
database and still exercises actual PostgreSQL on a disposable cluster locally.
A fresh read-only PP check confirmed PP30 deployed with collection OFF.
Trial05 A/B and trial06 verified B and terminal A remain attached with their
writers OFF. Trial07 has no generation or writer yet. No production size or retirement policy changes.

## November 23, 2026 CST — Retained B timeout identified on PP

The bounded read-only check stopped in the local page-size query with SQLSTATE
`25P04`. The outbox coverage query took 1.532 seconds, and PostgreSQL canceled
the next query when their transaction reached the unchanged 3.5-second limit.
Zero requests reached Supabase. The larger live verification holds separately
at 54 of 56 pages under the unchanged 240-second gate.

The deployed live controller uses official market windows and rejects a size
override. The size-triggered live rehearsal needs a dedicated PP profile,
a fresh isolated origin and its own verification and removal authority.
Trial05 and trial06 B stay preserved. Both collectors were OFF after this
diagnostic. [Diagnostic evidence](PLAN/evidence/pp30-retained-b-local-transaction-hold-2026-11-23.md).

## Retained B local query timing is ready for a reviewed diagnostic

The local-only diagnostic records the reader, writer, attachment, manifest,
outbox coverage, page-size and payload query phases separately. A canceled
query retains its fixed phase and SQLSTATE without exposing database
credentials, statement text or row payloads. Timing the original two page
queries preserves their existing limits and selection behavior.

Generated PostgreSQL 17 read 500 rows from 27,528 acknowledged records and
validated 50 manifest entries in the same local diagnostic. A forced
cancellation was correctly identified as the page-size statement with
SQLSTATE `57014`. The 29 focused unit and lifecycle tests passed. The
original PP cancellation still has no statement attribution. This change
was qualified offline and did not run on PP or Supabase.
[Isolated qualification](PLAN/evidence/pp30-retained-b-statement-diagnostic-isolated.json).

## November 23, 2026 CST — Trial06 completed both switches; B retirement held

PP30 admitted trial06 at 3:44:09 p.m. CST. The live collector moved from A
to B at 4:15:25 and from B to a distinct fresh A at 5:00:29 on the original
session. Each outgoing slot recorded both required Polymarket markets.
The first observed quotes across six boundaries arrived 64.0–125.2 seconds
after each boundary. Storage switching passed. I7 rollover freshness
remains open.

- **Original A retired.** The independent Supabase verifier matched 39
  raw objects and 42 structured pages in 189.111 seconds while B collected.
  Local removal took 342.177 seconds from seal. Dashboard history and
  deterministic replay matched after physical removal.
- **B held.** The archive worker verified all 50 raw objects and all 27,528
  structured records were acknowledged. The separate mandatory final
  verification completed 54 of 56 structured pages when the 240-second
  operation deadline expired. The one pooled reader connection took
  0.371 seconds to establish. No destruction began, and all 24,896 B raw
  events remain attached.
- **Fresh A wrote live data.** Its Polymarket quote count rose by 32 between
  samples within the B verification interval. At durable OFF, it held
  5,084 raw events including 59 Polymarket quotes and 5,523 acknowledged
  structured records. Fresh A remains unsealed and attached.

Both collectors and both trial06 archive workers were verified OFF. All
structured queues were drained. Trial05's two local fingerprints matched
the predeployment record. Dashboard, prediction history and SSE passed all
85 sampled checks. Dashboard returned HTTP 200 after OFF. B post-removal
history was not performed because B remained attached.

**Next gate:** profile and qualify the larger 56-page workload before
another live attempt. Connection reuse already reduced setup to one
connection. The B hold spent 24.282 seconds on the in-window inventory,
30.482 seconds on raw local comparison, and 13.844 seconds on the final
structured comparison. These are separate measured local spans; nested
cloud timings must not be added together. Target redundant local work
while preserving fresh authenticated comparison for every row, exact
coverage, and the unchanged 240-second operation cap. No further live
attempt or hosted configuration change was started.

[Full trial06 outcome](PLAN/evidence/pp30-trial06-live-result-2026-11-23.json).

A separate read-only retained B first-page diagnostic stopped in local
reconstruction with PostgreSQL `QueryCanceled` after 3.577 seconds.
The attempt made zero hosted page requests. It did not isolate the local
statement or establish an exact-revision timing for Supabase. The next
diagnostic should time the local guards and page query separately before
attributing this hold to hosted SQL. B remained intact.
[Diagnostic evidence](PLAN/evidence/pp30-trial06-retained-b-first-page-hold-2026-11-23.json).

## November 23, 2026 CST — Trial06 A verified and retired while B collected

PP30 admitted trial06 at **3:44:09 p.m. CST**. A switched to B at 4:15:25
on the original collector session after the two required Polymarket
markets. The independent Supabase reader matched all 39 raw objects
(19,018 events) and 42 structured pages (20,874 rows) in **189.111 seconds**
with **50.889 seconds** of headroom. A single physical connection served
42 fresh read-only transactions. The longest page took 3.658 seconds.

B persisted 27 Polymarket quotes between read-only snapshots taken within
the verification interval. The verifier measured 1,554 new B rows while
running. A's local partition was removed at 4:21:07, **342.177 seconds**
after sealing, and its dashboard history and deterministic replay matched
after removal. Trial05's older A and B remain outside this scope.
B is active. Its two full markets, retirement, fresh A and final OFF
checks remain in progress. Production collection stays OFF.

[First retirement evidence](PLAN/evidence/pp30-trial06-a-retired-2026-11-23.json).

## November 23, 2026 CST — PP30 deployed and trial06 ready with collectors OFF

[PR #208](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/208) bound
the attested controller to the release profile. An outdated CI pin was
updated to match the identity workflow. The exact push then timed out in
the shared PostgreSQL lifecycle phase. The existing terminal archive
module now runs in its own bounded CI child, preserving every case and
the overall qualification deadline. The controller bundle stayed identical.
Merged source `ad11d85` passed
[exact-release CI](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/45268743428).

The first PP30 deployment stopped at the existing RAM floor before
consuming its permit. After a bounded, reversible PP firmware-service
pause, the same source and permit passed all 11 generated deployment checks
in [CD Preprod](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/45270349587).
The firmware service was restored. Trial05's two partitions, exact raw
and outbox fingerprints, and manifest and checkpoint digests matched
before deploy, after deploy, and at ready-off.

Trial06 has a new empty A and two scoped archive workers ready. The admin
freeze confirmation covers both 295-second windows. At ready-off, both
collectors were disabled and neither window had opened. The planned
admission targets the 3:45 p.m. CST market boundary. Production remains
on `d56b4a7` with collection OFF.

[PP30 readiness evidence](PLAN/evidence/pp30-trial06-ready-off-2026-11-23.json).

## November 23, 2026 CST — Trial06 isolated candidate for live requalification

The retained trial05 readback passed with 65.580 seconds of headroom. Trial06
is the isolated follow-up on the same PP host. It uses a new empty A and
separate authenticated Storage and structured-history identities. The controller
disallows restarting retained trial05. Preparation checks the prior A/B
attachments, exact seal and writer, and protected evidence before creating
the new generation. Trial05 and earlier archives remain available.

[PR #207](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/207)
passed exact candidate CI and merged to `preprod`. The new controller was
installed code-only and passed the dedicated identity workflow. Hosted
trial06 synthetic write and independent authenticated readback passed for
structured data and Storage. All 18 Storage permission checks passed, and
the prior policy fingerprints, object references and receipt counts matched.
PP has restored generated mode and both collectors remain OFF pending the
release. [Qualification evidence](PLAN/evidence/pp30-trial06-cloud-and-controller-2026-11-23.json).

The trial06 retirement verifier requires connection reuse and a fresh read-only
transaction on each page. The 4-second page, 240-second final readback and
30-minute seal limits remain fixed. The operator confirmed both administrative
freeze windows of at most 295 seconds. Each window opens only on its separately
announced, exact sealed-generation authorization. Both collectors are currently
durably OFF. The trial06 live run remains pending.

The live checkpoint requires two Polymarket markets in each outgoing generation,
full raw and structured verification before each partition is removed, Polymarket
persistence on the successor, and historical reads after removal. End with PP
OFF and fresh A preserved. Production collection stays OFF.

## November 23, 2026 CST — Trial05 retained A passes read-only connection reuse

The PP29 retained readback verified all 52 structured pages (25,872 rows)
and all 49 raw objects (24,044 events) in **174.420 seconds** against the
unchanged **240-second** operation cap. The slowest structured readback
was 2.855 seconds under the 4-second page cap. The run left 65.580 seconds
of operation headroom and charged 103 requests including preflight and
44,948,463 logical bytes. Fifty-three read-only transactions used two
physical connections. The exact A seal, both attached partitions and
both empty structured queues matched after the test. Both collectors
remain durably OFF.

The previous live verifier held at 239.641 seconds with 51 completed
pages while B was writing. The observed 65.221-second difference
combines connection reuse and different runtime conditions. This is
retained-workload evidence. It grants no retirement authority and
leaves the trial05 live result unchanged.

The test used the existing PP29 read-only audit and exact scoped
credentials. Two setup failures were corrected before the full timed
workload. The original operation, request and byte caps stayed fixed.
The one-use trial05 scope now contains retained A and B, so the next
live attempt needs a clean isolated scope and its own destructive
verification windows. Use one authenticated reader connection with a
fresh read-only transaction per page in that attempt. Preserve trial05
and the earlier trials, record the actual live margin for both seals,
and prove history following physical retirement.

[Full readback evidence](PLAN/evidence/pp29-trial05-retained-a-reuse-2026-11-23.json).

## November 23, 2026 CST — Trial05 A switched to B, retirement held

PP29 admitted the single trial05 collector at 1:44:09 p.m. CST. The same
session persisted through A's two 15-minute Polymarket markets (1:45–2:00
and 2:00–2:15) and switched to B at 2:15:20. The first observed quote for
the 2:00 market arrived 66.46 seconds after its start. Rollover latency and
continuous collector ownership are separate acceptance results.

A sealed with 24,044 raw events and 25,872 structured acknowledgements.
Its worker verified 49 raw objects. While B persisted new Polymarket
quotes, A's independent final verifier opened the single 295-second
freeze at 2:18:34. The verifier held at 239.641 seconds during structured
readback with 51 of 52 pages completed and 0.359 seconds remaining. The
receipt reports `archive_limit`, 102 requests and 44,947,056 logical bytes.
The inventory identified 52 pages. The readback consumed 138.801 seconds
in the structured phase, including nested connection/query accounting.
The read-only pre-retirement history check replayed original inputs.

A remained attached. PP was durably stopped at about 2:23 p.m. with B
attached, 5,690 raw events and 6,149 structured acknowledgements. Both
outboxes had zero pending records. Production's collector remains OFF at
`d56b4a7`, and both scoped PP workers were stopped. B's complete market
pair, fresh A, the second verification window and post-removal history
were not reached. No partitions were deleted. Trial04 remained outside
trial05's scope.

The observer saw 466 live API samples with zero errors and a maximum of
465.612 ms. All 38 dashboard, prediction-history and SSE checks passed.
The chart had data in 35 of 38 checks. The dashboard still returned
HTTP 200 after stopping PP.

**Next gate:** qualify the existing PP-only option for a single authenticated
reader connection across the entire retained 52-page workload. Keep each
page in its own fresh read-only transaction and preserve the 4-second page,
240-second operation and 30-minute seal limits. The failed run opened 51
physical connections totalling 16.292 seconds. That is an optimization
target, not a measured savings claim. Ten session safety, six accounting
and three canonical-readback tests passed offline. The full retained
workload must show margin before any fresh live attempt. Preserve
mandatory independent readback, references and reader drainage, and leave
trial05's original seal-deadline result recorded as held.

[Sanitized outcome and phase timings](PLAN/evidence/pp29-trial05-retirement-hold-2026-11-23.json).

## November 23, 2026 CST — PP29 trial05 ready with collectors OFF

[PR #205](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/205)
isolated trial05 and carried the PP28 lease watchdog fix forward.
[PR #206](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/206) bound
the verified controller to the PP deployment profile. Source `74f2aa2`
passed [exact CI](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/45246319676).
[CD Preprod](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/45247660239)
deployed `v0.2.0-pp.29` and passed all 11 generated acceptance checks.
The temporary deployment runner deregistered, and PP firmware service
settings were restored and reverified.

Trial05's restricted Supabase writer and independent reader passed exact
synthetic structured and private-object readback and cross-origin denial
checks. Trial04's 659 local raw rows and 705 acknowledged outbox rows
matched their before/after fingerprints. Its 706 hosted receipts and
revisions were preserved. Both trial03 partitions remain attached.

PP is in `ready_off` with an unused A, zero trial05 local raw and outbox
rows, and both scoped workers running idle. Production's collector was
independently verified OFF at `d56b4a7` and will stay OFF. The remaining
admission prerequisite is trial05's confirmation that administrators and
privileged automation will leave each sealed generation's Supabase objects,
history and access policies untouched during its announced verification
and retirement window. Neither window has opened.

After confirmation, start PP ahead of a Polymarket boundary. Require two
complete 15-minute markets in A and then in B. Count each sealed generation
as passed only after its authenticated Supabase verification, local
retirement within 30 minutes while the successor continues collecting, and
post-retirement dashboard history checks. End with PP durably OFF and drain
the final fresh A without removing it.

[Sanitized readiness evidence](PLAN/evidence/pp29-trial05-ready-off-2026-11-23.json).

## November 23, 2026 CST — Trial05 isolated scope and production collector off

Production's collector was explicitly disabled at the approved service fence.
The deployed production source remains `d56b4a7`. The operator verified both
collector flags were false. Production collection is to stay OFF after the
rehearsal, pending the separately reviewed PostgreSQL cutover.

Trial05 uses a new origin with distinct structured SQL and private Storage
principals. Its candidate inherits the PP28 lease watchdog fix. Local
preparation checks the exact stopped trial04 writer, attached A, preparation
and admission checkpoints, 659 raw row identities and hashes, and all 705
acknowledged outbox entries. It binds that evidence to trial05 and makes no
changes to trial04. Retained04 is excluded from new collector entry and ON.

Generated PostgreSQL 17 tests passed trial05 A → B → fresh A, both fresh
readback and independent successor-write retirement checks, and trial04
isolation. Hosted preflight found 12 RLS history tables, a private raw bucket,
706 retained trial04 receipts and revision payloads, and zero trial05 roles
or Auth users. Hosted identities and verification remain pending. PP remains
in generated mode with its live collector off.

## November 23, 2026 CST — PP28 live preflight found no unused trial scope

The temporary production fence was authorized for a fresh PP28 run. The
read-only PP preflight stopped before installing it. The deployed controller
allows trial04 as its only writable qualified trial scope. The earlier trial
scopes are retained or already populated. Trial04's writer is OFF at epoch 3,
with its prior admission recorded, 659 raw events and 705 outbox records
retained. Its preparation checkpoint belongs to PP27 source `17ba31e`.
PP28's preparation requires an unused epoch-1 A, no event or outbox
rows, and a checkpoint bound to its exact source. Its independent cloud
reader and writer proofs also bind the exact source, image and anchor.

A fresh rehearsal requires an isolated trial scope that preserves trial04.
Both collectors' configuration and the Supabase policies stayed as found.
PP remained in generated mode with zero enabled live writers. No rehearsal
authority was issued, and neither verification window or deletion ran.

## November 23, 2026 CST — PP28 deployed and validated in generated mode

[PR #204](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/204) merged
into `preprod` as `88da36a`. The exact
[merge CI](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/45238401404)
and [release publication](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/45239533391)
passed. [CD Preprod](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/45240092424)
deployed `v0.2.0-pp.28` and passed all 11 generated acceptance checks.
The deployed API image was independently matched to the CD record, and the
private dashboard returned HTTP 200. The deploy permit was consumed and
the temporary private runner deregistered.

The exact PP27 transition returned to generated mode before deployment.
PostgreSQL preserved trial04 A with 659 raw events, 705 structured
acknowledgements and zero pending records. Both trial03 partitions remain
attached and verified. No live PP writers are enabled.

**Fresh live rehearsal is held before ON.** Production remains on
`d56b4a7` with its original collector configuration. Read-only checks before
and after deployment confirmed it is enabled and stopped by its legacy
storage guard. The current plan requires durable sole ownership for PP
collection. Neither the production configuration nor `main` changed.
Live A → B → fresh A, independent Supabase verification and timely
physical retirement are still open. Both verification windows are unopened.

[Sanitized deployment and preservation evidence](PLAN/evidence/pp28-deployment-2026-11-23.json).

## November 20, 2026 CST — PP27 deployed; fresh trial04 ready with collection off

[PR #202](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/202) and
[PR #203](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/203) merged.
The PP27 release binds exact preprod source `17ba31e`, exact push CI
`44869270426`, verified controller `486ad278` and the existing PP VM.
Trial04's fresh SQL and Storage identities passed exact authenticated
synthetic readback and denial checks against the older scopes. Existing
policy, grant, role and receipt/revision fingerprints matched.

The first CD attempt `44869823304` held before migration on the 1 GiB
memory floor and left its permit unused. The reviewed, temporary pause of
idle fwupd yielded passing memory samples for one retry. [CD retry
`44870088476`](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44870088476)
passed generated acceptance with the guards unchanged. fwupd was restored
and persistent enablement was unchanged. PostgreSQL was preserved.

The source/image-bound trial04 proofs were installed and ENTER returned
`PP_LIVE_READY_OFF`. A is empty and there is no collector session or lease.
Both recurring workers are ready with retirement off. The private dashboard
and SSE respond and the empty, OFF profile reports missing live feeds.
A read-only snapshot after deployment and ENTER matched both attached
trial03 partitions and their stopped writer. Production was not changed.

Final retirement uses the qualified indexed receipt lookup and fresh
connections. The existing recurring writer's separate connection reuse
remains enabled. Do not start the new live rehearsal until the two fresh
trial04 administrator mutation-free windows can be honored. Trial03's
completed/expired windows do not carry over. When ready, establish the
production collector fence and use a single finite quarter-aligned session.
Live A → B → fresh A and both timely retirements remain unproven.

[Sanitized PP27 deployment and ready-OFF evidence](PLAN/evidence/pp27-trial04-ready-off-2026-11-20.json).

## November 20, 2026 CST — Indexed fix merged; fresh PP rehearsal preparation

PR #201's existing-fixture CI failure was caused by a captured default origin.
Resolving the default at call time passed the exact PostgreSQL 17 regression.
The PR merged as `c278be7` and [merge CI](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44865255705) passed.

Independent readback of trial03 B verified 25 raw objects (12,301 rows) and
13,210 structured rows across 27 pages in 97.899 seconds. The slowest page
was 2.627 seconds, using the existing receipt index and fresh connections.
PP then returned to its generated-data profile with the collector and cloud
workers off, keeping PostgreSQL in place. Before/after snapshots match for
both retained partitions and the writer record. The prior live trial
remains failed at retirement.

The separate trial04 scope uses the same PP VM and a fresh A anchor.
Its admission preserves both retained trial03 partitions. The collector will
run only after exact Linux CI, controller qualification, explicit cloud
role/policy checks, generated/OFF deployment proof and the production
collector fence. The retirement verifier uses the index with fresh connections.
Per-leg windows, fresh readback and retirement checks remain required.

[Retained B readback and host preservation](PLAN/evidence/pp26-retained-b-independent-readback-2026-11-20.json).

## November 20, 2026 — PP26 A read-only timeout reproduced and indexed readback passed

The retained A audit used reader-only credentials, with both PP partitions
attached and every collector off. The original rank lookup and fresh connection
per page passed all 50 raw comparisons, then failed on the first structured page.
The client recorded `history_projections` and the hosted PostgreSQL log reported
`25P04` (transaction timeout) at 20:54:16.213 UTC. The latest-receipt rank lookup
had consumed 2.435 seconds on that page. This establishes the diagnostic
failure, independently of the missing details from the original live attempt.

Changing only the receipt lookup to the existing checked index passed all
50 objects and 26,480 structured records across 53 pages. Total measured work
was 212.801 seconds, the slowest structured page was 3.264 seconds and the
slowest indexed latest-receipt lookup was 0.129 seconds. The 240-second operation
and four-second page limits stayed in force. Local wait samples reported no
lock wait during either run. The read-only audit does not exercise concurrent
opposite-slot writes, permit issuance or partition removal.

The indexed query with a reused connection failed on structured page four
at 4.650 seconds. The longest exact-revision span reached 3.217 seconds and
the final error surfaced at connection release. A single comparison does
not isolate reuse as the cause. The selected live verifier candidate keeps
fresh connections and exposes an explicit PP trial-only indexed lookup using
the existing checked index and exact receipt comparisons. A fresh database
snapshot confirmed both trial03 partitions remain attached and verified,
with unchanged row counts and a durably stopped collector.
A fresh live rehearsal must preserve trial03 and qualify its own independently
scoped writer, reader, release and retirement authority. Production and both
retained trial03 partitions were untouched by these audits.

[Sanitized timing and query-wait evidence](PLAN/evidence/pp26-retained-a-diagnostic-2026-11-20.json).

## November 20, 2026 — PP26 B archived during recovery; live retirement still open

With PP's collector durably off, the exact Linux CI-passed B recovery helper
sealed B at **19:00:04 UTC**. All **12,301 raw records** verified in **25
Supabase Storage objects** at **19:01:07 UTC**, 63.36 seconds after seal.
All **13,210 structured records** remained acknowledged with zero pending.
The archive worker was stopped and a fresh database check confirmed A and B
both verified, still attached and never retired. The collector remained off,
with no active session or lease. This was maintenance of the stopped trial,
so the live B → fresh A handoff and retirement deadline remain unproven.

The retirement command now preserves the failure phase, sanitized timings,
budget use and SQLSTATE when present. The original failure remains unknown.
For the next read-only verifier run, correlate phase evidence with PP
PostgreSQL wait samples and Supabase query and connection metrics. Keep
timing and wait data separate from row payloads or credentials.

[Sanitized recovery evidence](PLAN/evidence/pp26-retained-b-archive-2026-11-20.json)
and [exact Linux CI](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44797052857).

## November 20, 2026 — PP26 A→B/archive passed; retirement failed, recovery in progress

The recovery candidate adds a B-only seal operation pinned to the failed
trial, observed counts and durable OFF state. Seven focused PostgreSQL
tests passed locally, including a generated fixture at the observed raw
and structured row counts. The candidate also preserves the verifier's
failure stage and timing on future attempts. This does not reconstruct
the original failure. Linux CI and the PP B archive remain pending.

A switched to B at **18:15:07.207508 UTC**, with the original collector session
still running. A covered both complete official markets and sealed **24,649 raw
records**. All **50 raw archive objects** verified by **18:17:00.381174 UTC**
(113.174 seconds after seal); all **26,480 structured records** were acknowledged.
Supported retained-A history and original-input deterministic replay passed.

The first read-only inventory launcher failed at its 12-second supervisor; Docker
exit 137 and an empty-output parsing bug were recorded. A reviewed, six-test
correction aligned inventory supervision with the already-selected 240-second
verifier budget, without changing final retirement limits. Inventory then passed
in **19.882 seconds**, examining all 53 structured pages; this does not itself
authorize retirement.

The first announced final-verification window was **18:25:44–18:30:39 UTC**.
The retirement attempt returned a native nonzero result after about 249 seconds;
the wrapper discarded its detailed HOLD because the native response lacked the
expected `stage` field. The exact failure reason/phase remains **unproven**.
A fresh database check confirmed A remains verified, attached and not retired.
**No DROP occurred. The window is consumed; no blind retry is authorized.**

Root explicitly stopped PP after this failure. At **18:31:37 UTC** durable OFF
was verified with NULL session and lease. B retained **12,301 raw records**, with
**13,210 structured acknowledgements and zero pending**. Both recurring workers
were stopped. Production's prior service setting was restored: same legacy
revision, enabled but storage-guard-held collector. No production data changed.

Next work is diagnostic preservation and a narrowly qualified failed-trial03 B
sealing/archive path; the existing final-A helper cannot accept this failed chain.
B raw is not yet archived. Both partitions remain local. No B→fresh A, retirement,
or complete freshness PASS is claimed. Coinbase source-age excursions were kept
separate from Polymarket continuity. Phase1.75/I7 remain open.

[Sanitized outcome and recovery evidence](PLAN/evidence/pp26-live-retirement-hold-2026-11-20.json).

## November 20, 2026 — PP26 live rehearsal admitted; rotation not yet proven

Actual PP admission succeeded at **17:44:08.840017 UTC** on deployed `08ea1b9`.
Trial03 uses the same initial A `15a239c9-2f9b-4bdc-bd89-7cd1e2812f45` and
session `142a0c69-147d-4b90-8483-ac6d9773e7f9`; its unchanged lease expires
**19:34:08.840017 UTC**. Production is temporarily collector-fenced/read-only;
restore its prior setting only after independently confirmed PP durable OFF.

Polymarket crossed the 17:45 market boundary without stopping the session:
discovery at +11.0 seconds, first official quote receipt at +22.252 seconds.
The supported dashboard/history/chart/SSE checks advance. Coinbase source-age
excursions exceeded 30 seconds while Polymarket continued; forecasts correctly
abstained with `reference_price_not_fresh`. This is not a full freshness PASS.
A separately coordinated 500-row local history query returned in 0.816 seconds.

At this in-progress checkpoint A remains collecting, with no retirement yet.
A's two full official markets are 17:45–18:00 and 18:00–18:15. B must likewise
cover two full official markets: quarter alignment can make its elapsed duration
longer than 30 minutes. Each retirement deadline remains actual seal +30 minutes.
Root owns each announced final verification window, exact retirement, history
parity, final OFF/drain and production-fence restoration. No cache purge is needed.

[Sanitized admission/observation evidence](PLAN/evidence/pp26-live-admission-2026-11-20.json).

## November 20, 2026 — PP26 deployed; existing trial03 proofs rebound

PP26 `v0.2.0-pp.26` is deployed in PP: source `08ea1b9`, image
`sha256:6044c859…`, generated-only CD `44783463740` **PASS**. Exact merge-source
CI `44782153188` and publication `44783320663` passed. PRs #199 and #200 are
merged. This supersedes the earlier pending-deployment/rebind notes below.

The CI history remains explicit: profile source `579fea9` passed exact push
`44780471640`; PR run `44780508098` attempt 1 failed a dashboard Node subprocess
at its existing 10-second timeout. Its cause remains unproven. One failed-jobs-only
rerun, attempt 2, passed; the original failure is preserved and no timeout was raised.

The completed local authority rebind preserves trial03 origin
`pp-live-pp-trial-20261119-03`, initial A `15a239c9-2f9b-4bdc-bd89-7cd1e2812f45`,
and cloud qualification source `413aac3`. Both pure proof byte hashes are unchanged;
the original PP25 bytes remain in the dated root backup. The authorities now bind
the actual PP26 source/image and installed controller `895d252f…`. Rebinding
creates no collector authority. Read-only cloud inventory still contains only the
known synthetic fixture: one receipt, one revision payload and one 210-byte object;
that catalog check did not repeat authenticated object readback.

At this checkpoint, no collector ON or live-trial success is recorded. Next are
actual LIVE_READY_OFF, a fresh production fence and finite ON authorization/admission,
then two complete official 15-minute markets per leg. A → B → fresh A archive,
both physical retirements, and independent before/after historical readback parity
remain unproven. [Sanitized deployment/rebind evidence](PLAN/evidence/pp26-deployment-rebind-2026-11-20.json).

## November 20, 2026 — PP26 controller identity verified

PR #199 merged as `e16d7b8` after exact-source and PR Linux CI passed
(`44778846799`, `44778892704`). The installed controller `895d252f…`
passed dedicated identity workflow `44780241320`, with `database_changed=false`.
This profile binds that observed installation; it does not start collection.
PP remains on the PP25 generated application, with live collection OFF.
Next: exact profile CI and merge, publish/deploy PP26, then rebind existing
trial03 proofs and perform the authorized live rehearsal. No new cloud roles,
credentials or trial data are created by this profile change. Production is
unchanged. A → B → fresh A archive/retirement acceptance remains unproven.

## November 20, 2026 — cache audit and release reconciliation

PR #198 merged into `preprod` as `4a2112c`. Its source and PR CI passed;
the subsequent merge CI `44744191572` failed four Docker Compose configuration
renderings at their existing 5/10-second deadlines. No production or PP release
is qualified by that failed run. Diagnosis is in progress; do not rerun blindly
or weaken application latency gates.

The cache audit found 52.38 GiB free disk and approximately 1.23 MB of reclaimable
build cache. No cache purge or database deletion was performed. The relevant
entry failure was the available-memory prerequisite while applications were
still running, addressed by #198's reviewed quiesce-before-headroom sequencing.
A fresh read-only reconciliation confirms PP25 source `2ea5b03`, controller
`16f7e3ec`, generated-restored state, and healthy PostgreSQL/API with the four
application services running. Trial03 collection has not been started.

PP26 preparation additionally found a crash window after replacing both cloud
release bindings but before recording completion. The implemented pending-update guard blocks ENTER/ON until the binding
transaction completes while preserving OFF, recovery and read-only proof checks. The offline rebinder keeps both original proofs unchanged,
checks all writers/sessions/leases are off and all trial03 records are absent,
and retains exact predecessor bindings. No rebinding or PP26 installation has
occurred. The test-only Compose renderer now terminates its entire owned process
group on timeout and reports sanitized version/timing diagnostics; the original
5/10-second limits remain unchanged, with no automatic retry. The specific
GitHub runner hang remains unexplained. Next: exact successor CI, then PP26.
Local qualification: 294 deployment-control tests ran successfully (14 platform
skips), 56 CI-control tests passed, and 44 offline operations tests passed,
including crash-after-both-replacements against the actual admission guard.
The live A → B → fresh A archive/retirement acceptance remains unproven.

## November 20, 2026 — PP25 recovered; permanent transition sequencing fix

PP25 generated deployment passed. Two live-ready entry attempts held before
collector ON. A complete read-only check isolated the host memory prerequisite:
1,072,451,584 bytes available,1.23MiB below the unchanged1GiB threshold; profile,
PostgreSQL,filesystem,exact runtime and API/operator checks passed.

The temporary firmware maintenance has been restored (earlier unconfirmed
restoration remains evidence). Exact reviewed application-only quiescence then
allowed the installed controller's normal LEAVE to pass: generated dashboard/API
restored, all collectors OFF, PostgreSQL not recreated. No production fence or
live observer started. The original failed entries remain failures.

The code candidate validates host identity,disk,owned runtime and durable OFF,
then stops/proves the owned applications quiescent before checking the **same**
1GiB RAM/10GiB disk startup prerequisite. Ordinary deployment admission is
unchanged. Recovery is performed once with its existing fresh180-second budget;
pre-mutation failures never call OFF/stop/recreate. Fixed original failure phase
and code are retained independently of recovery status. No guard is lowered.

Local validation:284 deployment-control tests passed (14 platform skips),56
CI controls passed; independent review covered the mutation boundary. Exact
successor Linux CI and controller release remain required. A→B→freshA with
live verified retirement and history remains unproven; Phase1.75/I7 OPEN.

[Recovery evidence](PLAN/evidence/pp25-quiescent-recovery-2026-11-20.json).

## November 20, 2026, 4:04 a.m. CST — PP25 deployed; live entry recovery pending

PRs #196/#197 merged into `preprod`; source `2ea5b03` passed exact merge
CI44667808289. Publication44668599488 and CD44668724097 passed for
`v0.2.0-pp.25`. Actual image is `sha256:5ac2350c2cf6a25b76ae308c593088d02696c870698dee3b9ae79e91d513ceec`.
API/SSE/operator/schema/migration/generated-data checks passed. This is
**generated-only deployment acceptance**, not live rotation acceptance.

Fresh trial03 proofs bound initial A `15a239c9-2f9b-4bdc-bd89-7cd1e2812f45`,
but ENTER failed before ON. Its authority was consumed and the transition
journal is `recovery_unproven`. A subsequent read-only check reproduced
`insufficient_host_headroom`; the original generic receipt does not establish
its exact initial failing stage. No live observer or production fence started.

After a session time gap, fresh memory inventory at10:03:42UTC showed
1,098,579,968 bytes available against the unchanged1,073,741,824-byte guard.
Idle fwupd used about38–43MiB. A bounded temporary pause/recovery is under
review, not yet applied. No cache purge, guard increase or database recreation.
Do not reuse expired authority or stale measurements. A→B→freshA with concurrent
verified retirement and dashboard history remains unproven; Phase1.75/I7 OPEN.

[Exact deployment and hold evidence](PLAN/evidence/pp25-deployment-entry-hold-2026-11-20.json).

## November 19, 2026, evening CST — PP25 controller identity qualified

Controller `16f7e3ec…` was installed from exact-CI-qualified `bd842fc` without
creating authority or changing PostgreSQL. Dedicated identity workflow
44666918397 passed at `6f53f5d`; this profile binds its observed result.
Trial03 host credentials were confirmed absent by a metadata-only check and
then staged create-only (10 files), without starting collection or cloud writes.
Existing trial03 Supabase qualification remains attributed to source `413aac3`;
no roles or objects were recreated. PP25 application publication/deployment and
live A → B → fresh A acceptance remain next. Production is unchanged.

[Observed identity](PLAN/evidence/pp-controller-identity-2026-11-20-16f7e3ec.json).

## November 19, 2026, evening CST — PP25 preparation and preserved recovery failure

PR #196 merged into `preprod` as `6f53f5d`. Exact source `bd842fc` passed
push CI44665494143 and PR CI44665501868. It qualifies bounded operator startup
readiness and Coinbase candle transport degradation without converting missing
reference data into fresh forecasts. Production is unchanged; no new live trial
or retirement has occurred.

A read-only cache audit found 52.38 GiB filesystem free and 1,189 MiB available
RAM with the candidate stopped; only 1.229 MB build cache was reclaimable.
Nothing was purged. The first exact-candidate availability restoration safely
stopped again: failed-CD recovery had set restart policy `no`, while the runtime
validator requires `unless-stopped`. The successor restores that policy only for
the four recorded generated/OFF candidate IDs and fences/stops them on failure;
13 offline fault tests and independent review passed. This restoration cannot
turn the original failed CD into PASS. The corrected attempt restored generated/OFF
API and operator availability with PostgreSQL unchanged.

[Preserved restoration/cache evidence](PLAN/evidence/pp24-restoration-hold-2026-11-20.json).

# BTC Intelligence: live plan and status

Updated October 2, 2026. This is the short progress tracker. [STRATEGIC_PLAN.md](STRATEGIC_PLAN.md) holds the architecture and longer roadmap. [PLAN_CROSSWALK.md](PLAN_CROSSWALK.md) maps every phase of the original handoff to current implementation; the original documents remain unchanged.

## Goal

Build a local, read-only analysis system for Polymarket US BTC Up/Down markets. The current implementation focuses on 15-minute markets. Save source data, calculate reproducible signals, make measured forecasts, and compare them with confirmed outcomes. Add 1-hour support after the 15-minute path is reliable. Trading execution is deferred.

## Progress

- [ ] PP24 smoke held on operator startup; database preserved, collector neverON. Bounded readiness and transient Coinbase candle isolation fixes locally tested; exact CI/deployment/live proof pending. [Evidence](PLAN/evidence/pp24-operator-readiness-failure-2026-11-20.json).

- [x] PR194 exact CI and dedicated new-controller identity44662010928 PASS; old PP profile restored, no DB restart/cache purge/guard change. Fresh live acceptance still OPEN.

- [x] Failed PP23 A archived and independently verified with collection OFF: 18,930 raw / 20,362 structured; all retained locally. [Evidence](PLAN/evidence/pp23-failed-a-archive-2026-11-20.json).
- [ ] Fresh Polymarket-priority trial03: reconnect regression passed, new scope locally tested; exact Linux CI, old-profile recovery, deployment and both live retirements remain open.

- [ ] **PP23 live continuity failed before first A seal.** Source `f964c93`;
  Coinbase WebSocket failure stopped collection at 7:38:52 p.m. CST November 19.
  A retains18,930raw /20,362structuredACK /zero pending; no raw archive or deletion.
  Durable OFF and temporary service restoration confirmed. Reconnect cause/fix,
  failed-initial-A archival and fresh full A→B→A proof remain open.
  [Evidence](PLAN/evidence/pp23-live-stop-2026-11-20.json).

- [ ] **PP23 fresh two-leg live qualification (deployed, OFF readiness passed).**
  Source `f964c93`, merge CI 44647163600, publication 44647852318 and CD
  44648041989 PASS. Exact trial02 reached `PP_LIVE_READY_OFF`; both cloud
  workers started. Live ON, two-market A → B → fresh A and concurrent retirement
  acceptance remain pending. The unchanged 1 GiB headroom guard held an earlier
  instrumented entry; a reviewed idle `fwupd` pause has a 120-minute automatic
  restore plus pending explicit cleanup. Production API collection is temporarily
  OFF/process-fenced; its prior configuration restoration remains pending after
  PP final drain/readback. No production database change.
  [Readiness evidence](PLAN/PP23_DEPLOYMENT_READY_OFF_2026-11-20.md).

- [x] **PP22 retained-data drain and archive before another live trial.**
  All 4,888 pending records freshly verified/ACKed in 126.359 s (38.683/s).
  Initial A sealed with collector OFF; 5,241 raw rows archived in 11 objects.
  Independent readback passed all objects and 5,651 structured rows; pending
  zero. No deletion, new live trial or production change. Exact drain/helper
  CI passed; recurring runtime release and fresh admission remain open.
  [Evidence](PLAN/evidence/pp22-retained-drain-archive-2026-11-19.json).

- [x] **PP21 old A/B Supabase drain.** Old A remained verified with 57
  private Storage objects covering 28,411 raw rows. Sealed old B with the
  collector durably OFF and archived its 9,784 raw rows as 20 authenticated
  objects. Independent B readback matched all 20 objects and 10,971 structured
  rows in 82.914 seconds. Supabase receipt and revision counts match across both
  generations (42,133 each). Before/after A/B raw and outbox fingerprints match
  and pending rows are zero. Both partitions remain attached. The first
  profile-entry attempt held and the installed leave procedure restored the
  healthy generated profile. The drain used disposable, digest-bound workers
  on the pinned PP21 image and left the services in generated mode.
  [Evidence](PLAN/evidence/pp21-historical-drain-2026-11-19.json) ·
  [Seal source CI](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44610742055)

- [ ] **Fresh PP trial origin.** Source scope is
  `pp-live-pp-trial-20261119-01` in the existing PP database. Isolated native
  tests pass both directions of the shared collector fence, preserve the old
  origin, and verify exact trial retirement with its separate 30-minute
  windows. The old A/B drain grants no deletion or fresh-trial authority.
  Hosted setup created exact trial-only SQL writer/reader logins and two
  Storage Auth identities. The bounded fixtures proved one exact structured
  receipt/revision and one 210-byte private archive object, with independent
  reader readback and denied reader writes and foreign-origin access. Ten
  private files were staged on PP without activating a collector or replacing
  legacy credentials. The live profile must qualify both workers and the
  independent reader, deploy the exact release, prepare the initial A and
  verify the production fence before collection starts. PP22 source
  `0c86b47` passed exact CI and generated-mode deployment. The installed
  controller passed the dedicated identity check. The exact trial initial A
  was created empty with collection OFF, and both scoped cloud workers passed
  host readiness. Live rollover, two deadline-bound retirements, history after
  removal and the final fresh-A drain remain open.
  [Exact CI](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44623771290) ·
  [PP22 deployment](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44624765516)
  [Trial scope](PLAN/PP_TRIAL_CLOUD_ORIGIN_2026-11-19.md) ·
  [Hosted qualification and PP staging](PLAN/evidence/pp-trial-cloud-setup-2026-11-19.json)

- [ ] **PP22 live rehearsal held before the storage switch.** Collection
  advanced across the 22:15 UTC Polymarket boundary. PostgreSQL persisted 333
  Coinbase events during the discovery gap. The dashboard paused the displayed
  Coinbase price during that same gap. The structured worker stopped after
  Supabase committed a 50-row page. A 25-row fallback also hit its deadline
  and processed about 3.8 rows/s against 13.6 incoming rows/s. PP stopped
  before the queue guard. A retained 5,241 raw rows and 4,888 pending
  structured records. All 763 hosted receipts and revisions matched local
  acknowledgements after exact readback. No seal, B, raw upload or retirement
  occurred. Production's original service setting was restored. Qualify
  fewer remote transaction round trips and sustainable sync before a new
  live attempt.
  [Live evidence](PLAN/evidence/pp22-live-initial-a-hold-2026-11-19.json)
  The exact-CI batching candidate returned the same 25 receipts/revisions in
  3.784 s in a classified read-only PP comparison; the released code's read
  held at 4.369 s. Sustained put, readback and local ACK remain unqualified.
  [Comparison](PLAN/evidence/pp22-structured-readback-comparison-2026-11-19.json)
  A bounded test of that candidate against the retained backlog with collection
  OFF held on the first 50-row import at 4.112 s. The hosted writer log records
  transaction timeout `25P04` during the revision SELECT. Supabase reports zero
  committed rows for that page. Local counts remain 4,888 pending and 763
  acknowledged, with all 5,241 raw rows attached. The 13.6 records/s gate failed.
  [Offline qualification](PLAN/evidence/pp22-offline-sync-qualification-2026-11-19.json)

- [ ] **Paired SSE and Realtime latency.** Three local runs matched all 180
  generated tick IDs and prices. Local Realtime median was 66–90 ms and the
  app's 250 ms SSE path had a 122–137 ms median. The paired median favored
  Realtime locally by 37–55 ms, while Realtime arrived later on 52 of 180
  ticks. Actual PP replay awaits the release owner's rehearsal ON receipt.
  [Methods and limits](PLAN/SUPABASE_ISOLATED_CAPABILITY_LAB_2026-11-19.md)

- [x] **Isolated Supabase capability lab.** Generated local tests covered
  REST/RPC and role policies, GraphQL, private Storage, the Edge runtime,
  webhook transport, Cron, Queues, Realtime, vectors and PostgreSQL telemetry.
  Independent native tests measured RPC round trips and reproduced exact
  research features after an A/B restore. The local WAL/analytics trial
  preserved the immutable evidence and demonstrated duplicate delivery.
  The combined Cron and Queue probe published the existing audit telemetry
  after a forced rollback and retry, deduplicated job delivery, and reported
  missing evidence as unknown. The scheduler probe now distinguishes fresh
  stopped collectors from stale or missing resource observations. A live
  report bridge and hosted Pipelines and Analytics Buckets still need
  separate qualification.
  [Lab findings and PP decisions](PLAN/SUPABASE_ISOLATED_CAPABILITY_LAB_2026-11-19.md)

- [x] **PP21 retained-A read-only verifier — bounded diagnostic passed.**
  Exact qualified canonical-byte transport verified all 57 raw objects / 28,411
  rows and 63 structured pages / 31,162 rows. Core elapsed 214.390169 s under
  240 s, with 25.609910 s remaining; attached-container interval 219.458 s.
  Retained before/after fingerprints matched. This is a diagnostic result;
  regular PP21 deployment/collection state is unchanged, and the expired
  original trial and local retirement remain unqualified.
  [Exact receipt, source binding and limits](PLAN/PP21_CANONICAL_RETAINED_AUDIT_2026-11-19.md)

- [ ] **PP raw archive restore and readback evidence — tools qualified on generated data.**
  A disposable PostgreSQL 17 reader exported the complete generated catalog.
  The offline verifier recovered **57 objects and 28,411 generated rows** from a
  separate staged copy with the primary path unavailable, then rejected a
  missing final object. The audit timing CLI distinguishes verified progress
  from attempts and preserves the actual PP20 hold at 239.608 seconds after
  57 raw objects and 62 of 63 structured pages. The exact first page passed in
  2.729 seconds. An actual independent PP backup destination and restore, a
  complete retained-A readback, and any local retirement remain open with the
  release owner. [Drill and commands](PLAN/PP_RAW_RECOVERY_DRILL_2026-11-19.md)

- [ ] **PP A/B retirement and deterministic dashboard history.** The
  [five-step master plan](PLAN/INTELLIGENCE_REBUILD_PLAN.md) now binds the actual
  legacy FastAPI and SQLite contracts, PP release recovery, both rotations, and
  deterministic history parity across retirement. The full-schema raw cursor
  study preserved exact hashes and reduced the generated 57-page sweep from
  4.613 s to 0.761 s. The fixture measured about 4% more bulk-insert time
  and 15% more WAL with the index. PP21 passed normal deployment and the
  independent retention snapshot with both generations intact. The release
  team is checking the live-ingest outcome envelope against the point-in-time
  prototype. Actual PP query plans, live write overhead,
  full retained-A verification and multi-generation deterministic parity
  remain to be verified.
  [Local query study](PLAN/PP_LOCAL_RETENTION_QUERY_STUDY_2026-11-19.md)

Documentation update October 7: [PROGRESS_SUMMARY.md](PROGRESS_SUMMARY.md) summarizes completed work, recorded validation, partial features, and remaining gaps. Reviewed against this checklist and commit history; no new live verification or implementation milestone is claimed.

- [x] **Milestone 1 — Data access and SQLite collector.** Discover the active 15-minute market and exact target, store Polymarket observations and Coinbase candles, join mid-session, reconcile delayed outcomes. Tests passed; pushed as `05ce7f4`.
- [x] **Milestone 2 — Live BTC streaming.** Save Coinbase ticker events with source times and deduplication; reconnect with backoff; keep public Polymarket REST discovery and settlement checks. A 25-second live test saved 102 ticker events; 16 tests passed; pushed as `e9fdd73`.
- [x] **Milestone 3 — Deterministic features.** Versioned 15-minute snapshots store exact target distance, remaining seconds, 1/5/15-minute returns, 15-minute realized volatility, 5/15-minute volume, source evidence, freshness and missing flags. Recent completed Coinbase candles refresh in one bounded request about once per minute; a one-minute lag is labeled. Live runs stored consecutive complete snapshots and verified the candle first-seen migration; 24 tests passed.
- [x] **Milestone 4 — Baseline forecasts and evaluation.** An untrained, versioned probability proxy saves live forecasts or abstentions against feature snapshots. The report evaluates one forecast per confirmed 15-minute market at T-10m, T-5m and T-1m, with Brier score, log loss, calibration counts, a 50/50 reference, and chronological splits after 30 distinct markets. A live rollover paired T-5m and T-1m forecasts with one confirmed DOWN outcome; 30 tests passed. This verifies the pipeline, not predictive skill.
- [ ] **Milestone 5 — More history and signals.** **In progress.** Coinbase's 30-day candle backfill stored 43,200/43,200 completed minutes. The 30-day Polymarket US scan completed 90/90 eight-hour chunks: 795/2,880 expected 15-minute intervals had resolved markets, with 12,694 stored book-derived display-price points. The earliest returned market starts September 22 at 15:15 UTC; 2,065 expected intervals precede it, and 20 gaps occur after it. Three transient price-history failures were retried successfully; the checkpoint now reports zero request failures. Timestamp-safe matching selects one live snapshot per prior resolved market and links the observation that established its known outcome. The October 1 retrospective prior-case comparison has 29/29/28 paired markets at T-10m/T-5m/T-1m; on the same pairs its Brier scores are worse than the saved price baseline (0.253 vs 0.213, 0.222 vs 0.148, 0.210 vs 0.003). This proxy was never issued live, and none of its checkpoints reaches 30 paired markets. Next: characterize the 20 within-range historical gaps and improve or discard the case signal based on later evidence. Full historical order books and trades are not represented by display-price history.
- [ ] **Milestone 6 — News and OpenAI.** **News ingestion started.** A read-only CoinDesk RSS collector stores headlines, links, categories, publisher publication times, and local first-seen times. The six-hour bounded poll has finished; it checked every ten minutes while running. The saved data has nine BTC-tagged headlines, but only one was first seen within an hour of publication; median publication-to-first-seen delay is about 17.3 hours. Availability alone is not evidence of a timely signal. Next: improve source freshness and coverage before testing news contribution. OpenAI calls remain deferred pending configured API access and a spending limit.
- [ ] **Milestone 7 — Text and traversal memory.** **In progress.** FTS5 headline search is built. Typed SQLite links now trace a prediction to its snapshot and retrospectively eligible news/prior cases, with source IDs and availability times. These links explicitly do not mean the baseline model used the context. Next: connect real analysis outputs and evaluate whether retrieved evidence adds value.
- [ ] **Milestone 8 — Dashboard and 1-hour expansion.** **Read-only local dashboard started; one-hour work deferred.** It displays the active 15-minute market, latest saved Coinbase stream tick separately from the Coinbase price used by the saved forecast, a 15-minute Coinbase price chart with the Polymarket target as a labeled blue dotted line, snapshot and feed freshness, UP/DOWN market prices, confirmed-market checkpoint counts, recent outcomes, BTC headlines, and the latest retrospectively linked evidence. The UTC clock, countdown, and evidence ages tick between two-second SQLite checks. A local server-sent event stream checks newly saved Coinbase ticks every 100 ms and updates the orange graph as they arrive; grouped history still refreshes every five seconds for recovery. A live local check delivered one new tick about 0.07 seconds after database receipt; this does not measure Coinbase source latency or BRTI alignment. The dashboard also opens its own authenticated read-only Polymarket US WebSocket on the backend and relays compact UP/DOWN last price samples and bid/ask updates directly to the local browser, without waiting for SQLite saves or exposing credentials. Saved quotes remain the fallback and evidence trail. The completed combined collector gathered Coinbase, REST, and Polymarket market books separately, limiting full-book storage to one per second. The displayed experimental baseline estimate recalculates from each fresh Coinbase tick and the latest saved volatility snapshot, using the same tick as the orange graph; it abstains when tick or volatility evidence is stale. It is not saved per tick. Separately saved forecasts updated about every 30 seconds during collection for evaluation. Neither estimate is a live Polymarket market price. The Polymarket BTC chart uses BRTI rather than Coinbase; the market WebSocket carries outcome prices, not a verified BRTI feed. Next: improve 15-minute data-quality display and assess BRTI licensing; do not start one-hour work yet.

- [x] **Collector operations and recovery milestone — October 2.** Per-database kernel locks and private local stop sockets support status/start/stop/restart; crashed owners release their locks and stale PIDs are never signaled. Fresh legacy REST heartbeats prevent accidental duplicate starts. SQLite online backup includes committed WAL data, validates integrity/foreign keys, and publishes only to a new destination. Recovery creates a separate database without overwriting the original. All 67 tests passed, including crash/restart, duplicate ownership, WAL snapshot consistency, corrupt-input cleanup and overwrite refusal. A live backup and recovered copy each contain 850 markets, 241,726 stream events, 1,587 snapshots, 1,580 predictions and 28 news events. Both passed integrity checks. The existing legacy collector was gracefully migrated, then the controlled stop/start restored Coinbase, Polymarket, REST and saved forecasts in 1.57 seconds. Collection remains local and open-ended with the 2 GiB stop-only ceiling; no boot service, backup schedule or retention was added.

## Ordered remaining roadmap

1. **Timely news (next):** characterize source delivery delays, add only justified sources, support controlled continuous polling, and preserve publication/first-seen provenance. Test coverage before treating news as a forecast input.
2. **Historical cases and baseline evaluation:** expand later distinct-market samples, characterize unavailable historical windows, compare timestamp-safe case signals and quote baselines on matched checkpoint sets, and discard signals that do not help. Reserve later holdout data.
3. **Additional numerical evidence:** verify a second exchange, then synchronized trades/books and optional derivatives where usable; evaluate incremental value independently. Preserve Coinbase/BRTI distinctions.
4. **OpenAI and memory:** configure API access plus a spending cap before any paid calls; persist independent analysis outputs and source links, cache/deduplicate requests, and fail gracefully at budget exhaustion. FTS5 and evidence links already exist.
5. **Models and ensemble:** train/calibrate only with sufficient independent labels; combine components only after chronological comparisons demonstrate value. No proven trading edge today.
6. **Dashboard and 1-hour expansion:** continue honest source/quality display; validate 1-hour sessions and evaluation separately after the 15-minute path is reliable. Hourly work remains deferred now.
7. **Deployment and storage:** plan capacity around the approximately 1 GiB database threshold; choose explicit retention, backup scheduling and persistent hosting only as authorized. The existing 2 GiB cap stops collection without deleting evidence.

**Parallel external dependency:** investigate licensed real-time BRTI access and parity if access becomes available. Official Polymarket confirmed outcomes remain usable for evaluation; Coinbase is a reference and does not reproduce the BRTI graph. No further eight-hour soak is planned; order execution remains deferred.

Each milestone is committed and pushed only after its relevant checks pass. Keep the code and this tracker synchronized.

## What the database contains today

The local `data/btc_intelligence.db` stores market records, Polymarket observations, one-minute Coinbase candles, streamed Coinbase ticker events, versioned feature snapshots and forecasts, retrospective market display-price history, feed health, confirmed results, and now sourced news headline references. The 30-day Coinbase backfill reports 43,200 complete minute candles. Live collection and news polling are local processes started by commands; neither is deployed to a separate server or installed as a background service.

## Active multi-market test

The bounded 15-minute collection window finished October 1, 2026 near 09:53 UTC (4:53 AM Chicago daylight time). It started near 01:53 UTC, stopped near 06:58 UTC during an app restart, and resumed near 07:00 UTC. The roughly two-minute interruption is accepted; the user does not want another eight-hour test. Logs are ignored local files `data/soak_20261001.log` and `data/soak_resume_20261001.log`. The read-only audit found 33 observed markets, 32 consecutive rollovers with no missing internal market starts, 32 outcomes confirmed by window end, 923 complete snapshots and 923 forecasts with no abstentions. One snapshot gap exceeded 90 seconds (150 seconds, at the restart). SQLite quick check passed with no foreign-key violations. Historical missing-window reports and 52 book-404 requests are listed separately from two live request errors. The same existing collector was restarted near 22:04 UTC in local open-ended mode (`--seconds 0`), with no eight-hour timer. Live checks showed current 15-minute discovery, subsecond-age Coinbase ticks, fresh snapshots, and live Polymarket books. This process is not a separate server or persistent service; stopping it stops those updates while the dashboard remains readable.

A separate resumable `history_batch.py --days 30 --end 2026-10-01T03:00:00Z` run scanned the 30 days before 03:00 UTC on October 1 and has finished. Its ignored log is `data/polymarket_30d_backfill.log`; chunk results are checkpointed in SQLite. The price-history retry completed and SQLite `quick_check` is `ok`. Local open-ended collection still needs the Mac awake.

A separate CoinDesk RSS poll finished near 09:31 UTC after the restart, using ignored logs `data/news_20261001.log` and `data/news_resume_20261001.log`. This was a bounded single-source feed, not continuous news coverage. At the three checkpoint sets, 25/25/24 saved forecasts had at least one previously seen BTC-tagged headline; news has not been used in or scored as a forecast input.

## Open verification

- One continuous run crossed a real 15-minute boundary: the expired market was reconciled after a brief discovery gap, and collection followed the next active contract. Repeated rollover and prolonged-outage recovery still need measurement.
- The Polymarket markets WebSocket authenticated successfully with the local developer API key; a 60-second read-only subscription saved live full-book updates for the active 15-minute market. The signed-key WebSocket is separate from the JWT-authenticated gRPC data-vendor route. Public REST access works without login. Sustained quote coverage and reconnects remain to be measured.
- Long-running storage retention and recovery after prolonged outages have not been measured. An open-ended collector now checks SQLite database plus WAL size every 30 seconds and stops at a configurable 2,048 MiB default ceiling without deleting saved evidence. The dashboard preserves and displays the `limit_reached` reason. A local restart confirmed the storage guard is watching while Coinbase and Polymarket feeds are live; hitting the ceiling was verified with a temporary database test, not by filling the real database. This cap does not implement raw-data retention.
- The post-run evaluation has 31/33/32 distinct confirmed markets at T-10m/T-5m/T-1m. Brier scores for the saved untrained price baseline are 0.208/0.131/0.003 versus 0.25 for 50/50. Chronological 60/20/20 score blocks are now available, but the latest blocks contain only seven markets each. T-1m directional accuracy is 32/32 in this small sample; this is preliminary, source-dependent, and not evidence of a trading edge. Coinbase is a reference, while BRTI determines settlement. No model tuning should use the latest block as both selection data and final holdout.
- Historical case matching has a preliminary paired retrospective report, but its sample is small. One CoinDesk RSS feed is polled every ten minutes during its bounded local run; it is neither all news nor a continuous stream. FTS5 search, eligible-context links and the local status dashboard exist, but the baseline does not use news or cases. OpenAI analysis has not run. Feature and forecast coverage depends on fresh public data; snapshots retain missing and lag flags when feeds fall behind. The baseline is untrained and uncalibrated.

## Next implementation: live validation and independent panels

Stay on 15-minute markets. The read-only `data_quality.py` report groups the 20 within-range historical gaps into four clusters (2, 8, 8, and 2 intervals). All 20 are absent from the saved normalized market table because the backfill saves only resolved markets with settlement prices; a separate API recheck found four listed as resolved without settlement prices and 16 absent from its returned market list. Investigate source availability before treating these as genuine missing contracts. The same report measures publication-to-first-seen delay for BTC headlines. A short October 1 feed check found the latest BTC item in Decrypt's RSS about five hours old and Cointelegraph's Bitcoin RSS newest item about six hours old; neither justified adding a source for 15-minute signals. Improve news timeliness before evaluating any news/context signal against the saved price baseline without future information. The local dashboard now labels the stopped collector prominently and loads correctly with no active saved market. BRTI access requires a separate licensing request. Do not schedule another eight-hour run or begin one-hour market work yet. Group related work into one milestone pull request rather than a PR for every commit.

## Decisions and evidence

- **Start with 15-minute markets.** The user chose this order; saved 1-hour data remains intact for later work.
- **Keep settlement separate from exchange prices.** Polymarket's BRTI result determines the label; Coinbase BTC/USD is a predictive reference feed.
- **Use one SQLite database initially.** It already stores the numerical evidence; relationship and FTS5 tables will join it when those layers are built.
- **Separate public and authenticated access.** Public Polymarket REST feeds the current collector. Its read-only markets WebSocket uses the developer Key ID and Secret Key, saved locally; it was live-tested without an order request. A separate JWT-authenticated gRPC route is documented but is not needed for this WebSocket.
- **Commit each milestone.** The user requested GitHub commits and pushes after tested milestones.

## Run and validate

From the project root, run `.venv/bin/python -m unittest discover -s backend/tests -v`, then `.venv/bin/python backend/app/streaming.py --seconds 60` for a bounded live check. See [README.md](../README.md) for setup. Inspect SQLite `feed_health`, `runs`, `feature_snapshots`, and `predictions` before declaring a live feed healthy.

## PP size-triggered rehearsal profile

- The generated PostgreSQL profile binds the initial A and byte threshold before the first write. The fixture measures actual partition allocation, verifies and removes both sealed predecessors through the existing generated archive transport, follows the bound profile after a repository restart, and stops rotating at fresh A.
- Run `python -m unittest discover -s backend/tests -p 'test_generated_size_cycle.py' -v`. The native cases launch a disposable socket-only PostgreSQL 17 cluster. The fixtures use small measured triggers. The 32 MiB generated-profile ceiling is a candidate test bound; neither that size nor a 72-hour production window has been qualified.
- The trial07 candidate binds the fresh origin and exact 32 MiB trigger to initial-A preparation, the one-use controller authorizations, the finite writer lease and its admission record, the active profile and the retirement permit. Existing origin policies remain independent. Terminal cleanup requires both verified physical removals and archives the final fresh A without deleting it.
- Before live qualification, require exact CI, reviewed trial07 cloud writer/reader and Storage policies, installed source/image/controller bindings, both privileged-change freeze windows, and retained trial05/trial06 fingerprints. No hosted role, VM deployment, collector activation, or retirement was performed by the offline work.
