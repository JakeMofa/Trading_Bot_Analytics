# PP23 reconnect repair and failed initial-A recovery

## Observed failure

PP23 source `f964c93` stopped at 2026-11-20 01:38:52.370522 UTC
(November 19, 7:38:52 p.m. CST) with `coinbase_stream.ws_closed_error`.
A remained unsealed with 18,930 raw records and 20,362 structured ACKs.
No B, raw archive, local deletion or completed 30-minute window was observed.
The exact historical retry-limit branch remains unknown because timing was off.

An exact-source offline reproduction persisted a tick before each of thirteen
separated connection failures, outside the rolling storm window, and still
exhausted the twelve-reconnect lifetime budget. This demonstrates a code defect;
it does not retroactively establish which limit ended the live run.

## Candidate behavior

- Retry only the existing four transient Coinbase stream diagnostic codes.
- Replace fatal lifetime exhaustion and burst exhaustion with interruptible
  backoff (1, 2, 4, 8, 16, 30 seconds) and no more than three actual reconnect
  starts in a rolling 60 seconds. No extra collector session is started.
- Preserve the outer finite session deadline, durable lease, explicit OFF,
  ownership fencing and fatal storage, integrity, authentication and payload errors.
- Reset backoff only after newly acknowledged, strictly advancing, actually
  fresh source data. Replayed, stale and future data do not reset it.
- Enable existing parser/dequeue/save timing only in the exact active trial
  operator profile. Summaries are bounded to 4,096 JSON bytes, emitted every
  five seconds or on reconnect/cooldown/exit; no raw payload, prices or exception
  bodies are logged. Session counters distinguish rate-limit waits.

This is not a demonstrated cure for Coinbase source-age violations. The failed
run had 90 ON samples over 30 seconds, maximum 70.589 seconds. Separate offline
experiments distinguish receive buffering from pre-parser delivery delay.
The independent chat's local generated connection-reuse benchmark is a future
experiment, not a deployed optimization or evidence of the live cause.

## Preserve and archive failed initial A

`postgres.pp_failed_trial_drain` is default-off and bound to origin
`pp-live-pp-trial-20261119-02` and initial A
`41c82044-0fb8-4900-bea0-7c43ba079ff0`. It requires exact counts, source-bound
preparation, writer epoch, all PP collectors durably OFF, zero pending records,
and the actual attached child relation. It seals without creating a successor;
it does not drop anything or claim the original trial passed.

The 64,000 acknowledged-total admission limit is separate from the unchanged
10,000 pending limit. Raw catalog, cloud request, memory and operation-time
limits remain unchanged. Native generated qualification includes 20,362 real
acknowledged fixture revisions and complete 41-page independent readback within
64 MiB. Bad counts, source, partition metadata, pending records, an enabled
collector, incomplete readback and failed checkpoint preserve the data.

Run the exact reviewed maintenance helper only after its exact Linux CI passes.
Use the existing installed PP23 controller and credentials for failed-A archive
and independent audit, then leave the old live profile. Do not install the new
controller while expecting it to accept the old timing-disabled profile.
Preserve local A after audit; retirement requires its own evidence and gate.

## Release and continuation

1. Complete local regressions and exact-source Linux CI; review a small PR to preprod.
2. Archive and independently verify the retained failed initial A while OFF.
3. Leave the old trial profile; retain the raw partition and all older archives.
4. Qualify a fresh origin and release with the retry repair and diagnostics.
   Never reset/reuse the consumed trial02 admission or erase its failed evidence.
5. Run A → B → fresh A; both sealed partitions must independently verify and
   retire within 30 minutes while successor collection continues. Check historical
   retrieval after deletion, and report freshness separately.

Production's prior storage-held collector configuration and the temporary fwupd
pause were restored after durable PP OFF. No production migration, retirement,
resize or cache clearing occurred. Phase 1.75/I7 remain open.

## Local validation before exact Linux CI

- Full backend suite: 558 tests, 66 documented skips, PASS (58.446 seconds).
- Deployment controls: 257 tests, 14 documented skips, PASS (7.204 seconds).
- Failed-A native PostgreSQL suite: 7 tests, zero skips, PASS (16.446 seconds),
  including actual 20,362 acknowledged fixture records and partition-metadata
  fault injection without weakening the schema constraint.
- Independent reconnect/diagnostics review: 91 focused tests, PASS; no blockers.
- The first broad local run failed only because its disposable virtualenv lacked
  the already-pinned cryptography dependency. Installing that exact existing pin
  resolved it; the complete rerun above passed. No dependency-file change.

Exact-source Linux CI and runtime maintenance execution remain pending.

## Exact-source CI and harness follow-up

Candidate `5fb9fa3` passed exact push CI 44656678313, including all 182 Linux
application tests (160.301 seconds) and all seven restricted-role recovery cases.
The separate PR run 44656728101 timed out in the old combined 180-second
application phase; its partial output was lost, so no individual failing test
or assertion can be identified. That failed run remains failed.

The successor harness partitions the same discovered test identities: original
application tests retain their 180-second budget; the full-volume failed-trial
recovery suite gets a separate 90-second phase. The overall 600-second deadline
and resource caps are unchanged. Missing, skipped or empty phases fail. Timeout
output is redacted before truncation and reports termination/reaping status.
All seven recovery cases passed through the actual new child command in 12.96
seconds. The revised control suite passed 263 tests with 14 platform skips.
