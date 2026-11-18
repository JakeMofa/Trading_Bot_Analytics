# CP6 PP raw archive host control — review

This candidate adds a default-OFF, PP-only host route for **one** bounded raw
archive cycle of an already sealed `pp-live-pp` PostgreSQL generation. It does
not deploy an application image, run the route, start cloud sync as a service,
change the persistent lifecycle service, enable retirement, or alter
production. PP currently has an A generation still collecting and no sealed
`pp-live-pp` generation, so this route cannot yet be executed.

The one-shot Compose profile uses the exact reviewed application image, a
read-only root process with all capabilities dropped, no host port, 128 MiB
memory, 0.25 CPU and bounded logs. It mounts only the lifecycle DSN, separate
private `history_v2` DSN/CA, and the dedicated PP Storage publishable key and
Auth identity files. The four Storage Auth files must already be root-owned,
mode 0600, regular, distinct and in the root-only PP cloud directory. The
original UID10001 lifecycle DSN is copied briefly to a root0600 file under
`/run/tradebot-pp-deploy` so the capability-free one-shot can read it; the
controller removes that pathname after the owned container exits. Any stale
staging file blocks the next attempt. No credential bytes enter logs or
evidence. The persistent API, calculation, lifecycle and operator services
receive no new mounts.

The fixed command `raw-archive-probe-v1 preflight` performs host/source/image,
file-metadata and normalized Compose checks, without a cloud call. The
`execute` command requires a separate root-owned, 30-minute, one-use permit
bound to the exact source, artifact, controller, image, sealed generation UUID,
seal count and manifest count. The application rechecks the seal/progress
before cloud I/O. The child has 25 seconds plus a fresh 30-second owned
container recovery budget. The application cycle itself allows up to 25 raw
and 25 structured rows, 256 KiB decoded/object bytes, 1 MiB total bytes,
eight cloud operations and 20 seconds. Partial coverage is reported as
partial. An ambiguous result remains failed even after cleanup.

The installed controller still predates this route. There is no PP runtime
attempt or cloud write from this PR. **Fresh read-only PP metadata preflight
found `pp_history_dsn` root0600 and `pp_history_ca` root0644 present, but all
four dedicated Storage Auth files absent. This is a concrete preflight STOP.**
Before an installation review, verify
that the dedicated Storage Auth files are present on PP, the exact
application artifact contains `pp_raw_archive_probe.py`, the source and
controller hashes match, and the PP live profile is safely `ready_off`.
Separately qualify a size-trigger A→B switch to produce a sealed A; then
run a bounded archive cycle while B collects. Each verified chunk advances
the raw manifest only after authenticated readback. A failure preserves the
local sealed partition. Full backlog/capacity and privileged mutation
authority remain unproven, so local retirement stays OFF.

## Credential staging procedure for separate review

1. Reconcile the existing dedicated PP Auth UID against the two installed
   `market-raw` policies and the private bucket. Inventory the original
   operator-held credential files by **metadata only**. If the original
   password is unavailable, stop and use a separately reviewed Auth credential
   rotation; do not guess or create another identity.
2. Transfer only the four dedicated PP Storage Auth files through the existing
   pinned operator route into a temporary root-only directory on PP. Never put
   values in command arguments, shell tracing, GitHub artifacts, application
   logs or chat. The PP host must not receive a service-role/admin key.
3. A root-owned installer must open staging paths without following symlinks,
   check regular files, unique inodes, exact expected names, bounded sizes and
   root0600 permissions, then atomically place them in
   `/etc/tradebot/cloud`. Preserve existing `pp_history_dsn` and
   `pp_history_ca` bytes and permissions. Do not restart any persistent
   service.
4. Verify only the final file metadata and exact UID binding. Keep any
   content-integrity digest inside the operator process; do not publish
   password, API-key or low-entropy email digests as evidence. Then
   remove temporary input files and report a STOP on missing, mismatched or
   ambiguous state. Then run the controller's read-only preflight. This
   procedure does **not** authorize the one-shot cloud call or local deletion.
