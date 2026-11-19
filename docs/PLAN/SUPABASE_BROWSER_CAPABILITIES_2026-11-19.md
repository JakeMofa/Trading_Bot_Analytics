# Supabase browser capability review — November 19, 2026

Read-only inspection of the existing TokenBot dashboard completed at 07:02 UTC.
The walkthrough covered 39 page contexts, including navigation-only and inaccessible
contexts. It did not inspect every nested page or the entire documentation corpus.
[Sanitized page-by-page evidence](evidence/supabase-browser-capabilities-2026-11-19.json)
separates loaded observations, navigation-only contexts and explicit gaps.

## What is usable for this platform

Keep the VM RAM/local PostgreSQL path for live state, prediction and collection.
Use hosted services asynchronously for private history, archive retrieval and
research. The hosted main branch's PRODUCTION badge does not establish the origin
of stored records; PP/prod isolation remains an application and permission contract.

| Dashboard area | Actual observation | Practical PP/prod use and limitation |
|---|---|---|
| PostgreSQL tables/functions/indexes | Legacy public tables coexist with 12 private history_v2 tables. Public rls_auto_enable is Definer. Public market/time/model indexes exist. | Existing hosted structured history is the closest fit for saved predictions/features/outcomes. A function could provide bounded cold retrieval, but function grants, origin predicates, exact decimals and revision integrity need qualification. UI presence does not qualify a new API. |
| Database policies | Public tables show RLS enabled. | Preserve private history and separate scoped readers/writers. A policy name or enabled-RLS control is not proof of effective authorization. |
| Data API | Installed; settings show 0/22 tables and 1/3 functions exposed, automatic new-table exposure enabled, 1000-row cap. | A deliberately constrained history-only API schema is possible after review. Do not expose all history_v2 or attach importer credentials to browsers. Automatic exposure warrants a separate compatibility review. |
| Storage and policies | market-raw, knowledge and backups buckets visible. Authenticated archive upload/readback and exact history-reader/deny-mutation policies listed. | Continue immutable raw objects plus exact metadata/hash verification. Empty knowledge/backups policy lists do not establish working access or a backup strategy. |
| S3 protocol | Enabled with direct Storage endpoint; no key generated. | Alternative object transport may help tooling, but existing HTTP exact GET is already qualified. Protocol availability does not establish narrower authorization, better speed or independent recovery. |
| S3 Wrapper | Read-only SQL over CSV/JSON Lines/Parquet; Vault integration; wrappers extension disabled. | Potential offline SQL research over selected archive exports. Dashboard says compressed files load fully into memory. Current Nano and the exact reader's scope make this a separate experiment, not a transparent archive-reader replacement. |
| Pipelines | No configured pipeline; enabled Add pipeline control; primary source Oregon. | External analytics replication could later offload research. Do not treat the button as a qualified destination, enabled replication, complete immutable history or PP local outbox replacement. |
| Analytics and vector buckets | Both show private-alpha notices and empty create-bucket states. | Do not rely on these for required recovery. Vector search could later support semantic news/event retrieval, but does not improve exact numerical archival or substitute for receipt hashes. pgvector is a separate database extension and is disabled. |
| Edge Functions | No deployments; templates for database access, Storage upload, WebSockets and other tasks. | Could host a future narrow archive verification/query gateway or notification handler. Existing backend already supplies a boundary; added cold starts, runtime limits, credentials and another deployment need measured benefit. |
| Cron, Queues, Webhooks | Install controls only; pg_cron/pgmq/pg_net disabled. | Possible cloud-only verification scheduling, repair tasks or notifications. None can read VM-local outbox/partitions without a new authenticated bridge. Do not make delivery or a queue ACK archive authority. |
| Vault | Installed beta module; secrets not opened. | Future hosted task secrets can stay server-side. It does not synchronize existing VM credential files or prove reader/writer isolation. |
| Realtime | Inspector available; no channel joined. Publication has zero tables. | Archive-job status notifications may help UI later; unnecessary for the existing VM SSE live path and not durable archive acknowledgement. |
| Hosted Compute | Explicit no-access/private-alpha/waitlist state. | No deployable worker capability established. This product is distinct from sizing the current Postgres instance. |
| Observability and backups | Metrics available with missing panels; physical daily backups visible; UI excludes Storage object bytes. | Add phase-specific archive latency/retry/integrity evidence to existing telemetry. Raw object recovery needs separate tested protection beyond database backups. |

## Capacity and recovery observations

Loaded infrastructure showed Nano, no read replicas, approximately 126 MB of
database data, 128 MB WAL, 168 MB system space and 0.41 GB used of 2 GB. The UI
offered a same-displayed-price Micro upgrade; nothing was selected. The last-hour
database report showed 396.45 MB memory usage, 1.19 GB memory commitment with a
severe warning, and 1.62% CPU. Several disk/network/connection panels failed to
load. These facts justify checking memory before adding database-side extensions
or compressed-file scans; they do not prove compute is causing remote latency.

The loaded Storage report showed 27 requests and 210.22 ms aggregate response
speed in its last-hour window. Browser catalog reads and intentional permission
probes appear in that traffic. This is not a PP full-sync benchmark or a production
percentile. Public and private table counts are UI estimates; observed revision
payload growth must not be reported as completed release/backfill verification.

Scheduled physical backups for November 12–18 were visible. The backup screen
explicitly excludes Storage bytes. No restore or independent raw-object recovery
was tested. Database recovery and exact archive recovery remain separate gates.

## Documentation discrepancies and boundaries

The embedded S3 Wrapper overview lists GetObject and ListBucket. The parallel
current official-documentation review found GetObject/GetObjectAttributes and
version variants instead. Preserve this discrepancy; do not assert listing is
universally required. There is no demonstrated compatibility between wrapper
credential configuration and the existing scoped JWT exact-GET reader. Broad S3
keys must not be introduced merely to make the wrapper work.

The current official Pipelines documentation is newer than some search-tool and
embedded material. The parallel documentation matrix controls supported destination
claims; this UI pass established only the available empty pipeline surface. No
pipeline was created and no destination credentials, slots or billing changed.

## Prioritized implementation direction

Qualify the existing bounded structured cold-history reader behind an explicit
backend history request, retaining immutable receipt/envelope checks, exact decimal
text, source/availability times, coverage limits and origin/generation cursors.
Give it a separately qualified read-only role rather than the importer role.
Keep current live endpoints local and report cloud unavailability explicitly.
This closes an observed application gap without requiring a new hosted product.

The source implementation/review is owned by the parent research workstream.
The release chat owns cloud permission changes, backfill, deployment, collection,
raw recovery qualification and retirement. No browser observation grants retirement
authority or establishes a privileged-mutation freeze. Production adoption needs
its own role, credentials, origin boundary, mixed-environment denial tests and
performance evidence.

## Coverage gaps

Database types, role details and migrations; private function/trigger/index detail;
individual Auth users and most nested Auth pages; secret/key pages; raw object
content; actual restore flows; Realtime settings/policies; every wrapper's setup;
pipeline creation and every destination; and all nested logs/observability reports
were not exhaustively audited. No secret values were revealed or copied. Browser
inspection remained read-only throughout.
