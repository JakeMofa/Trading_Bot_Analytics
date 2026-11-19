# PP readback: measured recommendation and bounded next probe

November 19, 2026. Recommendations/evidence only. PR #164 merged at `a4e39d1`;
this followup changes documentation only. The release chat owns optimization
implementation, hosted permissions, merge integration and all PP/prod operations.

## Recommendation

Qualify **binary results for the narrow revision-envelope SELECT first**, then
measure its full structured readback on PP. The native experiment demonstrates
fewer protocol bytes, not a PP speedup. Keep the VM-local live prediction path,
all existing verification checks and the four-second per-operation deadline.
Do not add indexes, a warehouse, RPC privileges or a bigger timeout from this
baseline alone. Reuse is a separate candidate: #159's flag affects the recurring
worker; it is not wired into `pp_retirement_verify`.

## Demonstrated versus unproven

| Evidence | Demonstrated | Limit |
|---|---|---|
| Release-supplied PP18 rich 500-row pages | 2.499–3.393 seconds per page | Not our own measurement or a 75-page run |
| Read-only hosted baseline, 08:00–08:05 UTC | Retained tail 500 IDs 21152–21651 contain 743,038 envelope bytes. EXPLAIN estimates 500 rows and uses both existing primary-key indexes. | No ANALYZE; a different scope from the operator's rich-page sample. Connector role only: SET ROLE to the runtime role was denied; no grant changed. |
| Hosted normalized-query cumulative statistics | Two matching PP-role query IDs: 686 calls/1.801 ms mean and 427 calls/0.422 ms mean, zero recorded shared/temp block reads | Mixed page sizes since the October 14 reset. These are individual SQL execution statistics, not setup/network/full-transaction timings. |
| Generated native PG17.2/psycopg 3.2.13 | 36 exact 500-row reads under four seconds; 12 negative checks; two exact `74a850b` codec probes passed. Narrow binary results cut revision server-to-client stream bytes 48.0%, and full structured readback about 32.0%. | Warm/analyzed loopback fixture, no TLS/Supavisor/live load. Local full-path timings overlapped; no proven PP elapsed improvement. |

The native fixture has 499 rich candles and one mutable price, 500 distinct
projection keys, with a separate one-record B-replacement case. Both the candidate
CASE query and the older deployed query decoded exact canonical values, including
the old query's directly selected hash domains. This is pinned native codec proof,
not live server/pooler qualification. All selected result types need compatible
loaders; avoid a global binary setting. [Psycopg formats](https://www.psycopg.org/psycopg3/docs/basic/params.html#binary-parameters-and-results)

## Whole-work budget

For the supplied 75-page scenario, structured work extrapolates to
**187.425–254.475 seconds**. The slow endpoint already exceeds 240 seconds by
14.475 seconds before raw/local work; the approximate 212-second estimate leaves
28 seconds. These are arithmetic scenarios, not measured completion times.

Required average page time is `(240 − raw/local reserve) / page_count`:

| Assumed raw/local reserve | Maximum mean for 75 pages |
|---:|---:|
| 0 seconds | 3.2 seconds |
| 30 seconds | 2.8 seconds |
| 45 seconds | 2.6 seconds |

Actual raw authentication/GET/hash/decode, inventory/protected-reference checks,
reader drainage, opposite-slot evidence and local commit reserve remain unknown.
A successful four-second page does not prove whole-work fit. Preserve the seal
clock, overall deadline and HOLD behavior when complete verification cannot fit.

## Exact bounded followup for the release owner

After qualifying a narrow per-query candidate, choose one reviewed A manifest
with 500 IDs and canonical hashes. Outside the critical removal window, run
**four full `read_retirement_revisions` calls**, alternating text/binary twice,
each with a fresh physical connection, unchanged four-second cap and a
**25-second whole-probe deadline**, including startup/cleanup. Stop on any
identity/hash/order/size/checkpoint/projection mismatch, timeout or deadline;
no hidden retry, local ACK, cloud write, permit, rotation or deletion.

Record setup, transaction/setup queries, checkpoint, envelope receive/decode/hash,
latest-receipt and projection phases; original/replacement/projection bytes;
K distinct keys, G newer generations, replacement IDs/hashes and exact source/
image/driver/server identities. Keep protocol byte counts separate from interface
counters. B can advance: record and classify changing replacement work instead
of freezing it. Two samples per format cannot support percentiles or a latency
guarantee. A subsequent 2×2 cold/reused × text/binary comparison can isolate reuse
only after its separate wiring and transaction/credential lifecycle qualification.

The source currently performs six sequential setup/read statements, K projection
SELECTs in one pipeline, and two more queries per newer generation. That is
`6 + K + 2G` SQL statements, roughly `7 + 2G` application wait boundaries plus
BEGIN/COMMIT/setup; it is not a literal TCP round-trip count. Retain the fresh
repeatable-read read-only snapshot, exact original bytes, receipt hashes,
latest/checkpoint/order and current-projection checks.

[Native samples, codec checks and reproducible harness](COLD_READBACK_PERFORMANCE_2026-11-19.md) ·
[Read-only hosted plan/statistics evidence](evidence/hosted-readback-baseline-2026-11-19.json)
