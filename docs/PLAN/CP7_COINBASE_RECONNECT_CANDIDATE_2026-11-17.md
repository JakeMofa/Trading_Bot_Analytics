# CP7 Coinbase reconnect candidate — November 17, 2026

## Scope and result

This is an offline, default-off code candidate stacked on the PR #93
WebSocket diagnostic taxonomy. It has no PP host, Supabase, production or
collector-activation effect. The historical PP `coinbase_stream.unexpected`
failure remains unattributed: its exception subtype was not retained, so this
candidate is not evidence that the live failure is fixed.

The source worker retries only `ws_closed_ok`, `ws_closed_error`, `transport`
and `timeout` from `coinbase_stream`. The delay is 1, 2 and 4 seconds for
successive failures in a rolling 60-second window. A fourth failure in that
window stops the session. No session performs more than 12 reconnects. The
existing operator session also has a hard 30-minute maximum. Each reconnect
uses the existing bounded Coinbase subscription and source timeouts.

The worker never retries a storage write or ownership hold, invalid payload,
protocol or handshake error, or an HTTP rejection (including 401, 429 and
5xx). An exhausted retry budget propagates a fixed sanitized failure code to
the supervisor, which durably stops the collector. OFF during backoff returns
promptly; supervisor cancellation also remains in force. Reconnect does not
create, backfill or mark a tick fresh. Each received event is acknowledged
before another is read; duplicate source IDs remain subject to Store's
durable content-hash conflict check. Existing source-age health becomes stale
without new acknowledged data.

This classification is intentionally narrower than the automatic reconnect
facility described by the official [websockets 15.0.1 client documentation](https://websockets.readthedocs.io/en/15.0.1/reference/asyncio/client.html):
it does not retry handshake statuses because PP has not qualified which
provider responses are recoverable. The [exception taxonomy](https://websockets.readthedocs.io/en/15.0.1/reference/exceptions.html)
distinguishes clean/error closure from invalid handshakes and protocol faults.

## Generated qualification

Network-free tests exercise repeated closure, rolling-window and total
budgets, stop during real backoff, duplicate replay, rejected handshake,
invalid payload, an actual `StorageHold`, and sanitized diagnostics. The
updated boundary smoke tests verify which fixed failure classes reconnect
and which stop immediately. The affected local source, ingestion, supervisor,
operator and boundary suites passed **42 tests**. Exact-commit Linux CI is
required before this candidate is qualified.

## Remaining gates

- The previous PP `unexpected` exception needs a new bounded observation with
  preserved sanitized subtype before any root-cause claim.
- PP's last reported 5,268 pending outbox rows against the 10,000 cap are an
  independent live-run gate. A further long ON trial needs verified structured
  backlog drain or a separately qualified safe capacity path.
- No actual PP reconnect continuity, live market boundary, source freshness,
  A/B switch, archive readback or retirement is established here.
- PR #93 must be merged or otherwise incorporated before this stacked
  candidate targets `preprod`; no PP deployment is authorized by these tests.
