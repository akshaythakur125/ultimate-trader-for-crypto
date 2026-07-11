#!/usr/bin/env bash
cd "$(dirname "$0")"
PYTHON=".venv/bin/python"
while true; do
  BINGX_EXECUTION_MODE=live $PYTHON -u -m production_replay.live_scan >> hourly_loop.log 2>&1
  sleep 3600
done
