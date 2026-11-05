# Selected historical evidence recovery — November 5

Verification and isolated selected-row staging only. Production repair, transfer,
activation, cutover and retirement are NOT authorized by this checkpoint. PR9 stays
draft. Source verification tools are default-off; production paths fail closed.

## Source and dependency verification

The existing pre-retention file was opened read-only. No whole database copy was
created. Source1983184896B,SQLite user_version0,full integrity_check ok,zero foreign
key violations. Raw columns/order and primary identities match the legacy schema;
source/supporting-market schema identities are checked. Source SHA256:
`a7edbb886d71d4690d608d915a975fe43c1ff9d194cb1c7dd54fdbbfa90787a6`.
Full schema SHA256:
`a88b290dd84c4718226dbffcd9ee7c962860d26a4437f4f07c927be90aed852b`.
Initial independent whole-source verification2.910s;source inode/device/size/mtime
bound before/after. Nonempty candidate WAL is rejected without separately approved
hash verification;no checkpoint/truncation/journal operation touches the source.

A fresh bounded read-only manifest from the stopped production legacy binds file
identities,6755missing metadata IDs,6493missing stream IDs,6776snapshot dependencies
and6745prediction references. Dependency file SHA256:
`8e8473f444983419d60e2004ca2e7c41d89657f6767fe691d36e8e1a5003eb61`.
The candidate verifies exact identities,market/receipt/source times,metadata kind,
price-to-beat,exact reference prices,JSON/finite decimal text and timezones. All
selected identities must be used by a protected dependency. Duplicate/conflicting
snapshot/prediction identities,wrong markets and unknown feature versions hold.
No snapshot/prediction values are fabricated:the staged dependency tuples are
reference proof,not reconstructed forecasts.

**PASS:** all13248selected rows,0conflicts,0unverifiable rows. Exact original TEXT,
payload whitespace,decimal strings,timestamps and IDs are preserved. This establishes
current source identity/integrity and agreement with independently collected legacy
references;no earlier trusted creation-time checksum exists in this checkpoint.
Cryptographic attestation of the file's historical origin remains NOT PROVEN.

## Exact recovery manifest and review artifacts

Actual qualification used exact-export tools from
`b8786e001c5c3f8757838e4d0c523c72cc3ca1a5`;the earlier66c9c09 launch FAILED before
verification/staging due missing exporter import path. That failure is preserved.
The fix has a clean-directory,PYTHONPATH-empty subprocess package regression.

Private artifacts retained at `/private/tmp/generated-ab-recovery-s1r_pa53/`:

- `recovery-manifest.json`:13248per-record dataset/key/SHA256 entries,source/dependency
  bindings,schema,369supporting-market hashes and protected reference set checksum.
- `staged-core.db`:exact metadata rows and application-compatible legacy pins/audit
  maps,369real supporting market rows and dependency proof. Runtime activationOFF.
- `qualification-report.json`:whole-operation/resource and idempotence measurements.
- `recovery-stream-spec.json`:future canonical JSONL stream specification and checksum;
  no stream payload file was created or transferred.

Manifest internal canonical SHA256:
`cce959118eb774d8131a8bd60876bcd2f3f16c1a8d90c086621dfe6c1dd1c208`.
Manifest file SHA256:
`9577e6f53d2150f107eb7fd6914a0dc93ab7d806d52f04a230347332765ff07b`.
Sorted selected catalog SHA256:
`6c9ee8583c58a2dac0ba804b962d6cd467b483e73b77478331056d99d7ef4a55`.
Selected canonical row bodies30868806B. Future13248-row canonical JSONL stream:
32552271B,SHA256
`01f3ce94b62f3f91690b33e5aa4721de6ac6c22635d91b7c71dea7c0e689061c`.
Order isSQLite ORDER BY dataset,key(BINARY),one canonical object(dataset,key,row,
sha256) plus newline. This is an exact content specification,not upload authority.
All per-row data/manifests remain private and untracked;only summary evidence is git.

## Stage and failure qualification

One transactional stage inserted60390rows across records,pins,audit,real support
markets and reference proof;13248selected bodies. FULL synchronous=2. Complete
staged integrity/FK checks pass. Second application made**zero changes**. Existing
same identities must match every stored field;different bodies/bindings/extraneous
identities hold and preserve the files. No INSERT OR REPLACE repairs a conflict.

Actual Mac qualification5.596s including verification/staging/retry;verification
3.776s,stage1.045s,retry0.657s;RSS102940672B. Accounted peak2142367108B includes
existing1.983GBsource,dependency manifest,entire exact export,source sidecars and
named stage/working files. Anonymous SQLite TEMP was not independently measured
on Mac;complete TEMP/resource highwater is NOT PROVEN. Only5116540B(4.88MiB) below original2GiB envelope. No capacity
credit for reusable pages. This is a narrow selected-stage fit,not full migration
capacity.170swork/180s absolute supervisor retained. Mac does NOT apply Linux
512MiB address-space limit;actual-data Linux/VM qualification NOT PERFORMED.

Generated fault tests cover exact retries,body/identity conflict,missing/malformed/
wrong-price/time inputs,source/dependency hash mismatch,unsupported version,FK
failure,unexpected stage membership,deadline and injected disk-full errors,open
reader,transaction rollback andpostcommit failure. Additional actual process exits
before/after commit prove SQLite normal recovery preserves acknowledged selected
rows and idempotent retry. Physical power loss/real ENOSPC filesystem NOT PROVEN.
Local full390backend/120controlsPASS(17/3platformskips) preceded final packaging/
process-fault additions;final focused9PASS. Exact1547a43/CI42121991450 exported
backend392PASS/13privilege skips,all9selected testsPASS onLinux. CI overallFAILED
in the existing raw4000 profile:save727.764ms/heartbeat1165.206ms,unchanged<1s gate.
Source raw/profile files are byteidentical to qualifiedcff60e4;the delay's cause is
NOT PROVEN. Rootraw18ran with1failure;laterroot/control/import/integrated gates
were NOT COMPLETED. No unchanged retry or policy change. Priorpasses remain scoped
evidence,not a replacement for this failed exact run. Actual13248-row qualification
usedb8786e0;verifier/runner bytes are identical in1547a43.

## Production procedure for review — STOP, not execution authority

Prefer recovery into the NEW core while retaining legacy unchanged. This avoids
in-place repair and preserves the old source/fence as evidence. No database file
transfer or source backup restore is part of this proposed route.

1. Freeze final exact release/export/CI,manifest and future stream checksums above.
   Recheck source/dependency identities and intended service UID/permissions. Accept
   this selected recovery source explicitly in the consolidated production review;
   candidate-verification approval alone is not production source-use authority.
2. Implement/qualify the full ApplicationStore bootstrap consumer for the exact
   selected stream and proof maps. Import current structured tables from legacy,
   then recover only the approved13248missing rows. Use current legacy markets;
   the369historical market rows in this isolated stage are FK support only.
   Preserve current prediction/snapshot IDs,outcomes,archive cursors and provenance.
   Full bootstrap/restart/history/feature/lifecycle validation is NOT PERFORMED by
   this selected-stage test. Current importer still rejects missing legacy rows.
3. Qualify the FULL selected scope and logical bytes. At least161602required audit
   identities exceed current150000max;128MiB logical byte budget adequacy remains
   unproven. No row/byte/production guard increase is implemented here. Derive a
   finite core horizon and aggregate peak with actual fanout before approving
  8GiBaggregate/2GiBnew-layout/512MiBcore/64MiBslots/512MiBrecovery/10GiBfloor proposals.
4. Adapt/rehearse ONLY the existing manual workflow/controller for that exact scope.
   Bind release/CI/data/config/UID/helpers/manifest/expiry andone-use authority.
   Resolve full-legacy versus targeted verification policy explicitly;this source
   integrity check does not replace the previously required production checks.
   Do not reuse old exception/deadline/verification evidence silently. Preserve
  2590s absolute interruption,180s recovery and10s reaping unless separately reviewed.
5. After separately approved production scope:pause old writers once,prove quiescence
   andestablish nonroot legacy write/replace fence. Freshly verify physical capacity
   andtime against the reviewed expiry. Stream only approved selected records to
   the privileged bounded importer;verify bytes/checksum/catalog andexact current
   references before one core transaction. A repeated identical attempt must make
   no changes;a conflict stops. Keep legacy unchanged andretirement/paidAI OFF.
6. Complete full staged/new-core integrity/FK/schema/reference checks before exposure.
   Start exactly one collector only after approval andsuccessful checks. Run bounded
   functional API/current-market/freshness/persistence/dashboard/SSE/service smoke.
   No20–30minute soak/polling/restart loop. Real-boundary/multi-cycle acceptance
   remains NOT PERFORMED unless independently evidenced.
7. Before newacknowledgements,restore code/permissions only ifno new committed data
   andcompatibility are proven. After any newack,keep the legacy fence andrecover
   FORWARD from core/raw/proofs. Never restore database contents. Revoke temporary
   authority/restore helper code andreport actual interruption/revision/headroom.

No production command is supplied for step5:the reviewed stream consumer/manual
scope is not implemented/qualified yet;using the old command with a new SHA would
fail its gates. This document makes that prerequisite explicit,not a general bypass.

I7 real-boundary/freshness,cloud recovery/operational visibility,continuous72h-or-size
capacity,retirement enablement andsustained operation remain open. Historical raw
replay anddeferred knowledge/RAG remain as reconciled. Redis deferred. Phase1.75
NOT complete. Production remained untouched throughout this checkpoint.

## Remaining exact-CI gate

[CI42121991450](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/42121991450)
remains FAIL. A bounded diagnostic must establish where the heartbeat stall occurs
before another qualification attempt. No cause is inferred from aggregate save/
heartbeat maxima alone. This is separate from selected-row correctness and does
not authorize a threshold increase,new architecture or production change.
