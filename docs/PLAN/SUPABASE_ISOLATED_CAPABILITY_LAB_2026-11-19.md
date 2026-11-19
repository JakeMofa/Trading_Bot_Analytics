# Supabase capability tests for PP and research

November 19, 2026. The browser audit inventoried the project and the 31-card
integration catalog. This lab exercises the features relevant to PP archive
reads, secondary jobs and deterministic history. It used generated data in an
unlinked local Supabase CLI 2.65.5 stack (Supabase PostgreSQL 17.6.1.059) and
separate disposable PostgreSQL 17.2 clusters, with fictional PP and production
identities. PP, production and the hosted Supabase project were outside the lab.

## What passed

| Feature | Isolated evidence | Application to PP |
| --- | --- | --- |
| Data API, REST RPC and RLS | A scoped invoker function returned the first 500 exact, ordered rows and the next 25. SQL returned the same IDs, decimal text and hashes. Anonymous execution and authenticated mutation were denied, the other identity only saw its own row, and a request for 501 returned no rows. | If phase measurements identify repeated network trips, compare one narrow archive lookup with today's verified PostgreSQL reader. Keep the existing receipt, revision, origin and byte-bound checks. |
| Native SQL RPC with archive query shape | Twelve matched 500-row reads returned identical canonical data for A after the current projection advanced to B. Eleven negative checks passed. With no added RTT, three statements took 40.87 ms versus 44.32 ms through the invoker function. With 50 ms of delay injected per statement, the comparison was 202.14 ms versus 101.92 ms. | A measured network-bound operation could benefit from two fewer sequential SQL requests. The isolated timing excludes HTTP and PP. |
| GraphQL | Both signed-in identities fetched their own row for the same generation. A value of `0.500000000000000001` arrived as an exact string. | An alternative for scoped structured reads. The test does not identify a new archive benefit over the existing reader. |
| Private Storage | The writer put a generated object. The owning reader got byte-identical content. The other tenant and anonymous role were denied, and the reader's upload was denied. | Matches the existing split between compressed raw archive files and SQL-queryable structured history. |
| Cron and Queues | pg_cron 1.6.4 ran two one-second observations and the job was unscheduled. PGMQ 1.5.1 hid an unacknowledged message until its visibility timeout, redelivered the same ID, then removed it from delivery after archive acknowledgement. | Suitable candidates for secondary freshness checks or retryable research jobs. Durable VM outbox acknowledgements remain the source for archive progress. |
| Edge Functions and webhook transport | A local Edge Function forwarded the caller's token to RPC and returned the same 500 rows. No token returned 401. The second identity retained its own scope. pg_net posted a generated request inside the local stack and got the expected exact response. | Useful for a small status summary or notification. No full verifier or retention operation was delegated to Edge. |
| pgvector and deterministic research | pgvector 0.8.0 returned the expected ordering for three generated vectors. A separate generated A/B fixture restored 3,240 gzip ticks from 36 markets. The point-in-time query excluded 36 late arrivals and matched an independent exact-decimal oracle for retained and restored features and nearest-five ranking. | Exact SQL inputs remain appropriate for deterministic forecasts. The vector test is basic functionality. An embedding-quality use case, such as searching notes, needs its own evaluation. |
| Realtime | Two signed-in clients subscribed to the same generated table and each received its own committed notice, with no cross-scope notice observed in the bounded test. | Can deliver dashboard archive status updates. The fixture did not compare it with the VM’s existing SSE or test reconnection recovery. |
| PostgreSQL telemetry | Local `pg_stat_statements` recorded the generated RPC statements. | Pair statement counters with VM archive phase timings and oldest pending age. A live Grafana scrape and combined dashboard have separate acceptance. |

## Product scope and decisions

Managed Pipelines and Analytics Buckets require hosted capabilities. The
parallel local proxy was PostgreSQL logical WAL decoding plus DuckDB/Parquet.
It observed 2,002 row changes and demonstrated replay duplication if the same
unconsumed batch is applied twice. After a mutable row was removed, 999 current
rows remained and all 1,000 immutable revision envelopes were still available.
The Parquet round trip preserved every canonical envelope and hash, numeric
precision, original decimal spelling and 200 missing outcomes. A PP-origin
and availability query returned 150 eligible rows with zero future labels.
This qualifies the local mechanism and export format. Managed delivery,
hosted destinations, and Iceberg catalog behavior remain unverified.
[Managed Pipelines requirements](https://supabase.com/docs/guides/database/replication/pipelines)
· [Analytics Buckets](https://supabase.com/docs/guides/storage/analytics/introduction)

The release accepted the hosted receipt/index lookup and the canonical
byte-reuse improvement. With those changes, the PP21 read-only diagnostic
verified 63 structured pages and 57 raw objects, with the first 500 rows at
2.163305 seconds and identical retained fingerprints. Keep the current reader
for that milestone. Match any future alternative against the same inputs,
scope, exact outputs, request count and elapsed budget. Qualify the active
50-row write configuration and any larger write batch separately.
[PP21 retained-A evidence](PP21_CANONICAL_RETAINED_AUDIT_2026-11-19.md)

Third-party catalog entries for unrelated workflows remain catalog research.
The lab adds no application dependency, credentials, paid service, lifecycle
authorization, or hosted configuration.
