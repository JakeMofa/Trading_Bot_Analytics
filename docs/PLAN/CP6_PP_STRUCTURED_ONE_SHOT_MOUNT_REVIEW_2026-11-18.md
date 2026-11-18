# CP6 PP structured one-shot mount review — 2026-11-18

## Scope

This code prepares a **default-OFF, PP-only** way to run one bounded
`history_v2` structured outbox diagnostic. It does not install a controller,
mount a cloud credential on the PP host, make a cloud call, enable a persistent
sync service, enable local retirement, or alter production.

The two staged PP files stay at `/etc/tradebot/cloud/pp_history_dsn` (root,
0600) and `/etc/tradebot/cloud/pp_history_ca` (root, 0644). Only the new
`structured_probe` Compose profile mounts them. A one-shot root-only copy of
the existing PP lifecycle credential is staged under `/run/tradebot-pp-deploy`
at mode 0600, then removed after the container exits or fails. This is a
credential copy in the host's `/run` staging area, **not a database
copy**; no credential bytes enter logs or evidence. The persistent API,
calculation, lifecycle and operator services keep their original secrets,
users, network and restart policies. The one-shot container runs as root only
to read the root-owned DSN. It has a read-only filesystem, `cap_drop: ALL`,
`no-new-privileges`, bounded memory/PIDs/logs, no host port and no Docker
socket. Its additional egress bridge is restricted to that one-shot service.

**Successor correction:** The first merged mount candidate (`4f66635`, PR
#114) could not read the PP lifecycle file: it is owned by UID 10001 at mode
0400, while container UID 0 had all capabilities dropped. An isolated Linux
reproduction returned permission denied. A separate generated root0600 file
was readable with all capabilities dropped. The successor stages exactly that
short-lived local credential and mounts it only on the one-shot container.
It refuses stale staging files; an uncatchable host termination leaves a
root-only file that blocks later preflight pending explicit reconciliation.

## Host control and command

The reviewed controller bundle adds these fixed forced-command forms:

```text
structured-probe-v1 preflight
structured-probe-v1 execute
```

Preflight checks the exact PP host marker, the completed deployed source and
image, current PP live profile, expected probe modules, normalized Compose
configuration, staged file metadata and pinned CA fingerprint. It reports
only source/image identifiers and disabled-state evidence. It sends zero
cloud requests.

Execution requires a separate root-owned, unexpired, one-use permit bound to
the exact source, artifact, controller, image, generation UUID, generation
state and first pending outbox ID. The local installer prepares that permit
with `authorize-structured-probe`; it does not run the probe. The controller
consumes it before invoking only `docker compose run --rm --no-deps` for the
one-shot profile. The application probe has its own 25-row, 256 KiB object,
two-cloud-operation and 20-second limits. The host command has a 25-second
child deadline plus a fresh 30-second container recovery budget. A timeout or
error is a failed attempt even if the container is stopped afterward.

No `up`, persistent-service restart, API/collector cloud mount, production
path, raw archive acceptance or retirement command is available through this
route. Normal generated PP CD omits the overlay and continues rejecting
unexpected services and secrets.

## Qualification and remaining gates

The normalized Compose profile and operator tests cover wrong host, wrong
file permissions, secret aliasing, unauthorized service mounts, unsafe
network/volume/restart/capabilities, cloud flags, no accidental activation,
one-use permit targeting, root-only temporary credential staging, cleanup
failure reporting and container cleanup on child deadline. Local PP
controls: **116 tests passed, one platform skip**. This is source-level
qualification. Exact-commit Linux CI and review are required before any
installation.

The installed PP controller currently predates this route. Fresh read-only
host evidence reports the live-transition journal as `generated_restored`,
which meets the installer's state prerequisite for a separately reviewed
controller replacement. Exact identity, helper hash, authority and source
checks still apply. The application image must also contain the exact probe
module; it has not been deployed on PP.
Only then may an operator perform a dry-run preflight and propose one bounded
live call. The 5,268-row outbox and sustained sync remain separate gates.
Storage archives, first sealed-generation verification and retirement are
still OFF and require their own authorization and evidence.
