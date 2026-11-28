# Benchmark local database admission

The reviewed capacity profile is deployed in Benchmark `.11`, source
`1b232c2`, through CD 46116573223. The user approved one maintenance cutover;
current A and all 20 retained generations were preserved. Actual role/mount
checks, three-source immutable Supabase readbacks, repeated writer renewals
and a 500-row HTTP read passed after adoption. See the [master checkpoint](INTELLIGENCE_REBUILD_PLAN.md#november-28-2026--local-connection-budget-adoption)
for measured interruption, boundary status and evidence limits.

## Observed failure

At 05:34:53 UTC November 28, PostgreSQL refused an application connection
because `tradebot_app` had reached its eight-session limit. Collection became
OFF the next second. Source/control diagnostics masked the error as
`session.unclassified`. The public API also used this login for read-only
transactions. No particular requester was uniquely identified.

Four source writers intentionally keep physical sessions open across events;
their fresh transactions do not release those sessions. Coinbase candles,
preferences, ownership checks, calculation and dashboard work can overlap.
Closing ordinary per-operation connections does not prevent this legitimate
concurrency from exceeding eight. There is no evidence of a connection leak.

Host memory remained available, without swap or OOM increments. Most reported
PostgreSQL cgroup usage was file cache. This incident does not establish a
need for more VM RAM.

## Enforced deployed budget

Keep server and role ceilings unchanged. PostgreSQL permits 20 sessions with
three reserved; normal role maxima sum to the remaining 17.

| Login | Ceiling | Required client admission |
| --- | ---: | --- |
| `tradebot_app` | 8 | Operator process at most 6, including retained source sessions; calculation process at most 2 |
| `tradebot_reader` | 4 | Single-worker public API at most 2; private operator reads at most 1; host diagnostics at most 1 |
| `tradebot_lifecycle` | 3 | Existing lifecycle limit and reviewed worker/controller use |
| `tradebot_migrator` | 2 | Existing restricted maintenance identity and deployment gates |

Admission begins before libpq connection establishment and environment
validation. It ends only after the physical connection closes, including
commit/rollback failures and canceled callers whose worker threads still run.
All operator Store factories share their process budget; creating another
Store must not create another allowance. Calculation and API worker counts
must match the qualified process topology.

The API uses the existing read-only login and rejects writable or alternate
logins. Existing grants must pass every normal local API read. A busy history
request returns an explicit bounded error while the RAM live-state stream
continues. Private ownership/status reads use short exact-state queries.

Live controller diagnostics must stop opening application-role sessions and
share a host diagnostic lane. That lane serializes independent processes and
holds admission until the psql/driver process genuinely exits. External
samplers must follow the same lane; role ceilings alone are not reservations.
Connection metrics must count client backends rather than every background
process in `pg_stat_activity`.

## Diagnostic and recovery corrections

PR #256 preserves `selected_feeds` as a supported sanitized failure stage.
Only proved connection-capacity refusals while acquiring a side-effect-free
control/ownership connection can be retried. Ownership retries stay inside
the existing aggregate two-second fence deadline. A false owner result,
authentication/identity error, query failure, write rejection or expired lease
does not gain fallback authority.

Historical failure remains visible. A terminated task plus confirmed explicit
durable OFF can acknowledge that failure for re-arm. Unknown or failed OFF
cannot. Per-ingest origin, generation, producer UUID and lease checks remain.

## Qualification and deployment gates

- Prove actual role exhaustion and alternate-reader behavior on disposable
  PostgreSQL 17; exercise wrong-login and write rejection.
- Hold the full simultaneous application and reader budgets, reject extra
  admissions, and test establishment, commit, cancellation and close failures.
- Validate normalized Compose, singleton API worker, exact secret mounts,
  restricted grants, source identity and controller checks under CI.
- Independently review every live connection consumer and diagnostic helper.
- Prepare an exact release and recovery packet preserving the current A and
  all old retained generations. No deletion authority is introduced.
- Adopt through a qualified collection-preserving profile/controller handoff
  or an explicit user maintenance exception. The existing same-profile
  API-only update cannot change these mount/controller/collector contracts.
- After adoption, repeat actual 500-row HTTP history while all feeds collect,
  verify actual login/session/epoch, identities and ACKs, and observe queue age
  through market boundaries. Report any interruption and its cause separately.

The API-only `.9` deployment already preserved collection but did not apply
this capacity profile. No unconditional availability or 72-hour retirement
claim follows from the isolated qualification.

## Residual scheduling diagnostic

A later old `.7` stop at 06:25 UTC reported `ownership.timeout`; it is not
proved to be the same native role-cap fault. A nearby bounded diagnostic
aggregation ran inside PostgreSQL, but no evidence establishes that it caused
the timeout. The `.11` operator still has a 0.25-CPU quota. Its first
100.4-second measured interval accumulated 17.467 seconds of CPU throttling
without operator memory-full pressure or OOM; this is an interval total, not
a duration attributable to one request. Host spare RAM cannot rule out
container scheduling limits.

If the ownership timeout recurs, separately measure monotonic time waiting
for the worker thread, admission ticket, libpq connection and exact ownership
SELECT/validation. Correlate these with per-container CPU throttling and
memory/IO pressure while preserving the aggregate two-second ownership fence.
Keep measurements bounded and sanitized. Do not retry a false owner, extend
an expired lease or relax that deadline to mask the cause. A CPU quota change
would require its own controlled comparison, not an inference from host RAM.

## New adoption failure: status availability latched renewal OFF

The `.11` capacity-profile acceptance is partial, not sustained. The private
status route returned HTTP503 at 06:41:31.369854 UTC. `watch_service.run()`
classified that HTTPError as a permanent hold. Seven further timer ticks
skipped renewal; the last valid lease expired at 06:43:15.166854, producing
`ownership.lease_lost`. All 98,058 envelopes were ultimately ACKed and zero
were pending. The route masked the underlying read exception; role-cap,
CPU-pressure or semaphore-wait causality is not established.

A narrowly scoped status503 retry can preserve existing authority by checking
fresh status and all normal worker/identity gates on the next tick. Persistent
unavailability must still expire the existing lease; renew409, false owner,
expired authority, auth or binding failures must remain holds. This successor
requires its own offline regressions and live acceptance.

## Qualified recovery successor

Benchmark `.13` source `4741ce0` passed exact CI, normal CD and the full
07:45–08:00 UTC market plus its successor. The two actual private status503
failures recovered on the next checks before expiry, retaining epoch 8 and
the same writer session. The identical 500-row local HTTP page passed in
0.671619 seconds including decode. The watch was left ON. Full evidence,
timestamped preservation scope and still-open long-window/handoff gates are
in the [master checkpoint](INTELLIGENCE_REBUILD_PLAN.md#november-28-2026--heartbeat-recovery-qualification).

## Complete-origin preservation at larger size

The later `.13` ownership stop is recorded in the
[active repair plan](OWNERSHIP_TIMEOUT_RECOVERY_2026-11-28.md). Its first
runtime repair merged in #263. Adoption remains blocked by a distinct bounded
read-only preflight: the same full-row origin digest that qualified at 98,058
rows reached 19,000.576 ms/SQLSTATE57014 at 235,755 rows on the actual stopped
Benchmark. The captured epoch, generation, high-water ID, ACK count and zero
pending count were unchanged afterward. No new CD was dispatched.

The separate controller candidate enumerates narrow occupied ID-page ranges
and hashes one bounded range per statement using one physical read-only
REPEATABLE READ session per origin. It must reproduce the previous full-row
SHA256 page/outer digest exactly, cover every approved origin and preserve
counts and pending state. Statement19s, response20s, temp64MiB, work_mem2MiB,
role ceilings and the controller's 600-second total remain the bounds. Total
origin work can span multiple responses; it is not another long statement.

Qualification must include sparse/negative/extreme IDs, content and ACK
mutation, committed concurrent changes across a pinned snapshot, failed SQL,
frontend cancellation and real backend/diagnostic-lock lifetime. Do not claim
cleanup from a successful local client exit alone. The complete controller
inventory and all normal before/after-migration checks remain required.

This repairs statement granularity, not linear total cost. The descriptor
cursor's initial narrow grouping and all complete-origin hashes must still fit
their respective bounds at the actual data size; neither a synthetic small-row
fixture nor the current-size test qualifies arbitrary 72-hour inventories.

The first candidate passed 338 local controller cases (12 skips, including
three Linux-container cases) and 58 CI-control cases. Its native PostgreSQL
17.2 oracle test matched all 235,755 synthetic full rows, including 2,357
pending rows, across 231 page statements; the 1.474-second local time does
not represent the real Benchmark payload or disk workload.
[Native digest parity evidence](evidence/benchmark-cursor-235755-native-parity-2026-11-28.json).
Independent macOS PostgreSQL cancellation tests also exposed and verified
repairs to inherited lock-FD lifetime and interrupted pre-PID registration.
Exact pinned Linux/Docker tests and the real read-only full inventory remain
release gates; no current-size VM pass or deployment is claimed here.

Final review also replaced the interrupted-login fallback's child-list lookup
with numeric procfs PID inspection and exact parent/start identity. Linux's
[child-list documentation](https://man7.org/linux/man-pages/man5/proc_tid_children.5.html)
warns that exiting siblings can hide surviving children. The
[process-stat format](https://man7.org/linux/man-pages/man5/proc_pid_stat.5.html)
defines the parent PID and start ticks used for identity; unreadable surviving
processes retain exclusion. This path is covered by the Linux sibling-churn
fixture, not inferred from the successful macOS SQL test.
