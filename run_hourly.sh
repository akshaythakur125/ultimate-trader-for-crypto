#!/usr/bin/env bash
cd "$(dirname "$0")"
PYTHON=".venv/bin/python"
while true; do
  $PYTHON -m production_replay.bb_paper_pipeline >> hourly_loop.log 2>&1
  sleep 3600
done
