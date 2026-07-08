#!/bin/bash
export BINGX_API_KEY=gDwH54YiBGgWXFWn4Ms82fKp3NuBzSV7rHhx17he2c8cHNkrv0l8iWSsNKTPnC6YuMNu9vPeW59F8CIv0e5w
export BINGX_API_SECRET=YggtJmMraojKmonzFx5eRZh39oSWw5JytYL6YSmnagmQvTw2XqJXJfPtzG0DJFWZ4zXyxOzAeX2vTkFUlYQ
export BINGX_EXECUTION_MODE=live
cd /home/docakshaythakur/ultimate-trader-for-crypto
while true; do
  /home/docakshaythakur/venv/bin/python3 -m production_replay.live_scan 2>&1 | tail -30
  sleep 3600
done