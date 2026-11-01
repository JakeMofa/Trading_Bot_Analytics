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
