# Tradebot context recovery

Updated October 30, 2026. This is a context index, **not another roadmap**.

## Read first

1. [Current project instructions](../AGENTS.md).
2. [Official master roadmap](PLAN/INTELLIGENCE_REBUILD_PLAN.md).
3. [Historical session handoff](reference/chat-memory-2026-10-30/SESSION_HANDOFF.md).
4. [Reconciliation with newer evidence](reference/chat-memory-2026-10-30/RECONCILIATION.md).
5. [I7 measured diagnosis and prepared fix](PLAN/I7_FEATURE_STALL_2026-10-30.md).

The handoff and memory pack summarize historical discussions. They do not authorize operations or establish fresh production health. Current user instructions and verified evidence take precedence.

## Compact memory pack — fully read

The six supplied files were extracted and read completely; originals are preserved byte-for-byte:

- [PROJECT_VISION.md](reference/chat-memory-2026-10-30/PROJECT_VISION.md): product goals and long-term vision.
- [ARCHITECTURE.md](reference/chat-memory-2026-10-30/ARCHITECTURE.md): LiveState, SQLite, Supabase, forecasts and future AI.
- [DECISIONS.md](reference/chat-memory-2026-10-30/DECISIONS.md): historical decisions and guardrails.
- [PROGRESS.md](reference/chat-memory-2026-10-30/PROGRESS.md): historical phase/checkpoint summary.
- [SESSION_HANDOFF.md](reference/chat-memory-2026-10-30/SESSION_HANDOFF.md): continuation context; not new authorization.
- [README.md](reference/chat-memory-2026-10-30/README.md): source and usage notes.

## Full conversation exports — local only

The supplied full Markdown/TXT transcripts already are text. Copies are stored under `docs/reference/chat-history-local/`, excluded from Git by that folder's `.gitignore`:

- `BTC_Forecasting_Dashboard_Full_Transcript.md`
- `BTC_Forecasting_Dashboard_Full_Transcript.txt`
- `BTC_Forecasting_Dashboard_Transcript_Parts.zip`
- `Tradebot_Project_Memory_Pack.zip`

Original supplied files: `/Users/jake/Downloads/BTC/`.
Earlier PDF extraction and verification: `/Users/jake/Documents/ChatGPT/TradebotAnalytics/evidence/chat-history/`.

The PDF export has 1,590 pages with extractable text on every page, from the original September 28 question to the final roadmap discussion. This establishes extraction coverage, **not completion of a line-by-line model review**. The full reading remains unfinished. Three section reviewers encountered usage-limit errors; they were not restarted. No Tradebot paid OpenAI calls were made for this review. The compact pack was subsequently read in full to recover context without repeatedly processing the whole transcript.

Use the compact pack and official roadmap for normal work; consult specific transcript sections for provenance. Original attachments, hidden tool outputs, collapsed content and alternate conversation branches are not guaranteed by a browser print export.

## Latest working direction

The user resumed implementation through the remaining Phase 1.75 gates and deferred the broader architecture discussion. Stop before starting Phase 2. Continue in the same repository, branch and main session.

- Current working branch at verification: `codex/phase1-75-retention-enable`.
- I7 remains OPEN. `b809efc` is the prepared, tested worker-containment fix; it has not been deployed.
- The old ~83-second estimate is superseded by recorded feature cycles of 131.05 and 140.81 seconds. Synchronous historical SQLite scan/sort page reads block the API event loop; no SQLite lock wait was observed in those samples.
- Containment moves work off the event loop; it does not shorten scans or prove fresh features.
- Retention qualification R5/R6 remains STOP; R7–R17 remain pending. Do not confuse historical PASS records with a fresh deletion preflight.
- Preserve all safety gates and unrelated local changes. Do not treat this index as authorization for retention, guard increases, infrastructure/network changes or Phase 2.

### Fresh read-only resume observations

October 30, 2026, approximately 17:21 America/Chicago: production Git revision `a7c098900f8310367fc262a1b837c369bb63dc56`; API/ensemble/lifecycle active, zero automatic restarts. Three concurrent two-second HTTP probes (`/health`, `/state/current`, `/system/status`) all timed out. This does not alone establish the operation causing that particular timeout.

DB 3,995,750,400 bytes; WAL 5,409,592 bytes; free disk 51,879,768,064 bytes. Headroom calculated against the **previously recorded** 4096 MiB guard: 293,807,304 bytes (~280.20 MiB). The guard configuration and OFF flags were not freshly verified by this timed-out HTTP sample. No deployment, restart or production modification occurred.

Next implementation work is I7 release-scope review and controlled production validation. The current feature branch also contains unqualified retention changes; do not deploy those merely to release the feature-worker fix. The official roadmap remains the sole execution checklist.

### Subsequent I7-only release attempt

See [the October 30 release attempt](PLAN/I7_RELEASE_ATTEMPT_2026-10-30.md). Isolated worker revision `d56b4a7` passed 159 backend tests, six deployment controls and exact-revision CI, excluding retention changes. Manual CD was cancelled in SQLite preflight before checkout when observed feature age exceeded 331 seconds and HTTP responsiveness remained poor. Only this attempt's verification reader was terminated; the ephemeral runner was removed. Production stayed on `a7c0989` with the same service PIDs, OFF flags and 4096 MiB guard. The worker fix is still undeployed; I7 remains OPEN. The next gate is a reviewed verification/release procedure that protects collection while preserving complete SQLite checks, not an automatic retry or a skipped integrity gate.

A [bounded maintenance procedure](../deploy/lightsail/I7_MAINTENANCE.md) and plan-only-by-default helper are now prepared locally, with 26 deployment/maintenance tests passing. This is a proposed operator-approved collection gap (20-minute work budget plus five-minute recovery reserve), not an executed maintenance window. It preserves complete SQLite verification, recovery copying, private binding, OFF flags and the unchanged guard. Production validation remains outstanding.

## Current continuation — user-authorized no-copy release

The copy-based maintenance proposal was rejected; its runbook is withdrawn and execute CLI disabled. Follow [the exact-release exception](../deploy/lightsail/I7_SCOPED_RELEASE.md) and the official roadmap. Full integrity/FK checks are explicitly outstanding; no historical PASS substitutes for current evidence. Production release and multi-cycle validation remain pending at preparation time.

## Latest verified result — worker deployed, I7 OPEN

Actions41159675569 released`d56b4a7`. More than20min and11 feature cycles showed zero failed sampled API probes; snapshots remained84–204s old and rollover was delayed. Original helper restored; one-use exception/runner cleaned up. Final follow-up streams live, but health degraded pending new-market features. See [production evidence](PLAN/I7_PRODUCTION_VALIDATION_2026-10-30.md) and the official roadmap. No new DB copy/snapshot or retention; full quick/FK audit outstanding.
