# Production preflight diagnosis — November 1, 2026

**Evidenced operation:** deployed `streaming.rest_loop` awaits the complete slow
`feature_cycle` before its30s pause and next REST discovery/`sync_live_market`.
Polymarket subscription rollover depends on that RAM identity. Across16:15UTC,
this kept the websocket following ended market2038542 instead of2037956.
Coinbase collection and HTTP service continued. No retention load had started.

**Smallest proposed fix:** reuse the already-tested independent REST/feature
scheduling from `a6958f6` (`rest_loop`, single serial `feature_loop`, awaited worker
and publication guards). Discovery must not await feature completion. Do not
bundle checkpoint ownership changes. Do not deploy or build indexes under this
read-only instruction. Independent scheduling fixes this dependency; it does not
make the183–186s feature computation fresh. The prepared publication age/market
guards must reject those stale results, and feature query/index qualification
remains separate. No runtime change was made.

All times below are November1 **UTC** (Chicago CST = UTC minus6h).

| Evidence | Timestamp / duration |
|---|---|
| Last discovery before boundary succeeded | 16:14:45.968105 |
| Feature worker starts | 16:14:46.019391 |
| Old market2038542 ends / new2037956 starts | 16:15:00 |
| Last advancing old-market book source timestamp | 16:15:15.440365678Z |
| Its first local receipt | 16:15:15.517345 |
| Repeated identical source timestamp received | 16:15:46.684883,16:16:17.954791,16:16:49.162850,16:17:20.356350,16:17:51.562487,16:18:22.707881 |
| Initial failed preflight HTTP200 | 16:16:42.426392 |
| Feature worker finishes | 16:17:51.940735;185.921s |
| New market first persisted / discovery success | 16:18:26.153924 /16:18:26.172766 |
| First new-market book source / receipt | 16:18:26.746047160Z /16:18:26.836114 |
| Recovery-window last probe HTTP200 | 16:19:11.881732 |
| New-market feature cycle finishes | 16:21:29.989157;183.695s;as_of16:18:26.295258 |

## Source failure versus classification

The affected path is **Polymarket current-market collection**. New-market metadata
was first seen206.154s after its start; first websocket book206.836s after start.
This is an observed collection delay, not proof that the venue failed to publish
the new market earlier. No contemporaneous venue/network capture exists.

Old-market receipts did not cease entirely: six repeated snapshots arrived about
every31.15–31.27s, all with exactly the same old source timestamp. Their timing,
plus reconnect count1088 at16:15:30 and1094 at16:20:40, is consistent with the
existing30s silent-feed/reconnect path. Individual reconnect transitions are not
logged, so their precise cause/times cannot be certified. The interval between
the last advancing old book receipt and first new book receipt is191.318769s.
The interval between the last replay receipt and first new book is only4.128233s;
calling that the full interruption would hide the stale source/market problem.

At the initial failed probe16:16:42.426392, the nearest preceding persisted
Polymarket receipt was24.471601s old and belonged to the **ended** market; Coinbase
receipt was0.080797s old. At recovery start16:17:11.105647, corresponding ages were
21.942797s and0.157502s. The deployed Polymarket loop marks no-book periods stale
after15s, but reports live/data=True on each successfully saved replay regardless
of old source timestamp or expired market. This explains alternating receipt-based
health while the real current-market gap persisted. The failed preflight body and
per-probe statuses were not saved: the exact enum/transition instant at assertion
is unavailable, so receipt reconstruction is not presented as a captured response.

The preflight was **not shown to be falsely rejecting healthy current-market
data**. There is direct evidence of missing current-market collection. There is
also a separate **false-healthy** problem: at16:15:30 the existing telemetry
recorded `/health` status=ok, Polymarket status=live, and market2038542 with
end16:15:00/seconds_remaining0. The aggregate health checks presence of cached
required data, not market expiry; successful replay saves refresh receipt health.
A robust health correction must distinguish receipt liveness, source-time
freshness and active-market identity, and degrade ended/mismatched market state.
The existing `ea6e6de` stopped-collector health correction does not address this
case: the collector was running. Do not represent that fix as sufficient.

Once new books resumed16:18:26.836114, at most~45s remained before the recovery
window's final probe;13consecutive5s samples require60s between first and last.
Thus later recovery does not invalidate the bounded preflight STOP. Exact status
history during every sample is unavailable; no precise continuous stale-enum
start/end claim is made.

## Correlated collection, features and API

Bounded16:13..16:21 receipt sample contains2624Coinbase events. Maximum interreceipt
gap4.908937s; source-to-receipt delay0.008083..1.612083s. No corresponding multi-
minute Coinbase interruption is evidenced. REST run records show no discovery
between16:14:45.968105 and16:18:26.172766 (220.204661s); both runs succeeded. The
feature185.921s await plus30s pause accounts for most of this interval. Worker
containment kept the event loop responsive but did not decouple REST scheduling.

The journal contains HTTP200 for the initial failed preflight and all25recovery
probes16:17:11.105647..16:19:11.881732. HTTP200 is not evidence of healthy sources.
There are no paired request-start logs to derive historical HTTP latencies; the
original runner's2s timeout did not trigger. Follow-up read-only calls at16:28:42
completed `/health` in53.3ms and `/state/current` in38.8ms. These are single samples,
not a recovery soak.

The185.921s worker published an old-market snapshot as_of16:14:46.021171 at
16:17:51.940735. After rollover a183.695s worker published new-market snapshot
as_of16:18:26.295258 at16:21:29.989157. Its internal price=fresh log refers to its
historical as_of, not freshness at publication. At16:20:40 both feeds were live
but aggregate health was correctly degraded for missing new-market features.
These are separate freshness issues, not evidence of a dead API or collector.

## Bounds, reuse and limitations

Read-only evidence: six minutes of existing journal (44entries), then two minutes
of feature journal (cap100entries); latest8192observation rowids,32768stream rowids,
32markets,64feature snapshots,256runs; a262144-byte telemetry tail. Receipt details
were filtered locally to16:13..16:21. Follow-up selected only21identified observation
IDs623870..623890 to compare exact source timestamps. Queries used bounded rowid
order/ranges, mode=ro/query_only and progress deadlines. No timestamp historical
scan, production trace, generated load, restart or configuration mutation.
Service-user journal read was denied before queries; the same read-only request
was run with existing root access. No credentials/environment were read.

Deployed streaming SHA remains
`95a49c2ac04b6dbb04223e0f363df0a6132bd7b0cc10fda7145a2055bd1efa12`, matching the
previously pinned d56b4a7 source. Source inspection establishes the dependency;
receipt/journal/telemetry evidence establishes its occurrence at this boundary.
No live expensive feature SQL was timed or traced, so this investigation attributes
the blocking scheduling operation, not an individual SQL query's current latency.

Prepared change `a6958f6` already tests discovery advancing while one feature worker
waits, absence of overlapping workers, stale/expired/mismatched publication refusal,
and worker cancellation. See [prepared freshness validation](I7_FRESHNESS_LOCAL_2026-10-31.md).
Reuse those changes for a narrowly reviewed rollover correction. Preserve the
existing separate feature-index storage/build qualification; do not promise fresh
features from scheduling alone. A source-time/expired-market health regression is
still needed before claiming truthful overall health in this case.

Evidence outside repository:
`/Users/jake/Documents/ChatGPT/TradebotAnalytics/evidence/phase175-baseline/lifecycle-implementation-20261031/feed-preflight-diagnosis-0c46f45/`.
Contains bounded projections, reader scripts and checksum manifest; no database.

Retention commit issue remains OPEN separately; no cleanup, enablement, manual
WAL operation or acceptance-gate change. Production deletions0, paidAI/retention
OFF; I7/Phase1.75 OPEN, Phase2 deferred. Temporary cap-review deadline unchanged:
2026-11-02T01:56:47.671426Z.
