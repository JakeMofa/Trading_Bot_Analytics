#!/bin/sh
# Exercise the running workstation fixture with local file-held lab identities.
set -eu
lab_dir=${TRADEBOT_ARCHIVE_LAB_DIR:-"$HOME/.local/share/tradebot-archive-lab"}
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$lab_dir/venv/bin/python" "$script_dir/probe.py" "$lab_dir/local-status.json" \
    --fixture-state "$lab_dir/archive-fixture.json" "$@"
