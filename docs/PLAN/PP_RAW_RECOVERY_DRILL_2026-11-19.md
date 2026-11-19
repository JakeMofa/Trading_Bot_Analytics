# Verify a separate copy of one PP raw archive

PP keeps incoming event rows in local PostgreSQL `raw.events`, with one partition
per generation. Archival packages those rows as compressed JSON Lines in the
private Supabase `market-raw` bucket. The local PostgreSQL `archive.generations`
and `archive.manifests` tables carry the seal, object keys, counts, checksums, and
coverage. Supabase `history_v2` keeps synchronized structured records and receipt
metadata. A receipt or a manifest can identify the expected content. Recovering
the original raw events requires the corresponding compressed bytes.

The first indexed PP20 audit verified all 57 raw objects and 62 of 63 structured
pages. The same initial 500-row page took 2.729 seconds, below the four-second
operation limit. The full audit held at 239.608 seconds. The release owner
coordinates the successful full readback and any later retirement decision.
[Indexed replay evidence](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/178)

Storage readback and a separate backup answer different failure cases. Exact
readback checks that the current remote archive contains A before local removal.
A separate copy allows recovery after source-bucket loss or deletion. Supabase
database backups include Storage metadata and exclude Storage object contents.
This drill measures that second capability separately from the existing
retirement protocol.
[Supabase database backup coverage](https://supabase.com/docs/guides/platform/backups)

## Operator drill

1. Use the retained A generation ID, seal digest and row count from approved
   release evidence. Export just that generation's verified catalog with the
   existing PP database reader. Record the SHA-256 of the exact inventory bytes
   in a separate trusted location. Keep the known seal and count with it.
2. Through the release owner's existing PP Storage identity, fetch each exact
   object key listed in the trusted inventory. The archive writer and project
   administrator credentials provide unnecessary access for this read. Copy the
   inventory and compressed chunks to a separately controlled destination,
   retaining the object keys as relative paths. Record destination object
   versions or equivalent file identities and the copy time. Keep archive
   payloads, credentials and database copies outside Git.
3. Retrieve the inventory and chunks **from the backup** into a fresh private
   scratch directory. Run the offline verifier from that directory's object root
   with the independently recorded inventory SHA-256, exact origin and generation.
   Run this stage without access to the source bucket so success demonstrates
   recovery from the backup copy.
4. A full A pass requires **57 matching objects and 28,411 matching raw rows**,
   with the compressed and decoded hashes, ordered cursors and generation seal
   all checked. Keep a sanitized report with the copy and restore timestamps,
   destination version identifiers, totals and seal. A sample object is a
   connectivity check. Full scope is needed to claim full raw recovery.

The output establishes recoverability of the staged raw files. Structured
Postgres history requires its own recovery evidence, and the exact full-A
readback remains a release gate. The verifier is independent of retirement
permits and application startup.

## Destination and access

One possible destination is an existing approved private Amazon S3 bucket in the
AWS project's assigned Region, controlled separately from Supabase. Versioning
preserves prior object versions when an object is overwritten or a delete
marker is added. Use the bucket's scoped copy and read permissions and record
the version for each recovered object. Object storage, requests, transfer,
and retained versions can incur costs. Select the destination and confirm its
controls before moving real PP data. An encrypted independent local store can
also exercise the same verifier.
[Amazon S3 Versioning](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html)
· [Amazon S3 pricing](https://aws.amazon.com/s3/pricing/)

The release chat owns the PP connection and authenticates exact Storage GETs
through the existing dedicated identity. The local AWS CLI profile currently
requires reauthentication, so the first verification uses generated fixtures.

## Commands for the proposed drill

For the inventory, use the release owner's existing secret-injected libpq
connection as the direct `tradebot_reader` login on `tradebot_pp`. The
example assumes a private libpq service named `pp_inventory_reader`. Set
`generation_id`, `expected_count` and `expected_seal` from release evidence
and `scratch` to an existing private absolute directory outside the checkout.
Keep the credentials in the existing scoped configuration.

```sh
umask 077
pending="$(mktemp "$scratch/inventory.XXXXXXXX")"
if PGSERVICE=pp_inventory_reader psql -X -w -qAt \
    -v expected_origin=pp-live-pp -v generation_id="$generation_id" \
    -v expected_seal_count="$expected_count" -v expected_seal_hash="$expected_seal" \
    -f deploy/preprod/export_raw_restore_inventory.sql > "$pending"
then
    shasum -a 256 "$pending"
else
    rm -f "$pending"
    exit 1
fi
```

Store that digest separately from the staged bytes. After retrieving from the
independent copy, set `restore_root` to the resolved absolute directory with
the copied inventory and its `raw-v1/...` files. Use a real filesystem path
that does not traverse a symlink, such as the resolved macOS temporary
directory. The verifier checks all files and emits a compact summary.

```sh
PYTHONPATH=backend python -m postgres.raw_backup_verify \
    --inventory "$restore_root/inventory.json" \
    --expected-inventory-sha256 "$trusted_inventory_sha256" \
    --backup-root "$restore_root" --origin-id pp-live-pp \
    --generation-id "$generation_id"
```

The archive timing report operates on sanitized evidence offline. Use its phase
rankings to decide where to measure next. A timing delta is descriptive when the
audits hold, and nested timing spans cannot be added together.

```sh
PYTHONPATH=backend python -m postgres.retirement_telemetry pp19-evidence.json \
    --candidate pp20-evidence.json
```

## Qualification evidence

An isolated PostgreSQL 17 fixture exported a generation through the reader login,
then a separate file copy populated a fresh restore directory while the primary
directory was unavailable. The verifier recovered all 57 objects and 28,411
generated rows, compared the inventory against the known seal, and rejected
a second run with the final object missing. These counts mirror A's shape.
The generated bytes are not PP observations.

The timing report was also run on the recorded PP19 and indexed PP20 evidence.
It preserves the PP20 hold and the explicit 62 of 63 completed structured pages,
distinguishes 63 attempts from 62 completions, and omits a whole-run improvement
percentage for the incomplete runs. This tooling operates on prior evidence.
Hosting a metrics endpoint or wiring a Grafana dashboard remains a separate step.
