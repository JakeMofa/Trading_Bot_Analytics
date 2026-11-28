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

The successor watch profile pins Uvicorn to one worker and uses the existing PostgreSQL `tradebot_reader`
login for the single Uvicorn API process. All local reads share two admission
slots. Excess market and prediction page requests receive HTTP 429. Live state
and SSE can still publish from memory. Two of the reader role's four sessions
remain available for other read-only consumers. Collection, calculation and
the private source controls keep their original application role.

On the pinned Benchmark host, qualify the exact candidate release and run
`python3 deploy/preprod/provision_runtime.py prepare-watch-reader` from its
verified source as root. This prepares the read-only mount from the existing
foundation secret. The public API process verifies both its authenticated login
and read-only transaction mode. No database role, grant or password changes
are needed.

The installed .7 controller pins the old API mount. A normal API image-only
update cannot introduce this new profile. Keep the live collector active until
a reviewed controller/profile handoff proves continuity or the operator
authorizes a maintenance window. After adoption, run history under concurrent
hydration and verify login, writer session, ACK progress and response latency.
