# AB72 production-readiness checkpoint — November 3, 2026

Frozen integrated baseline remains `61e0008c59696168bdaa043fce6b88e5b22f6d19`,
exact CI41738983997 PASS_SCALED_INTEGRATED. Do not rerun or reinterpret it as
production-scale proof. This successor prepares controls and evidence, not enablement.
**Overall: NOT PROVEN; production stays held. No migration approval is requested.**
Successor SHA/CI are recorded in the completion addendum; this text supplies no CI.

## Fresh bounded read-only evidence

At 2026-11-04T00:07:01Z (November3 local), the existing pinned-host-key/operator-key
SSH route ran read-only metadata in an eight-second outer timeout and three-second
SQLite progress budget. No helper installed, secret displayed, service changed,
COUNT over raw history, ANALYZE, full integrity scan or database copy occurred.
The default SSH configuration initially failed host-key validation; the existing
repository-local pinned known_hosts and operator key resolved it without weakening
verification. No host-key bypass or new trust was added.

| Fact | Fresh evidence / interpretation |
|---|---|
|Legacy main|5,323,907,072 logical and physically allocated bytes|
|Legacy WAL|45,171,712 length;45,178,880 allocated bytes (larger figure used)|
|Main+WAL|5,369,085,952 allocated bytes; SHM98,304 separately|
|Geometry|4096-byte pages;1,299,782 pages;0 freelist;schema_version57|
|Schema|38 non-internal objects; actual legacy schemas retained in private metadata evidence|
|Observation maximum ID|671248, **not a row count**; sparse historical IDs preserved|
|Recent observation payload lengths|32 indexed latest IDs:732..7830 characters,mean7475.34; not a full payload distribution|
|Recent stream payload lengths|32 indexed latest receipts:435..437 characters,mean436.41; not a long-term distribution|
|Actual bounded structured counts|1826markets,18289snapshots,27743predictions,20context links,28news rows|
|Direct outcome-observation references|8distinct targets across those20links; embedded evidence dependencies still need full audit|
|Filesystem free|49,806,835,712bytes, not a renewed ceiling or cap deadline|
|VM memory|1,322,000KiB available of1,951,736KiB at00:08:31Z|

Structured counts were bounded to50001rows/table, two-second SQLite budget and
8-second process timeout; completed in0.007576s. All were below the sentinel, so
these structured counts are exact for that read, unlike raw identities/cursors.
No sqlite_stat1 existed. Exact raw cardinalities, complete embedded references,
production core/index/ledger demand and a real active-day/burst distribution remain
unknown. The two tiny recent samples do not establish them.

Existing archive cursors still match last November2 collection: observation671248,
feature18289,prediction27743; stream cursor is timestamp/composite-key based. Cloud
cursor agreement does not prove complete archive/decommission coverage. No missed
collection is assumed backfilled. Production remains on its stopped old layout.

## Capacity: separate measurements, stress assumptions and decisions

The selected two72-hour generations need approximately144hours of raw storage.
Existing80.154s physical growth9402.65B/s and logical12110B/s are short-window whole-
DB measurements, not segmented rates. The selected preliminary floor20KiB/s gives
10,616,832,000bytes/144h before separately unmeasured core demand. Existing2GiB
workspace cannot contain even that raw estimate or retained5.37GB legacy allocation.

`backend/prototype/readiness_workload.py` freezes an **unexecuted resource proposal**:
720000observations,12200000stream events, the five declared observation shapes and
three stream shapes,1826markets,18289snapshots,27743predictions,20direct links/8targets.
These raw counts are conservative stress assumptions, not inferred production
counts. Generated content must use actual schema/provenance/decimal/reference forms;
never populate fixtures by copying production. Embedded evidence cardinality is a
missing fact, never invented as zero. Maximum sampled lengths inform shape, not a
claimed maximum permitted production record. UTF-8 encoded bytes must be measured
when generating; these character counts alone do not certify byte allocation.

| Proposed generated resource term | Bytes / basis |
|---|---:|
|Retained generated legacy allocation target|5,369,085,952; fresh physical metadata|
|Raw payload target|10,969,000,000; fixed counts times largest fixed shape|
|Raw index allowance|10,969,000,000;100%payload hypothesis, NOT measured upper bound|
|Persistent identity ledger allowance|6,615,040,000;512B/event hypothesis, NOT measured production slope|
|Legacy audit/ID maps and other structured/protected evidence|2,147,483,648; explicit hypothesis/cap, not omitted|
|Aggregate WAL|1,073,741,824; proposed measurement cap, not production qualification|
|Archive/TEMP|2,147,483,648; filesystem working term|
|Recovery|1,073,741,824; separate reserve including >=512MiB physical headroom|
|Total assumptions|40,364,576,896 (37.592GiB)|

Proposed **generated-only** workspace ceiling40GiB (42,949,672,960bytes), with10GiB
additional actual filesystem-free floor; total required free space before start
50GiB (53,687,091,200bytes). Keep512MiB AS/process, at most2processes, one serial
feature worker, one collector; require >=1.5GiB available host RAM and one CPU core
maximum. Proposed one48-hour absolute wall deadline includes export, preparation,
all requests/readback/recovery/report; no clock reset, automatic retry or soak.
Original99.69rows/s small-workload throughput extrapolates about36hours for12.92M
new events before extra large-fixture preparation; it cannot promise48h completion.
STOP if any fixed quota, backlog/latency/durability gate or original cloud deadline
fails. A profile timing out is NOTPROVEN, not permission to enlarge it again.

These limits are proposals only. Current2GiB/512MiB/170s-work/180s-total harness
limits were not changed, nor was a large trial launched. Existing VM lacks the
50GiB free-space prerequisite by3,880,255,488bytes and available-memory prerequisite
by250864KiB. Operator Mac had33,883,201,536bytes available (df sample), also below
50GiB by19,803,889,664bytes. Neither recorded host currently qualifies. No deletion,
resource provisioning, service stop or filesystem expansion was used to make room.
Before executing an amended profile, an existing approved host must meet these
fresh prerequisites; permission alone cannot repair insufficient resources.

**Production normal/migration ceilings remain NOT DERIVED.** The stress terms
would imply31GiBnormal/36GiBmigration, excluding2GiBnon-DB working space, but these
are arithmetic consequences of unqualified assumptions, not replacement approved
caps. The prior16/21GiB proposals cannot be defended from this stronger stress
model. Core identity history persists beyond144h: neither31 nor16GiB is a permanent
capacity promise. Measure ledger/protected growth and select a finite planning
horizon/expiry before choosing final ceilings. Full slots or blocked retirement
hold ingestion, retaining both generations; no third slot, hidden queue or credit
for internal free pages. No automatic deadline extension.

## Deployed Supabase compatibility

Read-only connector queries against existing TokenBot project
`xttdqeimdujweijxcuro` found the expected schema and cursors matching local evidence:
markets.id PK; snapshots.source_id PK and(market_id,as_of,version)unique;
predictions.source_id PK and(snapshot_source_id,model_version)unique;
raw_archives(bucket,object_path)unique;sync_checkpoints.dataset PK. Target/final
are NUMERIC; existing probabilities remain double, original exact provenance is
retained by the adapter. Metadata JSONB can carry generation identity; existing
historical rows do not by themselves prove new generation semantics.

Bucket`market-raw` is private. Two bounded latest manifests are gzip/application-
jsonl,4584/5000events,267950/292195compressed bytes, verified_at present and metadata
verification=`authenticated_readback_sha256`. This is **stored historical evidence**,
not a fresh authenticated HTTP object read using the runtime identity. No object
body, credentials or private raw payload entered reports. Initial read filtered by
source='observations' returned no rows: deployed source is provider identity (latest
coinbase), dataset is in metadata; adapter already preserves that distinction.

All eight inspected tables have RLS enabled; service_role catalog SELECT/INSERT/UPDATE
grants are present. These catalog grants do not identify or authenticate the runtime
key and do not prove HTTPwrite/concurrent behavior. No grants or policies changed.

Read: PASS for inspected metadata/schema/cursors. Fresh runtime private-object
HTTPread: NOTPROVEN. Write/RLS/concurrent conditional insert/ambiguous write:
NOTPROVEN; no real cloud mutations performed. Existing MockTransport cases remain
valid, not substituted. Management-connector SQL privilege is not runtime privilege.
[Supabase private bucket access model](https://supabase.com/docs/guides/storage/buckets/fundamentals)
requires authenticated access; the changelog/docs were reviewed, no SDK/schema or
permissions change introduced. No AWS S3 infrastructure is proposed.

### Prepared synthetic cloud operation — requires separate explicit permission

One operation in the existing project/bucket using exact namespace
`ab72-readiness/2026-11-03-v1/`, dataset`ab72_qualification:2026-11-03-v1`, market IDs
`ab72-qualification-20261103-{1,2}`, and synthetic source IDs
-720000000001 through-720000000008. Preflight GET each exact identity: if any exists,
STOP without overwrite or automatic retry under another prefix. Never advance a
real archive/checkpoint cursor or update existing production records.

Exact eight-row maximum:2markets,1snapshot,1prediction,2rawmanifests,1isolated
checkpoint and1news event. Initial creation must be conditional insert-only even
for mutable tables: no merge-upsert may overwrite a hidden pre-existing identity.
An existing or unreadable conflicting identity is STOP. Later same-identity probes
are confined to proven test-owned records with exact evidence reconciliation.

At most2objects,65536bytes/object; at most8synthetic structured/manifest/checkpoint
rows,16384encoded bytes/row; at most60HTTPattempts and180seconds across preparation,
all operations/retries/readback/response processing/cleanup. Keep <=3attempts only
for classified safe GETs,10seconds per logical operation bounded by original180s
outer deadline. Writes remain conditional/single-attempt; emulate a dropped
response in the client only after a sent request and reconcile exact server state.
Concurrent identical/conflicting attempts use two owned children within existing
512MiB/process and outerdeadline; one winner, no conflicting overwrite/cursoradvance.
Use actual existing SupabaseHTTP/wire path and exact decimals/original provenance,
not direct SQL to bypass RLS. No permission grants, signed-public URLs or SDK install.

Cleanup, **only if expressly approved with the synthetic test**, may remove only
those exact newly created synthetic identities after hash/body comparison and FK-
ordered reconciliation. No prefix-wide/wildcard deletion, production record or
private historical object removal. On identity mismatch/ambiguous cleanup/deadline,
preserve at most those2objects/8rows, report residual exact identifiers, yield; no
background retry. Payload maximum262144bytes plus database/index overhead bounded
by a proposed1MiB test allocation allowance, not claimed host physical measurement.
The bounded live test runner and actual permission evidence are not yet qualified;
this is a precise permission scope, not an instruction to execute it now.

## Verification, cutover and recovery preparation

Reused `maintenance_controller.run`, not another controller. Its old unconditional
code rollback/restart is incompatible with committed A/B writes. Added a default-
off **generated_transition** rehearsal capability: rejects non-private/non-generated
roots and production paths before preflight; starts the original envelope before
preparation; uses512MiBreserve, never the consumed128MiBexception; records transition
intent BEFORE a potentially committing call. The rehearsal binding additionally covers main/WAL device,inode,length,allocated
bytes andmtime, not schema/inode alone. A same-schema data mutation after successful
verification is tested to STOP before transition. This metadata binding still
requires complete quiescence and full checks; it is not a full content hash.
Any failure after intent preserves
files, stops roles, requires forward recovery and never checks out old code or
restarts an unaware writer. Earlier failures also preserve the stopped state.
Normal pinned rollover route/default behavior and existing numeric limits unchanged.
No production CLI/adapter bypass or live path enablement was introduced.

Generated tests run the existing controller with actual legacy fixture,
ApplicationStore, durable collector save and original verifier quick/FK checks on
legacy/core/new raw files. Failures after commit and smoke preserve the exact
committed row and legacy identity. Production paths, inherited128MiBexception and
preflight deadline exhaustion are rejected. This proves generated controller
ordering; it does NOT prove Linux systemd ReadOnlyPaths/old-writer OS isolation,
full-volume import, live service startup or functional HTTPsmoke. Those missing
production host bindings remain a mandatory hold, not mocked as acceptance.

Complete verification still requires complete quick_check andforeign_key_check
for every applicable legacy/core/raw file in owned, bounded children; one consistent
identity/schema snapshot per file, all unchanged across the phase. Existing
release_verification.check_database retains durable per-check start/completion,
PID,active_check,elapsed and finalidentity; timeout/failedcheck remainsSTOP and
partial evidence cannot authorize cutover. Existing owned child process-group
TERM/KILL/reaping tested, no unknown-owner signals. No immutable WAL shortcut,
manual checkpoint or repeated1790s production scan occurred. Exact historical
active check remains UNKNOWN; timeout alone is not corruption.

One future absolute operation envelope must include capacity/release preflight,
helper/authority preparation, pause/drain, complete legacy verification, bounded
streaming reference import, complete core/raw checks, cutover/startup, bounded
functional smoke, helper restoration/authority revocation and recovery. Existing
limits remain1800sverification,600sother,10sreap,180srecovery,2590sabsolute; they are
not renewed authority and are NOT shown sufficient. The generated rehearsal now
charges preflight; the historical production host still needs complete exact
operation bindings and OS legacy-read-only enforcement before it is executable.
Collection is already stopped; no time accounting can turn this outage into a
newly approved2590s deployment. A larger verification/maintenance envelope requires
review with measured evidence, not silent exclusion of preparation or old outage.

The importer now rejects over-bound input after at most10001row visits instead of
COUNT(*) scanning arbitrary raw history; a >10000-row generated legacy test proves
the bound without a full count. It still refuses >10000total legacy rows/128MiBencoded audit and
production paths. Exact structured counts alone exceed10000. This is an explicit
technical prerequisite, not an invitation to remove a check. A bounded streaming
import/audit under the reviewed resource policy and production old-writer guard
must be implemented/qualified before migration approval. Legacy decommission is
not implemented; retained legacy remains counted. Routing and retirement stayOFF.

Before new writes, old-code recovery only after proving compatibility and no
transition intent. After an attempted transition, freeze/preserve/reconcile forward;
never restore DB contents or pretend failed return means no durable commits.
Unreaped child, changed identity, full slots, missing archive/reference or capacity
proof leaves collection stopped. Future smoke is bounded API/currentmarket/source
freshness/advancing persistence/dashboard/SSE/service stability only; no background
soak. Real boundary/multi-cycle acceptance remains NOTPERFORMED.

## Consolidated disposition and next decision

CHECKPOINT: production readiness preparation; completed baseline preserved.
RESULT: NOT PROVEN for migration. Generated control/metadata tests only may pass.
EXACT CANDIDATE / CI: successor completion addendum;61e0008/41738983997 stays frozen.
REPRESENTATIVE VOLUME / CAPACITY: fixed stress proposal prepared; NOTEXECUTED.
SUPABASE READ / WRITE / CONCURRENCY: metadataPASS;runtime HTTP/write/concurrencyNOTPROVEN.
COMPLETE-VERIFICATION: generated full checks/progress/reapPASS;production finishNOTPROVEN.
CUTOVER / RECOVERY: actual generated commit+forward-failurePASS;production routeNOTPROVEN.
PROPOSED NORMAL / MIGRATION CEILINGS: withheld;16/21unqualified,31/36stress-only arithmetic.
TEMPORARY POLICY EXPIRY: no current extension; future review+72h/expiry+96h remain proposals.
MAXIMUM INTERRUPTION / RECOVERY: unchanged2590/180sconstraints; sufficiencyNOTPROVEN.
PRODUCTION CHANGED: no mutation/restart/migration/cleanup/guard/helper installation.
REMAINING GATES: resource host,full-volume streaming/import/evidence audit,runtime cloud,
complete verification timing,guarded live path/old-writer isolation and exact releaseCI.
APPROVAL NEEDED: **no production migration approval requested**. One proposed prerequisite
package is40GiB/48hgenerated-only qualification on an existing host with>=50GiBfree,
>=1.5GiBavailable RAM,512MiB/process,max2processes/oneCPU,plus the narrowly bounded
synthetic cloud operation above. Neither current host meets the storage prerequisites;
no dispatch even if policy is approved until they freshly pass. No existing files
may be deleted to make room without separate authorization. No new infrastructure.
NEXT ACTION: review that prerequisite package/host availability, then finish the
streaming/live-guard implementations and qualify their exact successor. Do not ask
for production enablement while those preceding gates remain unproven.
