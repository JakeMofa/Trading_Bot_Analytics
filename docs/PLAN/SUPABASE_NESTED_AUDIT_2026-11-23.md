# TokenBot Supabase nested-screen audit

November 23, 2026, America/Chicago. This is the screen-by-screen follow-up to the [earlier catalog audit](SUPABASE_DEEP_NAVIGATION_2026-11-19.md). The scope is TokenBot's dashboard, the nested screens and setup previews it exposes, and their first-hop documentation. A visible card, a loaded screen, and a completed feature test are different evidence. Prior performance measurements are in the [capability lab](SUPABASE_ISOLATED_CAPABILITY_LAB_2026-11-19.md).

The team used dedicated Chrome tabs and reviewed setup before submission. No settings were saved and no cloud jobs, functions, buckets, credentials, policies, or reports were created. Account records, secret values, archive payloads, and raw logs were outside the screen audit.

- [Platform implications](#practical-implications-for-this-platform)
- [Auth, Storage, Edge, Realtime, and project settings](#authentication)
- [Overview, advisors, observability, logs, and compute](#tokenbot-dashboard-audit--overview-advisors-observability-logs-and-compute)
- [Integration catalog and wrapper setup](#tokenbot-integration-screens-and-linked-documentation)
- [Auth providers and hooks](#tokenbot-auth-provider-and-hook-audit)
- [Database, Table Editor, and SQL Editor](#tokenbot-supabase-browser-audit--database-table-editor-sql-editor)
- [Query Performance and Advisor details](#tokenbot-query-performance-and-advisor-detail-follow-up)
- [System-table definitions and remaining gaps](#tokenbot-system-table-definition-audit)

## Practical implications for this platform

1. **Measure the structured verifier first.** Query Performance, Database Connections, Unified Logs, and the installed Grafana integration can separate hosted query time and connection waits from the VM's transfer and verification time. Verify the Grafana scrape. The retained A index-only run took 212.8 seconds under a 240-second budget. Structured readback took 131.7 seconds, and the 48.0-second exact-revision phase includes client work as well as database work. [Metrics API](https://supabase.com/docs/guides/observability/metrics)
2. **Use actual plans to choose a database change.** The advisor showed four unindexed foreign-key suggestions on `history_v2` tables. Treat them as candidates for an exact verifier plan comparison. If network round trips dominate, compare a narrow scoped RPC against the existing reader on identical 500-row pages, with the same IDs, decimal text, hashes, and permissions. [Database inspection](https://supabase.com/docs/guides/observability/inspect) · [Data API access controls](https://supabase.com/docs/guides/api/securing-your-api)
3. **Keep optional services attached to a specific job.** Realtime can deliver archive-status notices. Cron, Queues, and Edge Functions fit periodic checks, retryable jobs, and small notifications. Analytics Buckets, Pipelines, and vector services need a separate historical or research workload. The current private Storage and `history_v2` paths already provide archive retrieval and SQL history. [Realtime authorization](https://supabase.com/docs/guides/realtime/authorization) · [Analytics Buckets](https://supabase.com/docs/guides/storage/analytics/introduction)
4. **Measure compute during verification.** The infrastructure showed Nano, no read replicas, and controls for Micro, disk, autoscaling, IOPS, and throughput. A point-in-time dashboard sample cannot establish the source of an earlier timeout. [Compute and disk](https://supabase.com/docs/guides/platform/compute-and-disk) · [Read replicas](https://supabase.com/docs/guides/platform/read-replicas)

## Authentication

Opened Users, OAuth Apps, Emails, SMTP Settings, Sign In / Providers, Third-Party Auth, Passkeys, OAuth Server, Sessions, Rate Limits, Multi-Factor, URL Configuration, Attack Protection, Auth Hooks, Audit Logs, and Performance. Auth's Policies entry shares the database policy screen. OAuth Server exposed its endpoint section. User records and outbound notifications were outside the review. [Authentication](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/auth/users) · [OAuth Server](https://supabase.com/docs/guides/auth/oauth-server) · [Custom providers](https://supabase.com/docs/guides/auth/custom-oauth-providers) · [Auth Hooks](https://supabase.com/docs/guides/auth/auth-hooks) · [Audit logs](https://supabase.com/docs/guides/auth/audit-logs)

Opened all 13 individual email editors under [Auth Emails](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/auth/templates): Confirm sign up, Invite user, Magic link or OTP, Change email address, Reset password, Reauthentication, Password changed, Email address changed, Phone number changed, Sign-in method linked, Sign-in method removed, MFA method added, and MFA method removed. Editor headings matched their routes. SMTP Settings loaded as a separate tab.

## Storage

| Screen or subview | Evidence |
| --- | --- |
| [Files and Buckets](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/storage/files) | Opened the list and all three bucket detail routes: `market-raw`, `knowledge`, and `backups`. The list showed ten policies for `market-raw` and zero for each other bucket. The detail navigation exposed policy links and edit controls. Individual stored objects were outside the screen audit. |
| [Files Settings](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/storage/files/settings) | Opened settings and saw the enabled image transformation switch. [Image transformation docs](https://supabase.com/docs/guides/storage/serving/image-transformations) |
| [Files Policies](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/storage/files/policies) | Opened grouped sections for all three buckets, other `storage.objects` policies, and `storage.buckets`. |
| [Analytics](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/storage/analytics) | Opened the private-alpha product screen and the Create analytics bucket dialog. [Analytics docs](https://supabase.com/docs/guides/storage/analytics/introduction) |
| [Vectors](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/storage/vectors) | Opened the private-alpha product screen and the Create vector bucket dialog. [Vector docs](https://supabase.com/docs/guides/storage/vector/introduction) |
| [S3](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/storage/s3) | Opened Configuration, Connection, and Access keys headings. [S3 authentication](https://supabase.com/docs/guides/storage/s3/authentication) |
| [URL signing keys](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/storage/signing-keys) | Opened the management screen. [Signing keys](https://supabase.com/docs/guides/storage/security/signing-keys) |
| Create file bucket | Opened the pre-submit dialog from Files. [Bucket docs](https://supabase.com/docs/guides/storage/buckets/fundamentals) |

## Edge Functions and Realtime

- [Edge Functions](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/functions). Opened Functions, Secrets, the deploy-method menu, and the CLI instructions. The menu presents Editor, CLI, and AI Assistant. All eleven template editors loaded: Hello World, Database Access, Storage Upload, Node Built-in API, Express, Stream text with AI SDK, Generate recipes with AI SDK, Stripe Webhook, Send Emails, Image Transformation, and WebSocket Server. AI Assistant deployment, function invocations, and live function detail screens were outside the inspected workflows. [Edge Functions docs](https://supabase.com/docs/guides/functions)
- [Realtime](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/realtime/inspector). Opened Inspector, the Join a channel dialog, Policies for `messages`, and Settings. Settings displayed Realtime and public access enabled, connection pools of 2 for both Database and Postgres Changes, and visible limits of 100 events per second and 20 presence events per second. The inspector dialog was viewed before joining or sending. [Settings](https://supabase.com/docs/guides/realtime/settings) · [Authorization](https://supabase.com/docs/guides/realtime/authorization) · [Postgres Changes](https://supabase.com/docs/guides/realtime/subscribing-to-database-changes)

## Project and billing settings

| Screen or subview | Evidence |
| --- | --- |
| [General](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/settings/general) | Opened project settings, access, availability, versions, custom domains, transfer, and deletion sections. |
| [Infrastructure](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/settings/infrastructure) | Opened compute tiers, read replicas, disk, and advanced sizing controls. [Database size](https://supabase.com/docs/guides/platform/database-size) |
| [Project integrations](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/settings/integrations) | Opened GitHub, Vercel, AWS PrivateLink, and Connections sections. Provider authorization was outside the reviewed flow. |
| [API Keys](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/settings/api-keys), [Legacy API Keys](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/settings/api-keys/legacy), and [JWT Keys](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/settings/jwt) | Opened the screens and used headings only. [API key guide](https://supabase.com/docs/guides/getting-started/api-keys) · [Migration guide](https://supabase.com/docs/guides/getting-started/migrating-to-new-api-keys) |
| [Log Drains](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/settings/log-drains) | Opened all eight destination forms: Custom Endpoint, OTLP, Datadog, Loki, Amazon S3, Sentry, Axiom, and Last9. [Log Drains docs](https://supabase.com/docs/guides/observability/log-drains) |
| [Add-ons](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/settings/addons) | Opened the catalog and read the three visible cards for IPv4, point-in-time recovery, and custom domains. [IPv4](https://supabase.com/docs/guides/platform/ipv4-address) · [Backups](https://supabase.com/docs/guides/platform/backups) · [Custom domains](https://supabase.com/docs/guides/platform/custom-domains) |
| Subscription and Usage | Opened both organization pages and verified the Billing and Usage headings. Payment details were outside the audit. |

## Official docs opened from these sections

Reviewed the linked product material for Auth hooks, custom providers, OAuth server, audit logs, Realtime authorization, settings and subscriptions, Edge Functions, all three bucket types, Storage signing and S3 authentication, image transformations, OAuth integrations, API keys and legacy migration, read replicas, compute and disk, database size, production configuration, IPv4, backups, custom domains, and Log Drains. [OAuth integration guide](https://supabase.com/docs/guides/integrations/build-a-supabase-oauth-integration) · [Production checklist](https://supabase.com/docs/guides/deployment/going-into-prod)


## TokenBot dashboard audit — overview, advisors, observability, logs, and compute

Browser observations from November 23, 2026, America/Chicago. Dashboard menus, reports, and visible controls were reviewed in dedicated Chrome tabs. Counts below are dashboard snapshots for the visible time ranges. Live project reports are project-wide unless explicitly filtered. No setup, settings save, export, account action, or deployment was submitted.

### Project Overview and related screens

| Screen | Status | Observed |
| --- | --- | --- |
| [Project Overview](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro) | Opened | Status, Nano compute, GitHub, recent branch, last migration, and last backup cards. Infrastructure diagram and map controls. Request cards link to Postgres, Edge Functions, Auth, Storage, Realtime, and API Gateway. Time range selector for the request cards. Reports section offered a custom report and an Add block control. |
| [Database infrastructure](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/settings/infrastructure) | Linked card, settings assigned separately | The Overview card showed Nano and the direct link to infrastructure. No size change was attempted. |
| [Production Branches](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/branches) | Opened | Main production branch, no other branch visible, GitHub configuration, View Logs, and Create branch. Branch creation and connection submission were outside the read-only review. |
| [Merge requests](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/branches/merge-requests) | Opened | Merge requests list and New merge request action. No request was created. |
| Help & Support | Menu opened | Docs, Contact support, and Community support. No support request was submitted. |
| Report builder | Entry points observed | Add block, Add your first block, and New custom report were shown. Creating or editing a saved report would be a separate change. |

The Branching docs describe dashboard branching and GitHub integration. The changelog calls out Production Branches read-write permission for branch merges. Branching is a separate deployment tool and could isolate an experiment if needed. [Branching](https://supabase.com/docs/guides/deployment/branching) · [Dashboard workflow](https://supabase.com/docs/guides/deployment/branching/dashboard) · [GitHub integration](https://supabase.com/docs/guides/deployment/branching/github-integration) · [Changelog](https://supabase.com/changelog.md)

### Advisors

| Screen | Status | Observed |
| --- | --- | --- |
| [Health Advisor](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/advisors/health) | Opened | Errors, Warnings, Info, filtering, refresh, and export. Counts were 0 errors, 0 warnings, 0 suggestions. |
| [Security Advisor](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/advisors/security) | Opened | 0 errors, 3 warnings, 11 suggestions. Filters and linter controls visible. Individual issue details and remediation were not verified in this pass. |
| [Performance Advisor](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/advisors/performance) | Opened, Info selected | 0 errors, 0 warnings, 13 suggestions. Four entries concern unindexed foreign keys on `history_v2.outcomes`, `predictions`, `protected_evidence`, and `snapshot_evidence`. Unused-index notices included `public.markets`, `feature_snapshots`, `predictions`, `news_events`, `raw_archives`, and `history_v2.outcomes`. The follow-up opened all four individual foreign-key issue panels. |
| [Query Performance](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/observability/query-performance) | Opened through its observed route | Advisors links to the same Observability report. |
| Advisor Center | Entry points observed | The follow-up opened the toolbar Advisor Center. Legacy Advisor pages supplied the counts above. |

Advisor findings identify candidates for inspecting actual query plans. Existing index usage and write overhead matter before any index change. [Supabase Advisors](https://supabase.com/docs/guides/observability/advisors) · [Inspect the database](https://supabase.com/docs/guides/observability/inspect)

### Observability

All ten report routes below loaded and showed report-specific content. The report pages have time selectors and service-specific filters. The audit read those controls without changing project configuration. The gateway report briefly showed a session-expired overlay even though its chart headings and aggregate figures loaded.

| Screen | Read-only observations and nested controls |
| --- | --- |
| [Overview](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/observability) | Database summary, 24-hour selector, refresh, information buttons, and service-health cards. At inspection, the aggregate cards showed 57 slow queries, peak 7/60 connections, 35% disk, 99% disk I/O balance, 58% memory, and 2% CPU. The Slow Queries card links to filtered Query Performance. The other database metric cards link to the Database report. |
| [Query Performance](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/observability/query-performance) | Primary Database selector, Calls, Total Time, Roles, Source, refresh, export, and Reset report controls. Headline fields include cache hit rate and average rows per call. Columns are Query, Time consumed, Calls, Max time, Mean time. Query-details shell and 12 data rows were visible. The follow-up opened the Query details drawer through a visible grid cell. Query text was excluded from this audit. |
| [API Gateway](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/observability/api-overview) | Geography, total requests, response errors and speed, ingress and network traffic. Last 60 minutes, All Requests, Add filter, and Show more affordances. One aggregate snapshot showed 182 requests and 287 ms. |
| [Database Connections](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/observability/connections) | Live overview for connections, active queries, idle transactions, blocked queries, top blocker, and longest-running sessions. Sessions has state, role, application, and root-blocker filters. Query/session, duration, and blocked-by columns. More actions opened and exposed Copy prompt. The prompt was not copied or sent. |
| [Database](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/observability/database) | Primary selector, refresh, Last 60 minutes, memory usage and commitment, CPU breakdown, network throughput, and database size. A point-in-time snapshot showed about 398 MB usage, 1.38 GB commitment, and 13.64% CPU. These figures use a different view/window than the overview cards. |
| [Data API / PostgREST](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/observability/postgrest) | Total requests, response errors and speed, network traffic, Add filter, and request tables. This reports the Data API path. It does not directly measure the PP verifier's native Postgres sessions. |
| [Auth](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/observability/auth) | Usage, sign-in attempts, sign-ups, password resets, error codes, processing times and percentiles, Auth API Gateway, Provider and Status Code filters. User records were outside this section audit. |
| [Edge Functions](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/observability/edge-functions) | Invocations, status codes, execution time, region, and Function/Status Code/Execution Time/Region filters. Zero invocations displayed in the selected window. |
| [Storage](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/observability/storage) | Total requests, response speed, ingress/network traffic, request caching, and Add filter. Local archive ownership and client-side verification need separate evidence. |
| [Realtime](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/observability/realtime) | Connected clients, Broadcast, Presence, Postgres Changes, channel joins, message size, database-to-broadcast replication lag, requests, errors, and response speed. Broadcast, Presence, and Postgres Changes displayed zero in the selected window. |

Supabase's report guide covers the service report families. The Metrics API is Prometheus-compatible and can provide Postgres CPU, I/O, WAL, connection, and query time series for a Grafana dashboard. The Realtime lag chart measures from database commit to broadcast, which is a different boundary from collector-to-client delivery. [Reports](https://supabase.com/docs/guides/observability/reports) · [Performance Tuning](https://supabase.com/docs/guides/platform/performance) · [Database and disk size](https://supabase.com/docs/guides/platform/database-size) · [Metrics API](https://supabase.com/docs/guides/observability/metrics) · [Realtime Reports](https://supabase.com/docs/guides/realtime/reports) · [Troubleshooting](https://supabase.com/kb/topics/troubleshooting)

### Unified Logs

- Opened [Unified Logs](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/logs). The dashboard showed the preview banner, time range, live view, refresh, hide/open filters, and export controls. Display columns include date, method, pathname, and event message. Private messages and paths were excluded from the captured notes.
- Log type controls included API Gateway and Postgres with Expand, PostgREST, Auth, Storage, Edge Function, Realtime, Supavisor, PgBouncer, and Compute. Severity filters showed 2xx, 4xx, and 5xx. User, Status, Method, Pathname, and Pipeline ID headings were observed. Individual event payloads and exports were outside the review.
- More information opened Dashboard feature previews. It showed Editors, Observability, Database, and Others settings, including Updated Logs interface. No feature flag was changed. Capture your logs links to Project Settings → Log Drains. [Logs in Studio](https://supabase.com/docs/guides/observability/logs) · [Log Drains](https://supabase.com/docs/guides/observability/log-drains)

### Compute workspace

- Opened [Compute](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/compute). It showed Private Alpha, a message that this project does not have Compute access, and a public waitlist page. No runtime, sandbox, service, or deployment can be verified behind the access gate. [Compute product page](https://supabase.com/compute)
- Opened [Compute Secrets](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/compute/secrets). The screen lists platform-managed secret names and descriptions. No values were retrieved or copied. The managed Compute workspace and database instance sizing are separate surfaces.

### PP applicability

1. Use Query Performance and Database Connections to distinguish a slow server query, a lock wait, a long transaction, or connection churn. Pair those with the same A/B verifier page and client phase timings instead of treating the full readback interval as hosted SQL time.
2. Verify the existing metrics scrape before creating a saved report or log drain. A joined dashboard can align Postgres connections, host saturation and timeouts with VM readback phases and pending-row age. Report cards provide baselines only.
3. Keep Storage, Data API and Realtime metrics scoped to their service and time windows. This browser pass observed capability and aggregate dashboard behavior. It did not benchmark a collector, a verifier or proposed index changes.


## TokenBot integration screens and linked documentation

Browser and public documentation review of the 31 distinct cards present in TokenBot’s Integrations catalog. The catalog showed Data API, Grafana Cloud and Vault as installed. The initial dashboard snapshot exposed Category and Search controls and featured duplicates. I deduplicated catalog cards by their actual Overview URL. Each public first-hop guide was reopened individually via web, including vendor GitHub documentation and the Grafana redirect. I also opened the catalog’s [Build a Supabase Integration guide](https://supabase.com/docs/guides/integrations/build-a-supabase-oauth-integration). This inventory covers project-linked feature screens and first-hop docs.

### Nested screens inspected

| Integration | Nested coverage | What the screen establishes |
| --- | --- | --- |
| Data API | Overview, Settings and generated Docs verified. The project connection panel was confirmed in Docs with credential-bearing examples excluded. | The Data API card is installed and exposes Overview, Settings and project-generated Docs. Settings showed 2/3 schemas, 0/22 tables, 1/3 functions, automatic exposure on, max rows 1,000, plus search path, pool size and Harden Data API. Schema selection popover listed graphql_public, history_v2, and public. An incidental draft change was discarded by reload. The saved count returned to 2/3 and Save was disabled. |
| Grafana Cloud | Overview and the Settings interior were confirmed. Settings exposes Connected resources and OAuth application. | Installed label is authoritative for the card. Connected resources and OAuth application were visible. A successful metrics scrape or linked dashboard has not been established. |
| Vault | Overview confirmed. Secrets tab loaded and showed the empty state. | Public docs explain encrypted values and restricted decrypted access. Secret values are outside the audit. |
| Cron | Overview and Jobs interior loaded. Jobs explicitly says Cron is not installed. | Card offers installation. The extension is a prerequisite for managing jobs. |
| Queues | Overview, Queues and Settings routes opened; both nested screens loaded the integration heading and install gate. | pgmq is required before queue management. |
| Database Webhooks | Overview and Webhooks tab loaded, with the install gate present. | The extension/workflow can wake secondary work after database events. |
| GraphQL | Overview and GraphiQL tab loaded. | GraphiQL displayed pg_graphql extension disabled. A separate session-expired dialog blocked further access in that tab. No test operation was submitted. |
| ClickHouse | Overview, Wrappers tab and unsubmitted configuration dialog verified. | The dialog exposes required extensions, a server name, the connection string, manual foreign tables, and schema import. I closed the dialog with Cancel. |
| Remaining wrappers | Catalog links and each available Overview/nested route are listed in the inventory below. | All 23 Wrappers management screens and unsubmitted setup dialogs were individually verified. Their service-specific inputs and import controls are listed below. |
| Stripe Sync Engine | Overview and Settings tab loaded. Install remains the entry gate. | The linked Stripe repository says the fork will merge into stripe/sync-engine. There is no observed project deployment. |

The on-screen Install, Create, Save, Deploy and Delete actions were treated as project mutations. I followed each Wrappers page’s setup link to view its configuration dialog and canceled without submitting. Credentials were left out of the evidence. Dashboard navigation intermittently timed out while loading an interior screen. All timed-out overviews subsequently recovered through their visible catalog cards rather than direct navigation.

### What matters for PP

- Use the already-installed Grafana integration with Supabase Query Performance and logs to separate database execution from VM transfer, parsing and verification. Check whether the metrics scrape works.
- Consider a narrowly scoped Data API RPC only if the existing 500-row verifier is network-bound. Keep the private archive/history roles and data separation.
- Cron, Queues, Webhooks, and Edge work can support asynchronous archive notices and retries. The integration catalog supplies no evidence these will accelerate the synchronous verifier.
- S3, Iceberg, ClickHouse and cloud warehouse wrappers need an actual research scan benchmark. They add external availability and access dependencies. The earlier isolated tests and hosted readback remain the performance evidence.

### Card inventory and official documentation

Each row is a distinct project card. The Overview column separates fresh page observations from catalog and prior-November-19 evidence.

| Card | Fresh Overview | First-hop docs | PP fit from earlier technical review |
| --- | --- | --- | --- |
| [Data API](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/data_api/overview) | Full overview | [Opened](https://supabase.com/docs/guides/api) | Private bounded history HTTP after grants/RLS qualification |
| [Grafana Cloud Observability Platform](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/grafana-cloud/overview) | Full overview | [Opened](https://grafana.com/docs/grafana-cloud/observe-and-act/monitor-infrastructure/integrations/integration-reference/integration-supabase/) | Installed label now visible; ~200 Supabase metrics at one-minute cadence; does not automatically instrument PP/prod VMs |
| [Vault](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/vault/overview) | Full overview | [Opened](https://supabase.com/docs/guides/database/vault) | Installed; future hosted consumer credentials; secrets not opened |
| [Cron](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/cron/overview) | Full overview | [Opened](https://github.com/citusdata/pg_cron) | Hosted periodic summaries/reconciliation after explicit scheduling contract |
| [Queues](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/queues/overview) | Full overview | [Opened](https://github.com/pgmq/pgmq) | Secondary cloud work queue; cannot replace offline VM outbox |
| [Airtable Wrapper](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/airtable_wrapper/overview) | Full overview | [Opened](https://supabase.com/docs/guides/database/extensions/wrappers/airtable) | Operational planning data only; no archive need |
| [Auth0 Wrapper](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/auth0_wrapper/overview) | Full overview | [Opened](https://supabase.com/docs/guides/database/extensions/wrappers/auth0) | Identity research only; no market archival benefit |
| [BigQuery Wrapper](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/bigquery_wrapper/overview) | Full overview | [Opened](https://supabase.com/docs/guides/database/extensions/wrappers/bigquery) | Optional remote research warehouse SQL; separate warehouse cost |
| [Cal.com Wrapper](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/cal_wrapper/overview) | Full overview | [Opened](https://supabase.com/docs/guides/database/extensions/wrappers/cal) | Scheduling data; no current archive need |
| [Calendly Wrapper](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/calendly_wrapper/overview) | Full overview | [Opened](https://supabase.com/docs/guides/database/extensions/wrappers/calendly) | Scheduling data; no current archive need |
| [Clerk Wrapper](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/clerk_wrapper/overview) | Full overview | [Opened](https://supabase.com/docs/guides/database/extensions/wrappers/clerk) | External identity data; no current archive need |
| [ClickHouse Wrapper](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/clickhouse_wrapper/overview) | Full overview | [Opened](https://supabase.com/docs/guides/database/extensions/wrappers/clickhouse) | Potential analytics pushdown; docs/overview disagree on aggregate pushdown; measure |
| [Cloudflare D1 Wrapper](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/cfd1_wrapper/overview) | Full overview | [Opened](https://supabase.com/docs/guides/database/extensions/wrappers/cloudflare-d1) | External SQLite-like dataset federation; no durable archive substitution |
| [Cognito Wrapper](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/cognito_wrapper/overview) | Full overview | [Opened](https://supabase.com/docs/guides/database/extensions/wrappers/cognito) | External user pool federation; no current archive need |
| [Database Webhooks](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/webhooks/overview) | Full overview | [Opened](https://supabase.com/docs/guides/database/webhooks) | Optional secondary-job wakeup after durable record exists |
| [Firebase Wrapper](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/firebase_wrapper/overview) | Full overview | [Opened](https://supabase.com/docs/guides/database/extensions/wrappers/firebase) | External app data federation; no current archive need |
| [GraphQL](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/graphiql/overview) | Full overview | [Opened](https://supabase.com/docs/guides/database/extensions/pg_graphql) | Alternative bounded query surface after grants/RLS; no executed queries |
| [HubSpot Wrapper](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/hubspot_wrapper/overview) | Full overview | [Opened](https://supabase.com/docs/guides/database/extensions/wrappers/hubspot) | CRM integration; no current archive need |
| [Iceberg Wrapper](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/iceberg_wrapper/overview) | Full overview | [Opened](https://supabase.com/docs/guides/database/extensions/wrappers/iceberg) | Future cold analytical tables; separate ingestion/catalog needed |
| [Logflare Wrapper](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/logflare_wrapper/overview) | Full overview | [Opened](https://supabase.com/docs/guides/database/extensions/wrappers/logflare) | Potential archive error/latency correlation with logs; full results use memory |
| [Microsoft SQL Server Wrapper](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/mssql_wrapper/overview) | Full overview | [Opened](https://supabase.com/docs/guides/database/extensions/wrappers/mssql) | External research source only if adopted |
| [Notion Wrapper](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/notion_wrapper/overview) | Full overview | [Opened](https://supabase.com/docs/guides/database/extensions/wrappers/notion) | Rules/research notes possible later; not market evidence authority |
| [Orb Wrapper](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/orb_wrapper/overview) | Full overview | [Opened](https://supabase.com/docs/guides/database/extensions/wrappers/orb) | Usage billing; no current archive need |
| [Paddle Wrapper](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/paddle_wrapper/overview) | Full overview | [Opened](https://supabase.com/docs/guides/database/extensions/wrappers/paddle) | Payments; no current archive need |
| [Redis Wrapper](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/redis_wrapper/overview) | Full overview | [Opened](https://supabase.com/docs/guides/database/extensions/wrappers/redis) | External cache SQL does not replace local hot cache; full reads use memory |
| [S3 Vectors Wrapper](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/s3_vectors_wrapper/overview) | Full overview | [Opened](https://supabase.com/docs/guides/database/extensions/wrappers/s3_vectors) | Semantic similarity after justified embedding workload; not exact archive |
| [S3 Wrapper](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/s3_wrapper/overview) | Full overview | [Opened](https://supabase.com/docs/guides/database/extensions/wrappers/s3) | Read-only CSV/JSONL/Parquet scans; compressed files fully in memory; scoped-JWT compatibility unproven |
| [Slack Wrapper](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/slack_wrapper/overview) | Full overview | [Opened](https://supabase.com/docs/guides/database/extensions/wrappers/slack) | External operations discussion research only; no current archive need |
| [Snowflake Wrapper](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/snowflake_wrapper/overview) | Full overview | [Opened](https://supabase.com/docs/guides/database/extensions/wrappers/snowflake) | Optional warehouse research, separate cost/access |
| [Stripe Sync Engine](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/stripe_sync_engine/overview) | Full overview | [Opened](https://github.com/stripe/sync-engine-fork) | Payments replication, no market archive need |
| [Stripe Wrapper](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/integrations/stripe_wrapper/overview) | Full overview | [Opened](https://supabase.com/docs/guides/database/extensions/wrappers/stripe) | Billing SQL, no current archive need |

Fresh browser coverage: 31/31 Overview pages. Public first-hop docs: 31/31. Wrapper management tabs and unsubmitted setup dialogs: 23/23.

### Wrapper management and setup inventory

Each row below had a separate Wrappers tab and its own configuration dialog opened. The controls describe what an administrator would need for a future integration. No credential values were entered, read aloud, or captured in this inventory.

| Wrapper | Setup surface observed |
| --- | --- |
| Airtable | Named server, API credential and foreign-table mapping. |
| Auth0 | Named server, endpoint and API credential or PAT, then mapping. |
| BigQuery | Project and dataset IDs, service account input, then mapping. |
| Cal.com | API URL and credential, then mapping. |
| Calendly | Organization URL, API URL and credential, then mapping. |
| Clerk | API URL and credential, then mapping. |
| ClickHouse | Connection string, manual foreign tables or schema import. |
| Cloudflare D1 | API URL, account and database IDs, API credential, then mapping. |
| Cognito | Region, user pool ID and AWS credential inputs, then mapping. |
| Firebase | Project ID and service account input, then mapping. |
| HubSpot | API URL and credential, then mapping. |
| Iceberg | AWS region, S3 table bucket ARN, namespace and destination schema, with AWS credential inputs. |
| Logflare | API credential and foreign-table mapping. |
| Microsoft SQL Server | Connection string and foreign-table mapping. |
| Notion | API URL and credential, then mapping. |
| Orb | API URL and credential, then mapping. |
| Paddle | API URL and credential, then mapping. |
| Redis | Connection URL and foreign-table mapping. |
| S3 Vectors | Region, endpoint, AWS credential inputs and destination foreign schema. |
| S3 | Region, AWS credential inputs and foreign-table mapping. |
| Slack | Workspace, bot credential and foreign-table mapping. |
| Snowflake | Account, user, key metadata and private-key input, then mapping. |
| Stripe | API URL and credential, then mapping. |

The uninstalled integrations’ enabled management functions remain behind extension or installation gates. Deeper branches inside unsaved configuration forms, generated credential-bearing examples, OAuth authorization, and actions that create or change hosted state were outside this navigation pass.


## TokenBot Auth provider and hook audit

Read-only live Chrome inspection on November 23, 2026, America/Chicago. Opened each of the 25 built-in provider panels individually, checked the 6 third-party setup forms, opened the Custom Provider form and the Passkeys screen, and inspected all four available hook forms. The audit captured field labels and status badges. Provider credentials, account details, and project data are outside this inventory. No changes were submitted.

### Sign In / Providers

The main tab exposes User Signups, default auth confirmations, manual identity linking, anonymous sign-in, built-in Auth Providers, and Custom Providers. The adjacent Third-Party Auth tab is separate. Email is the only built-in card marked Enabled. All other built-in cards below were Disabled. [Sign In / Providers](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/auth/providers) · [Identity linking](https://supabase.com/docs/guides/auth/auth-identity-linking) · [Anonymous sign-ins](https://supabase.com/docs/guides/auth/auth-anonymous)

| Card | Panel opened and inspected | Official guide |
| --- | --- | --- |
| Email | Email control, secure email and password changes, current password, leaked password protection, password requirements, magic links and email OTP parameters. Secure email change and magic links/email OTP were checked. | [Password-based Auth](https://supabase.com/docs/guides/auth/passwords) · [Password security](https://supabase.com/docs/guides/auth/password-security) |
| Phone | SMS-provider selector, SMS provider credential fields, confirmations, OTP expiry and length, message template, and test-number entry. | [Phone login](https://supabase.com/docs/guides/auth/phone-login) |
| SAML 2.0 | SSO enablement, metadata URL, and encrypted assertion option. | [SAML SSO](https://supabase.com/docs/guides/auth/enterprise-sso/auth-sso-saml) |
| Web3 Wallet | Ethereum and Solana sign-in options. | [Web3 authentication](https://supabase.com/docs/guides/auth/auth-web3) |
| Apple | Client IDs, OAuth configuration and callback, and option to accept accounts without email. | [Supabase Apple guide](https://supabase.com/docs/guides/auth/social-sign-in/auth-apple) · [Apple Sign in with Apple JS](https://developer.apple.com/documentation/signinwithapplejs) |
| Azure | Application client ID, credential input, Azure Tenant URL, email option, and callback. | [Azure](https://supabase.com/docs/guides/auth/social-sign-in/auth-azure) |
| Bitbucket | OAuth key/credential fields, email option, and callback. | [Bitbucket](https://supabase.com/docs/guides/auth/social-sign-in/auth-bitbucket) |
| Discord | OAuth application fields, email option, and callback. | [Discord](https://supabase.com/docs/guides/auth/social-sign-in/auth-discord) |
| Facebook | Facebook client application fields, email option, and callback. | [Facebook](https://supabase.com/docs/guides/auth/social-sign-in/auth-facebook) |
| Figma | OAuth application fields, email option, and callback. | [Figma](https://supabase.com/docs/guides/auth/social-sign-in/auth-figma) |
| GitHub | OAuth application fields, email option, and callback. | [GitHub](https://supabase.com/docs/guides/auth/social-sign-in/auth-github) |
| GitLab | Application ID, self-hosted GitLab URL, email option, and callback. | [GitLab](https://supabase.com/docs/guides/auth/social-sign-in/auth-gitlab) |
| Google | Client IDs, nonce-check option, email option, and callback. | [Google](https://supabase.com/docs/guides/auth/social-sign-in/auth-google) |
| Kakao | OAuth application fields, email option, and callback. | [Kakao](https://supabase.com/docs/guides/auth/social-sign-in/auth-kakao) |
| KeyCloak | Client ID, Realm URL, credential input, email option, and callback. | [Keycloak](https://supabase.com/docs/guides/auth/social-sign-in/auth-keycloak) |
| LinkedIn (OIDC) | OAuth application fields, email option, and callback. | [LinkedIn](https://supabase.com/docs/guides/auth/social-sign-in/auth-linkedin) |
| Notion | OAuth client ID and credentials, email option, and callback. | [Notion](https://supabase.com/docs/guides/auth/social-sign-in/auth-notion) |
| Twitch | OAuth application fields, email option, and callback. | [Twitch](https://supabase.com/docs/guides/auth/social-sign-in/auth-twitch) |
| X / Twitter (OAuth 2.0) | Current client ID, credentials, email option, and callback. | [X / Twitter](https://supabase.com/docs/guides/auth/social-sign-in/auth-twitter) |
| Twitter (Deprecated) | Separate legacy OAuth panel and callback. | [X / Twitter](https://supabase.com/docs/guides/auth/social-sign-in/auth-twitter) |
| Slack (OIDC) | Current client ID, credentials, email option, and callback. | [Slack](https://supabase.com/docs/guides/auth/social-sign-in/auth-slack) |
| Slack (Deprecated) | Separate legacy OAuth application panel, email option, and callback. | [Slack](https://supabase.com/docs/guides/auth/social-sign-in/auth-slack) |
| Spotify | OAuth application fields, email option, and callback. | [Spotify](https://supabase.com/docs/guides/auth/social-sign-in/auth-spotify) |
| WorkOS | WorkOS URL, client fields, and callback. | [WorkOS OAuth](https://supabase.com/docs/guides/auth/social-sign-in/auth-workos) |
| Zoom | OAuth application fields, email option, and callback. | [Zoom](https://supabase.com/docs/guides/auth/social-sign-in/auth-zoom) |

The Custom Providers list displayed no configured providers. Search, Provider Type, Status, sorting by Name, Identifier and Type, and the New Provider action were available. The Create Custom Auth Provider form opened. It offered auto-discovery or manual configuration and showed provider identifier, display name, issuer/discovery URLs, OAuth endpoint section, client credentials, scopes, absent-email setting, and callback. Auto-discovery was the default. The manual variant was not selected. [Custom OAuth and OIDC providers](https://supabase.com/docs/guides/auth/custom-oauth-providers)

### Third-Party Auth

The adjacent tab displayed an empty-state prompt to add an authentication provider. The Add Provider menu had six choices, each of which opened a form. These integrations allow a different identity provider's JWTs to be recognized when using supported Supabase product APIs. [Third-party Auth overview](https://supabase.com/docs/guides/auth/third-party/overview) · [Third-party MAU](https://supabase.com/docs/guides/platform/manage-your-usage/monthly-active-users-third-party)

| Integration | Setup form visible fields | Official guide |
| --- | --- | --- |
| Firebase | Firebase Auth Project ID. | [Firebase Auth](https://supabase.com/docs/guides/auth/third-party/firebase-auth) |
| Clerk | Clerk domain. The linked vendor setup page redirects to Clerk sign-in. | [Clerk](https://supabase.com/docs/guides/auth/third-party/clerk) · [Clerk setup](https://dashboard.clerk.com/setup/supabase) |
| WorkOS | Issuer URL. | [WorkOS](https://supabase.com/docs/guides/auth/third-party/workos) |
| Auth0 | Auth0 domain name. | [Auth0](https://supabase.com/docs/guides/auth/third-party/auth0) |
| Amazon Cognito | User Pool ID and AWS region selector. | [Amazon Cognito](https://supabase.com/docs/guides/auth/third-party/aws-cognito) |
| Custom OIDC | Issuer URL. | [Custom OIDC](https://supabase.com/docs/guides/auth/third-party/custom-oidc) |

### Passkeys

Opened the separate Passkeys Beta page. The project’s Enable Passkey authentication switch was off. The public guide documents WebAuthn relying-party and HTTPS origin requirements. Further browser settings behind enablement were not exposed in the observed state. [Passkeys project screen](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/auth/passkeys) · [Passkeys guide](https://supabase.com/docs/guides/auth/passkeys)

### Auth Hooks

The Hooks section offered a create-hook empty state. Add hook opened a menu with four selectable types and two disabled types. Each available type opened its own form. All showed an enable toggle, hook type, schema and function controls in the default PostgreSQL variant. The HTTPS transport option was visible. No transport, schema, or function setting was selected. [Auth Hooks project screen](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/auth/hooks) · [Auth Hooks guide](https://supabase.com/docs/guides/auth/auth-hooks)

| Hook | Dashboard access | Official documentation |
| --- | --- | --- |
| Send SMS | Form opened. | [Send SMS hook](https://supabase.com/docs/guides/auth/auth-hooks/send-sms-hook) |
| Send Email | Form opened. | [Send Email hook](https://supabase.com/docs/guides/auth/auth-hooks/send-email-hook) |
| Customize Access Token (JWT) Claims | Form opened. | [Custom Access Token hook](https://supabase.com/docs/guides/auth/auth-hooks/custom-access-token-hook) |
| Before User Created | Form opened. | [Before User Created hook](https://supabase.com/docs/guides/auth/auth-hooks/before-user-created-hook) |
| MFA Verification Attempt | Menu item disabled. | [Hook availability](https://supabase.com/docs/guides/auth/auth-hooks) |
| Password Verification Attempt | Menu item disabled. | [Hook availability](https://supabase.com/docs/guides/auth/auth-hooks) |

Auth Hooks documentation describes Postgres functions and HTTP endpoints and how Supabase Auth grants execution to its Auth administration role for configured database hooks. These tools may support future user sign-in or token policy. The dashboard pass did not identify a collector or structured verifier speed benefit. [Auth Hooks configuration and permissions](https://supabase.com/docs/guides/auth/auth-hooks)


## TokenBot Supabase browser audit — Database, Table Editor, SQL Editor

Browser audit on November 23, 2026, Chicago time. The inventory describes production dashboard screens read through the signed-in browser. Query execution, creation, migration application, permission changes, restore activation, exports, and feature activation were outside this observation. No row values, credentials, or connection strings are recorded. Privileged forms were inspected as previews when they opened without executing their action.

### Database browser walkthrough

I opened all **14 Database navigation destinations**, both trigger tabs, and all three backup tabs. I opened all **11 visible schema options in Schema Visualizer** one at a time and verified the selected schema each time.

| Screen opened | Nested screens or controls observed | Relevance to TokenBot |
| --- | --- | --- |
| [Schema Visualizer](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/database/schemas) | Individually selected `auth`, `extensions`, `graphql`, `graphql_public`, `history_v2`, `pgbouncer`, `public`, `realtime`, `storage`, `supabase_migrations`, and `vault`. Opened the export menu, which offered Markdown copy and PNG and SVG download alongside the page's Copy as SQL control. | Map archive relationships and view database-native metadata. |
| [Tables](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/database/tables) | Database table list and New table control. The Table Editor pass below opened each of the 22 application table Definition tabs. | The application spans private archive tables and public analytics/legacy tables. |
| [Functions](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/database/functions) | `history_v2` lists `check_revision_envelope` and `source_epoch` as invoker functions. Opened the latter's action menu and Edit panel, including arguments, return type, and Save/Cancel. Its menu offers Duplicate, Edit with Assistant, and Delete. | Relevant to exact timestamps and receipt validation. Function metadata alone does not prove latency. |
| [Data triggers](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/database/triggers/data) and [Event triggers](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/database/triggers/event) | Navigated both tabs. Event Triggers links to documentation on DDL-level hooks. | Data triggers and DDL event triggers have different performance and lifecycle effects. |
| [Enumerated Types](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/database/types) | List and Create type entry point. | Schema maintenance. |
| [Extensions](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/database/extensions) | Extension catalog and linked reference. | Explore query inspection before enabling another extension. |
| [Indexes](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/database/indexes) | `history_v2` list and View definition modal for `structured_receipts_latest_identity_v1_idx`; browser shows B-tree order `(origin_id, entity_type, md5(entity_id), outbox_id DESC)`. Existing primary index shown separately. | The exact deployed index associated with the measured retained-archive verifier improvement. |
| [Publications](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/database/publications) | Publication list and related management entry points. | Useful when assessing logical replication or Realtime table publication; no membership audit was performed. |
| [Policies](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/database/policies) | Individually selected public and `history_v2`. Opened one policy creation form and inspected name, permissive mode, command, and template affordances, then cancelled. Public screen showed tables with no policy rows; history_v2 cards offered Disable RLS, indicating RLS is enabled on those cards. | A dashboard control is not a substitute for negative tests using real roles and grants. |
| [Roles](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/database/roles) | Supabase service roles, project database roles, and Add role entry point. | Distinguish direct database reader/writer credentials from Data API grants and RLS. |
| [Database Settings](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/database/settings) | Connection pooling, SSL, Disk management, Network restrictions, Connection logging, and Network bans sections. Project pool size field displayed 15. | Pool size is one configuration observation. Pool saturation, connection cost, and query round trips must be measured independently. |
| [Pipelines](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/database/pipelines) | Opened Add pipeline, which showed an Enable Pipelines confirmation with usage docs, then cancelled. Opened More actions, showing View Pipelines usage and a disabled Disable Pipelines action. | Warehouse/export research candidate. The setup preview and documentation do not establish performance on the live archive path. |
| [Scheduled backups](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/database/backups/scheduled), [Point in time](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/database/backups/pitr), [Restore to new project](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/database/backups/restore-to-new-project) | Scheduled tab displayed physical backups and Restore actions. PITR displayed an add-on requirement. Restore-to-new-project displayed available backups and Restore actions. | Postgres backup includes only metadata for Storage API files. The raw object restore path needs its own evidence. |
| [Migrations](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/database/migrations) | Read migration history and opened the newest View migration SQL modal, then closed it. | Inspect deployed history here and use source-controlled, reviewed migrations for schema changes. |

### Table Editor and individual application tables

Opened and verified the **Definition view of each of the 22 application tables** listed below. The distinct Data view controls include Schema, table tabs, filter, row operations, Add RLS policy, refresh, and Definition versus Data. For `structured_receipts`, also opened its table menu, showing copy name/schema, edit, duplicate, policies, export, and delete. Opened the New table form to its default Columns and RLS controls without saving. The browser initially timed out during the public Definition sweep, then the views were each re-opened and individually verified.

#### Private `history_v2` Definitions

| Table | Definition |
| --- | --- |
| candles | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/45571?schema=history_v2&view=definition) |
| coverage | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/45690?schema=history_v2&view=definition) |
| current_prices | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/45581?schema=history_v2&view=definition) |
| feature_snapshots | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/45607?schema=history_v2&view=definition) |
| generation_checkpoints | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/45682?schema=history_v2&view=definition) |
| markets | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/45556?schema=history_v2&view=definition) |
| outcomes | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/45662?schema=history_v2&view=definition) |
| predictions | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/45643?schema=history_v2&view=definition) |
| protected_evidence | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/45590?schema=history_v2&view=definition) |
| snapshot_evidence | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/45626?schema=history_v2&view=definition) |
| structured_receipts | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/45751?schema=history_v2&view=definition) |
| structured_revision_payloads | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/45992?schema=history_v2&view=definition) |

#### Public Definitions

| Table | Definition |
| --- | --- |
| candles | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/17680?schema=public&view=definition) |
| evaluation_metrics | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/17774?schema=public&view=definition) |
| feature_snapshots | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/17688?schema=public&view=definition) |
| markets | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/17666?schema=public&view=definition) |
| model_outputs | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/17755?schema=public&view=definition) |
| news_events | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/17743?schema=public&view=definition) |
| official_outcomes | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/17728?schema=public&view=definition) |
| predictions | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/17704?schema=public&view=definition) |
| raw_archives | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/17794?schema=public&view=definition) |
| sync_checkpoints | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/17784?schema=public&view=definition) |

### SQL Editor

- Opened [Examples](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/sql/examples) and [Templates](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/sql/templates) individually. Examples includes basic table and end-to-end application starters along with Vector Search. Templates includes DDL, extension and version inspection, active connections, `pg_stat_statements` reports, query frequency and runtime comparisons, hit rate, and replication status.
- Inspected query search, Create a new query entry point, Shared and Favorites folder controls, Private folder, and nested Reference. The expanded Shared and Private folders displayed no queries. The templates and examples were reviewed as catalogs. The individual template actions, which may create or alter a saved SQL draft, were left at the catalog.

### Linked official documentation

The first-hop URLs from the database screens were opened, along with the database backup handbook and the current Supabase changelog.

| Topic | Official documents opened |
| --- | --- |
| Schema and security | [Database functions](https://supabase.com/docs/guides/database/functions), [Event triggers](https://supabase.com/docs/guides/database/postgres/event-triggers), [Postgres extensions](https://supabase.com/docs/guides/database/extensions), [RLS](https://supabase.com/docs/guides/database/postgres/row-level-security) |
| Query performance | [Query optimization](https://supabase.com/docs/guides/database/query-optimization), [Index Advisor](https://supabase.com/docs/guides/database/extensions/index_advisor) |
| Database configuration | [Pooling and limits](https://supabase.com/docs/guides/database/connecting-to-postgres/pooling-and-limits), [Connection management](https://supabase.com/docs/guides/database/connection-management), [SSL enforcement](https://supabase.com/docs/guides/platform/ssl-enforcement), [Database and disk size](https://supabase.com/docs/guides/platform/database-size), [Network restrictions](https://supabase.com/docs/guides/platform/network-restrictions), [Network bans CLI reference](https://supabase.com/docs/reference/cli/supabase-network-bans) |
| Replication and recovery | [Pipeline setup](https://supabase.com/docs/guides/database/replication/pipelines), [Pipeline usage](https://supabase.com/docs/guides/platform/manage-your-usage/pipelines), [Database migrations](https://supabase.com/docs/guides/deployment/database-migrations), [Database backups](https://supabase.com/docs/guides/platform/backups) |
| Recent changes | [Supabase changelog](https://supabase.com/changelog.md), [Correlated Logs Beta](https://supabase.com/changelog/53230-correlated-logs) |

The November 10 changelog adds correlated Logs Beta for request ID, trace ID, and user ID when present, with Timeline or User detail tabs as applicable. This is worth testing for the relevant API and Storage request sequences that expose those identifiers. A direct Postgres query and a verifier's local JSON or hash work still require separate timing unless matching identifiers are actually available.

### Practical findings and boundaries

- Keep the confirmed latest-receipt index as the current measured improvement. Query plan, server execution, transfer, and local verification should be timed on identical pages before proposing another index, pool setting, RPC, or compute change.
- The SQL Editor has diagnostic templates for server-side attribution and the project already exposes pool and connection monitoring. The browser audit did not execute or apply their SQL.
- The inspected setup pages are a navigation audit. Several workflows end at submission, activation, or restore gates. The application table sweep covered every visible table in both project schemas. The follow-up below covers historical migration, publication, and role detail screens.


### Follow-up on historical migrations, roles, and publications

- **[Database Migrations](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/database/migrations)** — Opened all 16 visible **View migration SQL** dialogs individually and confirmed a populated SQL editor in each. The visible history spans October 23 through November 21. No additional page control was visible. The audit records successful renders and avoids capturing stored SQL text.
- **[Database Roles](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/database/roles)** — Expanded all 24 role panels individually, covering 14 protected service roles, the project administrator, the PP history role, and the four pairs of trial reader and writer roles. Each panel displayed all six privilege controls. Opened all 10 project role action menus. The administrator menu had disabled Reset password and Delete controls, and the nine custom role menus offered those same actions. Opened the Active roles filter, the Active connections control, and the Add role form. The connection control exposed no additional screen when clicked. Closed the blank Add role form without submitting. The active snapshot showed five connected roles and 11 of 60 connections.
- **[Realtime publication membership](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/database/publications/16430)** — Opened the only visible publication and all 11 schema choices individually. Its Insert, Update, Delete, and Truncate settings were checked, and no table membership was enabled. The membership browser showed 64 candidate tables across auth (27), history_v2 (12), public (10), storage (10), realtime (3), supabase_migrations (1), and vault (1). Extensions, graphql, graphql_public, and pgbouncer showed empty results. The unlabeled publication-name button produced no separate screen. The observed membership means this publication had no tables to emit via Postgres Changes when inspected. It does not establish whether the app uses Broadcast or Presence.
- **Remaining boundaries** — Credential reset, role deletion, saving privilege changes, and toggling publication events or membership are operations outside this read-only sweep. System-table definitions outside the 22 application definitions and live SQL template execution remain outside this specific follow-up.


## TokenBot Query Performance and Advisor detail follow-up

Read-only Chrome checks on November 23, 2026, America/Chicago. This follow-up resolves the detail-opening limitation in the first observability pass. The grid rows use no independent visible rectangle. Selecting a visible cell opened the respective panel.

### Query Performance

Opened a loaded query record’s Query details panel via its visible first cell. The panel has a Query details tab with time consumed, calls, maximum/mean/minimum time, cache hit rate, and role. The selected record’s database query text and parameters were excluded from the audit. Explain with AI is a separate control. The Enable Index Advisor banner and Enable action were visible. Neither action was used. The screen confirms that a live verification window can be correlated with server-side statement observations. It does not establish that any sampled query came from the PP verifier. [Query Performance dashboard](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/observability/query-performance) · [Performance tuning](https://supabase.com/docs/guides/platform/performance#examining-query-performance) · [pg_stat_statements](https://supabase.com/docs/guides/database/extensions/pg_stat_statements)

### Performance Advisor

Opened the Info tab and all four Unindexed foreign keys detail panels for `history_v2`. Each displayed an Issue section, the unindexed foreign keys explanation, and the linked linter documentation. The reported constraint names are shown here as schema metadata. [Performance Advisor](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/advisors/performance) · [Unindexed foreign keys rule](https://supabase.com/docs/guides/observability/advisors?queryGroups=lint&lint=0001_unindexed_foreign_keys)

| Table | Constraint reported without a covering index |
| --- | --- |
| `history_v2.outcomes` | `outcomes_origin_id_evidence_id_market_id_fkey` |
| `history_v2.predictions` | `predictions_origin_id_snapshot_id_market_id_as_of_fkey` |
| `history_v2.protected_evidence` | `protected_evidence_origin_id_market_id_fkey` |
| `history_v2.snapshot_evidence` | `snapshot_evidence_origin_id_evidence_id_fkey` |

These four lints concern foreign-key coverage. To estimate a speed benefit for PP, compare the actual predicates and plans on the exact verifier statements and measure lookup time and write overhead.

### Advisor Center

Opened the toolbar Advisor Center. The panel surfaced potential database issues and displayed diagnostic entries that can be expanded individually. It surfaced public and signed-in eligibility to execute a security-definer function. This was a dashboard advisory observation, with no execution or grants checked. No suppression or remediation was applied. [Advisors documentation](https://supabase.com/docs/guides/observability/advisors)


## TokenBot system-table Definition audit

This read-only follow-up used the [project Table Editor](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor) in Chrome. It uses the [publication table inventory](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/database/publications/16430) as the denominator for physical tables. That inventory omits views. The main database audit separately verified all 22 application-table definitions.

| Schema | Physical tables in publication inventory | Individually confirmed Definition screens | Coverage detail |
| --- | ---: | ---: | --- |
| `auth` | 27 | 27 | The follow-up verified all five previously timed-out Definitions. Direct links are listed below. |
| `storage` | 10 | 10 | The follow-up verified all four previously timed-out Definitions. Direct links are listed below. |
| `realtime` | 3 | 3 | Confirmed `messages`, `schema_migrations`, and `subscription`. |
| `supabase_migrations` | 1 | 1 | Confirmed `schema_migrations` after recovering the browser tab. |
| `vault` | 1 | 0 | Located `secrets` and the `decrypted_secrets` view in Table Editor. Normal table navigation initially opens Data, and the inspection did not open either secret-bearing relation. |
| `extensions`, `graphql`, `graphql_public`, `pgbouncer` | 0 | 0 | Each was previously opened in Schema Visualizer and in Publication Membership. Publication Membership displayed no physical tables. This follow-up did not verify individual views or empty states in Table Editor for these schemas. |

The confirmed total is **41 of 42 physical system table Definition screens**, in addition to all 22 application table Definitions. For each of the nine recovered views, Chrome showed the selected schema-qualified table tab, the exact table name under SQL Definition, and a matching rendered `CREATE TABLE` statement. `vault.secrets` remains at list-level evidence. The `vault.decrypted_secrets` view is outside the physical-table count. No Data grid output was collected, no secret values were captured, and no project settings changed.

| Recovered table | Verified Definition |
| --- | --- |
| `auth.schema_migrations` | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/16537?schema=auth&view=definition) |
| `auth.scim_tokens` | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/17198?schema=auth&view=definition) |
| `auth.scim_users` | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/17167?schema=auth&view=definition) |
| `auth.sessions` | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/16716?schema=auth&view=definition) |
| `auth.sso_domains` | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/16803?schema=auth&view=definition) |
| `storage.migrations` | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/17262?schema=storage&view=definition) |
| `storage.objects` | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/17280?schema=storage&view=definition) |
| `storage.s3_multipart_uploads` | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/17329?schema=storage&view=definition) |
| `storage.s3_multipart_uploads_parts` | [Open](https://supabase.com/dashboard/project/xttdqeimdujweijxcuro/editor/17343?schema=storage&view=definition) |
