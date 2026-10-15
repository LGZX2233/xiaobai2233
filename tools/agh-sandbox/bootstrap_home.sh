#!/bin/bash
# Build a fresh, self-contained AGH home for one recorded run: profile with the capability ceiling,
# the Project Kernel plugin (add -> trust -> enable) and ONE model provider account.
# Everything must happen inside this single call because the daemon dies with the call's shell.
#
#   bootstrap_home.sh <AGH_HOME> <provider: deepseek|agnes-ai> <model id> <key file> [kernel_next dir]
# Needs: node 24 (AGH_NODE), the packaged AGH (AGH_JS), python3, and tools/agh-sandbox/*.py next to this file.
# The API key is only ever read from <key file> by configure_provider.py and never printed.
set -e
HOME_DIR=${1:?AGH_HOME}; PROVIDER=${2:?provider}; MODEL=${3:?model}; KEYFILE=${4:?key file}
KN=${5:-/tmp/kn_agh/kernel_next}
HERE=$(cd "$(dirname "$0")" && pwd)
export AGH_NODE=${AGH_NODE:-/tmp/node-v24.22.0-linux-x64/bin/node}
export AGH_JS=${AGH_JS:-/tmp/aghrt/agnes.mjs}
export PATH=$(dirname "$AGH_NODE"):$PATH TMPDIR=/tmp
export AGH_HOME=$HOME_DIR AGNES_PROFILE=local-dev
mkdir -p "$HOME_DIR/profiles/local-dev"
[ -f "$HOME_DIR/profiles/local-dev/profile.yaml" ] || cp "$HERE/profile.local-dev.yaml" "$HOME_DIR/profiles/local-dev/profile.yaml"
cd "$KN"
# 1. the web server first: it fixes the daemon's web origin (a daemon started by a package command
#    would pick another origin and `serve` would then refuse to start).
node "$AGH_JS" serve --port 5186 --profile local-dev --cwd "$KN" --data-dir "$HOME_DIR/data" > "$HOME_DIR/serve-bootstrap.log" 2>&1 &
SERVE=$!
for i in $(seq 1 30); do curl -s -o /dev/null -m 2 http://127.0.0.1:5186/ && break; sleep 1; done
# 2. plugin
python3 "$HERE/install_plugin.py" --cwd "$KN" --home "$HOME_DIR" | tail -4
# 3. provider account (key from file, masked output)
python3 "$HERE/configure_provider.py" --provider "$PROVIDER" --model "$MODEL" --key-file "$KEYFILE" \
  --account-name "$PROVIDER" --cwd "$KN" --home "$HOME_DIR" --transcript "$HOME_DIR/provider-wizard.txt" | tail -6
kill $SERVE 2>/dev/null || true; sleep 1; kill -9 $SERVE 2>/dev/null || true
echo "bootstrap done: $HOME_DIR ($PROVIDER / $MODEL)"
