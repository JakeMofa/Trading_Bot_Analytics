# Offline PP A → B → fresh A admission evidence

Source-only planner: `backend/postgres/rehearsal_admission.py`. It has no route,
I/O, database dependency, clock reads, activation or retirement authority. Input
metadata must come from captured Polymarket US market IDs; it does not discover
markets or certify quote receipt. Exchange data cannot establish official market
identity. Proposed future generation UUIDs are plans, not allocated partitions.

## Existing contracts and blocking evidence

- `lifecycle.py:286–305` requires exact UTC 900-second boundaries, the next two
  full contiguous official markets after collection admission, and quote source
  and receipt times inside each market and the exact collecting generation.
- `lifecycle.py:355–360` returns early while B collects under the market-pair
  profile. This profile never performs B → fresh A. A schedule fit cannot make
  the currently deployed profile executable.
- `OperatorSession.start` and `LifecycleRepository.enable_collector` cap each
  lease at 4560 seconds. Database lease validity is strict `expires > clock`.
- `bound_seal_window` in `pp_retirement_verify.py` fixes each verification and
  commit deadline at that generation's actual `sealed_at + 30 minutes`.
- The target A slot must have its old generation retired before fresh A can be
  allocated. A/B labels do not substitute for three distinct generation UUIDs.

The planner validates these immutable identities and exact supplied schedules.
It reports both original seal deadlines, proposed completion reserves, expiry
margin and specific HOLD reasons. Readback reserves include archive, structured
drain, independent readback, permit and commit; a network timeout alone is not a
whole-leg budget. A reserve is a proposal, not measured performance evidence.

With admission exactly at 12:00 UTC and earliest possible seals:

| Event | Time |
| --- | --- |
| A's two official markets | 12:00–12:15 and 12:15–12:30 |
| A seal / B start | 12:30 |
| A original readback deadline | 13:00 |
| B's two official markets | 12:30–12:45 and 12:45–13:00 |
| B seal / fresh A start | 13:00 |
| B original readback deadline | 13:30 |
| Maximum existing lease expiry | 13:16 |

Reserving both complete seal windows requires validity past 5400 seconds,
840 seconds beyond the cap even without alignment or operation delays. A
one-microsecond mid-market start waits for the next quarter and has a
1739.999999-second shortfall. Old A's full-window completion also coincides
with the proposed second switch: that does not prove retirement before fresh-A
allocation. With measured, defensible 240-second whole-leg reserves the timing
can fit; the current profile still cannot rotate B, so the planner always HOLDs.
No result is an executable admission or permission to shorten a deadline.

## Minimally scoped continuation to review separately

Preserve the cap and both actual seal deadlines. Prefer two explicit finite
sessions with operator-confirmed OFF and re-admission between them, rather than
an implicit renewal or a larger cap:

1. Session one binds the old A UUID and one actual admitted lease. Observe its
   next two complete official markets, switch to B, archive/verify/retire that
   exact old A before its original 30-minute deadline while B keeps collecting.
   Require independent committed-retirement proof and exact B writer identity;
   then explicitly OFF and prove writer drain. Failure holds existing files and
   stops; it does not establish the rehearsal.
2. A separately reviewed B continuation must bind that same collecting B UUID,
   the already-retired old A UUID, an empty/free A slot and the new finite lease.
   Observe the next two full official markets after this re-admission; no old
   observations can satisfy the new pair. The existing B early return requires
   a narrow, separately qualified continuation mechanism, not a planner bypass.
   A successful exact switch allocates a distinct fresh A UUID. Archive/verify/
   retire exact B against B's original 30-minute seal deadline while fresh A
   persists new feed and saved calculation evidence.
3. Each leg's worst alignment + two markets + full readback window is strictly
   below 4500 seconds; a 4560-second lease leaves only about 60 seconds for
   additional delays. Check actual database lease expiry, predicted remaining
   bounds, host capacity, source/receipt freshness, pending outbox and live reader
   references before every destructive admission. No approval or qualification
   follows from arithmetic alone. Keep fail-closed OFF and exact-generation
   recovery behavior on expiry, missing proof or occupied slots.

This deliberately changes no profile, lease, guard, permit or retirement policy.
The staged design still requires a source implementation, generated native
A/B/fresh-A and partial-failure tests, reviewed exact resource/readback evidence,
independent review and explicit operational authorization. Neither a historical
readback success nor a plan-only schedule closes concurrent collection or full
rehearsal parity.

## Validation

Six admission tests pass, covering exact and mid-market boundary arithmetic,
both original deadlines, cap deficit, strict expiry equality, three UUIDs/slot
order, invalid market/reserve inputs, and a short-reserve schedule that remains
non-executable. A test calls the actual `OperatorSession` and proves 4561 seconds
is rejected without invoking a runner. No host/cloud commands or collectors run.
