# Tradebot CI controls

See [environment and release operation](ENVIRONMENTS.md) and the authoritative
[roadmap](../../docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md).

`python-tests.yml` preserves legacy SQLite regressions and runs isolated
PostgreSQL migrations, schema-drift checks, application/lifecycle tests and the
actual runtime container on Linux. Separate jobs cover release/deployment
controls, syntax/workflow validation and dependency advisories.
`PR readiness` fails when any required job fails, is skipped or is incomplete.
No live cloud credentials are supplied to PR tests. Workflow actions are pinned.
The reviewed Node 24 action pins are `checkout` v5.1.0, `setup-python`
v6.3.0, `setup-go` v6.5.0 and `upload-artifact` v6.0.0. The minimum runner
version for these actions is 2.327.1; the current private PP runner was
2.338.2 at the November 18 check. Hosted jobs use the explicit
`ubuntu-24.04` image while GitHub migrates `ubuntu-latest` to Ubuntu 26.04.
See the official [checkout release](https://github.com/actions/checkout/releases/tag/v5.1.0),
[setup-python release](https://github.com/actions/setup-python/releases/tag/v6.3.0),
[setup-go release](https://github.com/actions/setup-go/releases/tag/v6.5.0),
[upload-artifact release](https://github.com/actions/upload-artifact/releases/tag/v6.0.0),
and [runner-image notice](https://github.com/actions/runner-images/issues/14748).
The `test_workflow_runtime_pins.py` gate detects an old action runtime or
floating hosted image in a later workflow edit. These pins do not authorize
deployment or change the PP database.
The release source-package carrier uses scratch and runs no application code.
The PostgreSQL integration job separately builds and exercises the runnable
application image; those two artifacts serve different purposes.
This configuration is independent of the closed SQLite A/B implementation PRs.

Branch-protection enforcement is still separate from reporting checks. Require
`PR readiness` on main/preprod once the checks are registered and qualified;
production environment approval is already configured, and does not substitute
for branch protection. No main protection policy was silently modified here.
