# PR9 split 2/4: Default-off collector dashboard and prediction integration

This is a review slice, not another roadmap. `INTELLIGENCE_REBUILD_PLAN.md` remains authoritative.

Frozen original source: `0204901ae856810fcff06c3a1181f59884261fbf`. Original branch/PR #9 and unrelated local edits are preserved. Base: `codex/pr9-storage-foundation`.

Default-off actual API/collector/ensemble/lifecycle routing, active-generation dashboard status, scheduling/health/feature changes, application adapter, selected recovery/bootstrap, and shared cloud adapter primitives. Explicit archive-history HTTP retrieval is introduced by the next PR.

Local macOS generated/offline backend suite: **418 tests, PASS, 20 platform skips**. Applicable deployment controls: **41 tests, PASS, 1 platform skips**. These results do not prove Linux-only cases or production capacity. The intermediate CI runs unit/control suites plus each available applicable root suite; split 4 restores the complete existing fail-closed CI pipeline, including its mandatory exact post-retirement history execution check.

A/B production activation, local retirement, storage-limit changes and paid AI are not authorized by merging this PR. The 5 GiB slot target and 24 GiB aggregate proposal remain unqualified. Historical evidence retains its original commit bindings and does not certify this new split commit. Exact split CI and review are still required.
