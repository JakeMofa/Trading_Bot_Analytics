# PP Storage archive identity: operator review

This command prepares **one dedicated PP Supabase Auth user** for the private
`market-raw` Storage policy. It does not apply that policy, install credentials
on PP, enable cloud sync, or authorize retirement. It has no application startup
hook. Production remains separate.

The operator supplies an explicit dedicated email and an existing private
Supabase admin/secret key file. The command binds the exact Tradebot project
`xttdqeimdujweijxcuro`, creates an email-confirmed Auth user through the
supported Admin endpoint, and sets admin-controlled metadata
`tradebot_role=pp_storage_archive` and `tradebot_origin=pp-live-pp`. It prints
only the returned Auth UUID after validating the response. It never sends a
confirmation invitation and never inserts into `auth.users` directly.

## Reviewed invocation, not yet run

The output parent must already exist, be owned by the operator, and be mode
`0700`. The admin key file must be a regular one-link file owned by the operator
or root, inaccessible to group and others. Use a **new** output directory on a
private operator filesystem. Do not put it in Git, a CI artifact, shell tracing,
or a shared temporary directory.

```sh
python3 deploy/preprod/provision_supabase_archive_identity.py \
  --project-ref xttdqeimdujweijxcuro \
  --email 'DEDICATED_PP_ARCHIVE_EMAIL' \
  --admin-key-file '/PRIVATE/ADMIN_KEY_FILE' \
  --output-dir '/PRIVATE/NEW_PP_ARCHIVE_STAGE' \
  --execute
```

The stage is mode `0700`; `supabase_auth_email`, `supabase_auth_password`,
`supabase_auth_uid`, and `status` are mode `0400`. The admin key stays in its
input file and is never copied into the stage. A separate reviewed installation
step will transfer the email, password and UUID to PP's runtime identity as
private files. The Storage runtime must never receive the admin key.

The command durably writes `UNCONFIRMED_CREATE` **before** its one HTTP POST,
which has a ten-second deadline and no redirect or proxy. Short local writes
are completed or the partial file is removed before any request. A definite
Auth rejection removes the new stage. A timeout, server error, malformed
success, identity mismatch, or post-success local write failure leaves the
private credential and `UNCONFIRMED_CREATE` status for operator reconciliation.
**Do not rerun
after an uncertain result.** Inspect the intended project's Auth Admin record
for the exact email, UUID and metadata, then decide whether to complete or
discard the stage. An existing stage blocks another request. No automatic
delete or recreation is attempted, because the first POST may have succeeded.

This command does not protect against privileged Supabase service-key or
administrator mutation of published Storage objects. The separate retirement
authorization gate remains in force; local raw retirement stays OFF.

Official references: [Auth Admin create user](https://supabase.com/docs/reference/python/auth-admin-createuser),
[Storage access control](https://supabase.com/docs/guides/storage/security/access-control).

## PP archived-history reader

For the dashboard/API reader, use the same private operator-side Admin Auth
route with `--purpose history-reader`, a dedicated machine email and a new
private output directory. The implementation stages `history_reader_email`,
`history_reader_password` and `history_reader_uid`. A successful response
must echo the dedicated reader UID and the admin-controlled metadata
`tradebot_role=pp_storage_history_reader` and `tradebot_origin=pp-live-pp`.
Keep the privileged Admin key on the operator host.

Independently verify the distinct reader and writer UIDs. Bind those IDs in
`supabase/review/pp_history_reader_policies.sql.in` and review the rendered
exact-bucket, exact-origin policy. The PP release expects authenticated GET of
known archived bytes, denial of wrong-origin access and list/upload/replace/
move/delete operations, and exact source/image binding. Use separately scoped
sacrificial HTTP fixtures for mutation-denial tests. The earlier writer's
successful uploads do not establish the reader's authority.

After the effective HTTP proof, install the reader's separate publishable
project key and three dedicated Auth files as `0400` owned by UID 10001 in PP's
runtime secret directory. The root-owned `0400` scope proof and its hash-bound
authority marker bind the exact application image and source. The host
controller validates those bindings before including the optional reader
overlay. Requalify the binding for the release that will serve archived history.
