# Generated split-gate qualification — November 1, 2026

Result: **NOT PROVEN — representative VM trial did not start.**

The user approved the split policy only for generated qualification. Implementation
is frozen at `a18ce3c6a9ab1e8c9321f521d17768c3f39526db`.
[Exact-commit CI 41359072373](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41359072373)
passed: 252 backend tests and 103 deployment-control tests. The Linux installed
strace integration test actually ran and passed, deleting exactly 98 observations
and 99 stream events in a tiny generated fixture. This establishes harness
conformance, not representative VM performance or production qualification.
Local retention safety suite: 93 tests passed, two Linux-only skips. Coverage,
exact deletion identities, protected/late references and committed-overrun
reporting tests remain intact.

## Implemented controls

Only `backend/qualify_retention_sql.py` and its new qualification-only parser/tests
change. Production `backend/app/retention.py` remains unchanged at its 500ms gate.
The generated child privately imports the candidate and applies a 1000ms total
budget; it requires FULL synchronous=2 and default automatic checkpoint=1000.

Every committed retention batch requires the matching main-thread trace with
successful POSIX F_SETLK operations on the exact canonical fixture.db-shm,
byte120 length1 (WAL WRITE). Occupancy uses syscall entry/exit brackets plus a
2us rounding reserve. Missing, duplicate or ambiguous evidence is NOT PROVEN.
No transaction flag or commit-return duration is used as lock occupancy.
Monotonic BEGIN-entry through commit-return is separately bounded at1000ms,
as is the commit call; occupancy upper bound remains500ms. Collector saves and
heartbeat remain strictly below1s with zero errors and save-before-RAM ordering.
Tracing is confined to private generated processes. Trace disk usage is counted
cumulatively within the existing2GiB fixture limit;512MiB/process and180s/trial
limits remain. Each batch is checked before another begins. The supervisor
stops after the first failed trial; no automatic retry or threshold adjustment.

Report fields include exact committed rows, occupancy upper/lower bounds,
transaction/commit time, collector delays/errors, workload completion, end-to-end
throughput, parser time, trace bytes and tracer CPU/RSS where available. Tracing
perturbs wall timing; no untraced control is run, so baseline overhead is not
isolated. This limitation must accompany any future timing result.

## Representative attempt

Prepared existing workload:800000 observations,2350000 stream events,
500-row batches, ten-digit synthetic Coinbase IDs, indexed timestamp guards,
FULL/default checkpoint, actual deployed save helper SHA256 pinned to
`95a49c2ac04b6dbb04223e0f363df0a6132bd7b0cc10fda7145a2055bd1efa12`.
Three trials were configured with fail-fast behavior, as authorized.

The single pinned existing SSH connection to the VM failed with
`ssh: connect to host 3.13.133.25 port 22: Operation timed out` before connecting.
The remote runner never started: no remote fixture, preflight, scan, trace or
qualification workload was launched. No retries or recovery windows followed.

| Representative measurement | Result |
|---|---|
| Trials started / completed |0 /0 of3 required|
| Actual committed cleanup rows |0|
| Maximum writer-lock occupancy |NOT MEASURED|
| Maximum transaction / commit-call duration |NOT MEASURED|
| Collector save / heartbeat / errors |NOT MEASURED|
| Cleanup throughput |NOT MEASURED|
| Workload completion |NOT PERFORMED|
| Tracing overhead |NOT MEASURED; no representative tracer launched|

These are unavailable measurements, not zero-latency or zero-error passes. The
original1000-row,500-row and256-page failures remain failures under their original
500ms total-duration policy. The earlier reduced lock trace remains diagnostic
only and does not fill this representative evidence gap.

One next action: restore the existing approved VM SSH execution path, then run
the pending fail-fast qualification once. No new performance-policy decision is
needed. No production deployment, deletion, retention enablement, storage-policy
change, manual WAL operation or new infrastructure was performed or authorized.
Capacity remains separately STOP; frozen rollover release93161cf is preserved.
Retention and paid AI remain OFF; I7/Phase1.75 OPEN; cap deadline unchanged.

## Resumed execution after access restoration

The user confirmed restored/tested SSH and authorized resumption from6fd4ce0
using the CI-passed a18ce3c harness. Existing pinned SSH was independently verified
at2026-11-01T22:59:15.577677Z. All five staged source files were compared byte for
byte with a18ce3c. No harness or production code changed. The prior connection
failure remains an accurate historical record, superseded only as an access blocker.

The initial safe-start launcher rejected the early seconds of the new interval
before any trial or fixture started. Its bounded wait was corrected to handle
that interval edge; this was not a workload retry. One bounded wait then reached
the already-required safe start at23:01:30Z. No recovery window or soak followed.

Fresh preflight PASS: current matching market and fresh Coinbase/Polymarket source
timestamps; collector running; helper SHA pinned; installed strace; available RAM
1386545152bytes and filesystem space50758447104bytes. API confirms retention and
paid AI false. Production main5001482240/WAL34459712bytes are metadata only; their
combined headroom under5120MiB is317.351501MiB, below512MiB. Capacity remains STOP;
this is not a capacity approval. Generated work uses a separate private directory
on the existing filesystem with the unchanged2GiB/process-workspace guard.

### First trial: FAIL runtime gate; retention performance NOT PROVEN

Started2026-11-01T23:01:30.606778Z. The existing170-second work deadline interrupted
fixture preparation at `generate_observations`. Last progress recorded740000 of
800000 observations; stream generation, indexed-guard preparation and retention
application were not reached. The harness stopped after this first failure;
trials2/3 were not launched. No unchanged retry or threshold change.

| Measurement | Observed result |
|---|---|
| Trial attempts / completed representative workloads |1 /0; trials2/3 NOT RUN|
| Actual committed cleanup rows |0|
| Maximum retention writer-lock occupancy |NOT MEASURED; no retention transactions|
| Retention transaction / commit-call duration |NOT MEASURED; no retention transactions|
| Competing collector saves / delays / heartbeat / errors |NOT MEASURED; actor not started|
| Cleanup throughput |0rows over174.034300451s supervised time; no measured retention execution rate|
| Workload completion |false; fixture preparation incomplete|
| Child elapsed including cleanup |173.729699602s|
| Supervised elapsed including cleanup |174.034300451s|
| Peak fixture plus tracing disk |713822456bytes, below2GiB guard|
| Generated child peak RSS |41172KiB|
| Tracer CPU / sampled RSS |57.58CPU seconds /4014080bytes|
| Trace output |610562532bytes|
| SQLite settings |WAL,FULL=2,default automatic checkpoint1000,page4096|
| Production guard errors during trial |0; distinct from unmeasured fixture collector errors|

The report's empty-list maximum transaction value0 is an implementation sentinel,
not a timing measurement. There is no lock-occupancy evidence for retention, so
performance qualification is NOT PROVEN despite the definitive runtime FAIL.
Tracing included fixture construction: the measured tracer CPU and610.6MB output
establish substantial instrumentation work before retention. There is no untraced
control; elapsed overhead and whether the same preparation would fit untraced are
not isolated. Do not attribute the historical502.686ms failure to this result.

The supervisor reaped the generated workload and removed its disposable fixture;
no fixture.db files remain. Only generated trace evidence remains in
`/tmp/tradebot-split-qualification-eqt2u2w_/work/trace-evidence-1`.
Main trace SHA256:
`01d3133fd823c58f7fb3384da3122c4eefa96b242a154d0e3aeedf57760026d4`.
Private local report/source hashes:
`/Users/jake/Documents/ChatGPT/TradebotAnalytics/evidence/phase175-baseline/lifecycle-implementation-20261031/split-qualification-a18ce3c-restored/`.
No database copied, restored or retained as a backup.

One bounded post-check at23:05Z: both feeds live with current source timestamps,
matching unexpired23:00–23:15market, collector running/no reported error; health
1.6294s,current-state0.2473s,system-status0.5935s (all below2s). Reported API,
ensemble and lifecycle services active with zero restarts, service evidence fresh.
Retention/paid AI remain false. Main5004308480/WAL34459712bytes; capacity STOP.
No application deployment, production cleanup, configuration, journal or storage
policy operation occurred. Multi-cycle/boundary acceptance NOT PERFORMED.

One next action: review a narrow instrumentation change that begins syscall
capture after fixture preparation, before the first retention BEGIN, while still
requiring complete lock evidence for every batch and preserving the existing
whole-trial/resource limits. This is a proposal, not an implemented change or an
authorization to retry. It avoids spending tracing work on fixture construction;
its ability to meet the runtime gate remains unproven. Keep production500ms and
all generated split limits unchanged. Old failures remain failures; capacitySTOP,
I7/Phase1.75OPEN, frozen93161cf and cap-review deadline unchanged.

## Scoped tracing implemented; new representative preflight STOP

User authorized correcting tracing scope, tiny tests, exact-commit CI, then one
representative trial with conditional trials2/3. Implementation241b1ee moved
capture after untraced fixture generation/index/plan preparation. Corrected test
commit `6d9edc3e2ba6de31cc3dd8115736314d74c7ece3` passed
[exact CI41361239486](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41361239486):
253 backend tests and103 deployment-control tests. Linux strace integration
actually ran. All six staged source files match that exact commit byte for byte.
Local93 retention safety tests PASS(two Linux skips),7 harness tests PASS(two
Linux skips),7 lock/phase tests PASS(one Linux skip).

The earlier241b1ee CI41361117611 failed a test assertion: the tiny qualification
passed, but the test counted TEMP bookkeeping commit markers as retention commits.
Corrected assertion counts complete measured BEGIN/commit-return brackets, with
exactly2validated lock intervals. No representative trial ran on failed CI.

### Trace scope and preserved limits

Preparation runs without strace. Timing markers are disabled during preparation.
After preparation, before the competing collector starts, the private generated
child authorizes only its exact tracer child PID through LinuxPR_SET_PTRACER.
A bounded attachment handshake requires matching TracerPid and captured
`trace_ready`; this is attachment evidence, never writer-lock evidence. Actual
occupancy still requires exact fixture shm byte120,len1 F_SETLK entry/exit bounds.
The collector starts only after attachment. Save-before-RAM ordering unchanged.

Capture onlyfcntl,fdatasync,fsync andwritev(markers). SQLite payload pwrite64 and
ordinary write syscalls are excluded. Trace limit:32MiB hard per file, aggregate
32MiB monitored per trial, all trace bytes also included in existing aggregate
2GiB fixture accounting. Dead tracer before next batch, missing or ambiguous
lock evidence, or trace-limit failures stop. No package/new native extension,
VFS, service, writer coordinator or production instrumentation introduced.

The original170s work alarm,177s supervisor work cutoff and180s total trial limit
are unchanged. Neither the alarm nor overall elapsed clock resets at attachment.
Preparation and stage durations are recorded even when preparation is interrupted.
FULL/default1000-page automatic checkpoint,800000/2350000-row workload,500-row
batches,500ms writer-occupancy/1000ms transaction/commit split limits and collector
<1s/noerrors protections remain unchanged. Production retention.py remains unchanged.

The tiny generated test deletes exactly98 observations/99 events and proves:
preparation elapsed is included, earliest trace follows preparation, first marker
is trace_ready, no payload write syscalls, bounded trace, exactly2complete measured
transactions and validated occupancy evidence for each. It is conformance evidence,
not representative VM performance or production qualification.

### Representative attempt blocked before preparation

After exact CI success, the launcher reached the read-only production preflight.
It raised `ProductionGuardStop: production_market_not_current` before any generated
fixture/preparation, collector or tracer started. No trial runtime was consumed;
0of3 new qualification trials started,0 cleanup rows committed. No recovery window
or unchanged retry. The temporary source staging directory was
`/tmp/tradebot-scoped-qualification-8w5xjc7h`; it is not a database or backup.

One bounded explanatory snapshot at2026-11-01T23:17:16.335158Z showed:

| Evidence | Value |
|---|---|
| Displayed market |2051369 /cpc-btc-updown-15m-2026-11-01-2300z|
| Market end |23:15:00Z; expired by136.335s|
| Quote identity |matches that expired market, not a current market|
| Polymarket source_time |23:15:34.714391858Z,~101.621s old|
| Polymarket feed label /last_data_at |live /23:17:08.870998Z|
| Coinbase source_time |23:17:16.387512Z, current|
| Collector |running,error null|
| Health /current-state response |0.081088s /0.042213s|
| Installed tracer /helper identity |strace available,pinned helper SHA unchanged|
| Available memory /filesystem free |1391448064bytes /50136244224bytes|

The recent receipt timestamp and live label do not prove current-market source
freshness. The current-market preflight correctly rejected the expired identity.
This snapshot establishes the safety blocker, not a new investigation of feature
job duration or persistence. Do not classify responsive API/receipt activity as
healthy current-market collection. No further production queries/scans or recovery
observation were run.

New representative occupancy, transaction/commit duration, collector interference,
cleanup throughput and tracing overhead: NOT MEASURED. Workload completion:
NOT PERFORMED. No new preparation bottleneck measured, because preparation did
not start. Prior traced-preparation deadline failure remains FAIL; historical
500ms failures unchanged. Source-policy and trace-boundary conformance PASS;
representative performance NOT PROVEN, qualification preflight STOP.

Private source manifest, completed CI log and bounded snapshot are retained under
`/Users/jake/Documents/ChatGPT/TradebotAnalytics/evidence/phase175-baseline/lifecycle-implementation-20261031/scoped-qualification-6d9edc3/`.
Next action is to resolve the expired-current-market feed precondition before
resuming this pending qualification. No gate bypass, automatic recovery wait or
retry is authorized by this report. No production changes/deployment/cleanup,
no manual WAL operation, no storage or deadline change. CapacitySTOP remains
separate, flags untouched, frozen93161cf preserved,I7/Phase1.75OPEN. Multi-cycle
and real-boundary acceptance NOT PERFORMED.
