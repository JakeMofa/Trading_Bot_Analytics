# I7-only release attempt — stopped before checkout

October 30, 2026. I7 remains OPEN; Phase 1.75 is unfinished. This report records a failed release gate, not production validation of the worker fix.

## Completed preparation

- Preserved the working checkout on `codex/phase1-75-retention-enable`; no new branch or Git worktree. Pre-existing edits to AGENTS.md and the master roadmap, plus unrelated untracked files, were preserved.
- Saved the historical memory pack and context index in documentation, commit `9876eb9`. Full conversation exports are local-only under `docs/reference/chat-history-local/`, ignored by Git. All six compact pack files were read; the full transcript reading remains unfinished. Failed history reviewers were not restarted; no Tradebot paid OpenAI calls were made.
- Exported the existing deployment base into a temporary test directory (no Git worktree) and applied only the four-file worker-containment patch from `b809efc`.
- I7-only validation: **159 backend tests, six deployment-control tests and compilation PASS**. The lower backend count reflects exclusion of the feature branch's retention changes; it is not the 182-test full-feature-branch suite.
- Prepared `d56b4a73ad6f1a10ba2bac928087cd5d85c6a42a` on the existing deployment branch. Only `streaming.py`, its two test files and the I7 diagnosis document differ from that branch's prior HEAD. Collector timestamp behavior, retention implementation, schema, dependencies and deployment helpers were not changed by the release.
- [Exact-revision CI passed](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41138048640).

## Controlled attempt and STOP

[Manual workflow 41138249460](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/41138249460) targeted the exact approved revision. Workflow validation and branch/SHA/CI checks passed. A checksum-verified official one-job runner was registered on the operator Mac using the existing private SSH path; no AWS resource or firewall change was made.

The root-owned deployment helper remained in preflight SQLite verification, before checkout or a new deployment record. A progress observation found that reader in `folio_wait_bit_common`, with about 611 MB physical reads at that observation. The original API process also continued its already-diagnosed synchronous scans. During 85 five-second samples, HTTP responsiveness remained intermittent and a successful recovery response exposed feature age above 331 seconds (prior recorded recovery sample about 163 seconds). Concurrent disk work is a concern; these samples do not individually time the helper's SQL or prove that all additional lag was caused by verification.

The attempt was cancelled rather than extending its budget or bypassing checks. After verifying the production SHA was still the old revision and no candidate checkout record existed, sent normal SIGTERM **only to this attempt's verification Python process, PID 9199**. Confirmed it exited. Application services were not signaled. GitHub records the workflow as `cancelled`; the runner's job reported failure during cancellation. The ephemeral runner unregistered automatically; GitHub runner inventory returned zero, and its task-created local directory was removed after `.runner` and `.credentials` removal was confirmed.

## Verified preserved runtime

- Production revision: `a7c098900f8310367fc262a1b837c369bb63dc56` — unchanged.
- API PID 2273, ensemble PID 849, lifecycle PID 843 — unchanged, active/running, zero automatic restarts.
- Observed process flags: OpenAI OFF, retention OFF, guard 4096 MiB; OpenAI credentials absent (boolean check only).
- No candidate deployment/rollback occurred. No application service restart, retention, schema/index change, VACUUM, WAL manipulation, SSH/firewall change, AWS resource creation or Phase 2 work occurred.
- The worker fix remains **undeployed**. Service-running status is not a sustained health PASS. The final bounded read-only observation is preserved separately and must not be replaced by an assumed recovery claim.
- After helper termination, 13 additional five-second samples through 17:38:13 America/Chicago still had two-second HTTP timeouts; recovery was not observed in that bounded window. API PID stayed 2273, OpenAI/retention OFF, guard 4096 MiB. Final DB 3,996,729,344 bytes, WAL 9,805,632 bytes, free disk 51,865,370,624 bytes. The unresolved original feature scan remains an availability problem; no healthy final-window claim is made.

## Remaining gate

**BLOCKER:** fresh full SQLite verification through the current live deployment preflight was not completed safely while the blocking production feature scans continued.

**OWNER:** controlled release/preflight verification path, separate from the already-prepared worker containment.

**STOP CONDITION:** worsening observed feature age and persistent HTTP timeouts during heavy verification; do not force release, repeat the same scan or weaken integrity/FK checks to obtain a deployment.

**NEXT:** review a bounded verification/release procedure that preserves complete structural/FK checks and rollback while protecting collection. Any controlled maintenance, revised helper or altered release procedure must be concrete and reviewed before use. Then deploy the I7-only revision through the approved path and validate several complete feature cycles, API/feed responsiveness, feature age, disk reads, collector coexistence and WAL behavior. Worker containment alone still does not shorten the historical scan. Retention R5/R6 remain STOP; Phase 2 remains deferred.

Local evidence: `/Users/jake/Documents/ChatGPT/TradebotAnalytics/evidence/phase175-baseline/i7-only-release-20261030/` (backend/deployment test logs, live/final monitor JSONL and final revision/service projection). Historical evidence remains in `i7-feature-stall/`.

## Prepared continuation — not executed

The bounded operator procedure is now implemented in
`deploy/lightsail/i7_maintenance.py`, with [the reviewable runbook](../../deploy/lightsail/I7_MAINTENANCE.md).
It defaults to plan-only, is not installed in the VM, and is not called by normal CD.
It is fixed to old runtime `a7c0989` and I7-only application revision `d56b4a7`.

Local validation: **26 deployment/maintenance tests PASS**, compilation and diff
checks PASS. Tests cover real immutable SQLite verification, foreign-key violations,
corrupt copies, alias/inode ownership, WAL preservation, child timeout/reaping,
restart-file configuration that inherited variables cannot mask, failed-check
non-deployment, partial-stop recovery and code rollback ordering. CI now runs all
deployment/maintenance tests in addition to the backend suite.

Proposed scope is 20 minutes of work plus five reserved for recovery, under a
separate supervised maintenance approval. Stop the monitor, find a responsive API
stop window, then stop the three SQLite-owning application services. Refuse
remaining DB owners/nonempty WAL; create and independently verify a root-private
consistent copy on the same VM; require full quick/FK checks before checkout.
Each SQL check has a maximum 420-second budget and an independently bounded child.
Restore old code/services on failure, preserving the live DB and any new data.
Never certify old-code API health from service-running status alone.

This requires a deliberate collection gap and one-time trusted-operator path,
with fresh exact-SHA CI verification for both the application and helper. It is
not a request to bypass the original checks or expand the forced deployment key.
No production upload, service stop, new live scan or release retry occurred while
preparing it. I7 remains OPEN and the worker fix remains undeployed.

## Superseded continuation

The user rejected the copy-based maintenance proposal above. It was never executed; its CLI is now disabled. The user authorized [the no-copy exact-release exception](../../deploy/lightsail/I7_SCOPED_RELEASE.md): bounded metadata readiness, explicitly outstanding full quick/FK audit, exact-CI application/helper, API-only restart, code rollback and separate containment/freshness validation. The historical STOP remains recorded; this is a new explicit policy decision, not a retroactive verification PASS.

## Later authorized release — successful, I7 still OPEN

The scoped no-copy exception subsequently released`d56b4a7` through Actions41159675569. The original protected helper is restored. [Production validation](I7_PRODUCTION_VALIDATION_2026-10-30.md) supersedes this report's earlier undeployed runtime checkpoint; the original failed attempt remains historical evidence. Sampled API containment passed, freshness/rollover did not. Full quick/FK audit remains explicitly outstanding.
