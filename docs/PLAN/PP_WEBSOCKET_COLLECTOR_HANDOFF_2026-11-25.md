# PP WebSocket collector and archive handoff

November 25, 2026, Central time. Use the 4 GB PP Benchmark environment for the next live quote test. Make the Polymarket US Markets WebSocket the primary source for saved contract quotes and dashboard updates. Keep REST market lookup for discovery and official BTC terms, and use REST book snapshots for quote recovery when the socket is unhealthy. The switch is pending in the PostgreSQL collector.

[Master roadmap](INTELLIGENCE_REBUILD_PLAN.md) · [Session handoff](SESSION_HANDOFF.md) · [Milestone checklist](../MILESTONES.md)

## Evidence from the live PP comparison

The 4 GB rollout ran release `v0.2.0-pp.benchmark.1` at `93558b2`. The 3:45 p.m. CST market rollover was a single local-only generation. The three readers matched market ID `2915937`. [Successful CD Benchmark](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/45704911568)

| Stage | Seconds after rollover |
| --- | ---: |
| Early reader discovered the market | 9.260 |
| WebSocket subscribed | 9.726 |
| WebSocket received first usable quote | 9.746 |
| Early REST received first usable quote | 14.785 |
| Current REST collector received first usable quote | 18.848 |
| Current REST collector recorded a durable commit | 19.007 |
| Dashboard API returned the saved quote | 19.794 |

WebSocket led early REST by **5.039 s** and the current REST collector by **9.102 s**. The dashboard API returned the matching REST quote **0.946 s** after receipt. WebSocket ran as an observer, so the run measured its quote arrival and the REST path to the API. Measuring WebSocket through the same writer and API is the next acceptance check. Browser rendering has its own latency.

The collector stayed on across 35 live database samples and recorded 10 Coinbase candle-revision rejections while Polymarket continued. PR #216 preserves the first accepted candle when a later response conflicts with it. Minimum available memory was **2,755.49 MiB**, cumulative full memory pressure rose **17.192 ms**, and swap I/O and OOM counts were zero. The 4 GB run had headroom. Its different market and release make the RAM upgrade's contribution to first-quote latency unmeasured. After the test the collector was durably off, 5,356 pending outbox records remained local, and all five retained-generation fingerprints matched. The test used no cloud sync, rotation or retirement.

In the earlier 2 GB PP33 run, all four matched observer windows completed. WebSocket won three by roughly 55–104 s, and REST won one by 0.445 s. Only the first window had a complete canonical trace. The shared canonical collector stopped in the second window on a Coinbase candle-write conflict. The minimum available memory was 852.09 MiB, with zero swap or OOM activity. The evidence identified the candle rejection as the stop cause. [PP33 evidence](evidence/pp33-polymarket-boundaries-2026-11-24.json)

## What the two API responses actually contain

A separate live JSON comparison used the same 4:45–5:00 p.m. CST BTC market across REST market details, REST book and the authenticated full WebSocket subscription. It was a field and snapshot comparison.

| Response | Observed |
| --- | --- |
| REST market details | The slug, market window, BRTI reference index and `assetPriceTerms.priceToBeat` of **$60,089.31** |
| REST `/book` | Bid **$0.60 × 169.90**, offer **$0.61 × 291.09**, 60 bid and 39 offer levels |
| WebSocket full market data | Bid **$0.62 × 73.00**, offer **$0.63 × 1,338.67**, 62 bid and 37 offer levels |
| REST `/bbo` | HTTP 404 on both attempts for this slug |

REST book and WebSocket had the same six `marketData` keys and the same 16 keys inside `stats`. The six keys were `marketSlug`, `bids`, `offers`, `state`, `stats` and `transactTime`. WebSocket added `requestId` and `subscriptionType` outside the book object. The 16 statistics were `openPx`, `lowPx`, `highPx`, `lastTradePx`, `sharesTraded`, `notionalTraded`, `lastTradeQty`, `openInterest`, `openSetTime`, `highSetTime`, `lowSetTime`, `lastTradeSetTime`, `openInterestSetTime`, `notionalSetTime`, `currentPx` and `lastPriceSample`.

The responses arrived about 2 ms apart locally, with exchange book timestamps **15.15 s apart**. Sixty-four price levels had the same quantities and 33 shared price levels had different quantities. This observed difference describes those two book states. The timed rollover above measures the first-quote advantage. Neither book payload carried the official BTC threshold or the running reference price. [Markets WebSocket](https://docs.polymarket.us/api-reference/websocket/markets) · [REST book](https://docs.polymarket.us/api-reference/markets/get-market-book) · [REST market discovery](https://docs.polymarket.us/api-reference/markets/get-markets)

Polymarket US also documents a lightweight quote subscription and a separate trade subscription. The authenticated observer used the full feed with explicit slugs. Automatic rollover means our backend discovers and subscribes to the upcoming market over the socket. The documented US quote feed has no wildcard or new-market discovery subscription. The Asset Prices API supplies one-second BTC/USD reference-price buckets and was tested separately. Keep those buckets labeled by source and freshness, alongside Coinbase spot and candles. Missing Coinbase data should leave Polymarket quotes available and mark the Coinbase input stale. Institutional gRPC access is pending and its live performance is unmeasured. SDK choice alone does not establish a different transport latency. [BTC reference price API](https://docs.polymarket.us/api-reference/asset-prices/overview) · [Institutional gRPC](https://docs.polymarket.us/grpc-api/overview)

## Resume implementation here

1. Discover upcoming market metadata separately from quote ingestion and subscribe before the boundary when a slug is available. Keep the current subscription until handoff. Save the official threshold when it becomes available. Leave empty books visible as missing and handle valid one-sided quotes.
2. Add the source behind a default-off setting. At rollover or reconnect, admit the first usable WebSocket or REST quote for the same market. Route accepted quotes through the current normalization, provenance, exact-decimal and durable PostgreSQL write path. Publish the saved quote through the existing dashboard API. Resume on reconnect, keep one canonical writer, and prevent duplicate or older snapshots from overwriting a newer quote. Use REST book on stream failure and resume socket-first after recovery.
3. On 4 GB PP, measure one rollover from subscription and first usable quote through commit and dashboard API visibility. Keep the **5 s receipt-to-API target** and measure pre-receipt wait separately. Verify stream recovery, Coinbase failure isolation, source freshness, and first quote near a rollover. Keep retained A and B intact. Use the dedicated [CI PP Benchmark](../../.github/workflows/ci-pp-benchmark.yml) and [CD Benchmark](../../.github/workflows/cd-pp-benchmark.yml) workflows.
4. Keep Polymarket BTC reference buckets, Coinbase BTC prices and contract quotes distinct in storage and the dashboard. Correlate source freshness, quote receipt, commit and API timestamps with host memory and collector state. Use [TokenBot Grafana](https://heftychameleon632.grafana.net/d/jagbfc8/tokenbot-archive-observability) for overview and verify which panel series actually arrive during the next run.

## Archive and history context

PP32 trial07 completed A → B → fresh A. Keep the 72-hour rollout and frontend redesign parked during the feed change. The 4 GB live run was a feed comparison and did not repeat the database rotation. Preserve the old 2 GB PP and retained archive generations. [Rotation and archive milestones](../MILESTONES.md)

The retained trial06 B quiet test read and verified 500 pinned rows (828,368 bytes). Cold end-to-end latency was **2.643 s** and warm runs were **1.954, 2.236 and 1.850 s**, all under **4 s**. Separately replayed SQL measured **5.327 ms planning** and **5.774 ms execution**, with no result-row transfer. This supports keeping the existing query for this page. A real dashboard request with history and browser rendering remains a separate measurement. [500-row evidence](evidence/pp32-retained-b-500-quote-diagnostics-2026-11-24.json)

The long-term read path needs hot PostgreSQL rows and verified, deduplicated structured Supabase history queryable by the same deterministic and ML readers. Raw Storage objects support archive verification and replay. Their presence is independent of the structured SQL read path. [Master roadmap](INTELLIGENCE_REBUILD_PLAN.md)
