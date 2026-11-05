# Fresh-B recovery route — retained sealed legacy, November 5

**Route:** keep the existing legacy database at its current path; start new raw
collection in fresh B, with persistent structured/protected core. No legacy raw
copy, full raw import, row deletion, checkpoint, VACUUM or retirement. Legacy stays
queryable and explicitly held. This is the current PR9 recovery preparation,
not production authority or a permanent72h capacity qualification.

## What was missing, and what changed

The existing adapter already retained legacy raw and UNIONed it with new raw and
core protected observations. But `_initialize` counted/audited ALL raw, mapped
every stream row, and selected A first. A single raw-archive cursor could also
put new B behind the legacy backlog. Consequently the prior full-import startup
could not supply the requested no-full-raw-import route.

The new explicit `AB_STARTUP_MODE=fresh-b`:

- Audits/imports structured tables only (60000-row/128MiB generated scope), retaining
  original IDs, exact decimals/timestamps/provenance, embedded evidence and cursor
  rows. Protected outcome/metadata/price bodies and current recorded inputs are
  point-selected into core. No full raw fingerprint or stream identity map is
  built. `MAX(id)`/`MAX(rowid)` reserve disjoint new numeric/display-order space;
  source/event keys remain identities and archive cursors never use rowid.
- Starts first generation in B, then alternates B→A→B by72h-or-size. Reused roles
  still receive fresh UUIDs. Legacy is a separate retained history file, never
  presented as a reusable raw slot or a verified/retirable generation.
- Keeps history/dashboard views spanning sealed legacy and acknowledged new raw,
  with structured/prediction history and protected bodies in core. The dashboard
  identifies active B and reports `legacy_history=sealed_retirement_held` and
  `legacy_full_verification=NOT_PERFORMED_BY_FRESH_BOOTSTRAP`.
- B archives incrementally through the same lifecycle worker, deterministic
  generation-specific object keys, authenticated readback and manifest handling.
  New local/cloud cursors `archive:ab72:observations` and
  `archive:ab72:stream_events` are separate from legacy `archive:*`. The latter
  remain unchanged; a legacy archive backlog cannot block B. Cloud status lists
  the dataset states and active-buffer status gives the new prefix.
- Fresh mode alone permits an explicitly read-only root-owned legacy file to be
  read by the normal service UID when the file is nonwritable and its parent is
  root-owned/sticky. This is a narrow sealed-reader exception; normal owner and
  symlink checks remain. Main/WAL identity now binds UID/mode/device too. The old
  writer UID cannot chmod the root-owned main or replace it through the sticky
  parent. Linux permission testing must prove this, not assume root application
  execution. The new app/core/raw files remain service-owned/private.
- Preserves pending-intent reconciliation and forward recovery. No new generation
  is reported acknowledged solely because raw commit finished. Default full-import
  mode, production path restrictions and retirement flag remain unchanged.

Current calculation inputs are copied exactly, never marked current merely because
copied. Old source times stay old. Fresh B feed data must genuinely advance before
fresh features can become available. Existing slow legacy feature queries remain
separate I7 performance work; this change does not install indexes or claim speed.

## Tests and recorded evidence

Frozen prior7b5e327 exactCI41998043241 PASS (checked once): known structured count
fixture47935 rows/54,715,760 audited bytes,1826markets/18289snapshots/27743predictions/
20links to8outcomes/28news andFTS. Full-import constructor25.264s, quick/FK+exact table
verification0.578s, restart0.556s,total28.083s, sample allocated164,331,520B,RSS46,358,528B.
This proves the structured cardinalities under2GiB/512MiB/170s-work/180s-total,
not the production raw population or the new fresh-mode source.

New local fresh-mode tests use20000 unprotected generated legacy raw rows left
in place, plus actual legacy schema/prediction/evidence/cursors. They verify real
API runtime startup and active-B dashboard/history, one collector lock, fresh B
acknowledgements, calculation/forecast continuity, UID/mode/device source binding,
legacy-byte equality, B-only archive and independent cursors, archive failure holds,
restart/mode-change refusal, and72-hour B→A with fresh UUID. The focused4 tests
pass. One small startup/function/rotation run took~0.052s with4,390,912B sampled
aggregate allocation. This is a small fixture timing, not production performance.

Linux root tests now include fresh B with **both old and new application using an
unprivileged UID**, reading a root-owned nonwritable legacy under a sticky parent.
They require old writer failure, before-ack recovery and raw-commit exit followed
by forward recovery, unchanged legacy bytes, no pending intents and valid references.
Exact candidate CI is required for that result. The existing4000-event ApplicationStore
qualification is switched explicitly to fresh-B mode (same limits/workload,4000new
archived rather than4002 including legacy), with separate lifecycle, predictions,
simulated boundary and sealed-new-generation retirement; legacy retirement stays held.

## Aggregate guard proposal — recovery-only, not permanent72h ceiling

No runtime guard was changed on production. Proposed initial envelope:

| Term | Bytes / rule |
|---|---:|
|Recorded retained legacy main+WAL+SHM|5,369,184,256 (freshly remeasure before any approved operation)|
|Additional core + new A/B + all their WAL/SHM + working allocations|2,147,483,648 aggregate new-layout quota, not a per-file allowance|
|Physical DB/working recovery headroom|536,870,912 minimum within aggregate reserve|
|Subtotal|8,053,538,816 (~7.5004GiB)|
|Proposed aggregate ceiling rounded upward|8,589,934,592 = **8192MiB /8GiB**|
|Independent core+its sidecars stop|536,870,912 (512MiB), not a growth forecast|
|Filesystem free-space floor|10,737,418,240 (10GiB), additional to all allocated files|
|Initial generation trigger|2,097,152 (2MiB), existing qualified small trigger; may shorten local window drastically|

Fresh-mode accounting charges max(file length,allocated blocks) for each local/
retained/unlinked file. All legacy bytes count toward the same aggregate ceiling;
only the *additional* independent2GiB new-layout quota excludes retained legacy.
Worker limits load from the core binding. Guard changes on reopen fail. Reserve,
core/new-layout quota, full slots or filesystem floor STOP collection. FULL stays.
No internal free-page credit, sparse legacy substitution or hidden retained file.

This8GiB value is a conservative finite recovery envelope from explicit quotas,
not a measured8GiB fixture/production peak or permanent two72h-buffer promise.
Before any execution, test/verify write-overrun margin and target reference/copy
volume; a128MiB input quota does not prove a512MiB output size or completion time.
Recorded measured structured/core sizes support feasibility, not a full arbitrary
fanout bound. Last host46.38GiB free/~1.257GiB available RAM is historical and not
fresh dispatch readiness. New-layout maximum demand2GiB plus the spare aggregate
reserve is far below that disk reading but must pass fresh preflight.

Proposed authority expires24h after the approved first cutover (or the explicitly
approved absolute UTC expiry, whichever is earlier); no automatic extension.
RetirementOFF at startup means the two small new slots eventually fill and STOP.
This is expected finite collection runway, not continuous lifecycle acceptance.
Do not lower the threshold or increase any quota automatically to avoid STOP.
Do not revert to the old writer or silently shrink a ceiling containing live data.

## Verification decision and exact operation still held

The recovery route avoids copying/re-auditing unrelated raw but does **not** silently
replace the existing complete-legacy verification policy. A concrete policy review
must decide whether the initial recovery may verify new core/B completely plus
exact selected legacy reference/input bodies and immutable source/permission binding,
while leaving complete legacy integrity/archive/reference-retirement checks pending.
Any unknown/malformed/missing protected dependency or128MiB/60000-row overflow STOPs.
Legacy must stay held and history/read errors visible. No old1790s full scan retry.

Required proposed startup configuration, applied only through the approved existing
systemd/manual deployment route, not a parallel shell collector:

```text
ENABLE_AB_STORAGE=true
AB_STARTUP_MODE=fresh-b
AB_STORAGE_ROOT=/opt/tradebot/data/ab72
SQLITE_DB_PATH=/opt/tradebot/data/btc_intelligence.db
MAX_LOCAL_STORAGE_MB=8192
AB_GENERATION_BYTES=2097152
ENABLE_AB_RETIREMENT=false
ENABLE_LOCAL_RETENTION=false
ENABLE_OPENAI_ANALYST=false
```

The eventual dispatch form is the existing manual workflow, `operation=maintenance`,
with exact CI-passed full SHA on the deployment branch, never a broad bypass:

```sh
gh workflow run deploy-tradebot.yml --ref codex/lightsail-deployment \
  -f revision=FROZEN_APPROVED_DEPLOYMENT_SHA -f operation=maintenance
```

**This is not yet an executable production approval request.** No exact production
cutover command can honestly be supplied on the current controls: their narrower
scope/old baseline and generated-only path gates correctly reject this integration.
Do not dispatch that template. After the verification/reserve policy is reviewed,
the existing host/controller must bind the frozen export, legacy inode/device/
main+WAL allocation/UID/mode/schema, service identities, exact guard/expiry and
single-attempt authority, implement the permission fence and fresh-core validation,
and pass exact Linux failure/recovery tests. No new controller/service is needed.
The application startup compatibility is implemented; those operator bindings are
still an actual release-control prerequisite, not concealed as a command that works.

Execution order for that future reviewed command: refresh physical space/flags/time;
stop old writers once; prove quiescence and install reversible root-owned legacy
fence; prepare core and prove exact protected/current bodies/FKs; fully verify new
core/B under a bounded budget; checkout exact release; start the single service
collector and lifecycle/ensemble; bounded functional smoke; revoke authority/report.
Before a new acknowledgement, code/permission recovery requires no new committed
writes and proven old compatibility. After any new acknowledgement keep the fence
and preserve core/B/intents, stop unsafe collection and recover forward. Never
restore DB contents. Retain legacy until its own complete archive/reference/drain
checks and separate retirement approval pass. I7/Phase1.75 remain open.


## Exact Linux result and scope correction

ba7873c5a5b793dbdeb87d45ac31e7472442e353 /CI42004431809 PASS:366backend/11privilege
skips covered by root18raw/38application/8runtime/2cutover;120controls. Fresh-mode
functional tests and unprivileged old/new UID fence/forward recovery passed.
Fresh fence→recovery1.184s before-ack/0.736s after-ack, new core quick/FK1.011/1.560ms;
small fresh startup/function/rotation81ms and4,390,912B sampled aggregate allocation.
The4000-event artifact, however, said full-import/4002archived: sudo stripped the
mode environment variable. Do not call that fresh-B qualification. Successor uses
explicit CLI mode plus a report assertion fresh-b/4000/legacyHELD. Its exact CI is
required; no unchanged retry or production command was run.
