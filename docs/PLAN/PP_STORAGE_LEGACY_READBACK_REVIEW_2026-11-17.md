# PP Storage authenticated-readback operation amendment

Status: **bounded synthetic authenticated readback PASS; full archival OPEN**.
The authoritative roadmap remains `docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md`.

## Observed checkpoint

The first policy migration ledger entry is `20261118031950`
(`pp_market_raw_storage_auth_20261118`), with rendered SQL SHA-256
`560e472b8997092961beaaca93c0a2fcb1af36bca853c59c24e8a651f19f3ac5`.
The dedicated PP Auth UID is `600b06fc-f121-4a96-a21c-6278b0f38be6`.
The private `market-raw` bucket has the two reviewed policies and no mutation
grant. No credentials, token values or request headers belong in this report.

The first bounded live probe's create-only POST returned HTTP 200. Its
authenticated GET returned HTTP 400 `NoSuchKey`, so readback **failed at that
initial checkpoint**. Read-only
Storage logs recorded upload operation `storage.object.upload` and GET operation
`object.get_authenticated_info`. The current readback policy permits only
`storage.object.get_authenticated`. The exact object row, UID, bucket and PP
prefix were present. The operation mismatch was the supported explanation for
that failed read; the later successful result is recorded below.

One synthetic object remains retained:

`raw-v1/6157f7800b12255ab48111b5c6258a444712a38baca54d3b0929ede8994b2ae8/500b0871-6f59-46de-a17c-537f6b0aee5d/5589f047e23adedca048ccadb7351f5d6eefb82b55314fdb3676d4a01096b7bf.jsonl.gz`

The two deterministic synthetic records reconstruct locally to **126 bytes**
and SHA-256 `5589f047e23adedca048ccadb7351f5d6eefb82b55314fdb3676d4a01096b7bf`.
That local reconstruction alone did not verify the remote bytes. PP retirement
stays OFF. No structured history claim follows from this synthetic probe.
The first exact CI on this successor failed one backend test: Python/zlib
produced different gzip bytes for the same two records on Linux. The reviewed
126-byte synthetic blob is now pinned in code and independently checked by
gzip decode, record values and SHA-256 before network. This preserves the
original object across runtimes; the prior CI failure remains a failure.

## Narrow amendment

The reviewed `readback-patch` renderer produces one SQL transaction that
changes only the `tradebot_pp_raw_readback` `USING` expression to
`storage.allow_any_operation(ARRAY['storage.object.get_authenticated',
'object.get_authenticated_info'])`. Both operation names appear in
[Supabase's Storage access-control guide](https://supabase.com/docs/guides/storage/security/access-control)
and [Storage operation definitions](https://github.com/supabase/storage/blob/master/src/http/routes/operations.ts).
The upload policy, bucket, Auth user, object rows and local retention remain
untouched. Listing, update, delete, public and other-UID access remain denied
in the generated policy fixture.

The transaction refuses a changed project/bucket input, Auth UID/email/role or
PP markers, unconfirmed email, nonprivate bucket, disabled RLS, missing helper,
unexpected policy count/names/roles/commands, or changed **SHA-256 of the
current two catalog policy rows**. The operator must inspect the live catalog
and record that digest before rendering; it is not hard-coded from a fixture.
The digest query is:

```sql
SELECT encode(sha256(convert_to(
  jsonb_agg(to_jsonb(p) ORDER BY p.policyname)::text,'UTF8')),'hex')
FROM pg_policies p
WHERE p.schemaname='storage' AND p.tablename='objects';
```

The operator must independently verify that the connected Supabase project is
`xttdqeimdujweijxcuro`. The local renderer cannot attest connector selection.
This was the review procedure used for the applied amendment. Any future
policy change needs a new reviewed catalog hash and migration; the prior hash
cannot be reused.

## Reconcile-only probe

After the reviewed amendment, run the probe as a module from the repository
root: `python -m deploy.preprod.probe_market_raw_storage`. The direct script
path is not the supported invocation. Supply `--live`, exact project URL and
bucket, private publishable-key and dedicated bearer file paths, reviewed
UID/email, plus `--reconcile-key` with the exact retained key above,
`--expected-bytes 126` and `--expected-sha256` with the object hash above.
The module CLI is smoke-tested. The runtime validates the exact PP prefix,
generation, digest and reconstructed body **before network access**, checks
`/auth/v1/user`, performs authenticated GET and a bearer-free public-denial
GET. It makes **zero POST requests**, does not delete the object and retains
the original 30-second default and five-attempt absolute cap. A mismatch,
timeout or inconclusive denial is a failure, with no automatic retry.

The generated PostgreSQL fixture proves both authenticated operation names
can select only the exact PP object while list, wrong UID, update and delete
remain denied. Its SQL approximation does not by itself prove live Storage
HTTP behavior.

## Applied amendment and bounded live outcome — November 18 UTC

[PR #108](https://github.com/JakeMofa/Trading_Bot_Analytics/pull/108) merged to
`preprod` as `83f6a41` after exact [push CI 44232805427](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44232805427)
and [PR CI 44232810997](https://github.com/JakeMofa/Trading_Bot_Analytics/actions/runs/44232810997)
passed. The catalog-bound rendered patch had SHA-256
`2527e7642139bb8a04d50a50baf34b1cc5a4cfd261596e380330ddd5283b1d22`.
It was applied as migration `pp_market_raw_legacy_readback_20261118`, ledger
`20261118035125`. Post-checks retained the private bucket and exactly two
policies bound to the dedicated UID: upload and authenticated readback, with
zero update/delete grants. The upload policy and existing object rows were
preserved.

The reviewed reconcile-only probe used **three HTTP attempts and zero POST**.
Authenticated readback matched all **126 bytes**, object SHA-256
`5589f047e23adedca048ccadb7351f5d6eefb82b55314fdb3676d4a01096b7bf`,
both synthetic records and their generation identity. Public retrieval was
denied. The object remains retained. Read-only Storage logs showed legacy
`object.get_authenticated_info` returning HTTP 200 followed by
`storage.object.get_authenticated` returning HTTP 200; anonymous legacy info
returned HTTP 400. The ephemeral bearer used for the attempt was removed.
No credential, request header or secret path is included in this report.

**Gate disposition:** The bounded synthetic private-Storage upload and exact
authenticated readback gate is PASS. This is one 126-byte object, not a full
sealed generation or sustained Supabase-throughput test. Structured
`history_v2` write/readback, full archive coverage, privileged mutation
protection, local retirement, PP runtime lifecycle integration and production
remain OPEN. Local retirement is OFF; no production change follows from this
probe.
