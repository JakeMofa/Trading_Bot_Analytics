# CP6 structured import preparation — November 17, 2026

Status: **preparation PASS; cloud write/readback NOT PROVEN**. This is an offline,
default-off code milestone. It does not grant a runtime role, connect a cloud
writer, acknowledge local outbox rows or authorize local retirement.

## Applied contract and concrete mismatch

The already applied private `history_v2` migration has eight structured data
tables. The local `core.snapshot_evidence` outbox envelope carries a deterministic
`content_hash` derived from its three identity fields. Its cloud table has only
those three fields and two foreign keys; there is no hash column. The new
`cloud_row` mapping verifies that exact derived hash and omits it from the cloud
row. Authenticated readback must reconstruct the hash from the same three keys
before comparing the complete outbox envelope and acknowledging anything.

The mapper pins all eight column sets against the applied migration and rejects
missing/extra fields. Exact numeric text, literal source timestamps, origin,
generation and payload remain bound to their local envelope. `cloud_row_matches`
allows equivalent UTC timestamp rendering while requiring exact numeric spelling
and exact source-time spelling. This comparison is a preparation helper, not a
remote verification result.

## Mutable projection ordering

`markets` and `current_prices` have one cloud row per origin-aware identity but
can have multiple local outbox revisions. The current batch validator continues
to **HOLD** when conflicting revisions of an identity appear in one batch.
`projection_order` classifies a later market by `last_seen` and a later price by
`(source_epoch, received_at)`. Older revisions and same-time content conflicts
HOLD. This rule has **not** been installed as a cloud update. The eventual writer
must enforce it atomically in cloud PostgreSQL and bind a cloud checkpoint to the
committed revision before local acknowledgement. A read-then-write decision in
application code would race another importer. In particular, a newer cloud row
cannot serve as exact readback of an older local outbox revision.

## Remaining CP6 gates

1. Review a narrow direct-database runtime identity and grants for the private
   schema, or another server-side atomic write path. The current schema has zero
   runtime grants/policies; no credentials are configured. Do not expose
   `history_v2` broadly through the Data API just to make this adapter work.
2. Design atomic mutable revision/checkpoint writes, duplicate and crash retry
   behavior, and an exact readback for every local outbox revision. Preserve
   separate PP and production origins.
3. Implement and run the default-off cloud adapter against an isolated database,
   then separately review bounded authenticated Supabase writes/readback and
   permissions. Raw Storage transport in draft PR #79 is independent.
4. Qualify privileged object mutation fencing before any retirement authorization.
   RLS on an ordinary runtime identity does not constrain project admins or a
   service-role key. Mandatory final fresh readback remains in force.

Focused local tests: `PYTHONPATH=backend:backend/tests python3 -m unittest
test_history_v2_envelope test_postgres_lifecycle -q` — 28 PASS. They include
generated duplicate/conflict, hash/shape, timestamp/decimal, and existing
partial-failure/readback lifecycle cases. No live cloud attempt was made.
