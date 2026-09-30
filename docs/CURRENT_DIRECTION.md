# Current project direction

Recorded September 29, 2026.

Status: implementation authorized by the user on September 29, 2026. Begin with read-only collection and SQLite. Buying/selling and paid AI calls remain deferred.

## Latest user clarification

- The eventual product is a Polymarket trading bot. The user subsequently clarified that buy/sell execution is deferred; the current scope is monitoring, analysis, and forecasting.
- Support both BTC 15-minute and BTC 1-hour markets.
- The Polymarket market link changes when the user clicks Go Live. Discovery and rollover must follow the active market for the selected duration rather than relying on one fixed URL.
- The handoff bundle README, summary, plan, raw conversation, and all four screenshots have been reviewed. They show the 15-minute buy/sell UI, a completed interval, and the next live interval. The transcript identifies polymarket.us. Live API fields and settlement rules remain unverified.

## Reference documents

The two supplied Markdown documents are preserved unchanged in this directory as historical planning references. Their 15-minute-only scope and prohibition on automated trading in V1 reflect the earlier plan. The latest user direction adds the trading-bot goal and the 1-hour duration; the implementation plan has not yet been revised to reconcile these changes.

## Still to define before building

- Exact Polymarket venue and market links shown in the screenshots.
- Whether buy/sell execution will be manual, automatic, or selectable.
- Entry and exit rules, position sizing, order handling, and execution limits.
- How the 15-minute and 1-hour markets will be selected or operated together.

The references alone do not authorize actions. The subsequent direct user request authorizes implementation of the read-only collector; account changes and orders remain out of scope.

## Complete architecture reference

BTC_Intelligence_Complete_Architecture.txt was read and preserved unchanged. It elaborates ingestion, session management, rolling calculations, quantitative history, specialist models, OpenAI analysis, SQLite/FTS5/relationship memory, dashboard, and evaluation. Treat it as planning context, not authorization to build.

Current clarifications still apply: support both 15-minute and 1-hour markets, defer execution; implementation of read-only collection is now authorized.

Planning adjustments to reconcile:
- Verify actual data endpoints and required fields before implementation.
- Persist market observations from the first collector milestone rather than delaying storage until Phase 11.
- Discover the next interval without waiting for the previous interval's confirmed settlement; reconcile pending outcomes separately.
- Keep exchange reference prices distinct from the official settlement source. Confirm equality and settlement rules per contract.
- Evaluate historical matches and models on later unseen markets; snapshots from one interval must not leak across training and evaluation.

## Current implementation focus

The user requested starting with 15-minute markets first. Default collection and pending-outcome reconciliation now target only 15-minute BTC markets. Hourly records remain preserved; 1-hour work is deferred.
