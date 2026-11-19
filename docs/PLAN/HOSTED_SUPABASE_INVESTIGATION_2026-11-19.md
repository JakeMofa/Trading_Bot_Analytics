# Hosted Supabase investigation

Research date: November 19, 2026 UTC. Base: preprod `1c753c6`.

Recommendation: complete the existing bounded structured cold-history reader,
using independently scoped read-only access to private immutable envelopes. Keep
VM RAM/local PostgreSQL responsible for live predictions. Supabase remains the
asynchronous history/archive tier. The user subsequently requested parallel
browser exploration, documentation review and a small local implementation;
those outputs accompany this report. The release chat owns deployment, live
collection, revision backfill and retirement. This research grants none of those
operations and changes no cloud state.

## Evidence and measured opportunities

| Evidence | Observation | Meaning and limit |
|---|---|---|
| [PR155](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/155), actual PP | Four paired reads of 50 acknowledged receipts: cold mean 632.35ms, reuse including initial setup 378.34ms, warm 288.20ms; each matched 18,000 canonical metadata bytes | Removing connection setup reduced total elapsed by 40.17%; this is receipt metadata, not full synchronization or immutable-payload throughput |
| [PR159](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/159), generated source candidate | 100 mixed records: cold 5.447s/18.36 ACK/s versus reuse 4.837s/20.67 ACK/s; four connections versus one | Default-off reuse preserves distinct durable transactions; SQL/setup waits were modeled. Open draft at review; no deployed full-sync claim |
| Master roadmap, actual PP15 | 5,243 ACKs/431.490s = 12.15/s versus observed arrivals 13.25/s | The 25-row service lacked measured catch-up headroom; source optimization alone does not prove concurrent capacity |
| Master roadmap, actual PP raw transport fixture | Ten objects/620,549 compressed bytes: upload 5.105s, first readback 8.612s, second 0.450s | Actual transport works at these fixture sizes. This is separate from sealing, complete replay and safe retirement |
| [PR157](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/157), dashboard audit | 2% CPU/55% memory overview; 395.83MB memory usage and 1.19GB commitment/severe warning in another window; gateway mean 311.48ms | Different windows, mixed traffic and missing panels prevent PP percentiles or a compute-sizing conclusion. Memory review is warranted; larger compute does not remove network setup |

At **06:52:08 UTC**, a bounded read-only SQL snapshot found 5,268 PP receipts,
400 revision payloads, 108,377,779 database bytes and zero replication slots.
All twelve history tables had RLS enabled, without FORCE RLS. A separate compact
table-list result reported zero revisions; exact SQL counts take precedence over
catalog estimates. The release workstream may have been adding payloads during
these observations: 400 does not establish backfill completion.

At **06:52:35 UTC**, role metadata showed one `tradebot%` login,
`tradebot_pp_history`, without superuser/BYPASSRLS. Its receipt/revision grants
were SELECT/INSERT with PP-origin policies. No separate structured reader role
was observed. All three buckets were private. Storage catalog metadata counted
980 `market-raw` objects and 339,576,344 bytes, across origins/fixtures, not a PP
archive checksum or restore proof. These admin-visible reads do not prove runtime
permissions. [Sanitized evidence](evidence/hosted-supabase-investigation-2026-11-19.json)

## Existing prototype and actual application gap

The prototype already existed as **uncommitted work** in the
`supabase-audit-docs` worktree on `codex/pp-cold-history-prototype-20261119`.
Its original files were inspected and left intact. Six independently rerun
offline tests passed. Its injected-source reader binds exact PP origin,
generation, market, entity and manifest hashes; pages 50 IDs/256KiB/four seconds;
and preserves original envelopes, decimal strings, NULL and provenance. It
honestly limits coverage to the supplied manifest.

On preprod, `/history/predictions` queries local PostgreSQL and
`/history/archive/{generation_id}` retrieves raw events. Existing
`HistoryV2PostgresTransport.read_revisions()` can verify immutable structured
payloads, but an application cold-query contract, trusted manifest selection and
reader-specific grants were missing. Raw replay and a successful receipt count
do not recover every saved prediction/feature/outcome revision. Reuse the
prototype rather than create another parallel cold-history design.

## Integration assessment

The [parallel integration matrix](SUPABASE_INTEGRATION_MATRIX_2026-11-19.md),
[initial browser walkthrough](SUPABASE_BROWSER_CAPABILITIES_2026-11-19.md) and
[completed 31-integration deep review](SUPABASE_DEEP_NAVIGATION_2026-11-19.md)
provide product-specific evidence and explicit coverage limits.

Private PostgreSQL gives the closest fit for receipt/envelope joins and exact
historical research. Client reuse is a separate decision from changing pooler
mode. Current [connection guidance](https://supabase.com/docs/guides/database/connecting-to-postgres)
recommends direct connections for persistent servers, or shared session pooling
for IPv4-only clients. Supavisor transaction mode needs prepared statements off.
Neither a new endpoint nor more parallel connections is justified by the small
read comparison alone.

A dedicated Data API schema or invoker database function could later offer a
bounded historical contract or fewer round trips. Keep `history_v2` unexposed:
[object grants and RLS](https://supabase.com/docs/guides/api/securing-your-api)
control separate boundaries, and functions require explicit EXECUTE review.
[Invoker functions](https://supabase.com/docs/guides/database/functions) preserve
caller privileges; they do not make SQL automatically read-only. Direct-SQL
writer policies do not authorize an ordinary Auth JWT. Use the existing FastAPI
boundary first, with separate reader authority and decimal-safe envelopes.

Keep authenticated Storage HTTP for exact raw objects. An S3 protocol switch has
no measured benefit here. Generated [S3 access keys](https://supabase.com/docs/guides/storage/s3/authentication)
bypass Storage RLS across buckets; JWT session-token access honors RLS. Neither
protocol makes an archive immutable against administrators.

**Documentation correction:** MCP `search_docs` returned an older FAQ claiming
private alpha and BigQuery-only Pipelines. The current official
[FAQ](https://supabase.com/docs/guides/database/replication/pipelines-faq), updated
November 16, lists public-alpha BigQuery, ClickHouse, DuckLake and Snowflake;
organization access varies. The earlier prototype report's restriction should
not guide future decisions. [Managed Pipelines](https://supabase.com/docs/guides/database/replication/pipelines)
runs in Frankfurt and adds usage/destination costs. It exports Postgres changes,
not our verified raw-object restore contract. Slot retention, resets, publication
scope and duplicate recovery add obligations. No pipeline was created.
[Open-source ETL](https://github.com/supabase/etl) is separately operable software,
not proof a managed destination is enabled in this project.

Cron, Queues, webhooks and Edge Functions may eventually handle hosted summaries,
notifications or scheduling. They cannot acknowledge a VM outbox or authorize
retirement without the same exact identity/readback contracts. Realtime does not
replace durable history. Vector/analytics buckets need a measured retrieval or
research workload; no semantic/vector need has been shown for exact market IDs.

## Prioritized next implementation and acceptance

The [local candidate](COLD_STRUCTURED_HISTORY_CANDIDATE_2026-11-19.md) now implements
**one read-only structured cold-history path**, building on the existing prototype.
It adds a SELECT-only source, reviewed server query registry and optional FastAPI
composition hook. The route is absent by default. It rejects the writer role,
effective table/column write grants and altered continuation scope; local live
endpoints remain independent. No deployed profile or cloud privilege changed.
The final full backend suite ran 362 tests: 316 passed, with 46 explicit
platform/fixture skips. Separate native PostgreSQL17 qualification ran 75 tests:
72 passed, three unrelated app-fixture skips, including six cold-source and 13
generic history/import/reuse tests. [Exact-source Linux CI](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44480584156)
passed at 5a44c7f. The SQL read uses separate 256KiB envelope and 256KiB receipt-text
budgets; fixed-row/protocol/TLS overhead is additional. Admission precedes
dispatch to an isolated cold worker, and cancellation preserves source cleanup.
Hosted identity, TLS/DSN factory qualification and manifest authenticity remain
prerequisites, not features proven by generated tests. Injected dependency I/O timeouts are required:
a post-call elapsed check cannot cancel arbitrary blocking Python code.

Before any release, qualify trusted manifest/catalog selection, exact hashes and
scope-bound continuation, missing/corrupt/oversize/outage behavior, admission
limits and original decimal/timestamp/NULL preservation. Compare canonical bytes
and phase latency on identical reviewed payloads; keep four-second limits.
Prove local live responses continue through cloud outage. Schema/grant application
and real payload tests require a separate release-owned gate.

PP qualification cannot authorize production. Use distinct PP/prod reader/writer
identities, volumes and origin/generation-scoped catalogs/cursors. Never blend PP
observations into production evaluation. No production VM was inspected here.

Raw disaster recovery remains an independent release prerequisite:
[database backups](https://supabase.com/docs/guides/platform/backups) omit Storage
object bytes. Restore a retained raw object plus manifest/receipt to an isolated
location and verify hashes/counts before claiming durable recovery. RLS does not
freeze privileged administrators. This report issues no retirement ticket.

The [next-step assessment](SUPABASE_NEXT_STEPS_2026-11-19.md) prioritizes existing
telemetry, independent recovery verification and measured query-plan review.
It also classifies the observed event-trigger function advisory without
claiming a demonstrated ordinary-RPC exploit.
