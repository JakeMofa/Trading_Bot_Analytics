# First PP live observation

This is the collector and PostgreSQL query trial, not an archive or
retirement test. The operator separately enters READY_OFF, authorizes one
session of at most 1,800 seconds, and retains the OFF/leave controls. This
observer cannot change a collector lease, database, cloud object or service.

For a separate PP host resource sample, send the reviewed read-only script
through the same pinned SSH route. Run as root on PP; the script rejects another
host or database binding. Replace `mid` with `before` or `after` for the other
two checkpoints:

    ssh [pinned PP SSH options] "ubuntu@${TRADEBOT_VM_HOST}" \
      'sudo -n /usr/bin/python3 -IS - --phase mid' \
      < deploy/preprod/live_resource_observe.py

The script reads only the PP origin's writer row and up to 10,001 raw records
per active generation. A count below 10,001 is exact; 10,001 is a lower bound.
It reports relation/database bytes, PostgreSQL WAL segment allocation,
filesystem free bytes and available RAM. Every SQL sample uses a read-only
transaction with a three-second statement deadline. It never prints database
credentials, raw event payloads or prices. A failed sample is `INCOMPLETE`,
never a storage PASS.

Use the approved pinned PP operator SSH route to forward only the host's
loopback API. Set the variables to the existing verified host, key and
known-hosts file; never put their contents in a report.

    ssh -N -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
      -o ExitOnForwardFailure=yes -o ConnectTimeout=10 \
      -o "UserKnownHostsFile=$TRADEBOT_KNOWN_HOSTS" -i "$TRADEBOT_SSH_KEY" \
      -L "127.0.0.1:18000:127.0.0.1:8000" "ubuntu@$TRADEBOT_VM_HOST"

After the reviewed ON control confirms the PP lease, run this in another
local terminal:

    python3 deploy/preprod/live_observe.py \
      --base-url http://127.0.0.1:18000 --seconds 1500 \
      --output /private/tmp/tradebot-pp-live-observation.json

The default 25-minute observation leaves five minutes inside the maximum
30-minute ON lease for an explicit OFF and recovery. It samples /state/current
and /health every five seconds with two-second HTTP timeouts. At one-minute
intervals it checks the dashboard, prediction history, chart and first SSE
frame. It emits only IDs, ages, status and latency, not prices or credentials.
The API exposes the last Coinbase price's generation ID, which this tool
records. It does not expose an authoritative active writer generation, so a
separate bounded database/host check is required for rotation proof. The
output path is create-only. A failed or incomplete result must be reported
as such; do not relabel it PASS after OFF or a code rollback.

PASS requires at least 20 minutes with sufficient five-second coverage,
three feature and prediction IDs, advancing Coinbase events and Polymarket receipts,
a real 15-minute market boundary, working dashboard/history/SSE, no API errors
or two-second latencies, fresh feeds and at most 30-second input/feature ages
after the first minute. Missing boundary or insufficient samples is
INCOMPLETE. A stale feed, wrong mode, failed health or timeout is FAIL.

The operator must issue the reviewed OFF control and verify durable OFF after
the observation, even if this tool fails. Then use the reviewed leave control
to return to generated mode. This tool does not prove exact raw-row
acknowledgement, disk/WAL growth, a size-triggered A/B switch, Supabase
archive/readback, local retirement or 72-hour sustainability. Collect those
with their separate bounded host/database and lifecycle gates.
