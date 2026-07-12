#!/usr/bin/env bash
# Run bb v1 live, forever, once per hour (1h candles).
#
# Setup (one time):
#   1) Create the virtualenv and install deps:
#        python3 -m venv ~/trader-venv
#        ~/trader-venv/bin/pip install -r requirements.txt
#   2) Put your secrets in ~/.bbv1.env (this file is NOT committed):
#        BINGX_API_KEY=your_key
#        BINGX_API_SECRET=your_secret
#        BINGX_EXECUTION_MODE=live
#   3) Run it (survives disconnects under tmux, or use the systemd unit below):
#        tmux new -s bbv1 'bash scripts/run_bbv1_live.sh'
#
# Override the venv or interval if needed:
#   VENV=~/other-venv INTERVAL=1800 bash scripts/run_bbv1_live.sh

set -u

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${VENV:-$HOME/trader-venv}"
INTERVAL="${INTERVAL:-3600}"
ENV_FILE="${ENV_FILE:-$HOME/.bbv1.env}"
PY="$VENV/bin/python"

cd "$REPO_DIR" || exit 1

if [ -f "$ENV_FILE" ]; then
  set -a; . "$ENV_FILE"; set +a
fi

if [ ! -x "$PY" ]; then
  echo "venv python not found at $PY — create it: python3 -m venv $VENV && $VENV/bin/pip install -r requirements.txt"
  exit 1
fi

echo "bb v1 live loop starting | repo=$REPO_DIR | mode=${BINGX_EXECUTION_MODE:-unset} | interval=${INTERVAL}s"

while true; do
  echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) cycle start ====="
  "$PY" -m production_replay.operator || echo "operator exited non-zero (continuing)"
  echo "===== cycle done, sleeping ${INTERVAL}s ====="
  sleep "$INTERVAL"
done
