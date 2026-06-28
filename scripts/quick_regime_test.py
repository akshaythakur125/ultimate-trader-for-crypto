#!/usr/bin/env python3
"""Fast regime gate test on 60 days only."""

import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(line_buffering=True)

from ultimate_trader.historical_replay.models import ReplayConfig
from ultimate_trader.robustness_lab import (
    FrozenConfig, ensure_data, run_selective_replay,
    run_selective_replay_with_regime,
)
from ultimate_trader.regime_filter import RegimeGate

frozen = FrozenConfig()
rcfg = ReplayConfig(warmup_candles=50, taker_fee_percent=0.04,
    slippage_percent=0.02, funding_per_candle_percent=0.001)

candles = ensure_data("BTCUSDT", "15m")
# Use last 5760 candles = 60 days
sub = candles[-5760:]
print(f"Using {len(sub)} candles (last 60d)", flush=True)

t0 = time.time()
m, ra, db = run_selective_replay(sub, frozen, rcfg)
t1 = time.time()
print(f"[{t1-t0:.0f}s] A+ alone: {m['total_trades']}t "
      f"EV {m['expectancy']:.2f}R PF {m['profit_factor']:.2f} "
      f"DD {m['max_drawdown']:.1f}R", flush=True)

# Reference = first 30 days of sub (not the same as test period)
train = sub[:2880]
t0 = time.time()
gate = RegimeGate()
gate.fit(train)
t1 = time.time()
print(f"[{t1-t0:.0f}s] Fit reference on {len(train)} candles", flush=True)

t0 = time.time()
m2, _, _, s2 = run_selective_replay_with_regime(sub, frozen, rcfg, gate)
t1 = time.time()
scores = s2.get("regime_scores", [])
blk = s2.get("regime_blocked", 0)
pct = blk / max(len(scores), 1) * 100
print(f"[{t1-t0:.0f}s] +regime: {m2['total_trades']}t "
      f"EV {m2['expectancy']:.2f}R PF {m2['profit_factor']:.2f} "
      f"DD {m2['max_drawdown']:.1f}R blocked {blk}/{len(scores)} ({pct:.1f}%) "
      f"avg_score {sum(scores)/len(scores):.1f}", flush=True)

print(f"\nVERDICT: {'NOT USEFUL' if pct < 5 else 'USEFUL'} "
      f"(blocks {pct:.1f}%)", flush=True)
