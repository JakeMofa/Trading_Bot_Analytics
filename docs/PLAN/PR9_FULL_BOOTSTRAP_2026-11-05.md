# Selected recovery full application bootstrap — November 5

Heartbeat source8bb945a / exact Linux CI42126289598 PASS is preserved. The
historical1547a43 heartbeat failure remains FAIL; its individual host scheduling
and disk contributions cannot be recovered from its missing timeline.

## Implemented scope

Explicit three-file/hash-bound selected recovery capsule; immutable selected
bodies, exact manifest membership, conflict rejection, physical legacy binding,
transactional core proof, protected read fingerprints, sparse-ID reservation,
worker/history access and default production holds. No source database was copied.
Exact private manifest and qualification files are fsynced under ignored
`data/recovery-evidence/selected-2026-11-05-v1/`; committed sanitized attestation
is `evidence/selected-recovery-2026-11-05.json`. Selected JSONL was exported from
the already verified isolated stage and independently loaded by the capsule:
32,552,271 bytes, SHA256
`01f3ce94b62f3f91690b33e5aa4721de6ac6c22635d91b7c71dea7c0e689061c`.
No payloads, per-row identities, machine bindings or credentials are committed.

Complete bounded read-only legacy inventory found17 structured tables/189,576
rows,90,150,112 canonical array bytes; required metadata18268 +stream17924 +8
outcomes +1current-only price =>225777 audited inputs. The earlier150k and200k
estimates were insufficient. Explicit GENERATED qualification ceilings are now
250000 rows/256MiB logical bytes; defaults remain10000/60000 rows and128MiB.
Original2GiB workspace,512MiB Linux address space,170s work/180s total remain.
These are not production guard approvals.

Core layout3 (not feature/model version) adds a persisted logical admission
budget and atomic INSERT/UPDATE/DELETE quota triggers. Old layout2 activation
and writers hold. Fresh-B proposed core ceilings:250000 rows/256MiB logical,
512MiB physical including core WAL; raw ledger100000;64MiB/slot and2GiB new layout
remain separate. No automatic pruning or live production expansion. The finite
remaining logical allowance is NOT a qualified duration or continuous-operation
policy. Allocation sampler deduplicates inode length/blocks, includes all owned
regular FDs and unlinked TEMP, traverses Linux children of every thread, and
holds on incomplete visibility. Sampled peaks are not kernel quotas and do not
cover independent systemd service processes.

## Local bounded evidence

First full bootstrap FAIL32.629s: validator incorrectly assumed all source_time
fields were ISO text; actual historical_market_prices schema requires INTEGER
epoch seconds. Field-specific typed validation and malformed regressions fix this;
no timestamp normalization or original failure relabeling.

One changed full bootstrap PASS81.828s including preparation16.757s/cleanup.
225777 inputs/179671813 audit bytes; all17 structured tables compared exactly;
6755 metadata+6493 stream recovered;6776 snapshot/6745 prediction dependencies.
Core207852 rows/168200760 logical bytes; remaining42148 rows/100234696 bytes.
Constructor51.361s, restart6.084s, after-new-ack restart6.130s; new acknowledgement
229700 preserved. Legacy unchanged. Peak sampled allocation1079271424 bytes,
RSS178372608 bytes. macOS self-FD measurement only; Linux and complete real raw
volume NOT PROVEN by this run. See committed development JSON. Full source raw
volume is deliberately absent, not credited as free capacity.

Backend410 PASS/18 platform-or-privilege skips before final extra capsule test;
final capsule suite9 PASS. Controls120 PASS/3 privilege skips plus revised
fresh-B transition7 PASS, including selected recovery startup, B active/history,
pre/post-ack failures and forward reopen. Root Linux/exact export CI required.
Joint collector/scheduler/dashboard/SSE/prediction/rotation fixture now starts
with selected recovered inputs; it must pass Linux, no substitute component run.

## Remaining release gates and executable order (STOP)

1. Freeze successor exact source/export and require full exact Linux CI, including
   full-volume structured/fanout bootstrap, root descriptor/crash/joint proofs.
2. Keep legacy and all collector/ensemble/lifecycle writers stopped. Rehearse and
   review OS identity/permissions fence for all actual roles before any activation.
   Existing generated controller preserves2590s interruption/180s recovery/10s
   reaping and rejects production paths; old rollover scope/expiry cannot be reused.
3. Fresh post-quiescent identity is mandatory: normal last-close SQLite recovery
   may change main/WAL allocation, so the pre-stop capsule physical binding must
   HOLD. A reviewed fresh logical dependency proof/binding procedure is still
   required; never ignore a mismatch or invoke manual checkpoints.
4. Complete production legacy integrity verification budget is unresolved: prior
   1800s timeout cannot be silently replaced by targeted checks or rerun unchanged.
   Independent service TEMP/FD visibility, actual retained legacy/core/raw/WAL,
   recovery reserve and current physical headroom require complete accounting.
5. Production adapter allowlist/manual workflow still rejects this scope. Do not
   dispatch the old deployment command with a new SHA. After these gates, present
   one exact root/identity/hash/expiry/budget-bound command for separate approval.
6. Initial retirement OFF. After possible new acknowledgement, STOP all roles,
   preserve all files and recover forward using the identical capsule/core; never
   resume legacy writes or restore database contents. Generated control rehearsal
   proves committed-row preservation, not physical power-loss production proof.

Production capacity8GiB aggregate and any cutover/guard changes remain proposals.
No transfer, production repair, restart, migration, retirement or cloud write.
I7 fresh inputs/live rollover, cloud recovery, visibility, real-boundary/sustained
operation, historical raw replay and deferred knowledge/RAG remain OPEN; Redis
DEFERRED. PR9 remains DRAFT and Phase1.75 OPEN.
