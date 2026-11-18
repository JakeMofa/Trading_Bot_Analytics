# CP6 sealed structured drainage — November 17 CST / November 18 UTC

Status: **PASS in generated Linux PostgreSQL; PP runtime NO-GO**.
This is a stacked, default-OFF change on draft PR #92. No host, Supabase
permission, schema, cloud data or production setting changed.

## Ordering and deadline model

The single-writer local switch seals A before B accepts writes. B's structured
worker holds while any other same-origin generation has pending outbox rows.
A separate worker can drain sealed A while B keeps collecting. Both workers
take one PostgreSQL session advisory lock per origin across import, fresh
readback and local ACK. Contention returns HOLD before cloud I/O. A crashed
worker loses its local session lock; a retry remains idempotent against the
cloud receipt/checkpoint transaction. PostgreSQL documents that session
advisory locks release when the session ends.
[PostgreSQL 17 advisory locks](https://www.postgresql.org/docs/17/explicit-locking.html#ADVISORY-LOCKS)

The direct structured adapter uses PostgreSQL 17 `transaction_timeout` for
each whole cloud import/readback transaction and gives its connection factory
the same per-call budget. Connection time and transaction time share one
monotonic request deadline. The local ACK transaction uses the remaining cycle
budget and PostgreSQL transaction timeout. A late return after a committed
cloud write or local ACK is reported as an **ambiguous failure**, not a PASS;
retry reconciles durable state. [PostgreSQL 17 timeout documentation](https://www.postgresql.org/docs/17/runtime-config-client.html)

## Generated evidence

- Local focused suite: 36 passed, including sealed A → collecting B,
  A-pending/B-newer HOLD, cloud outage, ambiguous post-commit response,
  corrupted readback, deadline/cancellation and concurrent workers.
- Isolated PostgreSQL CI adds same-origin advisory-lock contention, an actual
  two-generation pending-outbox guard, timeout-setting and slow-connection
  checks. Source `8f4d498` passed exact
  [push CI 44221644336](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44221644336)
  and [PR CI 44221649679](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44221649679).
- This slice creates no cloud adapter runtime, service scheduling, raw archive
  path or retirement authority. The pending-outbox cap remains 10,000.

## Remaining runtime gates

The local lock requires an actual PP connection factory with a verified
connection timeout. PostgreSQL 17's transaction timeout must be confirmed
against the intended Supabase project and narrow PP role. A separate runtime
integration must schedule sealed A drainage before B sync without starving
collection. Actual PP authenticated readback, sustained backlog reduction,
outage runway and cloud mutation authority remain unproven. Until those pass,
this code does not authorize PP cloud enablement or raw retirement.
