# CP6 PP private-history SQL role review — November 17, 2026

Status: **generated SQL qualification pending; live Supabase unchanged**.
This is one small permission candidate for draft PR review. It does not turn on
structured sync, Storage upload, or local partition retirement.

## Read-only cloud facts

The connected TokenBot project `xttdqeimdujweijxcuro` has the applied private
`history_v2` schema migration `20261116050522`: ten RLS-enabled tables, zero
RLS policies, and table/schema access only for `postgres`. No `tradebot`, PP,
history-import, or archive login role exists. `market-raw` is private;
`storage.objects` has zero policies. The draft PR #92 receipt migration is
**not applied**. This inspection read catalog and bucket metadata only, not
credentials, user rows, archive objects, or application data.

The Supabase advisor also reports a pre-existing, separate warning:
`public.rls_auto_enable()` is SECURITY DEFINER with anon/authenticated EXECUTE.
It is an event-trigger function owned by `postgres` that enables RLS on new
public tables. Its scope and grants need independent review; this PP role
migration does not change it or claim to resolve that advisory.

## Narrow SQL role candidate

The additive migration `20261118020000_pp_history_v2_role.sql` creates
`tradebot_pp_history` as **NOLOGIN, NOINHERIT, NOBYPASSRLS**, without
superuser, role, database or replication powers, and with a two-connection
limit. A future secure credential/connection review must explicitly change
NOLOGIN before any runtime can use it. The role receives schema/type usage and
only the timestamp-validation function's EXECUTE privilege, needed for market
and current-price timestamp checks; a generated market insert exercises it.
It receives
SELECT/INSERT on the eight structured tables plus generation checkpoints;
UPDATE only on markets, current prices, and generation checkpoints. It gets
no DELETE, DDL, `coverage`, public-history, Storage, or receipt-table grant.
Each table's SELECT, INSERT and applicable UPDATE policy binds **exactly**
`origin_id = 'pp-live-pp'`; a prefix match is insufficient.

The connected project currently has no role matching `tradebot_pp_history`.
The migration intentionally uses `CREATE ROLE` without `IF NOT EXISTS`:
an unexpected name collision or manual replay stops rather than silently
accepting unreviewed privileges. The Supabase migration ledger, when the
file is later applied, is responsible for one-time execution.

The generated PostgreSQL gate applies the existing private schema, this role
migration and SQL denial probes in a disposable database. It must prove a PP
checkpoint insert/read/update, hide and reject production-origin rows, and
reject deletion, immutable-row update and unqualified coverage access. It
also checks that anon/authenticated/service-role remain outside `history_v2`.

This role is deliberately incomplete for PR #92: `structured_receipts` does
not exist on `preprod`. After PR #92 is reviewed and merged, a separate
extension must grant it only SELECT/INSERT with exact-origin policies and
exercise the actual importer under the narrow identity. No conditional grant
or duplicate PR #92 DDL is hidden in this migration.

## Separate Storage and connection gate

The raw Storage adapter requires a publishable project API key plus a distinct
bearer identity. A dedicated Supabase Auth machine identity, scoped by exact
UID, private `market-raw` bucket and the hash-derived `raw-v1/` PP-origin
namespace, can receive INSERT and authenticated-object-read SELECT policies.
It must receive no UPDATE, DELETE, list, move or copy permission. Actual
operation-aware policy behavior, token issuance/expiry and denial tests are
still open. The service-role key bypasses Storage RLS and is unsuitable as the
PP runtime bearer. Admin and service-key mutation remain outside an ordinary
RLS policy; local retirement needs a separate mutation-fence decision and
fresh authenticated readback.

The direct PostgreSQL endpoint may require IPv6; an IPv4-only PP host must use
the reviewed session pooler. Exact host reachability, TLS verification, a
small connection pool, connection timeout and a whole-operation deadline are
unqualified. The prepared importer currently limits individual statements,
not connection establishment or the entire transaction.

**Rollback:** with runtime still NOLOGIN/OFF, a failed generated or cloud
permission test leaves sync and retirement OFF. If the reviewed migration is
ever applied and needs revocation, first stop the runtime, revoke its grants
and policies, disable LOGIN, and preserve cloud rows and objects for evidence.
Do not delete history or archived raw data as a permission rollback.

Official references: [Supabase Storage access control](https://supabase.com/docs/guides/storage/security/access-control),
[operation-aware Storage policies](https://supabase.com/docs/guides/storage/schema/helper-functions),
[PostgreSQL connection modes](https://supabase.com/docs/guides/database/connecting-to-postgres).
