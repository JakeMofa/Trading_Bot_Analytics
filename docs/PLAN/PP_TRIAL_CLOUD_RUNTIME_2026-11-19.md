# Exact trial cloud application wiring — source only

Base `307e5f4`. Scope is exactly `pp-live-pp-trial-20261119-01`, alongside the
unchanged legacy `pp-live-pp` defaults. This milestone made no host/cloud call,
secret deployment, credential provisioning, policy application, collector start
or partition retirement.

The new `backend/postgres/cloud_runtime_profile.py` centralizes fixed container
credential targets. Writer/verifier entrypoints select the exact origin from
the existing reviewed environment. Trial selection requires preprod/pp_live,
`TRADEBOT_PP_WINDOW_POLICY=two-official-markets-cycle` and the canonical
`TRADEBOT_PP_CYCLE_INITIAL_A` UUID. Unknown origins, missing/wrong profiles and
opposite-role secret paths fail before reading secrets or opening connections.
There are no path overrides or inline cloud DSNs.

## Runtime data paths

- `pp_structured_service`: trial writer SQL factory and role; explicit selected
  origin flows through `drain_bounded` into pending-generation selection and
  Active/SealedStructuredWorker. Thus the new service cannot accidentally drain
  the old origin's outbox. Existing page caps, fresh readback-before-ACK and
  recurring/one-shot exclusion remain. Revision retention still requires its
  existing explicit `TRADEBOT_PP_RETAIN_REVISIONS=true` profile flag.
- `pp_sealed_archive`: trial writer Auth identity, exact raw prefix and explicit
  origin selection/lock/query throughout recurring cycles. It still waits for
  verified structured acknowledgements and never retires. Auth readback failure
  preserves sealed data and emits a hold.
- `pp_retirement_verify`: trial read-only SQL role and separate history-reader
  Auth identity, both scoped to the exact target origin. Trial requires the
  existing two-market-window gate; window deadlines, tickets, source/proof
  binding and retirement authority checks are unchanged. Optional `--origin`
  asserts the environment origin; mismatch fails before secret access. A
  readback without a separately issued permit remains read-only.
- `runtime_history`: explicit `TRADEBOT_PP_ARCHIVE_HISTORY=true`, preprod/pp_live
  settings and one of the two exact origins. The trial API lazily creates only
  trial reader Auth transport for an explicit retired-generation read. Attached
  local reads do not open cloud credentials. API reads do not require the write
  cycle admission profile and cannot acquire writer credentials.

The legacy one-shot probe defaults remain unchanged. Their validation helpers
accept an explicit reviewed trial scope for the new service/verifier paths;
this does not make their legacy diagnostic entrypoints auto-select a trial.

## Distinct mount contract for the host integration

Host controller/Compose changes are a separate task. Suggested private host
sources below belong under `/etc/tradebot/cloud/`; the backend consumes only the
fixed targets. Keep old secrets unchanged for the separately scoped old A/B
disposition. All existing file ownership/mode/TLS checks still apply.

| Consumer | Container target | Suggested host filename |
| --- | --- | --- |
| Structured writer only | `/run/secrets/pp_trial_history_writer_dsn` | `trial_20261119_01_history_writer_dsn` |
| Verifier only | `/run/secrets/pp_trial_history_reader_dsn` | `trial_20261119_01_history_reader_dsn` |
| SQL consumers | `/run/secrets/pp_history_ca` | Existing pinned CA |
| Raw archive writer only | `/run/secrets/trial_archive_api_key` | `trial_20261119_01_archive_api_key` |
| Raw archive writer only | `/run/secrets/trial_archive_email` | `trial_20261119_01_archive_email` |
| Raw archive writer only | `/run/secrets/trial_archive_password` | `trial_20261119_01_archive_password` |
| Raw archive writer only | `/run/secrets/trial_archive_uid` | `trial_20261119_01_archive_uid` |
| Verifier and history API | `/run/secrets/trial_history_reader_api_key` | `trial_20261119_01_history_reader_api_key` |
| Verifier and history API | `/run/secrets/trial_history_reader_email` | `trial_20261119_01_history_reader_email` |
| Verifier and history API | `/run/secrets/trial_history_reader_password` | `trial_20261119_01_history_reader_password` |
| Verifier and history API | `/run/secrets/trial_history_reader_uid` | `trial_20261119_01_history_reader_uid` |

Structured/raw/verifier retain their existing local lifecycle DSN target
`/run/secrets/lifecycle_dsn`. API uses its existing application/local reader
connection, not lifecycle credentials. API needs no cloud SQL DSN to serve raw
archive history. Never mount writer secrets in the trial verifier/API.

`cloud_files(origin,reader=...)` returns the existing environment keys with these
exact paths: `TRADEBOT_PP_HISTORY_DSN_FILE`, `TRADEBOT_PP_HISTORY_CA_FILE`, and
`TRADEBOT_PP_STORAGE_{API_KEY,AUTH_EMAIL,AUTH_PASSWORD,AUTH_UID}_FILE`.
Structured checks SQL keys; raw worker checks Storage keys; trial verifier
checks both reader SQL and Storage keys. Existing service opt-in/OFF flags are
still required. The API reader uses fixed targets directly, never environment
path redirection.

## Evidence and remaining deployment gates

Eight new generated application-wiring tests pass. They execute the actual main
entrypoints with intercepted dependencies and actual in-memory archive/drain
cycles, proving writer/reader selection, exact trial outbox scope, fresh
readback before ACK, failure preservation, correct raw-prefix keys, lazy API
reader construction and misbound credential rejection before I/O. Sixty-seven
surrounding targeted controls also pass (75 total), including six native
Unix-socket PG17 policy/receipt/envelope tests. No tests in this targeted set skip.

The host task must independently stage/prove exact new SQL/Auth identities,
apply the reviewed additive policies, pin source/image/profile and mount only
the intended role's files. Reader readiness/proof must bind the exact trial
origin, source/image, reader Auth UID and SQL reader role; do not reuse a legacy
reader proof. Verify actual bounded cloud readback and wrong-origin/mutation
API denials before collection/retirement. Role/session capacity and real network
throughput remain live gates. This source wiring alone authorizes no live action.

```sh
PYTHONPATH=backend python -m unittest discover -s backend/tests -p test_trial_cloud_runtime.py -v
```
