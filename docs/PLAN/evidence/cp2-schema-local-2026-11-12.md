# CP2 PostgreSQL schema implementation evidence

Scope: local versioned business schema, contract helpers and explicit migration
runner; additive private history_v2 SQL contract only. No live database service,
production, AWS, Supabase, market feed, paid AI, or real retirement was used.

Implemented origin-aware keys, exact finite numeric domains, original RFC3339
source text plus exact sortable NUMERIC epoch, persistent protected evidence and
market/snapshot/reference constraints, UUID-generation raw partitions, outbox,
checkpoints, bounded-expiry dedup and indexes for bounded reads. A narrow lifecycle
role can create registered partitions. Retirement DDL is hard-restricted to
`generated-` origins in preprod and requires transaction-bound readback evidence,
verified manifests, no outstanding outbox/references/readers and explicit gate.
Real retirement authority remains unqualified and disabled by this contract.

Migrations run only via an explicit command. Applied files have a checksum ledger;
repeats validate definitions, columns, constraints, indexes, functions, domains,
sequences, privileges and ownership against the owner-only committed catalog.
Registered dynamic partitions are checked separately. Foundation schema is
validated before first business install. The restricted lifecycle role must be
provisioned explicitly by the administrator; business migrator cannot create roles.

Local result: Python compile succeeded. `PYTHONPATH=backend python -m unittest
discover -s backend/tests/postgres -v` passed six pure contract tests, with eight
actual-PostgreSQL cases skipped because no generated server was running. This is
unit evidence only. Parent owns isolated Linux PostgreSQL 17.12 execution and
integration qualification, including exact SQL install/repeat/upgrade/drift/role behavior. Added generated
checks exercise broken protected references, outcome/market identity, prediction
as-of identity, partition shape/grants, and preservation after a generated raw drop.
DSN fixture names: `TRADEBOT_TEST_MIGRATOR_DSN_FILE`,
`TRADEBOT_TEST_APP_DSN_FILE`; file contents are never printed by the tests.

Limits: no production readiness, capacity, cloud compatibility, sustained lifecycle,
or deployment claim. Cloud SQL is outside local migration discovery and deliberately
has no public policies or service-role mutation grants. CP6 must review and qualify
it independently. Original SQLite modules and shared roadmap/workflows are unchanged
by this workstream; parent consolidates checkpoint evidence in the master roadmap.

References checked November 12, 2026:
- https://www.postgresql.org/docs/17/ddl-partitioning.html (partition uniqueness and locks)
- https://www.postgresql.org/docs/17/datatype-numeric.html (unconstrained exact numeric)
- https://www.postgresql.org/docs/current/datatype-datetime.html (microsecond timestamp resolution)
- https://www.postgresql.org/docs/17/sql-createfunction.html (SECURITY DEFINER fixed search path)
- https://supabase.com/changelog.md (reviewed relevant current changes; no client API applied)

## Generated CI connection correction

Integrated source `1aa8001`, run `43345696255`, passed the CP1 foundation but
stopped before business migration: the NOINHERIT migrator could not read
`ops.environment_identity` through the ordinary runtime connection. Added an
explicit `connect_migrator` path that verifies the login name before SET ROLE,
then validates environment; the migration CLI and schema fixture use that path.
App/lifecycle connections never activate owner. Lifecycle is expected to fail
before explicit business grants are installed and works only after migration.

Local verification after the fix: seven unit tests pass, nine actual database
cases remain pending on the successor generated run. This correction changes no
migration SQL, grants, role inheritance, or current database contents.
