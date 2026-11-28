# Sustained Benchmark collection

The watch binds one collector to the 4 GB Benchmark instance, a specific
accepted release and the stable origin `pp-live-pp-benchmark-watch`. The
collector maintains one PostgreSQL session identity across lease renewals and
market rollovers. The separate structured worker writes and verifies history
in Supabase. Raw events remain in the local generation.

## Starting and stopping

Complete generated Benchmark CD first. Prepare the origin in the live profile
and check retained fingerprints. Provision the reviewed structured writer and
read-only role, run their isolated synthetic write and independent readback,
and stage their DSNs and verified CA on Benchmark. Install the market
read credentials as UID 10001 mode 0400 under the protected runtime directory.
Start the scoped recurring worker and verify its release identity. Install the
service and timer from the exact release under /etc/systemd/system. After a
fresh production-OFF readback, the Benchmark root operator runs:

```sh
sudo python3 -I -c "import sys; sys.path.insert(0,'/usr/local/lib/tradebot-pp/controller.pyz'); from watch_service import main; main()" arm --source "$source_sha" --anchor "$initial_a"
sudo systemctl daemon-reload
sudo systemctl enable --now tradebot-pp-benchmark-watch.timer
sudo systemctl start tradebot-pp-benchmark-watch.service
```

The operator can explicitly stop the watch with the same module's `off`
command or the authenticated collector OFF endpoint. OFF persists through
reboot. Source controls can pause the Coinbase readers, Robinhood, or
Polymarket independently. Check requested state, actual running or held state
and last source receipt separately.

Every 15 seconds the service verifies its release and archive worker. The API
renews the existing 120-second database lease only while that same process owns
it. PostgreSQL disk reserve, pending structured limit and the active
generation's integrity hold are checked. After a process restart the host can
admit a new fenced writer under the existing intent. A failed guard holds
automatic admission. Inspect the service journal and private control status;
resolve the cause and prove OFF before explicitly arming again.

## Rotation and updates

The ordinary 72-hour generation age applies. Automatic raw verification and
retirement are disabled. The first eligible A can seal and a new B can
collect. A still occupied on the next swap holds the writer. The Benchmark
still needs a same-host multi-window rotation and scalable full readback proof
before this can operate through successive 72-hour retirements. Check disk
headroom and the backlog throughout long runs.

Full CD and profile transitions reject an armed watch before fencing a writer.
Dashboard-only release and collector handoff need separately qualified update
paths. An operator must explicitly stop the collector before today's full CD.

### Dashboard-only replacement while collecting

Publish the candidate through the existing release workflow. Download its
manifest, checksums and source package, and verify the exact successful CI
commit, source branch, package digest and release identity. Install
`api_component_update.py` from that same reviewed source on the pinned
Benchmark host as root-owned mode 0500 at
`/usr/local/lib/tradebot-pp/benchmark-api-update.py`. Its imports come from
the installed collector controller. The privileged operator runs:

```sh
sudo python3 -I /usr/local/lib/tradebot-pp/benchmark-api-update.py build --source "$source_sha" --artifact "$artifact_sha256" < "$release_tar_gz"
sudo python3 -I /usr/local/lib/tradebot-pp/benchmark-api-update.py apply --artifact "$artifact_sha256"
```

Build verifies the archive digest, Git identity, every migration, Dockerfile and
requirements against the running release. Apply checks the active lease and
migration ledger, then recreates the API with the running Compose configuration.
An interrupted replacement has a host-owned rollback watchdog. A successful
receipt records API container identities, protected service PIDs and start times,
writer session and epoch, and outbox progress. Individual browsers reconnect
to the existing event stream. A source-code or database-schema change that
requires a new collector still follows its own release qualification.

## Local database budget for the public dashboard

| Local PostgreSQL login | Maximum simultaneous sessions in the successor |
| --- | --- |
| `tradebot_app`, limit 8 | Operator process shares six slots across all producer sessions and private control writes. Four long-lived feed writers can occupy four of these. The calculation process shares two slots between discovery and calculation. |
| `tradebot_reader`, limit 4 | One Uvicorn API worker uses two for all public history, chart and background reads. The private operator serializes ownership, status and preferences reads in one. Read-only host diagnostics share the fourth. |
| `tradebot_lifecycle`, limit 3 | The existing lifecycle, lease and archive workers retain their existing role and admission rules. |
| `tradebot_migrator`, limit 2 | Migrations run with the watch disarmed. |

The server allows 20 connections, including three reserved PostgreSQL slots.
When the watch is armed the documented service role maxima total 15. Tickets
span actual connection establishment and use through physical close, including
the time a background thread continues after its HTTP caller disconnects.
Excess market and prediction pages receive HTTP 429. In-memory quote state and
SSE remain available. Under prolonged load the dashboard can report unknown
collector/DB status between successful refreshes.

The Benchmark API-only release helper executes every PostgreSQL diagnostic as
the reader. In-container `flock -n -E 75 -F /var/run/postgresql/.tradebot-watch-diagnostic.lock`
serializes diagnostic processes **before** they connect and remains held by
the actual psql process. Use the normal API-backed Grafana sender for ongoing
samples. Operator probes requiring fresh PostgreSQL SQL must use the same lock
and reader on the pinned container; retire historic ad-hoc direct-DSN probes
before profile adoption. A busy diagnostic retries later. Lease renewal uses
its independent private connection path.

### Adoption on the existing generation

The published .7 controller pins the previous mount and runtime. Its healthy
collector and .9 UI cannot adopt this change with an image-only update. A
qualified collector-preserving handoff is pending. The following full-profile
procedure requires an explicit maintenance window while that work is pending.

1. Pass PR and exact merged push CI; publish the complete release, verify
   manifest and package digest and stage the verified controller and release
   before the maintenance interval. Record the old release/controller and
   dashboard component receipt for rollback. Prepare the reader projection on
   the pinned 4 GB Benchmark host from the exact source as root:
   `python3 deploy/preprod/provision_runtime.py prepare-watch-reader`. The
   existing reader password and grants remain valid.
2. Snapshot the 20 retained fingerprints, current generation, writer epoch,
   most recent ACK and active outbox watermark. Record the last source receipts
   and the current dashboard image. Under the accepted existing controller
   run the `off` action and prove durable OFF. Stop the recurring archive
   worker only after independent readback/ACK reaches the recorded final
   watermark. Preserve every raw partition and outbox row.
3. Leave the old live profile using its bound transition. Install the exact
   successor controller and run generated Benchmark CD on the same PostgreSQL
   volume. This can recreate API, operator, calculation and lifecycle
   containers. Collection, new calculations and archive processing pause
   during this cutover. The release cannot guarantee a fixed outage; record
   UTC from the old writer's last receipt to the new writer's first receipt.
4. Enter the successor live profile with the **same** initial A
   `8b7c3058-c10c-4900-89c9-2d7569fca67d` and stable watch origin. Confirm
   READY_OFF, all retained fingerprints, old market ranges, the current
   generation and its checkpoint. Rebind the existing approved scoped
   archive writer and independent reader, verify the recurring worker and
   independent production-OFF receipt, then use the arm commands above. A
   fresh fenced writer UUID is expected after this explicit stop.
5. Confirm effective states and fresh quote identities for all three feeds,
   compare them to verified hosted bytes and receipts, and measure a 500-row
   History HTTP request during actual collection. Record writer UUID, epoch
   and ACK counts before/after. Repeat API-only exchange on a future compatible
   API release. Preserve the retention hold on raw generations.
6. If qualification or admission fails, keep the database and all partitions,
   disarm the candidate, and use the same reviewed full release procedure for
   the last accepted controller and .7 rollback release. Restore its verified
   .9 API-only component separately. Confirm OFF, the existing generation,
   retained fingerprints and archive worker before re-arming. Publish the
   actual gap and component identities. An unverified runtime stays OFF.

Offline reproduction from the repository root:

The heartbeat treats only an HTTP 503 from its authenticated
`GET /collector/status` as a temporarily unavailable observation. It leaves
the original database lease deadline unchanged and retries the entire proof
on the next timer tick. No status snapshot is cached. A successful recovery
still requires the exact release binding, fresh status, qualified archive
worker and server-side renewal of the currently owned writer UUID. Expired
or transferred leases cannot be re-enabled by this retry. Status 401/403/409,
renewal errors (including 409/503), release/worker drift and explicit OFF keep
their existing terminal or disarm behavior. Persistent unavailability can
still expire the lease; this is not an indefinite-uptime guarantee.

```sh
PYTHONPATH=deploy/preprod python -m unittest discover -s deploy/preprod/tests -p test_watch_service.py
PYTHONPATH=backend:backend/tests python -m unittest discover -s backend/tests -p test_postgres_watch_dashboard_reader.py
PYTHONPATH=deploy/preprod python -m unittest discover -s deploy/preprod/tests -p test_trial_cloud_control.py
PYTHONPATH=deploy/preprod python -m unittest discover -s deploy/preprod/tests -p test_api_component_update.py
```
