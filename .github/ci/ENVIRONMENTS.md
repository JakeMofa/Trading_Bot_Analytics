# Environment pipelines and retained versions

This guide implements the authoritative [master roadmap](../../docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md).
It does not create a second roadmap or certify a database migration.

| Workflow | Purpose | When it runs |
| --- | --- | --- |
| `python-tests.yml` — CI — Tradebot checks | Existing application/SQLite regressions, release/transport controls, workflow syntax, dependency audit, fail-closed PR readiness | PR, merge queue, push main/preprod/codex branches |
| `ci-pp.yml` — CI Preprod | Reuse latest exact push CI for permitted PP source | Successful shared push CI; manual |
| `ci-prod.yml` — CI Prod/Main | Reuse exact main push CI | Successful shared main push CI; manual |
| `cd-pp.yml` — CD Preprod | Deploy published candidate to tradebot-preprod-01 after host qualification | Explicit dispatch from main |
| `cd-prod.yml` — CD Prod/Main | Promote exact main candidate with successful matching PP acceptance and owner approval | Explicit dispatch from main |
| `release-candidate.yml` — Release — publish version and package | Explicit candidate tag, source package, checksum, attestation and GitHub prerelease | Explicit dispatch from main |

## What merging PR #14 does

It registers these definitions on the default branch, making manual workflows
visible in Actions. It imports no A/B code and triggers no deployment or
publication. CI runs on main and follows with environment CI summaries.
The permanent preprod branch starts from an older main; sync these definitions
into it through a reviewed main → preprod PR before relying on its push checks.
Main's existing application differs from production's deployed d56b4a7. Do not
ship the old main app merely because this configuration merged.

Source and test dependencies are independent of the superseded A/B stack.
The only baseline dependency change is cryptography 46.0.7 → 50.0.0, removing
the known audit blocker; the existing signing/collector regressions qualify it.
CI preserves real backend tests, but does not pretend to test undeveloped
PostgreSQL migrations or live Supabase policies. Add isolated generated
migration/compatibility/recovery tests with each PostgreSQL schema PR.

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
2. Publish that preprod candidate, dispatch CD Preprod from main with its
   source_branch/version/SHA. PP uses isolated generated/replayed DB data, no
   production mount, extra live collector, retention or paid AI.
3. Review preprod → main. A merge/squash creates a new source SHA: publish and
   test **that main SHA in PP** before production. Similar trees do not replace
   exact-source evidence.
4. Dispatch CD Prod/Main from main with that published main version/SHA and
   successful PP CD run ID. PP evidence must match source/archive/policy/version/
   registry digest, current attempt, all ten acceptance checks and age ≤24h.
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
Both profiles currently say `runtime_qualified=false`; CD stops before bundle
creation, SSH or service changes. Do not flip that flag as a workaround.
A hostname/public IP alone does not establish a deployment connection.

Qualify the PostgreSQL app, local schema/migration checks and restricted
host-side controller on PP; then install its dedicated forced-command key,
verified SSH host pin and approved private runner. At the November 12 read-only
GitHub inventory, no runner was registered and both environments had zero
secrets. Required bindings:

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
