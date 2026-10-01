# Initial data access findings

Verified during September 29, 2026 (America/Chicago); responses carry September 30 UTC timestamps. Public unauthenticated GET requests only. No account cookies or keys used.

| Check | Result |
|---|---|
| Crypto market discovery | `https://gateway.polymarket.us/v1/markets?limit=100&active=true&closed=false&categories=crypto` returned 63 markets, including both BTC durations |
| 15-minute target | `assetPriceTerms.priceToBeat` available; sampled active target 83399.79 |
| 1-hour target | Available; sampled target 83408.05 |
| Actual session timestamps | `assetPriceTerms.windowStart/windowEnd`; administrative startDate/endDate differ |
| Canonical identifiers | API slugs include `cpc-`, unlike the event URLs in screenshots |
| BBO | 1-hour request succeeded; first 15-minute BBO returned 404 |
| Order book fallback | 15-minute `/v1/markets/{slug}/book` succeeded with bids/offers, stats and transactTime |
| Resolved example | `/v1/market/slug/cpc-btc-updown-15m-2026-09-29-2300z` returned resolved target 83573.58 and settlement 83807.85, consistent with screenshot UP result |
| Settlement rules | Sampled descriptions specify BRTI, average of 60 observations in preceding minute, rounded to 2 decimals; equality resolves UP |
| Coinbase historical candles | Public minute candles succeeded; bounded test stored 60 of 60 completed minutes |

Collector uses discovery and typed terms, not guessed URLs. It stores raw metadata, rules and decimal strings, and only labels results after confirmed resolved status. BBO 404 uses the verified book fallback; other errors remain visible.

Not yet verified: observed real rollover across a boundary, confirmed 1-hour settlement example, reconnecting live streams, exhaustive historical Polymarket coverage, sustained rate limits or long-term data access costs. Current collection uses bounded REST polling; streaming is a subsequent milestone. No institutional onboarding was needed for these retail public requests.

Sources: https://docs.polymarket.us/api-reference/oapi-schemas/markets-schema.json and https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles . Exact sample responses are in research/samples/.

## Restart and boundary follow-up

A subsequent two-cycle run discovered both 02:00 UTC markets after the initial saved 01:45/01:00 markets expired. The database now contains four distinct market records. Restart discovery successfully advanced both durations without guessed URLs. This demonstrates recovery after a boundary, not uninterrupted streaming across it.

The previous 15-minute market returned MARKET_STATUS_RESOLVING and the previous 1-hour market returned MARKET_STATUS_CLOSED, both without settlementPrice. Their outcomes remain null rather than inferred from exchange prices. Further reconciliation is required once settlement is published.

A quote/book request returned 404 in both follow-up cycles despite the market metadata being available. The collector recorded errors and continued saving BTC reference prices and other market data. Availability of quote/book endpoints is therefore intermittent; metadata quotes can still be preserved but should not be represented as a fresh book. Continuous streaming and automatic reconnect remain future work.

## Streaming verification

Public Coinbase WebSocket received and persisted 102 ticker events during a bounded 25-second live test, with no reconnects. SQLite integrity check passed. Unit tests simulate disconnect/reconnect, resubscription, trade deduplication, credential signing and HTTP 429 backoff.

Official Polymarket documentation distinguishes unauthenticated public REST from API-key-authenticated market WebSocket: https://docs.polymarket.us/api-reference/websocket/markets and https://docs.polymarket.us/api-reference/authentication . The optional adapter is implemented, but its live handshake/subscription and rollover remain unverified without locally configured credentials. Public REST fallback is active.

## Retrospective 15-minute history verification (October 1, 2026 UTC)

The public Coinbase candles endpoint returned all 480 completed one-minute buckets requested for the previous eight hours. The Polymarket US `GET /v1/markets` endpoint with bounded `endDateMin`/`endDateMax` discovery, followed by validation of typed `assetPriceTerms.windowStart/windowEnd`, found 32 of 32 completed BTC 15-minute markets in a separate eight-hour window. All 32 had confirmed outcomes. `GET /v1/price-history` with one market slug and its exact window returned book-derived Yes/No display prices; 512 points were stored. One sampled market returned 16 points over its 15-minute window.

The market-list date filters use administrative dates, so the backfill validates actual typed window times and reports gaps. These responses are retrieved after settlement; they do not establish what the live feed received at a particular moment. Price history is derived from displayed bid/ask, not trades or full depth. No retrospective forecast is entered into `predictions`.

Official references: [Polymarket US Get Markets](https://docs.polymarket.us/api-reference/markets/get-markets), [Polymarket US Get Price History](https://docs.polymarket.us/api-reference/price-history/get-price-history), and [Coinbase Get Product Candles](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles).

## News RSS feasibility (October 1, 2026 UTC)

[CoinDesk publishes an official RSS feed](https://www.coindesk.com/coindesk-news/2021/09/17/coindesk-rss) at `https://www.coindesk.com/arc/outboundfeeds/rss/`. A read-only GET returned HTTP 200, 25 items and GUID, title, HTTPS link, category, and `pubDate` fields. The initial collector pass saved 25 headline references with all publication times present; a repeated pass saved zero duplicates. Eight items matched a simple BTC keyword label. Only headline metadata is stored, not article bodies. The newest sampled feed item was about ten hours old at retrieval, so feed timeliness for 15-minute signals is unproven. Local `first_seen` is the availability bound even when a publisher's `pubDate` is earlier. No paid access or account authentication was used for this check; ongoing access terms and coverage should be rechecked before relying on the feed operationally.
