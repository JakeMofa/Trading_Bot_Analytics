# PP controller transfer: code only

This is a one-release operator procedure. The authoritative phase state is in
[`INTELLIGENCE_REBUILD_PLAN.md`](../../docs/PLAN/INTELLIGENCE_REBUILD_PLAN.md).
It does not authorize a deployment, cloud call, collector, or retirement.

## Exact reviewed binding

- Source: `701a68b433ed888c56ec48cc0555d0ff9e2e609e` (preprod merge of PR #119,
  including the earlier structured controller from PR #118).
- Expected previous installed controller: `bdb11511039365990249846d1e5a521228255530db000a25181ad260f7aebee7`.
- New deterministic bundle: `c3fac37cb56945ad74d41188b8e22013a199fe8d656b87be4f4154676d3c9479`.
- Input: the ten-member zipapp and four exact tracked installer dependencies.
- Output: installed controller code, with the previous code retained by
  `install_controller.py`. No database, configuration, secret or credential
  content is copied. The existing forced-command deploy **public** key is
  read from its root-owned host file; its private key never enters staging.

**Hold this transfer if a newer controller source is selected.** Revise the
exact source and hashes, qualify a successor helper, and install only once.

## Before an operator runs it

1. Require exact source CI and the transfer helper's exact CI. Confirm the
   intended PP controller candidate has not changed, and record the host's
   current controller hash, `generated_restored` state and absence of unused
   one-use authorities. Confirm collector OFF and no active PP lease.
2. Use the existing pinned SSH identity and known-hosts file. Do not weaken
   host verification or copy database/configuration files.
3. Build the deterministic bundle from the exact reviewed source. Verify its
   hash above. A source change requires a newly reviewed transfer binding.

From the reviewed checkout, the operator command is:

```sh
python3 deploy/preprod/controller_bundle.py /absolute/private/controller-701a68b.pyz
python3 deploy/preprod/transfer_controller.py --send \
  --bundle /absolute/private/controller-701a68b.pyz \
  --repo /absolute/path/to/Trading_bot_Analytics \
  --identity /absolute/path/to/existing/operator-private-key \
  --known-hosts /absolute/path/to/existing/pinned-known-hosts
```

The tool reads the four installer dependencies from the reviewed checkout,
validates their pinned source digests and byte bounds, then sends them with the bundle
over strict pinned SSH. The root receiver verifies all bytes before staging,
uses exclusive no-follow files in root-only `/run`, checks the prior controller
and existing forced-command public key, and invokes the existing installer with
a 90-second child deadline. A 120-second SSH deadline bounds the transfer.
Staging is removed after the attempt. Existing code is preserved under its
digest; the helper never restores database contents.

## Required result and next gate

Require `CONTROLLER_INSTALLED_NOT_AUTHORIZED`, the exact new hash, the old code
still present by digest, no authority created, and unchanged PP database and
services. Any error is **STOP**. An ambiguous SSH result is not a reason to
retry: inspect the installed hash, retained code, journal and authority first.

Then use the existing manual PP controller identity workflow to qualify the
installed hash. Update the preprod target profile through a small reviewed PR
with that actual host evidence and exact CI. A separate one-use authorization
is still required before any application release or structured cloud probe.
