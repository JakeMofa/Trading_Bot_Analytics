# Environment pipelines and retained versions

This guide implements the authoritative [master roadmap](../../docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md).
It does not create a second roadmap or certify a database migration.

| Workflow | Purpose | When it runs |
| --- | --- | --- |
| `python-tests.yml` — CI — Tradebot checks | Application/legacy SQLite compatibility, isolated PostgreSQL migrations/application/lifecycle and runtime image, release controls, dependency audit and PR readiness | PR, merge queue, push main/preprod/codex branches |
| `ci-pp.yml` — CI Preprod | Reuse latest exact push CI for permitted PP source | Successful shared push CI; manual |
| `ci-prod.yml` — CI Prod/Main | Reuse exact main push CI | Successful shared main push CI; manual |
| `cd-pp.yml` — CD Preprod | Deploy published candidate to tradebot-preprod-01 after host qualification | Explicit dispatch from main, or exact preprod controls for a preprod source only |
| `cd-prod.yml` — CD Prod/Main | Promote exact main candidate with successful matching PP acceptance and owner approval | Explicit dispatch from main |
| `release-candidate.yml` — Release — publish version and package | Explicit candidate tag, source package, checksum, attestation and GitHub prerelease | Explicit dispatch from main |

## What merging PR #14 does

It registers these definitions on the default branch, making manual workflows
visible in Actions. It imports no A/B code and triggers no deployment or
publication. CI runs on main and follows with environment CI summaries.
PR #15 aligned the reviewed workflow definitions from main into the permanent
preprod branch. Application changes still reach preprod through reviewed PRs;
merging them does not automatically deploy either environment.
Main's existing application differs from production's deployed d56b4a7. Do not
ship the old main app merely because this configuration merged.

Source and test dependencies are independent of the superseded A/B stack.
The only baseline dependency change is cryptography 46.0.7 → 50.0.0, removing
the known audit blocker; the existing signing/collector regressions qualify it.
CI retains SQLite regressions for the legacy code still present. The required
`PostgreSQL PP foundation` job now runs the pinned database image on Linux,
checks environment/column/ownership contracts, restricted authenticated roles,
exact generated values, full durability and container-recreation persistence.
An injected unexpected column must fail verification. Failure or a skipped job
fails `PR readiness`; this feeds the existing exact-commit CI Preprod / CI
Prod/Main qualification. No separate database service is contacted in production.

The additional `PostgreSQL migrations and application lifecycle` job starts an
isolated PostgreSQL 17 container and runs empty/repeat/upgrade, immutable
migration checksum, schema/constraint/index/privilege drift, exact-value,
application and partition-retirement/history tests. Any skipped database case
fails this qualification. It builds the runnable app image and exercises actual
API/SSE endpoints with generated data; the source-bundle registry carrier remains
a different artifact. The job owns only disposable CI data and cannot run on the
marked PP host. Sanitized evidence is retained as `postgres-integration-<SHA>`.

Generated proof does not establish live collection, representative capacity or
Supabase permissions. `history_v2` remains an unapplied CP6 contract. CD must bind
the inspected host schema and migration evidence to the exact artifact and
reject unreviewed drift. Application startup validates; only the explicit
migration command applies reviewed SQL. Production controls remain disabled.

## Publication and visible rollback inventory

After source push CI succeeds, dispatch **Release — publish version and package**
from **main**, choosing source_branch (preprod or main), full source SHA, and an
explicit unused `vX.Y.Z` or prerelease version, for example `v0.1.0-rc.1`.
No version is chosen or published by the configuration PR. Branch HEAD and
latest push CI must still match; failed/cancelled/newer CI cannot reuse an old
success. Source code is archived as data and never executed by the publisher.

Publication produces:

- [Releases](https://github.com/JakeMofa/Trading_Bot_Analytics/releases): candidate notes, exact source SHA/CI link, `source.tar.gz`, `release-manifest.json`, `SHA256SUMS`.
- [Packages](https://github.com/JakeMofa/Trading_Bot_Analytics/packages): linked GHCR package `ghcr.io/jakemofa/trading_bot_analytics/releases`, with explicit version tag and content digest. Every prior published version stays unless an operator explicitly removes it.
- Provenance attestation for the registry digest; no mutable `latest` tag.
- Actions summaries and evidence artifacts retained for 90 days, subject to repository retention policy. These artifacts are not the long-term rollback registry.

The scratch image is a source-bundle carrier containing the archive and its
manifest. It is **not a runtime image**, includes no database or credentials,
and does not require Docker on a VM. CI uses Docker only to package and inspect
that carrier. The package label associates it with this repository. First
publication is private by GitHub default; manage visibility separately if
public anonymous pulls are desired. Repository workflow access must be retained.

Tags, Releases and packages are create-only in this workflow. A partial failure
may leave a package or draft; it never automatically retries, deletes or
clobbers it. Reconcile the exact version/digest before another attempt. GitHub
administrators can still mutate/delete packages; these controls do not assert
registry-wide immutability. There is no scheduled pruning in this PR.

## PP, then production

1. Feature PR → preprod; exact push CI and review.
2. Publish that preprod candidate, dispatch CD Preprod from main or the exact reviewed preprod HEAD with its
   source_branch/version/SHA. PP uses isolated generated/replayed DB data, no
   production mount, extra live collector, retention or paid AI.
3. Review preprod → main. A merge/squash creates a new source SHA: publish and
   test **that main SHA in PP** before production. Similar trees do not replace
   exact-source evidence.
4. Dispatch CD Prod/Main from main with that published main version/SHA and
   successful PP CD run ID. PP evidence must match source/archive/policy/version/
   registry digest, current attempt, all ten acceptance checks and age ≤24h.
   Evidence must explicitly have production-candidate scope; generated-only PP
   acceptance is rejected even when every smoke check passes.
   Production environment requires the owner's approval; no automatic deploy
   follows a merge, tag, Release or package publication.

GitHub environment deployment history records attempts/results. Candidate
Release notes deliberately remain CANDIDATE, not a claim of production status;
follow the environment's successful deployment and acceptance evidence for
actual state. A bounded smoke does not close I7 or the sustained-operation gate.
The VM and database are never moved from PP to production.

## Host activation is a separate runtime milestone

Targets are bound by instance name, Region, host, dedicated user, qualified
controller digest and qualification commit in `.github/deploy/targets.json`.
The PP profile is qualified using actual controller/SSH/role evidence and has
completed generated deployment v0.2.0-pp.2 in run 43356521535. Production remains
`runtime_qualified=false`. The flag cannot substitute for runtime qualification.
A hostname/public IP alone does not establish a deployment connection.

Qualify the PostgreSQL app, local schema/migration checks and restricted
host-side controller on PP; then install its dedicated forced-command key,
verified SSH host pin and approved private runner. PP environment secrets are configured. An ephemeral operator Mac runner takes
one manual job, then unregisters; none remains after the successful pp.2 attempt.
The deployment job validates existing Python 3.12 instead of installing a hosted
runner toolcache. The earlier pp.1 setup failure and revoked authority remain
recorded. Required bindings:

| Environment | Secrets | Target |
| --- | --- | --- |
| preprod | PP_DEPLOY_KEY, PP_DEPLOY_KNOWN_HOSTS | tradebot-preprod-deploy@18.119.253.233 |
| production | PROD_DEPLOY_KEY, PROD_DEPLOY_KNOWN_HOSTS | tradebot-production-deploy@3.13.133.25 |

PP's address is not static: reverify instance identity and host key when it
changes. Never copy the production operator key into PP secrets or disable SSH
verification. Do not expose public API/Postgres ports or widen firewall rules
for hosted runners. Only manually dispatched CD may use `tradebot-private`;
PR code runs on disposable hosted runners, never the private VM runner.

The controller protocol is documented by environment_pipeline.py and must
report matching source/archive/instance plus api/sse/schema/migration/
data_correctness/collector_ownership/disabled_flags/recovery/freshness/
market_identity PASS. Host-side deadlines, pre-change checks, bounded code-only
recovery and post-acknowledgement forward recovery require real qualification;
terminating an SSH client is not proof of remote recovery. No controller is
installed by this configuration PR. Each later engine/schema change needs
isolated fixtures; production DB checks are bounded approved runtime checks.

## Rollback

Retained source releases and registry digests provide version selection and
recovery evidence; they are not database backups. Select an old version and
review its manifest plus current database compatibility first. Current CD
accepts branch HEAD with current exact CI and PP evidence, so it intentionally
rejects blind deployment of an old SHA. Restore reviewed old code through a
revert PR, test the resulting main commit in PP, and publish a new candidate;
or separately qualify a dedicated old-version controller route before adding
one. No one-click database rollback, snapshots or automatic data restoration is
implemented. Dependency/runtime availability also needs host qualification;
a retained source bundle alone is not a self-contained runtime image.

## Sources

[GitHub Container registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry),
[GitHub Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases),
[workflow artifact retention](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/remove-workflow-artifacts),
[artifact provenance](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations).

## Generated PP controller implementation

The controller source in `deploy/preprod/controller.py` implements a bounded
one-use authorization, exact source/archive/controller binding, safe extraction,
explicit migration stage and forward-preserving recovery. Its tests inject
wrong bindings, unsafe archives, stage failures, timeouts and recovery failure.
The Linux adapter, installed identity/pin, runtime preparation and actual manual
workflow need separate qualification. Neither creating a controller file nor
setting a target flag establishes that evidence.

The prepared PP route reserves 600 seconds of work, 180 seconds of recovery and
30 seconds for transport. Production's existing controls are unchanged.
Recovery preserves PostgreSQL and new acknowledgements; code rollback never
restores database contents. The current runtime cannot enable a live collector,
cloud writes or retirement. Normal runtime container caps total 1 GiB: PostgreSQL
512 MiB, API 192 MiB, calculations 192 MiB and lifecycle 128 MiB. The migration
container has a separate 192 MiB cap and runs before the application starts.
These caps are prepared limits, not a production capacity qualification.

## Verified PP operator route

The generated API/dashboard/SSE passed through pinned operator SSH to its
dynamically resolved internal container IP. Docker did not publish the configured
host localhost:8000 mapping. Container-local CI/controller checks do not prove
that mapping, so use the [verified README procedure](../../README.md) and retain
the deployment key's no-forwarding restriction. Production-preview networking
is a separate gate. Do not add public exposure or loosen the internal database
network to make a dashboard link work.
