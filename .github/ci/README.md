# Tradebot CI controls

See [environment and release operation](ENVIRONMENTS.md) and the authoritative
[roadmap](../../docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md).

`python-tests.yml` preserves application/SQLite regressions and adds exact-source
release/deployment regressions, syntax/workflow checks and a dependency audit.
`PR readiness` fails when any required job fails, is skipped or is incomplete.
No live cloud credentials are supplied to PR tests. Workflow actions are pinned.
The source-package Docker fixture uses scratch and runs no application code.
This configuration is independent of the closed SQLite A/B implementation PRs.

Branch-protection enforcement is still separate from reporting checks. Require
`PR readiness` on main/preprod once the checks are registered and qualified;
production environment approval is already configured, and does not substitute
for branch protection. No main protection policy was silently modified here.
