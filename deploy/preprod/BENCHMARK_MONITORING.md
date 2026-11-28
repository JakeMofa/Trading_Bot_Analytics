# Benchmark monitoring

The 4 GB Benchmark service reads `http://127.0.0.1:8000/system/telemetry`
every 15 seconds and sends timestamps, counts and ages to the TokenBot
Grafana Cloud Prometheus tenant. The collector sends cumulative sanitized
failure and retry counts to the API over its private Unix datagram socket.
The sender runs independently of browser tabs, SSH and the operator account.
It has no database, exchange or collector-control credentials.

Install this unit only on the Benchmark host after the matching release is
qualified. Install `benchmark_metrics.py` root-owned under
`/usr/local/lib/tradebot-benchmark/`, install
`tradebot-benchmark-metrics.service` under `/etc/systemd/system/`,
and create `/etc/tradebot-benchmark-metrics/` mode 0700. Stage the approved
metrics-write token as `metrics-write` mode 0600. Set `GRAFANA_METRICS_USER`
in the private `account` environment file. systemd supplies a protected,
read-only credential copy to the dynamic user. Enable and start this unit
after the approved transfer, then verify fresh data from Grafana. A change
of tenant requires review of the pinned remote-write host.

Local proof includes the target origin, current A/B generation, attached
draining window, durable collector lease, verified ACK deltas, pending count
and oldest age. The aggregate read uses one read-only transaction with a
1.2-second statement timeout and a 15-second shared cache. A timeout leaves
the database status unknown. Compare this query on future 72-hour volumes.
The API sampling round trip is a private local request. Feed age measures
the actual provider timestamp or PP receipt timestamp. Auth, HTTP rate-limit,
network and retry counters only increment for real observed failures.
The per-process counters reset when the collector session is restarted.
Raw provider bodies, identifiers, secrets and Docker logs stay off Grafana.

The [dashboard](https://heftychameleon632.grafana.net/d/jagbfc8/tokenbot-observability)
already has collector and rolling-slot status and hosted SQL/connection/I/O
panels. The [Benchmark stall alert](https://heftychameleon632.grafana.net/alerting/grafana/bg5mmzb2nturkb/view)
uses a ten-second evaluation interval and a one-minute pending period.
The older trial05/06 rule retains its original scope. A Grafana test email
was accepted by the contact integration. Inbox receipt is unverified.
