# Trial structured synchronization, offline candidate

Source-only, based on qualified PP22 source `0c86b47`. No live operation,
release/profile/environment change, acknowledgement, collector action, cloud
DDL or grant was performed. The transport's new `sync_barriers=True` constructor
option defaults OFF and accepts only the one exact trial origin. No worker or
host control selects it. It is not a recovery deployment or a PP throughput claim.

## What changes

The 50-row importer currently waits separately for receipt INSERT batches,
revision INSERT/read batches and the generation checkpoint. In the opt-in path,
the same physical INSERTs (at most 25 rows each), bounded revision SELECT and
checkpoint UPDATE share one pipeline synchronization. Every revision still
passes canonical encoding, origin/generation/schema and exact receipt/hash
validation. Its full canonical page must equal the supplied page. Validation
runs before transaction commit; failures roll back the already queued checkpoint,
receipts, revisions and projections together.

Authenticated readback first pipelines deadline settings and server identity,
then checks the identity before scoped data reads. Independent checkpoint,
receipt, bounded revision and projection SELECTs then share a synchronization.
All original receipt fields, checkpoint coverage/hash, canonical bytes and exact
current projections remain checked before return. The local worker still ACKs
only after successful fresh authenticated readback. There is no hash shortcut,
latest-state substitution, implicit retry or cross-operation snapshot cache.

The opt-in import/read page is at most 50 rows / 256 KiB. The existing four-second
per-operation deadline, transaction timeout, 20-second worker cycle and 10,000
pending cap remain. Legacy/default calls and retained/cold readback semantics
stay on their existing paths. Session reuse is supplied independently by the
caller; this option does not introduce one or enable runtime reuse.

## Exact checks and ambiguity

Seven owned native PostgreSQL 17 tests pass with the actual trial SQL writer/RLS
policy. They cover rich FK-ordered 50-row import/read/replay; a genuinely committed
import followed by a lost/late confirmation with no local ACK; full-page replay
and ACK; rejection of an unsafe first-25 projection read; deferred-validation
rollback of projections/receipts/envelopes/checkpoint; corrupt checkpoint,
receipt, missing receipt/revision, noncanonical/oversized envelope, current
projection and server role; explicit scope/page/deadline rejection; and retained
A readback authenticating a later B revision while returning original A values.

The surrounding 16 existing native transport tests also passed across two runs.
The first run lacked the reader DSN for its retained-audit case; supplying that
fixture's restricted reader DSN made that case pass. Existing canonical,
envelope and receipt unit regressions pass. All databases are owned disposable
Unix-socket fixtures, with no externally supplied or hosted DSN.

## Paired generated benchmark

[Exact samples and source digest](evidence/sync-barriers-generated-2026-11-19.json)
compare the pinned original implementation with the candidate, alternating arm
order. Each arm has four samples per delay, the same 50 records / 67,991 canonical
bytes, warm physical connection and real restricted-role PostgreSQL transactions.
The mix includes candles, repeated mutable prices, a market, protected evidence,
features, predictions and explicit input edges. Both operations retain their
four-second cap; all 24 put/read sets passed. The cycle/ACK path was not timed.

| Injected wait per synchronization | Original median put + read | Candidate median put + read | Candidate observed maximum |
| --- | --- | --- | --- |
| 0 ms | 0.0749 s | 0.0755 s | 0.0791 s |
| 100 ms | 2.7435 s | 1.6907 s | 1.7028 s |
| 200 ms | 5.2574 s | 3.1887 s | 3.2028 s |

Observed synchronization counts fall from 17 to 11 on import and 8 to 4 on
readback. There is **no measured CPU improvement** in the zero-delay case.
The injected waits are sensitivity inputs used in the repository's existing
benchmark style, not measurements of PP network latency. This is not TLS,
Supavisor, a quarter-CPU container or live concurrency. Four samples do not
establish a production percentile.

At 200 ms, the generated remote stages alone yield 15.68 rows/s. That leaves
little room above the observed approximately 14 incoming rows/s once local
selection/ACK, CPU contention, connection validation and real network variance
are included. The result justifies a separately reviewed matched PP comparison;
it does not establish that the candidate can keep up. Larger real pages or
server-side work may erase the gain. Preserve all HOLD/deadline/cap behavior.

Reproduce without a hosted DSN:

```sh
python -m unittest discover -s backend/tests -p test_sync_barriers_pg.py -v
python deploy/preprod/bench_sync_barriers.py --pairs 4 --output /tmp/sync-barriers.json
```

Any operational admission still needs exact CI/release/profile review, measured
headroom on the actual page mix and full post-ambiguity reconciliation. Neither
this candidate nor the previous PP22 fallback converts a failed live trial into
PASS or authorizes partition retirement.
