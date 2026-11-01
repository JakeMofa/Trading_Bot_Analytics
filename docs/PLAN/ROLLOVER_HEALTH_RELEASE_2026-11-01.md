# Independent rollover and truthful health release — November 1, 2026

Status: implementation prepared; **production release/acceptance blocked** by
verification controls. This is collection-continuity work, not feature-speed or
retention completion. No production attempt or observation has run.

## Application scope

Reuse `a6958f6` independent REST scheduling, one awaited serial feature worker,
worker-owned SQLite connection and publication age/market guards. REST keeps its
existing request/pause cadence and single collector. No queued/overlapping feature
jobs. Cancellation drains the sole worker, including repeated cancellation, without
publishing cancelled results. Historical capture is preserved.

Only live results with age0..30s, matching current market, and start<=now<end may
publish. Malformed result timestamps are rejected. Startup hydration uses the same
guard instead of publishing an old saved feature; saved history is unchanged.

New pure snapshot health evaluator checks market identity/interval, quote slug and
optional market ID, both source timestamps, features and collector/guard state.
Source timestamp age allowance30s; future tolerance5s. Missing, malformed, naive,
stale or excessively future timestamps degrade health. Receipt timestamps never
replace source timestamps. Replayed old books cannot restore aggregate ok.
Feature unavailability, age or market mismatch remains an explicit reason.

API routes/status codes/previous fields stay; aggregate values remain ok/degraded.
`diagnostic_reasons` is additive in health/system status. Health status and reasons
are computed together after the asynchronous cloud read, avoiding a boundary race
between an earlier ok decision and later expired reasons.

The release excludes price-query changes, feature-version changes, index code or
installation, dependencies, configuration, units and retention changes. Scoped
streaming export retains the deployed raw-writer timestamp format. Working-branch
pre-existing price/index/retention work remains on its branch; it is not promoted.

## Tests and candidate requirements

A blocked single feature worker is advanced through a simulated186s boundary:
REST discovery changes RAM identity and websocket subscription before the worker
finishes. The late old-market result is not published. Existing cancellation,
worker-connection ownership/cleanup, publication boundaries and independent REST
progress tests are reused. Health tests cover age30/future5 boundaries, missing,
malformed/naive timestamps, expired/missing/mismatched identity, replayed old events,
feature unavailability and recovery on genuinely current source timestamps.
API integration verifies expired-market degraded/HTTP200 with previous fields.

Full working backend and deployment-control suites plus exact-revision Linux CI
are required. The sandbox initially blocked an existing Unix-socket test; the
suite is run with sockets permitted, not silently skipped. Candidate must be tested
as its own exported tree and have exact CI, not inherit working-branch evidence.

Candidate construction uses the deployed d56b4a7 application tree plus only reviewed
application/test/report files, with existing deployment HEAD84513b0 as parent.
This preserves deferred candidate history and the existing local deployment ref,
while preventing unshipped retention/index changes from entering this application
release. No force push, new branch, worktree or working checkout switch.

## Exact release-control blocker — no production attempt

Normal protected `deploy/lightsail/deploy.py:preflight` opens the live database and
runs complete quick_check and foreign_key_check inline, with no SQLite child
progress/work deadline. Actions deployment has a15-minute/900s job ceiling that
also includes checkout, CI verification, transport, application restart, smoke and
rollback. The consumed exception is pinned to a7c0989->d56b4a7 and cannot accept
this candidate; its metadata-only verification cannot be reused.

Existing independently recorded full audit measured quick_check782.745s plus
FK78.092s =860.837s with writers paused. That is historical evidence, not a
prediction that a fresh live check will finish in that time. Even that result
leaves39.163s in900s, insufficient for180s recovery reserve, let alone deployment.
The earlier normal live path already failed to complete safely. Do not repeat it,
reuse old verification as fresh approval, squeeze checks into remaining time,
restore a database, or bypass complete checks. Existing full audit source:
`production-integrity-7e5e7d2.jsonl` in the lifecycle evidence directory.

Smallest required control change for review: separate full verification into an
explicitly budgeted, supervised child phase before application checkout; retain
both complete checks and fail closed on timeout/error. Give that phase its own
approved budget/collector-health stop conditions and preserve recovery reserve,
then bind its evidence to the exact candidate/runtime/database/schema identity
and an approved freshness window for the existing code-only/API-only deployment.
Alternatively the enclosing workflow must have a newly approved sufficient budget
and the same bounded-child/recovery controls. Neither route is implemented or
approved here. A time-budget or verification-policy change is reviewable release
control work, not an implicit extension of existing authorization.

No production restart, helper install, verification scan or workflow dispatch.
Only API may restart in the eventual application deployment; rollback restores
code only. Do not stop/restart unrelated services under this release instruction.

## Production acceptance remains unperformed

After a compatible route is approved: at least20minutes,3completed feature cycles
and a market boundary, within30minutes. Require zero2s API probe timeouts,
advancing Coinbase/current-market Polymarket RAM and persistence, discovery while
features calculate, no expired-market healthy response, no stale/wrong-market live
feature publication, stable services and working dashboard/SSE. Record discovery,
first-current-book and feature age independently. Missing venue evidence or cycles
means incomplete validation, not automatic retry. Slow rejected features may stay
unavailable; freshness is not fixed by this milestone.

Retention/paidAI OFF, production data intact, deleted0, storage ceiling unchanged.
No backups/copies/snapshots, VACUUM, manual WAL operations, indexes, infrastructure
change or Phase2. Temporary review deadline2026-11-02T01:56:47.671426Z unchanged.
I7/Phase1.75 remain OPEN; retention experiments must not resume before this passes.
