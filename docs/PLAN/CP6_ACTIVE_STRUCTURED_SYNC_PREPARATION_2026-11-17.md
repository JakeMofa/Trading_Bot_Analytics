# CP6 active structured sync preparation — November 17 CST / November 18 UTC

Status: **PASS in disposable generated PostgreSQL; PP/Supabase runtime NOT
QUALIFIED**. This is default-OFF source. It has no service wiring, cloud
credentials, Supabase grants, raw upload, or retirement authority.

## Why this slice exists

The first 159-second PP live session left 1,530 pending structured outbox
rows. `Store._admit` holds at 10,000 pending rows per origin. The observed
average is about 9.6 rows/second; extending that rate to a longer session is
an extrapolation, not a measured stop. A 72-hour active A window cannot rely
on post-seal outbox drainage alone.

The raw policy is unchanged: B accepts writes after A seals; only then does
raw A upload to private Storage and receive authenticated readback. Structured
markets, prices and prediction evidence may be imported while A still
collects. That import does not authorize raw retirement.

## Prepared contract

- `ActiveStructuredWorker` only accepts the exact collecting PP-live origin and
  generation. It enforces the existing cycle request, time, byte and row
  limits, then acknowledges local outbox records only after a separate
  authenticated readback matches exactly.
- Ordered outbox validation permits monotonic revisions of `markets` and
  `current_prices`, holds stale/equal-time conflicts, and rejects changed
  immutable identities. It preserves outbox order and source text/decimals.
- Active B sync holds before any cloud request if the same origin has pending
  rows in another generation. This prevents B's newer mutable projection from
  overtaking A's unsynced older revision. It does not drain A by itself.
- A new **unapplied** additive private migration creates one immutable hash
  receipt per structured outbox revision. It grants no runtime role and enables
  RLS. In the prepared direct-PostgreSQL adapter, projection updates,
  per-revision receipts and a generation-scoped checkpoint commit atomically.
  Fresh readback verifies every receipt plus the current projection before
  local acknowledgement. An ambiguous post-commit result is safe to retry;
  changed receipt contents hold. Readback requires an **exact** projection
  match; a newer-looking value without a proven receipt cannot authorize ACK.
- The adapter is constructed only from an injected connection factory with
  exact database and role binding. No deployed service constructs it.

## Evidence and limits

Source commit `02dad1a` passed local focused tests: **32 passed**. Exact
[push CI 44216336523](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44216336523)
and [PR CI 44216373853](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44216373853)
passed. The Linux integration applied both private migrations to a disposable
PostgreSQL database, proved the new receipt table has RLS and no public/service
grants, and exercised ordered price revisions, fresh readback, idempotent
retry, stale revision HOLD, receipt conflict and wrong-database rejection.
The actual PostgreSQL transport test ran without skips in that isolated job.

The generated test used the isolated database administrator identity. A narrow
PP importer role and policy remain unqualified. Neither Supabase HTTP nor
live Supabase PostgreSQL was contacted. Cloud request rate, receipt storage
growth, sustained backlog reduction and outage runway are unmeasured. This
slice does **not** clear the 10,000-row operating cap or the planned 30–45
minute PP A→B trial. Raw archive/readback, mutation protection and partition
retirement remain separate gates.

The direct adapter currently applies a PostgreSQL statement timeout per
statement. Connection establishment and a whole multi-statement transaction
still need a qualified wall-clock deadline before any PP runtime wiring.
The follow-up generated PostgreSQL regressions cover parent-before-dependent
imports, changed projections/receipts, and a receipt missing below an
advanced checkpoint; their exact successor CI result is pending.

Review also exposed the A-pending/B-newer ordering hazard. A generated
two-generation regression now requires B to HOLD without a cloud request until
A's pending rows drain. Sealed A drainage with ordered revisions, cross-worker
serialization and replay of an older batch after a later valid projection are
not yet qualified. This remains a runtime **NO-GO**, even if this PR's offline
tests pass.

For the later PP runtime, use a reviewed direct or session-mode PostgreSQL
connection with TLS and a small explicit pool. Supabase documents direct
connections for persistent backends and session mode for IPv4-only hosts;
transaction pooling has prepared-statement and session-state constraints.
Confirm the actual PP network path and role before configuring either mode.
[Supabase connection guidance](https://supabase.com/docs/guides/database/connecting-to-postgres)
