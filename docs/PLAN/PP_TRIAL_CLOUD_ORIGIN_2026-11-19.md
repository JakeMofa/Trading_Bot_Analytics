# Exact fresh PP trial cloud scope — source-only review

Base source: `e00bd2c`. Exact new origin:
`pp-live-pp-trial-20261119-01`. No Supabase inventory query, mutation, Auth-user
provisioning, secret deployment, host operation or collector activation was
performed by this slice. Catalog statements below describe committed source and
prior evidence, not a fresh live inventory. The existing `pp-live-pp` origin,
its identities, rows, archives and policy definitions remain unchanged.

## Authority mapping

| Surface | Existing source binding | Trial source candidate |
| --- | --- | --- |
| Structured SQL writer | `tradebot_pp_history`; exact `pp-live-pp` RLS | `tradebot_pp_trial_20261119_01_writer`; exact trial RLS |
| Structured verifier/reader | Existing SQL role has writer grants; transactions read-only | Separate `tradebot_pp_trial_20261119_01_reader`, SELECT only |
| Structured data | Nine projections/checkpoints plus immutable receipts and revision envelopes | Same existing eleven tables, additive exact-origin rows/policies; coverage stays inaccessible |
| Mutable SQL | UPDATE markets/current_prices/generation_checkpoints only | Same three tables for writer only; reader no INSERT/UPDATE/DELETE/TRUNCATE |
| Raw Storage | `market-raw`, exact old Auth UIDs and old origin SHA-256 path | Same private bucket; two new exact Auth UIDs, independent archive writer and history reader |
| Storage path | `raw-v1/6157f780…/<uuid>/<sha>.jsonl.gz` | `raw-v1/ab43e88045d4c354566bc2612c83b04a8636bfeea44e54aa839d0f807ac4446f/<uuid>/<sha>.jsonl.gz` |
| Raw operations | Create-only writer + authenticated readback; independent read-only Auth identity | Same operations; reader cannot upload; neither may list/overwrite/update/delete/copy/move/sign/public-read |

Adding exact trial policies to the old SQL/Auth principals would give each old
credential authority over both old and new origins. It is technically possible
with exact equality rather than a prefix, but it removes principal isolation
between draining old data and the new trial. The smallest isolated additive
path is two new SQL roles and two new Auth identities while reusing the schema,
bucket, project publishable key, TLS CA and existing archive format. No new
Supabase project, bucket, database or broad `pp-live-%` cloud policy is needed.

## Review-only policy artifacts

- `supabase/review/pp_trial_20261119_01_structured.sql`: transaction creates two
  NOLOGIN/NOINHERIT/NOBYPASSRLS roles, limit two connections each, exact trial
  policies and SELECT11 / writer INSERT11 + UPDATE3 grants. It creates no login,
  password or membership and grants no coverage/future-table/public privileges.
  Restrictive exact-origin fences protect both roles even if another permissive
  policy exists. Existing role/policy definitions are preserved.
- `supabase/review/pp_trial_20261119_01_storage.sql.in`: requires two new distinct
  canonical Auth UIDs/emails with confirmed, admin-controlled `app_metadata`
  (`tradebot_origin=pp-live-pp-trial-20261119-01`; writer role
  `pp_storage_archive`, reader `pp_storage_history_reader`). It checks the exact
  fresh Storage policy-catalog SHA-256, private bucket and RLS before creating
  six additive trial policies. Restrictive fences affect only the two new UIDs.
- `deploy/preprod/bind_trial_cloud_policy.py`: offline create-only renderer;
  takes reviewed UIDs/emails/catalog hash, never credentials. Templates remain
  outside migrations and CI/CD does not apply them.

Fresh operator catalog hash, after inspecting every existing policy:

```sql
SELECT encode(sha256(convert_to(
  COALESCE(jsonb_agg(to_jsonb(p) ORDER BY p.policyname),'[]'::jsonb)::text,
  'UTF8')),'hex')
FROM pg_policies p
WHERE schemaname='storage' AND tablename='objects';
```

A changed hash aborts instead of dropping or editing legacy policies. Before
application also inventory existing table/domain/function grants, RLS, table
owners, role attributes/membership and any default/public privileges. The SQL
schema candidate checks table presence/RLS and refuses pre-existing trial roles;
it does not replace this full fresh operator review.

## Runtime binding interfaces and remaining integration dependencies

`backend/postgres/cloud_origin_binding.py` admits only the two reviewed exact
origins. `cloud_binding(origin).role(reader=bool)` selects the pinned role;
`raw_prefix` derives its exact origin SHA-256. It reads no environment variables.

- `PPHistoryConnectionFactory(origin_id=TRIAL_ORIGIN, reader=False/True)` pins
  the new writer/reader pooler username and matching `application_name`; project,
  pooler host, database `postgres`, CA hash, TLS verify-full and timeout remain
  fixed. `ReusablePPHistoryConnectionFactory` inherits these explicit arguments.
- `HistoryV2PostgresTransport(..., origin_id=TRIAL_ORIGIN,
  expected_database='postgres', expected_role=binding.role(reader=...))`
  accepts only those trial roles. A reader append fails before connection; SQL
  privileges independently reject mutation. Receipt/envelope and exact decimal
  verification remain unchanged. Existing explicit test constant substitution
  remains available for disposable generated tests; no runtime environment can
  broaden the allowlist.
- `SupabaseStorageTransport.from_machine_files(..., origin_id=TRIAL_ORIGIN,
  reader=...)` checks trial admin-controlled JWT origin/operation-role metadata
  and rejects keys outside its exact trial prefix before I/O. Reader uploads
  fail. Legacy default behavior is preserved; legacy generation scoping remains
  enforced by its existing `ScopedArchiveTransport` and server policies.

These adapters do **not** automatically activate trial services. Integration
must pass exact trial origin/role/credential selection into structured service,
sealed raw worker, retirement verification, retained audit and runtime history.
At the inspected base these call sites still import or close over the legacy
`ORIGIN`/role and default credential files. Trial verifier and reader must use
`reader=True` SQL factory plus the new read-only expected role, not trial writer
credentials. Old A/B drain keeps old bindings and cannot consume trial authority.
Cloud grant application alone therefore cannot make a fresh trial ready.

## Operator prerequisites and reversible deployment

1. Keep collectors fenced while qualifying the new exact-origin profile and
   independently preserve/drain old A/B under their own origin/authority. Do not
   relabel, copy, renew old deadlines or count maintenance disposition as a
   fresh-trial pass.
2. Review the live schema/role/policy inventory and candidate SQL. Create two
   separately authenticated, confirmed machine Auth identities through the
   supported Auth Admin API; verify returned UIDs/emails/app metadata. Render
   Storage SQL using their actual identities and the fresh catalog hash.
3. Apply only separately reviewed additive SQL/policies through the approved
   operator route. Provision writer/reader SQL login secrets separately (the
   source roles remain NOLOGIN until then); use no broad role membership or
   service-role bearer. These are deployment prerequisites, not changes already
   performed. Runtime role checks require the actual login/current_user to be
   the exact pinned writer or reader role.
4. Stage separate private files, for example trial writer/reader DSNs and trial
   archive/history-reader Auth files, with existing ownership/mode checks. Keep
   legacy files intact for old-data disposition. Project publishable API key and
   pinned CA may be reused; passwords/DSNs/Auth identities must stay separate.
   No secret belongs in Git, command output, a report or model context.
5. Mount only trial writer secrets to archive/import workers, only trial reader
   secrets to verifiers/history API. Confirm exact source/image/profile/role
   and perform bounded real API/SQL positive and negative tests: exact upload,
   authenticated readback, no old/production access, reader mutation denial,
   listing/overwrite/delete/copy/signed/public denial, original decimals/times,
   genuine receipts/envelopes and independent readback before local ACK.
6. If qualification fails: stop trial workers/collector and release their
   sessions, unmount only trial secrets, disable only the two new SQL logins and
   revoke their table/function/schema privileges. Retain data and role/policy
   definitions for evidence. For immediate raw-access revocation, separately
   review dropping only new **permissive** upload/select policies while keeping
   restrictive fences; globally sign out only the new Auth identities and
   verify remaining JWT requests are denied. Deleting an Auth user alone does
   not invalidate access tokens. Do not remove old credentials, archived rows,
   raw objects, bucket/schema or legacy policies. Re-enablement requires exact
   fresh review, never a broad policy or a token/grant bypass.

## Generated qualification

Six adapter tests and six native PG17 policy tests pass without skips. The
owned disposable PostgreSQL17 cluster uses only a Unix socket and generated
records; no externally supplied DSN or secret is accepted. The tests execute
existing schema migrations, actual new SQL RLS/grants and a Storage-policy
approximation, verify old policy definitions unchanged, and prove old/trial/
production/generated isolation. A genuine trial structured price envelope with
nanosecond epoch, exact decimal and NULL is inserted by the trial writer; the
separate read-only role verifies actual receipts and immutable envelope bytes.
Restrictive fences survive deliberately broader generated permissive policies;
wrong catalog hashes, opposite/old DSNs, bad JWT metadata and reader writes fail.

The actual Supabase Storage HTTP operation mapping, Auth-user provisioning,
login/session limits, runtime integration/deployment and real cloud readback
remain unqualified. Local policy approximation cannot close those live gates.
Existing 5 connection, 10 session, 5 Storage-wire and 12 Auth-wire tests pass;
16 externally configured structured PG cases skip without their explicit DSN.

```sh
python -m unittest discover -s backend/tests -p test_trial_cloud_binding.py -v
python -m unittest discover -s backend/tests -p test_trial_cloud_policies_pg.py -v
```

Guidance checked November 19: [Supabase changelog](https://supabase.com/changelog),
[grants and RLS](https://supabase.com/docs/guides/database/postgres/row-level-security),
and [Storage access control](https://supabase.com/docs/guides/storage/security/access-control).
The reviewed docs distinguish grants from row policies and confirm that create-only
upload needs INSERT, while overwrite/upsert additionally needs SELECT/UPDATE;
those overwrite privileges are deliberately absent here.
