# SQLite commit versus writer-lock diagnostic — November 1, 2026

Conclusion: the existing timer measures elapsed work after `BEGIN IMMEDIATE`
returns through `commit()` return. It includes post-release work and is **not an
accurate writer-lock occupancy measurement**. It is conservative with respect to
post-release work, but not a strict upper bound on the entire lock lifetime:
acquisition/wait and the small acquisition-to-BEGIN-return interval are excluded.
The existing 500 ms acceptance policy and every previous STOP remain unchanged.

One reduced generated-only trace establishes delay both before and after writer
release in this diagnostic. It does **not** establish where the historical
495.384 ms commit / 502.686 ms transaction delay occurred. No further trial ran.

## Timer and exact runtime

`backend/app/retention.py` starts `locked_at` after `db.execute("BEGIN IMMEDIATE")`
and appends `time.monotonic()-locked_at` after commit returns. `_measure_phase`
wraps the whole Python `db.commit()` call. Existing `write_lock_seconds` and
`max_write_lock_seconds` names therefore overstate what the instrumentation knows.
Neither Python's transaction flag nor those field names establish kernel lock state.

Existing Linux fixture interpreter `/opt/tradebot/.venv/bin/python`:

- Python 3.12.3, GCC 13.3.0; SQLite 3.45.1, Ubuntu package `3.45.1-1ubuntu2.8`.
- `sqlite_source_id()`: `2024-01-30 16:01:20 e876e51a0ed5c5b3126f52e532044363a014bc594cfefa87ffb5b82257ccalt1`.
- `_sqlite3` loads `/lib/x86_64-linux-gnu/libsqlite3.so.0`; backing library
  `/usr/lib/x86_64-linux-gnu/libsqlite3.so.0.8.6` SHA256
  `85265a9d4afca6f4b325ceb078b669c754fb881abed4cafe91ccebe9d625d975`.
- Compile options include DEFAULT_SYNCHRONOUS=2, DEFAULT_WAL_SYNCHRONOUS=2,
  DEFAULT_WAL_AUTOCHECKPOINT=1000, THREADSAFE=1, SECURE_DELETE, ENABLE_PREUPDATE_HOOK.
  No ENABLE_SETLK_TIMEOUT or alternative Linux locking-style option reported.
- Actual fixture settings stayed WAL / FULL(2) / automatic threshold1000 /
  page size4096. No threshold or durability mutation in this diagnostic.

## Official ordering and matching package source

[SQLite WAL hook documentation](https://www.sqlite.org/c3ref/wal_hook.html)
places the hook after transaction commit and associated writer-lock release.
[WAL performance documentation](https://www.sqlite.org/wal.html#performance_considerations)
explains that the commit triggering the automatic checkpoint also performs its work.
[FULL synchronous documentation](https://www.sqlite.org/pragma.html#pragma_synchronous)
requires an additional WAL sync on each transaction commit.

Inspected the installed version's [official Ubuntu source package](https://packages.ubuntu.com/noble/sqlite3),
not just current SQLite master. Official source manifest SHA256 entries match:

- `sqlite3_3.45.1.orig.tar.xz`: `e32e817f7b4166a301f60b14a711871bfab7d35c1d7e29b585dfc479ae150aa4`.
- `sqlite3_3.45.1-1ubuntu2.8.debian.tar.xz`: `d543bf91c6f14ccd52ebe44d6ef3b360196b2596e0a7ca86089aef5fc52f5ec0`.

In that source: `wal.c` sqlite3WalFrames performs FULL commit WAL sync before
sqlite3WalEndWriteTransaction releases WAL_WRITE_LOCK; `pager.c`
pager_end_transaction calls that release during commit phase two. `vdbeapi.c`
doWalCallbacks runs after successful statement completion in autocommit mode.
`main.c` sqlite3WalDefaultHook invokes sqlite3_wal_checkpoint, the PASSIVE API.
`wal.c` sqlite3WalCheckpoint takes CKPT and only non-PASSIVE modes request WRITE.
`os_unix.c` maps WRITE to shm byte120, CKPT121, readers123..127 and DMS128.
Ubuntu's patch series does not modify wal.c, pager.c or vdbeapi.c; main.c changes
are lookaside allocation, and os_unix.c changes are Hurd locking selection.
These do not change this Linux commit/checkpoint path. No source was built or installed.

## One diagnostic and evidence

Started 15:54:57.263384 UTC (09:54:57 CST), supervised11.798s. Existing exact-hash
84513b0 retention/harness and deployed save SHA
`95a49c2ac04b6dbb04223e0f363df0a6132bd7b0cc10fda7145a2055bd1efa12`.
Generated12000 observations +12000 stream events; 500-row batches, unchanged
100ms handoff; explicit timestamp guards. No production database was opened by
instrumentation. Existing harness production HTTP guards remained active.

Existing strace6.8 used `-f -ttt -T -yy` for open/close, fcntl, writes and syncs.
A temporary Python connection subclass emitted paired monotonic/realtime markers
around explicit BEGIN and commit calls. This adds instrumentation, not a WAL hook,
native extension or journal change. The deployed collector actor and save-to-RAM
order remained unchanged. Its context-manager commits are observed by syscalls;
per-save Python entry/return markers were not added to the actor.

The parser joins unfinished/resumed syscalls by TID and retains syscall entry/exit
bounds. It requires successful F_SETLK F_WRLCK/F_UNLCK, SEEK_SET, offset120,
length1 on the resolved **fixture.db-shm descriptor**, not the database shared
lock range or CKPT byte. Main PID27148 used shm fd5, WAL fd4 and DB fd3;
collector PID27150 used shm fd8 for the same path. All48 retention transactions
have exactly one identified acquisition and release; the separate guard-build
transaction is excluded. Acquisition/release transitions lie inside their syscall
intervals; occupancy is reported as a bracket, not an exact kernel instant.

Slowest retention commit (observation batch6), UTC epoch seconds:

| Event | Entry | Exit/return | Evidence |
|---|---:|---:|---|
| Main WRITE acquisition | 1793548499.647491 | .647505 | shm fd5 byte120, success |
| Python commit entry marker | 1793548499.663729 | — | monotonic paired marker |
| WAL fdatasync under WRITE | 1793548499.688564 | .746809 | strace duration58.225ms |
| Main WRITE release | 1793548499.746899 | .746914 | shm fd5 byte120, success |
| Collector WRITE acquisition | 1793548499.759434 | .759457 | shm fd8 byte120, success |
| Main database fdatasync | 1793548499.767127 | .883872 | strace duration116.707ms |
| Python commit return marker | 1793548499.8841085 | — | monotonic paired marker |

This commit took220.379ms: approximately83.185ms before release and137.195ms
following release. Total WRITE occupancy bracket99.394..99.423ms includes the
pre-commit work. Commit performed408 WAL writes before release, then204 database
writes afterward. The post-release work includes CKPT locking and database sync;
the collector's successful byte120 acquisition before commit return independently
confirms the writer lock was available while main commit was still running.
Another commit took207.702ms with158.082ms after release, including126.007ms DB
sync. FULL durability also incurred measurable lock-held WAL sync (58.225ms in
the slowest sample); time is present on both sides, not solely after release.

Reduced harness completed with maximum legacy duration236.473ms; collector65
saves/65 RAM updates, zero errors, maxsave137.707ms, heartbeat165.329ms. Production
guard failures0. Maximum observed WRITE occupancy upper bound99.423ms. These are
**traced reduced-scale diagnostic results**, not full-scale qualification. Ptrace,
FD decoding, marker writes, scheduling and trace output perturb timing. No paired
untraced control was run, so overhead is unquantified; no subtraction or latency
projection is justified. The historical 256-page failure was not traced and used
a much larger fixture. It cannot be retrospectively apportioned or made PASS.

Private local evidence directory (outside repository):
`/Users/jake/Documents/ChatGPT/TradebotAnalytics/evidence/phase175-baseline/lifecycle-implementation-20261031/sqlite-writer-lock-084ca92/`.
Contains raw trace, harness report, instrumentation, parser, analysis and SHA256
manifest; no database. Raw trace SHA256
`ae7e9465801ed8518f0702650b89734a706bd38e659751ac96973a7cc1c68156`.
Parser assertions verified all48 commit/lock pairs and no unresolved syscall.
Generated work directory confirmed empty by the supervisor. Post-check15:57:34UTC:
collector running; Coinbase and Polymarket live with fresh last-data timestamps.
This single sample is not a recovery soak or rollover proof.

## Smallest justified next change; stop condition

Propose companion metrics for observed WRITE occupancy (including acquisition
bounds), acquisition wait, total commit-call duration, existing post-BEGIN total,
and collector save/heartbeat interference. Keep the existing500ms gate on its
current timer until explicit policy approval; never fill occupancy from Python
transaction state or commit-return duration. This milestone changes documentation
only, avoiding a speculative runtime instrumentation or checkpoint redesign.

The original overrun's cause remains inconclusive: missing syscall evidence from
an actually slow representative commit prevents determining whether its excess
was lock-held sync, post-release checkpoint work, or both. Do not launch more
unchanged qualification trials. The observed58ms lock-held sync does not establish
that lock-held durability caused the historical failure. FULL sync can stall and
cannot safely be cancelled halfway through a durable commit; the existing gate
detects an overrun after return, rather than preempting sync. No durability or
policy change follows from this diagnostic.

Production unchanged; this chat deleted zero production rows. Retention and paid
AI remain OFF. I7/Phase1.75 OPEN; no Phase2. Temporary5120MiB review deadline stays
2026-11-02T01:56:47.671426Z (November1 19:56:47 CST), without extension.
