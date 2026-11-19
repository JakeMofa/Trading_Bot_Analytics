# Exact trial cloud child profiles and readiness

Source-only continuation of the OFF preparation milestone. The exact scope is
`pp-live-pp-trial-20261119-01` and its root-bound initial A. No hosted/host call,
credential provisioning, policy/grant change, deployment or collector ON was
performed for this source work.

## Isolation and controls

The existing root-only `structured-sync-start` and `sealed-archive-start` commands
select the new child launcher only when the trusted active transition names the
exact trial origin. Legacy start/probe/profile paths keep their existing guards.
The child Compose services use the same bounded 128 MiB, 0.25 CPU, capability-free,
read-only, root secret-reading isolation and database plus one egress network.
They launch with `run --no-deps`, never recreating collector/API services.

- Structured child mounts local lifecycle DSN, exact trial SQL writer DSN and
  pinned CA only. It uses the existing 50-row recurring drain and immutable
  revision/readback-before-ACK behavior.
- Raw child mounts local lifecycle DSN and four trial archive Auth writer files
  only. It uses the existing sealed archive bounds and cannot retire.
- The independently attested trial API reader mounts only four reader Auth
  files. It receives no cloud SQL, writer, lifecycle or legacy cloud credentials.

Normalized profile equality checks every field before launch. Owned-container
readiness checks source/image/anchor/proof, exact command/environment, root user,
resources, read-only mounts, networks and no published ports. Failed launch
stops only its owned child; existing ownership journals still fence deployment
and permit-free cleanup. Status includes the exact trial origin and anchor.

Both root ON authority issuance and subsequent session dispatch now require the
writer proof, independent reader attestation and **both** exact owned children
running. Readiness never calls ON or creates an ON permit. Existing root one-use
ON authority is still consumed before activation; normal finite 4560-second
sessions and the explicit 6600-second/final-minute trial contract are unchanged.
A missing/malformed proof or stopped/misbound worker holds before consumption.
Optional reader evidence is excluded from OFF/leave recovery composition so its
corruption cannot prevent durable collector OFF or generated restoration.

## Fixed files and proof contract

Root-only writer sources remain under `/etc/tradebot/cloud/`:
`trial_20261119_01_history_writer_dsn`, existing `pp_history_ca`, and
`trial_20261119_01_archive_{api_key,email,password,uid}`. Private files are root
0600, CA root0644; directory root0700. SQL container DSNs require literal
`sslrootcert=/run/secrets/pp_history_ca` and the exact trial role application name.
The host never opens credential contents except identity UIDs; containers read
their own least-privilege files. File identity, modes, ownership and pinned CA
checks remain enforced.

`/etc/tradebot/pp-runtime/trial_writer_authority.json` and
`trial_writer_proof.json` are root0400. Authority has exactly:

```json
{"version":1,"scope":"pp-trial-cloud-writer-v1","origin_id":"pp-live-pp-trial-20261119-01","initial_a":"<canonical UUID>","source_sha":"<40 hex>","image_id":"sha256:<64 hex>","proof_sha256":"<exact proof file SHA256>"}
```

Proof has exactly `version:1`, the same `origin_id`,
`sql_writer_role:tradebot_pp_trial_20261119_01_writer`,
`sql_reader_role:tradebot_pp_trial_20261119_01_reader`, distinct canonical
`archive_writer_uid` / `archive_reader_uid`, and these independently qualified
verdicts, each exactly `pass`:

- `sql_writer_insert`, `sql_reader_select`, `sql_wrong_origin_denied`,
  `sql_reader_mutation_denied`;
- `storage_upload_readback`, `storage_wrong_origin_denied`,
  `storage_reader_get`, `storage_reader_create_denied`.

Those claims must follow actual bounded hosted checks. The create-denial verdict
does not claim every Storage mutation was tested on the hosted API. Writer UID
must match the fixed writer file, reader UID its staged reader file, and neither
may reuse the legacy writer UID. Reader authority/proof use the separate exact
schema in [reader attestation](PP_TRIAL_READER_ATTESTATION_2026-11-19.md), bound to
this source/image/anchor and exact object evidence. No legacy reader proof can
qualify the trial.

## Source evidence and limits

Eight new cloud-host tests pass, including actual Docker Compose normalization
with/without the API reader and both child profiles, role-secret exclusion,
wrong-origin/isolation rejection, source/image/anchor/proof rejection, owned
launch cleanup, two-child readiness, mocked one-use dispatch ordering and OFF
recovery despite corrupt reader evidence. The surrounding host test suite and
workflow controls were also run. Six platform-specific host tests remain skipped.
The two historical controller-transfer scripts keep their exact ten-member
protocols; only their generated fixture bundles use that historical shape.
The new installer separately requires exactly thirteen named bundle modules.

These generated checks do not establish a live trial, remote performance,
actual runtime readiness or retirement. Exact combined CI, release/image and
root evidence staging, bounded host readiness, original seal deadlines and
separate per-generation retirement permits remain operational gates.
