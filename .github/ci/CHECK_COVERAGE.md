# Automated-check completeness review

Reviewed November 6, 2026. Workflow display names: **CI — Tradebot checks** and
**CD — Lightsail deployment**. Filenames remain `python-tests.yml` and
`deploy-tradebot.yml`; stable job/check names remain unchanged. `verify_ci.py`
and its regression explicitly query `/actions/workflows/python-tests.yml`.
A filename rename requires coordinated migration and tests of every reference,
not just a cosmetic UI edit.

Tests provide evidence within their stated scope; they cannot prove every bug
absent. Mocks/generated fixtures never count as production acceptance. See the
[database before/during/after matrix](DATABASE_COVERAGE.md) for detailed limits.

## Priority checklist

| Priority | Area | Status | Remaining action / boundary |
| --- | --- | --- | --- |
| 1 | Required PR readiness / merge enforcement | **Missing** | Aggregate readiness is implemented, but inspected main/deployment branches are unprotected and repository rulesets are empty. Require PRs and the stable `PR readiness` check only after final source and PR checks pass. Preserve reviewed emergency access; no protection change here. A workflow alone does not prevent merging. |
| 1 | SQLite supported schema/migration/bootstrap/restart/partial failure | **Implemented, finite offline scope** | Existing generated predecessor/recovery/exact-reference/decimal tests plus root/import/integrated workloads; actual production files and all historical schemas are not certified. |
| 1 | Isolated Postgres SQL/migration compatibility | **Implemented, finite offline scope** | Five required real SQL-engine tests on pinned bounded disposable Postgres; minimal Supabase roles/buckets fixture, not the hosted service stack or live drift validation. Ownership-verified cleanup is regression tested. |
| 1 | Protected history / archived application replay | **Dependent on application work** | Existing storage-owned tests exercise exact payloads, references, corruption, cancellation and privileged replay. Current 1fb579f Linux background-verification child failures block backend/root/import/integrated qualification. Do not bypass or relabel them; checkpoint4 remains separate. |
| 1 | Dependency audit | **Implemented** | pip-audit on actual requirements; crypto50 correction is applied by the application owner. Latest completed 1fb579f audit PASS; future source must be re-audited. Update automation is separate. |
| 1 | Secret scanning | **Implemented, limited** | Tracked-source key/AWS/GitHub signatures redact matches; GitHub reports secret scanning and push protection enabled. Arbitrary credentials, non-provider patterns, old history and all token validity are not proven clean by this CI gate. No local data or credentials collected. |
| 2 | Targeted security analysis | **Partially implemented / missing semantic security scan** | Ruff E9/F63/F7/F82, syntax and actionlint detect narrow errors, not security dataflow. No repository CodeQL workflow found; API inspection could not establish analysis state (404 plus missing scope hint). Evaluate a Python CodeQL baseline separately; no broad lint/type rollout here. |
| 1 | Manual production release protections | **Implemented guards; environment approval missing** | Manual-only production operations, approved release branch, exact push-SHA CI, private runner, reviewed evidence and non-cancelling concurrency exist. No workflow environment binding or configured GitHub environment was found. Separate reviewed environment/branch/reviewer setup would add independent approval; manual dispatch alone is not a second reviewer. |
| 1 | Sanitized artifacts and provenance | **Implemented** | Source/tested SHA distinction, exact export verification, bounded sanitized reports/counts/skips and aggregate evidence checks. Missing reports block readiness. Artifact availability/retention does not imply deployed or accepted state. |
| 1 | Deployment smoke / failure recovery | **Implemented legacy controls; production-only A/B gap** | Offline control tests cover smoke/rollback/restoration/reaping. Actual host smoke, A/B/core/retained-legacy identities, cross-file references, aggregate disk/RAM and whole-layout recovery remain separately reviewed production gates. No live probe or dispatch here. |
| 2 | Versioned candidate artifacts/tags/prereleases | **Implemented manual candidate scope** | See [release visibility](RELEASE_VISIBILITY.md). Manifest version authority, exact push CI, create-only mocked publication; no real version/tag/release created. Host version/outcome recording and immutable-release settings remain separate reviewed work. No automatic deployment trigger. |

## Dependabot evaluation — proposed, not enabled

[Version updates are available for all repositories](https://docs.github.com/en/code-security/concepts/supply-chain-security/dependabot-version-updates).
This public repository has no `dependabot.yml`; inspected repository metadata
reports Dependabot security updates disabled. Recommendation for a later focused
change: weekly pip updates for `/backend` and GitHub Actions updates for `/`,
with a small open-PR limit (for example two per ecosystem), reviewed grouping and
no auto-merge. Configure on the intended default branch and review changelogs;
do not silently retarget this implementation branch or enable account settings.

It complements pip-audit by proposing maintenance, rather than replacing the
merge gate. Each update can invoke costly-in-time root/import/integrated suites;
a weekly cadence and bounded PR count reduce review/CI noise. No paid package,
new runtime dependency or update-bot rollout is included in this PR.

## CodeQL evaluation — eligible, permission/setup validation deferred

[Code scanning is available for public repositories](https://docs.github.com/en/code-security/concepts/code-scanning/code-scanning).
The configured identity has repository admin permission, but the analysis API
returned no analysis and a scope hint; this does not establish that all required
API/upload permissions are present or that scanning is disabled. No credentials
were refreshed. Public eligibility does not require purchasing a private-repo
Code Security license.

A later scoped proposal should evaluate Python with GitHub's standard/default
security query suite first, inspect extraction coverage and triage existing
alerts before selecting any required check. Avoid extended/noisy suites and
multiple overlapping scanners initially. GitHub recommends starting with
[default setup](https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/configure-code-scanning/configure-code-scanning),
which needs admin/owner authority; an advanced workflow would require carefully
scoped `security-events: write` for result uploads and read permissions appropriate
to checkout/actions, with fork-PR behavior checked before making it required.
Do not give the general test workflow write privileges just to add scanning.

CodeQL adds analysis time and alert-review work. GitHub states that
[standard hosted runners for public repositories are free](https://docs.github.com/en/billing/concepts/product-billing/github-actions);
larger runners are billed and artifact/cache storage has separate allowances.
No larger runner, paid feature, security setting or scanning workflow is enabled
here. Reassess eligibility and billing if repository visibility changes.

## Official release/merge guidance

[Branch protection](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
supports required checks; unique stable job names prevent ambiguous requirements.
[Environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)
can restrict deployment branches and require reviewers; required reviewers are
available for public repositories on Free/Pro/Team. Configure actual reviewers,
self-review policy and secret placement in a separate reviewed scope. Do not
claim those protections from an unbound workflow or an empty environment list.

This change adds no jobs, triggers, paid calls or security-setting mutations.
Existing application failures stay failed. No unchanged run is manually retried;
a push of the changed tracked workflow names follows the existing CI triggers.
