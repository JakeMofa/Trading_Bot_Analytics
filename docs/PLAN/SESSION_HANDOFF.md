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

[Sanitized PP27 deployment and ready-OFF evidence](evidence/pp27-trial04-ready-off-2026-11-20.json).

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

[Retained B readback and host preservation](evidence/pp26-retained-b-independent-readback-2026-11-20.json).

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

[Sanitized timing and query-wait evidence](evidence/pp26-retained-a-diagnostic-2026-11-20.json).

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

[Sanitized recovery evidence](evidence/pp26-retained-b-archive-2026-11-20.json)
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

[Sanitized outcome and recovery evidence](evidence/pp26-live-retirement-hold-2026-11-20.json).

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

[Sanitized admission/observation evidence](evidence/pp26-live-admission-2026-11-20.json).

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
remain unproven. [Sanitized deployment/rebind evidence](evidence/pp26-deployment-rebind-2026-11-20.json).

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

[Recovery evidence](evidence/pp25-quiescent-recovery-2026-11-20.json).

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

[Exact deployment and hold evidence](evidence/pp25-deployment-entry-hold-2026-11-20.json).

## November 19, 2026, evening CST — PP25 controller identity qualified

Controller `16f7e3ec…` was installed from exact-CI-qualified `bd842fc` without
creating authority or changing PostgreSQL. Dedicated identity workflow
44666918397 passed at `6f53f5d`; this profile binds its observed result.
Trial03 host credentials were confirmed absent by a metadata-only check and
then staged create-only (10 files), without starting collection or cloud writes.
Existing trial03 Supabase qualification remains attributed to source `413aac3`;
no roles or objects were recreated. PP25 application publication/deployment and
live A → B → fresh A acceptance remain next. Production is unchanged.

[Observed identity](evidence/pp-controller-identity-2026-11-20-16f7e3ec.json).

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

[Preserved restoration/cache evidence](evidence/pp24-restoration-hold-2026-11-20.json).

## November 20 UTC — PP24 deployment held; startup and candle fixes tested

Exact merge source `d5615a3` passed CI44663447570 and publication44664123475
(v0.2.0-pp.24). CD44664385511 failed at smoke with
`host_operator_loopback_unavailable`; recovery stopped the candidate and
preserved PostgreSQL. No live collector started. PostgreSQL remained healthy
and was not recreated. The API returned /state/current at02:59:10.542UTC;
operator startup completed at02:59:10.868UTC, then recovery stopped it. No
operator HTTP requests were logged. This supports a startup-readiness race.

Smoke previously checked operator loopback once, although Compose health only
proved the API. The candidate reuses the existing bounded generated-host
readiness poll for smoke and restore; only connection/timeout startup errors
retry. Malformed/token/auth/state failures remain immediate holds.

Legacy comparison also found candle-request failures could still terminate PP's
whole supervisor. The candidate degrades only exact candle fetch timeout,
transport,429 and5xx codes at the unchanged60–300-second cadence; Polymarket
continues, with payload-free failure/recovery logs. Write/auth/schema and
ownership failures remain fatal; missing reference data never becomes fresh.

Local controls271 tests passed(14 platform skips); candle6, supervisor9 and
Coinbase26 tests passed. Independent local review reran46 controller and6 candle
tests successfully. Exact candidate CI/release and forward PP restoration remain
next. Actual trial03 cloud allow/deny/readback and old-scope preservation passed;
no new live trial or deletion occurred. Phase1.75/I7 remain OPEN.

[Deployment failure evidence](evidence/pp24-operator-readiness-failure-2026-11-20.json).

## Profile CI correction — November 20 UTC

PR195 initial source9171919 failed the deployment-control gate because the
profile was updated but `environment_pipeline.py` retained the prior exact
controller/identity pins. These pins now match the actual installed ec2e8baf
controller and identity44662010928 at66178cf. All56 local CI-control tests pass;
successor exact CI remains required. No application deployment occurred.

## November 20 UTC — fresh trial code and controller qualified

PR #194 merged as `66178cf`. Exact source `413aac3` passed push CI
44661102402 and PR CI44661109552; the earlier external-fixture PATH failure is
preserved, corrected and independently reproduced/passed in external DSN mode.
The old PP23 profile was restored with collection OFF by stopping only four
application services before the original leave checks. PostgreSQL was untouched;
no cache purge or memory-guard change. The current headroom hold was process
memory, not disk capacity (about56GB free).

The successor controller `ec2e8baf…` is installed from qualified `413aac3` and
passed dedicated deployment-identity run44662010928. This profile binds that
observed result; it is not application deployment or collector ON. Fresh trial03
cloud enrollment and its allow/deny/readback qualification are in progress.
Both30-minute live rotations, concurrent archive/deletion and dashboard/history
acceptance remain OPEN. Production remains unchanged by this release.

[Identity evidence](evidence/pp-controller-identity-2026-11-20-ec2e8baf.json).
[Old profile recovery](evidence/pp23-profile-recovery-2026-11-20.json).

## November 20 UTC — failed A recovered; fresh Polymarket-priority trial preparing

The previous live trial remains **FAIL before A → B**. Its retained initial A
has now been sealed with collection OFF, archived and independently verified:
**18,930 raw records in 38 objects, 20,362 structured records, zero pending**.
Independent readback used 81 requests / 35,230,341 bytes within the 240-second
budget. Source and older metadata fingerprints were preserved. **No partition
was deleted.** Production's previous setting and the temporary fwupd pause were
restored. Archive worker stopped after verification.

PR #193 merged as `6a09ed4`: transient Coinbase transport failures now reconnect
within the finite lease instead of exhausting a lifetime retry cap and ending
Polymarket collection. The concurrent regression proves Polymarket writes and
rotation continue while Coinbase retries; stale-reference forecasts abstain.
This is tested code, not a completed live rotation result.

The fresh trial03 candidate retains failed trial02 intact, requires its exact
verified archive and independent audit, and uses separate origin/credentials.
Local qualification: **580 backend tests (66 platform skips), 265 controls
(14 platform skips), 11 CI-control tests passed**. Exact successor Linux CI,
controller/release qualification and live A → B → fresh A remain pending.
A host leave attempt returned `entrypoint_precondition_failed`; read-only
inspection shows state `leaving`, collector OFF and 1,042,944,000 available
memory bytes. Recovery cause is being checked; do not repeat admission or
install a successor controller over unresolved old-profile state.

Next: recover the old profile, qualify/deploy the successor, then run two full
30-minute windows. Each sealed partition needs independent authenticated
readback before deletion while its successor keeps collecting. Both retirements,
archived history and dashboard freshness still require live evidence.
Phase 1.75/I7 remain OPEN.

[Failed-A archive evidence](evidence/pp23-failed-a-archive-2026-11-20.json).
[Fresh trial scope](PP_THIRD_TRIAL_SCOPE_2026-11-20.md).

## November 19 CST — PP23 live attempt stopped before first rotation

**FAIL, not a completed A/B trial.** Deployed `f964c93` started the exact trial02
collector at approximately 7:14 p.m. CST. The operator recorded
`coinbase_stream.ws_closed_error` and durable OFF at **7:38:52 p.m. CST**
(`2026-11-20T01:38:52.370522Z`), before the scheduled 7:45 first seal.
Initial A remains attached and unsealed: **18,930 raw rows, 20,362 structured
ACKs, zero pending**, zero raw manifests. No B, fresh A or deletion was observed.

The 7:30 market boundary recovered without ending collection. Observed API/SSE
and dashboard/history requests stayed below two seconds. Freshness failed:
Coinbase exceeded 30 seconds in 90 ON samples, maximum 70.589 seconds. An
87.596-second observer gap is preserved; it is not evidence of a collector stop.
The code has rolling and lifetime reconnect limits, but the stop code does not
identify which limit fired or distinguish upstream from local receive backlog.
Do not label a raised reconnect limit a demonstrated freshness fix.

PP durable OFF was independently confirmed, both cloud workers stopped, the
production API's original storage-held collector setting restored, and the
reviewed temporary fwupd pause restored without persistent enablement changes.
All collected data remains local. The next work is tested reconnect diagnostics
and resilient transport recovery, followed by a narrowly scoped OFF-only archive
of this failed initial A; do not misuse the final-three-generation drain helper.
A new qualified attempt must still prove both retirements and historical reads.
Phase 1.75/I7 remain OPEN.

[Sanitized run and recovery evidence](evidence/pp23-live-stop-2026-11-20.json).
[Reconnect and failed-A recovery candidate](PP23_RECONNECT_AND_FAILED_A_RECOVERY_2026-11-20.md).

## November 20 UTC — PP23 deployed; fresh trial OFF readiness passed

PR #192 source `f964c93` passed exact merge CI 44647163600, publication
44647852318 and CD 44648041989. All generated deployment checks, including
recovery, passed. Exact trial02 initial A `41c82044-0fb8-4900-bea0-7c43ba079ff0`
reached `PP_LIVE_READY_OFF`; both source-bound cloud workers started with
collection OFF. This snapshot contains no ON receipt or live acceptance PASS.

Instrumented entry exposed the unchanged 1 GiB guard: 1,071,587,328 available
bytes versus 1,073,741,824 required. A reviewed, reversible idle `fwupd` pause
provided headroom without changing the guard. Its 120-minute automatic restore
is armed; explicit restoration and observed restoration completion remain pending.
Production's API collector is temporarily OFF/process-fenced, with no production
database change; restore its prior configuration after PP final drain/readback.
The authorized two-leg observation, concurrent archive/deletion proof and final
cleanup remain open. Phase 1.75/I7 remain OPEN.

[Deployment, holds and maintenance](PP23_DEPLOYMENT_READY_OFF_2026-11-20.md) ·
[Sanitized evidence](evidence/pp23-deployment-readiness-2026-11-20.json).

## November 19 — PP23 release preparation, live proof still pending

Exact application source `59c5993` passed Linux CI 44643071297; combined
source `1f5f15e` passed push CI 44644055724 and PR CI 44644062715.
PR #191 had already merged the prior drain evidence; successor PR #192 carries
the fresh trial changes. The old01 trial left cleanly after the unchanged
1 GiB host-memory guard identified insufficient headroom. Only idle calculation
and lifecycle containers were temporarily stopped; the normal leave restored
all generated services. PostgreSQL and API stayed available, collector OFF.

Installed controller `65de5662…` through the pinned code-only transfer.
Independent02 cloud identities passed actual synthetic create/readback and
cross-origin denial checks. Existing policy/role/grant hashes and legacy/01
receipt/revision counts are unchanged. Ten new02 credentials were staged without
replacing old paths. No new live collection or local retirement has occurred.
The next gates are verified controller profile, exact release publication/CD,
then the authorized two-leg live trial. Production is unchanged.

[Preparation evidence](evidence/pp23-release-preparation-2026-11-19.json).

# Resume here

**November 19 UTC — retained PP22 drain/archive PASS.** Collector remains OFF;
4,888 pending structured records acknowledged at 38.683/s, all 5,241 raw rows
archived in 11 objects, and independent readback of 5,651 structured rows plus
all raw objects passed. No deletion or new live trial. Exact maintenance source
`3850776`, CI 44636450530 PASS. Follow the opening
[master roadmap](INTELLIGENCE_REBUILD_PLAN.md) and its linked evidence.
Preserve current uncommitted runtime sync/reuse wiring and Coinbase gap hydration;
qualify that release and safe fresh admission before another live rehearsal.
Never reset or reuse the sealed one-use trial origin as an empty trial.

## Historical handoff entries

**Current PP checkpoint, November 19 UTC:** pp.16 is deployed and ready with its collector OFF. Follow the [master roadmap](INTELLIGENCE_REBUILD_PLAN.md) for the 50-row sync, measured raw transfer scope, and pending combined live run. Earlier entries below are historical.

**November 19 UTC** — pp.15 is deployed to PP and real structured archival passed for 25 records. Read the [master roadmap](INTELLIGENCE_REBUILD_PLAN.md) for release evidence, sync timings and the outstanding A-retirement gate. PP is ready with its collector OFF. Earlier entries below are historical.

**Historical checkpoint (November 18 CST):** `preprod` source `2e38ecd` passed CI
44422595480, and `v0.2.0-pp.12` passed manual PP CD 44423321845. The PP app
and PostgreSQL are healthy. Mode transition 44423758592 passed, leaving PP
`PP_LIVE_READY_OFF` with collector OFF. The first one-use `history_v2` probe
FAILED with Supabase SQLSTATE `25P04` (transaction timeout); read-only
reconciliation found zero PP cloud receipts/projections/checkpoints and zero
local ACKs for the selected page. Its permit was consumed. Raw archival,
retirement, paid AI and production remain unchanged. See the opening master
roadmap section for the exact next gates. The earlier pp.11 account below is
historical.

**Current checkpoint (November 18 CST):** Follow the opening section of
[INTELLIGENCE_REBUILD_PLAN.md](INTELLIGENCE_REBUILD_PLAN.md). PRs #124–#126
merged to `preprod` at `56e4de5`; exact merge CI passed. Candidate
`v0.2.0-pp.11` published in run 44418143697; installed successor controller
`acec846b…` passed identity run 44418190583. Manual PP CD
[44418602445](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44418602445)
**FAILED before authority consumption** because the target profile still
expected old controller `c3fac37c…`. Source extraction and read-only preflight
passed. No candidate journal was created; the unused permit was revoked.
Prior application containers and PostgreSQL are healthy, API HTTP 200,
collector OFF. Node 20 and `ubuntu-latest` warnings did not cause the failure.
PR #128 corrected the exact target-profile binding and merged as `f09987c5`
with merge CI 44421342321 PASS. PR #129 separately pinned Node 24 Actions
and Ubuntu 24.04 and merged as `2d0a449` with CI 44421906498 PASS; neither
merge retried pp.11 or deployed PP. Qualify a new exact release before
another manual attempt.
Structured cloud sync, raw archival, retirement and production cutover remain
OPEN. Older entries below are dated history, not current instructions.

Latest CP6 permission checkpoint (November 18 UTC): PR #98 merged to
`preprod` as `2c6ffd2` and its exact PP-only NOLOGIN `history_v2` role was
applied to Supabase as migration `20261118021900`. Catalog readback passed.
This does **not** enable PP cloud writes, raw Storage access, local retirement,
or a production change. Draft PRs #92/#97 still need runtime/cloud
qualification. CP7 Coinbase reconnect and generated leave fixes are merged
in source but undeployed to PP; its last observed collector state was
generated/OFF after the failed diagnostic trial. Follow the opening master
roadmap section for exact evidence and next gates.

The November 17 opening section of the master roadmap now distinguishes the
**selected** PP modes from what is deployed. PP normally should preview the
production API, switch temporarily to its own live collector/PostgreSQL for a
bounded test, then return to preview; no production pause is needed. Today PP
has one `tradebot_pp` database and generated-only dashboard, not the separate
experiment database or production-preview route. PP cloud sync/retirement are
OFF. Audit actual production/Supabase coverage before claiming recent data is
complete; the last recorded production collector state was storage-held.

CP7 policy correction (November 17): PP and production may independently read
the read-only market feeds into their separate databases. Do not stop or change
production for a PP live trial. Qualify one leased collector per **PP database**,
the private ON/OFF host process control, bounded request cadence and truthful
source health first. The master roadmap's opening section supersedes older
cross-VM sole-collector language below. Production cutover still requires its
own old-writer fence. PP remains live-collector OFF as of the pp.7 release.

Current CP7 runtime (November 17): `preprod` source `4eea47b` passed exact
CI 44166604082 and was deployed as `v0.2.0-pp.7` in manual CD 44167381155.
Migration 0002 and generated-only acceptance passed. PP has five running
services; collector, cloud sync, retirement and paid AI remain OFF. The one-use
authority was consumed and the ephemeral runner unregistered. The pp.6 package
mentioned below is historical and was never deployed. Next qualify the host
ON/OFF path and cross-VM production fence before any bounded PP live run.
The master roadmap and sanitized deployment artifact have exact evidence.

Current CP7 checkpoint (November 17): PR #60 merged at `e849794`; exact CI
passed. Generated-only `v0.2.0-pp.6` is published but **not deployed**. PP still
runs `v0.2.0-pp.5` and has no lease migration 0002. The installed controller
matches the candidate, but the approved ephemeral private GitHub runner is
absent; no one-use host authority was created. Restore that runner, then run
the exact manual PP release and bounded acceptance. Do not activate PP live
collection until the host ON/OFF path and cross-VM production fence pass.
The master roadmap has the exact SHA, run links and remaining gates.

Read `AGENTS.md` and the active section of
[INTELLIGENCE_REBUILD_PLAN.md](INTELLIGENCE_REBUILD_PLAN.md). The master roadmap is
authoritative; this handoff only points to the current checkpoint. Preserve the
dirty original checkout on `codex/phase1-75-retention-enable`, including all
unrelated edits and secrets. Small reviewed PRs target `preprod`.

PR #52 merged a separate loopback-bound PP operator status/OFF service; merged
source `a11d922` passed exact CI 44022560772. The first explicit token
preparation stopped before writing because the existing PP marker correctly
said `application_installed=true`. PR #53 fixed that narrow preflight and
merged as `989f461`; exact preprod CI
44024202007 passed. The explicit token preparation and controller installation
passed on PP, followed by dedicated identity run 44024832718 PASS. The
operator service was not deployed at that binding checkpoint. See the sanitized binding in
`docs/PLAN/evidence/pp-operator-controller-binding-2026-11-17.json`.

PP release `v0.2.0-pp.4` in CD 44026013400 **failed** at the GitHub-side
acceptance check after the host controller passed and started the operator
container. PP now has five running containers. Authenticated operator status
reports collection OFF; unauthenticated access is denied. Do not call this
release PASS. The authority was consumed. A PP-only acceptance-check
correction was required; production remained unchanged.

That correction merged as `e907022`, exact CI 44026918955 PASS. Version
`v0.2.0-pp.5` passed manual CD 44027443677 in generated-only scope. PP now
runs five services; private API and authenticated operator status respond,
but collection, cloud sync, retirement and paid AI remain OFF. The one-use
authority and temporary runner are gone. See
`docs/PLAN/evidence/pp-operator-release-2026-11-17.json`. Continue CP7 with
the cross-VM sole-collector fence and bounded ON/OFF session control before
any live PP feed run. Production is unchanged.

## Current PP checkpoint — November 15, 2026

The private PP API route is **PASS in generated-only scope**. Source `b50861d`
passed [exact CI 43765914993](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/43765914993),
published as `v0.2.0-pp.3`, and passed
[CD 43766281486](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/43766281486).
The installed controller hash is `d66518ce...`; its dedicated-key identity run
43765449362 passed. An approved operator SSH tunnel to PP host
`127.0.0.1:8000` returned HTTP 200 for dashboard, state, health, local history
and SSE. The prior dynamic-container-IP tunnel is historical. Read the
[sanitized acceptance result](evidence/pp-loopback-acceptance-2026-11-15.json).

PP runs four Compose services and local PostgreSQL. Its application remains in
generated mode; live collector, cloud archival/retirement, paid AI and trading
are OFF. The temporary runner deregistered and one-use authority is gone.
Production was not changed or freshly audited by this release.

## Current work — November 15 CST / November 16 UTC

CP6's additive private `history_v2` schema was applied as
`history_v2_private_20261116`; see the
[sanitized schema result](evidence/cp6-history-v2-schema-2026-11-16.json).
PRs #37 and #38 added default-off bounded private Storage requests and strict
structured-outbox envelope validation. PR #41 separated the Storage project
key from its bearer token after confirming that privileged service keys bypass
Storage RLS. No cloud runtime is connected. A read-only catalog check found no
`history_v2` runtime grants and no `storage.objects` policies. Scoped identity,
reviewed allow/deny tests, actual isolated write/readback, mutable projection
ordering and privileged mutation protection remain CP6 gates.

CP7 PR #39 added default-off bounded Coinbase ticker and Polymarket US 15-minute
market source clients. PR #40 requires the durable collector-enabled flag for
any future `pp_live` ingest. PR #42 added an idempotent stop transaction and a
generated PostgreSQL lock-handoff test. All five PRs merged into `preprod`;
latest source `a0e2678` passed
[preprod CI 43813105666](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/43813105666).
These changes were not deployed to PP. They do not enable collection.

**Continue with:** the restricted authenticated PP operator control, real
source/market-boundary integration and cross-VM
sole-collector fence. CP6 cloud identity/grants and actual readback must pass
before archival/retirement is enabled. Keep PP generated-only, production
legacy SQLite held, and retirement/paid AI OFF until their separate gates.

November 16 CP7 progress: PRs #45-#49 merged into `preprod`. The default-off
source bridge, generated PostgreSQL write/read/stop qualification, unstarted
authenticated status/OFF operator surface, and prepared-OFF `pp_live` origin
configuration and bounded closed Coinbase candles passed their PR CI and
preprod merge CI. PR #50 added a supervised, bounded coordinator with
independent source tasks, one-second durable-flag/owner checks and a required
durable-OFF callback; its exact preprod CI 44018709047 passed. None was
deployed to PP or enables a live collector. The next candidate makes the
status/OFF operator API a separate process with file-mounted credentials, but
it has no Compose binding or ON route. Qualify host-bound operator control and
the cross-VM fence before any bounded live run. PP remains generated-only and
production is unchanged.

Keep the selected 72-hour-or-qualified-size A/B generation policy inside
PostgreSQL. Archive verification precedes local retirement. Current PP access
success does not close I7 or Phase 1.75; both remain OPEN. The old SQLite A/B
branch is historical and must not be bulk-merged.
