# CP6 PP Storage Auth delivery — review, not executed

The PP raw archive one-shot host control merged in PR #119. Its read-only
preflight currently stops: `/etc/tradebot/cloud` contains the separate
`history_v2` DSN and CA, but lacks the four dedicated Storage Auth files. The
operator-only installer in this PR provides the missing delivery step. It has
no cloud client, service restart, runtime schedule, retirement or production
path. No PP credential or cloud state was changed by this review.

## Required bindings before transfer

1. Confirm the existing private operator stage from
   `provision_supabase_archive_identity.py` has status
   `CREATED_VERIFIED_RESPONSE` and the three files
   `supabase_auth_email`, `supabase_auth_password`, `supabase_auth_uid`.
   Independently reconcile that UID to the approved `pp-live-pp` Auth user and
   both exact private `market-raw` policies. A missing or uncertain password
   requires a separately reviewed Auth rotation, not a guessed replacement.
2. Prepare a **publishable** Supabase API key in a separate private file. A
   service-role/admin key is forbidden. Keep the key
   file and operator stage outside Git, CI artifacts, shell tracing and shared
   temporary directories. The three Auth input files and status are mode
   `0400` in a `0700` stage. The existing separate publishable-key source is
   mode `0600`; its remote stage copy is renamed `pp_storage_api_key` and
   tightened to `0400` before installation. The publishable-key file may
   contain the exact token without a trailing newline; the Auth files and
   status still require the provisioner's single trailing newline.
3. Verify the current PP IP and pinned SSH host key through the existing
   approved operator route. The target must be `tradebot-preprod-01`, not
   production. Confirm the root host marker, `/etc/tradebot/cloud` mode `0700`,
   current `history_v2` files, and no existing destination Storage Auth file.
   A partial earlier install is a STOP requiring manual reconciliation.

## Bounded installation sequence

The operator copies the four runtime files plus the nonsecret creation status
over the already pinned `ubuntu`
SSH route into `/home/ubuntu/.tradebot-pp-storage-stage`, owned by `ubuntu`
and mode `0700`. Use `scp -p` with `BatchMode`, `IdentitiesOnly`,
`StrictHostKeyChecking` and the verified `UserKnownHostsFile`. Do not include
credential values in arguments, command text or logs. Create the stage with
`umask 077`; check it contains exactly five regular, distinct, single-link
mode-`0400` files after transfer. A failed or ambiguous transfer stops here.

Transfer `deploy/preprod/install_storage_auth.py` separately as public code,
verify its exact CI-reviewed SHA-256 on PP, then copy it to a root-owned path
under `/usr/local/lib/tradebot-pp` with `sudo install -o root -g root -m 0644`.
Execute that **root-owned reviewed code** with `sudo -n /usr/bin/python3 -I`
and only `--expected-uid <independently verified PP Auth UUID> --execute`.

The reviewed operator runs the following shape from the exact CI-passed
checkout. Replace only the paths, verified PP address and canonical UUID;
keep all values out of shell tracing. The same pinned key/known-hosts options
must be used for both `ssh` and `scp`:

```sh
set +x
ssh -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
  -o "UserKnownHostsFile=$TRADEBOT_KNOWN_HOSTS" -i "$TRADEBOT_OPERATOR_KEY" \
  "ubuntu@$TRADEBOT_PP_HOST" \
  'umask 077; test ! -e /home/ubuntu/.tradebot-pp-storage-stage && mkdir -m 0700 /home/ubuntu/.tradebot-pp-storage-stage'
scp -p -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
  -o "UserKnownHostsFile=$TRADEBOT_KNOWN_HOSTS" -i "$TRADEBOT_OPERATOR_KEY" \
  "$TRADEBOT_AUTH_STAGE/supabase_auth_email" \
  "$TRADEBOT_AUTH_STAGE/supabase_auth_password" \
  "$TRADEBOT_AUTH_STAGE/supabase_auth_uid" \
  "$TRADEBOT_AUTH_STAGE/status" \
  "ubuntu@$TRADEBOT_PP_HOST:/home/ubuntu/.tradebot-pp-storage-stage/"
scp -p -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
  -o "UserKnownHostsFile=$TRADEBOT_KNOWN_HOSTS" -i "$TRADEBOT_OPERATOR_KEY" \
  "$TRADEBOT_PUBLISHABLE_KEY_FILE" \
  "ubuntu@$TRADEBOT_PP_HOST:/home/ubuntu/.tradebot-pp-storage-stage/pp_storage_api_key"
ssh -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
  -o "UserKnownHostsFile=$TRADEBOT_KNOWN_HOSTS" -i "$TRADEBOT_OPERATOR_KEY" \
  "ubuntu@$TRADEBOT_PP_HOST" \
  'chmod 0400 /home/ubuntu/.tradebot-pp-storage-stage/pp_storage_api_key'
```

Check transfer exit status and remote stage metadata before
installing. Transfer the public installer source to a separate temporary
path, verify its hash equals the **exact reviewed CI source**, then use the
pinned route to run:

```sh
sudo -n install -o root -g root -m 0644 \
  /home/ubuntu/pp-storage-auth-installer.py \
  /usr/local/lib/tradebot-pp/install_storage_auth.py
sudo -n sha256sum /usr/local/lib/tradebot-pp/install_storage_auth.py
sudo -n /usr/bin/python3 -I \
  /usr/local/lib/tradebot-pp/install_storage_auth.py \
  --expected-uid <CANONICAL_PP_AUTH_UUID> --execute
sudo -n /usr/bin/python3 -I \
  /usr/local/lib/tradebot-pp/controller.pyz \
  'raw-archive-probe-v1 preflight'
```

Those `sudo` commands run **on PP through the same pinned operator SSH
route**. Compare the displayed installer hash with the reviewed hash before
the install command. The preflight is read-only and does not create an
archive permit. Do not execute any `execute` command in this sequence.

The installer checks the PP host marker and the root controller lock, parses
every private input before writing, rejects symlinks, hard links, changed
files, unexpected names, wrong modes, malformed values and UID mismatch. It
creates each destination with `O_EXCL`, verifies exact bytes in-process and
fsyncs files and the cloud directory. Existing history DSN/CA identities must
remain unchanged. It removes the remote stage only after success, reports
file count and OFF flags without values or secret digests, and never retries.
File creation is individually exclusive; a process crash can leave a partial
set. That state fails the next preflight and **must be reconciled manually**.

After installation, run the installed raw archive controller's **read-only**
`raw-archive-probe-v1 preflight` with the exact source/image/controller binding.
This may still STOP if the controller has not been updated, the PP live profile
is not `ready_off`, or no sealed `pp-live-pp` generation exists. Do not create
a one-use archive permit or cloud call as part of credential installation.

The later live archive attempt is a separate decision: first qualify the
size-trigger A→B switch, then bind one permit to sealed A and its exact counts,
run bounded raw upload plus authenticated readback while B collects, and keep
local retirement OFF. `history_v2` structured rows and private Storage raw
objects have separate credentials and verification; one passing path does not
certify the other.

## Test scope and open limits

The generated installer tests exercise success, wrong UID, unsafe files,
symlinks, existing partial state and interrupted writes. They do not establish
that the original operator-held Auth password remains available or that the
installed controller is already current. No live credential transfer, cloud
write or PP retirement is included in this PR.
