# First PP live PostgreSQL trial — November 17 CST / November 18 UTC

## Outcome

**FAIL, bounded and recovered.** PP collected real Coinbase and Polymarket US
15-minute data for 159 seconds, then its session ended at a market boundary.
PP is restored to generated mode, collector OFF. Its PostgreSQL volume and
committed `pp-live-pp` data remain. This does not qualify I7, a 72-hour window,
Supabase archive/readback or local retirement.

## Scope and controls

- PP host `tradebot-preprod-01`, separate `pp-live-pp` origin and PostgreSQL.
- Published source `9dbeec6ef57ae2089109c21877436cc9ed46625a`, image
  `sha256:1b9426d2cc1a01118c544cdfb6ea62e7e33900987297b7d1277cc5462195190a`.
- Controller SHA-256 `bdb11511039365990249846d1e5a521228255530db000a25181ad260f7aebee7`.
- One-use ON permit and a 1,800-second maximum lease. Cloud sync, retirement,
  trading and paid AI stayed OFF. Production was untouched.
- The PP firewall added only the current operator `/32`, retaining prior SSH
  CIDRs and the Lightsail browser alias. Pinned SSH succeeded.

## Sequence (UTC)

| Checkpoint | Evidence |
|---|---|
| Before ON | Generated PP API, four application containers and PostgreSQL were healthy; collector OFF. |
| READY_OFF | [Workflow 44209122389](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44209122389) host artifact recorded `PP_LIVE_READY_OFF`, origin `pp-live-pp`, collector OFF. Workflow result **FAILED** because its reporter returned exit 1 after replacing its PASS gate with the host gate. |
| Initial OFF | Private operator status showed `initialized=false`, collector OFF. Authenticated OFF returned HTTP 503 and the installed controller blocked. |
| Bootstrap / OFF | Existing lifecycle `--bootstrap --once` created an empty PP live A generation. Pinned-controller `session-v1 off` returned `PP_LIVE_OFF`; status confirmed initialized true, process stopped, collector OFF. |
| 00:42:33–00:45:13 | Pinned-controller `session-v1 on 1800` returned `PP_LIVE_ON`. First raw acknowledgement was 00:42:34.017. Initially both feeds were fresh; a bounded API sample showed Coinbase input age 1.1 s, feature age 4.5 s and Polymarket receipt age 6.2 s. |
| 00:45 boundary | Market ID advanced from `2633366` to `2637773`. At 00:45:21 Polymarket was missing and the new-market feature/prediction were unavailable; at 00:45:43 Coinbase was stale. |
| 00:45:13 OFF | The writer row updated at 00:45:13.079. Last Coinbase and Polymarket raw receipts were 00:45:12.836 and 00:45:12.551. The collector process was no longer running. |
| Recovery | Explicit `session-v1 off` returned `PP_LIVE_OFF`; `transition-v1 ... leave` returned `PP_GENERATED_RESTORED` with collector, cloud and retirement OFF. The PP API reported generated mode; all five containers were running; PostgreSQL was not recreated. |

Read-only PostgreSQL queries with a three-second SQL deadline counted:

| PP live dataset | Persisted rows |
|---|---:|
| Raw Coinbase | 1,360 |
| Raw Polymarket US | 29 |
| Feature snapshots | 28 |
| Predictions | 28 |
| Markets | 2 |
| Pending cloud outbox | 1,530 |

The pending outbox is local because cloud sync is OFF. It does not prove
Supabase archival. A bounded post-recovery sample measured PP database
43,267,763 bytes, A relation 2,711,552 bytes, WAL segment allocation
33,554,432 bytes, free filesystem 56,830,771,200 bytes and available RAM
1,202,831,360 bytes. The 1,389 raw-row count was exact below the 10,001-row
sample bound. No production row was changed.

## Failure and next gate

The exact supervisor exception was not retained: `OperatorSession` records
only `session_failed_or_cancelled`, which explicit OFF clears. Boundary timing
does not prove which source or operation failed. The planned 20-minute observer
was stopped early after durable OFF, so its acceptance report is **NOT
PERFORMED**. Limited API probes responded; zero two-second timeouts over the
required observation window was not measured.

The reporting correction in [PR #85](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/85)
does not retroactively pass the failed workflow. Clean-start OFF also needs
a code fix so a new origin does not require manual bootstrap to prove OFF.
Record a fixed, sanitized task/source failure code in private operator status
before another bounded trial; do not log provider bodies, URLs, credentials or
payloads. Then qualify the exact release and rerun the feed, prediction,
dashboard/SSE, freshness and market-boundary checks. A size-triggered A/B
switch, Supabase write/readback and retirement remain separate gates.
