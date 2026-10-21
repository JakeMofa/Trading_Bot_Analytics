# BTC Intelligence Project — Conversation Summary

## 1. Core Goal

Build a local-first real-time Bitcoin intelligence system focused first on **Polymarket US BTC Up/Down 15-minute markets**.

The system should continuously answer:

> What is the probability that BTC finishes the current 15-minute Polymarket interval above or below the current **Price to Beat**?

The system should not make a simple chart guess. It should combine live market data, recent history, historical similarity, derivatives, order flow, order book behavior, Polymarket pricing, and optional AI-based news/event interpretation.

The system should display probabilities such as:

```text
UP   64%
DOWN 36%
Confidence: 72%
```

The system must never assume 100% accuracy. It should be evaluated objectively and allowed to say that there is no strong edge.

---

## 2. Polymarket 15-Minute Market Behavior

Each Polymarket BTC 15-minute market is a separate market/session.

Example sequence:

```text
23:00–23:15 UTC
23:15–23:30 UTC
23:30–23:45 UTC
23:45–00:00 UTC
```

Each session has its own:

- Start time
- End time
- Price to Beat
- Current BTC price
- Up/Down market prices
- Final result

When a session ends, the Polymarket UI shows **Go to live** and moves the user to the current active market.

Our application must simulate that automatically without depending on manually clicking the UI.

The application should:

1. Find the current live BTC 15-minute market.
2. Capture its Price to Beat.
3. Capture start/end time.
4. Monitor the market until expiration.
5. Save the result.
6. Automatically roll into the next active 15-minute market.

The application must not hard-code a single Polymarket URL because the URL changes every 15 minutes.

---

## 3. Starting the App Mid-Session

The application may start when a Polymarket interval is already underway.

Examples:

```text
10 minutes remaining
5 minutes remaining
2 minutes remaining
```

The app should not wait for the next session.

On startup it should:

1. Determine the current live 15-minute market.
2. Read the Price to Beat.
3. Determine elapsed and remaining time.
4. Backfill recent BTC price/trade history from available APIs.
5. Join the current session immediately.
6. Mark the first market as a partial-session capture if necessary.
7. At the next 15-minute boundary, begin a full-session capture from second zero.

For very late startup (for example only seconds left), the app may show a prediction but should mark confidence lower or wait for the next interval depending on the final backtested policy.

---

## 4. What the Model Is Actually Predicting

The main prediction target is not simply:

> Will BTC go up?

It is:

```text
P(final settlement price >= Price to Beat)
```

The key real-time variables include:

- Current BTC price
- Price to Beat
- Distance from target in dollars
- Distance from target in percent
- Seconds remaining
- Recent price velocity
- Recent acceleration
- Volatility
- Volume
- Buy/sell pressure
- Order-book imbalance
- Liquidations
- Open interest
- Funding
- Cross-exchange price behavior
- Current Polymarket Up/Down pricing
- Optional relevant news/events

Time remaining is extremely important. Being $30 above the target with 14 minutes left is very different from being $30 above with 10 seconds left.

---

## 5. Data Sources

The first version should use free/public market data wherever possible.

### Market and exchange data

Potential sources:

- Binance
- Coinbase
- Kraken
- Deribit
- Polymarket US

Use **WebSockets** for continuously changing market data whenever possible.

Use REST/API calls mainly for:

- Market discovery
- Session metadata
- Historical backfill
- Occasional verification

Avoid continuous webpage scraping.

Scraping should only be a fallback for values that are not exposed through structured endpoints.

---

## 6. Why We Do Not Rely on the Chart Alone

The chart shows what price has already done.

A stronger short-horizon model should also see what is happening underneath the chart:

- Aggressive market buys and sells
- Bid/ask depth
- Order-book imbalance
- Spread
- Liquidity changes
- Trade velocity
- Funding
- Open interest
- Liquidations
- Cross-exchange behavior
- Market-implied Polymarket probability

Two charts can look nearly identical while the underlying market structure is very different.

Therefore chart/pattern analysis should be one model, not the entire system.

---

## 7. Historical Data Strategy

The project does **not** need 5–10 years of detailed data before starting.

Recent history matters heavily for a 15-minute model.

Useful windows include:

```text
Last 5 seconds
Last 30 seconds
Last 1 minute
Last 5 minutes
Last 15 minutes
Last 1 hour
Last 4 hours
Last 24 hours
Last 7 days
Last 30 days
```

Longer history is useful as a bonus for training diversity and regime testing.

Basic OHLCV price history for years is cheap and small.

High-frequency order-book history is the expensive/storage-heavy part.

The system should start collecting its own detailed history from day one.

There are 96 fifteen-minute windows per day:

```text
1 day   = 96 markets
30 days = 2,880 markets
90 days = 8,640 markets
```

Each completed interval becomes a new training example.

---

## 8. Historical Similarity Model

The historical model is the system's quantitative memory.

It should answer questions such as:

> When BTC was $20–$50 below the target with 5–7 minutes remaining, similar volatility, similar order flow, and similar derivatives conditions, what usually happened?

Example:

```text
Similar historical states: 428
Ended UP:   142
Ended DOWN: 286
```

This becomes one signal, not the final decision.

Historical similarity should compare structured features, not only chart shapes.

---

## 9. Specialist Model Layers

The model should use multiple specialist layers.

### Target/Time Model

Inputs:

- Price to Beat
- Current price
- Distance from target
- Seconds remaining
- Current volatility

### Price / Momentum Model

Inputs:

- Recent returns
- Velocity
- Acceleration
- Trend
- Candle structure
- Volume

### Order-Flow Model

Inputs:

- Market buy volume
- Market sell volume
- Buy/sell imbalance
- Trade delta
- Trade velocity

### Order-Book Model

Inputs:

- Bid depth
- Ask depth
- Spread
- Imbalance
- Liquidity near price
- Liquidity changes

### Derivatives Model

Inputs:

- Funding
- Open interest
- Open-interest change
- Liquidations
- Perpetual basis
- Futures behavior

### Historical Model

Inputs:

- Similar past market states
- Regime information
- Recent performance patterns

### Optional News / World Intelligence Model

Inputs:

- Major market news
- Macro events
- Fed statements
- Crypto-specific events
- Exchange incidents
- Regulatory news
- Large institutional BTC announcements

### Meta-Model

The final decision layer combines all specialist outputs and learns which models matter most in different conditions.

It should not simply average all model probabilities.

---

## 10. What Makes the Smart Decision

The final decision should come from a **meta-model**, initially something lightweight such as XGBoost or LightGBM.

Example specialist outputs:

```text
Target/time model      DOWN 66%
Order-flow model       DOWN 72%
Order-book model       DOWN 64%
Derivatives model      DOWN 59%
Historical model       DOWN 69%
News model             Neutral
```

The meta-model can learn different weighting behavior by market regime.

Example:

- In high volatility: trust order flow and derivatives more.
- In quiet markets: trust order-book and target/time features more.
- During important macro events: increase news/macro weight.
- In the final minute: target distance + time remaining + volatility matter heavily.

---

## 11. OpenAI's Role

OpenAI should **not** be the main BTC predictor.

Do not send every trade, tick, or order-book update to OpenAI.

Python and ML models should handle numeric data.

OpenAI should be used as an **intelligence/analysis layer** for things such as:

- News interpretation
- Event relevance
- Unusual market situations
- Contradiction analysis
- Concise explanation of why the model moved

Example structured AI output:

```json
{
  "btc_relevance": 0.91,
  "direction": "bearish",
  "impact": 0.74,
  "confidence": 0.86,
  "time_horizon": "1-3h"
}
```

The OpenAI layer should receive compact, already-calculated context rather than raw data.

Example compact market state:

```json
{
  "price_to_beat": 83807.85,
  "btc": 83776.42,
  "distance": -31.43,
  "seconds_remaining": 376,
  "momentum_1m": -0.09,
  "momentum_5m": -0.21,
  "order_flow_30s": -0.61,
  "book_imbalance": -0.27,
  "oi_change_5m": -0.31,
  "polymarket_up": 0.38
}
```

This keeps context and cost small.

---

## 12. Free-First Architecture

The project should be essentially free to start.

Primary free/open-source stack:

- Python
- FastAPI
- SQLite
- SQLite FTS5
- XGBoost
- LightGBM
- scikit-learn
- PyTorch (later)
- Next.js
- React
- TradingView Lightweight Charts
- Docker

Free/public market APIs and WebSockets should be used where possible.

Optional paid component:

- OpenAI API using existing pay-as-you-go credit

No need initially for:

- Kafka
- Kubernetes
- Neo4j
- Dedicated vector database
- Paid institutional market data
- Large cloud infrastructure

---

## 13. Storage Strategy

V1 should use a lightweight local database.

Recommended starting point:

```text
SQLite + FTS5
```

Potential tables:

### markets

```text
id
start_time
end_time
price_to_beat
final_price
result
polymarket_market_id
```

### snapshots

```text
timestamp
market_id
btc_price
distance_to_target
seconds_remaining
momentum_10s
momentum_1m
momentum_5m
volume
order_flow
book_imbalance
volatility
funding
open_interest
liquidations
polymarket_up_price
```

### predictions

```text
timestamp
market_id
up_probability
down_probability
confidence
model_version
actual_result
```

### model_outputs

```text
timestamp
market_id
model_name
up_probability
down_probability
confidence
```

### events

```text
timestamp
headline
summary
source
btc_relevance
direction
impact
confidence
```

### relationships

```text
from_type
from_id
relation
to_type
to_id
```

This relationships table gives a lightweight graph/traversal layer.

---

## 14. Lightweight Traversal / Knowledge Memory

Do not store every BTC tick in a graph database.

Use SQLite for numeric/time-series snapshots.

Use the `relationships` table for semantic relationships such as:

```text
Prediction 581
  USED_EVENT -> Event 92
  SIMILAR_TO -> Prediction 341
  OCCURRED_IN -> Market 126
  USED_PATTERN -> Pattern 44
```

SQLite recursive queries can support light traversal.

FTS5 should index:

- News
- AI explanations
- Market summaries
- Prediction failures
- Model notes

A vector database is not required initially.

If semantic search becomes important later, possible upgrades include:

- OpenAI embeddings stored locally
- PostgreSQL + pgvector

---

## 15. Short-Term vs Long-Term Memory

The system can think of memory in three layers.

### Short-Term Memory

Current/live state:

- Latest BTC price
- Current Price to Beat
- Current timer
- Current order book
- Current rolling features

V1 can keep this in Python memory and SQLite; Redis can be added later if needed.

### Quantitative Historical Memory

Stored in SQLite initially:

- Markets
- Snapshots
- Predictions
- Outcomes
- Model outputs

### Semantic / Traversal Memory

Stored through:

- FTS5 text indexes
- Relationships table
- Optional embeddings later

---

## 16. Continuous Operation

When the app starts, it should continue running.

Live data should primarily arrive via WebSockets.

Example flow:

```text
Exchange WebSocket
    ↓
new trade/order-book update
    ↓
Python ingestion
    ↓
update rolling state
    ↓
recalculate features
    ↓
run models
    ↓
update current probability
    ↓
store prediction snapshot
```

Predictions might update every 1–5 seconds, even if raw market data arrives much more frequently.

Polymarket market discovery can be checked periodically as a safety mechanism around session boundaries.

---

## 17. Dashboard Concept

The dashboard should show something like:

```text
BTC UP/DOWN • LIVE

23:15 → 23:30 UTC

PRICE TO BEAT        $83,807.85
BTC NOW              $83,755.99
DISTANCE                -$51.86
TIME LEFT                 09:50

OUR FORECAST
UP                         34%
DOWN                       66%
Confidence                 72%

POLYMARKET
UP                         30%
DOWN                       70%

SIGNALS
Target/time             Bearish
Order flow              Bearish
Order book              Neutral
Derivatives             Slight bearish
Historical similarity   Bearish
News                    Neutral
```

The app should also display why the probability changed.

Example:

```text
18:31  54% -> 61% UP
Reason: aggressive spot buying increased

18:34  61% -> 67% UP
Reason: short liquidations increased
```

---

## 18. Evaluation and Accuracy

The system must never claim 100% accuracy.

The first goal is to determine whether the model has a measurable edge.

Track:

- Directional accuracy
- Calibration
- Brier score
- Accuracy by confidence bucket
- Performance by time remaining
- Performance by volatility regime
- Performance by signal/model
- Comparison against Polymarket implied probability
- Optional simulated P/L after fees/slippage later

Example calibration test:

```text
Predicted ~60% -> should be correct around 60%
Predicted ~70% -> should be correct around 70%
Predicted ~80% -> should be correct around 80%
```

If the model says 80% but wins only 55%, it is overconfident and not trustworthy.

---

## 19. Model Improvement Philosophy

Do not assume more complexity improves accuracy.

The system should prove that each new layer adds value.

Compare:

```text
Quant-only model
vs
Quant + historical similarity
vs
Quant + OpenAI
vs
Quant + historical + OpenAI
vs
Polymarket market probability
```

OpenAI may help, may only help during news events, or may hurt in quiet markets.

The system should record enough detail to learn which components actually improve predictions.

---

## 20. Storage / Hardware Constraints

The user's Mac has roughly 100 GB free storage available at the time of planning.

Therefore V1 should avoid storing unlimited raw order-book history.

Recommended approach:

- Store derived features permanently.
- Store market/session summaries permanently.
- Store predictions and outcomes permanently.
- Store raw high-frequency data only for short retention if needed.
- Use compression where practical.
- Avoid large local LLMs if memory pressure becomes a concern; use OpenAI API instead.

---

## 21. Initial Technology Decisions

### Backend

- Python
- FastAPI

### Database / Memory

- SQLite
- SQLite FTS5
- Relationships table for traversal

### Machine Learning

- XGBoost first
- LightGBM optional
- PyTorch later for sequence/order-book models

### AI

- OpenAI API using existing credit
- Local Llama/Ollama can be tested later as a fallback or cost-saving option

### Frontend

- Next.js
- React
- TradingView Lightweight Charts

### Streaming

- Native exchange WebSockets directly in Python for V1
- No Redpanda/Kafka initially

---

## 22. Important Design Rules

1. Do not hard-code a Polymarket event URL.
2. Automatically discover the live BTC 15-minute market.
3. Automatically roll forward at each 15-minute boundary.
4. Support joining a market already in progress.
5. Prefer APIs/WebSockets over scraping.
6. Scraping is fallback only.
7. Do not send raw market streams to OpenAI.
8. Use deterministic Python code for calculations.
9. Use ML for numerical probability estimation.
10. Use OpenAI mainly for unstructured intelligence and explanation.
11. Store every prediction and final outcome.
12. Track which specialist model produced which signal.
13. Compare our model to Polymarket's implied probability.
14. Keep V1 lightweight and local-first.
15. Add complexity only after proving it adds predictive value.
16. Do not implement automated trading in the first version.

---

## 23. Definition of a Successful First Version

V1 is successful if it can reliably:

1. Start at any time.
2. Find the current live Polymarket BTC 15-minute market.
3. Determine the Price to Beat.
4. Determine how much time remains.
5. Backfill recent BTC context.
6. Stream live BTC market data.
7. Calculate live features.
8. Produce Up/Down probabilities every few seconds.
9. Show the reason/signals behind the forecast.
10. Store every prediction.
11. Detect the final market result.
12. Automatically move to the next live 15-minute market.
13. Compare predictions against actual results over time.
14. Evaluate whether OpenAI improves the model.

