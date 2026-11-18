# CP6 bounded structured drain: first offline slice

Status: **generated-only candidate**. It is default OFF and has no CLI,
Compose service, host controller command, cloud credential mount or schedule.
No PP host, Supabase row, production service or retention setting changes here.

## Why the one-shot is insufficient

The reviewed one-shot probe acknowledges at most 25 rows. The last PP live
trial moved pending outbox from 1,530 to 5,268 in about 282 seconds, a net
13.25 rows/second. With the unchanged 10,000-row admission cap, the 4,732-row
remaining runway is about six minutes at that *observed net* rate. A 30-minute
trial would need to verify and acknowledge about 29,100 rows to end with no
pending backlog. These estimates are not a cloud throughput qualification.
No cap increase is included.

## First code boundary

`LifecycleRepository.structured_pending_generations` bounds the pending count
and selects sealed/verified generations before the collecting generation.
Unknown, orphaned, null or more-than-two pending generations cause HOLD. The
selection is only a hint: each existing worker rechecks its generation and
pending rows under the origin-wide advisory lock before cloud I/O.

`drain_bounded` accepts only an explicit call, the exact `pp-live-pp` origin
and the unchanged 10,000-row cap. It reuses the existing active/sealed workers,
whose local ACK follows a separate fresh authenticated readback. One call is
limited to 12 cycles, 300 rows, 24 cloud operations and 180 seconds; each
cycle keeps the existing one-shot's 25-row, 256 KiB decoded, two-operation and
20-second bounds. It yields the origin lock between cycles. Cloud failure or
changed evidence propagates a failed result; a late return after an ACK is
reported as ambiguous and requires durable reconciliation.

The selector runs before the worker takes its advisory lock. Another worker
may acknowledge that page meanwhile; an `idle` worker result is therefore
counted as one bounded selection, with zero claimed ACKs/cloud operations,
then reselected. Repeated races stop at the cycle limit. The injected
transport factory receives a finite per-cycle deadline but **must be proved a
pure constructor before runtime wiring**; only the workers' two cloud methods
may open bounded connections.

This conservative limit **cannot sustain** the observed PP live outbox rate.
It proves scheduling, ordering and fail-closed behavior in generated tests;
it is deliberately not wired to PP. Its transport factory must be pure until
the worker's per-operation deadline applies; host wiring must verify that.

## Release path and next gate

1. Qualify the merged one-shot controller source and exact preprod CI. Build
   the deterministic controller zipapp and verify its hash. On PP, the current
   `generated_restored` journal permits a separately reviewed controller-code
   replacement; preserve the previous helper code. Verify the new installed
   hash via the dedicated forced-command identity route.
2. Update the PP deployment target's controller hash and qualification commit
   through a small reviewed PR. Require exact preprod CI. Publish a unique
   candidate for that exact source, then dispatch existing manual CD Preprod.
   It installs the application image while leaving the collector, cloud sync
   and retirement OFF. Record its image ID and generated acceptance.
3. Use the existing PP live-control workflow to enter `ready_off` without
   starting collection. Run `structured-probe-v1 preflight`, which sends zero
   cloud requests. Review the exact generation/state/first pending outbox ID;
   prepare one root-owned, expiring permit. The fixed one-shot performs at
   most 25 rows, two cloud operations and 20 seconds, then reconciles
   receipts and local ACK before claiming PASS.
4. Measure actual row rate, per-page cloud time, receipt growth and PP outbox
   change. Only then review a larger *separately bounded* drain session and
   its host control. Require sustained verified drain faster than peak live
   generation, plus outage headroom, before a 30-minute A/B live trial.

The published source and controller hash are distinct. Current
`.github/deploy/targets.json` still pins the prior controller, so a successful
source CI alone cannot deploy this path. There is no GitHub Actions workflow
for the structured one-shot; its operator command uses the same dedicated
pinned PP identity and one-use host authority. Adding a workflow is a separate
control change, not a reason to bypass the installed controller.

No production cutover, raw Storage archive, local partition retirement or
Phase 1.75 acceptance follows from this first slice.
