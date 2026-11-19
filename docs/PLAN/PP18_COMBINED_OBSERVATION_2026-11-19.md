# PP18 combined observation and retained-A outcome

November 19, 2026 UTC. Sanitized local evidence; the pinned runtime source was
`74a850bc90f5cad40e7d342bd580f151bfe65e3f`. Subsequent source/docs merges did
not deploy that runtime. This document grants no retirement or operational authority.

## Outcome and measured times

**The required 30-minute B continuity run failed.** The operator reports early
durable collector OFF at 08:50:36.853109 UTC with `ownership.lease_lost`, following a
lifecycle-role connection rejection at 08:50:36.850. B collected for 20m32.235895s
and retained 9,784 raw events; no planned 09:00 completion is claimed. Local
diagnostic at 08:52:15.542668 confirms collector disabled, process stopped and
that failure code. The forced OFF gate was 08:52:26.279678 and the local
observer stopped 08:53:10.651252. Database sampling assertions also failed after 08:51:24;
those missing observations are not zero counters or proof of continued writes.

A→B is observed, and B write counters advance before that stop. A raw archive verification completed,
but the bounded final verifier returned **HOLD `archive_limit`**, so A remains
attached with **28,411 local raw rows** and no retirement. This is successful
retention on an incomplete final verification, not successful local deletion.

A sealed at `2026-11-19T 08:30:04.617214+00:00` and raw verification completed at
`2026-11-19T 08:38:23.243026+00:00`: **498.625812 seconds
(8m18.63s)** elapsed. The recorded verified archive has **28,411 rows,
57 chunks and 3,623,081 compressed bytes**. Raw
verification and the full structured/raw final verifier are distinct gates.

The inventory examined **31,162 structured rows / 63 pages / 50,073,891 bytes**,
with 57 raw objects / 3,623,081 bytes. Its bounded upper byte estimate was
267,864,233 versus a 134,217,728-byte limit and its fit was conditional on newer
revision bytes. These inventory estimates do not replace final readback. The
final verifier returned `archive_limit` under its unchanged 240-second budget;
that generic result does not by itself identify time, byte or request exhaustion.
The measured ticket-issue→container-die interval is 247.855136s, including
startup/finalization; it is not verifier-exclusive time or dominant-phase proof. Its unused ticket expired, the ticket file
was absent, and reconciliation at 08:48:37.737712 recorded A still attached,
28,411 rows and no `retired_at`.

The carried retained subset 11989 has matching local, cloud and independent
client canonical stream hashes (`406f45fb…e7f869`, 18,879,672 bytes). That client
readback used earlier pinned source `1c753c6`, 24 operations/46.099s and zero
writes/ACK changes; it is not a new full 31162-row final-A client readback or
proof against the PP18 runtime. The exact scoped receipts remain in JSON.

## Writer switch and truthful dashboard output

The writer change is bracketed by database observations at
`2026-11-19 08:29:45.444937+00:00` and `2026-11-19 08:30:17.153041+00:00`. The exact switch
instant is unknown. This is a writer-generation change, separate from market
rollover and Coinbase event advancement.

The nearest pre-bracket API sample was 08:29:40.681979, with saved/live current
numeric output and input ages 1.409436s/1.203794s. The nearest post-bracket sample
was 08:30:20.725197, on new market 2684759 and generation B, with both outputs
unavailable. At **2026-11-19T 08:30:25.738910+00:00**, both recovered current numeric output:
feature age **5.522756s**, saved input age
**6.692186s**, live input age
**1.258448s**. Ages use server `generated_at`,
not the operator's wall clock.

The offline classifier therefore reports **dashboard publication integrity
PASS**, but **strict numeric switch continuity
INCOMPLETE**. The predeclared nearest-side check remains
incomplete because the first post-bracket observation was unavailable; later
numeric recovery does not rewrite that check.

Across `2026-11-19T 07:58:38.436367+00:00` through
`2026-11-19T 08:53:08.626636+00:00`, **690 captured payload samples**
classify as follows. These are sampled observations, not continuous availability.

| Output | Current numeric | Truthful abstain | Unavailable | UI age-suppressed numeric |
|---|---:|---:|---:|---:|
| Saved | 622 | 14 | 54 | 0 |
| Live | 530 | 18 | 54 | 88 |

Truthful `reference_price_not_fresh` abstention preserves missingness, but does
not establish continuous input freshness. Saved/live stale-reference abstain
counts are 10/
11. Source
Coinbase age reached **49.357s**
while the sampled collector flag was true. Across all samples, including after
OFF, that age reached 153.634s;
this later aging is not an active-collection delay. Live numeric ticks aged 10–30s are intentionally hidden
by the dashboard and counted separately; they are not accepted current headline
forecasts. No forecast quality or calibration conclusion follows.

## Observation gap and sampled API contracts

The payload observation gap was **91.281318 seconds** from
`2026-11-19T 08:33:50.960563+00:00` to `2026-11-19T 08:35:22.241881+00:00`. Saved and live output were
current numeric on both recorded sides; B remained the writer. There is no
proof of uninterrupted collection or publication inside that gap. The separate
state, contract and database datasets retain their own exact gaps in JSON;
contract and generation gaps were about 131s and 132s.

There were **637 state samples** (600 with collector flag true), 0 recorded request
errors and storage status `ok` in all 637;
health statuses were {'degraded': 66, 'ok': 571}. State latency median/p95/max was
**109.325/
129.774/
215.055ms**. These include the
observer's path; p95 is nearest-rank over sampled requests, not a service SLO.

The contract dataset contains **53 checks**. Dashboard HTML wiring,
nonempty prediction history and initial SSE environment binding were present
in all recorded checks. Chart nonempty-points check was false at 08:00:08.660029,
08:15:09.584043 and 08:30:10.795726 during market gaps. These checks do not
prove a rendered browser, active numeric forecasts or continuous SSE coverage.

## B writes and resource counters

Between B observations `2026-11-19 08:30:17.153041+00:00` and `2026-11-19T 08:56:09.912353+00:00`:

| Counter | First | Last | Delta |
|---|---:|---:|---:|
| raw_events | 147 | 9,784 | 9,637 |
| acknowledged | 0 | 10,971 | 10,971 |
| pending | 147 | 0 | -147 |
| relation_bytes | 335,872 | 18,391,040 | 18,055,168 |

Acknowledged and pending structured rows are separate from raw event counts.
These deltas demonstrate B writes and sync progress between samples, not lossless
continuous coverage or sustained headroom. Final queue drainage is proven separately below. Database
size and cumulative WAL endpoints are retained in JSON; they do not prove CPU,
memory, disk reclamation or a compute-upgrade benefit. Filesystem preflight at
07:39:26 recorded 56,671,576,064 bytes available against 10,737,418,240 required;
it is not a whole-run low-water measurement. No CPU/RSS samples were collected.

At 08:25:34 the structured worker held after a lifecycle-role connection rejection
(`too_many_connections_for_role`). Database sampling subsequently used the reader
role, and the operator resumed structured sync. This was a real connection-budget
contention event; API publication integrity does not waive that operational gap.

## Decision and remaining gaps

Keep local A and preserve the HOLD outcome. Qualify full-path verification within
the unchanged byte/request/deadline budgets before another retirement attempt.
Binary-format byte savings and recurring session reuse remain separate candidates;
no latency, privilege or deadline waiver is inferred from their research.

Post-OFF drain reached zero pending at 08:56:08.264388. The raw worker was OFF
at 08:56:08.726312 and structured worker OFF at 08:56:09.689807. Final database
sample 08:56:09.912353 has collector disabled, no session/lease, A 31,162
structured ACKs / zero pending and B 10,971 structured ACKs / zero pending.
A is verified/attached; B remains locally retained and unsealed, with 9,784 raw
rows. No raw-cloud verification or retirement of B is claimed. The early OFF
remains a failed continuity requirement despite successful backlog cleanup. No
legacy environment or production claim is made. This PR changes evidence/docs
only; it does not change a host, reader, collector, workflow, cloud setting,
credentials, grant or deployed source.

[Sanitized machine-readable evidence](evidence/pp18-combined-observation-2026-11-19.json)
contains hashes of local input artifacts, exact switch/gap samples, API summaries,
raw/inventory/HOLD reconciliation and B counters. It includes no raw bodies,
DSNs, tokens, runner credentials or host commands.
