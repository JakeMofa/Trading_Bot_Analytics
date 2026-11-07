# PR9 resumable verification and continuous A/B checkpoint

Production remains unchanged and held. The tested 4bc3699 bootstrap, selected
13,248-row recovery, archive probes, repeated application handoff and conflict
resolution remain valid for their recorded scopes. No new production/cloud scan,
write, deployment, permission change, deletion or storage-limit change is made.

## Verification implementation

The lifecycle may opt into `AB_RETIRE_VERIFY_OBJECTS` (default0, range1–8 when
selected). Each cycle persists successful bounded verification progress in core.
It is bound to generation identity, main/nonempty-WAL inode/length/mtime, exact
manifest catalog, per-generation ledger/receipt/manifest mutation epoch and
validator code hashes. Writes to the other active generation do not invalidate
sealed-generation progress. Actor restart resumes valid progress. Changed or
expired proof causes re-verification; missing/corrupt contents preserve raw files.

**Cached checks never authorize retirement.** Final fresh authenticated readback,
exact body/identity/count/coverage checks, protected evidence and reader/OS handle
drain remain mandatory through the existing retirement implementation. A remote
object changed after a cached check is detected by that fresh gate. Final work is
charged to the same per-cycle object budget and original cloud deadline; a catalog
that cannot fit that tail remains explicitly verifying/held. Local SQL has
cooperative expiry and an additional deadline check before unlink. This is not a
new atomic remote snapshot or an OS I/O hard-time guarantee. The existing generated
supervisor still bounds the whole fixture to180s. No cached-proof bypass was added.

`AB_RETIRE_VERIFY_MAX_AGE` defaults300s (explicit supported bound1–21600s); this
is progress freshness, not feed freshness, feature age, a network timeout or
production approval. A wider progress window cannot clear the final fresh gate.
All production routing/retirement defaults remain disabled/generated-only.

The actual collector/scheduler/HTTP/SSE/feature/lifecycle joint regression now
starts lifecycle retirement OFF, completes archive/readback while new data is
acknowledged, explicitly enables retirement without restarting the collector, and
repeats B→A→B→A. It requires correct active-generation dashboard/predictions,
reader holds, fresh final readbacks and preserved acknowledged rows. Linux root
is required for actual unlink; local platform skips are not represented as proof.

Local completed evidence before freezing: backend425PASS/20platform skips before
last deadline/corruption additions; final focused incremental7PASS/1root skip;
runtime10PASS/1root skip; controls123PASS/3platform skips; FK progress8PASS.
Exact successor Linux CI is mandatory and will qualify the final source.

## Complete legacy verification remains complete

The existing helper still performs whole-database `quick_check`, then checks EVERY
schema table declaring a foreign key, fully consuming its FK result in the same
read transaction. This is equivalent FK scope to the global check, not sampled
rows or table-local integrity substituted for the full quick check. Durable
progress records the active FK table and completed-table count; tests inject a
failure in the second declaring table, timeout and interruption, preserving the
first-table progress. Parent sanitization and owned-child reaping are preserved.
Original1800sverification/600sother/10sreap/180srecovery/2590sinterruption stay.

The historical1790s failure's active check is still UNKNOWN. The new code makes
an approved future attempt distinguish full quick-check time from a specific FK
table. No speedup, completed production verification, resumed partial SQLite
integrity scan or relaxed verification policy is claimed. A complete production
PASS is a hard gate; no unchanged heavy production attempt ran here.

SQLite documents whole-database vs partial integrity and FK-check semantics at
[PRAGMA](https://www.sqlite.org/pragma.html). WAL transactions remain atomic per
file, not across files; the existing durable intent/acknowledgement recovery stays.
[WAL documentation](https://www.sqlite.org/wal.html).

## Applied, measured and proposed settings

| Category | Setting/status |
|---|---|
|Applied production|Legacy5120MiB guard, A/B routing OFF, retirement OFF, paid AI OFF; collection held. Existing authorization/deadline expired, not extended|
|Qualified generated runtime|64MiB per slot,2MiB early trigger,2GiB new layout,512MiB core,100000-event lifetime ledger;250k-row/256MiB logical audit. These are finite bounds, not a5GiB-slot release|
|Temporary recovery proposal|8GiB aggregate, above small limits, retirement OFF only at startup then a separately recorded enablement gate. Not applied|
|Continuous target|5GiB per slot INCLUDING its WAL/SHM,4GiB physical trigger or72h maximum active age. Provisional, current runtime correctly rejects it|
|Continuous aggregate planning envelope|24GiB INCLUDING retained legacy, detailed below; not implemented/qualified/applied|

The 8GiB proposal cannot contain two5GiB buffers. Leaving retirement OFF would
stop when both small slots are occupied. The VM outage fixture measured61.395
**simulated** seconds of B collection after sealing A, with1667acknowledgements;
this is not live runway. At an assumed6.7events/s, the lifetime100000-event cap
alone is4.15h; slot/core/source/burst limits may stop earlier. Production runway
has not been measured. Retirement does not reset that ledger or logical core cap.

Temporary collection is **not required** to recover/stage the missing inputs:
that isolated bootstrap is already qualified. Prefer staging quiescently and
qualifying the intended continuous profile before starting collection. If a
separate finite recovery release is approved, it must enable verified retirement
of NEW generations after the tested gate, preserve legacy retirement HOLD, and
explicitly accept its bounded/unknown live runway. Do not describe it as the final
continuous5GiB design or silently promote its guards after startup.

## One proposed aggregate budget

All numbers below are planning allowances, not new runtime settings. Main/WAL/SHM
share each slot/core allowance; WAL is not omitted or counted twice.
Here5GiB means the entire physical slot,not5GiB of main-file payload plus an
uncharged WAL. If5GiB main-file capacity is required,this proposal does not meet
that requirement;an additional measured WAL allowance would be necessary.

| Term | GiB |
|---|---:|
|A main + WAL + SHM|5.000|
|B main + WAL + SHM|5.000|
|Persistent core + its WAL + SHM|4.000|
|Archive working files/buffers charged to disk, capsule and proofs|1.000|
|Verification TEMP/other temporary working files|0.500|
|Recovery reserve|1.000|
|Measured retained legacy + other observed regular FD allocation|5.000446|
|Total assigned|21.500446|
|Unassigned margin within proposed24GiB aggregate|2.499554|

A separate10GiB filesystem-free floor remains outside this aggregate. Last measured
46.38GiB free disk makes the arithmetic feasible; it is not a fresh dispatch check
or an aggregate peak proof. The core4GiB allowance needs a qualified growth,
ledger/dedup/reference-retention and restart-audit policy. Current100000events,
512MiB physical core,250000auditrows/256MiB audit bytes and10000protected-reference/
manifest bounds cannot be silently enlarged. A finite core guard still stops if
persistent structured history grows without a qualified lifecycle policy.

A single5GiB fixture already exceeds the approved2GiB whole-workspace limit before
core, B or archive working files. The proposed full envelope is19.500446GiB above
that qualification limit. No full-size trial was attempted. Full-fixture RAM and
preparation/runtime needs are NOT MEASURED, not assumed to fit512MiB/180s. Larger
qualification must be separately scoped; no sparse/copied legacy substitution.

## Throughput and outage estimates: extrapolations only

Reuse the two approved live objects: slower upload846958B/s, download721984B/s,
verification0.050744s/623236B. The small2MiB fixture compressed to781446B.
At the generated32.50KiB/s physical growth assumption, a4GiB trigger is reached in
35.85h, earlier than72h. The sealed compressed estimate is1600401408B. Upload +
initial readback + final readback + measured verification slope has a109.73minute
floor; B adds about209MiB at that assumed rate. This omits manifest/checkpoint
requests, backlog, outages, retries, core/WAL bursts and reader-drain tails.

At the small probe object size there would be2568objects. Eight progress objects
per60s cycle imply a5.35h preparation floor and about611MiB B growth. Default raw
archive cadence is3600s, not60s; neither cadence is changed on production. More
importantly, the required fresh final tail cannot fit2568objects into the current
8-object/30s limit. Therefore the5GiB retirement path remains NOT PROVEN. Cached
checks, compression extrapolation and nominal bandwidth cannot make that a PASS.
A reviewed scalable fresh/immutable-object verification strategy is required;
create-only client behavior alone is not server-side immutability evidence.

Reproduction, no cloud/prod mutation:

```sh
.venv/bin/python backend/prototype/continuous_budget.py
```

## One coherent release sequence, conditional on approval and completed gates

1. Freeze exact source/export and require push Linux CI, including the new root
   OFF→archive→enable→repeat regression and full controls. Keep PR9 draft until all
   production prerequisites qualify; do not promote a synthetic PR merge SHA.
2. Select the finite recovery profile OR qualify the5GiB continuous profile and
   its single aggregate budget first. Do not deploy8GiB/OFF as an undeclared
   intermediate. No automatic slot/core/guard expansion or deadline extension.
3. For a separately approved one-attempt maintenance scope, pin release/CI/helper/
   source/capsule/code/config/UID/paths and a fresh absolute UTC authority expiry.
   Existing manual route still rejects this recovery scope and storage-held start;
   matching production path/fence/aggregate/manual controls remain to be completed.
4. Pause all writer roles once, prove descriptor drainage, run complete legacy
   verification with per-table progress within the unchanged envelope. If any
   check/deadline/capacity gate fails:STOP,retain evidence,reap owned work and
   preserve the stopped collection state. No automatic retry or partial PASS.
5. Fence the legacy writer including main/parent/sidecars,refresh post-fence
   identity/dependencies and revalidate exact approved selected rows. Stage core/B
   with exact references,decimal/timestamp/provenance and full core verification.
   No database copies, manual WAL, unverified deletion or legacy retirement.
6. Start the sole collector with one serial feature worker; verify automatic
   active-generation dashboard/history/prediction routing. Lifecycle archives
   while the NEW-generation retirement gate is initially OFF.
7. After the first exact archive/readback/protected-reference proof,explicitly
   record enabling NEW A/B verified retirement. Test-proven small-slot path keeps
   the collector running. Legacy retirement remains independently held. Any
   corruption/missing object/readers/insufficient coverage preserves the raw file;
   two occupied slots stop collection safely rather than overwrite evidence.
8. Run one bounded functional smoke for current market/source freshness, advancing
   persistence, truthful health, dashboard/SSE and service stability. No automatic
   soak or20–30min session. Real-boundary/multi-cycle production acceptance NOT
   PERFORMED unless evidenced. Record actual interruption/revision/headroom,yield.
9. On failure after any possible new acknowledgement,stop and recover FORWARD
   from committed intents/receipts with all files preserved. Never restore DB
   contents or resume the legacy writer. Revoke temporary operator authority and
   restore only reviewed helper code/monitor state within the recovery reserve.

**No production approval request is execution-ready yet.** Outstanding gates are
complete legacy verification, production allowlist/permission/manual/aggregate
controls, live runway/core growth and full-profile capacity/final-readback scale.
This packet presents the concrete sequence for review without treating proposals
as applied settings. The latest interrupted task's bounded-resume and failure
regressions are a distinct generated checkpoint; the5GiB target stays provisional.
I7/Phase1.75,real freshness/boundary,cloud recovery/visibility/sustained operation,
raw replay and deferred knowledge/RAG stay open. Redis stays deferred.

## First exact Linux run: failed stage barrier, preserved as FAIL

be6e121 /CI42159636989: all7incremental tests passed as Linux root, including
real retirement after enablement. The repeated application handoff failed because
OFF-first startup did not enter draining until the first enabled retirement call.
The fixture refreshed its collector attachment before that call,then issued8fast
retirement attempts without another owner-thread refresh. Its own shared lease
correctly blocked unlink. The fix calls the existing rotation_tick after a held
transition,using the real collector detach path. No retries/timeouts were increased
and no reader safety rule was bypassed. Deadline validation additionally rejects
NaN/infinite/malformed boundaries rather than ignoring them. Focused7tests pass
locally; successor exact Linux CI required. Later import/integrated gates in the
failed run were NOT COMPLETED.

## Second Linux result and targeted diagnostic correction

4774946/CI42160233749 FAIL. All7incremental tests again PASS as root. The joint
fixture surfaced a collector durable_raw_save_failed hold;the underlying error
was swallowed by its task cleanup,so the first stage-barrier explanation is NOT
established as the full cause. No hold is cleared or reader check relaxed.
The new regression had forced structured synchronization on every verification
attempt;the original path used normal lifecycle scheduling after the initial
archive. Successor restores normal cycles,allows their explicit idle state,
surfaces producer failures and preserves sanitized first failure type/SQLite code/
whitelisted admission reason. The object/retry/time/resource gates stay unchanged.
A focused admission-failure diagnostic test passes;incremental suite8tests locally
passes with1root-only skip. Both failed CIs remain FAIL and later gates unexecuted.

The current worker already prioritizes new seal/drain tokens, caps pending-seal
archive spacing at30s and invokes after_archive on idle handoff cycles. Thus the
hourly default does not by itself establish the small-slot outage runway. Force-
cycle test results still cannot qualify normal live cadence or5GiB completion.

## Consolidated exact-source result: PASS for the bounded checkpoint

Frozen **101921ee00d3e89a50d02c61569bd808ed268cec**, [push Linux CI42161684724 PASS](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/42161684724).
Both test/integrated jobs passed. Exported backend428tests/14privilege skips all
covered by root raw18/application38/runtime10/incremental8/cutover2/joint2;
zero root skips. Controls123PASS/0skips include complete per-table FK progress,
late-table failure,timeout/interruption and owned reaping. Exact manifest rechecked
against frozen Git objects after suites and integrated qualification.

| Checkpoint | Disposition and exact evidence |
|---|---|
|Resumable bounded progress|PASS generated: persists across actor restart/cycles; other-slot writes continue; changed file/manifest/receipt/expired proof blocks reuse; no whole-generation materialization|
|Changed remote content after cached check|PASS fault regression: final fresh authenticated readback detects corruption, preserves raw and invalidates progress; cache alone never permits deletion|
|Operation bounds|PASS generated: bounded object budget, original cloud deadline, expired/NaN/infinite/malformed boundary refusal, SQL cooperative expiry and pre-unlink check; whole fixture180s hard supervisor retained|
|OFF→archive→enable→repeat|PASS actual generated application path: archive/readback while OFF; enable without collector restart; B→A→B→A; progress completion3,1,1lifecycle cycles;29acknowledged ticks;one feature worker;3reader-held verified retirements|
|Dashboard/prediction continuity|PASS generated/simulated clock: active generation follows collector via HTTP/SSE;fresh values advance;historical inputs equivalent;expired/stale states truthful;62HTTP requests/0timeouts|
|Concurrent latency|PASS unchanged gates: save110.821ms,heartbeat151.566ms,API74.024ms,SSE196.039ms,price1.882ms,feature27.661ms,history49.099ms,ackinterval884.527ms|
|Whole joint run|7.473s actual case;9.384s whole root suite;sampled protocol peak11145216B. Small generated local transport,not WAN/real cadence/full-scale proof|
|Full recorded-fanout bootstrap|PASS109.084s inclpreparation/cleanup,225777inputs;legacy unchanged,new acknowledgement/restart preserved;sampled peak1023041536B,RSS134516736B|
|4000-event exported ApplicationStore|PASS4000committed/4000archived,0pending/errors,20publications;save58.982ms,heartbeat329.957ms,55.753s;workspace23057141B,RSS57102336B|
|Existing cutover/recovery controls|PASS generated root UID fence/forward recovery and123controls. Production path/manual scope/post-fence binding still not implemented for this release|
|Legacy production verification|NOT PERFORMED: full quick/FK requirement preserved;new durable table diagnostics qualified;historical timeout cause/completion budget still unproven|
|5GiB slots /24GiB budget|PROPOSED/NOT PROVEN: existing slot/core/ledger/audit limits and final fresh-tail budget correctly hold;no larger fixture/guard/deadline approval inferred|

[Sanitized exact artifacts](evidence/resumable-verification-101921e.json). Both
be6e121/42159636989 and4774946/42160233749 remain FAIL. The passing successor
restored representative normal scheduling and the owner-thread stage refresh;
it does not retrospectively prove the swallowed error's original cause. Its new
sanitized diagnostic makes any future first admission/SQLite failure observable.
No producer hold was cleared and no extra retries or timeouts were introduced.

### Cadence and transfer correction for the proposed scale

Existing pending seal/drain tokens already prioritize archive and cap that stage's
spacing at30s;idle handoff cycles can resume verification using the original cloud
budget. The hourly base cadence alone therefore cannot calculate live outage
runway. The5.35h model above is explicitly an assumed60s scenario,not measured
scheduler cadence. The corrected joint regression uses normal scheduling for
progress after the initial archive,not force-sync on every verification attempt.

The calculator's109.73minute two-read estimate is the BASELINE path (initial
readback + final recheck). Selecting the new progress preparation adds at least
one additional download/verification pass: for1600401408B this contributes about
2347s, making a roughly148.8minute lower bound and roughly283MiB B growth at the
assumed32.5KiB/s. Retries/invalidation,metadata/checkpoint latency and reader tails
remain additional. Neither estimate overcomes the8-object/30s final fresh-tail
HOLD or qualifies a5GiB generation. Public Supabase access policies distinguish
INSERT from UPDATE/DELETE;create-only client requests are not a server immutability
guarantee. See [official Storage access control](https://supabase.com/docs/guides/storage/security/access-control).

**Release disposition:** bounded generated checkpoint PASS; production continuous
release NO-GO. Do not enable the24GiB/5GiB planning profile or ship retirement OFF
as continuous operation. First qualify scalable final verification plus core/
ledger/admission/aggregate controls under a separately reviewed larger fixture;
complete the unchanged legacy verification gate and matching production control
scope. The conditional procedure above remains for review,not execution-ready
production approval. No new VM/cloud scan,retirement,guard change,service restart,
helper installation or production operation occurred. I7/Phase1.75 stayOPEN.
