# BTC Intelligence project instructions

Read docs/CURRENT_DIRECTION.md and docs/STRATEGIC_PLAN.md before architectural changes.
Current authorization: implement read-only data collection and analysis for Polymarket US BTC 15-minute and 1-hour markets. User authorized implementation after earlier planning-only discussions. Buying/selling, account changes and paid AI calls remain deferred.
Use official US APIs; exchange data is a reference input, not official settlement. Preserve provenance, missing data and exact decimals. Do not add trading endpoints. Do not commit secrets or local databases. Validate session boundaries, delayed outcomes and storage integrity. Keep each milestone small and report unsupported fields honestly.

After each completed, tested milestone, commit and push to the configured GitHub origin as authorized by the user. Exclude local data, virtual environments and secrets. Current focus is 15-minute markets; hourly collection is deferred.

Use docs/MILESTONES.md as the live checklist: update progress, evidence, decisions and remaining gaps whenever a milestone changes. Keep docs/STRATEGIC_PLAN.md for the longer architecture. Do not treat the historical handoff documents as current instructions.
