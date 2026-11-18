# CP6 PP Storage permission review — November 17, 2026

Status: **offline policy fixture PASS; live Storage unchanged**. This is a
review template, not an executable migration. It contains no Auth user UUID
or credential and sits outside `supabase/migrations`.

## Current cloud state and exact scope

Read-only project metadata found TokenBot `xttdqeimdujweijxcuro` with a private
`market-raw` bucket and zero `storage.objects` policies. PR #98's separate
NOLOGIN role concerns direct PostgreSQL `history_v2` access; it does **not**
authorize Storage HTTP requests. The template
`supabase/review/pp_market_raw_storage_policies.sql.in` needs an actual,
reviewed dedicated PP Supabase Auth user UUID before it can be applied. Its
unfilled preflight raises and leaves zero policies. No Auth user or token was
created in this checkpoint.

With that UUID filled, it would allow only:

- `INSERT` by that exact authenticated user into private `market-raw` with a
  key matching `raw-v1/<SHA-256 of pp-live-pp>/<generation UUID>/<SHA-256>.jsonl.gz`
  and Storage operation `storage.object.upload`.
- `SELECT` by that same user for `storage.object.get_authenticated` on the same
  path, for exact authenticated readback.

It grants no `UPDATE` or `DELETE` policy and no list, signed-upload, copy,
move, public-read or cross-origin policy. A separate publishable project API
key and the dedicated Auth bearer are required; the service-role bearer would
bypass Storage RLS and must not be installed in PP. The template fails if the
bucket becomes public, Storage RLS is off or any existing object policy appears.

## Generated qualification and limits

An isolated PostgreSQL 17 fixture with no external network exercised the
template using a disposable synthetic UUID. Upload and authenticated GET
passed. Different user and anon access, wrong bucket/origin/key, list,
public-read, signed upload, copy, move, update and delete were denied. The
protected generated object remained after all denial probes. One initial
test exposed a missing UUID group in the proposed readback regex; that was
fixed before the passing fixture. Each transaction models a separate HTTP
request because Supabase's operation helper is STABLE.

These SQL tests prove the **policy expression** against a generated Storage
schema. They do not prove Supabase Auth token issuance/refresh, live Storage
HTTP operation mapping, API gateway behavior, ambiguous uploads or privileged
mutation resistance. The next bounded live test must use a separately
provisioned machine identity, verify create-only upload and fresh authenticated
GET, and assert all relevant deny paths before runtime wiring. Cloud sync and
retirement remain OFF.

## Identity and rollback decision

Provision the dedicated machine identity through Supabase's supported Auth
Admin API, with credentials kept in private secret files. The user UUID is a
binding, not a secret; it must be captured in a separately reviewed policy
migration after the identity exists. Never insert directly into `auth.users`.
The connected Supabase plugin exposes database/migration tools but no Auth
Admin user-creation or session-issuance tool. The Supabase Dashboard's **Create
new user** form requires an email address and password; it has no verified
credential-free machine-user route. The supported Auth Admin API also needs a
secret key and must run in a trusted operator context; that key must never be
installed as PP's Storage bearer. No identity can be bound to this template
until that separate provisioning step produces a reviewed UUID and access-token
refresh route.
If a later policy application fails, keep the runtime OFF, remove only the two
reviewed policies after recording their definitions, and preserve all archive
objects and structured rows. Admin/service-key mutation is outside ordinary
RLS and remains a separate retirement-authorization gate.

Official references: [Storage access control](https://supabase.com/docs/guides/storage/security/access-control),
[operation-aware policy helpers](https://supabase.com/docs/guides/storage/schema/helper-functions),
[Storage operation names](https://github.com/supabase/storage/blob/master/src/http/routes/operations.ts),
[Auth Admin create user](https://supabase.com/docs/reference/python/auth-admin-createuser).
