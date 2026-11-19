# Durable generated smoke capacity

Source candidate only; no PP host action, cloud call or migration applied on PP/cloud.
Fenced-runtime forward recovery remains the separately reviewed operator task.
The existing CD preflight still requires its qualified running prior profile.

## Trigger and resulting behavior

PP20 generated smoke started with 9,997 pending rows under origin `generated-pp`.
It reached the fixed 10,000 pending admission bound and the next candle stopped
before API acceptance. The separate PP live origin had 42,133 acknowledged rows
and zero pending. Repeated generated seed/calculation runs create new immutable
outbox rows, while the existing generated lifecycle has no storage consumer.
The calculation loop can publish every five seconds, so a reusable generated
profile needs a verified destination rather than a fresh origin or a larger cap.

The generated lifecycle now opts into a bounded local storage consumer. Bootstrap
runs it before services/smoke and requires at least 128 free admission slots.
Periodic generated lifecycle cycles keep consuming pending rows. Acceptance
checks the same headroom before the first seed, before a rollover reseed and before reporting PASS.
Every ordinary ingest/calculation still performs its existing serialized
admission check, with the same 10,000 pending limit. Insufficient headroom,
malformed legacy evidence, unavailable storage or exhausted storage capacity
HOLD without reporting acceptance success.

## Genuine generated-local acknowledgement

Migration `0004_generated_outbox_storage.sql` adds a logged table in the existing
local PostgreSQL `archive` schema. Its CHECK constraints require origin exactly
`generated-pp`, a matching canonical envelope origin/id/generation, bounded
bytes, a SHA256 of those bytes, and an existing local generation. Runtime
lifecycle gets SELECT/INSERT; the reader gets SELECT. App/lifecycle get no
UPDATE/DELETE/TRUNCATE privilege on this table. The existing source rows remain.

For each bounded source page, the consumer:

1. Validates complete canonical outbox envelopes and their immutable identities.
2. Rechecks fsync/full-page-write durability and stores append-only exact bytes/hash under a transaction-local synchronous
   commit, accepting a duplicate only if its existing bytes are identical.
3. Opens a separate authenticated lifecycle connection and READ ONLY transaction,
   rechecks database/login/read-only identity, reads committed target rows and
   compares every exact byte/hash/id against the source page.
4. Calls the existing content-checked source acknowledgement only after that
   proof. A failed or ambiguous copy/read leaves the source pending for exact
   reconciliation; a later process can recover the committed target bytes.

This destination is explicitly `durable_generated_local_storage` with
`cloud_receipts=false` and `raw_retirement_authorized=false`. Its rows and source
outbox/raw rows share the same database and failure domain. Supabase receipts,
remote backups and raw-retirement qualification remain separate. No raw archive
manifest, retirement checkpoint, partition DROP or source-row deletion is
performed. The copy is included in migration-preservation inventory by count
and digest, including actual envelope hash and stored metadata.

## Bounds, profile isolation and failure behavior

- The existing per-origin pending cap stays 10,000; the consumer rejects a
  repository configured with a different value. Origin allowlists stay unchanged.
- Each generated cycle is at most 20s, four 250-row pages, eight charged write/read
  operations and 16MiB of logical transfer charges. Page encoding remains capped
  by existing 4MiB limits. Write/read stages use four-second deadlines and SQL
  transaction timeouts; the existing common connection contract is bounded to
  five seconds and late setup refuses acknowledgement under the cycle budget.
- Target capacity is fixed at 100,000 envelopes and 128MiB of logical envelope
  bytes, checked under a dedicated transactional lock. PostgreSQL row/index/WAL
  overhead is additional and existing overall disk checks still apply. Reaching
  the target bound stops progress for review; no automatic deletion/compaction or
  cap increase is included.
- Only generated lifecycle has exact `TRADEBOT_GENERATED_LOCAL_STORAGE=true`.
  The PP live overlay requires false. Other origins, replay mode, live mode and
  malformed selections reject activation. PP cloud probes omit the capability
  and keep their exact profile comparison.
- Source outbox updates serialize through the existing generated structured-sync
  lock. Source admission can run concurrently because acknowledgements only
  reduce pending counts. An unexpected concurrent producer can still exhaust
  headroom; its ordinary admission checks fail closed and acceptance cannot pass
  a partial run.
- CD start requires the typed pending/headroom arithmetic and explicit local-only
  proof before starting services. A generic bootstrap success is insufficient.
  Existing migrations, secret bindings, running-service preflight, process fences
  and post-migration recovery checks keep their authority boundaries.

Rollback uses a schema-compatible image/configuration with the consumer disabled,
retaining migration/table/source rows. An older image without migration 4 cannot
claim compatibility with the upgraded ledger. Deployment and fenced-forward
bootstrap require separate exact-source qualification and operator coordination.

## Native evidence

A disposable official-foundation PostgreSQL 17 fixture uses distinct SCRAM
lifecycle and reader credentials. It creates exactly 10,000 pending generated
rows plus 42,133 preexisting acknowledged live rows. The real consumer and
`lifecycle_worker --once --bootstrap` path qualify:

- Before-copy headroom fails before seed or HTTP access.
- A crash before ACK preserves all 10,000 pending while committed target bytes
  survive. A new repository and a separate bootstrap process reconcile exact bytes and then acknowledges.
- An incomplete independent read returns no ACK; two distinct authenticated
  backend PIDs prove the read is a separate session.
- Owner-only fixture corruption, mismatched exact bytes and target-cap pressure
  refuse ACK. Runtime roles cannot rewrite/delete the target. SQL independently
  rejects a PP live origin.
- Eight repeated seed/calculation cycles keep the fixed origin and pending cap.
  A complete source fingerprint excluding only ACK timestamps is unchanged after
  the initial drain and all later generated writes, and every live row including ACK metadata is unchanged
  through all operations.
- The actual bootstrap CLI emits the scoped headroom proof with retirement OFF
  and raw archive still unqualified. Separate API and acceptance processes pass
  real HTTP/chart/history/two-SSE checks after recovery. No synthetic local proof becomes cloud or
  raw-delete authority.

Validation: 392 backend tests passed (51 external/isolated DSN skips); 210 deploy
control/profile tests passed (5 external/native skips); all 57 real PG17
schema/application/lifecycle/generated-storage tests passed with zero skips,
unchanged shared catalog after tests and final schema validation. The dedicated
full-queue case takes about 10s on local hardware; that is not a PP performance
promise. No generated payload, database, environment credential or secret file
is committed.

## Real Linux controller inventory correction

PR #177 source CI runs 44551764623 and 44551780122 stopped after the fresh
controller migration with `child_failed`. A disposable Ubuntu 24.04 nested Docker
diagnostic reproduced the exact SQL error: the application role cannot SELECT
`archive.generated_outbox_storage`. Migration 0004 deliberately withholds that
grant; the controller's post-migration inventory and recovery inventory used
the application connection for every table. Earlier runtime migration/API checks
passed because they do not run this controller inventory.

The controller now reads only that storage table through the existing mounted
reader credential and an authenticated READ ONLY transaction. All other table
connections, 1024-row digest pages, actual envelope hashing, before/after
comparisons and recovery requirements remain the same. Writers are fenced before
the preservation inventory. No application grant, migration checksum, pending
cap, acknowledgement or storage admission rule changes. Targeted controls cover
an absent pre-upgrade table, an existing table with committed rows, exact digest
fields and the reader command/transaction bounds.

The local nested Docker reproduction is diagnostic evidence only: Docker Desktop
had 6.9 GiB free, so that run substituted the host disk-headroom gate. The real
Linux daemon, restricted roles, migration, table query and credential paths were
exercised. Unmodified hosted CI remains the qualification gate.
