# PR9 archived application history and cursor reconciliation

November6,2026. Application/storage successor to1cc9e8d, preserving CI ownership.
Reviewed cryptography remediation4c673bf precedes this milestone. No production,
Supabase writes/permissions/schema,guard,service,deadline or infrastructure changes.

## Actual history path

Added explicit `GET /history/archive` with generation,dataset and exact requested
identities. Existing routes/fields/HTTP behavior remain. Default response is
unavailable unless an archive factory is explicitly configured; no production
factory/credentials are installed or enabled. Production wiring remains gated.

The route uses the existing history connection factory and starts a separate
isolated Python subprocess, never a fork of the threaded API process. Private
runtime config is passed over stdin, not command-line arguments/files/logs;
stderr is suppressed. Worker imports exact colocated code with Python-I, receives
the ORIGINAL one-second deadline including startup,requests,body/JSON validation
and response processing. Parent kills/reaps its owned process group on timeout,
including any authenticated-GET child. No outstanding network thread is abandoned.
Linux worker preserves tighter inherited limits and caps address space at512MiB.

History requests are explicit and do not run in discovery,REST collection,live
feature scheduling or live publication. Existing deterministic calculations use
preserved local/core inputs; no automatic remote fallback or fabricated current
values were added. This is not a new service/cache/writer coordinator.

Bounds:100requestedidentities,8objects,10000manifestcatalogentries,existing64MiB
compressed/256MiBdecoded/8MiBline limits;oneMiBresponse and64KiBprivateIPC request.
No complete generation is materialized or copied. Reads validate generation/path,
exact manifest/checksum/size/count/order/identity boundaries,then every returned
row against its durable committed core receipt. Application JSONL preserves original
payload TEXT last; replay preserves that exact text (including decimal lexemes
and whitespace),original fields/source times and provenance. Unsupported lexical
provenance fails closed. It does not normalize old timestamps into fresh input.

Missing/corrupt/late/unverifiable data return HTTP200 with explicit unavailable
reason and empty records, never partial placeholder success. Authorization permits
no raw write or retirement. Returning authenticated archived evidence does not
create a deletion token or invalidate the original final-fresh-readback gate.

Generated endpoint tests use a loopback synthetic authenticated HTTP server;no
Supabase request or structured cloud write is made. The root-only regression uses
the ORIGINAL fresh readback/reference/drain gate to remove a generated raw file,
then calls the real API to retrieve observation/stream evidence. It also checks
deterministic historical calculation equality,protected outcome reference90,
foreign keys,prediction/context history and dashboard availability. Missing,
corrupt and stalled archives expose unavailable states within the two-second probe
gate. Root case is included by a wrapper in the existing root application suite;
no CI workflow files were edited.

Local corrected history run:3tests,2PASS/1Linux-root skip,3.134s. Actual post-unlink
PASS remains dependent on exact-source Linux root CI; a local skip is not evidence.
Main backend run440PASS/22platform skips in42.334s preceded final small isolation/
identity/fixture corrections. Those corrections are covered by affected checks
and final exact-source CI,not mislabelled as tested by the earlier full run.
Final affected selection under cryptography50.0.0:31tests,30PASS/1root skip,4.006s,
including stalled-source cancellation,changed receipt refusal,metadata-only status,
cursor reconciliation,API/rollover/Ed25519 streaming. No full-suite unchanged rerun.

## Historical shared-cursor reconciliation

Explicit idle lifecycle-worker method reconciles ONE sealed generation/dataset,
using authenticated archive bytes plus exact local rows and committed fingerprints.
It verifies a contiguous archived PREFIX,not arbitrary islands;holes,overlap,bad
receipts,changed main/WAL/catalog/state or conflicting exact-generation cursors
hold. It never consults a global/shared cursor as proof. It can recover a partial
archive prefix and leave unarchived suffix rows eligible.

Bounded to8manifests,1000rows/object and original<=30s deadline with SQL progress
expiry. Larger historical scopes HOLD for a separately qualified reconciliation
strategy;no blanket migration PASS. The method checks bindings before remote
checkpoint acknowledgement and before local commit. Remote acknowledgement precedes
local checkpoint installation. A crash after remote ack leaves raw intact;existing
idempotent checkpoint contract permits explicit retry without incrementing twice.
Legacy and historical shared checkpoint rows are not renamed/reset/overwritten.

Tests prove prefix recovery,restart,idempotency,remote-ack/local-commit crash,
remaining suffix eligibility,global-cursor independence and corrupt/gapped/changed
receipt refusal. An initial fake-remote comparison wrongly treated updated_at as
content;test double corrected to use the actual adapter's same_row semantics.
No production/shared state was repaired. Runtime remains default-disabled.

## Historical CI failure and smallest supported status change

439c93b exact pushCI42320474396 FAIL,not pending or PASS. The retained log shows
joint HTTP/SSE probe reading active_buffer=None during archive. API caught a raw
history-worker opening error without its cause;the original error remains UNKNOWN.
Later1cc/7bee application PASS does not establish that historical cause.

Status/SSE previously opened/leased all nonretired raw generations merely to read
active identity. They now read verified-version durable CORE metadata only,requiring
at most one active row. No raw handle is needed for this metadata. Failures remain
None/unavailable with sanitized exception type/SQLite code,not private exception
text. A targeted test makes raw-history opening fail and proves active identity
still comes from core;unsupported core version reports unavailable/diagnostic.
This removes an unnecessary raw-retirement race/dependency;it is not a fabricated
proof of the swallowed historical failure's cause. No retries/gates were loosened.

## One retirement-authorization decision

**Keep the mandatory full fresh readback. Do not accept reusable cached verification
as deletion authority.** Qualify a separate final FULL-PASS retirement checkpoint
only after its overall budget is supported:the same isolated actor would perform
fresh authenticated readback,exact manifest/row/core/protected checks,reader/OS
handle drainage and immediate generation-specific removal with durable intent.
The current background diagnostic still returns retirement_authorized=false;
this proposed final worker integration/budget has NOT been applied.

Ordinary existing application operations use create-only objects,exact duplicate
reconciliation and conflict refusal;there is no application raw-cloud delete path.
That is an application contract,NOT enforceable protection against a compromised
runtime holding service-level credentials. Repository schema grants service_role
CRUD on structured raw_archives/checkpoints;deployed effective Storage/RPC/S3/
administrator capabilities are NOT inventoried by offline tests. RLS does not
constrain service-key/admin bypass.

Necessary review before any cached-proof replacement:inventory effective ordinary
runtime credentials and every mutation route,review least-privilege published-
object/manifest protection,and establish a race-free policy-change fence. Privileged
administrators remain trusted break-glass actors who must disable retirement and
drain/revoke in-flight permits BEFORE mutation/policy changes. If this assumption
is not accepted/enforceable,immutable cached-proof authorization stays BLOCKED.
A periodic policy hash or short token expiry does not close the race. No Supabase
permission/schema change is applied or presumed approved. Administrators/cloud
provider compromise is not solved by application hashes or a fresh GET.

## Coordination and release disposition

CIworker owns .github/workflows and .github/ci in its separate clone/branch.
Preserved1cc9e8d;reviewed42f207c proposed50.0.0 patch and applied only the application
pin in4c673bf. Isolated candidate pipcheckPASS,pip-audit0knownvulnerabilities;
Ed25519/streaming/API/state/rollover/fresh-B checks executed. Local test-selection
and fault-fixture errors remain recorded,not rewritten as successful batches.
PR10's control setup/readiness corrections must qualify with reviewed dependency
base,then merge via the reviewed CI-only PR into THIS working branch only.
No CI-only branch switch,workflow edit,main/deployment merge or dispatch here.

5GiBphysical/slot selected target;24GiBaggregate unqualified proposal;applied legacy
5120MiBSTOP/routing+retirement+paidAI OFF unchanged. Finite100kledger/core/audit and
manifest/reference bounds,representative capacity,outage runway,complete legacy
verification and production path/identity/manual controls remain release blockers.

Cutover+bounded smoke,later first naturally sealed-generation verification,and
retirement enablement remain separate checkpoints. Legacy remains retained until
structured core/Postgres history,source-bound raw manifests/archive readback,
references,reader drainage and post-removal application history qualify;legacy
archive retrieval after its eventual removal is NOT proven by A/B-only replay.
Separate exact-file legacy retirement approval remains required.

I7freshness/realrollover,historyrecovery/replaybeyond qualified scope,visibility,
sustainedoperation and Phase1.75 remainOPEN;Redis/knowledge-RAG/paidAI/Phase2 deferred.
PR9 stays DRAFT. Final exact-source LinuxCI and all readiness checks are required.

## Production verification coverage is a separate gate

CI/mock schema checks do not certify live Supabase drift or actual host files.
Before release,an approved preflight must bind exact project/private bucket/runtime
identity,actual table keys/types/grants/checkpoints and source identities to the
release;no such live query is authorized/performed here. Confirm all legacy/core/
A/B main,WAL,SHM,working files and process-held allocations in ONE aggregate guard.
Record current schema versions,counts/protected dependencies and storage flags;
do not present the old legacy-only controller as full-layout qualification.

During an approved cutover,writer quiescence/fencing and complete required checks
must cover every actual retained/created SQLite file plus cross-file references
and exact selected recovery identities. SQLite foreign_key_check alone cannot
prove cross-database references. Bind post-close/post-fence identity and staged
core/raw integrity before sole-writer activation. Verification/interruption/
recovery budgets and fresh authority remain explicit;no silent skip or extension.

After release,bounded functional smoke must prove advancing source persistence,
current market identity,truthful freshness/API/SSE/dashboard/history and stable
services,plus actual A/B/core/legacy allocation/identity checks. Later first natural
seal/readback and recorded retirement enablement are separate bounded gates.
Supabase/SQLite before/during/after checks are NOT PERFORMED production evidence;
no production operator dispatch/scan/live cloud probe is authorized by this report.

## First exact successor failure and owned-fixture correction

0cef90a6eb2f6fdc1784e6e2deeab431709f3578 pushCI42326920556 FAIL:
https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/42326920556 .
Dependency audit,source/workflow quality and API/SSE contracts PASS. Controls FAIL
because the old isolated job omitted runtime dependencies (websockets import);
CIworker already owns that setup fix. Backend374tests/16skips failed with3errors
in background_verification:hard GET refused a non-single-thread test process.
Root/import/integrated evidence therefore NOT COMPLETED;no post-unlink PASS.

The new stalled loopback HTTP fixture used daemon request handlers;API cancellation
closed its client but the synthetic remote's2s handler could still be alive when
the next verifier test started. Fix ONLY fixture ownership:non-daemon handlers,
block_on_close and owned server shutdown/join. No guard/retry/time limit changed.
History suite followed immediately by background_verification now6tests/5PASS/
1root skip in5.668s;the verifier's guard remains unchanged. Sample after cleanup:
12objects/2011B,0.247752s,19acks,save5.830ms,heartbeat19.795ms,phaseRSS24576000B,
sampledworkspace2438336B. Not a replacement for the slower prior0.616s sample.
macOS emitted the existing fork supervisor's native-thread DeprecationWarning;
no production single-thread/OS-scheduling guarantee is claimed from this run.

Source0cef's302-file/3145273B export passed its direct explicit history API test
in2.487s and exact Git manifest re-verification after subprocess use. Explicit-B
prevents helper imports modifying exported bytes despite-I ignoring environment
bytecode flags. This packaging PASS does not erase source0cef's CI failure.


### Explicit worker admission is bounded

Release review added one nonblocking archive-read semaphore per API instance.
A concurrent request receives explicit archive_history_busy/empty records instead
of spawning another subprocess or queuing archive jobs. Normal/corrupt/cancelled
requests always release the slot. The sole API/collector deployment constraint
remains;this is not a new service or writer coordinator. No live feature path
calls the remote reader. Busy/cancellation/recovery regression plus immediate
history→background verifier run7tests/6PASS/1root skip in8.295s undercrypto50.0.0.
The existing single-thread guard remains untouched. Root post-retirement and full
exact-source Linux qualification still required;no production wiring enabled.
