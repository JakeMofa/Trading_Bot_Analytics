# BTC Intelligence project instructions

Read docs/CURRENT_DIRECTION.md and docs/STRATEGIC_PLAN.md before architectural changes.
Current authorization: implement read-only data collection and analysis for Polymarket US BTC 15-minute and 1-hour markets. User authorized implementation after earlier planning-only discussions. Buying/selling, account changes and paid AI calls remain deferred.
Use official US APIs; exchange data is a reference input, not official settlement. Preserve provenance, missing data and exact decimals. Do not add trading endpoints. Do not commit secrets or local databases. Validate session boundaries, delayed outcomes and storage integrity. Keep each milestone small and report unsupported fields honestly.
