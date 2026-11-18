# PP market-raw Storage binding and qualification

Status: **offline controls implemented; live policy and probe not executed**.
This is a scoped checkpoint under the authoritative
`docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md`. It does not authorize retirement.
The policy follows Supabase's [Storage access-control guidance](https://supabase.com/docs/guides/storage/security/access-control)
and [operation helpers](https://supabase.com/docs/guides/storage/schema/helper-functions).

## Binding

The reviewed SQL grants only `INSERT` for `storage.object.upload` and `SELECT`
for `storage.object.get_authenticated`, to one dedicated authenticated Auth
UID. Its path is restricted to `raw-v1/<SHA-256 of pp-live-pp>/<generation UUID>/<object SHA-256>.jsonl.gz`
inside private `market-raw`. There is no update, delete, list, move, signed
URL or public retrieval grant. Service-role and project-admin bypass authority
remains a separate retirement blocker.

The SQL preflight requires the exact canonical UID, exact reviewed email,
`authenticated` role, and admin-controlled `raw_app_meta_data` markers
`tradebot_role=pp_storage_archive` and `tradebot_origin=pp-live-pp`. It also
requires private `market-raw`, Storage object RLS, and **zero existing object
policies**. Any drift aborts the transaction before policy creation. The
renderer accepts only the pinned template digest, the expected project ref and
bucket, and writes a private new file without overwriting an existing file.
The operator must independently confirm that the SQL connector is targeting
Supabase project `xttdqeimdujweijxcuro`; a local renderer cannot attest the
remote connector's selected project.

The separate rollback candidate checks for exactly the two reviewed policy
names, commands, roles, operation predicates and UID binding before dropping
them. It **only revokes policy grants**. It does not remove Auth users, archived
objects or any local database rows. Changed policy definitions require manual
review rather than a blind rollback.

## Live probe, when separately reviewed

`deploy/preprod/probe_market_raw_storage.py` requires an explicit `--live`,
the exact project URL and bucket, private token files, and the reviewed Auth
UID/email. It checks `/auth/v1/user` and the admin-controlled markers before
writing. It creates one random-generation, two-record gzip object under the
PP origin, with `x-upsert:false`; reads it back through authenticated Storage;
compares exact bytes and SHA-256; and checks that a bearer-free public GET
cannot retrieve it. A timed-out or duplicate POST is **never retried**; one
authenticated GET reconciles the exact bytes or the probe fails. The object
remains in private Storage as audit evidence.
The API key must use the `sb_publishable_` format; secret and legacy
service-role keys are rejected by the probe. Supabase's [API key guidance](https://supabase.com/docs/guides/getting-started/api-keys)
confirms that secret/service-role keys bypass RLS.

Bounds: at most five HTTP attempts, a 30-second normal deadline (180-second
absolute input ceiling), five seconds per request, and 64 KiB per response or
synthetic object. Network errors and changed identity fail closed. The probe
does not write structured `history_v2` rows, delete objects, grant permissions,
change retention or enable PP collection. Offline tests cover a wrong UID,
bucket, origin prefix, duplicate/ambiguous upload, corrupted readback,
unexpected public access and deadline rejection. A second live Auth identity
would be needed to prove the wrong-UID denial through the actual Storage API;
the generated SQL fixture proves that denial only in its local approximation.

## Execution sequence

1. Provision the dedicated Auth user through the separately reviewed operator
   command. Compare its returned UID, email, role and app metadata to the
   intended binding without disclosing credentials.
2. Recheck project identity, private bucket, zero existing `storage.objects`
   policies, operation helper and intended Auth user. Render the apply and
   rollback SQL into fresh `0600` files with `python -m
   deploy.preprod.bind_market_raw_policy` using exact reviewed arguments.
3. Review both generated hashes and SQL. Apply only the reviewed policy via
   the connected Supabase migration route. Verify exactly two policy entries.
4. Run one reviewed bounded live probe with the dedicated bearer and
   publishable project key. Record the object key, byte hash, attempts and
   denial outcome. A failure stays STOP and invokes the reviewed policy-only
   rollback if the applied policy is unsafe.

No step above has been executed against live Supabase by this checkpoint.
Archive readback alone does not authorize local raw retirement. Final
verification, protected references and reader drainage remain required.

## Offline evidence

Seven focused Python tests passed. A disposable local PostgreSQL 17.12
container with no network, 512 MiB memory and a 64 MiB temporary data volume
applied the generated fixture, exercised its denial SQL, and completed
policy-only rollback. Final fixture state: **zero policies and two original
objects**, proving rollback did not delete objects in this scope. The fixture
approximates Storage RLS and does not prove Supabase's actual HTTP operation
mapping or privileged mutation controls.
