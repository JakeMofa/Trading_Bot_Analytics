# Environment CI and CD

This implements the user's four environment entry points. The master roadmap
in docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md remains authoritative.

| Actions name | File | Scope |
|---|---|---|
| CI Prod/Main | .github/workflows/ci-prod.yml | Qualify current main SHA after shared exact push CI |
| CD Prod/Main | .github/workflows/cd-prod.yml | Manual main-only promotion, matching PP acceptance, production approval |
| CI Preprod | .github/workflows/ci-pp.yml | Qualify trusted main/preprod/codex source after shared exact push CI |
| CD Preprod | .github/workflows/cd-pp.yml | Manual deployment to isolated PP with independent credentials |

## Reuse checks, preserve release compatibility

python-tests.yml remains the canonical full test/quality/security/application/
database/control workflow, with its filename and name unchanged. It also covers
the preprod branch if/when created. The two environment CI workflows consume its
successful exact push result; they do not repeat the full suites or call a VM.
An older passing run cannot override a newer failed or running exact-source run.

The environment CI workflows use workflow_run, so automatic follow-up registration
requires the files on the default branch. A manual dispatch also requires a full
SHA matching the dispatched branch HEAD. No branch was merged by this work.
PR checks remain in the existing shared workflow. Environment CI is a source
qualification status, not deployed/runtime/migration acceptance.

release-candidate.yml remains separate, manual-only and unchanged. Tags and
candidate prereleases do not trigger a production deployment.

## Separate environments

GitHub environments preprod and production are configured independently.
Preprod allows main, preprod and codex/*; production allows main and requires
the repository owner's approval. Self-review is allowed for this single-operator
project; this is a manual approval, not independent peer review. Branch protection
on main remains a separate pending configuration, not implied by environments.

No environment deployment secrets have been installed. Required names:
PP_DEPLOY_KEY / PP_DEPLOY_KNOWN_HOSTS for PP, and
PROD_DEPLOY_KEY / PROD_DEPLOY_KNOWN_HOSTS for production. There is no fallback to
the existing human SSH key or repository-wide legacy production credentials.
Do not reuse production database/cloud credentials in PP.

## Deployment protocol and current HOLD

Both targets in .github/deploy/targets.json deliberately have
runtime_qualified=false, with empty controller/qualification hashes.
The current state fails before bundle creation, environment-secret jobs or SSH.
A provisioned VM is not a qualified application runtime. Do not flip these fields
to make a workflow green. Enablement requires a separately tested and reviewed
runtime/controller, its exact hash and qualification commit, dedicated restricted
deployment identities, pinned host keys and approved runner access.

The prepared transport sends a tracked-source-only git archive to the dedicated
forced-command account, with protocol:

    deploy-v1 ENVIRONMENT INSTANCE SOURCE_SHA ARCHIVE_SHA256 CONTROLLER_SHA256

The installed controller must independently verify its own hash, VM identity,
archive digest/path safety, release scope, configuration and schema compatibility;
own its transaction/restart/smoke/recovery deadlines; and emit only bounded JSON.
That controller is NOT supplied or installed by these workflow entry points.
Its setup and qualification are the next deployment prerequisite.

The client requires strict host verification, one SSH attempt, a 600-second
controller/SSH deadline and bounded output. Failure/timeout terminates and reaps
the owned SSH process, with a seven-second cleanup allowance. No automatic retry
occurs. Terminating SSH alone is not proof of remote recovery; the controller's
independent bounded recovery must be qualified before enabling it. Jobs have a
15-minute limit. Existing legacy maintenance/check budgets are unchanged.

Controller acceptance must bind exact source/artifact/environment/instance and
pass API, SSE, schema, migration, data-correctness, collector ownership, disabled
flags, recovery, freshness and market-identity checks. Paid AI and retention must
stay OFF on this route.
PP additionally must have no real market collector and no production data mount.
Remote fields outside the allowed report schema are discarded.

## PP before production

Production requires a successful CD Preprod run from this repository and the
exact SHA, with one non-expired preprod-acceptance-SHA artifact. The bounded ZIP
must contain only deployment.json. Its instance, source, archive digest, target
policy digest, run/attempt, ten acceptance checks and safe flags must match.
The report must be timezone-aware and no more than 24 hours old. Changed target
policy or code requires new PP acceptance; successful source CI alone is insufficient.

The production job repeats these checks after approval, before SSH. It regenerates
the tracked-source archive and requires the same digest qualified in PP; differing
bytes cannot be promoted. No arbitrary operator-supplied JSON authorizes production.

Legacy deploy-tradebot.yml retains its filename, verification phase and historical
control tests. Its display name is Legacy — Lightsail maintenance. The deploy and
maintenance paths now require the production environment preflight and cannot
bypass the main/PP-first policy. The new normal release entry is cd-prod.yml.
Legacy read-only verification remains separate and does not authorize deployment.
This changes the new source tree, not historical workflow revisions. Inventory
and retire/restrict any legacy repository deployment credentials before enabling
the new production controller; environment rules do not revoke old credentials.

## What is not complete

No workflow was dispatched to a VM. PP PostgreSQL/application setup, real controller
qualification, restricted deploy keys, pinned deployment host keys, runner access,
production migration, runtime acceptance and main branch protection remain open.
The current guards are expected to HOLD until those prerequisites are delivered.
Four prepared workflow definitions are not proof of working database deployment.
