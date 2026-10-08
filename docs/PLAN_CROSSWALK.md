# Original handoff plan → current build

Updated October 2, 2026. This page connects the user's original handoff to the implementation. The source documents are preserved unchanged: [project summary](BTC_Intelligence_Project_Summary.md), [implementation plan](BTC_Intelligence_Implementation_Plan.md), and [complete architecture](BTC_Intelligence_Complete_Architecture.txt). [STRATEGIC_PLAN.md](STRATEGIC_PLAN.md) explains the revised build order; [MILESTONES.md](MILESTONES.md) reports current evidence and running checks.

The handoff zip in Downloads also contains `README.md`, `RAW_CONVERSATION.md`, and four screenshots. The summary and implementation-plan copies in this repository match the zip exactly. The zip and its raw conversation/screenshots have not been copied into the public Git repository.

| Original implementation phase | Status in this project | What remains |
| --- | --- | --- |
| 0. Repository and skeleton | **Partial** — Git, Python, tests, config and SQLite exist. | FastAPI endpoint and Next.js frontend are later dashboard work. |
| 1. Live market discovery | **Built for 15m** — discovers the active Polymarket US contract by API, without a fixed URL. | Apply and test separately for 1h. |
| 2. Price to Beat | **Built for 15m** — saves the typed API target and provenance. | Continue checking contract rules and source changes. |
| 3. Session manager and Go Live | **Built for 15m** — mid-session starts, 32 audited rollovers, delayed outcomes, controlled restart and verified SQLite recovery. | Prolonged outages remain unmeasured; no further eight-hour soak is planned. |
| 4. Live BTC feeds | **Partial** — Coinbase BTC/USD WebSocket with reconnect and health state. | Add and validate a second exchange before composite prices; the proposed Binance/Kraken feeds are not built. |
| 5. Recent-history backfill | **Built for Coinbase minute candles** — 30-day bounded backfill. | Historical seconds-level trades are not available from minute candles. |
| 6. Calculation engine | **Partial** — target distance, time, 1/5/15-minute returns, realized volatility and volume, with missing/freshness flags. | Proposed seconds-level, order-flow and other features need suitable verified feeds. |
| 7. Order flow and order book | **Deferred** — public Polymarket quotes/books have intermittent 404s; no synchronized depth/order-flow model is claimed. | Verify and collect dependable trade/book data before adding features. |
| 8. Derivatives | **Deferred.** | Verify public funding, open-interest and liquidation sources; test incremental value. |
| 9. SQLite history | **Core built** — markets, observations, candles, stream events, snapshots, predictions, outcomes through market records, retrospective prices and news headlines. | Add model-output, evidence-relationship and richer event tables only as used. |
| 10. Baseline statistical/ML model | **Initial untrained proxy built** — live Up/Down probabilities are saved with model version and assumptions. | Train logistic/XGBoost only after enough distinct labeled markets; compare to simple baseline and quotes. |
| 11. Historical similarity | **Initial retrieval built** — one timestamp-safe live case per prior market. | Evaluate later markets and store a separate historical-model output if it helps. |
| 12. OpenAI intelligence | **News collection begun; OpenAI not called.** | Verify news freshness, link pre-forecast events, then configure API key/budget and test separately. |
| 13. Meta-model / ensemble | **Deferred.** | Need independently measured component outputs and chronological training data. |
| 14. Dashboard | **Partial** — a local read-only status view displays the current 15m market, saved quotes and forecast, feed ages, evaluation counts, news headlines and evidence links. | Authenticated direct Polymarket quote relay is built; richer analysis panels and separate 1h support remain. |
| 15. Evaluation | **Partial and moved earlier** — checkpoint reports, Brier/log loss, calibration, 50/50 comparison and an ongoing forward test. | Need more distinct resolved markets and later holdout data before skill claims. |
| 16. FTS5/traversal memory | **Partial** — FTS5 indexes stored headlines and typed links trace predictions to snapshots and retrospectively eligible cases/news. | Connect timestamp-safe context to separately evaluated analysis outputs; do not imply those links influenced saved baseline forecasts. |
| 17. Optional embeddings | **Deferred.** | Only test if structured retrieval and FTS5 are insufficient. |
| 18. Optional advanced models | **Deferred.** | Benchmark against validated simpler models first. |
| 19. Optional infrastructure | **Deferred.** | Remain local SQLite until measured scale requires more; no separate server is deployed. |

The build order changed for evidence quality: SQLite started alongside collection instead of at original phase 9, and evaluation started with the first forecasts instead of waiting for phase 15. Coinbase was the first verified live exchange feed. The original plan's multi-exchange, order-book, derivatives, specialist-model, OpenAI, dashboard and memory ideas remain on the roadmap; none is marked complete merely because it appears in a planning document. The user's later direction adds 1-hour markets after the 15-minute path and keeps buy/sell execution deferred.
