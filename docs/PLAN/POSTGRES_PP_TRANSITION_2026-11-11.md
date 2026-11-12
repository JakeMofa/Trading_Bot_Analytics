# PostgreSQL preproduction transition review — November 11, 2026

This report supports [the master roadmap](INTELLIGENCE_REBUILD_PLAN.md); it is
not another roadmap. The user selected PostgreSQL as the intended replacement
for SQLite A/B, to qualify first in isolated PP/PRT. This authorizes planning and
inventory, not provisioning, production migration or retention enablement.
Phase 1.75 and I7 remain open.

## Verified starting point

Measurements were taken November 11 CST / November 12 UTC. See
[evidence](evidence/postgres-pp-inventory-2026-11-11.json).

| Component | Observed |
|---|---|
| Lightsail | One running Ubuntu instance, tradebot-analytics-01, us-east-2; 2 vCPU, 2 GiB RAM, 60 GB SSD; no instance snapshots in this Region |
| Guest filesystem | 57.076 GiB total, 46.397 GiB available; this is separate from the app's SQLite cap |
| Guest memory | 1,905.99 MiB total, 1,299.80 MiB available at the sample; no swap |
| Deployed revision | d56b4a73ad6f1a10ba2bac928087cd5d85c6a42a |
| Services | API, ensemble and lifecycle active/running; sampled PIDs 31763 / 31767 / 31771; NRestarts=0 |
| SQLite | Main file 5,323,907,072 bytes; WAL 4,517,712; SHM 98,304; file lengths, not a full allocation/integrity audit |
| Effective flags | MAX_LOCAL_STORAGE_MB=5120; retention and paid AI false; API host 127.0.0.1, reload false |
| Collection | Persisted Coinbase/Polymarket/rest states stopped; storage_guard limit_reached |
| Health reporting | /health returned ok; this does not prove fresh collection and conflicts with stopped feed state |
| PostgreSQL/Docker units | Both not-found/inactive; no A/B deployment is established by the existing generated tests |

The deployed single SQLite file contains raw observations and stream_events,
markets, candles, reference/historical prices, features, predictions, prediction
context links, news/FTS, AI suggestion/decision history, schema migration,
feed-health and cloud checkpoint tables. A schema catalog read succeeded;
complete quick/FK checks and exact table counts were not run.

The explicitly authorized Wi-Fi access change added only the current operator
IPv4 /32 to TCP22, preserving all existing Lightsail rules and browser SSH.
Direct pinned SSH still timed out. Browser SSH succeeded; existing UFW TCP22
already delegates source filtering to Lightsail, so UFW was unchanged.
No restart, application deployment, database repair or cleanup occurred.

## Supabase structure

TokenBot (xttdqeimdujweijxcuro) is in us-west-2 on PostgreSQL 17.11.
The SQL database is 102,233,779 bytes (97.50 MiB). Its ten public application
tables all have RLS enabled:

- markets, candles, feature_snapshots, predictions, official_outcomes
- model_outputs, evaluation_metrics, news_events, raw_archives, sync_checkpoints

Prices and targets use numeric; forecast probabilities use double precision;
evidence/payload fields use jsonb. Candles use an epoch bigint time key and many
other timestamps use timestamptz. Archive manifests carry bucket/path, checksum,
counts, byte sizes, recorded verification and source identity boundaries.

Private Storage is a separate history layer: market-raw has 966 objects totaling
338,708,904 metadata-reported bytes (323.02 MiB); knowledge and backups are empty.
Catalog presence and RLS enablement do not certify archive contents, least
privilege or coverage. No fresh authenticated object readback was performed.

Local PostgreSQL would be another database instance. Matching the engine does
not automatically synchronize it with Supabase. Keep explicit structured sync,
raw object uploads, exact checkpoints, authenticated verification and replay.

## Recommended PP layout and cost

Use a second Lightsail VM in us-east-2 for isolated PP application + PostgreSQL.
A single VM can run both environments with separate processes/containers,
databases, roles, ports and volumes, but production and tests still share RAM,
CPU, I/O and host failure. Docker limits help bound consumption; they do not
supply another machine or eliminate interference.
[Docker resource limits](https://docs.docker.com/engine/containers/resource_constraints/)

| Option | Public-IPv4 Linux bundle list price | Combined compute list price |
|---|---:|---:|
| Existing production, 2 GiB / 60 GB | $12/month | $12/month |
| Add matching 2 GiB / 60 GB PP | +$12/month | $24/month |
| Recommended starting PP candidate, 4 GiB / 80 GB | +$24/month | $36/month |

These AWS API/pricing figures exclude taxes, usage extras and credits; they are
not an invoice. AWS reports the project is on the active FREE plan, not PAID.
Confirm plan eligibility, credits/spend controls and the exact provisioning
scope before creation. No resource or plan upgrade has been authorized here.
[Lightsail pricing](https://aws.amazon.com/lightsail/pricing/)

Four GiB is a proposed test-host size, not proven production sizing. Qualify
the candidate under the existing production memory/CPU envelope too, or review
a separate production resize. More PP RAM cannot prove the 2 GiB host will cope.
The old fixture caps remain until a specific test resource change is approved.

Keep one real external-market collector. A preview-only PP dashboard can use
the production read-only API. Candidate backend/query/migration testing must use
a separate writable database and generated/replayed inputs; previewing live
values alone does not test candidate SQL. A PP replay producer is not a second
Coinbase/Polymarket collector. Start with generated data; existing-data exports
or archive replay require their exact source, destination and scope to be set.

## PostgreSQL qualification model

Use a local PostgreSQL service on the PP VM, with application and database
co-located. Start with a pinned supported version compatible with required
Supabase types. Docker Compose is a packaging option; it is not yet installed
or selected as a deployed production runtime. PP must have separate database
credentials/volumes, collector disabled, paid AI disabled, and no production
database or Supabase write credentials mounted.

Replace raw A/B file switching with time-partitioned raw tables and persistent
structured/evidence tables within PostgreSQL. Preserve the adapter/API contract
so dashboard and calculations do not select files manually. Partitioning can
make expiry cheaper than bulk row deletion, but still has lock/DDL constraints
and requires measured concurrency qualification.
[PostgreSQL partitioning](https://www.postgresql.org/docs/17/ddl-partitioning.html)

Propose hourly receipt-time partitions and an explicit rolling 72-hour local
raw window: only retire a whole partition once its upper bound is outside the
cutoff and all archive/reference gates pass. This can retain nearly one extra
hour plus blocked archives. Review this semantic change: the old A/B policy
rotated at 72 hours OR size and did not guarantee a rolling 72-hour history.
Do not silently claim those policies are equivalent. Preserve original event
time independently, including late/out-of-order events.

Preserve exact decimals, raw timestamp strings/submicrosecond precision,
stable identities, source/receive times, original payloads and protected
references. PostgreSQL timestamps have microsecond resolution, so normalizing
a nanosecond source timestamp must not discard its original representation.
[PostgreSQL timestamp types](https://www.postgresql.org/docs/17/datatype-datetime.html)

MVCC supports concurrent ordinary reads/writes; it does not remove conflicting
writes, DDL locks, slow scans, resource saturation or archive failures.
[PostgreSQL concurrency](https://www.postgresql.org/docs/17/mvcc-intro.html)

Archive in bounded exact-identity chunks to the existing private Supabase
Storage destination. Verify authenticated readback, counts, checksums and
identity coverage before local removal. Preserve protected evidence/history;
cloud failure holds local data. The existing mutation-protection and final
verification requirements remain open and are not solved by changing engines.
Retain legacy SQLite until separately qualified archival, reference/history
access, writer fencing, reader drainage and recovery permit its retirement.

## Ordered decisions and acceptance

1. Inventory: completed in the scoped sense above. Full integrity, archive
   readback, representative growth and backup/recovery coverage remain unproven.
2. Select the exact PP host/billing/network/runtime/test-resource scope for
   approval. Recommended starting candidate: second VM, 4 GiB / 80 GB, us-east-2.
3. Implement small reviewed PRs for PostgreSQL schema/adapter parity, isolated
   PP packaging, migration/recovery, archive/retention, then release controls.
   Preserve SQLite implementation and tests as evidence until classification
   and migration decisions are reviewed.
4. Qualify generated ingestion, duplicate/reordered inputs, schema/type/FK
   protections, archive outages, mutation, crash recovery and partition expiry
   concurrently with collector/API/SSE/features/history. Measure cold/warm
   queries, disk/index/WAL/TEMP peaks, connection limits and memory. Existing
   save/heartbeat <1 s and API no 2 s timeouts remain; qualify feature/input
   freshness <=30 s and market rollover, not HTTP responsiveness alone.
5. Reconcile release policy before any release: user intends main=production;
   deploy-tradebot.yml currently permits manual production operations from
   codex/lightsail-deployment. Implement and test distinct PP vs production
   identities, exact-commit artifacts/CI, manual production approval and recovery.
   A green Supabase-schema CI job is not application PostgreSQL qualification.
6. Review one bounded cutover procedure only after compatibility, capacity,
   complete verification and forward recovery pass. Code rollback must not
   restart an old writer after PostgreSQL acknowledges new data. Legacy
   retirement, continuous retention enablement and production acceptance remain
   separate decisions. Complete I7/Phase 1.75 evidence before Phase 2.

PR #9 is closed/superseded. #11 is open/ready; #12–#14 are open/draft. At the
single check, their existing code checks passed; Supabase Preview was skipped.
The reviewed heads and checks are in the evidence file. No merge is authorized
by this architecture inventory. Review each SQLite-specific PR for reuse,
amendment or deferral rather than merging it as a PostgreSQL release.

No new VM, database-engine migration, application deployment, restart, retention,
paid AI call, database copy/snapshot, manual WAL operation or guard increase was
performed. The sole infrastructure mutation was the user-requested SSH /32.
