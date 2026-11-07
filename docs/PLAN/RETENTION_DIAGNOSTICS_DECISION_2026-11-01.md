# Retention diagnostics implementation and decision C — November 1, 2026

Decision **C: STOP**. No revised acceptance policy or runtime retention solution
is qualified. Review checkpoint scheduling separation as the smallest architectural
alternative; do not launch another unchanged qualification trial.

Implementation `ddda7d52e482b2d11c184ee122efb1500f6e9be2` has
[exact CI41325279117](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41325279117)
PASS. Local retention suite93 tests PASS(two Linux-only skips). Initial test
invocation used system Python without project dependencies; rerunning with the
existing project virtual environment passed. No packages were installed.

## Implemented diagnostics

- Retention reports `transaction_total_seconds`, `max_transaction_total_seconds`
  and `commit_call_seconds`. Legacy duration fields and their500ms gate remain
  unchanged. Partial failures retain total durations and per-phase commit timing.
- Actual `writer_lock_occupancy_seconds` is explicitly null in runtime reports.
  Occupancy comes only from the separate offline syscall analyzer, which brackets
  successful shm byte120 acquisition/release, associates resolved descriptors and
  commit markers, and retains pre/post-release writes and sync calls. It does not
  interpret Python transaction state as a kernel lock. The48-transaction prior
  trace was revalidated; tests reject database-file locks and unfinished syscalls.
- Generated harness reports collector save duration, heartbeat interval and errors
  independently under `collector_interference`; original collector limits and
  save-before-RAM behavior remain. Normal production does not import or enable
  the generated trace connection subclass or run strace. Trace markers require
  explicit environment opt-in and private generated fixture paths.

See the earlier [ordering evidence](SQLITE_WRITER_LOCK_DIAGNOSTIC_2026-11-01.md).
That reduced trace established post-release checkpoint work and lock-held WAL
sync, but did not explain the historical502.686ms STOP. It remains STOP.

## Bounded representative investigation: stopped at prerequisite

Prepared exactly one profile:800000generated observations/2350000stream events,
500-row batches, default1000-page automatic checkpoint threshold, FULL durability,
100ms handoff, existing500ms/180s/512MiB-process/2GiB-fixture guards. Source-only
staging used the exact passing CI revision; no production application release.
No batch-size or checkpoint-setting matrix, native extension or dependency added.

The first13-sample preflight encountered a non-live or stale feed before workload
launch. Its assertion did not retain which feed/status/age failed; that detail
is unknown. One bounded120s recovery window then failed to obtain13 consecutive
healthy5s samples. No fixture process, collector actor, strace process, generated
database or retention operation was launched in either preflight. Both staged
work directories were independently confirmed empty, with no trace/report file.
The representative causal measurement is therefore **unavailable**, not a
retention performance failure and not a completed qualification run.

Read-only follow-up16:19:42.951572UTC: collector running, Coinbase live/age0.112536s,
Polymarket live/age0.973491s. A fresh single sample does not retrospectively satisfy
the failed sustained baseline. No later trial was started. There is no evidence
that generated workload caused feed degradation: it never started. No claim
about the failed preflight's specific feed or its cause is warranted.

Private evidence directory outside the repository:
`/Users/jake/Documents/ChatGPT/TradebotAnalytics/evidence/phase175-baseline/lifecycle-implementation-20261031/lock-diagnostics-ddda7d5/`.
Includes prepared source-only runner, preflight STOP transcript, follow-up empty-work
and health evidence, local test log and checksums; no database or credentials.

## Specific implementation decision and alternative for review

Do **not** change the500ms policy, enable retention, alter checkpoint settings,
shrink batches again, or roll out intrusive production tracing. Missing evidence
is a representative slow commit with validated syscall boundaries under a healthy
collector baseline. Without it, neither post-release checkpoint work nor
lock-held FULL WAL sync can be declared the dominant representative delay.

Smallest architectural alternative worth reviewing: give passive checkpoint
scheduling an explicit owner separate from the deleting connection. A future
reviewed design would disable automatic checkpoint triggering on that connection
only, retain FULL WAL commit sync, and use a separate connection/worker for PASSIVE
checkpoint work. This is a proposal, **not implemented or authorized by this
milestone**; it would require explicit review of the current no-manual-WAL boundary.
It does not require a new SQLite dependency, custom VFS, single-writer redesign
or a raw-event buffer.

The reason to review it is specific: the existing validated trace proves that
checkpoint writes/database sync can occupy a retention commit call after WRITE
release. Separating ownership would make that work independently observable and
scheduled. It would not eliminate lock-held FULL WAL sync or prove that it solves
the historical overrun. It also would not grant a policy exception: the current
500ms total gate remains until separately approved.

Required design checks before implementation: collector continues its existing
durable-save-before-RAM ordering and cadence; no claim of uninterrupted updates
during lock-held fsync. WAL backlog and total physical storage must remain within
the existing caps; stop further retention work on worker failure/storage pressure.
Worker memory must fit existing process/aggregate budgets. Checkpoint I/O can
still compete with collector persistence even without its writer lock, so collector
latency/heartbeat/error and complete-workload gates must remain. Crash recovery
uses SQLite's existing durable WAL; no early WAL removal, durability weakening,
backup or new buffering semantics. These are review requirements, not measured
properties of an implemented worker.

Production unchanged, deleted0; retention/paidAI OFF. I7/Phase1.75 OPEN, Phase2
not started. Temporary5120MiB review remains2026-11-02T01:56:47.671426Z
(November1 19:56:47 CST); no extension or permanent cap promotion.
