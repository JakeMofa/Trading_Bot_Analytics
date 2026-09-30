# BTC Intelligence Project — Implementation Plan

## Objective

Build the project incrementally so that each phase is testable before adding more complexity.

The first target is a reliable local application that monitors the live Polymarket US BTC Up/Down 15-minute market and produces continuously updated Up/Down probabilities.

Do **not** build the entire architecture at once.

---

# Phase 0 — Repository and Project Skeleton

## Goal

Create a clean local project with backend, frontend, database, configuration, and tests.

## Stack

- Python
- FastAPI
- SQLite
- SQLite FTS5
- XGBoost
- Next.js / React / TypeScript
- TradingView Lightweight Charts
- OpenAI API integration stub

## Tasks

- Create repo structure.
- Add `AGENTS.md` for Codex instructions.
- Add `.env.example`.
- Add `.gitignore`.
- Add backend Python environment.
- Add frontend Next.js project.
- Add a basic FastAPI health endpoint.
- Add SQLite initialization.
- Add test framework.

## Acceptance Criteria

- Backend starts locally.
- Frontend starts locally.
- Frontend can call backend health endpoint.
- SQLite database file is created.
- API keys are loaded only from environment variables.

---

# Phase 1 — Polymarket Live Market Discovery

## Goal

Always know which Polymarket US BTC 15-minute market is currently live.

## Tasks

- Research the official Polymarket US market/reference endpoints.
- Identify how active BTC 15-minute markets are represented.
- Implement a `PolymarketMarketDiscoveryService`.
- Never hard-code event URLs.
- Determine:
  - market ID
  - market URL/slug
  - start time
  - end time
  - Up/Down contract identifiers if available
- Add a fallback strategy if the API does not expose enough metadata.

## Acceptance Criteria

At any time, the app can print something like:

```text
Market: BTC Up or Down — 15m
Start: 23:15 UTC
End:   23:30 UTC
Status: LIVE
```

---

# Phase 2 — Price to Beat Detection

## Goal

Automatically capture the exact Price to Beat for the active market.

## Tasks

Try in this order:

1. Official Polymarket structured API/metadata.
2. Public page structured data.
3. Terms-compliant HTML parsing as fallback.
4. Official benchmark calculation only if practical and necessary.

Store:

```text
market_id
price_to_beat
source
captured_at
```

## Acceptance Criteria

For the current active market, the application can display the exact Price to Beat shown by Polymarket and save it in SQLite.

---

# Phase 3 — Session Manager and Automatic “Go Live” Behavior

## Goal

Automatically follow the current live 15-minute market without user interaction.

## Tasks

Create a `SessionManager` that:

- Detects the active market on startup.
- Supports starting mid-session.
- Calculates elapsed time.
- Calculates seconds remaining.
- Detects expiration.
- Archives completed market metadata.
- Automatically discovers the next market.
- Captures the new Price to Beat.
- Resets session state.

## Acceptance Criteria

The application can run through multiple consecutive 15-minute markets without restarting or clicking Polymarket's Go to live button.

---

# Phase 4 — Live BTC Price Feeds

## Goal

Stream live BTC market data from multiple exchanges.

## First Sources

- Binance
- Coinbase
- Kraken

## Tasks

- Implement WebSocket clients.
- Normalize timestamps.
- Normalize symbols.
- Track connection health.
- Automatically reconnect.
- Maintain latest price per exchange.
- Calculate a simple composite/reference spot price.

## Acceptance Criteria

The backend continuously receives live BTC prices and updates without REST polling.

---

# Phase 5 — Recent-History Backfill

## Goal

When the app starts mid-session, immediately reconstruct recent market context.

## Backfill Windows

- 1 minute
- 5 minutes
- 15 minutes
- 1 hour
- 4 hours
- 24 hours
- optional 7 days

## Tasks

- Pull recent OHLCV/trade data from free exchange endpoints.
- Normalize into internal candle/trade structures.
- Mark data as backfilled vs live-collected.

## Acceptance Criteria

Starting the app halfway through a Polymarket market still gives the model usable recent context within seconds.

---

# Phase 6 — Core Calculation / Feature Engine

## Goal

Create deterministic Python calculations for live model features.

## Initial Features

### Target/time

- distance_to_target_usd
- distance_to_target_pct
- seconds_remaining
- fraction_of_interval_remaining

### Price/momentum

- return_10s
- return_30s
- return_1m
- return_5m
- return_15m
- return_1h
- velocity
- acceleration

### Volatility

- realized_volatility_30s
- realized_volatility_1m
- realized_volatility_5m
- range_1m
- range_5m

### Volume

- volume_30s
- volume_1m
- volume_5m
- volume_acceleration

## Acceptance Criteria

Features update continuously and can be logged/displayed for the active market.

---

# Phase 7 — Order Flow and Order Book

## Goal

Measure active buying/selling pressure and liquidity.

## Features

- market_buy_volume
- market_sell_volume
- buy_sell_ratio
- trade_delta
- trade_velocity
- bid_depth
- ask_depth
- bid_ask_imbalance
- spread
- microprice
- liquidity near current price
- depth changes

## Acceptance Criteria

The app can show a live structured signal such as:

```text
Order flow: bearish
Book imbalance: -0.31
Buy/sell ratio: 0.68
```

---

# Phase 8 — Derivatives Layer

## Goal

Add futures/perpetual intelligence.

## Source

Start with Deribit and/or exchange futures data that is publicly available.

## Features

- funding rate
- funding change
- open interest
- open-interest change
- liquidation activity
- perpetual basis
- futures basis if available

## Acceptance Criteria

Derivatives features update in real time or near real time and are stored with predictions.

---

# Phase 9 — SQLite Data Model and Persistent History

## Goal

Persist all important market, feature, prediction, and outcome information.

## Tables

### markets

```text
id
polymarket_market_id
slug
start_time
end_time
price_to_beat
final_price
result
created_at
```

### snapshots

```text
id
market_id
timestamp
btc_price
distance_to_target
seconds_remaining
momentum_10s
momentum_1m
momentum_5m
momentum_15m
momentum_1h
volatility_1m
volatility_5m
volume_1m
order_flow_30s
order_flow_1m
book_imbalance
funding
open_interest
open_interest_change
liquidations
polymarket_up_price
polymarket_down_price
```

### model_outputs

```text
id
market_id
timestamp
model_name
up_probability
down_probability
confidence
model_version
```

### predictions

```text
id
market_id
timestamp
up_probability
down_probability
confidence
final_direction
actual_result
is_correct
```

### events

```text
id
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
id
from_type
from_id
relation
to_type
to_id
```

## Acceptance Criteria

Restarting the app preserves historical markets and predictions.

---

# Phase 10 — Baseline Statistical / ML Model

## Goal

Create the first measurable Up/Down probability model.

## Initial Model

Start with:

- Logistic regression baseline
- XGBoost primary baseline

## Features

Use only structured numerical inputs.

## Target

```text
1 = final settlement >= Price to Beat
0 = final settlement < Price to Beat
```

## Training Strategy

- Time-based train/test split.
- No random leakage across future data.
- Rolling / walk-forward testing.
- Recent data should be weighted more heavily if supported by testing.

## Acceptance Criteria

The model produces a probability, not just a hard label.

Example:

```text
UP   61%
DOWN 39%
```

---

# Phase 11 — Historical Similarity Model

## Goal

Use stored market states to find similar previous conditions.

## Candidate Methods

- K-nearest neighbors over normalized feature vectors
- XGBoost historical-state classifier
- Regime clustering

## Example Query

```text
Current state:
- $35 below target
- 5:30 remaining
- high volatility
- negative order flow
- falling OI

Find similar historical states and their outcomes.
```

## Output

```text
Similar cases: 312
UP outcomes: 103
DOWN outcomes: 209
Historical estimate: DOWN 67%
```

## Acceptance Criteria

Historical similarity contributes its own model output and is stored separately from the final meta-model.

---

# Phase 12 — OpenAI Intelligence Layer

## Goal

Test whether OpenAI adds measurable value.

## Responsibilities

OpenAI should analyze:

- News events
- Macro events
- Unusual contradictions among model signals
- Market context summaries
- Explanations

Do not send raw market streams.

## Input

Compact structured JSON plus only a few relevant retrieved historical/event records.

## Output

Strict structured JSON:

```json
{
  "direction": "down",
  "up_probability": 0.32,
  "down_probability": 0.68,
  "confidence": 0.73,
  "strongest_signals": [
    "negative order flow",
    "below target with limited time"
  ],
  "contradictions": [
    "one-hour trend remains positive"
  ],
  "risk_flags": [
    "short-liquidation pressure may reverse movement"
  ]
}
```

## Acceptance Criteria

OpenAI results are saved separately so later testing can determine whether the AI improves or harms forecasts.

---

# Phase 13 — Meta-Model / Ensemble

## Goal

Combine specialist model outputs into one final probability.

## Inputs

- Target/time model output
- Price/momentum model output
- Order-flow model output
- Order-book model output
- Derivatives model output
- Historical model output
- OpenAI/event output when available
- Polymarket implied probability
- Regime features

## Model

Start with XGBoost or LightGBM.

Do not simply average probabilities.

## Acceptance Criteria

Produce one final forecast:

```text
UP         34%
DOWN       66%
Confidence 72%
```

Store the component model outputs used to generate it.

---

# Phase 14 — Dashboard

## Goal

Build the live interface.

## Main Components

### Live chart

- BTC price
- Price to Beat horizontal line
- Session start/end markers

### Current session card

```text
Market: 23:15–23:30 UTC
Price to Beat: $83,807.85
BTC Now:       $83,755.99
Distance:      -$51.86
Time left:      09:50
```

### Forecast card

```text
OUR MODEL
UP   34%
DOWN 66%
Confidence 72%
```

### Polymarket card

```text
POLYMARKET
UP   30%
DOWN 70%
```

### Signal panel

```text
Target/time             Bearish
Momentum                Bearish
Order flow              Bearish
Order book              Neutral
Derivatives             Slight bearish
Historical similarity   Bearish
News                    Neutral
```

### Prediction-change timeline

```text
18:31  54% -> 61% UP
Reason: aggressive spot buying increased
```

## Acceptance Criteria

The UI updates live without refreshing the page.

---

# Phase 15 — Evaluation Engine

## Goal

Measure whether the system is actually useful.

## Metrics

- Accuracy
- Brier score
- Calibration
- Accuracy by confidence bucket
- Accuracy by time remaining
- Accuracy by volatility regime
- Accuracy by market hour/day
- Model-by-model performance
- OpenAI vs no-OpenAI performance
- Historical-model contribution
- Comparison against Polymarket implied probabilities

## Example Reports

```text
All predictions: 55.4% correct
Confidence >60%: 59.1% correct
Confidence >70%: 64.2% correct
Confidence >80%: 68.3% correct
```

These numbers are placeholders only until measured.

## Acceptance Criteria

The dashboard/report can objectively show whether the model is improving.

---

# Phase 16 — Lightweight Traversal and Text Memory

## Goal

Add semantic memory without adding a heavy graph database.

## FTS5

Index:

- event headlines
- event summaries
- model explanations
- prediction failure notes
- session summaries

## Relationships Table

Examples:

```text
prediction:928 -> USED_SIGNAL -> orderflow:1842
prediction:928 -> USED_EVENT -> event:392
prediction:928 -> BELONGS_TO -> market:518
prediction:928 -> SIMILAR_TO -> prediction:724
```

Use SQLite recursive CTEs for lightweight traversal.

## Acceptance Criteria

The system can answer internal queries such as:

> Which events were associated with high-confidence wrong predictions during high-volatility markets?

---

# Phase 17 — Optional Embeddings / Semantic Similarity

## Goal

Only add semantic vectors if FTS5 and structured historical matching are insufficient.

## Options

- OpenAI embeddings stored locally
- PostgreSQL + pgvector later

Do not add a separate vector database until there is a demonstrated need.

---

# Phase 18 — Optional Advanced Models

Only after the baseline system is stable and evaluated.

Possible additions:

- PyTorch sequence models
- LSTM
- Temporal transformer
- Deep order-book models
- Regime classifier
- Model stacking
- Dynamic model weighting

Each new model must be benchmarked against the simpler baseline.

---

# Phase 19 — Optional Infrastructure Upgrade

Only if local SQLite architecture becomes insufficient.

Possible future upgrades:

- PostgreSQL
- pgvector
- Redis
- ClickHouse
- Redpanda/Kafka
- Neo4j
- Cloud deployment
- Kubernetes

Do not introduce these in V1 unless required by actual scale.

---

# Data Retention Plan

Given limited local storage, use controlled retention.

## Keep permanently

- Markets
- Price to Beat
- Final outcomes
- Derived features
- Predictions
- Model outputs
- News/event summaries
- Evaluation results

## Keep temporarily

- Raw order-book messages
- High-frequency raw trades if storage grows quickly

## Suggested initial retention

- Raw order book: short retention
- Raw trades: limited retention
- Derived feature snapshots: long-term
- 15-minute market summaries: permanent

---

# OpenAI Cost-Control Plan

Use OpenAI only when useful.

Do not call the API for every market tick.

Possible strategy:

```text
Raw market data
    ↓
Python filters/calculates
    ↓
Only meaningful compact state
    ↓
OpenAI
```

For news:

```text
Many incoming headlines
    ↓
Free local filtering
    ↓
Deduplication
    ↓
Only important BTC-relevant items
    ↓
OpenAI analysis
```

Record token usage and API cost for later evaluation.

---

# Development Rules for Codex

1. Read the summary/specification before coding.
2. Implement one phase at a time.
3. Do not implement future phases prematurely.
4. Add tests for session rollover and mid-session startup.
5. Keep data-source adapters isolated from model code.
6. Keep storage behind repository/service interfaces.
7. Never commit API keys.
8. Prefer official APIs and WebSockets.
9. Scraping is fallback only.
10. Do not implement automated trading in V1.
11. Every prediction must be reproducible from stored features/model version.
12. Every completed market must be linked to its predictions and final result.
13. Every AI call must be saved separately from numerical model output.
14. Keep the system local-first and low-cost.
15. Add complexity only when measured results justify it.

---

# First Coding Milestone

The first working milestone should do only this:

```text
Start application
    ↓
Find current live BTC 15m Polymarket market
    ↓
Get Price to Beat
    ↓
Show start/end time
    ↓
Show timer
    ↓
Stream live BTC price
    ↓
Show distance from target
    ↓
Store session in SQLite
    ↓
At expiration automatically switch to next market
```

No AI prediction is needed for the first milestone.

Once this foundation is reliable, build the feature engine and baseline model.

---

# Second Coding Milestone

Add:

```text
recent backfill
momentum
volatility
volume
basic order flow
baseline logistic/XGBoost model
probability output
prediction storage
```

---

# Third Coding Milestone

Add:

```text
order book
derivatives
historical similarity
Polymarket probability comparison
```

---

# Fourth Coding Milestone

Add:

```text
OpenAI intelligence
news/event interpretation
meta-model
explanation layer
```

---

# Final V1 Success Criteria

V1 should be able to run unattended and repeatedly do the following:

1. Discover the current BTC 15-minute Polymarket market.
2. Join it even if already in progress.
3. Capture the Price to Beat.
4. Backfill recent context.
5. Stream live market data.
6. Calculate features.
7. Produce probability forecasts.
8. Store every forecast.
9. Track specialist model outputs.
10. Show reasons/signals.
11. Detect the final result.
12. Automatically roll to the next market.
13. Evaluate forecast accuracy and calibration over time.
14. Measure whether OpenAI improves forecasting quality.

