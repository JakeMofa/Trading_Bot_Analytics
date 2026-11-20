# PP23 deployment and OFF readiness — November 20, 2026 UTC

This is a readiness snapshot before the planned 01:15 UTC official market.
**Live acceptance remains pending.** It contains no collector ON or rotation
receipt and does not qualify concurrent archival throughput or deletion.

PR #192 merged corrected source `f964c93fdf67221837f20eb3e20faddb64ad4ab2`.
Exact merge CI [44647163600](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44647163600)
passed. Publication [44647852318](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44647852318)
created `v0.2.0-pp.23`; downloaded source and manifest checksums matched.
CD [44648041989](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44648041989)
passed all 11 generated acceptance checks, including recovery. The independently
qualified controller remains `65de5662…`; the application image is
`sha256:ad7fdf0db440444556c39a2fad474a901cb925091c68a58e3f39f8a318486799`.

The exact fresh origin `pp-live-pp-trial-20261119-02`, initial A
`41c82044-0fb8-4900-bea0-7c43ba079ff0`, reached `PP_LIVE_READY_OFF` after
source/image/anchor-bound cloud proofs were installed. Both separate structured
and raw archive workers returned `started`; collection remained OFF at this
readiness snapshot. Historic trial01 and older generations remain preserved.

## Holds and bounded maintenance

An instrumented entry and its recovery hit the unchanged host headroom guard:
**1,071,587,328 available bytes versus 1,073,741,824 required**. Separate read-only
checks passed profile, PostgreSQL, filesystem binding, generated runtime and
API/operator checks. The earlier uninstrumented generic failure's exact exception
cannot be reconstructed; the instrumented measurement establishes a later real
headroom failure. No memory guard was lowered or bypassed.

After confirming all PP writers durably OFF and the firmware daemon idle, an
independently reviewed, exact-host maintenance runner paused `fwupd` and its
refresh timer using owned runtime masks. It retained original service states and
unit fragments, with an automatic restoration scheduled after 120 minutes and
30-second retries on restoration failure. Explicit restoration is also required
as cleanup; **neither explicit nor automatic completion is claimed yet**.
Five mocked maintenance tests and independent review passed. The paused daemon
is unrelated to database or application collection services. Normal generated
services were restored before the successful fresh entry.

Production's API collector was temporarily configured OFF and process-fenced for
the authorized trial; this is not an unchanged-production claim. The production
fence receipt reports `enabled=false`, `running=false`. No production database
change was made. Restore the prior production service configuration after PP is
durably stopped and its final retained generation is drained and verified.

## Remaining live evidence

Observe the actual ON receipt, two complete official markets in each outgoing
generation, A → B → fresh A without an intervening collector stop, bounded
archive/independent readback/deletion for each outgoing generation while its
successor writes, and usable API/SSE/input freshness. Finish with durable OFF,
final retained generation drain/readback, maintenance restoration, and production
configuration restoration. Keep source gaps and performance failures explicit.
Phase 1.75/I7 stay open until these results are recorded.

[Sanitized readiness evidence](evidence/pp23-deployment-readiness-2026-11-20.json).
