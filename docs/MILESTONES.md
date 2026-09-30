# Milestones

## Completed and pushed

1. Read-only 15-minute collector and SQLite history: public market discovery, exact targets, quotes/book fallback, pending result reconciliation, one-day candle backfill, restart recovery. Commit `05ce7f4`.

## Streaming milestone

Implemented public Coinbase ticker streaming, deduplication, timestamps, reconnect/resubscribe, feed health, bounded or explicit continuous runtime, and bounded REST rate-limit backoff. Live temporary test saved 102 ticker events in 25 seconds. Optional Polymarket authenticated market streaming is implemented but not live-verified without keys. Tests cover signing, absent credentials, reconnects and deduplication. Commit is created after final verification.

## Remaining verification

- Actual uninterrupted streaming over a 15-minute market boundary.
- Delayed confirmed outcomes in the main database.
- Authenticated Polymarket stream and subscription protocol with local API keys.
- Sustained operation, reconnect coverage and storage retention.

## Next implementation

Deterministic feature snapshots: target distance, remaining time, candle/trade momentum, volatility and volume with source freshness and missing-data flags. Establish baseline probabilities and evaluation only after labeled coverage and target/source validity are verified.

## Later

Expanded history, deeper feeds and historical matching; news/OpenAI analysis; FTS5 and traversal; evaluated ensemble and dashboard. Buying/selling and paid AI calls remain deferred.
