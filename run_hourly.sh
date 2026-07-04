#!/usr/bin/env bash
cd "$(dirname "$0")"
while true; do
  python -m production_replay.hourly_alert >> hourly_loop.log 2>&1
  sleep 3600
done
