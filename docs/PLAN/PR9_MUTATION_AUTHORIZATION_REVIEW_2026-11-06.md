# PR9: mutation protection and retirement authorization — review first

November 6, 2026. Offline design/characterization checkpoint, not a production
permission change or replacement deletion policy. Existing fresh full readback
remains mandatory. Source baseline101921e, documentation baseline50ed1a4.

## Decision and threat boundary

Do not implement cached-proof retirement yet. Incremental verification can replace
the final complete download only if published bytes and the exact manifest stay
unchanged throughout verification AND through local retirement. A checksum proves
what was read, not continued remote availability. An observed policy hash, JWT
expiry, client create-only header or periodic policy poll cannot close the race
between the last observation and unlink. Local proof must also bind sealed raw,
acknowledged identities, preserved core references and reader drainage.

The proposed model is conditional on an enforceable publication/mutation fence.
Supabase Storage access control documents that INSERT permits upload, replacement
requires additional permissions, and a service key bypasses RLS entirely:
https://supabase.com/docs/guides/storage/security/access-control . Therefore RLS
alone cannot establish immutability against service-key holders/project admins.
This design does not claim storage-provider object lock or an atomic transaction
between remote Storage and local SQLite. Existing core intent/ack recovery remains.

## Identity and authority matrix (proposed; actual grants NOT INVENTORIED)

|Identity|Published raw objects|Manifest/checkpoint and local authority|
|---|---|---|
|Collector/API, feature/history/ensemble worker|No upload, replace, move or delete; authenticated evidence retrieval only through reviewed read path|Collector alone owns active raw writes; other roles cannot retire; structured roles retain only their required existing rights|
|Lifecycle archive runtime|INSERT new generation-specific objects and SELECT/readback; no UPDATE, DELETE, overwrite, move, destructive bucket action or alternate mutation route|Publish exact manifests without changing their content identity; monotonic checkpoints; no blanket raw retirement permission from upload success|
|Local retirement actor|Authenticated SELECT only for published bytes|Sole permission to unlink an approved local sealed generation after all gates; no cloud deletion authority|
|Existing service/secret keys, database owner/BYPASSRLS roles, project/storage administrators, S3 credentials or maintenance automation if present|Potential bypass/replace/delete/policy-change authority; NOT assumed constrained by runtime RLS|Must be explicitly inventoried as trusted break-glass authorities or removed from operational mutation paths; a lifecycle runtime using such authority cannot supply this fence|
|Anonymous/other authenticated identities|No read/write access to this private archive scope unless explicitly required and reviewed|No retirement approval|

These are logical roles, not new accounts/services or applied grants. Actual
identity names, effective grants, inherited/permissive policies, credential types,
bucket actions, RPC/definer paths and alternate endpoints require sanitized
read-only evidence. Never retrieve credential values to perform that inventory.
Existing runtime access-probe PASS establishes upload/readback, not absence of
mutation authority. Current tests cannot prove deployed grants.

## Proposed authorization state machine

1. **Sealed:** freeze unique generation UUID, slot incarnation, schema/version,
   acknowledged row identities/fingerprints, counts/boundaries and source times.
   Keep sole writer fencing; new slot continues independently. No slot-name-only
   identities and no cross-file atomicity assumption.
2. **Published:** existing private bucket, generation-specific content-bound
   object paths and exact manifest catalog. Reconcile duplicate uploads by exact
   bytes; reject conflicting identity. Freeze manifest identity separately from
   mutable progress/checkpoints. A checkpoint is never deletion authorization.
3. **Verifying:** each bounded cycle persists readback/checksum/body/coverage
   receipts in core, bound to generation/catalog/local mutation epoch/code and
   policy epoch. At most8objects and original30s operation budget; whole generated
   fixture180s including preparation/cleanup. Partial work gives no unlink right.
4. **Ready:** all exact required objects verified under the SAME valid protection
   epoch; required prediction inputs and references durable in core; history
   retrieval acceptance passed. No missing/malformed/unverified data can be waived.
5. **Authorized:** one-use intent binds exact generation/incarnation/catalog,
   local file identity, core dependency proof, verifier/config, authority expiry,
   policy epoch and all readback receipts. Exclusive local generation fence plus
   reader/OS-handle drainage. Recheck immediately before unlink. The remote
   mutation fence must remain in force; a signed/hash receipt alone is insufficient.
6. **Retiring/retired:** durable intent before unlink, then idempotent completion.
   On restart reconcile exact inode/path/incarnation and intent; never remove a
   reused slot or infer success from an absent unrelated file. Preserve protected
   core history and remote archive. This is LOCAL raw retirement, not cloud purge.

## Crash, expiry, policy-change rules

- Crash during upload/readback: reconcile exact remote identity; incomplete proof
  remains pending, raw retained. Commit a receipt only after complete validation.
- Restart: load durable intent/progress; re-establish current policy authorization,
  local file/catalog/epoch and dependency bindings before reuse. Other-slot writes
  alone must not invalidate sealed proof.
- Expired receipt/authority, backwards/uncertain wall clock, revoked identity,
  changed verifier/catalog/raw/reference or unprovable policy continuity: HOLD,
  invalidate applicable proof and reverify. An existing authorized intent does not
  bypass expiry after restart. No automatic extension.
- **Policy changes must fence retirement BEFORE changing protection.** Proposed
  break-glass protocol: disable/revoke local retirement permits, drain/reconcile
  in-flight intents, bump durable policy epoch, then mutate policy/objects. Resume
  only with fresh reviewed evidence and revalidation. If administrators/alternate
  mutators can bypass this protocol, mutation-proof authorization is NOT PROVEN.
- Polling policy metadata cannot guarantee this ordering. A race-free mechanism
  and its administrative threat boundary must be reviewed before implementation;
  no new authority service/controller is bundled here. A compromise of project
  administration is not solved by application hashes.
- Current fallback remains full fresh authenticated readback. It detects changes
  before that read, but is not a claim of absolute remote immutability afterward.
  If the proposed fence is infeasible, review a separately bounded full-generation
  final pass instead; do not silently widen30s/eight-object limits.

## Existing layout: tested facts and gaps

The private `market-raw` bucket, `raw_archives` Postgres format and structured
tables remain unchanged. ApplicationStore prefixes new raw paths with generation
UUID; legacy preserves its original path and metadata generation_id=`legacy`.
Reused A/B slots get fresh UUIDs. Mixed-generation archive batches are rejected.
The local new-generation manifest catalog is keyed by generation/dataset/path;
remote manifest identity is bucket/object_path and checks exact metadata/body hash.
Do not rename historical legacy keys. The `legacy` label is not a globally unique
multi-migration source identifier: bind the exact existing legacy source fingerprint
in its recovery/retirement manifest and reject a second source claiming that binding.

**Checkpoint gap:** legacy uses `archive:<dataset>`; fresh-B uses
`archive:ab72:<dataset>`, shared across NEW generations, with global source-ID/time
cursor ordering. These are distinct legacy-vs-new streams, NOT per-generation
checkpoints. New characterization proves that distinction rather than claiming the
user's per-generation checkpoint requirement passed. Smallest proposed follow-up:
add generation-specific progress using existing checkpoint dataset text field,
preserve historical cursor semantics and reconcile already-verified manifests.
Requires testing out-of-order/backdated receipts so a global cursor never hides a
new-generation row. No checkpoint rename/reset or SQL migration was applied here.

Structured sync preserves existing source_id keys for snapshots/predictions/news,
market IDs, candle composite identity and original source timestamps. Existing
adapter refuses conflicting values at a source identity, reconciles ambiguous
commits without a second blind POST, and preserves exact decimal JSON. This blocks
collisions rather than assigning arbitrary replacement IDs. Multi-origin ID
collision handling remains a release gate if a new namespace is introduced.

## Offline evidence and limitations

New test_ab_archive_namespaces.py:2PASS, identical legacy/new row paths distinct,
manifest generation identity preserved, mixed-generation batch rejected, shared
fresh-B checkpoint explicitly characterized. Initial fixture test failed because
generation activation is lazy; fixture now performs a real acknowledged save
before asserting active identity. No runtime behavior changed to satisfy the test.

Combined focused run20tests,19PASS/1Linux-root skip,2.294s: namespace tests,
incremental verification faults/restart/expiry, actual HTTP mock structured/raw
wire compatibility, collector/feature/history/lifecycle across A/B and real API
history/dashboard unavailable-state regressions. No new cloud requests/VM work.
Existing baseline101921e exact LinuxCI42161684724 covers root retirement and
B→A→B→A; this local skip is not new Linux evidence for the successor commit.

Calculations and dashboard history using legacy/core/active+sealed raw are PASS
at generated scale. Archive bytes/identities are verified by existing readback
tests. **End-to-end archived-raw retrieval into calculations/dashboard after local
retirement is NOT PROVEN by these tests.** Implement/test bounded replay/retrieval
with original provenance, timestamp/no-lookahead checks and honest unavailable
states before retiring history that those paths require. Do not confuse protected
core inputs remaining accessible with arbitrary raw archive replay being complete.

## Required reviews; no changes applied

1. Effective permission inventory may require restricting existing lifecycle
   authority and alternate mutators; exact grants/identity evidence unavailable
   here. No concrete Supabase SQL/schema change is yet justified or applied.
2. A durable policy-epoch/manifest-publication fence MAY require a schema/grant
   change. Present exact existing-schema compatibility and SQL/grants for review
   only after the administrative fence model is feasible. Do not fabricate a
   policy epoch from a client variable or pretend an RLS rule constrains service keys.
3. Replacement of final fresh readback requires explicit approval AFTER that proof.
4. Per-generation checkpoint implementation and archive-backed application history
   are independent offline follow-ups; keep published cloud paths/formats intact.

## Separate bounded production checkpoints, not one maintenance window

**Cutover:** exact-release preflight, writer pause/fence, complete legacy checks,
core/new-slot startup and bounded functional smoke. Existing1800sverification/
2590sinterruption/recovery reserve retained; storage-held startup route still needs
qualified controls. No wait for a72h/size seal inside this window.

**First sealed-generation verification:** later separately authorized/bounded
operation under live collection, only after automatic72h-or-size seal. Report
coverage, requests/bytes, wall time, B growth and physical headroom. Missing proof
holds sealed slot; two occupied slots cause safe STOP, never overwrite.

**New-generation retirement enablement:** separately recorded gate after qualified
authorization/history/drain/capacity evidence; no inherited enablement from cutover.

**Legacy archive and retirement:** preserve structured history in core/Supabase,
incrementally archive exact legacy raw with source-bound manifest/cursors, verify
authenticated coverage and protected references, prove post-removal history/replay,
drain all legacy readers/handles, then seek separate exact-file retirement approval.
Recovery preserves committed new writes and never restores/resumes legacy writer.

5GiB/slot remains target (main+WAL+sidecars);24GiB aggregate remains PROPOSED.
Applied legacy5120MiB guard and production holds unchanged. Existing generated
2GiBworkspace/512MiBprocess/180s bounds unchanged. Finite100k-event ledger/core/
audit limits must be resolved/qualified before continuous operation is claimed.
No slot increase is included. I7freshness/rollover,historyrecovery/replay,visibility,
sustainedoperation and Phase1.75 stay OPEN; Redis/knowledge-RAG/paidAI deferred.

**Result:** offline design/characterization delivered; scalable deletion
authorization NOT PROVEN and NOT ENABLED. Next decision is review of this model,
especially whether the privileged mutation/change-control boundary is acceptable;
no permission changes or replacement gate implementation before that review.
