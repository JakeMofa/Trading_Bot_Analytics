#!/bin/sh
set -eu
test "$(id -u)" -eq 0
cd /opt/tradebot
test -f .env
test -f data/btc_intelligence.db
for name in api lifecycle ensemble soak; do
    install -m 644 "deploy/lightsail/tradebot-$name.service" /etc/systemd/system/
done
install -m 644 deploy/lightsail/tradebot-soak.timer /etc/systemd/system/
install -d /etc/systemd/journald.conf.d
printf '[Journal]\nSystemMaxUse=100M\nRuntimeMaxUse=50M\n' > /etc/systemd/journald.conf.d/tradebot.conf
systemd-analyze verify /etc/systemd/system/tradebot-api.service /etc/systemd/system/tradebot-lifecycle.service /etc/systemd/system/tradebot-ensemble.service /etc/systemd/system/tradebot-soak.service /etc/systemd/system/tradebot-soak.timer
systemctl restart systemd-journald
systemctl daemon-reload
systemctl enable tradebot-api tradebot-lifecycle tradebot-ensemble
systemctl enable tradebot-soak.timer
# Start separately so readiness can be checked before enabling cloud writes.
printf 'Units installed and enabled; start API, lifecycle, then ensemble after database verification.\n'
