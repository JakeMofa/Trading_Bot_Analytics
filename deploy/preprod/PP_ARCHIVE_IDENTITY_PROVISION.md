# PP Storage archive identity: operator review

This command prepares **one dedicated PP Supabase Auth user** for the private
`market-raw` Storage policy. It does not apply that policy, install credentials
on PP, enable cloud sync, or authorize retirement. It has no application startup
hook. Production remains separate.

The operator supplies an explicit dedicated email and an existing private
Supabase admin/secret key file. The command binds the exact TokenBot project
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
