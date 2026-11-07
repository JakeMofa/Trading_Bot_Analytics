# Tradebot CI and Lightsail CD

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

## Isolated follow-up checkpoint

CI changes after 1cc9e8d belong to `codex/ci-pr-quality-gates` in the separate
`Trading_bot_Analytics_CI` clone. Review follow-up changes against
`codex/phase1-75-retention-enable`, not main. The original checkout stays owned
by the storage worker; its existing CI milestone is not reset or reverted.

Exact source 1cc9e8d / push run 42323117551 passed backend, root/generated,
known-cardinality import, joint HTTP/SSE handoff, integrated fresh-B, application
contracts and source/workflow quality. Controls failed to import `websockets`:
the isolated job omitted runtime requirements that had been installed in the
previous combined job. Both CI-owned control-validation jobs now install the
existing pinned runtime requirements before tests. Production dispatch branch,
operations, exact-push lookup, concurrency and operator code remain unchanged.
The dependency audit remains FAIL; no vulnerable pin or advisory exemption was
changed. Enforcement is still pending, including new exact-source qualification.

Local isolated follow-up validation: 123 deployment-control tests PASS with three
platform skips; four CI-control regressions PASS; actionlint and targeted Ruff
PASS. Audit fix versions range from 48.0.1 to 50.0.0, so the storage owner should
review a compatible cryptography pin at least 50.0.0 and qualify dependency,
Ed25519 authentication/streaming and application regressions. This is a proposed
dependency remediation, not an applied or compatibility-qualified upgrade.

## Latest reviewed results and merge dependency

Source `7bee563aa05c09592f4758520bab83477470d1db`:
[exact push run 42323798491](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/42323798491)
and [PR run 42323822761](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/42323822761).
PR tested merge SHA: `e645e553abbaafd79089334019fcfe0a49fa2bed`, not the source SHA.
Downloaded category artifacts verified those bindings. In both runs: backend
367/14 skips PASS, root 76/0 PASS, application 67/0 PASS, controls 123/0 PASS,
CI-control tests 4/0 PASS; source/static/workflows and integrated qualification
PASS. Dependency audit FAIL; readiness BLOCKED solely by that security failure.
There is no current joint-application handoff failure on these tested SHAs.
The historical 439c93b failure remains recorded; later PASS does not identify its
cause or qualify future storage changes.

The control setup defect is fixed. Remaining security remediation belongs to the
storage owner. See [tested exact patch, primary advisory references, environment
scope and safe merge order](proposals/README.md). Neither application's requirements
file was changed by this worker. PR #10 intentionally depends on that base-branch
dependency correction and fresh exact-source/PR qualification before merge.

The final job summary now lists required job states, test counts/skips, source
and tested SHAs, blockers and the run/artifact evidence link. Security failures
are reported separately from SHA mismatches. Five local CI regressions pass,
including pending/in-progress required jobs blocking readiness. Replaying the new
validator against downloaded 7bee563 push artifacts reports only the genuine
security failure, with no spurious SHA mismatch. New source CI is still required.

## Database deployment coverage

See [before/during/after coverage matrix](DATABASE_COVERAGE.md). The required
`Isolated Postgres schema compatibility` job executes unchanged reviewed SQL on
a bounded disposable PostgreSQL engine, beyond existing mock-wire tests. It
does not install the Supabase service stack, use live secrets or certify deployed
drift/permissions. `PR readiness` now requires its evidence too. Existing VM
controllers remain legacy-path-only; production A/B/core/retained-legacy identity,
aggregate resource guards and recovery/retirement gates remain storage-owned.

Storage dependency correction 4c673bf and final source 0cef90a (including cc06c01) are now available;
refresh this isolated CI branch from that base. Older failed audit evidence remains
FAIL for its original source; new passing checks are required for the combined SHA.

Final storage freeze update: 00f390e supersedes the earlier 0cef90a packaging
checkpoint by joining generated HTTP handlers after cancellation. The earlier
three background-verification errors remain FAIL on their original source;
the hard single-thread guard and budgets are unchanged. This CI branch includes
that storage-owner correction; exact combined-source and PR evidence are required.

The Postgres fixture cleanup review found and corrected a name-collision hazard:
cleanup is now bound to a recorded container ID plus unique owner label, never a
name-only deletion. Five mock ownership regressions and all five actual isolated
SQL tests pass. Final local backend 374 tests PASS/22 platform skips on storage
freeze 00f390e; eleven CI-control tests PASS. Final exact Linux/PR qualification
remains required; production A/B operator and live Supabase scopes remain separate.

## Workflow naming and completeness review

GitHub displays **CI — Tradebot checks** (`python-tests.yml`) and
**CD — Lightsail deployment** (`deploy-tradebot.yml`). Existing job/check names,
triggers and release guards are unchanged. See [prioritized checklist and
security-tool evaluation](CHECK_COVERAGE.md). Actual filename renaming would
require a coordinated, tested migration of every API lookup, test and document
reference, notably `verify_ci.py` and `test_release_lookup.py`; it is not part of
this display-name change.

## Versioned candidate visibility

[Manual release-candidate workflow and usage](RELEASE_VISIBILITY.md) now implement
version-bound source artifacts and explicit create-only prerelease publication.
The release manifest is the version authority. No actual tag/version/publication
is selected here; deployment and acceptance states remain separate. The existing
operator bundle format is not replaced, and host version/outcome recording remains
an explicit controller dependency. Prior source9847353 push42335758651 and
PR42335763918 PASS are preserved for that SHA only; new source needs fresh CI.
