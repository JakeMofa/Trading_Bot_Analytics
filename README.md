# BTC Intelligence

Read-only Polymarket US BTC collector, currently focused on 15-minute markets. No orders, account credentials or OpenAI calls. Python standard library only.

Run from this project folder:

```sh
python3 -m unittest discover -s backend/tests -v
python3 backend/app/collector.py --backfill-hours 24
python3 backend/app/collector.py --cycles 10 --interval 30
```

The default duration is 15 minutes. Hourly collection is deferred; saved hourly records remain intact. Explicit `--duration 1h` or `--duration both` options retain support for later use.

The default database is `data/btc_intelligence.db`. Each invocation is bounded and exits; nothing starts automatically. Errors are recorded in `runs` and printed. Historical candles come from Coinbase and are predictive reference data, not BRTI settlement prices. Coverage reports expose missing candles.

This first milestone polls market metadata/BBO every 30 seconds by default. Live exchange streaming, model forecasts, UI, FTS5/traversal and OpenAI analysis are subsequent milestones. No claim that a rollover has been observed until recorded across a real boundary.

Official terms determine each interval, not `startDate`/`endDate`. The collector selects `assetPriceTerms.windowStart/windowEnd`, preserves exact decimal target strings and only labels outcomes from resolved market terms. First-seen timestamps record late capture. Previous expired markets reconcile independently while the next active market is discovered.

See `docs/DATA_ACCESS_FINDINGS.md` and `docs/STRATEGIC_PLAN.md`.

## Streaming milestone

Install once:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python -m unittest discover -s backend/tests -v
```

Run a bounded one-minute collection or explicitly collect until Ctrl+C:

```sh
.venv/bin/python backend/app/streaming.py --seconds 60
.venv/bin/python backend/app/streaming.py --seconds 0
```

Public Coinbase BTC ticker events stream continuously and are deduplicated by trade ID. Each event preserves source and receive timestamps, price, size and source-provided side; side must not yet be interpreted as aggressive buying/selling pressure. Connection failures reconnect with capped exponential delay and resubscribe. Feed state distinguishes connecting, awaiting data, live, stale, disconnected, disabled and stopped. REST remains at 30-second intervals for market discovery, quotes and pending settlement; transient HTTP errors and 429 responses have bounded backoff. No order routes are implemented.

Polymarket WebSocket requires `POLYMARKET_KEY_ID` and `POLYMARKET_SECRET_KEY` environment variables. Set them locally using your secret manager/shell; never paste them into chat or commit them. `.env.example` lists names but is not automatically loaded. Without keys, that stream is explicitly disabled while public REST continues. The authenticated adapter signs each handshake and reopens its market subscription on rollover. Its live protocol remains unverified until credentials are configured.

Data remains local and ignored by Git. Ctrl+C closes the streams; shutdown may wait for an in-flight REST request. Raw streaming retention is not yet automatic: monitor database size before unattended multi-day runs. Nothing starts on boot or keeps running after a bounded command exits.

## Milestone commits

The user requested a tested commit and push for each completed milestone. See `docs/MILESTONES.md` for progress and outstanding verification.
