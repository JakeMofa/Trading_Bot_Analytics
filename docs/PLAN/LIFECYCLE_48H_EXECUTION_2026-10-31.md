# 48-hour lifecycle execution evidence — October31,2026

The official roadmap remains `INTELLIGENCE_REBUILD_PLAN.md`. This report records
execution evidence and gates; it does not establish completion of Phase1.75.

## Authorized bridge: PASS

- Exact helper commit`8187465a0af3965f0f1d811621710afc3358ef70`,
  [CI41263032555](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41263032555) PASS.
- Helper SHA256`d35433333d91a205d6f56169b22532679faea9c06a177e5a4cb237ed5cd2eafa` exported from that commit and verified on VM.
- Changed only the literal guard4096->5120. Configuration bytes/owner/mode preserved
  except that value; no retained configuration backup or credentials in evidence.
- Applied **2026-11-01T01:56:47.671426+00:00 UTC /2026-10-31T20:56:47.671426-05:00 Chicago**.
- API restart returned in~0.393s; no application checkout. API PID10915->17165;
  ensemble849/lifecycle843 and monitoring unchanged; zero automatic restarts.
- Passed **300.007s continuous observation**,
  114 samples total, one reset due the existing rollover
  delay. Both feeds/live timestamps, current market, private API, dashboard/SSE
  verified. Source collection resumed; previous gap is not assumed backfilled.
- Actual runtime guard5120, application`d56b4a7`, paid AI/retention OFF,
  paid credentials absent. DB4,283,228,160/WAL18,160,992 bytes at02:06:48UTC.
- Review due **2026-11-02T01:56:47.671426+00:00 UTC /2026-11-01T19:56:47.671426-06:00 Chicago**. Deadline uses UTC across
  the daylight-saving transition. This is a review deadline, not automatic limit
  reversion. Ceiling remains5120 and is not permanent until the24h soak passes.

## Retention candidate: local tests, Linux qualification pending

The candidate replaces Python manifest-envelope arrays/sorting with current SQL
range counts and bounded joins to TEMP exact approved identities. A TEMP indexed
cache holds only pure validity of exact strings, prepared outside the writer lock.
Fresh global scans of both raw tables find/validate unseen timestamp strings.
Range coverage, references, anchor and eligibility are still checked under the
same BEGIN IMMEDIATE as DELETE. No broad-range deletion or weakened archive proof.

New writer target250ms, deadline500ms, measured including commit. Interruption
before commit rolls back; a commit overrun records committed_rows and stops later
batches rather than falsely claiming those rows were rolled back. TEMP bookkeeping
and100ms handoff occur outside the main writer transaction. Qualification will use
1000-row batches; collector busy timeout remains5000ms.

Local validation: **194 backend tests PASS (one Linux-only harness self-test skipped
on Mac),51 deployment/control tests PASS**, compile/diff PASS. Existing archive,
mutation, new-identity, timestamp and late-reference tests pass. Deadline tests
cover rollback and the distinction between a completed commit and rollback.

`backend/qualify_retention_sql.py` accepts only generated fixtures, not a DB copy.
It loads actual deployed save/RAM code and verifies its SHA on production-guarded
runs. Actual last-rowid point lookups gave cardinality upper bounds578343
observations/1684881 stream events; they are not full row counts. Generated trials
use that global scale plus the previously qualified40031/196509 eligible-identity
scale. Passing this profile alone will not qualify a larger cleanup plan.

Each Linux trial:180s total (170s work +10s cleanup),512MiB address-space limit per
process,2GiB aggregate generated/TEMP disk guard, actual save every150ms and50ms
heartbeat. Production HTTP probes every5s; unexpected stopped/degraded feeds or
API timeout abort the fixture test. Stop after the first failed gate. Three full
successful trials required; warm-cache Mac benchmarks are not R5/R6 PASS.
Synthetic manifest claims are performance fixtures, not cloud verification.

## Remaining gates

R5/R6 remains STOP until actual Linux qualification passes. No production retention,
DELETE, schema/index change, full integrity/FK scan, archive recovery proof or
application release has occurred. Then follow the approved order: archive/readback
and full audit, exact raw-row recovery manifest, controlled<=1000-row first cleanup,
qualified indexes/freshness release, lifecycle-only enablement and24h soak.

No DB copies/snapshots, VACUUM, manual WAL, new resources/network changes, paid AI or
Phase2. Local evidence: `/Users/jake/Documents/ChatGPT/TradebotAnalytics/evidence/phase175-baseline/lifecycle-implementation-20261031/`.

## First Linux qualification — STOP

Candidate1c714e4 passed exact CI195backend/51controls. At647089 observations and
1867728 stream rows, trial1 reached the500ms writer limit (0.500101783s), with
zero committed fixture deletes. It stopped; trials2/3 were not run. Fixture actor
completed95saves and95RAM updates, no errors, maxsave431ms/heartbeat452ms. No
production interference was detected. Generated data was removed by the harness.

A local ordered SQL set-merge candidate now replaces per-value membership probes.
Binary collation and all current-snapshot checks are retained; the deadline is
unchanged. This remains R5/R6 STOP until a new exact-CI candidate completes all
three Linux trials. First-attempt evidence is preserved separately.

## Revised Linux qualification — STOP; guard diagnostics incomplete

Candidate2753c4a passed [exact CI41265091345](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41265091345),196backend/51controls. The revised647996-observation/1871555-stream profile stopped after40.725s during fixture generation when the production health guard raised RuntimeError. Retention apply had not begun. The older guard recorded only the exception class; the precise condition and cause are unknown. This is not evidence that the revised merge exceeded its writer budget. Trials2/3 were not run.

Follow-up02:33:46UTC confirmed unchanged d56b4a7, active API17165/ensemble849/lifecycle843, zero automatic restarts, live feeds, guard5120 and retention/paid AI OFF. DB4300345344/WAL18160992bytes; free disk51556388864bytes. Features remain stale. A subsequent90-second read-only baseline (02:37:53–02:39:23UTC) passed19/19 collector/feed samples; that does not establish the earlier failure's cause. Both generated-fixture staging directories were removed after process/content/hash checks.

Local diagnostic improvements now retain sanitized reason, feed status/timestamp/age and fixture stage without arbitrary response bodies.197backend tests PASS (one Linux-only test skipped),51controls PASS; unchanged deadlines and resource caps. No additional stress test or production cleanup was attempted.

**R5/R6 STOP; I7 and Phase1.75 OPEN.** Next resolve the guarded health condition and obtain three complete qualified Linux trials. All archive, integrity/FK, recovery-manifest, production cleanup, index/freshness release, lifecycle enablement and24-hour soak gates remain outstanding. Temporary5120 bridge review remains due2026-11-02T01:56:47.671426Z (November1,19:56CST); no automatic extension or ceiling increase.

## Bounded diagnosis — exact operation measured, qualification STOP

[Candidate44cb0ec CI41270810424](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41270810424) PASS;197 local backend tests (one Linux-only skipped)/51controls PASS. The initially restricted local backend run could not start its socket-based process-control worker; the complete suite passed with local socket access.

Generated Linux diagnostic began2026-11-01T03:52:10.489725Z with652932 observations/1890841 stream rows. It reached retention apply and failed at **timestamp_revalidation:sqlite_progress**, writer0.511735474s vs500ms limit, failing transaction committed0. Production guard failures0; fixture collector170saves/170RAM updates,0errors, maxsave532.6ms/heartbeat561.9ms. Preparation92.368s, total118.760s, peakfixture482989381bytes, maxRSS102216KiB. No trials2/3. This directly identifies the current blocker; the earlier health-guard failure remains unidentifiable from available historical logs.

A local generated EXPLAIN benchmark confirmed global scans plus an observations TEMP timestamp sort. At200k/600k rows shared-merge totals~196–202ms, scoped-cache merge~183–194ms, scoped probes~607–640ms over three warm repetitions. Neither alternative demonstrates sufficient improvement; no speculative algorithm fix was shipped. This is diagnostic evidence, not R5/R6 qualification.

All generated/staged files removed after process/content/hash checks. Post-test03:55:23UTC: production d56b4a7 unchanged, API17165/ensemble849/lifecycle843 unchanged, zero automatic restarts, both feeds live, paid AI/retention OFF, guard5120. DB4350054400/WAL18160992bytes (~954.1MiB guard headroom), free51506302976bytes. No production rows deleted, index installed or service/configuration changed in this diagnosis.

**STOP is retained as required by the approved plan.** Next develop an evidenced replacement for the expensive current-transaction timestamp proof, preserving strict formats and all safety checks, before another qualification attempt. Three full passing trials, archive verification, integrity/FK audit, recovery proof and controlled cleanup remain required. Bridge review deadline unchanged; I7/Phase1.75 remain open.

## Approved NOT IN candidate — implemented, benchmarked, rejected

Read-only production preflight2026-11-01T04:16:29UTC showed unchanged d56b4a7 and service PIDs17165/849/843, zero automatic restarts, both feeds live, guard5120, retention/paid AI OFF. DB4362436608/WAL18160992bytes; free51493785600bytes. Indexed maximum-rowid reads provided upper bounds585752 observations/1715411 streams; generated benchmark profile654328/1896953 includes10% plus10k margin.

The planned candidate passed correctness tests and used the TEMP primary-key IN-OPERATOR with explicit binary and NULL handling. At representative timestamp overlap, old/recent populations and97market/3kind groups, three local observation runs measured candidate1.652084/1.594193/1.723080s versus merge0.717894/0.332051/0.318074s. Median candidate was~5x slower. An earlier disjoint-timestamp fixture reached the same rejection. Stream merge was unchanged. Both experiments were generated-only local diagnostics, not production speed or R5 qualification.

The runtime candidate was reverted. Its exact query remains only in a generated-only reproducible benchmark, `backend/benchmark_retention_timestamps.py`. Added separate per-transaction phase timings and partial failure timings; retained NULL, case-distinct malformed/calendar, optional-index and unknown-dedup regression tests.199backend tests PASS (one Linux-only skipped),51controls PASS, tiny benchmark/diff PASS. No additional VM stress trial, production deployment, deletion/index/service/config change.

The approved plan requires rejecting a slower local candidate and retaining STOP if no compliant implementation is demonstrated. **R5/R6 remains STOP.** A fresh global timestamp check on both tables must still fit the500ms writer budget; neither existing merge nor this candidate qualifies. No safety requirement was weakened to manufacture a pass. Remaining release/cleanup/freshness/lifecycle/soak stages are blocked, and Phase1.75 is not complete. Temporary bridge review deadline unchanged.

### Bounded cache experiment — rejected without VM use

A follow-up local experiment set TEMP cache explicitly to2000KiB versus128MiB with the same representative654328/1896953 generated profile. Cached candidate observations0.547290/0.560505/0.537571s, median547.3ms; stream merge median342.7ms. Existing merge medians313.3/329.0ms. The cached observation check alone still exceeds500ms locally. No production cache setting changed, no runtime candidate retained, and no additional Linux qualification attempted. Reproducible benchmark now includes both settings. This does not prove that every possible compliant implementation is impossible; it rejects these measured candidates.

Diagnostics milestone6ef8ce2 [exact CI41272687425](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41272687425) PASS. R5/R6 remains STOP under the approved failure rule. End-to-end lifecycle/freshness delivery is unfinished, not declared complete by this diagnostic milestone.

## Native timestamp proof candidate — local safety and speed evidence

The user requested finding another way after SQL candidates failed. A native SQLite scalar validator now performs the same fresh global timestamp proof directly on both current raw tables under every writer transaction, replacing sort/membership work with fixed-format/calendar validation. It caches no mutable facts. Native source is small, reviewed C with byte-length checks before offsets and strict Python-contract equivalence. No schema/index changes, application configuration or public API changes.

Local generated prototype654328/1896953 rows: observation native50.3/51.6/52.0ms, stream146.0/161.3/144.0ms; median sum197.6ms vs merge649.7ms. This is local warm-cache evidence, not a qualification pass. Initial equivalence16701cases; retained tests add invalid-character/Unicode/NUL mutations and run the entire existing retention safety suite with the native path.203backend tests PASS (one Linux-only skipped),51controls PASS.

Loader pins reviewed source SHA and binary SHA, rejects malformed artifacts/symlinks/unsafe permissions, and disables extension loading after load. Native scalar is DIRECTONLY; missing artifact leaves portable safety path and unchanged deadline, while qualification explicitly requires native. CI builds the Linux artifact; the existing production VM has neither compiler nor headers, and no package install is planned. Source/build/qualification files must match exact passing CI before any isolated Linux trial. **R5/R6 remains STOP pending three full native-required qualification passes.** No production cleanup or release occurred.

Implementation follows [SQLite application-defined functions](https://www.sqlite.org/appfunc.html) and [extension-loading guidance](https://www.sqlite.org/c3ref/load_extension.html); Python supports controlled C-API-only loading where available, followed by immediate disablement.

## First native Linux result — total-budget STOP

Candidatea3e1593 [exact CI41273629417](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41273629417) passed and artifact13070079047's source/binary hashes were verified. Trial began2026-11-01T04:45:59.129643Z at656041 observations/1904238 streams. Native engine loaded; preparation71.842s, then apply hit the170s work deadline. Cleanup brought total to186.860s, exceeding180s. No RetentionBudgetError was reported, but missing partial timing prevents claiming every writer duration passed. Collector726saves/726RAM updates,0errors, maxsave331.7ms/heartbeat382.2ms; production guard failures0. Peakfixture486200645bytes/maxRSS138160KiB. Trials2/3 not run.

All fixture/staging files removed after process/content/hash checks. Fresh05:29:52UTC production remains d56b4a7, same PIDs/zero restarts, both feeds live, guard5120, paid AI/retention OFF. DB4405575680/WAL18366992bytes, free51450019840bytes. No production application/data/configuration changes.

Follow-up: use identical native proof during read-only planning instead of Python callbacks for every raw timestamp; commit generated SETUP in20000-row groups while preserving all rows/indexes/identities. Retention batches remain1000 and handoff100ms. Add partial committed-work/phase evidence and an outer177s terminate + bounded recovery supervisor so the entire fixture lifecycle must finish within180s. An unreaped fixture is explicitly retained/reported, never unlinked as if safe. FourMiB of2GiB reserved for metadata overhead;512MiB/process unchanged. No manual WAL action or deadline extension.205backend tests PASS (two Linux-only skipped)/51controls PASS; exact Linux CI and artifact required before a new full trial. R5/R6 and later production gates remain STOP.

## Supervised follow-up — writer commit STOP with complete attribution

Candidate71402ec [exact CI41277408489](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41277408489) passed; artifact13072290252 verified. Trial05:35:04UTC generated658953 observations/1914798 streams. Preparation50.382s, supervised total54.232s. It stopped after a1000-row fixture commit finished at502.769ms; partial result records7000fixture rows committed. Completed commits were not restored or described as rolled back. No production rows deleted.

Failing transaction: timestamp observations133.6ms +stream330.7ms =464.4ms; manifest coverage3.5ms, selection1.8ms, delete8.8ms, commit24.3ms. Actual fixture collector14saves/14RAM updates,0errors, maximum save432.8ms/heartbeat483.8ms; production guard failures0. Peakfixture489052781bytes, maxRSS99272KiB. No trials2/3. Staging removed after process/content/hash checks;05:38:38UTC production remained d56b4a7 with same PIDs/zero restarts, both feeds live, guard5120 and retention/paid AI OFF.

Next candidate adds a24-byte positive calendar-prefix validity cache inside the native function. Every current row still undergoes complete length/fraction/UTC checks; exact prefix comparison reuses only a pure calendar fact. Fresh global scan, row identities and eligibility checks unchanged. Cache storage is connection-local, bounded and freed by SQLite. See [SQLite function user data/destructor contract](https://www.sqlite.org/c3ref/create_function.html).

Fixture timestamps now span12h old and46h recent windows, and explicit planned-eligibility assertions preserve the full expected workload. This prevents a cache benchmark based solely on artificially dense timestamps. Local day-scale654328/1896953 O2-prototype checks: native medians46.1ms observations/124.5ms streams; not Linux qualification.206backend/51controls PASS (two Linux-only skipped). Final native build uses portable O3 without relaxed arithmetic/architecture flags and passes full parser/safety tests. Exact new CI/artifact and three passing Linux trials still required; R5/R6 STOP, later gates blocked.

## Prefix trial STOP; indexed-invalid proof candidate

Prefix829d257 CI41278263026 passed but indexed-time distributions exposed another global-proof overrun:05:49:56UTC generated659812/1918076,3000fixture rows committed then timestamp revalidation500.149ms caused rollback of that transaction/STOP. Preparation63.182s, supervised65.978s; collector8saves/8RAM,0errors,maxsave439.8ms/heartbeat488.7ms; no production-health failures. No later trials. Staging cleaned;05:53:56UTC production remained unchanged/live with guard5120 and retention/paid AI OFF.

New candidate: ordinary partial indexes contain exactly invalid raw timestamps. SQLite transactionally updates these indexes for every writer. Retention freshly checks exact definitions and probes both invalid sets in the same writer transaction as its exact-identity deletes. This preserves global validity proof and removes repeated raw scanning. It caches no mutable safety facts and requires no native library. Invalid raw rows remain stored and block cleanup.

Built-in-only predicate matches strict raw parser across16895cases, including NUL/Unicode/BLOB/NOCASE/calendar boundaries; all existing safety cases also run with guards installed before seeding. Foreign writers require no application hooks or new code. Local representative day-scale654328/1896953: build4.085s,8192bytes growth; median complete definition+guard probes26.4/19.2us.210backend/51controls PASS (two Linux-only skipped). Exact CI and three guarded indexed Linux trials required.

Guard installation is an explicit production schema prerequisite to cleanup, not a startup migration: it remains PENDING qualified operator controls, fresh readiness and the archive/integrity/recovery gates. Source-time indexes remain after cleanup/capacity qualification. No production guard index has been created. See [SQLite partial index semantics](https://www.sqlite.org/partialindex.html).

## Indexed trial — timestamp bottleneck cleared; stream-write STOP

3938fb4 exact CI41279502588 PASS.06:10:04UTC trial660998/1922598 built guards7.471s. Fresh global timestamp check83.2us; all40030observations completed (41batches,max57.3ms),1000streams committed, then source deletion stopped503.134ms: coverage112.4ms, selection6.3ms, delete384.2ms before rollback. Preparation64.282s, supervised108.123s; collector285saves/285RAM,0errors,maxsave434.8ms/heartbeat446.6ms; production guard failures0. No trials2/3. Staging cleaned, no production deletion/index/release/config change.06:16:22UTC production d56b4a7/samePIDs/zero restarts, feeds live, guard5120/paid AI/retention OFF; health degraded around rollover.

Next narrow candidate retains per-row exact identities (set-based alternatives did not improve local timing). Uses the existing archive cursor where verified, current full manifest counts split into indexed interior seconds and precise canonical boundaries AFTER fresh global raw-format proof, and16MiB MAIN cache on the private retention connection restored on every exit. No cutoff/candidate clipping, current-fact cache, stream-rowid identity, collector setting or WAL change.300range-equivalence checks cover widths, fractions, ties and midnight/month boundaries.

Local1.92m-row WAL diagnostics: range median46.3ms ->8.1ms; default per-row9.0ms, covered cursor11.2ms, cursor+16MiB6.2ms.213backend/51controls PASS (two Linux-only skipped). Not Linux qualification. Connection cache behavior follows [SQLite cache_size documentation](https://www.sqlite.org/pragma.html#pragma_cache_size); no persistent setting changes. R5/R6 STOP pending exact CI and three full trials; production guards/cleanup and later gates remain pending.

## Working-set trial STOP; unlocked warming candidate

e088ac2 CI41281335177 PASS.06:35:01UTC at662540/1928469: guards8.063s/preparation63.390s/supervised74.772s. All40030observations completed; first stream transaction stopped505.094ms (global validity0.472ms/coverage36.184ms/selection4.143ms/delete464.178ms), rolled back;0stream commits. Collector69saves/69RAM,0errors,maxsave532.6ms/heartbeat583.0ms; production guard failures0. No later trials.

Follow-up warms only static approved-identity pages with discarded SELECT values outside any transaction; all safety checks and selection are freshly repeated under the writer. Mutations after warming still block deletion. Frozen approved TEMP identities are inserted in key order; private MAIN32MiB/TEMP16MiB targets are restored exactly on success/failure, within512MiB/process. No application/storage/collector/WAL setting change or relaxed deadline. Local196509-row preparation1.896s->0.937s, not qualification. Added static-prep/unlocked-warm timings.214backend/51controls PASS (two Linux-only skipped), exact CI and three full Linux trials pending. No production guard indexes/deletion/release occurred; all later gates remain pending.


## Qualification deadline diagnostics and observed ID profile — November 1, 2026

Candidate b5ef255 / exact CI41282322948 PASS ran at06:49:59UTC with663455 observations/1931647 streams. The supervisor stopped it at177.151s (exit-15); no complete child report survived. This is STOP, not evidence that writer/collector gates passed. No subsequent trials ran. Exact-hash staging cleanup confirmed no fixture process/files remained. At07:00:41UTC production was still d56b4a7, same service PIDs/zero restarts, retention/paid AI OFF and guard5120; Coinbase live, Polymarket marked stale around rollover. No production schema, rows, code, settings or services changed.

Added atomic provisional STOP reports throughout fixture preparation and unlocked apply checkpoints, retaining stage, committed counts and phase timings even if cleanup is killed. Reporting never runs under the main writer lock and cannot certify an incomplete pass. Limits remain500ms/180s/512MiB/2GiB.

Read-only first100/last100 stream-ID shape samples at06:57:43UTC were all Coinbase ASCII digits of length10. This is a bounded sample, not a full-table assertion. Added explicit synthetic ten-digit-ID profile; default variable-width adversarial profile remains available and its failures remain recorded. Cardinality, full deletion workload, strict string identities, safety checks and deadlines are unchanged. Future passing results apply only to the tested profile; unfamiliar production scopes require qualification rather than numeric coercion.

Prepared a pure raw-row recovery verifier: bounded authenticated-readback bytes supplied by caller, checksum/size/count/boundary validation, exact Decimal JSON comparison and byte-exact original raw-column reconstruction in memory. Four tests pass. No cloud readback or production recovery manifest has been completed; R7 remains pending. Local220 backend tests pass (two Linux-only skipped),51 controls pass. R5/R6 STOP; production guard installation, cleanup, freshness release and24h soak remain blocked pending evidence.


## TEMP pending-table scan repaired — November 1, 2026

498284a exact CI41283166554 PASS. Observed-shape trial at07:03:18UTC used664240 observations/1934508 streams. STOP at173.062s from170s work alarm, not a writer overrun: all40030observations committed, max79.63ms;3000streams committed, max42.39ms and108.99ms total stream writer time. Collector737saves/737RAM,0errors,maxsave58.34ms/heartbeat129.54ms; production guard failures0. Full workload did not complete, so R5/R6 remain STOP. No later trials ran.

Incremental reports exposed the precise unbounded operation: outside-writer TEMP bookkeeping deleted by(source,event_id,received_at), omitting the leading stamp of its WITHOUT ROWID primary key. EXPLAIN confirmed a full pending-table scan per identity. Repaired bookkeeping includes canonical stamp plus all three original exact string identity fields; no current eligibility, coverage, cutoff, protected-reference or deletion check changed. Added a per-batch unlocked-bookkeeping timing and checkpoint.

Generated196509-row local comparison: old10removals178.38ms; new1000removals4.76ms. EXPLAIN changes SCAN to SEARCH USING PRIMARY KEY on all four columns. Regression verifies indexed lookup and distinct007/7/70 identities.221local backend/51controls pass (two Linux-only skipped). Exact CI and three full Linux trials required before release/cleanup. The observed10-digit profile remains distinct from adversarial variable-width qualification; no claim that untested shapes are qualified. Production unchanged; full archive/integrity/R7 gates and I7 freshness/rollover remain open.


## R5/R6 qualified on existing Linux VM — November 1, 2026

Exact candidate e0d311edcceb4be15811c55f6f8650484d107930, CI41283537103 PASS. Three complete generated-only trials passed: 101.998s / maxwriter87.44ms; 126.860s / maxwriter79.36ms; 77.612s / maxwriter97.61ms. Each deleted40030 observations and196509 streams at refreshed representative cardinality (664603–665010 observations/1936125–1938116 streams). Actual deployed save→RAM order,150ms save attempts,50ms heartbeat,500ms writer/180s total/512MiB-process/2GiB-fixture limits retained. All actor errors0, saves=RAM; maxsave108.52ms/heartbeat156.76ms; production guard failures0. No rows were deleted from production.

The complete TEMP primary-key repair removed the hidden outside-writer repeated scan. Generated benchmark old10removals178.38ms vsnew1000removals4.76ms; full Linux stream-bookkeeping now completes rather than timing out. Qualification applies to the explicit observed10-digit Coinbase key profile. Variable-width adversarial results remain historical failures; unfamiliar production scopes require qualification, never coercion. Generated payloads are synthetic, not a replica of production bytes. First actual cleanup remains a separately supervised≤1000-row trial.

R5 performance and R6 collector coexistence PASS for this tested profile. R0–R4 accepted historical evidence preserved. R7 exact raw-row recovery/archive readback and fresh full production SQLite verification remain PENDING; R8–R17/I7/Phase1.75 remain OPEN. Old board statements requiring snapshots or claiming no optimization authorization are superseded by the user's subsequent implementation plan; no copies/snapshots were made.

Exact-hash generated staging cleanup verified.07:18:46UTC production remained d56b4a7/same PIDs/zero restarts, bothfeeds live, retention/paidAI OFF,guard5120, DB4469121024/WAL18366992 bytes. This is a recorded sample, not an ongoing-health guarantee. Bridge review due2026-11-02T01:56:47.671426Z remains unchanged.

Prepared the next controls: TEMP exact-full-row recovery guard blocks mutation/unapproved deletes transactionally; its indexes avoid repeating the pending-scan mistake. Prepared explicit operator-only read-only quick/FK audit with30min work+3min recovery reserve, independent bounded/reaped SQLite child, partial-stop recovery, restoration of every stopped writer even after a restart failure, unchanged configuration and measured raw receive gaps. Default is plan-only; no audit/service stop/index installation has run.222local backend/57controls PASS (two Linux-only backend skips); require exact new helper CI, hash-pinned export and safe preflight before supervised production maintenance. No consumed I7 exception reuse.


### Integrity-child interruption containment

6201867 exact CI41284484947 PASS (222 backend plus57controls on Linux). Before production use, the audit helper now owns its read-only child process group directly: timeout or parent interruption terminates/kills/reaps it before service recovery. Added real Linux kill/reap and parent-interruption regressions. Local59controls pass with two Linux-only skips; backend unchanged. Requires new exact helper CI. No production maintenance has run; no live process or service was signalled by these generated/unit tests.


### Bounded private-archive recovery preparation

Added a default-plan-only operator that selects at most1000 raw rows through original full manifest ranges, reads applicable private objects using the existing authenticated download client, verifies checksum/compressed size/count/boundaries, preserves original raw columns and demonstrates in-memory reconstruction. It freezes the48h cutoff and exact approved identities; it never deletes, uploads, enables flags or creates indexes. Fresh eligibility/protected-reference checks remain required in the deletion transaction. Private proof publication is immutable and0600; diagnostic output includes only stage/type/count/hash, never credentials or raw payload.227local backend tests PASS (two Linux-only skips); requires exact CI before any production readback. Production R7 proof remains PENDING.

Supabase docs/changelog verified: private download remains supported; October12 TLS cipher notice does not change the download contract. Official reference: https://supabase.com/docs/reference/python/storage-from-download . No Supabase schema/access-policy change.

Production integrity helper7e5e7d2 CI41284629743 PASS; read-only preflight PASS, then supervised full quick/FK audit started2026-11-01T07:26:19.086790Z. Writer services intentionally paused; recovery reserve3min within30min work budget. This entry records IN_PROGRESS, not a passing audit or currently-live collection claim. No copies/snapshots/deletion/manual WAL operations.


### Full SQLite checks passed; verifier STOP and independent recovery

Production audit7e5e7d2/CI41284629743: quick_check PASS782.745s, foreign_key_check PASS78.092s. The attempt remains STOP: recovery verifier incorrectly indexed MainPID on tradebot-soak.timer, which has no process PID. This was a helper defect, not an observed failed service restart. Do not relabel the original attempt as successful. Corrected timer checks use ActiveState/UnitFileState; regression exercises actual recovery logic with a PID-less timer. Unreaped-child failures now retain PID/manual-recovery status.61local controls PASS (two Linux-only skips); backend227unchanged.

Independent read-only follow-up confirmed all three services active, zero automatic restarts, flagsOFF, guard5120, original appd56b4a7. Twelve5s feed/API samples passed, max39.34ms, both feed timestamps advancing. Monitoring timer active; envmtime2026-11-01T01:56:47.667263Z matches bridge application. API started07:40:41UTC. Persisted Coinbase received gap862.791950s:07:26:19.440384→07:40:42.232334UTC. Observation gap unavailable within bounded256recent rows; no broader scan/backfill claim. No additional restart or repeated integrity scan was used for confirmation.

Full SQLite verification is now evidenced separately from the failed overall maintenance report; independent recovery is PASS. R7 private archive/exact-row proof remains PENDING, no production deletion/guard indexes/application deployment. Evidence: production-integrity-7e5e7d2.jsonl, post-integrity-keyerror-runtime.json, independent-integrity-recovery.jsonl in lifecycle-implementation-20261031. Continue with exact-CI read-only archive recovery preparation, preserving all remaining gates and the existing bridge deadline.


## R7 first bounded recovery scope prepared; isolated retention release qualified

007a439 / CI41285656414 PASS performed authenticated private readback for three applicable observation archives. All size/SHA/count/identity-boundary checks passed;1000 proposed observation rows reconstructed in memory with exact raw columns. Fixed48h cutoff2026-10-30T07:50:12.491770Z. Private0600 proof /opt/tradebot/data/retention-recovery/observations-20261101T075011Z-007a439.json, SHA25645f1a977bc74f10a319970b00c3986670bb634310f5a0fecad27ce45a6a76c91. This is exact raw-delete recovery, not a database snapshot/full disaster-recovery backup. No rows deleted; proof status PREPARED_NOT_APPLIED. R7 PASS applies ONLY to this exact scope; later batches require their own verified proofs and fresh current checks.

Production reference metadata at07:54:48UTC: prediction_context_links rowid upper20, unindexed lookup. No large reference-table bottleneck evidenced; no reference-query/index change made. R5/R6 accepted three-trial profile remains unchanged.

Isolated retention/health candidate c1249503ffe7d4e5cb31e4120c9375d1488ce024 pushed to the existing remote deployment branch, CI41287429837 PASS;214local tests (two Linux-only skips), exact CI tests passed. No app deployment. API health correction plus qualified retention/proof modules only; existing collector/streaming/feature source and configuration unchanged. Scoped regression asserts the exact legacy seconds-format zero-microsecond writer output; deferred writer normalization was excluded rather than importing future feature code. Both legal raw formats remain strictly checked. Working branch/checkout unchanged; stale local deployment branch eaca36c preserved, remote advanced normally fromd56b4a7.

Prepared explicit timestamp-guard installer: requires full SQLite verification evidence plus independent recovered collection, creates only the two reviewed guard indexes in one transaction during supervised maintenance. No price indexes/startup DDL/deletion/config change. Enforces5120MiB physical cap with64MiB commit reserve,512MiB process limit,30min work+3min recovery. Invalid raw timestamps/deadline/storage/schema errors stop and roll back uncommitted DDL; committed late indexes are reported and never blindly dropped. Current schema is recorded after every completed child.68local controls PASS (two Linux-only skips); require exact new CI before use. Receipt-gap baseline now captured after all writers stop, avoiding saves that can arrive between preflight and shutdown.

Next: install timestamp guards only after exact helper CI/fresh preflight, restore/verify collection, then use the exact-CI candidate and protected recovery scope for the first≤1000-row cleanup. Full integrity passed separately from the original maintenance attempt's verifier STOP; independent recovery PASS. No guard index, cleanup, automatic retention, paid AI, freshness release or Phase2 has occurred. Bridge deadline unchanged.


### Timestamp-install attempt STOP before DDL; bounded owner-drain correction

2a1e5b8 CI41287687023 PASS attempted maintenance08:13:33UTC. STOP before its build operation; guard index catalog confirmed empty afterward. Recovery PASS; all three writer services active/zero automatic restarts. No rows deleted. The remaining-descriptor check failed before final paused-baseline capture; its original error omitted PID/reason. Exact past owner is UNKNOWN, not asserted to be monitoring. Current owner inventory shows only expected API/ensemble connections; read-only repeated preflight has no own leaked SQLite descriptors, before or after normal garbage collection.

Corrected control waits for zero descriptors within the SAME10s drain deadline, captures phase/PID/descriptor/access mode on failure, exempts nobody and never signals unknown owners. This addresses short close races without changing the gate. If no final paused baseline was captured, future recovery reports no misleading preflight-derived gap. Original attempt's Coinbase0.5105s/observation81.463531s figures used the preflight baseline and are not certified precise maintenance gaps. Collection-interruption upper bound100.710535s; no second full integrity scan or data operation occurred.

70local controls PASS (two Linux-only skips), backend227unchanged. Exact new CI required before a revised maintenance attempt. R5/R6 and exact R7 scope preserved; timestamp guards/first cleanup/continuous retention/I7 freshness remain pending. No budget, guard ceiling, flags, configuration, infrastructure or branch change.


## Timestamp guards installed; first exact cleanup operator tested

Revised4d6747a / exact CI41289317190 maintenance PASS. Both guard indexes committed in116.327s, both current invalid sets empty. DB+WAL4503465984→4503478272 bytes (+12288); no raw deletion. Writer services restored and advancing feeds verified; automatic retention/paidAI OFF. Measured final-paused-to-first-recovered raw receipt gaps: observations222.349703s, streams222.527555s; upper interruption237.550328s. Original2a attempt remains STOP with unknown past owner. This revised attempt drained immediately (6.16ms), so no claim that a particular prior owner/race was identified.

First-scope operator adds exact full-row recovery protection, runtime denial of structured writes/other-dataset deletes/attachments, discarded full-row page warming outside the writer, and in-memory DELETE identity callbacks. Callbacks do not inflate total_changes and are reconciled against actual committed counts; rollback callbacks are never reported as committed, and late commit overruns remain STOP with committed rows reported. All original current coverage/reference/anchor/global timestamp checks stay inside the500ms core transaction; no mutable safety cache. Post-checks cover every child table referencing the affected raw table; full pre-delete quick/FK evidence remains preserved.

234local backend tests PASS (two Linux-only skips), including late-reference, mutation-after-warm, structured-delete denial and committed-overrun cases;70controls previously PASS. Production first cleanup NOT RUN. Require exact helper/release CI, protect the private R7 artifact hash, then execute only this≤1000-row scope and verify collector/feed/API behavior before any later bounded catch-up. No automatic retention, price indexes, freshness application release, permanent cap promotion or Phase2.

## First authorized production cleanup trial STOP; dense-range coverage fix

Dedicated execution checkpoint November1,2026: c7061f70b20ffe0607f3bf2f07d7a7926b1f810d is pushed; exact CI41310818560 PASS. Isolated deployment candidate7a43fcd0ad58e9d58ee81e6d584a8f7e75fac899 advances only four trial files fromc124950; exact CI41318630094 PASS,221local backend tests (two Linux-only skipped). Candidate code staged separately, application remainsd56b4a7; no app deployment or service restart. Unrelated596-line roadmap edits and AGENTS.md preserved.

User explicitly approved the single≤1000-row recovery-proved observation cleanup after automatic approval review initially rejected deletion under read-only instructions. Initial rejected invocation did not run. Executed trial14:58:47UTC STOP at manifest_coverage:sqlite_progress, writer523.097ms; timestamp proof1.131ms, coverage521.554ms. **Committed0 rows, attempted delete callbacks0.** Immutable private report /opt/tradebot/data/retention-recovery/first-trial-7a43fcd.json SHA2565786c59ede7ae6d8c80969dcf66b28c22d5dd776fd212d1ccbcf0e26a062383b. Original proof hash unchanged; do not overwrite trial evidence or assume any successful cleanup. Allocation page_count1152995→1152997, freelist0→0; no capacity reclaimed.

Preflight61.050s/13samples PASS; post-STOP recovery60.785s/13samples PASS, both feeds advancing, every2s HTTP probe succeeded. Actual flagsOFF, guard5120, three services active/zero automatic restarts, originald56b4a7 preserved. No integrity scan, copies/backups/snapshots, manual WAL, new index or configuration change. Evidence first-trial-{preflight,stop,recovery,range-explain}-7a43fcd.jsonl in existing lifecycle evidence root.

Read-only EXPLAIN identifies payload-table rowid range counts for original ranges195001..198243/count3243,198244..198272/count29,198273..203272/count5000. Each count equals integer range capacity. Revised local coverage proof freshly verifies under the SAME writer transaction that observations.id is the sole INTEGER PRIMARY KEY rowid alias (ordinary table, no PK backing index). Its integer capacity is a conservative upper bound on current rows, including late/unapproved rows; if that bound≤archive count, overcoverage is impossible. Sparse bounds/unknown schemas/stream ranges retain fresh exact counts. No eligibility, full-row recovery, reference, identity, timestamp or writer limit weakened. No current-row count cached, no new schema/index.

239local backend tests PASS(two Linux-only skipped);70controls PASS(two Linux-only skipped), diff PASS. Regression covers DESC/nonalias/composite/WITHOUT ROWID schemas, schema replacement, sparse fallback, late insertion and unchanged stream counts; existing safety suites run native and guard variants. Revised core NOT production-qualified or executed. Next require exact revised working/release CI and reviewed updated operator trial with fresh preflight; do not repeat7a43fcd unchanged. First cleanup, reusable capacity, source-time indexes/freshness rollout, lifecycle-only enablement and24h soak remain outstanding. Bridge review deadline2026-11-02T01:56:47.671426Z unchanged; I7/Phase1.75 OPEN; Phase2 deferred.

## Revised dense-capacity Linux qualification STOP at commit latency

Working cced225 exact CI41319190397 PASS. Isolated8bb9bf9e7c6f66d71d8410c6ea9e33978886a806 exact CI41319318143 PASS;226local backend tests(two Linux-only skipped). Preserved scoped legacy raw-writer regression rather than importing deferred collector/streaming changes. Refreshed indexed rowid upper bounds619941observations/1833440streams; generated qualification691935/2026784, actual deployed streaming SHA95a49c2ac04b6dbb04223e0f363df0a6132bd7b0cc10fda7145a2055bd1efa12.

Trial1 PASS118.225s, maxwriter76.031ms,282collector saves/RAM updates,0errors,maxsave55.440ms/heartbeat97.344ms. Trial2 STOP87.252s at COMMIT692.804ms(writer): timestamp0.068ms,coverage0.078ms,selection1.231ms,delete11.490ms,commit679.865ms. Exactly12000GENERATED observation rows committed before STOP; no generated streams deleted. Collector25saves/RAM,0errors,maxsave53.989ms/heartbeat81.471ms; production-health guard failures0. Trial3 NOT RUN. **No production retry/deletion.** This candidate does not have three passing revised qualification trials; historicale0d R5/R6 accepted profile remains separate evidence, not authorization to ignore this new STOP.

Coverage optimization addresses the original production bottleneck; commit latency is now measured blocker. Periodic~400ms commits were observed before the693ms overrun; cause is not yet certified. No claim that an automatic checkpoint, disk fault or collector contention caused it. Preserve500ms hardwriter,180s overall,100ms handoff,512MiB/2GiB generated limits. No WAL/checkpoint/synchronous setting changes, manual WAL actions, infrastructure or service changes.

Prepared GENERATED-ONLY batch-size diagnostic accepting250/500/1000(default1000), forwarded through the bounded child and recorded in reports. Next diagnostic uses500-row ceiling to reduce per-transaction writes; full workload stays unchanged. Added read-only fixture SQLite settings and bounded16-sample WAL byte telemetry outside writer transactions; no checkpoint or setting mutations. Six harness tests PASS(two Linux-only skipped), compile/diff PASS; exact CI must exercise Linux child forwarding and report fields before another generated trial. Production operator still1000 and unchanged; do not execute it under failed qualification. Evidence dense-capacity-{qualification,scale}-8bb9bf9 in existing lifecycle evidence root. First production cleanup/capacity/freshness/lifecycle/soak and I7/Phase1.75 remain OPEN;5120 review deadline unchanged.

##500-row diagnostic STOP; total production deleted rows remain0

6886672 working exact CI41320056211 PASS; isolated a092bfb51868e8fcfe2abe65b5eeb20ddbf203de exact CI41320086640 PASS, including Linux fixture-supervisor and500-row child forwarding. No application deployment.

First500-row generated diagnostic STOP89.101s during fixture preparation at15:15:36UTC: production Polymarket guard observed stale/last_data15:15:15.483185,age21.008s; Coinbase live/age0.038s, collector running. Retention had not begun, collector actor not started. Trials2/3 not run; no claim this was a500-row performance failure or that fixture load caused source staleness. Separate I7/rollover defect remains OPEN. Evidence smaller-batch-boundary-stop-a092bfb.jsonl.

A new scheduling precondition required90..300s into a15-minute interval,13successful5s/two-second-timeout feed recovery probes, and≥570s before the next boundary. This limits performance evidence to a stable between-boundaries window; it does NOT weaken ongoing health guards or certify rollover. Preflight PASS with691.692s remaining. Recovered-window500-row trial1 STOP83.122s: writer537.332ms,commit525.525ms,delete10.404ms,coverage0.105ms,timestamp0.089ms. Exactly13500GENERATED observation rows committed across27batches before STOP; no generated stream deletion. Collector47saves/RAM,0errors,maxsave43.992ms/heartbeat78.615ms; production-health guard failures0. Trials2/3 not run. Evidence smaller-batch-commit-stop-a092bfb.jsonl.

Read-only fixture settings:journal_mode=wal,synchronous=2(FULL),wal_autocheckpoint=1000,page_size4096. Bounded WAL allocation samples stayed7107032bytes; these sizes do NOT establish that an automatic checkpoint caused the overrun. Neither500nor1000-row revised candidate has three complete passing trials. Do not retry production unchanged, weaken500ms/180s/100ms limits, disable durability, issue manual checkpoints or change journal settings under existing authorization. No new production cleanup, indexes, services, flags or configuration changed; total production deletions remain0.

Next proposed investigation is a GENERATED-ONLY automatic-checkpoint threshold experiment(256pages vs1000), preserving FULL durability and existing safety/resource/health gates. It requires explicit user permission under the handoff's no-manual-WAL restriction; not executed or approved for production. First actual cleanup, reusable capacity, source-time indexes/freshness release, lifecycle-only retention and24h soak remain pending. Full24h soak cannot finish before November1,19:56CST bridge review; no silent extension/permanent promotion. I7/Phase1.75 remain OPEN and Phase2 deferred.

Final recovered runtime60.535s/13samples PASS; actual flagsOFF, guard5120, applicationd56b4a7, all3services active/zero automatic restarts, both feeds advancing, no2sHTTP timeout. Evidence smaller-batch-final-recovery-a092bfb.jsonl.

## Authorized generated-only automatic checkpoint experiment prepared

User explicitly authorized the256-page automatic-checkpoint experiment on generated fixtures only, preserving FULL durability,500ms writer/180s trial limits and unchanged production. This does not authorize production journal changes or manual checkpoints.

Harness option --fixture-autocheckpoint-pages accepts only0(default,unchanged) or256. It applies AFTER generated population/guard build and BEFORE retention planning, only on the private newly generated fixture's exact main connection outside transactions; rejects production/non-generated paths, mismatched/in-memory connections and non-FULL durability. It records before/after SQLite settings and forwards the option through bounded child supervision. No PRAGMA wal_checkpoint, production connection, change to collector/runtime retention or service configuration. Existing500-row trial workload and100ms handoff retained.

Seven local harness tests PASS(two Linux-only skipped), compile/diff PASS. Linux CI must exercise actual tiny indexed256-page trial and report FULL durability/original1000-page setting before a new full generated run. Full-scale experiment not yet executed; prior1000/500-row commit STOP evidence preserved. Runtime remainsd56b4a7, retention/paidAI OFF; total production deletions0. I7/Phase1.75 OPEN; bridge review deadline unchanged.
