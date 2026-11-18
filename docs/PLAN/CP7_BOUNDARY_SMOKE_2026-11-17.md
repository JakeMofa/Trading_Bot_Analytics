# CP7 generated market-boundary smoke — November 17 CST

## Scope and result

The first PP live session ended after 159 seconds near a 15-minute market
boundary. Its original exception was not retained. This generated test does
**not** reproduce or identify that historical cause.

`backend/tests/test_postgres_live_boundary_smoke.py` combines the actual PP
supervisor, Polymarket cycle and operator session with generated feed responses
and an in-memory acknowledgement stub. It opens no provider connection, does
not enable the PP host collector, and writes no database or cloud rows.

- A missing new-market discovery produces no replayed old-market quote; the
  next generated discovery publishes only the matching new-market quote.
- A Coinbase tick is acknowledged while the new-market discovery/BBO path
  runs. The market loop does not block that independent task.
- Generated discovery 429/timeout and BBO 404/429/timeout/invalid data produce
  distinct fixed failure codes. The supervisor stops, calls durable OFF, and
  retains no new-market quote after the failed BBO.
- The operator retains the sanitized code through explicit OFF and blocks a
  new ON until that OFF is acknowledged. No provider response text appears in
  operator status.

The adjacent local regression run passed 34 tests in 9.3 seconds. Exact Linux
CI is a separate gate. The existing `python-tests.yml` backend discovery and
the isolated PostgreSQL qualification's `test_postgres*.py` discovery both
include this file; no new workflow or runtime flag is required.

## Remaining gates

This test uses generated clock times and a stub store. It cannot establish
live feed availability, real PostgreSQL write latency, the 30–45 minute PP
A→B switch, Supabase archive/readback, or the first trial's root cause. The
`v0.2.0-pp.9` bounded diagnostic run must capture its fixed code before a
profile restart. If it produces a specific failure, add a regression for that
measured operation and report the old and new outcomes separately.
