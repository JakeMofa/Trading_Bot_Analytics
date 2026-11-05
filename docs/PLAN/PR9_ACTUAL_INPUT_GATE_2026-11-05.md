# PR9 actual-input gate — November 5

Production remains stopped and unchanged. This report supersedes the assumption
that passing known-count fixtures made the real legacy source activation-ready.
No missing evidence is synthesized, dropped or silently reclassified.

## Exact failure and bounded evidence

79527a7 /CI42089343842 FAILED in generated fixture cleanup: ESRCH on a disappearing
/proc/2970/fd/26. Successor23aa5d2 treats ProcessLookupError like ENOENT only;
permission/unknown visibility still fails. Two injected descriptor outcomes pass.

Using the repository's existing pinned known_hosts/operator key, strict SSH passed.
An unprivileged file read failed PermissionError; sudo read-only access succeeded.
No trusted keys, service state, files, flags or permissions were changed. A five-
second serialized census exceeded its100000-row bound. Read-only indexed counts
then completed in0.06694s. The structured shape aggregate completed in4.14964s:

| Table | Exact rows | Sum body bytes | Largest row body bytes |
|---|---:|---:|---:|
|markets|1826|7425805|4568|
|candles|58812|5882158|103|
|feature_snapshots|18289|40003565|2236|
|predictions|27743|13313454|587|
|prediction_context_links|20|1895|118|
|reference_prices|18692|5289621|286|
|news_events|28|10690|433|

These seven tables total125410rows/71927188body bytes, excluding serialization,
other structured state, protected raw copies, indexes, WAL and TEMP. Feature evidence
has18268distinct metadata IDs and17924distinct Coinbase stream IDs: at least161602
audit rows including selected raw inputs, before other state/outcome/current pins.
The earlier17-shared-candle/reference fixture understated real selection fanout.

The five-second selected-body join timed out; no total selected-body byte claim.
A subsequent indexed-point shape diagnostic stopped on a missing input. EXPLAIN
confirmed observations INTEGER PRIMARY KEY(rowid=?) and stream composite PK
(source=? AND event_id=?) paths. A bounded reference diagnostic then established:

| Snapshot | Version | As-of UTC | Required metadata observation absent |
|---|---:|---|---:|
|1|1|2026-10-01T00:13:46.394082+00:00|25|
|2|1|2026-10-01T00:14:16.636851+00:00|28|
|3|1|2026-10-01T00:15:48.317775+00:00|30|
|4|1|2026-10-01T00:16:18.669210+00:00|33|
|5|1|2026-10-01T00:17:05.317989+00:00|36|

This check completed in0.41986s and stopped after five examples. It is NOT a complete
missing-reference census. No raw-history scan or payload was returned. The initial five-example check was followed only by the explicitly bounded
reference/available-source coverage diagnostics below; no production write occurred. The source
cannot pass the required exact protected-input gate, irrespective of storage size.

## Implemented offline preparation

- Added bounded read-only input census with early indexed missing-metadata refusal,
  source-change detection, explicit row/byte/deadline holds; no production authority.
- Import row accounting now includes selected raw copies rather than hiding them
  outside the structured-row budget. Missing referenced bodies still block activation.
- Explicit generated scope supports150000rows,128MiB audit,170s work/180s total,
  2GiB workspace,512MiB/process. Defaults remain10000full/60000fresh. Runtime can
  carry an explicit AB_MIGRATION_ROWS across startup/restart within that envelope.
  This is NOT an increase to any running production guard or an adequate scope for
  the now-known161602+selected rows. A future supported larger envelope needs proof.
- Generated fresh-B fixture now includes58812candles and18692reference_prices plus
  recorded market/snapshot/prediction/link/news counts. All structured candle history
  is preserved; actual predictions select17 completed BTC-USD60s candles with
  first_seen<=as_of, preserving missing/future evidence. Generated shared references
  do not prove actual fanout. This limitation stays in the artifact itself.
- Fresh-B raw event ledger gets a100000-event admission stop. Existing commits and
  archives remain readable; duplicate identity handling/recovery is preserved.
  No event/evidence/receipt deletion is introduced. Both collector and workers bind
  the same cap. Core512MiB admission guard remains independent of the raw cap.

Changed-source local suite382PASS/17platformskips,controls120PASS/3platformskips;
new census/ledger3PASS,budget4PASS. Linux/root/export proof remains mandatory.
Generated actual-count profile (before final row-accounting follow-up):125412
structured rows,65,696,467serialized bytes;constructor19.577s,restart2.311s,
24.066s total inclcleanup;235,360,256B peak allocation/RSS52,740,096B. Actual
reference fanout, missing legacy bodies and production-volume startup are NOT PROVEN.
An initial reference-price fixture used nonexistent symbol/raw_json columns and
FAILED; corrected actual payload schema passed. Failures are not erased.

## Finite numeric operating envelope — proposal, production unapplied

Keep retained legacy5369184256B as historical allocation requiring fresh binding.
Proposed aggregate8GiB;new-layout quota2GiB;core512MiB INCLUDING WAL/SHM;each new
slot64MiB INCLUDING WAL/SHM;early rotation trigger2MiB or72h maximum active age;
independent recovery reserve512MiB;filesystem floor10GiB;raw ledger100000events.
Budget new-layout workspace separately: core512MiB,two slots128MiB,archive working
256MiB,verification TEMP256MiB leaves896MiB within2GiB for admission overshoot and
other accounted files. Retained legacy+2GiB+512MiB=8053538816B,leaving536395776B
below8GiB. No reusable-page credit. Single bounded transaction can cross an
admission threshold; this is not a kernel byte quota or guaranteed full-window fit.

Measured core logical slope485.376B/event would mean48537600B for100000events;
a2KiB/event planning allowance means204800000B. Neither bounds protected evidence,
indexes/WAL or arbitrary input shapes; physical core guard may stop first. The
finite event cap stops raw-ledger growth without retirement making core unbounded.
Other structured growth remains subject to512MiB core admission/128MiB logical
verification bounds. No permanent continuous-operation claim. Proposed review
expiry24h is not installed or automatically extended; initial retirementOFF means
two-slot exhaustion may stop collection much sooner. At6.7events/s the ledger cap
alone is~4.15h;actual rate/earlier slot/core STOP and outage runway remain unproven.

## Cutover disposition and exact next action

Checkpoint1 actual startup inputs: **FAIL**: required historical metadata missing.
Checkpoint2 finite admission controls: implemented/tested at generated scale;
adequacy for actual source/runway **NOT PROVEN**. Checkpoint3 existing manual
cutover route: **BLOCKED** by failed source integrity and unqualified scope. Existing
root UID writer-fence, process-crash/forward-recovery and controller tests are reused;
no new production dispatch route can truthfully be declared executable for this data.

Smallest next action: review recovery of EXACT observations25/28/30/33/36 (and then
complete the missing-reference census) from provenance-verified existing archives.
Do not write recovered data to production under this milestone. If exact originals
are unavailable, the user must explicitly review a historical-unavailable evidence
policy; current fail-closed requirements prohibit silently weakening this gate.
A larger storage/row guard cannot repair absent referenced data.

The existing manual workflow must continue refusing this source. The concrete
review sequence in PR9_QUALIFICATION_REVIEW_2026-11-05.md remains STOP before
production: exact CI/export/source/config/UID/data/expiry binding;one old-writer
stop and permission fence;complete selected/new-core verification;initial retirement
OFF;one API collector;bounded smoke;2590s absolute interruption/180s recovery/10s
reap. After any new acknowledgement only forward recovery is allowed. No old
command with a new SHA is presented as a working cutover procedure.

PR9 remains draft. Real-boundary I7/freshness,cloud recovery/visibility,continuous
capacity/sustained operation,raw replay and deferred knowledge/RAG remain explicitly
open as reconciled. Redis deferred. No migration,deletion,copy/snapshot,VACUUM,
manual WAL operation,restart,production guard change,cloud write,infrastructure,
paid AI orPhase2 occurred. No new expired authority or cap extension is implied.

Exact source23aa5d2398ac499b37807dff24b27fc17653b79b /CI42094968368 PASS fixes
the795ESRCH failure. Later actual-input preparation needs its own exactCI. Four
focused census/ledger/whole-row-budget testsPASS; the extra case explicitly proves
selected inputs cannot bypass the row budget and source bytes remain unchanged.

## Final exact CI and recoverability evidence

Frozen cff60e40e69cfa86599fb082c3bce5b3c041757b /[CI42097085311 PASS](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/42097085311).
Known-count/shared-reference profile125422auditedrows/65697614B,49.546sconstructor/
3.067srestart/56.128stotal,205860864Bpeak,45531136BRSS. Fresh4000committed/archived,
0pending/errors,20cycles,save52.106ms/heartbeat271.185ms,22887503Bpeak,55.497s.
This qualifies generated behavior, not the missing real input set or its full fanout.

A complete bounded metadata identity census (7.034s) found6755missing of18268required
metadata IDs. A bounded stream-reference census(5.981s) found6493missing of17924.
The EXISTING local data/backups/pre_retention_phase1_75.db contains ALL13248missing
rows. No database copy was created. Read-only selected point checks(2.454s) matched
metadata market/receipt time/kind and stream time/exactprice,0mismatches. Serialized
selected bodies:26297384metadataB+4571422streamB=30868806B;selecteddigest
`ee2a7f4b4b05135369f7adb01ba92465299fa083bc603c32b4a057911e5364e9`.
That digest binds this selected-set ordering, not an approved full backup/archive.
Source authenticity/complete selected evidence, source binding and recovery-capsule
verification are still required; matching IDs and provenance are not independent
archive verification. No production repair, new recovery artifact or cloud mutation.

Fresh read-only allocation:main5323907072B,WALmax(length,allocation)45178880B,
SHM98304B,total5369184256B;filesystemavailable49796276224B. Storage arithmetic
proposals remain unapplied and cannot repair absent inputs. Numeric admission
limits and existing2590/180/10 budgets above remain distinct from production proof.

One concrete review decision: whether this existing historical source may be used
as recovery authority for the13248exact selected rows, after independent source/
selected-body verification, preserving legacy unchanged and importing only into
the staged new core. If that source is not accepted, an approved verified archive
source is required. This is NOT a request to dispatch production or restore data.
Do not claim an executable production cutover until that evidence route, sufficient
row/byte budget and matching manual control scope are implemented and qualified.
