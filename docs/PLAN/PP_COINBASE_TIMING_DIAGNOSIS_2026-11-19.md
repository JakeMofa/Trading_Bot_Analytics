# Coinbase source-age incident and opt-in diagnostics

## November 27 — Bounded feed writers on disposable PostgreSQL 17

The Coinbase reader can receive 32 queued ticks while one tick writes. When
that queue fills, the reader waits for capacity. It captures receipt time
before JSON decoding. The opt-in telemetry measures time in the parser, time
waiting for persistence and transaction duration for the same tick. Reconnect
progress still requires a fresh, newly committed event. The Polymarket book
trace can sample one committed event per five seconds with its source time,
receipt time and queue depth.

Coinbase, the Polymarket quote writer and the Polymarket index writer each
reuse a local connection. Each event has its own transaction, lease check,
deduplication and outbox entry under the existing rules. The index poll
publishes the newest validated one-second bucket on receipt and queues every
new observed bucket for persistence. The fresh Benchmark origin polls at most once per second and requests the
preceding 12 completed seconds. Each viewer shares these observations. Other
origins keep the five-second cadence. A 429 triggers bounded exponential
backoff and honors Retry-After. A requested wait longer than one minute
suspends this optional reader for the remaining session. Sustained overload
or a long provider outage can still leave a gap.

Four isolated passes wrote the same 180 generated ticks in A/B/B/A order.
Opening a connection per tick took 0.984 and 0.992 s. Reusing a connection
took 0.127 and 0.132 s. Each reused pass opened one connection. A separate
PostgreSQL test verified distinct committed transaction IDs, idempotent retry,
conflicting payload rollback and durable OFF enforcement. The 4 GB VM still
needs a full-market comparison of source age, writer queue time, verified
ACKs and dashboard visibility under concurrent collection.

## November 19 incident


The captured pp.17 event at 07:10:14 was already late at application dequeue. It is not explained by a frozen API cache: event identities continued advancing, and the API exposed each recently received record.

| Boundary | Captured UTC |
|---|---|
| Source event `1136506416` | 07:09:33.035341 |
| Existing `received_at` | 07:10:13.995072 |
| API generated snapshot | 07:10:14.666480 |

Source-to-dequeue delay was40.959731s; subsequent receipt-to-API delay0.671408s. Server-clock source age was41.631139s, consistent with the observer's41.492s at its earlier request timestamp. Raw evidence records515Coinbase prices over40.498s of receipt time, spanning15.529s of source time. This supports a faster source burst draining through a slower serial sink. It does not isolate upstream/provider delay from TCP/parser buffering or prove a reconnect caused the fresh-head jump at07:10:19. Coinbase's ticker channel batches cascading matches, so trade-ID jumps alone cannot establish loss or reconnect. [Official channel semantics](https://docs.cdp.coinbase.com/exchange/websocket-feed/channels)

`coinbase_session` awaits each `Store.ingest` before requesting the next source item. That transaction opens a local PostgreSQL connection and persists raw, deduplication, projection and outbox evidence. `coinbase_once` stamps `received_at` after `recv()` and JSON parsing, so this timestamp is dequeue/translation time, not socket arrival. The original `available_at=received_at` default is not a commit-duration measurement. Cloud structured sync is a separate process; its connection-reuse improvement does not by itself accelerate the local Coinbase save path.

The separate candidate enables diagnostics only with `TRADEBOT_PP_COINBASE_TIMING=true`. A documented `create_connection` subclass records complete-message WebSocket parser ingress before receive-queue insertion. It also records recv start/completion, dispatch wait, actual `Store.ingest` execution inside its worker thread, return scheduling and fixed reconnect codes. UTC supports source joins; monotonic clocks measure local durations. Parser ingress includes upstream/TCP/event-loop time and is explicitly not NIC arrival. [Client extension API](https://websockets.readthedocs.io/en/15.0/reference/asyncio/client.html), [buffer and backpressure behavior](https://websockets.readthedocs.io/en/15.0/topics/memory.html)

Every save is timed; bounded five-second summaries retain maxima and mean durations plus the worst-save and worst-source-age sample. No price, raw body, credential or provider error text is logged. The256-entry queue tracks timing metadata only; overflow marks ingress timing unavailable until the next connection and leaves raw processing unchanged. Output errors are observational. Existing source/receipt times, raw strings, serial durability, reconnect limits and collection policy remain intact.

Seven focused tests and the full local backend suite344run/40explicit platform/environment skips passed. Actual loopback WebSocket frames, including fragmentation and heartbeat, plus a delayed sink demonstrate queue time separately from true save execution while all three exact raw ticks survive. No live host, release or market endpoint was changed by this candidate.

Use these measurements before selecting a fix. If actual save duration is the bottleneck, qualify local connection/setup or SQL-cost improvements with identical raw identities, one durable transaction per event and the existing writer fence. A larger receive queue would retain more latency; changing coverage or discarding old ticks would change the evidence contract. Precise present cause remains unproven until parser/dequeue/save timings are observed on a separately qualified run.
