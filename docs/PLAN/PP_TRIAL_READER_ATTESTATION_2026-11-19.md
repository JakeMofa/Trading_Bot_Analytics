# Exact trial archived-history reader attestation — source only

Base `b956214`. `deploy/preprod/trial_history_reader.py` supplies the isolated
host predicate `trial_history_reader_enabled(context, initial_a=None)`.
`runtime.trial-history-reader.compose.yaml` introduces only four dedicated
reader Auth secrets into the API and sets exact trial origin plus the existing
archive-history flag. No SQL/writer/lifecycle/admin or legacy reader credentials
are added. Host profile/start integration is a separate change; this milestone
made no host/cloud call or mutation.

The predicate returns False only when its authority marker is absent. An
existing unsafe, malformed, stale, incomplete or mismatched binding raises
`DeploymentHold`; it never silently falls back to the legacy reader. It exports
`TRIAL_HISTORY_READER_FILES` and `TRIAL_HISTORY_READER_OVERLAY` for the host
integration, with no import dependency on `linux_actions`.

## Exact v1 file contract

Fixed host directory: `/etc/tradebot/pp-runtime`.

`trial_history_reader_authority.json`, root-owned regular file, mode 0400,
single link, at most 4096 bytes, must have precisely these fields:

| Field | Required value |
| --- | --- |
| `schema_version` | Integer `1` |
| `scope` | `pp_trial_raw_get_only_v1` |
| `origin_id` | `pp-live-pp-trial-20261119-01` |
| `source_sha` | Full final candidate source SHA, matching `context.request.source_sha` |
| `image_id` | Exact `sha256:…`, matching `context.image` |
| `initial_a` | Canonical actual trial initial-A UUID; must match caller's anchor when supplied |
| `reader_uid`, `writer_uid` | Distinct canonical reviewed trial Auth UUIDs |
| `policy_proof_sha256` | SHA-256 of the exact proof file bytes, including whitespace |

`trial_history_reader_proof.json`, root-owned regular file, mode 0400, single
link, at most 8192 bytes, must have precisely:

| Field | Required value |
| --- | --- |
| `schema_version` | Integer `1` |
| `project_ref`, `bucket` | `xttdqeimdujweijxcuro`, `market-raw` |
| `origin_id`, `initial_a`, `reader_uid`, `writer_uid` | Exact authority values |
| `effective_role` | `authenticated` |
| `sql_reader_role` | `tradebot_pp_trial_20261119_01_reader` |
| `authenticated_get`, `writer_get` | `pass`, from independently compared actual fixture bytes |
| `sql_read_only` | `pass`, from qualified separate-role SQL policy/privilege evidence; not a claim of an extra hosted probe |
| `hosted_denied` | Exactly `["old_origin","list","upload","sign","public"]` |
| `policy_fixture_denied` | Exactly `["production_origin","replace","move","delete"]` |
| `fixture` | Object below |

The fixture object has exactly `generation_id`, `object_key`, `sha256`, `bytes`.
Its UUID is the designated synthetic Storage fixture generation, **not** the
trial initial-A UUID. `sha256` is the actual compressed object's digest, and
`object_key` must equal
`raw-v1/ab43e88045d4c354566bc2612c83b04a8636bfeea44e54aa839d0f807ac4446f/<fixture UUID>/<digest>.jsonl.gz`.
`bytes` is an integer from 1 through 2 MiB. The reported hosted fixture is 210
bytes; the validator binds the actual reviewed receipt rather than hardcoding
one synthetic object's size for every future candidate.

The evidence split is deliberate. Hosted old-object GET/list/upload/sign/public
checks remain distinct from native reviewed production-origin and replace/move/
delete policy denials. A list response exposing zero objects can establish the
hosted list restriction; this does not assert every denial returned HTTP 403.
No unperformed production object request or destructive replacement/move/delete
probe is required. No code here performs probes or manufactures PASS evidence.

The proof can summarize already qualified cloud/policy evidence before the
final candidate exists. Its separate authority must bind the final reviewed
source/image and trial anchor **after** those values are known. No already
issued release SHA is required inside the earlier cloud receipt. Attestation is
an operator-reviewed binding, not independent remote verification by this module.

Each file named by `TRIAL_HISTORY_READER_FILES` must be a regular single-link
file owned by UID 10001, mode 0400, from 1 through 4096 bytes:

- `trial_history_reader_api_key`
- `trial_history_reader_email`
- `trial_history_reader_password`
- `trial_history_reader_uid`

Only the UID credential's contents are read, and it must equal the proof's
reader UID. API-key/email/password checks inspect metadata only. Authority,
proof and UID reads use O_NOFOLLOW plus before/opened/after inode, ownership,
mode/link/size/time checks. Duplicate JSON keys are rejected. Secret values are
never returned or included in errors.

## Qualification and remaining gates

Six generated tests pass: exact source/image/anchor/identity/role/fixture binding,
truthful hosted/native evidence separation, missing-marker OFF semantics,
proof-byte tamper rejection, metadata/link/symlink/owner rejection, UID-only
credential content reads and reader-only overlay targets. Tests use generated
identities/evidence and make no network calls. Backend trial runtime controls
also pass (eight tests). No deployed marker, staged secret or actual hosted
receipt is claimed verified by this source milestone.

Host integration must call the predicate with the exact active initial-A UUID
and validate the resulting normalized Compose profile against the expected API
reader-only mount delta. Existing backend JWT-origin/role checks, exact raw-key
prefix checks, lazy cloud construction and archive checksum verification remain
independent enforcement. Host operators retain actual probe receipts outside
Git and must never populate unexecuted checks as PASS.

```sh
python -m unittest discover -s deploy/preprod/tests -p test_trial_history_reader.py -v
```
