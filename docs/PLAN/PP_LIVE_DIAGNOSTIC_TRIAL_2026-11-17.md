# PP live diagnostic trial — November 17 CST / November 18 UTC

## Result

**FAIL; recovered.** The second bounded PP-only live session stopped before a
market boundary with private operator code `coinbase_stream.unexpected`. The
exact WebSocket exception was not retained, so this code identifies the failing
stage but does not establish whether the cause was a close, handshake, network
error, or another exception. There was no unchanged retry. The first
generated-profile leave attempt failed after service recreation; one bounded
permit-free recovery leave passed. PP is now in generated mode with its
collector durably OFF. Production was not changed.

## Exact release and scope

- `preprod` application source `437d0a4e56900038afe3203229bc1fb1f6284824`;
  [exact push CI 44214616202](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44214616202) PASS.
- Immutable PP candidate `v0.2.0-pp.9`, source bundle SHA-256
  `29a1dc6e22830f38015c0870ac6863c7483a33bc41535f2b73a8a95ad4675fa6`,
  runtime image ID
  `sha256:8b3912fd131fec1e6987a7d8cf4242896fbe62f64472aa4600612ca6c7778566`.
  [Candidate workflow 44215401524](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44215401524) PASS;
  [manual CD Preprod 44216017150](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44216017150) PASS with 11 generated-mode acceptance checks.
- Existing pinned, root-owned PP controller SHA-256
  `bdb11511039365990249846d1e5a521228255530db000a25181ad260f7aebee7`.
  A one-use READY_OFF and ON authority was consumed. The temporary private
  runner completed its job and was deregistered.
- PP host `tradebot-preprod-01` only. Cloud sync, local retirement, paid AI and
  trading remained OFF. PostgreSQL was not recreated. No Supabase operation or
  production change was made.

## Bounded observation

The controller returned `PP_LIVE_ON` at about 01:38:54 UTC for a maximum
600-second session. The authenticated private operator status captured
`coinbase_stream.unexpected` immediately after the task stopped, before
service restart cleared its in-memory code. Its durable writer state was OFF
at 01:43:36.729 UTC, about 282 seconds after ON. Explicit `session-v1 off`
then returned `PP_LIVE_OFF`.

The private API observer took 120 five-second samples over 600 seconds; its
overall result is **FAIL**, including post-OFF and profile-transition periods.
The phases must be read separately:

| Period (UTC) | Samples | Result |
|---|---:|---|
| 01:39:16–01:43:36, collector ON | 53 | Zero API errors; maximum successful API latency 190.6 ms; 51 fresh and two stale Coinbase samples, 53 fresh Polymarket samples; maximum feature age 5.403 s and Coinbase input age 33.145 s at the final ON sample. |
| 01:43:41–01:45:16, live profile OFF | 20 | Zero API errors; truthful degraded health as feeds aged. Maximum Coinbase age 133.139 s, Polymarket receipt age 84.625 s and feature age 28.864 s. |
| 01:45:21–01:45:41, first leave | 5 errors | `ConnectionResetError` during application service recreation. This is an API interruption and the original leave command returned `entrypoint_precondition_failed`; its exact failing post-recreation subcheck was not logged. |
| 01:45:46–01:48:46, generated profile | 37 | Generated mode and collector OFF, zero API errors. |
| 01:48:51–01:49:11, recovery leave | 5 errors | Four `ConnectionResetError` and one `RemoteDisconnected` during the second bounded service recreation. The recovery command returned `PP_GENERATED_RESTORED`. |

No `TimeoutError` type or two-second API timeout was observed. The 10 API
transport errors are still failures, regardless of their coincidence with the
two profile transitions. The observer saw 54 distinct Coinbase events, 40
distinct Polymarket receipts, 51 feature cycles and 51 predictions across its
whole interval; these counts are not a production acceptance measure. Only
market ID `2637240` was observed, ending at 01:45 UTC after collection had
stopped. **A real market rollover was not tested.** Source price age exceeded
the 30-second target near failure, and the task stopped before any A/B switch.

Read-only PP measurements before ON and after the task stopped:

| Measurement | Before | After |
|---|---:|---:|
| A raw rows | 1,389 | 4,845 |
| PostgreSQL database bytes | 43,931,315 | 59,791,027 |
| A relation bytes | 2,711,552 | 9,109,504 |
| Allocated WAL segment bytes | 33,554,432 | 33,554,432 |
| Free filesystem bytes | 56,825,651,200 | 56,809,697,280 |
| Available RAM bytes | 1,203,544,064 | 1,157,177,344 |
| Pending local outbox rows | 1,530 | 5,268 |

The outbox did not hit its 10,000-row cap. These are two bounded samples,
not a sustained growth rate or a qualified A/B size threshold. Cloud sync was
OFF, so pending rows were not sent to Supabase.

## Recovery verification and remaining gate

The first leave command marked the root journal `leaving` and had already
recreated the application services in generated mode, but returned
`entrypoint_precondition_failed`. Read-only source-qualified checks of the
generated runtime, host API and authenticated operator route all passed after
services settled. The single existing permit-free bounded leave recovery then
returned `PP_GENERATED_RESTORED`; the journal is `generated_restored`. API is
`generated-pp`, collector OFF; operator reports `process_running=null` and
collector OFF. API, calculation, lifecycle and operator containers are running
the exact image with zero automatic restarts. The PostgreSQL container ID is
unchanged. The original leave failure is not reclassified as PASS.

**Next engineering action:** retain this failed trial, classify the actual
Coinbase WebSocket exception into a sanitized, specific code and test that
taxonomy offline. Investigate the generated-profile readiness race revealed
by the first leave failure. Do not repeat the unchanged live trial. A later
separately qualified trial must prove a real boundary and the intended A/B
switch before claiming CP7 acceptance. Supabase archive verification, local
retirement, I7 and Phase 1.75 remain open.
