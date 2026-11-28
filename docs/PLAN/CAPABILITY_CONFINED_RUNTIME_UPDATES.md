# Capability-confined runtime updates

Status: architecture review and proposed qualification; no new rollout or
database policy is implemented here. Schedule this after Benchmark .14's
four-hour and 24-hour acceptance, before general same-schema collector
updates. Follow the [master checkpoint](INTELLIGENCE_REBUILD_PLAN.md) for
operational authority and current state.

## Why this checkpoint is needed

The .14 package, source `9a6f61bdfcab294c9b8e833d926af6ed8f1ba27d`, qualified
current-size recovery in 151.904/180 seconds. That includes fencing four
application containers, PostgreSQL identity, two fresh complete 11-table /
15-origin inventories and a real prediction anchor. History growth increases
those custody reads. This result does not qualify 72-hour capacity.

Separate runtime replacement from schema migration by restricting what the
replacement can change. Keep all 20 retained generations and A/B intact.
The existing full-CD custody and recovery checks stay required until a new
route passes its own review and qualification.

## Existing capability boundaries

- [API-only replacement](../../deploy/preprod/api_component_update.py):
  `compatible_build()` requires identical migration files and build/runtime
  contracts. `protected_state()` freshly checks the deployed schema ledger,
  protected container identities and writer UUID/epoch/generation. Replacement
  targets only API, whose Benchmark credential is SELECT-only with two local
  reader sessions. Independent renewal and rollback preserve collection. This
  is the existing example of a component update without a global history scan.
- [Store](../../backend/postgres/store.py): `_locked_writer()` takes `FOR SHARE`
  on the writer pointer; `ingest()` checks the producer UUID, collecting
  generation, enabled state and database-clock lease. These checks execute in
  application code inside a transaction. They are not a universal PostgreSQL
  write-admission policy for clients bypassing Store.
- [Business grants](../../backend/postgres/migrations/0001_business.sql),
  lines 198–234: app receives INSERT on raw/evidence/prediction/outbox tables
  and raw child partitions; some projection tables permit UPDATE. Denied
  UPDATE/DELETE on append-only records does not prevent new rows being added
  to retained history. Lifecycle can update archive generations, manifests,
  checkpoints and writer state, and acknowledge outbox records.
- [Operator runtime](../../backend/postgres/operator_runtime.py) mounts both
  app and lifecycle credentials. Restricting an INSERT trigger to the current
  generation would be insufficient if that same replacement could change the
  generation state or writer pointer through broad lifecycle privileges.
- [Retirement fence](../../backend/postgres/migrations/0003_pp_retirement_authority.sql)
  and later trial-specific migrations protect selected origins from insertion
  into absent/retired generations. They allow collecting, sealed and verified
  states. They do not establish exact producer authority for Benchmark raw
  inserts or freeze every retained rowset.

These observations identify enforcement boundaries; no data alteration was
observed in this review.

## Smallest qualification milestone

1. **Audit effective capabilities.** Record actual privileges, inheritance,
   function execution, ownership, triggers, direct child access and mounted
   credentials for each replaceable component. Keep API-only updates within
   their existing reader boundary. Identical schema files alone are not a
   writer confinement proof.
2. **Enforce write admission in PostgreSQL.** Design a separately reviewed
   hardening migration that binds exact origin, current collecting generation,
   producer authority and unexpired lease before canonical writes. Cover
   parent and direct-child inserts, immutable evidence, revisions and outbox.
   Deny retained/other-origin insertion and unauthorized historical mutation.
   A caller-selected GUC or publicly readable UUID alone is not authority.
   Define legitimate mutable projections separately from immutable input and
   prediction history.
3. **Isolate the control plane.** Remove broad lifecycle table authority from
   the replaceable ingestion process. Expose narrowly scoped lease/state/ACK
   operations with fixed transitions and restricted execution; preserve fresh
   ownership checks and stale-producer rejection. Keep the existing physical
   connection budgets, including operator6 + calculation2 and reader2 +1 +1.
   Qualify compatibility before adopting the one-time migration.
4. **Prove the boundary with native SQL.** Bypass Store in generated PG17 tests:
   attempt sealed/other-origin writes, direct child inserts, stale producers,
   valid-UUID/GUC spoofing, expired leases, unauthorized state/ACK changes,
   UPDATE/DELETE, DDL and trigger bypass. Race admission against rotation,
   transfer and explicit OFF. Test inherited/function privileges and recovery
   after cancellation. Verify retained fixtures remain unchanged.
5. **Qualify the runtime-only route.** Require identical migration/schema ABI,
   fresh actual schema/ACL/trigger/function-contract attestation, exact release
   and container binding, fresh lease authority and bounded new-event readback.
   Historical rows can leave this route's scan only when the replacement has
   no capability to change their protected contents or membership. Prior
   custody hashes do not become fresh authority. Migration or capability drift
   continues through the full-CD route. Test crash, refusal and exact rollback.

## Separate handoff and retention work

Collector replacement also needs the
[continuous handoff protocol](CONTINUOUS_COLLECTOR_HANDOFF.md): standby capture,
bounded durable buffering, exclusive producer transfer, no doubled connection
budgets, and protection against stale finalizers. A same-schema route does
not itself preserve vendor capture through a process replacement.

GitHub read-only verification on November 28 confirmed
[#209](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/209) merged on
November 24 and [#252](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/252)
merged on November 28 (merge dates are UTC). Their
[resumable verification qualification](LONG_WINDOW_QUALIFICATION.md) remains
generated/offline evidence. The
[prototype](../../deploy/preprod/long_window_shadow.py) explicitly restricts
itself to disposable generated-shadow scope and exposes no removal API.
Hosted immutable inventories, version invalidation, exact Storage versions,
reader/policy lifetime and protection through local removal still need proof.
Retained outbox, protected inputs, snapshot links and deduplication coverage
also need a qualified retention policy. This checkpoint grants no deletion
authority, budget increase, cached ownership or 72-hour rollout.
