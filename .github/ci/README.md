# Tradebot CI controls

See [environment and release operation](ENVIRONMENTS.md) and the authoritative
[roadmap](../../docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md).

`python-tests.yml` preserves legacy SQLite regressions and runs isolated
PostgreSQL migrations, schema-drift checks, application/lifecycle tests and the
actual runtime container on Linux. Separate jobs cover release/deployment
controls, syntax/workflow validation and dependency advisories.
`PR readiness` fails when any required job fails, is skipped or is incomplete.
No live cloud credentials are supplied to PR tests. Workflow actions are pinned.
The release source-package carrier uses scratch and runs no application code.
The PostgreSQL integration job separately builds and exercises the runnable
application image; those two artifacts serve different purposes.
This configuration is independent of the closed SQLite A/B implementation PRs.

Branch-protection enforcement is still separate from reporting checks. Require
`PR readiness` on main/preprod once the checks are registered and qualified;
production environment approval is already configured, and does not substitute
for branch protection. No main protection policy was silently modified here.
