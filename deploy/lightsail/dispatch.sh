#!/usr/bin/env bash
set -euo pipefail
umask 077
[[ "$GITHUB_EVENT_NAME" == workflow_dispatch ]]
[[ "$GITHUB_REF" == refs/heads/codex/lightsail-deployment ]]
[[ "$APPROVED_REVISION" =~ ^[0-9a-f]{40}$ ]]
[[ "$GITHUB_SHA" == "$APPROVED_REVISION" ]]
[[ "$DEPLOY_HOST" =~ ^[a-zA-Z0-9.-]+$ ]]
[[ "$DEPLOY_USER" =~ ^[a-zA-Z0-9_-]+$ ]]
: "${DEPLOY_KEY:?missing SSH secret}" "${DEPLOY_KNOWN_HOSTS:?missing host pin}"
cd_work_dir=$(mktemp -d)
trap 'rm -rf "$cd_work_dir"' EXIT
printf '%s\n' "$DEPLOY_KEY" > "$cd_work_dir/key"
printf '%s\n' "$DEPLOY_KNOWN_HOSTS" > "$cd_work_dir/known_hosts"
unset DEPLOY_KEY DEPLOY_KNOWN_HOSTS
# Export exactly one branch ref; never send untracked files, .env, data or credentials.
git update-ref refs/heads/codex/lightsail-deployment "$APPROVED_REVISION"
git bundle create "$cd_work_dir/source.bundle" refs/heads/codex/lightsail-deployment
ssh -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \
  -o ConnectTimeout=15 -o ServerAliveInterval=15 -o ServerAliveCountMax=4 \
  -o UserKnownHostsFile="$cd_work_dir/known_hosts" -i "$cd_work_dir/key" \
  "$DEPLOY_USER@$DEPLOY_HOST" "deploy $APPROVED_REVISION" < "$cd_work_dir/source.bundle"
