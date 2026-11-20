# Exact second-trial cloud scope

Preparation only: these files do not apply cloud changes or activate a collector.
The user authorized deployment and the next live trial. The implementation scope
is read-only collection/analysis, synthetic qualification writes and additive
archive infrastructure for `pp-live-pp-trial-20261119-02`. Trading, paid AI calls,
retirement and deletion remain disabled. The retained `01` trial is evidence of
completed maintenance archival, not a successful original timed live trial.

## Fixed identity and preserved evidence

The new SQL principals are `tradebot_pp_trial_20261119_02_writer` and
`tradebot_pp_trial_20261119_02_reader`. The structured review SQL creates them
NOLOGIN, NOINHERIT, without administrative attributes or memberships, with a
connection limit of two each. The writer gets SELECT/INSERT on the same eleven
private history tables and UPDATE only on markets, current prices and generation
checkpoints. The reader gets SELECT only. Both have restrictive exact-origin
fences. No public grants, DELETE, TRUNCATE or future-table defaults are added.

Create two fresh Auth identities, one `pp_storage_archive`, the other
`pp_storage_history_reader`, with server-controlled `app_metadata.tradebot_origin`
equal to the exact `02` origin. Never reuse or change `01` identities. Storage
policies require these exact UIDs, the private `market-raw` bucket, exact SHA-256
origin prefix and authenticated object operations. Writer access is create plus
get; reader access is get only. Restrictive fences deny replacement, deletion,
listing, public/signed access and cross-origin access. The template refuses UIDs
already named in existing Storage policies.

The existing `01` and legacy roles, policies, Auth identities, credentials,
archives, receipts and local partitions remain intact. New host credentials use
`trial_20261119_02_*` paths; generic in-container targets retain their current
names. Existing `01` authority/proof files must not be overwritten.

## Finite operational procedure

1. Qualify the exact combined source SHA with CI and native tests. Keep collectors
   durably OFF and deployment gates unchanged during provisioning. Record source,
   image and controller hashes. The reviewed scratch operations in
   `/private/tmp/tradebot-pp23-trial-release` are separate from repository scripts;
   none run through this document.
2. Capture fresh catalog evidence: table/RLS definitions; exact history grants,
   role attributes and memberships; complete `storage.objects` policies and their
   template catalog hash; private bucket status; retained-origin row/object counts.
   Stop if these differ from the reviewed baseline. Keep secrets out of evidence.
3. Apply only `supabase/review/pp_trial_20261119_02_structured.sql`. It fails if
   either new role exists. Inspect an uncertain application before any retry;
   do not drop or recreate principals to make a retry pass.
4. Run the create-only Auth provisioner twice using a private admin-key file,
   `--origin pp-live-pp-trial-20261119-02`, and separate fresh private output
   directories for `--purpose archive` and `--purpose history-reader`.
   `deploy/preprod/provision_supabase_archive_identity.py` permits only legacy,
   `01` and `02` literals. It never runs inside deployed application containers.
   An ambiguous POST preserves its private stage and requires reconciliation.
5. Bind the fresh public UIDs/emails and fresh Storage catalog hash with
   `deploy/preprod/bind_second_trial_cloud_policy.py`, using a new output file.
   Review the rendered SQL before application. Apply that additive policy once;
   it checks private bucket/RLS, confirmed Auth identities, server metadata and
   the complete preceding policy hash inside the same transaction.
6. Enroll only the two new SQL roles for LOGIN with independently generated
   credentials staged privately before the ALTER ROLE operation. The scratch
   `enroll-trial-sql.py` uses SCRAM verifiers, preserves an attempted marker and
   verifies both TLS identities and empty new-origin visibility. It does not
   change old roles/passwords or grant memberships. Uncertain enrollment stops.
7. Run scratch synthetic qualification in order: `trial-storage-smoke.py`,
   `trial-sql-smoke.py`, then `trial-storage-fences.py`. Durable create-only
   intents precede writes; unknown outcomes stop without blind retry. Structured
   writer import is followed by independent reader exact projection/revision
   readback. Both new SQL roles must see no retained `01` receipts; an attempted
   valid-shaped `01` receipt write must fail and rolls back if unexpectedly
   accepted. Both new Storage identities must be denied actual authenticated
   GET of known legacy and retained `01` keys. Test listing/sign/public denial
   and reader creation denial. Preserve synthetic evidence; delete nothing.
8. Compare old catalog/grants/role/credential bindings and retained evidence to
   step 2. Only additive `02` objects and new-role LOGIN enrollment may differ.
   Stage fresh source-bound `02` writer/reader proofs under the exact host profile;
   never relabel `01` proof as `02`. Install only the qualified combined release,
   validate the exact two trial workers and independent reader scope, and then
   follow the separately authorized host live-trial activation procedure.

Do not store credentials, private stages or databases in Git. Print only sanitized
status, public source/hash/UID bindings and bounded proof results. No service-role
key, access token, password, DSN or HTTP error body belongs in logs.

## Evidence and limits

The new native PG17 test installs legacy, `01` and `02` policies together and
checks least privilege, role/membership isolation, unchanged earlier catalogs and
grants, exact-origin visibility, cross-prefix denials and create-only guards.
The provisioning regression checks exact `02`, rejects wildcard/`03` origins,
and rejects reuse of an already staged operation. This is an approximation of
Storage SQL authorization, not proof of hosted HTTP operation mapping. Actual
hosted positive/negative probes in step 7 are required before runtime proof.

Official references consulted: [Supabase Storage access control](https://supabase.com/docs/guides/storage/security/access-control),
[Postgres RLS guidance](https://supabase.com/docs/guides/database/postgres/row-level-security)
and the [changelog](https://supabase.com/changelog). The November CLI and scoped
branch-access changes do not change these additive SQL/Storage policy rules;
use discovered CLI syntax and no implicit project or hosted-target selection.

## Combined local candidate validation

The combined candidate passed 536 backend tests with 66 environment-dependent
skips, 256 host controls with six platform skips, and 56 CI controls. Separately,
owned native PostgreSQL tests passed the second-trial admission/retirement scope
(six tests), its restricted-role CI adapter (four tests, zero skips), dual-origin
cloud policies (four tests), and dashboard/query hydration (23 tests). Linux
exact-source CI must run the restricted-role adapter through the existing
`test_postgres*.py` phase, which rejects skipped tests. These are generated
results; deployment and actual live collection remain unperformed here.
