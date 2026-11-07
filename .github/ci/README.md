# PR quality and release CI

`python-tests.yml` remains the qualifying release workflow. Push CI runs on
`main` and `codex/**`; PR CI runs for every base branch; merge groups are also
validated. Push and PR jobs intentionally both run: deploy/lightsail/verify_ci.py
requires an exact **push** commit on `codex/lightsail-deployment`, and PR tests
exercise the synthetic merge commit. A passing PR merge run cannot replace it.
`CI_SOURCE_SHA` identifies the PR head; `GITHUB_SHA` identifies tested bytes.

Stable check names:

- `test`: backend regressions, exact exports, generated legacy-schema imports,
  bootstrap/restart/partial-failure/recovery, root descriptor/cutover proofs and
  joint HTTP/SSE handoff. Existing resource and latency limits remain unchanged.
- `integrated-qualification`: original bounded fresh-B ApplicationStore workload.
- `Application dashboard API and SSE contracts`: existing application tests,
  partitioned out of backend discovery so they run once.
- `Deployment and maintenance controls`: existing offline deployment tests.
- `Source and workflow quality`: tracked Python/shell syntax, credential
  signatures, Ruff E9/F63/F7/F82 only, actionlint, evidence failure regressions.
- `Dependency audit`: pip-audit against the runtime requirements and resolved
  transitive dependencies. Vulnerabilities or audit service failure block CI.
- `PR readiness`: aggregate required jobs and reports, SHA bindings and counts.

No broad style cleanup or type coverage is claimed. There is no established
repository-wide type-check configuration; only targeted static errors are gated.
Credential scanning covers private-key headers and AWS/GitHub token signatures;
it does not prove absence of arbitrary credentials. Only tracked files are read,
matching values are redacted, and local environment/data files are not collected.
Test evidence contains counts/skips and elapsed time, never test payloads or
credentials. Existing sanitized workload artifacts retain measured latency and
resource figures. Missing required reports block readiness. Tests skipped for
privileges are reported, and the existing privileged qualification remains
required; a skip is not presented as executed coverage.

All automated tests use generated/offline inputs. Production acceptance, cloud
operations and full-scale capacity are NOT PERFORMED. Existing generated workloads
retain their own byte/RAM/time limits; no larger performance dispatch is added.
Production stays manual-only in deploy-tradebot.yml, with its existing exact-push
lookup, rollback requirements, branch guards and non-cancelling concurrency.
The test workflow has read-only repository permissions and no production secrets.
Its concurrency group is separate from production and separates push/PR events.

## Enforcement checkpoint (November 6, 2026)

Read-only GitHub inspection found no repository rulesets and no protection on
`main` or `codex/lightsail-deployment`. Configured identity has admin permission.
`branch-protection.json` is a proposed REST protection body for **those two
branches only**, after `PR readiness` exists and passes on exact-source CI.
It requires PRs, an up-to-date branch and the GitHub Actions readiness check;
admin emergency access is preserved. Re-read live protection before applying;
merge with any newly added restrictions rather than replacing them. Application
of this file is NOT performed by any workflow. A workflow alone prevents no merge.

Current blockers identified before this change:

1. Exact push 439c93b / run 42320474396 failed the joint fresh-B/A/B/A HTTP/SSE
   handoff (`active_buffer` generation lookup); PR run 42320479783 passed.
   The storage worker owns the application/test fix. No unchanged retry requested.
2. Local pip-audit reported PYSEC-2026-3552, PYSEC-2026-3553,
   PYSEC-2026-3554 and GHSA-537c-gmf6-5ccf against cryptography 46.0.7.
   Storage/application owner must review a compatible requirements update and
   rerun application/authentication regressions. No advisory exemptions added.

Until required checks pass, branch protection remains **NOT ENABLED**.
The master roadmap and handoff remain owned by the active planning/storage chat;
copy this checkpoint there with final commit/run links. This worker owns only
CI workflow/configuration/scripts/tests and leaves production operators untouched.
