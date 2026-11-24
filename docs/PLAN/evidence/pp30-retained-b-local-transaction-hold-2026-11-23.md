# PP30 retained-B local transaction hold

The one bounded read-only diagnostic ran on November 23, 2026 at 6:56 p.m.
CST. It used the deployed PP30 image and the diagnostic modules from
`cf43a91`, whose [exact CI](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/45298582646)
passed. The disposable container had no external egress or hosted credentials.

| Observation | Result |
| --- | --- |
| Local outbox coverage query | 1.532075 seconds |
| Local page-size query until cancellation | 1.874154 seconds |
| Cancellation | SQLSTATE `25P04` at the 3.5-second local transaction limit |
| Local connection, outside that transaction | 1.914894 seconds |
| Diagnostic elapsed | 5.425543 seconds |
| Requests to Supabase | 0 |

The 2-second statement and 250-ms lock limits were preserved. The diagnostic
ended before local page payload retrieval. It establishes where the reproduced
first-page check stopped. The complete live verifier's 240-second hold still
needs separate qualification. Both collectors stayed off and no partition was removed.

The deployed PP live profile rejects a size override. Generated PostgreSQL 17
tests separately passed the size-triggered A-to-B switch with continued B
writes during authenticated readback, and preservation of sealed A during
outage and corrupt readback. The live size-trigger path requires its own
default-off profile, new isolated origin, explicit bounded settings and
independent final verification. Previous trial scopes remain preserved.
