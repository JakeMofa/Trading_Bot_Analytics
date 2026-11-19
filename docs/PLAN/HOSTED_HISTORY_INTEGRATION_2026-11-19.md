# Hosted history integration research and offline prototype

Reviewed November 19, 2026. Decision: keep current hot RAM/local PostgreSQL and
private `history_v2`/authenticated raw Storage. Prototype only an explicit bounded
structured cold read over known immutable revisions. Do not add a Data API
surface, deploy RPC, create replication slots, change permissions, activate a
paid feature or promote this candidate during the pp17 freeze.

## Evidence and actual application gap

`backend/postgres/api.py` serves `/history/predictions` from local PostgreSQL,
while `runtime_history.py`/`history.py` retrieve archived `raw.events` only.
`HistoryV2PostgresTransport.read_revisions()` already recovers exact structured
outbox IDs with authenticated receipt/canonical-envelope validation. There is no
structured cold-history application query contract using that capability. Neither
nonempty local predictions nor raw replay automatically supplies old saved
feature/prediction/outcome revisions.

The existing measured PP receipt-metadata comparison reduced average elapsed
read time from 632.35 ms cold to 378.34 ms including first-use setup with reuse;
it does not measure full cold-history payload retrieval or prove another hosted
product would be faster. No performance claim is attached to this prototype.

## Product choices and direction

| Mechanism | Direction and access | Decision for this application |
|---|---|---|
| Existing private direct PostgreSQL | PP outbox importer writes ordered projections/receipts; separate bounded authenticated reads verify exact immutable revision IDs | Reuse existing private storage contract; do not mount a writer merely to add an API cold reader |
| Restricted Data API | HTTP client reads explicitly exposed objects, subject to grants and RLS | Future reviewed API schema could expose selected historical fields; current `history_v2` stays unexposed and tables remain private |
| Postgres RPC | Client invokes a granted database function; invoker uses caller privileges | A future invoker-only bounded query could reduce round trips; no function deployed, no definer bypass or PUBLIC execution added |
| Storage HTTP / S3 | Exact object retrieval for verified raw evidence | Keep current authenticated GET and independent hash/count checks; S3 is another protocol, not an extra settlement source or relational history engine |
| Managed Pipelines | Hosted Supabase Postgres publication feeds an external destination through logical replication | Does not replace local PG outbox → private Supabase imports or provide cold query access |
| Open-source ETL | Operator-run Postgres initial-copy/CDC engine with built-in/custom destinations | Separate infrastructure experiment, not automatically available managed ingestion or this prototype |

Data API exposure needs object grants plus row policies. Default object grants
and function execution warrant separate review; hiding `history_v2` is deliberate.
A dedicated API schema could expose a constrained query while leaving storage
private, but requires qualification of exact role, origin predicates, result
bounds and API grants. This proposal performs none of those steps.
[Supabase Data API security](https://supabase.com/docs/guides/api/securing-your-api)

An RPC's default invoker behavior preserves the caller's privileges; it does
not itself create a read-only contract. Restrict EXECUTE, use bounded SELECT
semantics and validate origin/market/time. A SECURITY DEFINER shortcut would
expand privilege and is unnecessary for this choice.
[Database functions](https://supabase.com/docs/guides/database/functions)

Generated S3 access keys bypass Storage RLS across buckets. A JWT session-token
path respects RLS; current docs require the legacy anon key for its S3 secret
parameter and do not yet support publishable keys there. Do not create a broad
S3 key to replace the existing narrowly scoped HTTP reader. Storage object
integrity remains a separate contract from relational receipts.
[S3 authentication](https://supabase.com/docs/guides/storage/s3/authentication)

Current hosted Pipelines setup/FAQ identifies Supabase Postgres as source and
BigQuery as the managed destination, says Analytics Buckets replication is no
longer supported, and labels the feature private alpha. Those hosted-specific
pages control this decision; availability must be verified before planning a
new destination. [Pipelines setup](https://supabase.com/docs/guides/database/replication/pipelines),
[Pipelines FAQ](https://supabase.com/docs/guides/database/replication/pipelines-faq)

The open-source ETL README separately lists ClickHouse, BigQuery, DuckLake and
Snowflake modules and custom destination/store interfaces. It describes
initial snapshot/catchup and ongoing ordered CDC with durable checkpoints and
at-least-once delivery. Its release-stage wording differs from hosted FAQ, so
library modules are not treated as evidence that each is enabled in this
project's managed dashboard. [Supabase ETL](https://github.com/supabase/etl)

Logical replication retains WAL while a slot needs it; a stalled consumer can
consume source disk. Replica identity FULL adds old-row WAL volume. Initial
copy/partition root settings, slot invalidation, duplicate replay and DDL need
independent capacity/correctness qualification. This matters with bounded local
A/B generations: blindly replicating deletes/truncates would reproduce lifecycle
retirement instead of preserve immutable cold history.
[Replication](https://supabase.com/docs/guides/database/replication)

## Durable sync and PP/production origin isolation

Preserve durable local outbox → atomic scoped projection + immutable receipt/
revision → independent readback → exact local ACK. Reconcile ambiguous remote
commit outcomes; duplicate replay uses origin/generation/outbox identity and
exact payload/envelope hashes. Neither CDC checkpoint nor successful HTTP status
substitutes for the application's receipts, provenance and retirement proof.
Do not add Realtime delivery or a queue as a second source of archive authority.

PP and production must have separate runtime identities, credentials, local
volumes and permissions; all historical identities/cursors include origin and
generation. A shared hosted project does not make test rows production rows.
The candidate reader accepts only `pp-live-pp`, matching its injected source's
origin/generation. It explicitly rejects production; production read access
needs a separate qualified role/transport, not a changed constant or reused PP
credential. Data API RLS and direct SQL roles require independent validation.

## Smallest useful local prototype

`backend/postgres/cold_structured_history.py` adds an unregistered query service.
The caller supplies a scoped receipt-verifying source and an independently
reviewed list of exact outbox IDs/envelope SHA256 values. It pages at most 50
records/256 KiB/four seconds, with no arbitrary SQL, discovery or hidden fallback.
Request scope is one origin/generation/entity type/market; continuation binds to
the whole reviewed manifest and scope digest. It supports saved features,
predictions and outcomes and preserves every original revision, decimal string,
source/receive/available/as-of field and NULL without relabeling history as live.

Each page rejects wrong scope, missing/reordered rows, changed envelope hashes,
oversize output and unavailable source. It reports only a bounded reviewed-ID
page and whether the supplied manifest has more IDs; it never claims complete
market or time-range coverage. It creates no outbox ACK, checkpoint or local
import and grants no retirement authority. Manifest authenticity and the
receipt-verifying source are caller prerequisites, not proven by mock tests.

Generated tests exercise 51 revisions/two pages, exact decimal text, original
record equality, scope/cursor isolation, corruption, missing rows, deadlines,
byte limits, unavailable source and zero calls for invalid requests. Run:

```sh
python3 -m unittest discover -s backend/tests -p 'test_cold_structured_history.py' -v
```

Remaining gaps: no live reader-specific SQL grant, structured catalog discovery,
API/browser wiring, manifest exporter/authentication, local import/cache,
production qualification or measured payload latency. None is implied by this
prototype. Add a separately reviewed admission/rate limit before server exposure.

## Mutation paths and the freeze limit

This inventory is based on dashboard observation and release-owner description,
not a complete credential-holder enumeration. No admin freeze is established
by RLS, a disabled feature or the narrow reader's successful negative tests.

| Principal/path | Capability described/observed | Freeze limitation |
|---|---|---|
| PP API history reader | Restricted authenticated exact raw GET | Does not constrain an administrator or SQL role capable of replacing policy |
| Scoped PP Storage writer | Create-only upload and GET qualified by release owner | Permitted creates are mutations; worker/process ownership still matters |
| PP structured role/worker | Scoped private history insert/update/import privileges | Recurring or one-shot jobs can mutate allowed cloud rows; inventory active processes and held credentials |
| Hosted service_role / master secret | Privileged Auth/Storage operations beyond reader constraints | Release owner reports operator CLI only, never mounted on PP; holder inventory unverified |
| Studio/project administrators and management SQL | Change data, grants, RLS, Auth identities and project settings | Dashboard access remains a mutation path; read-only audit is behavior, not enforced revocation |
| Storage owner / privileged SQL connection | Object/policy/database changes with sufficient privileges | Reader RLS cannot attest these owners are frozen |

Before any retirement proof requires a privileged-mutation freeze, the authorized
operator must attest all relevant human/automation holders, credentials and
management paths, active worker states, effective start/end times and exceptions.
Unattested human controls remain OPEN. Do not claim the freeze from this audit,
write a release/retirement authorization ticket, revoke credentials or change
settings as a side effect of documentation.

## Changelog check and implementation boundary

The [changelog index](https://supabase.com/changelog.md) was checked. Relevant
HTTP TLS cipher retirement affects Data API/Auth/Storage, not direct PostgreSQL
or pooler connections; use modern client TLS rather than weaken checks.
[Cipher change details](https://supabase.com/changelog/cbc-tls-ciphers-deprecated)
No CLI upgrade/migration/install was used. November 4 CLI v3 changes and the
September Pipelines rename are relevant to future tooling, not executed here.
All research is read-only. This branch is separate from pp17 release evidence
and must remain unmerged during that freeze.
