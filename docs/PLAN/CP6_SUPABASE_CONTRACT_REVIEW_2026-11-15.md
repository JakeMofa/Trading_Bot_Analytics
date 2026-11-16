# CP6 Supabase contract review — November 15, 2026

## Read-only cloud inventory

The confirmed project is `xttdqeimdujweijxcuro`. Its existing structured
history is in ten `public` tables, including markets, candles, feature snapshots,
predictions, official outcomes, sync checkpoints and raw archive metadata.
`history_v2` has no tables. The Supabase migrations-list call returned an internal
error. A read-only catalog query independently found two recorded migrations,
latest version `20261023023156`; their contents and tool-level history remain
unverified. No cloud DDL or data writes were performed for this review.

The security advisor reports ten existing public tables with RLS enabled and no
policies, and one existing public `SECURITY DEFINER` function, `rls_auto_enable()`,
executable by `anon` and `authenticated`. The latter needs a separate ownership
and intended-use review before any privilege change; CP6 does not alter it.
[Advisor documentation](https://supabase.com/docs/guides/database/database-linter?lint=0028_anon_security_definer_function_executable).

## Generated contract qualification

The proposed `backend/postgres/history_v2_contract.sql` remains an unapplied
contract. CI now applies it inside the disposable PostgreSQL fixture, checks that
the count of public tables is unchanged, all ten private tables have RLS enabled,
`anon` and `authenticated` lack schema/table access, and a pre-1970 fractional
timestamp remains exact. The fixture is destroyed after qualification. This is
not evidence of cloud permissions or application write/readback behavior.

Source `bc3db426a51bed67419825b4c695b39bc957eb6d` passed
[exact-source CI 43805048832](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/43805048832)
and [PR CI 43805066582](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/43805066582).
The sanitized generated artifact reports ten private/RLS tables, zero public
table-count change, no `anon`/`authenticated` schema or table access, and exact
epoch `-0.000000001`. It records `production_access=false` and
`cloud_writes=false`.

## Exact cloud migration gate

Before applying additive DDL, compare the live catalog and migration history to
the reviewed source. Use a named migration, preserve all existing public tables,
and qualify the exact importer and retriever role grants in an isolated fixture.
The collector and public API must have no cloud DDL, delete or overwrite grant.
Test exact decimals/timestamps, provenance, duplicate and conflicting identity
handling, generation-specific checkpoint progress, and authenticated archive
readback on bounded synthetic records. Record the project, migration identity,
row/object counts and sanitized results. A failed check leaves retirement OFF.

Supabase service-role/admin access can bypass ordinary RLS and alter Storage
objects. A private schema and RLS alone do not establish immutable archive
evidence. Keep full fresh authenticated readback before local retirement until
the privileged mutation paths, policy continuity and final authorization race
are separately qualified. No local deletion is enabled by this review.

## Schema-only successor prepared for review

`supabase/migrations/20261116050000_history_v2_private.sql` is the exact
additive migration candidate. It creates only the ten `history_v2` tables,
domains, timestamp parser and indexes in the existing contract. It revokes
schema, table and function access from `PUBLIC`, `anon`, `authenticated` and
`service_role`; it changes no existing `public` table. CI requires the migration
body to match the reviewed contract and applies the exact file to a disposable
PostgreSQL database. No importer or retriever can use it yet.

**Cloud application gate:** compare live catalog/migration version again, apply
this named migration only once through the Supabase migration facility, and
recheck ten private RLS tables, grants, public table inventory and advisories.
A failed migration or unexpected drift stops client integration. Dropping the
schema is not an automatic rollback; the release is additive and default-off.
Cloud application is separate from this local candidate and its generated test.

## Cloud schema outcome

The exact merge commit `589bb9786d91659d5939c72fbbf0a9e00ce5e52d`
passed [preprod CI 43807662623](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/43807662623).
Its migration SHA-256 was
`f30df30ddb45815bd1c6df316a7c4f7f39883e6bf0a5fc332501f67f51d7c275`.
The Supabase migration facility applied it once as
`history_v2_private_20261116`, ledger version `20261116050522`.

Read-only post-checks showed ten empty private tables, all ten with RLS;
`PUBLIC`/`anon`/`authenticated`/`service_role` have no usable table access,
and the public table count remained ten. The ledger moved from two to three
entries. The advisor now reports ten additional informational RLS-without-policy
notices for the new intentionally inaccessible tables. Its pre-existing public
security-definer warning remains unresolved; this migration did not alter it.
[Sanitized exact result](evidence/cp6-history-v2-schema-2026-11-16.json).

This proves schema installation only. Runtime importer/retriever permissions,
structured writes, private Storage upload/readback, archive mutation authority
and recovery/replay remain unqualified. Retention and retirement stay OFF.

Production and PP collectors, retirement and paid AI remain unchanged. CP6, I7
and Phase 1.75 are OPEN.
