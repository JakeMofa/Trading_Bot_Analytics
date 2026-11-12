# Four environment workflows — November 11, 2026

Local implementation/control checkpoint: PASS. Exact successor Linux CI pending.
Runtime deployment/acceptance: NOT PERFORMED; both target profiles remain disabled.
The authoritative master roadmap governs Phase 1.75/I7 and production approval.

| Actions entry | Purpose |
|---|---|
| CI — Production | Current main source qualification using existing exact push CI |
| CD — Production | Manual main-only deployment after matching PP acceptance and owner approval |
| CI — Preprod | Source qualification for main/preprod/trusted codex branches |
| CD — Preprod | Manual isolated PP deployment using a separately qualified controller |

The existing python-tests.yml engine and release-candidate.yml filenames/names
remain unchanged. Environment CI consumes source CI rather than repeating the
expensive suites. Existing PR checks are preserved. Four new workflow files are
in the release-control review branch; automatic workflow_run registration requires
the definitions on the default branch. Nothing was merged or dispatched.

GitHub now has preprod and production environments. PP permits main, preprod and
codex/*; production permits main and requires repository-owner approval.
Self-review is allowed for the single operator. No deployment credentials were
added and main branch protection was not changed. Required keys/controllers,
host pins and runner access are not installed by this milestone.

Both runtime_qualified fields are false in .github/deploy/targets.json. Current
CD refuses before building source or contacting SSH. The generic client transport
is implemented, but the independently qualified forced-command runtime controllers
are still missing. Their instance/hash/archive/scope checks and bounded remote
recovery must be delivered before enablement. A successful source CI or provisioned
VM is not application/database acceptance.

Production requires the exact same source/archive digest, target-policy hash and
successful PP CD run/attempt, with a single bounded acceptance report no older
than 24 hours. Ten checks cover API/SSE, schema/migration/data correctness,
collector ownership, disabled flags, recovery, freshness and market identity.
PP also must have no real market collector or production data mount. Both routes
keep paid AI and retention OFF. The owned SSH child has a 600-second deadline,
bounded stdout/stderr and termination/reaping; no automatic retry is included.
Client termination is not evidence of remote recovery; controller proof is open.

Legacy deploy-tradebot.yml keeps its read-only verification budgets and tests;
its mutating paths now depend on the new production preflight. Historical
workflow revisions and old deployment credentials are not revoked by changing
source files; audit/retire or restrict those before production enablement.

Validation: 31 CI-control tests passed, including 15 new pipeline cases; 123
legacy deployment tests completed with all executed cases passing and three Mac
platform skips. actionlint 1.7.7, new Python/JSON parsing and whitespace passed.
Cases cover stale/moved/failed CI, forks, wrong role/source, PP artifact mismatch,
expiry, flags, controller failures/timeouts, bounded generated children/reaping,
secret separation, output sanitization and branch movement before transport.
No application/database code changed; full backend acceptance is left to exact
candidate Linux CI and the separate runtime milestone, not claimed from controls.

Next: qualify isolated PostgreSQL/application runtime and the two restricted
deployment controllers; install independent environment credentials/host pins;
qualify exact CI; review/merge/register workflows; apply tested main branch
protection. Then run approved PP CD, followed by separately approved production
promotion. No VM, database, retention, archive object or paid AI mutation occurred.

Details: [.github/ci/ENVIRONMENTS.md](../../.github/ci/ENVIRONMENTS.md).
Evidence: [sanitized local results](evidence/environment-pipeline-2026-11-11.json).
