# Tradebot — Session Handoff (read this first)

Source: `BTC Forecasting Dashboard.pdf` (1,590 pages, exported October 30, 2026). Page references are PDF page numbers. These notes summarize discussions, not independently verified live production state. Current repo files and runtime observations take precedence.

## Identity / instruction
Work in the existing Trading_Bot_Analytics repository and current production workflow. This handoff is **context**, not a request to take autonomous infrastructure actions. Do not open a parallel roadmap or create a branch/session just to repeat I7 diagnostics.

## Authoritative order
1. Current repository code, deployed config and live observations for actual state.
2. `docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md` for the single execution roadmap.
3. Existing repo architecture docs and `BTC_Intelligence_Complete_Architecture.txt` for original vision.
4. This extracted reference pack and full conversation transcript for provenance and historical decisions.

## Context snapshot
- Goal: live 15-minute BTC/Polymarket probabilistic forecast dashboard; later intelligent market-analysis stack.
- Reported live path: Coinbase/Polymarket -> LiveState -> deterministic features/models -> API/dashboard; local SQLite hot/recovery; Supabase structured history + verified archives.
- Last detailed production checkpoint: **I7 in progress**, with recurring ~83-second feature-cycle stalls; collector restored; temporary 4,096 MiB DB+WAL guard.
- Retention: R0–R4 pass, R5–R6 stop, R7–R17 pending in the conversation.
- Phase 1.75 remains the gating phase before Phase 2 trades/L2 and Phase 3 microstructure.
- Keep Turso as a benchmark option, not a committed replacement; keep historical Supabase layer.

## Immediate safe workflow
1. Read `docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md` and relevant repo docs; report any conflict with these notes.
2. Inspect Git branch/status and existing tests; don't assume historical branch names are still in use.
3. Confirm current runtime health without making changes. Distinguish reported from observed facts.
4. If I7 stalls remain, isolate expensive feature-cycle work / CPU / SQLite contention / event-loop blocking; propose minimal tested fix within existing workflow.
5. Respect storage guard and retention safety gates. Seek approval before destructive/production-impacting operations.
6. Separately discuss specialized AI architecture and, **only after agreement**, revise the existing official roadmap rather than creating another roadmap file.

## Questions to resolve from repo/runtime
- Did I7 finish after PDF export? Is I8 closed?
- Are feature-cycle stalls still reproducible and what is their cause?
- What are current DB + WAL headroom, disk free, service uptime, collection lag and forecast health?
- What is the R5/R6 performance evidence, and can retention coexist with the collector safely?
- Which long-range AI layers are approved versus only discussed?

## Full evidence
See accompanying `BTC_Forecasting_Dashboard_Full_Transcript.md` and original PDF. Especially pp. 1470–1524, 1540–1590. Transcript ends with **planning first**, then updating the existing official roadmap, then resuming implementation.
