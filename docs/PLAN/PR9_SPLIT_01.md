# PR9 split 1/4: Storage protocol and recovery foundations

This is a review slice, not another roadmap. `INTELLIGENCE_REBUILD_PLAN.md` remains authoritative.

Frozen original source: `0204901ae856810fcff06c3a1181f59884261fbf`. Original branch/PR #9 and unrelated local edits are preserved. Base: `codex/lightsail-deployment`.

Raw generation protocol, acknowledged-write recovery, reader leases, exact timestamp/provenance protections, and the legacy retention/recovery helpers it imports. A pure shared price-query helper is added without activating feature version 2 or changing the existing price lookup. Receipt writers use explicit microseconds. No application A/B startup route is installed here.

Local macOS generated/offline backend suite: **277 tests, PASS, 9 platform skips**. Applicable deployment controls: **41 tests, PASS, 1 platform skips**. These results do not prove Linux-only cases or production capacity. The intermediate CI runs unit/control suites plus each available applicable root suite; split 4 restores the complete existing fail-closed CI pipeline, including its mandatory exact post-retirement history execution check.

A/B production activation, local retirement, storage-limit changes and paid AI are not authorized by merging this PR. The 5 GiB slot target and 24 GiB aggregate proposal remain unqualified. Historical evidence retains its original commit bindings and does not certify this new split commit. Exact split CI and review are still required.
