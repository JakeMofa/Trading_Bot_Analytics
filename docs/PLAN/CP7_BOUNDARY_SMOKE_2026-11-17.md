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

The adjacent local regression run passed 34 tests in 9.3 seconds. Exact source
`448cd1f` passed [push CI 44217282644](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44217282644)
and [PR CI 44217319889](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44217319889).
The isolated PostgreSQL job logs show both new smoke methods executed. The
existing `python-tests.yml` backend discovery and isolated PostgreSQL
qualification's `test_postgres*.py` discovery include this file; no new
workflow or runtime flag is required.

## WebSocket classification successor

The next bounded PP diagnostic run reported `coinbase_stream.unexpected`
before a market boundary. That names the failed task; it does not retain the
exception subtype or establish that either live run had the same cause.

The successor changes only sanitized classification. For the pinned
`websockets==15.0.1` client, a generated socket exercises normal and error
closures, rejected upgrade status, invalid handshake, protocol exception,
EOF transport failure and a genuinely unknown error. It asserts one connect
attempt, durable OFF and a fixed operator code with no close reason, URI,
response body or credential text. HTTP statuses map only to allowlisted
`http_404`, `http_429`, `http_4xx`, `http_5xx` or `http_unexpected` categories.
The 35 adjacent local tests passed; successor exact CI remains pending.

The pinned library [documents `recv()` closure exceptions](https://websockets.readthedocs.io/en/15.0.1/reference/asyncio/client.html)
and [handshake exception classes](https://websockets.readthedocs.io/en/15.0.1/reference/exceptions.html).
It also supports automatic reconnection, but this patch does not enable it.
A future bounded retry policy for an evidenced transient close or transport
failure must separately bound elapsed time and attempts, preserve truthful
feed staleness, and still stop on authentication/protocol/invalid-data errors.

## Remaining gates

This test uses generated clock times and a stub store. It cannot establish
live feed availability, real PostgreSQL write latency, the 30–45 minute PP
A→B switch, Supabase archive/readback, or the first trial's root cause. The
next bounded run must capture its more specific fixed WebSocket code before a
profile restart. A specific category should drive a separately reviewed fix;
this classification alone cannot qualify live continuity.
