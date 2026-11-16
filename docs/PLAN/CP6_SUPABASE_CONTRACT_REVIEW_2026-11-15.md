# CP6 Supabase contract review — November 15, 2026

## Read-only cloud inventory

The confirmed project is `xttdqeimdujweijxcuro`. Its existing structured
history is in ten `public` tables, including markets, candles, feature snapshots,
predictions, official outcomes, sync checkpoints and raw archive metadata.
`history_v2` has no tables. The Supabase migrations-list call returned an internal
error, so migration history is **not verified**. No cloud DDL or data writes were
performed for this review.

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

Production and PP collectors, retirement and paid AI remain unchanged. CP6, I7
and Phase 1.75 are OPEN.
