# PP21 fenced forward bootstrap

Status: operator source candidate. No migration4 or application restart on PP yet.
The code-only controller replacement and dedicated identity check below are complete.

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

Five targeted guards/fault controls pass: changed stopped profiles, migration
preservation faults, wrong migration versions, live ACK/outcome preservation
failure before smoke, and exact original-row fingerprint scope. Disposable native
PostgreSQL 17 executes the actual authenticated reader state/fingerprint SQL,
verifies unchanged catalog and final migration validation, with zero skips. The
same actual SQL case is included in the full isolated Linux qualification.
All 218 deploy controls pass (six external/native skips); 54 pipeline controls pass.
No full PP20 operator execution is claimed by these source tests. Remaining:
review/merge exact source, exact CI, release publication, operator preflight,
explicit one-use forward execution, normal CD and separately bounded live work.

[Sanitized precondition evidence](evidence/pp21-forward-precondition-2026-11-19.json).
