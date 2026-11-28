# Collection-preserving collector upgrades

Status: offline design, not an implemented or qualified deployment route.
The initial connection-budget adoption has a separate approved maintenance
exception. Ordinary same-profile API-only replacement already preserved the
collector; replacing the collector/profile itself still needs this capability.

## Required behavior

Keep vendor capture active while canonical database writers change. A short
PostgreSQL commit pause can be covered by durable buffering; this does not mean
every process remains running or that every upstream event is recoverable.
Keep the same origin and generation, preserve timestamps and provenance, and
make calculation inputs reproducible without pretending buffered data was
available to an earlier decision.

## Candidate protocol

1. Verify exact release, event codec, schema and role-budget compatibility.
   Introduce an explicit standby mode: current operator startup fences an
   existing writer, so launching a second ordinary operator is unsafe.
2. Ready the candidate vendor readers without canonical authority, database
   connections or live-display authority. The four old source connections plus
   four new ones and calculation sessions would exceed app8. Standby must use
   zero app/private-reader sessions until the previous producer closes them.
3. Continue capture into a bounded, checksummed, fsynced spool. Preserve source
   identity, immutable payload, original receipt time and ordering metadata.
   Abort before transfer if readiness, capacity or integrity cannot be proved;
   keep the old writer authoritative.
4. Drain the old canonical queue to a durable watermark, then close its four
   physical writer sessions while capture remains active. Verify actual close
   and returned admission tickets; cancellation alone is insufficient.
   Quiesce every old operator database factory, including transient writes and
   private reads, so background control tasks cannot reopen sessions. Retain
   vendor capture separately. Sequence any calculation-process replacement:
   old and new independent two-session budgets must never overlap.
5. Under the host transition lock, use a lifecycle transaction to compare the
   exact old UUID, epoch and generation, check explicit OFF and all normal
   guards, then transfer to a fresh UUID and incremented epoch. Existing writer
   row locks let in-flight transactions finish. The old finalizer may release
   only its own UUID and must not disable the successor.
6. Journal the transition before SQL mutation. After an ambiguous result,
   reconcile the actual database owner and durable checkpoint. Renew only that
   proven owner while source/controller/intent bindings transition; neither
   missing evidence nor a stale file authorizes a new writer.
7. Only after the old database consumers are quiesced and their physical
   sessions have closed, open the candidate's qualified connection budgets
   and replay its buffered
   envelopes through existing identity/hash checks. Stable duplicates preserve
   the first committed evidence; conflicts remain errors. Late/out-of-order
   receipts need an explicit reconciliation policy, not timestamp-only drops.
8. Assign buffered data canonical availability no earlier than promotion while
   retaining its original receipt time. Bind deterministic replay to saved
   input IDs. Generic history availability is not an exact commit timestamp.
9. Retire old capture only after each successor feed produces verified local
   records and the spool watermark clears. After transfer, rollback is another
   fenced handoff with a new UUID/epoch; it cannot reactivate the old lease.
   Preserve spools and partitions if recovery is unproved.

## Required race and failure tests

- Transfer during an in-flight write; stale writer and stale finalizer actions.
- Explicit OFF racing transfer. OFF must stop the current origin owner;
  targeting only the old UUID could otherwise leave the successor running.
- Crash before/after SQL commit and before/after controller/intent journal
  updates, including uncertain remote results and lost operator connections.
- Standby refusal, full spool, source disconnects, out-of-order receipts,
  conflicting immutable hashes, repeated replay and receipt/availability cutoffs.
- Physical role-budget overlap, cancellation and genuine connection close,
  including transient operator reads/writes, calculations and control-task
  attempts to reopen sessions after transfer.
- Rollback after the successor committed records, without database restore.
- Exact same-event capture, canonical commit, display and verified archive
  trace through the handoff, with source coverage gaps reported explicitly.

## Limits and authority

No existing `.7` bootstrap can safely adopt a parallel canonical operator.
This plan adds no live permit, SQL grant, deletion authority or production
change. Unbounded failures or unavailable upstream history prevent an absolute
no-loss guarantee. Qualify one bounded same-VM handoff before exposing it as
the default collector deployment path.

## Observed receipt-versus-persistence gap

During the November 28 `.11` lease expiry, the browser showed a Polymarket
book receipt at 06:43:15.200094 UTC after the database-clock lease expired at
06:43:15.166854. The last archived book receipt was 06:43:15.098181. A later
Robinhood display receipt also lacked matching final archived coverage. All
98,058 persisted envelopes were ACKed; this does not prove every received
quote was saved. A volatile writer queue cannot supply lossless abort or
handoff. Any future durable spool must recover exact identities/timestamps
under a fresh valid owner and show persistence status accurately.

[Observed stop and display evidence](evidence/benchmark-budget-stop-observability-2026-11-28.json)
records the incident separately from the `.13` recovery checkpoint in the
[master plan](INTELLIGENCE_REBUILD_PLAN.md#november-28-2026--heartbeat-recovery-qualification).
