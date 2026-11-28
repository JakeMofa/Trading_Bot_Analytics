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
