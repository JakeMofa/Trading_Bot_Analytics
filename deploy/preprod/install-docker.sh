#!/bin/bash
set -Eeuo pipefail
# Called only after foundation.py's PP identity/resource preflight.
# Do not remove conflicting packages or overwrite an existing Docker setup.
if command -v docker >/dev/null; then
  docker version >/dev/null
  docker compose version >/dev/null
  exit 0
fi
for package in docker.io docker-compose docker-compose-v2 podman-docker containerd runc; do
  if dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed'; then
    echo 'Conflicting package requires explicit review' >&2
    exit 1
  fi
done
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=l
apt-get -o DPkg::Lock::Timeout=30 update
apt-get -o DPkg::Lock::Timeout=30 install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
key=$(mktemp)
trap 'rm -f "$key"' EXIT
curl --fail --silent --show-error --max-time 30 https://download.docker.com/linux/ubuntu/gpg -o "$key"
fingerprint=$(gpg --show-keys --with-colons "$key" | awk -F: '$1=="fpr" {print $10; exit}')
[ "$fingerprint" = '9DC858229FC7DD38854AE2D88D81803C0EBFCD88' ]
if [ -e /etc/apt/keyrings/docker.asc ]; then
  cmp "$key" /etc/apt/keyrings/docker.asc
else
  install -m 0644 "$key" /etc/apt/keyrings/docker.asc
fi
source_file=$(mktemp)
trap 'rm -f "$key" "$source_file"' EXIT
cat > "$source_file" <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
if [ -e /etc/apt/sources.list.d/docker.sources ]; then
  cmp "$source_file" /etc/apt/sources.list.d/docker.sources
else
  install -m 0644 "$source_file" /etc/apt/sources.list.d/docker.sources
fi
apt-get -o DPkg::Lock::Timeout=30 update
apt-get -o DPkg::Lock::Timeout=30 install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl is-active --quiet docker
# No docker-group membership is granted; administration continues through sudo.
