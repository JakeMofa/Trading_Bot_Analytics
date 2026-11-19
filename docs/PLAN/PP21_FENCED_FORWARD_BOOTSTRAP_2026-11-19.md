# PP21 fenced forward bootstrap

Status: completed on PP at exact release source `c1da8d688dd8e9b860c473c965feb9099435ef97`.
Migration4, the finite operator bootstrap and separate normal generated CD passed.
Collectors remain OFF; no new live trial or retirement is qualified.

## Observed PP20 state

Read-only inspection confirms the failed PP20 source `b7b4c9f`, exact released
archive `1c45affb…`, and stopped image `sha256:711fcb3f…`. All four application
containers are stopped with restart=no. PostgreSQL 17.12 remains healthy with
migration ledger 1–3. `generated-pp` contains exactly10,000 pending/10,000 total
outbox rows. `pp-live-pp` contains 42,133 acknowledged/zero pending rows. Both
collector states are OFF with no session. Live sealed A retains 28,411 raw rows;
collecting B retains 9,784. Original A is expired and has no renewed retirement
or original-trial authority. Outcomes and both raw generations must survive.

The standard controller requires a running, qualified prior generated profile.
Restarting the old image alone does not make the new generated-storage profile
schema-compatible. The finite operator procedure is separate from normal CD;
it establishes a running new-schema generated/OFF profile before normal CD.

## Controller identity completed

Exact source `0219819cdd49ee34199566443e7a391dff8bb078` passed source CI 44555885698.
The established code-only transfer decoded exact bytes and rejected truncated,
extended and corrupted payloads. It installed controller
`9a7b10324bb9376193a7a5263efd9bd5e40818682f0e2cb77ba84d4373d9081a`, retaining
previous controller `1e10e106…`. Its receipt reports database_changed=false and
authority_created=false. Dedicated deploy-identity run
[44557716430](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44557716430)
passed without database changes. The profile change records this exact binding;
identity qualification alone does not deploy an application.

## Finite operator procedure

`deploy/preprod/pp20_forward_bootstrap.py` is an explicit operator entrypoint;
it is absent from the installed controller bundle and forced deployment command.
It acquires the existing controller lock and refuses active recurring sync,
unused normal deployment/live/probe authorities, any other failed source/archive,
a changed restored transition, any running/auto-restarting old application,
wrong credentials/mounts/networks/resource profile, unexpected origin, changed
A/B identity/count/seal, enabled collector, a non-1–3 ledger, or any departure
from the exact 10,000 pending generated queue. The stopped old image must retain
its exact source label. No PP live or production mode is accepted.

The operator passes a published, exact-CI source archive and its full source and
artifact digests. The entire archive is bounded and validated by the existing
extractor; installed controller modules must equal their archive copies. Before
any irreversible step, a non-mutating database preflight records original source,
raw, generation and outcome fingerprints through the authenticated reader.

Execute additionally requires a separate root-owned, one-use
`/run/tradebot-pp-deploy/forward-bootstrap.json` with exact request bindings,
operation `pp20-fenced-forward-bootstrap`, generated mode, allow_migration=true,
and live collector, paid AI, retention, cloud, retirement and production flags
all false. The existing root authorization nonce, lifetime and exclusive durable
consume rules apply. No normal CD or live authority is produced.

After the potentially long image build, the procedure rechecks the entire pinned
stopped profile/database state and original fingerprints before migration.
The procedure reuses the installed adapter's exact build, fencing, bounded
migration oneoff, generated bootstrap/start and full smoke methods. It requires
migration output exactly `[4]`, unchanged complete migration-preservation
inventory, real generated durable storage/readback before ACK, and the existing
128-slot headroom requirement. It verifies API/SSE/schema/restart/operator checks
without enabling collection. Work is bounded to 600s plus 180s for failure cleanup.
All daemon-side oneoffs remain exact-attempt owned and cleaned by the adapter.

Preservation checks compare every preexisting generated outbox row, excluding
only its permitted genuine ACK timestamp; all live outbox rows retain ACK
metadata. Original raw rows are pinned by their preflight receive-time maximum,
which must be safely in the past; new generated smoke raw rows are additive.
All outcomes and full live core/generation/writer rows remain equal. Generated
generation rows remain equal except an ordinary occupied-slot hold reason.
Migration itself must preserve the full inventory before generated service writes.
No source row, raw partition or outcome is deleted.

Operator staging and fsynced result receipts live under separate
`/var/lib/tradebot-pp/forward-recoveries`, so they cannot become a normal
`candidate-*/controller-journal.json` deployment PASS. Normal exact-source CD
remains required afterward and is the sole new candidate used for live entry.

On any post-migration failure, stop/fence candidate writers, clean exact owned
oneoffs, preserve PostgreSQL and new genuine ACKs, and report any unproven
preservation. Do not restart an old image or restore a database. The old stopped
container IDs are never automatically restarted. Reuse of this operation after
a partial migration is deliberately blocked by its1–3 ledger guard; inspect the
persisted result before preparing a separately reviewed recovery.

## Irreversible compatibility implication

Migration4 advances the checksum/catalog ledger and creates append-only local
generated storage. Older images without migration4 fail current-schema validation.
Any later rollback must keep schema4, all stored envelopes/source/raw/outcomes,
and all newly committed ACKs, using a schema-compatible image with its consumer
disabled if needed. The old saved controller is retained recovery code, not
permission to restore an old database or claim old-image compatibility. No
Supabase schema/data operation, cloud receipt or raw-retirement authority follows
from this local migration.

## Validation and remaining gates

Six targeted guards/fault controls pass: build-time source drift before any
migration, changed stopped profiles, migration
preservation faults, wrong migration versions, live ACK/outcome preservation
failure before smoke, and exact original-row fingerprint scope. Disposable native
PostgreSQL 17 executes the actual authenticated reader state/fingerprint SQL,
verifies unchanged catalog and final migration validation, with zero skips. The
same actual SQL case is included in the full isolated Linux qualification.
All 219 deploy controls pass (six external/native skips); 54 pipeline controls pass.
No full PP20 operator execution is claimed by these source tests. Remaining:
review/merge exact source, exact CI, release publication, operator preflight,
explicit one-use forward execution, normal CD and separately bounded live work.

[Sanitized precondition evidence](evidence/pp21-forward-precondition-2026-11-19.json).

## Completed host execution and independent preservation

The reviewed procedure from PR181 merged as `c1da8d6`. Exact source CI
[44560442424](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44560442424)
passed the actual isolated Linux controller in 259.064s, including API/SSE, schema,
restart ACK persistence, consumed authority rejection and forward-preserving
failure recovery. Exact CI Preprod 44561420990 passed. Source guard/fault controls
and authenticated native reader SQL coverage remain distinct from actual host
execution; the following receipts establish that host execution separately.

Publication
[44561555039](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44561555039)
created `v0.2.0-pp.21`, artifact
`3afcd69a39991791db224b7858b1003ac0d3671659f55446716669ee65c3eebd` and
OCI digest `997227c31b8d43d7aa900e61274a6818528b179f9d7400d8eb470907a0f349a5`.
The actual host preflight passed with database_changed=false and all old profile,
ledger, exact 10,000 pending and retained A/B guards. A separate operation-scoped
root permit was consumed. The operator applied only migration4, performed genuine
generated storage/readback/ACK/headroom, started healthy generated services and
passed full smoke. Its receipt correctly has cd_acceptance=false.

Separate normal CD
[44562705669](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44562705669)
then passed every required runtime check. The final image is
`sha256:880c013e6fd1936be6bfdf2fbd101f1b021357c45a1c454b42c6da7df7831040`.
The earlier operator image `sha256:04e7fdcb…` is not the final deployed image.
Both bind the same exact source/archive; the normal CD candidate is the sole
new completed deployment used for later transitions.

An independent authenticated reader check after normal CD reproduced all initial
preservation fingerprints: all 38,510 original raw rows, all 10,000 original
generated outbox bodies (only genuine ACK timestamps excluded), all 42,133 live
outbox rows including ACK metadata, and all live core, A/B and writer records.
Live A retained 28,411 raw rows and B 9,784. No outcome rows existed; the empty
outcome set stayed unchanged. The independent original-raw cutoff was the
forward authorization issuance, safely before generated services started; it
reproduced the original count and digest exactly.

At that snapshot generated total was 10,416, pending 6,834, headroom 3,166, and
3,582 committed envelopes occupied 9,729,232 logical bytes. A single read-only SQL
snapshot found zero generated ACKs lacking a matching source-equivalent stored
envelope and valid byte hash. Both collectors were OFF with NULL sessions.
The existing local history-reader eligibility was rebound to the final source
and image; its credentials, grants and policy proof stayed unchanged. No cloud
query/index/schema mutation, raw drop, production action or database restore
was performed.

This completes generated PP recovery/deployment. A new live session, 30-minute
collector observation and any retained-A query-plan/performance work remain
separate. Original expired A retirement/trial authority remains denied.
[Sanitized exact receipts and fingerprints](evidence/pp21-generated-forward-deployment-2026-11-19.json).
