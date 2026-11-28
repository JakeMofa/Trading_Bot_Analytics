# CP3 isolated PostgreSQL application

This application ports the deployed `d56b4a7` dashboard/API field contract and
the deterministic `features_v1` / `gaussian_distance_v1` calculation into the
CP2 schema. It does not import the superseded SQLite application branch.

`PYTHONPATH=backend` commands, after explicit CP2 migration and CP4 generated
origin bootstrap:

```sh
python -m postgres.ingestion --generated
python -m postgres.worker --once
python -m uvicorn postgres.api:app --host 0.0.0.0 --port 8000
python -m postgres.acceptance --base-url http://api:8000
```

API and calculation normally run as separate processes. Discovery runs on its
own task; calculations are serial. API refreshes bounded local records in the
background; `/state/current`, `/api/state`, `/forecast/current`, `/models/current`
and `/events` serve RAM. SSE reconnect returns a full snapshot and clock-driven
updates expire feeds even if no new event arrives. `/dashboard` serves the actual
deployed HTML with PostgreSQL, data-mode and unsupported-feature corrections.

`TRADEBOT_DATABASE_DSN_FILE` supplies the role-specific DSN. Environment defaults
to `preprod`, data mode to `generated`, origin to `generated-pp`. `replay` accepts
explicit JSONL input of at most 500 events / 2 MiB. Live/preview modes and an
enabled collector flag fail closed. `TRADEBOT_OUTBOX_MAX_PENDING` defaults to
10,000; serialized admission holds new writes before this bound without deleting
evidence. This fixture bound is not a production capacity estimate.

Ingestion acknowledges only committed transactions. Source IDs are scoped by
origin/source, exact decimals and original source timestamp text survive, and
duplicate events compare immutable content excluding retry receipt time. Late
events route the current generation under the writer-state shared lock. Every
core write and protected input appends an atomic outbox envelope. Markets are
revision projections; changed candle content deliberately raises a conflict
until an explicit revision importer is qualified. Calculations retain price
evidence plus the full exact market/candle envelope through protected FK links.

History requests are bounded; DB errors return unavailable, not empty success.
Archive retrieval is an injected CP4 service and disabled by default. It is never
a price fallback. No SQL DDL runs at API/worker startup; schema verification is
mandatory.

Offline evidence: `test_postgres_application.py` covers decimal arithmetic,
minute gaps, receipt-vs-source freshness, future/reordered prices, market rollover,
stale publication, real HTTP/SSE reconnect, dashboard routes, request bounds,
config rejection and independent discovery. Its PostgreSQL transaction test
requires `TRADEBOT_TEST_DSN[_FILE]` and optional
`TRADEBOT_TEST_LIFECYCLE_DSN[_FILE]`. Linux PostgreSQL 17 image qualification is
the integration gate; passing offline tests alone does not qualify the adapter.

Remaining gaps: real official-feed adapters/ownership fencing, production preview,
legacy import, candle corrections, ensemble/news/evaluation/context history,
dashboard outcome listing, detailed host monitoring, capacity/recovery and paid
AI. Existing legacy code/tests remain untouched. Delayed outcome writes are
represented immutably with protected evidence; displaying them is still a gap.

## Benchmark live quotes

The opt-in quote-display overlay replaces the supervisor's REST quote loop
with a direct markets socket. Discovery still reads the official catalog.
The operator and API share a private Unix datagram path. The API alone binds
the socket. Provision the directory owned by UID 10001 with mode 0700 on
Benchmark; only the operator receives the two signing secret files. The
operator sends compact market/quote snapshots without waiting for subscribers.
The durable writer uses a bounded FIFO (32 events), backpressures ingestion
when full, and rechecks the database writer lease at commit. A crash can
interrupt queued, uncommitted observations. The display is observational.

The existing structured worker authenticates archive readback before ACK.
Each WebSocket quote enqueues the structured evidence envelope inside its raw
write transaction. This does not create a second permanent local core row. Received and newly saved quote counters are per collector
session. The API samples acknowledged WebSocket quote envelopes every 15s.
A missing sample displays as unknown. Realtime and browser credentials are
unnecessary for this path.

For a live measurement enable boundary tracing. Match the first WS receipt,
API publication and writer commit traces by event ID. The rendered quote
element exposes its event ID in `data-event-id`. Observe the visible element
through a browser paint and record the browser/host clock offset or timing
bounds. The state field `database_quote_id` identifies the independently
hydrated local quote. An ID missed between refreshes is an unobserved
comparison. Check the structured record's event ID, source, exact prices and
content hash with the scoped hosted reader. Do not use receipt of a display
packet or an aggregate counter as evidence of a particular hosted row.


### Saved prediction history

`GET /history/market-predictions` takes `market_id`, `start`, `end`, and a fixed
`as_of` decision cutoff in RFC 3339 form. The forecast window includes the start
and excludes the end, spans at most one hour, and includes only forecasts saved
by the cutoff. Pages default to 100 rows and allow up to 500. Pass the returned
`next_cursor` with the same scope for the next page in descending decision order.

FastAPI reads the origin's durable local predictions across A and B. A retired
interval also queries private structured history and verifies each hosted
projection against its receipt and revision. Set `include_archive=true` to check
both tiers while the generations are still attached. The response identifies
the tier for each saved prediction and any incomplete coverage. Missing
predictions and persisted abstentions remain distinct.

The optional PP API profile enables `TRADEBOT_PP_PREDICTION_HISTORY=true` and
supplies its origin's SELECT-only session DSN at
`/run/secrets/pp_prediction_history_reader_dsn` and pinned certificate at
`/run/secrets/pp_history_ca`. The existing hosted role and TLS checks run per
request. Local reads work with the reader disabled.

### Robinhood BTC/USD quote observer

An isolated comparison process uses the official Robinhood Crypto v2 best
bid/ask GET for BTC-USD. The sample contains Robinhood's bid and ask, their
arithmetic midpoint for an uncrossed book, local request and receipt times in
UTC, and HTTP duration. Crossed books retain both prices with an explicit
status and an empty midpoint. The documented v2 schema lists symbol, bid and
ask. An authenticated response also supplied a nanosecond timestamp. Preserve
it as `provider_timestamp`; its meaning is undocumented. Age since PP receipt measures
the observer's handling of that response. Exchange-to-PP delay remains unknown. The midpoint is an auxiliary reference for comparison with the
Polymarket BTC index and Coinbase. [Official v2 market-data schema](https://docs.robinhood.com/crypto/trading/#operation/api_v2_crypto_marketdata_best_bid_ask).

With an authorized quote-reading key supplied to the observer process as
`ROBINHOOD_API_KEY` and `ROBINHOOD_PRIVATE_KEY` (a base64 32-byte Ed25519
seed), run from the backend directory:

```sh
python -m postgres.robinhood_quote_observer --duration-seconds 60 --interval-seconds 5
```

The CLI emits JSON lines. It polls one endpoint, disables redirects, reuses one
connection pool, honors 429 backoff and stops immediately on 401/403. The
default cadence sends up to twelve requests per minute. The observer has no
database, order, or calculation path.

### Robinhood v1 BTC/USD history

The optional Benchmark feed reads Robinhood's own `price` from
`GET /api/v1/crypto/marketdata/best_bid_ask/?symbol=BTC-USD`. Robinhood
defines that price as a midpoint of partner quotes that include its spread.
Its timestamp records Robinhood’s retrieval time. Each poll records the exact
response, quoted prices, buy/sell spreads, retrieval time, PP request time,
receipt time and HTTP duration. A crossed quote preserves both sides and the
reported price in the evidence while the displayed midpoint stays empty.
[Official v1 schema](https://docs.robinhood.com/crypto/trading/#operation/api_v1_crypto_marketdata_best_bid_ask).

One authorized collector signs and polls the endpoint once per second using a
shared HTTP client. The response is published to FastAPI over the private
display socket before its PostgreSQL commit. Event identity follows the
individual poll and stays stable across write retries. Verified structured
sync archives its `core.protected_evidence` revision. Market History includes
these shared BTC/USD observations within the selected receipt and decision
times. The dashboard labels Coinbase, the Polymarket reference and Robinhood
separately. The existing baseline calculation continues to use Coinbase.

Enable the feed on a qualified Benchmark run with
`TRADEBOT_PP_ROBINHOOD_REFERENCE=1` and the quote display enabled. Supply
`ROBINHOOD_API_KEY_FILE` and `ROBINHOOD_PRIVATE_KEY_FILE` as read-only
collector secret mounts. A 429 honors Retry-After. A 401/403 or persistent
database write failure stops the Robinhood feed independently of Polymarket.

Robinhood Crypto's November 2026 customer agreement limits use of third-party
market information and requires its written consent for storage, derived uses,
and redistribution. Confirm the rights covering the intended historical and
client-facing uses with Robinhood. [Customer Agreement, section 15](https://robinhood.com/us/en/crypto-customer-agreement/).
