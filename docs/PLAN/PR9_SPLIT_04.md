# PR9 split 4/4: Release controls CI and historical execution evidence

This is a review slice, not another roadmap. `INTELLIGENCE_REBUILD_PLAN.md` remains authoritative.

Frozen original source: `0204901ae856810fcff06c3a1181f59884261fbf`. Original branch/PR #9 and unrelated local edits are preserved. Base: `codex/pr9-archive-history`.

Existing CI/CD/release-candidate workflows and controls, maintenance/legacy verification helpers, deployment regressions, historical evidence, reconciliation, master roadmap and handoff. Production cutover, 5 GiB capacity, scalable authorization and retirement enablement remain open.

Local macOS generated/offline backend suite: **442 tests, PASS, 22 platform skips**. Applicable deployment controls: **123 tests, PASS, 3 platform skips**. These results do not prove Linux-only cases or production capacity. The intermediate CI runs unit/control suites plus each available applicable root suite; split 4 restores the complete existing fail-closed CI pipeline, including its mandatory exact post-retirement history execution check.

A/B production activation, local retirement, storage-limit changes and paid AI are not authorized by merging this PR. The 5 GiB slot target and 24 GiB aggregate proposal remain unqualified. Historical evidence retains its original commit bindings and does not certify this new split commit. Exact split CI and review are still required.
