# Tradebot — Project Vision (reference, not roadmap)

Source: `BTC Forecasting Dashboard.pdf` (1,590 pages, exported October 30, 2026). Page references are PDF page numbers. These notes summarize discussions, not independently verified live production state. Current repo files and runtime observations take precedence.

## Goal
Build a continuously monitored Bitcoin forecasting and market-intelligence system, initially focused on BTC 15-minute UP/DOWN markets and Polymarket, with explainable probabilities, a live dashboard and rigorous historical evaluation. Extend toward 1-hour forecasts and a market-specialized intelligence layer, but avoid treating an LLM's verbal guess as a statistically validated signal. (pp. 1–15, 1570–1587)

## Intended product capabilities
- Real-time exchange price feeds, Polymarket markets, market state and continuously refreshed forecasts.
- Deterministic forecast models with measured accuracy, probability calibration and regime-aware evaluation.
- Historical replay and similarity analysis using only information available at prediction time (avoid look-ahead leakage).
- Later Coinbase trades, Level-2 order books, order-flow imbalance, liquidity and microstructure features.
- Specialized market AI for news/event interpretation, contextual research, evidence-based trade analysis, and reasoning grounded in live state and historical retrieval.
- Eventually a trained ensemble/meta-model combining deterministic forecasts, specialized AI, Polymarket probabilities and historical performance; do not naively average signals.

## Essential quality criteria
Data correctness, reproducibility, timestamp integrity, no unsafe archival deletion, graceful degradation when cloud services are unavailable, prediction calibration, cost control and operational safety. Evaluate additional sources and model layers against simple baselines before expanding complexity. (pp. 10–15, 1581–1587)

## Scope reminder
This document captures the vision, **not** an authorization to enable AI trading, deploy infrastructure, or change the official execution roadmap.
