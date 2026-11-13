# Generated PostgreSQL PP release procedure

This document implements CP5 of the authoritative
[master roadmap](../../docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md). It is a procedure
and evidence record, not another roadmap. The production target remains disabled.

## Current qualification boundary

The schema, application and lifecycle passed combined generated PostgreSQL 17 and
actual container/API/SSE tests at `751f1f8`, CI 43346308984. The final deployment controller/adapter, including descendant cleanup, passed
exact Linux CI 43351324325 at `deb8f0d`. Combined source `687861e` also passed
exact CI 43351856515. That exact helper source is installed and its actual PP
host/SSH/role preflight is qualified; the first manual application deployment
remains unperformed. Its CI uses real Docker,
PostgreSQL, roles, migrations, API restart, persisted acknowledgements and recovery;
only the PP hostname binding is substituted on the disposable GitHub host.
Actual PP prerequisite bindings are recorded in
[the sanitized report](../../docs/PLAN/evidence/pp-runtime-binding-2026-11-13.json).
This does not certify a deployment or production acceptance.

The runtime permits generated/replay data only and has no real collector, cloud
transport or retirement activation route. A passing generated smoke cannot
satisfy production-candidate acceptance. No production database is mounted.

## Checkpoint A — exact source and controller qualification

1. Require latest exact push CI, all required jobs, no skipped PostgreSQL cases.
   The integration branch contains reviewed schema/app/lifecycle component PRs;
   CP5 includes their tested dependencies rather than reopening superseded SQLite
   work. Review the full diff and the recorded security/recovery findings.
2. Build the deterministic controller zipapp from that clean exact commit using
   `python3 deploy/preprod/controller_bundle.py /absolute/new/controller.pyz`.
   Record its SHA-256 and byte count. The package contains only the fixed root
   entrypoint, controller and Linux adapter; its hash binds all executed code.
3. Merge reviewed source through integration PR #17 to preprod. Require the new
   exact preprod commit's CI. Do not infer a merge commit's qualification from
   its parents. No production merge or dispatch follows automatically.

## Checkpoint B — PP preparation and restricted identity

Use only the existing independently pinned operator route to
`tradebot-preprod-01`. Recheck hostname/root marker, Ubuntu 24.04, at least 10 GiB
free disk and 1 GiB available RAM. The November 12/13 read found 57,428,275,200 free
bytes and 1,453,223,936 available memory bytes; those are dated measurements.

Export the approved source as code to a root-owned stable directory. Preserve
existing PP volume, foundation credentials and 32 generated foundation rows.
The explicit `provision_runtime.py prepare` creates restricted runtime DSN files;
it never logs values or loads production/Supabase credentials. Add the lifecycle
secret mount through the reviewed Compose overlay, recreating only PP PostgreSQL
against the same named volume. Run `provision_runtime.py activate` to create or
verify the separate NOINHERIT lifecycle role. These operations require the marked
PP host and cannot be run against production. Verify roles/volume/data continuity.

`install_controller.py install` installs the hash-verified package, fixed forced
SSH command, narrowly scoped sudo rule and dedicated `tradebot-preprod-deploy`
identity. Existing differing keys/rules require reconciliation; it does not
silently replace them. Only helper **code** is retained for restoration; no
database/configuration backup is made. The identity gets no Docker group or
interactive administrative route. Keep the private key outside Git/evidence.

Before enabling the target, prove through that dedicated key and strict host pin:

- `identity-v1 preprod tradebot-preprod-01 <controller-sha256>` returns the exact
  installed binding, with `runtime_qualified=false` and `database_changed=false`.
- Arbitrary commands and wrong hashes are rejected; no shell/PTY/forwarding.
- Existing foundation, restricted roles, secret ownership and resource limits
  match the candidate. No production service or firewall is touched.

Set the preprod GitHub environment's dedicated key and verified host pin through
secret input, never command-line values or evidence. Restore the approved private
runner mechanism. The recorded preparation configured both PP environment secrets and temporary
ephemeral runner 27. Recheck availability before dispatch; workflow definitions
alone do not establish those bindings.

Record actual binding evidence before committing a qualified preprod profile.
The source-reviewed target flag, controller hash and qualification commit must
match; the production profile remains disabled. This flag does not itself prove
an application deployment succeeded.

## Checkpoint C — one manual generated deployment

Publish a unique explicit prerelease/source package through the existing manual
release workflow, after exact preprod CI. Record its actual published archive
SHA-256; do not substitute a locally recompressed archive. Source packages and
runnable application images are distinct. This PP route builds from pinned source
and records the resulting runtime image ID; production exact-image promotion is
still CP8.

Prepare one root authorization binding source SHA, published artifact SHA-256,
installed controller SHA-256, PP identity, generated mode and disabled flags.
The permit expires after 30 minutes and is consumed once. Installation/authorization
and deployment share a host lock. Existing unused authority requires explicit
reconciliation. No automatic deployment retry is permitted.

Dispatch CD Preprod manually from reviewed preprod for that exact preprod source,
or from main for its permitted source. Preflight rechecks exact push CI, branch,
published version/artifact and qualified controller before using environment
secrets. Work is bounded to 600 seconds with 180 seconds recovery plus 30 seconds
transport inside the 15-minute deployment job.

The host controller verifies/extracts the bounded source, validates full Compose
configuration, builds the image, fences previous PP application writers, applies
explicit migrations and starts only API/calculation/lifecycle. PostgreSQL is not
restarted by application deployment. Smoke requires schema checks, exact generated
writes/conflict handling, API/dashboard/history, SSE reconnect, source freshness,
market identity, disabled flags and an API-only restart with persisted evidence.
An HTTP 200 alone cannot clear these checks.

## Failure and recovery

- Before migration, a failed build leaves the previous application running.
- After migration begins, stop/fence deployment-owned one-off containers and
  application workers before examining recovery evidence. A killed Docker CLI
  alone does not prove its container exited. Refuse foreign-attempt containers.
- Preserve the current PostgreSQL volume and newly acknowledged records. Stop
  safely or recover forward; do not restore a database or restart incompatible
  old code. Failed deployment stays failed after successful recovery.
- Unknown process/crash state requires inspection of the root-owned journal and
  exact container labels. The consumed authority cannot authorize another run.
- No retention, live collection, cloud writes, manual WAL/VACUUM or production
  action is included. Only disposable CI owns its generated-volume cleanup.

## Checkpoint D — report and developer documentation

Record the actual source/image/controller, CI/Actions run, process and schema
results, interruption, disabled flags, disk/WAL/memory and recovery evidence.
Update the master/README/handoff. Document host commands as working only after
execution. CP6 actual Supabase compatibility, CP7 live/capacity/legacy qualification
and CP8–10 production/retirement acceptance remain open. A healthy generated PP
application does not close I7 or Phase 1.75.
