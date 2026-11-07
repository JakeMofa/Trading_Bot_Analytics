# PR9 generation checkpoints and separate background verification

November6,2026. Baseline13740c7 exact pushCI42316045831 PASS (checked once).
Successor source/CI recorded in completion addendum. No production/cloud changes.

## Checkpoint1 — exact generation progress

Fresh-B selected runtime now uses `archive:ab72:<generation UUID>:<dataset>` for
local and existing Postgres sync_checkpoints rows. Legacy `archive:<dataset>` and
the historical shared `archive:ab72:<dataset>` rows remain untouched. Archive
object paths, private bucket, raw_archives wire format and structured identities
remain unchanged; no Supabase schema or grant change is applied. The checkpoint
name field is existing text, not a new remote table. The old full-import compatibility
route retains its historical semantics; it is not a qualified continuous route.

Each attached raw generation is queried with its OWN cursor; committing verified
archive advances only the exact batch generation/dataset, not a mutable active
slot or global cursor. Selection for summary diagnostics does not authorize a
commit. Mixed-generation batches remain forbidden. Composite stream cursor keys
are compared as binary source/event pairs for the new names as well as legacy.

If existing generation manifests have no generation checkpoint, HOLD for verified
manifest reconciliation. Do not seed from the shared cursor or silently rearchive
with a different overlapping batch partition. No production A/B state currently
exists to migrate; previously generated candidate state needs explicit reconciliation.

New regression archives newer generation BEFORE older pending generation and
proves older rows remain eligible. Other cases cover legacy preservation, actor
restart, rotation, duplicates, late SOURCE timestamps and failed readback leaving
both files and cursor unchanged. Initial receipt-regression fixture error was
correctly refused by the existing writer; test corrected to late source time with
nonregressing receipt time. No admission guard was weakened.

## Checkpoint2 — separate full authenticated readback diagnostic

`background_verification.verify_phase` is generated-only, NOT wired into production
or automatic lifecycle retirement. Parent supervises an entire phase with ONE
caller deadline capped120s. Preparation/cleanup still count toward fixture180s.
Each object suboperation gets <=30s and the remaining phase time. More than eight
objects can be processed across chunks without fitting a whole generation in one
ordinary lifecycle call. Production30s policy remains unchanged.

GET uses existing authenticated/no-store bounded transport, inside the supervised
phase child (no nested network child). Existing gzip JSONL validation reads lines
and validates exact checksum, compressed size, count, identities/order/boundaries,
ack fingerprints, row bodies/provenance and complete manifest/raw/ledger coverage.
No entire generation is materialized; compressed object cap64MiB, decoded object
cap256MiB, line cap8MiB and local scope1000rows remain. Linux phase address space
is capped512MiB; large valid objects may fail closed within this cap. No arbitrary
streaming-format/schema rewrite or large-object success is claimed.

The diagnostic discards its old derived checks before starting a FULL fresh pass;
every object is read again. It binds the initial catalog/local epoch throughout,
and returns `retirement_authorized=false` even on complete verification. It calls
incremental step only with finalize=False. Existing retirement always performs its
own fresh final readback and all reference/drain checks. No cached replacement.

On timeout the parent kills and reaps the owned phase child. On corruption/missing
coverage/uncertain state it returns HOLD/error; no unlink is attempted. A later
explicit diagnostic starts a full pass, rather than treating a killed prefix as
authorization. Tests exercise corruption, a stalled transport, raw preservation
and explicit fresh recovery; this is fault recovery, not unchanged qualification
retry. No periodic/automatic retry was added.

Focused26tests:25PASS/1root-only skip,4.822s. The final combined local sample:

|Measurement|Observed|
|---|---:|
|Objects / one-object chunks|12 /12|
|Verified compressed response bytes|2011|
|Sealed rows verified|12stream /0observation|
|Phase elapsed|0.616007333s|
|Phase peak RSS|24805376B|
|Nested GET child RSS|0 (there is no nested child)|
|Download staging disk|0B (object held in bounded memory)|
|Sampled entire generated SQLite workspace peak|2553696B|
|Concurrent collector acknowledgements|21|
|Maximum save delay|0.085201833s|
|Maximum heartbeat delay|0.175720208s|

Earlier focused sample0.259s/19acks/6.822ms save/21.391msheartbeat is retained as
an earlier observation, not selected instead of the slower combined sample.
Bytes exclude HTTP headers/TLS and unsuccessful retry bodies; normal mock path
has12GETs/no retries. Workspace sampling is not a filesystem allocation/full VM
peak proof and includes core/WAL/sidecars; it excludes in-memory mock archive.
RSS is phase process, not whole CI runner/family peak. No live-network throughput,
5GiB performance, sustained operation or large object memory proof is implied.

**Proposed production phase policy for later review:** separate read-only worker
phase with its own exact generation/catalog/deadline, <=512MiB process memory,
no unbounded request retries, cancellation+reaping and raw preservation; the120s
diagnostic ceiling is NOT a supported5GiB production deadline. Derive that deadline
from qualified representative object volume/throughput/collection headroom before
requesting an amendment. It must not consume or silently extend cutover2590s.

## Checkpoint3 — BLOCKED for replacement authorization

The existing deletion gate is retained. Changed local/remote/catalog/ack evidence
still holds. Prior exact Linux fault/crash/reference/drain tests are reusable;
the diagnostic issues no new unlink permit. Effective mutation protection against
runtime and alternate credentials remains unproven. Privileged service keys/admins
can bypass ordinary RLS; policy snapshots/polls cannot close a mutation/unlink race.
See PR9_MUTATION_AUTHORIZATION_REVIEW_2026-11-06.md for the exact proposed authority
matrix/expiry/crash/change-control protocol and outstanding review. No replacement
is enabled merely because the separate phase completes. Next: sanitized effective
permission inventory and a reviewed enforceable fence, or review a differently
bounded final fresh full-pass gate. No cloud permission/schema changes authorized.

## Checkpoint4 — BLOCKED: actual archive-backed application replay

Existing generated application tests cover legacy/core/A/B calculations and API
history, and root tests cover verified local retirement/ack preservation. They do
not prove automatic archived raw retrieval through calculation/dashboard history
after unlink. Do not label decompressing a fixture as an actual application-path
PASS. Needs bounded provenance-preserving archive retrieval/replay integration,
exact timestamps/identities/reference tests and truthful missing/corrupt states.
Do not connect a slow network lookup to market discovery's critical path.

## Checkpoint5 — exact successor CI required; full checkpoint BLOCKED

Affected/full suites and existing repeated collector/API/SSE/prediction/lifecycle
handoff run on the exact export in Linux CI. New phase fault/concurrent tests join
normal discovery. A passing small generated CI qualifies those paths only; full
integrated archived-history/independent-phase authorization path remains blocked
by checkpoints3/4. Preserve prior latency gates and failures, no new guard/retries.

Local full suites:434backend PASS/20platform skips in38.441s;123controlsPASS/
3platform skips in3.050s. Frozen source439c93b25ec05c04ef710afbfed5600ebd910f35.
Exact push LinuxCI42320474396 IN PROGRESS at the single valid status check:
https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/42320474396 .
Do not inherit baseline CI as successor qualification. Resume via completion
notification or one status check; no polling/retry. Source unchanged after freeze.

Concrete code evidence for checkpoint3:cloud_memory_v1.sql grants service_role
SELECT/INSERT/UPDATE/DELETE on raw_archives and sync_checkpoints;the repository
does not establish runtime Storage immutability. This is intended structured-table
schema evidence,NOT an inventory of deployed grants or the actual runtime token.
No credential was read. The existing retention_recovery.prepare_scope helper
selects CURRENT local rows before readback/reconstruction,so it does not by itself
implement post-retirement archive-to-application replay (checkpoint4).

## Checkpoint6 — release BLOCKED, numeric policy unchanged

5GiB physical total per raw slot is SELECTED TARGET;72h-or-qualified-size rotation
unchanged.24GiB aggregate including legacy/core/WAL/work/recovery/margin is an
UNQUALIFIED PROPOSAL. Applied production legacy5120MiB STOP/routing+retirement+paid
AI OFF unchanged. Finite100k-event ledger,core/reference/audit bounds, representative
capacity, complete legacy verification and real production path/fence/manual
cutover scope remain open. No executable production command/approval packet is
supported yet. No cloud writes or larger qualification workloads were run.

Cutover+bounded smoke, later first natural sealed-generation verification, then
retirement enablement remain SEPARATE bounded checkpoints. No waiting for a72h/
size seal inside cutover. Legacy remains until structured history core/Postgres,
verified exact raw archive,protected references,post-removal application history
and reader drainage qualify, followed by separate exact-file retirement approval.
I7freshness/realrollover,historyrecovery/replay,visibility,sustainedoperation and
Phase1.75 OPEN. Redis/knowledge-RAG/paidAI/Phase2 deferred;PR9 remains DRAFT.
