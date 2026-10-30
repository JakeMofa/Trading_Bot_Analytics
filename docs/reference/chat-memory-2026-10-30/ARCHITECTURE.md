# Tradebot — Architecture Extract (reference)

Source: `BTC Forecasting Dashboard.pdf` (1,590 pages, exported October 30, 2026). Page references are PDF page numbers. These notes summarize discussions, not independently verified live production state. Current repo files and runtime observations take precedence.

## Current architecture as described in transcript
```text
Coinbase + Polymarket live feeds
             |
             v
       LiveState (RAM)
             |
             v
  live features -> deterministic forecasts -> API/dashboard
             |
             +--> local SQLite on Lightsail (~48h operational/recovery window)
                      |
           verified sync/archive
                      v
           Supabase Postgres + private raw archive storage
           (historical analytics / outcomes / model training / future AI retrieval)
```
See pp. 1540–1564, 1580–1587. The live prediction hot path should **not** require a Supabase query on each tick. Prefetch, cache, train, or periodically refresh historical knowledge. A failure of the historical cloud layer should not stop low-latency live forecasts.

## Storage roles
- **LiveState:** freshest in-memory market state for inference and dashboard.
- **Local SQLite:** colocated hot/recovery store, currently intended to retain approximately 48 hours after archival and retention have been proven safe.
- **Supabase Postgres:** long-term structured history, predictions, official outcomes, analytics and future ML/AI research.
- **Verified raw archives:** raw market data in private object storage, with manifests/checksums/event counts. Rule: **NO VERIFIED ARCHIVE = NO DELETE**.
- **Turso:** discussed as an optional hot-layer substitute, **not an adopted migration**. Keep local SQLite unless benchmarks justify a change; retain Supabase for long-term data. (pp. 1525–1565)

## Future specialized intelligence
- Deterministic models: live market features + trained/cache historical priors + validation and calibration.
- Retrieval-enabled AI analyst: selectively access latest state, Supabase history, similar regimes, news and model evidence; distinguish structured facts from AI interpretations.
- Evaluation: store deterministic, AI and Polymarket forecasts alongside actual outcomes; compare Brier, log loss, calibration, regime/time-to-expiry breakdown and incremental value.
- Meta-model: learn weights by regime using out-of-sample evidence, not simple averaging. (pp. 1566–1587)

## Planned later capabilities, not deployed claims
Phase 2 Coinbase trades/L2; Phase 3 `microstructure_v1`; broader news, macro, on-chain, specialized AI, and model training. Early exploratory stack ideas (Kafka/Redpanda, ClickHouse, Redis, Next.js, etc.) should **not** be mistaken for current deployments. (pp. 15–25, 1501–1514, 1580–1587)

## Canonical source of truth
`docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md` in the local repo governs execution; verify actual implementation and topology from code and infrastructure before edits. (pp. 1589–1590)
