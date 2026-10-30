# Context import reconciliation — October 30, 2026

This folder contains a historical reference pack, not a new roadmap or execution authorization. All six supplied Markdown files were read and preserved byte-for-byte. The official roadmap remains `docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md`. The supplied full Markdown/TXT transcripts are already text; no additional PDF conversion was necessary for this import.

## Current evidence takes precedence

- Repository verified as `/Users/jake/Documents/Trading_bot_Analytics`, branch `codex/phase1-75-retention-enable`, HEAD `b809efc`. Existing unrelated tracked/untracked changes were preserved. No branch or worktree was created.
- The pack's ~83-second I7 stall description is historical. Later October 30 logs bracket feature cycles of 131.050819 and 140.813514 seconds. The observed path is `rest_loop -> capture_features -> features._price`, with synchronous SQLite historical scan/sort page reads blocking the API event loop; the evidence does not show a waiting SQLite writer lock.
- `b809efc` prepares one awaited feature/forecast worker with its own SQLite connection. Recorded validation: 182 backend tests, six deployment controls, exact-commit CI. It is not deployed. It isolates the event loop but does not shorten the scan or establish feature freshness. I7 remains OPEN; the recovery sample's features were about 163 seconds old.
- Phase 1.75 remains unfinished. Retention R5/R6 remain STOP; R7–R17 remain pending. Retention and paid AI calls remain OFF in the latest recorded evidence. The temporary guard is 4096 MiB. These are recorded findings, not fresh production measurements.
- The master roadmap's opening branch/migration text is older than its dated progress entries. Do not treat it as a request to repeat migration. Phase 2 and hourly work remain deferred.

Evidence: `docs/PLAN/I7_FEATURE_STALL_2026-10-30.md` and `/Users/jake/Documents/ChatGPT/TradebotAnalytics/evidence/phase175-baseline/i7-feature-stall/RESULT.md`.

## Product requirements that the compact pack abbreviates

The original transcript, particularly PDF pages 579–606 and the final architecture discussion, describes:

- AI ON means continuous background following of the active market, using bounded compact snapshots/material-change triggers; it is not limited to a manual Analyze button. AI OFF stops new paid requests. In-flight handling, stale-result rejection and budget behavior still need a concrete design.
- AI must not block numerical feeds, state updates or forecasts. Detailed reasoning can remain in the background while the dashboard shows a fast, simple result.
- Explicit actual-position and entry information, previous thesis/reasoning, what changed, invalidation conditions and reassessment should inform future decision support. Never infer an actual filled position from a model suggestion.
- Direction probability and whether entry is attractive at the executable contract price after costs are separate outputs. Holding, exiting and switching need separate logic rather than noisy directional flips. Example thresholds and hold times in the chat are illustrations, not validated settings.
- LiveState, selected recent SQLite history, long-term Supabase history, timestamp-safe cases/news, model outputs and sourced trading knowledge are intended context sources. Book/document retrieval and the specialized position-aware analyst remain future work.

Current code has a limited opt-in advisor, experimental numerical ensemble, historical matching and retrospective news/case evidence links. Those do not establish the full future AI design, profitable edge or an automatically trained meta-model. `knowledge.py` explicitly distinguishes eligible retrospective links from evidence used by the frozen baseline.

## Review boundaries

All six supplied pack files were read completely. This import does **not** claim that the entire approximately 2 MB full transcript has now been read line by line. Earlier full-history subagent reviews stopped on usage-limit errors and must not be recorded as completed. The full transcript/parts ZIP remain in `/Users/jake/Downloads/BTC/` for targeted provenance checks. A browser print export does not guarantee original attachment contents, hidden tool outputs or alternate conversation branches.

No production connection, deployment, service action, retention, WAL operation, AWS/network change, paid model call, code change or official roadmap edit was performed for this import. This reference note adds no operational authorization.
