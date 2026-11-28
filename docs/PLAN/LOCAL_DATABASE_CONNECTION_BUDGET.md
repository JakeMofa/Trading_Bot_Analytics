# Benchmark local database admission

This is the next capacity checkpoint linked from the master plan. The `.7`
collector and `.9` API/UI are live after recovery. The candidate changes below
are being qualified; this document is not evidence of their deployment.

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

## Enforced candidate budget

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
