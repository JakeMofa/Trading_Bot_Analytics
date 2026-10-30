# Tradebot — Historical Progress / Checkpoint

Source: `BTC Forecasting Dashboard.pdf` (1,590 pages, exported October 30, 2026). Page references are PDF page numbers. These notes summarize discussions, not independently verified live production state. Current repo files and runtime observations take precedence.

## Roadmap sequence from the conversation
- Phase 1.5 production platform/dashboard — **reported complete**.
- Phase 1.75 cloud lifecycle, archives, retention and production stability — **in progress**.
- Phase 2 Coinbase trades and Level-2 order book — **not started**.
- Phase 3 `microstructure_v1` — **not started**.
- Later specialized AI, historical similarity, evaluation and meta-model — planning/research, not completion claims. (pp. 1500–1514)

## I7 — last detailed checkpoint in this PDF
**Reported accomplishments:** SSH restored; travel /32 access model; temporary AWS resources cleaned; production instance `tradebot-analytics-01` maintained; storage guard changed temporarily from 3,584 to 4,096 MiB; collector restored; Coinbase, Polymarket and LiveState resumed. (pp. 1470–1485)

**Reported blocker:** recurring feature computation causes approximately 83-second collector/API stalls. Diagnose feature job / CPU / SQLite locking / event-loop blocking, make the smallest fix, test, then verify no stalls. I7 **not yet closed** in the cited checkpoint; I8 follows I7. (pp. 1470–1484)

## Retention R0–R17 board (as reported)
| Step | State | Description |
|---|---|---|
| R0–R4 | PASS | code correctness; archive/candidate safeguards; production baseline; qualification DB |
| R5–R6 | STOP | retention performance and collector coexistence |
| R7–R17 | PENDING | recovery point, first production retention, DB checks, live-engine health, restart/recovery, PR/deployment, recurring retention, multi-cycle proof, storage stability, permanent guard, completion |

Production deletion must not proceed until safety and performance gates pass. (pp. 1491–1505)

## Reported data inventory (historical, not live)
A checkpoint cited ~1,164 markets, 6,776 feature snapshots, 6,745 predictions, 198,243 Polymarket observations, 1,168,729 Coinbase stream events, 48,812 candles, 28 news events and 274 verified raw archives. Figures may have changed. (pp. 1490–1492 and earlier discussion)

## Deployment workflow described
Retention branch `codex/phase1-75-retention-enable` -> CI -> PR -> `codex/lightsail-deployment` -> CI -> controlled CD -> smoke checks; do not target `main` for that deployment. Treat branch names as historical until checked in Git. (p. 1521)

## Required next verification
Read actual repo plan and code, inspect Git status, confirm VM/live services and DB/WAL/disk/memory metrics, assess stalls, and reconcile what has been fixed since the PDF was exported. **Never infer current operational health solely from this file.**
