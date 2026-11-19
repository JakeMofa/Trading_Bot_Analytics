# Supabase deep navigation and integration review

Completed November 19, 2026 at 07:43 UTC. This expands the earlier
[39-context browser review](SUPABASE_BROWSER_CAPABILITIES_2026-11-19.md).
Every one of the **31 integration catalog overview cards** was loaded and read
individually, along with its primary linked public documentation destination.
Private database details, safe Auth configuration, all 13 email template details,
Realtime settings/policies, nested observability, advisors and project settings
were also inspected. [Page inventory and evidence](evidence/supabase-deep-navigation-2026-11-19.json)
distinguishes these observations from unavailable, sensitive and setup paths.

This is a thorough read-only capability inventory, not a claim to have read every
page in Supabase's entire documentation corpus or activated every clickable
control. Install, create, delete, save, upgrade, authorize, send, subscribe and
secret-reveal controls were left untouched. No cloud configuration/data/grants,
credentials, deployment or live collection changed. The browser part is complete;
the parent workstream owns source implementation and the release chat owns rollout.

## What can help first

1. **Expose verified structured cold history through our backend.** Existing
   private tables already have origin-scoped receipt/revision primary keys,
   prediction time indexes and Invoker envelope-validation functions. This fits
   the candidate reader being built, with a separately qualified SELECT-only
   identity and trusted manifests. Keep live state and predictions on VM-local
   RAM/PostgreSQL. A Data API or RPC adapter can later be compared on identical
   verified IDs; none is automatically faster or authorized by UI availability.
2. **Use existing observability before adding another analytics engine.** The
   catalog now labels Grafana Cloud installed, alongside Data API and Vault.
   Its overview describes roughly 200 Supabase Metrics API signals at one-minute
   granularity. Confirm that the existing connection actually produces usable
   dashboards before proposing new credentials or services. It covers hosted
   Supabase, not the PP/prod VMs unless those are separately instrumented.
3. **Investigate specific database evidence.** The performance advisor identifies
   four private-history foreign keys without covering indexes. Review actual
   query plans and workload before adding indexes. The current memory report
   still marks 1.19 GB commitment Severe on Nano, so database-side full-file scans
   and extensions need a memory budget. Neither observation proves current
   network latency is caused by insufficient compute.
4. **Keep raw recovery independent.** Standard private Storage remains suitable
   for exact chunks/manifests. A wrapper, same-project bucket or protocol change
   does not create a second copy or a tested restore. Database backups exclude
   Storage bytes; preserve release-owned recovery and retirement gates.

## Every integration card, with disposition

The links below are the primary documentation pages reached from the actual
catalog overviews, including redirects. Each assessment is about this project's
current archive/research needs, not a claim the product is generally unsuitable.
All wrapper installation and connection setup remained untouched.

| Integration | Practical PP/prod assessment |
|---|---|
| [Data API](https://supabase.com/docs/guides/api) | Useful future HTTP adapter for a narrow historical contract. Separate schema exposure, object grants, RLS, exact decimals and payload verification remain necessary. The private generated-documentation page was opened only to its shell; credential-bearing examples were not read. |
| [Grafana Cloud](https://grafana.com/docs/grafana-cloud/observe-and-act/monitor-infrastructure/integrations/integration-reference/integration-supabase/) | Installed label is new relative to the previous audit. Useful hosted CPU/memory/IO/connections/query/index monitoring. Successful scraping/dashboard visibility was not verified. Manual setup documentation asks for a privileged API credential; no key was retrieved or supplied. |
| [Vault](https://supabase.com/docs/guides/database/vault) | Installed. Useful for a concrete hosted SQL/Cron/worker consumer. Encrypted storage still has a decrypted SQL view requiring restricted access; it does not distribute VM credential files. Secrets page not opened. |
| [Cron](https://github.com/citusdata/pg_cron) | Potential periodic coverage/lag summaries after a durable reconciliation contract exists. No job created; cannot automatically execute private VM-local work. |
| [Queues](https://github.com/pgmq/pgmq) | Possible secondary hosted jobs. Visibility-window delivery and consumer completion do not replace exact outbox/receipt/ACK correctness during a VM network outage. |
| [Airtable Wrapper](https://supabase.com/docs/guides/database/extensions/wrappers/airtable) | Could join operational plans, but no market-archive need shown. Read-only; no query pushdown and large results transfer locally. |
| [Auth0 Wrapper](https://supabase.com/docs/guides/database/extensions/wrappers/auth0) | External identity reporting, not market archival. User object only, no query pushdown. |
| [BigQuery Wrapper](https://supabase.com/docs/guides/database/extensions/wrappers/bigquery) | Possible later warehouse research federation. Separate warehouse, credentials, cost, type and streaming-buffer limits; not ingestion or backup by itself. |
| [Cal.com Wrapper](https://supabase.com/docs/guides/database/extensions/wrappers/cal) | Scheduling data; no present archive benefit. Some writes supported; no query pushdown. |
| [Calendly Wrapper](https://supabase.com/docs/guides/database/extensions/wrappers/calendly) | Scheduling data; no present archive benefit. Read-only and no query pushdown. |
| [Clerk Wrapper](https://supabase.com/docs/guides/database/extensions/wrappers/clerk) | External identity/organization data; no current archive need. Some objects support writes; constrain any future access. |
| [ClickHouse Wrapper](https://supabase.com/docs/guides/database/extensions/wrappers/clickhouse) | Potential future research aggregation/federation. Overview claims aggregate pushdown, while the documentation limitations describe only basic WHERE/ORDER/LIMIT pushdown. Qualify the installed version and query plan before claiming offload or savings. |
| [Cloudflare D1 Wrapper](https://supabase.com/docs/guides/database/extensions/wrappers/cloudflare-d1) | External SQLite-like dataset federation if later needed. Does not improve the current local PostgreSQL archive contract; subquery foreign tables do not support modification. |
| [Cognito Wrapper](https://supabase.com/docs/guides/database/extensions/wrappers/cognito) | External user-pool reporting only; no current archive need, no identity-pool support or query pushdown. |
| [Database Webhooks](https://supabase.com/docs/guides/database/webhooks) | Optional wake-up for hosted secondary work after a durable row exists. Notification delivery is not archive verification or local retirement authority. |
| [Firebase Wrapper](https://supabase.com/docs/guides/database/extensions/wrappers/firebase) | External Auth/Firestore reporting, no current market-history need. Read-only, full results in memory and default 10,000-row cap. |
| [GraphQL](https://supabase.com/docs/guides/database/extensions/pg_graphql) | Alternative reflected query interface, requiring its own grants/RLS and bounded contract. Extension/install controls only; no GraphiQL query run. |
| [HubSpot Wrapper](https://supabase.com/docs/guides/database/extensions/wrappers/hubspot) | CRM data, no current archive need. Limited pushdown and full-transfer costs. |
| [Iceberg Wrapper](https://supabase.com/docs/guides/database/extensions/wrappers/iceberg) | Possible future analytical tables with filter/partition pushdown. Needs a catalog and ingestion plan; no UPDATE/DELETE/TRUNCATE support. Exact raw chunks do not become Iceberg tables automatically. |
| [Logflare Wrapper](https://supabase.com/docs/guides/database/extensions/wrappers/logflare) | Could correlate saved archive jobs with existing logs if justified. Endpoint parameters and full-result memory costs matter; does not automatically instrument VM workers. |
| [SQL Server Wrapper](https://supabase.com/docs/guides/database/extensions/wrappers/mssql) | External research source if adopted; currently unrelated. Read-only; limited types and no integrated Windows authentication. |
| [Notion Wrapper](https://supabase.com/docs/guides/database/extensions/wrappers/notion) | Potential future research/rules notes. Not market evidence authority; recursive block reads can be very slow. |
| [Orb Wrapper](https://supabase.com/docs/guides/database/extensions/wrappers/orb) | Billing data; no current archive benefit. |
| [Paddle Wrapper](https://supabase.com/docs/guides/database/extensions/wrappers/paddle) | Payments/billing; no current archive benefit. |
| [Redis Wrapper](https://supabase.com/docs/guides/database/extensions/wrappers/redis) | SQL federation of an existing external cache, not a reason to replace VM RAM. Read-only, full results loaded into PostgreSQL memory. |
| [S3 Vectors Wrapper](https://supabase.com/docs/guides/database/extensions/wrappers/s3_vectors) | Optional semantic retrieval after an evaluated embedding use case exists. Float32/vector query restrictions do not fit exact numerical evidence archival. |
| [S3 Wrapper](https://supabase.com/docs/guides/database/extensions/wrappers/s3) | Read-only CSV/JSONL/Parquet research over selected exports. Compressed files load completely into memory; CSV/JSONL columns must all be text. No S3 Select/pushdown. Current scoped-JWT exact-reader compatibility remains unproven. |
| [Slack Wrapper](https://supabase.com/docs/guides/database/extensions/wrappers/slack) | Possible operations-discussion research only; no current market archive need. No Slack data was accessed. |
| [Snowflake Wrapper](https://supabase.com/docs/guides/database/extensions/wrappers/snowflake) | Possible later warehouse federation, with separate access/cost/type/column mapping. Not durable archive replication by itself. |
| [Stripe Sync Engine](https://github.com/stripe/sync-engine-fork) | Payment/customer replication, no present market archive use. Linked repository redirects to a fork; no template installed. |
| [Stripe Wrapper](https://supabase.com/docs/guides/database/extensions/wrappers/stripe) | Billing queries, no present archive benefit. Not a webhook or real-time sync replacement. |

Wrappers can couple PostgreSQL availability to an external system and consume
memory even when the SQL looks like an ordinary local query. A foreign table is
not a durable backup. This is particularly relevant to the measured Nano memory
commitment. Do not broaden credentials or expose private VM databases to make a
wrapper convenient.

## New database, policy and advisor evidence

Private `history_v2` functions `check_revision_envelope` and `source_epoch` both
show Invoker security. The revision trigger is BEFORE INSERT, FOR EACH ROW.
Twenty private indexes were listed; the receipt unique-btree definition is
`(origin_id, generation_id, outbox_id)`. Migration metadata includes the private
history, scoped role, receipts/grants, revisions and Storage reader migrations.
The expanded PP history role has login enabled and create-role/create-database,
BYPASSRLS, superuser and replication capabilities disabled.

Storage policy inventory showed seven policy names/commands. The writer's read
and upload predicates and the reader's exact-GET guard were inspected without
saving. They reference a machine identity, `market-raw`, the PP path pattern and
specific Storage operations. Machine UID values are omitted from the evidence.
UI predicates alone do not prove the combined permissive/restrictive policy
behavior; the existing HTTP-denial qualification remains stronger evidence.
One read-only drawer unexpectedly showed an unsaved-form prompt on closing;
its incidental local state was discarded and nothing was saved or submitted.

Security Advisor showed **0 errors, 3 warnings, 11 informational suggestions**.
Two warnings concern public/signed-in EXECUTE on `public.rls_auto_enable()`, and
one concerns disabled leaked-password protection. Its return type is
`event_trigger`; a warning does not by itself demonstrate an ordinary callable
RPC or privilege exploit. The parent workstream separately verifies that nuance.
The informational RLS-without-policy notices include legacy tables and
`history_v2.coverage`; deny-by-default is not automatically a defect to “fix” by
adding broad access.

Performance Advisor showed **0 errors, 0 warnings, 13 suggestions**. Four concern
unindexed foreign keys in `history_v2.outcomes`, `predictions`,
`protected_evidence` and `snapshot_evidence`; the outcomes finding identifies
`outcomes_origin_id_evidence_id_market_id_fkey`. Eight are unused-index notices,
and one concerns Auth's absolute connection strategy. No index was added or
removed and no linter was rerun. A plan/workload review should precede changes.
Health Advisor displayed zero errors/warnings/suggestions.

## Remaining service/settings observations

Safe Auth pages covered OAuth apps/server, providers/third-party Auth, passkeys,
sessions, rate limits, MFA, redirect URLs, attack protection, hooks, performance,
email templates and SMTP. OAuth Server/passkeys/custom SMTP were off, no OAuth
apps or hooks were configured, and email was the sole enabled listed provider.
All 13 template-detail screens were inspected without changing content or sending
email. During navigation a template-validation TooManyRequests toast appeared;
audit traffic can affect logs, and it was not retried as an operational action.

Realtime was enabled with public channels allowed, pools of two connections,
200 clients, 100 events/s, 20 presence events/s and 256 KB payload limit. No
channel was joined. Its policy page was empty. These are configuration facts,
not authorization to route live forecasts through hosted Realtime.

Every nested observability report was loaded. The database report showed
378.09 MB used memory, 1.19 GB commitment (Severe), 1.27% CPU and a 0.14 GB
database, while several network/IOPS/pooler panels failed. Connections showed
9/60, one active, no idle-in-transaction or blocked queries in that snapshot.
Query Performance showed 26 slow queries and 99.99% cache hit. Gateway/Storage
request aggregates included dashboard admin/catalog reads and refresh delays;
none is a PP worker latency percentile or full-sync benchmark.

Project settings exposed GitHub deployment/preview controls, Vercel setup and
Team/Enterprise PrivateLink; none changed. Dedicated IPv4, PITR and custom-domain
add-ons were disabled. Log-drain destination cards displayed Additional $60.
Infrastructure remained Nano/Oregon with no replica and a same-displayed-price
Micro offer. Storage's global upload cap was 50 MB; no limit was raised.
Analytics and vector bucket screens remained empty/private alpha. Edge Functions
had zero deployments and 11 template choices; editor/deploy paths were not entered.

## Explicit coverage boundary

The machine-readable inventory records reviewed pages and excluded controls.
Individual Auth users, raw audit/log rows, API/JWT/Storage/Edge/Vault secrets,
private generated API credential examples, raw object contents and restore flows
were not read. Provider credentials, pipeline destination wizards, each wrapper
connection wizard, Edge template editors and all create/install/authorize/paid
controls were left unactivated. Their public overviews/docs were reviewed instead.
Not every SQL function body, policy combination, query plan, external linked code
example or recursive global documentation page was audited. These are explicit
limits, not implied production acceptance or missing-data substitutions.
