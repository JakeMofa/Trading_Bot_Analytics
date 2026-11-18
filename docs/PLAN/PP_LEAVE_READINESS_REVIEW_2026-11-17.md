# PP generated-profile leave readiness review — November 17, 2026 CST

## Recorded failure and limit

The bounded pp.9 trial ended with Coinbase stream `unexpected`, then the
operator durably switched collection OFF. The first leave-to-generated command
failed with `entrypoint_precondition_failed` after application services were
recreated. The transition journal remained `leaving`. Subsequent source-bound
checks found the generated API and operator routes healthy, and one bounded
permit-free recovery leave succeeded. The failed subcheck was not logged, so a
post-recreation loopback readiness race is a hypothesis, not a proven cause.
See [the merged trial report](PP_LIVE_DIAGNOSTIC_TRIAL_2026-11-17.md).

## Scoped candidate

After Compose recreation and exact runtime validation, leave waits up to ten
seconds for the generated API and operator loopback routes. It retries only
their fixed connection-unavailable codes. Reachable wrong state, wrong origin,
authentication mismatch, runtime mismatch and other failures stop immediately.
Each two-second host probe starts only with at least two seconds remaining in
both the readiness window and the existing 180-second leave budget. The
entrypoint exposes only fixed generated-runtime, API and operator stage codes
for these post-recreation checks; child diagnostics and all other failures
retain the generic public code.

Durable OFF still precedes any generated service recreation. A failed leave
keeps the fail-closed `leaving` journal; a later permit-free recovery is a
separate bounded command. This candidate does not add an unconditional retry,
extend the leave deadline, change PostgreSQL or enable collection.

Generated regressions cover delayed API and operator binding, permanent
unavailability, reachable wrong state, operator authentication mismatch,
runtime mismatch, durable OFF ordering and failed-leave
journal recovery. All PP control tests pass locally (90 tests, one existing
platform skip). Linux exact-commit CI and a PP release remain separate gates.

## Release boundary

This source change alters the self-contained root controller bundle. PP would
require an exact-source bundle build, hash verification, reviewed installation
and the existing manual deployment/transition controls before it takes effect.
No PP host, cloud or production operation was performed for this candidate.
