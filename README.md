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
