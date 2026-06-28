#!/usr/bin/env python3
"""Regime-gated only: 180d test with reference=last 30d. Skips A+ baseline (already known)."""

import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(line_buffering=True)

from ultimate_trader.historical_replay.models import ReplayConfig
from ultimate_trader.robustness_lab import (
    FrozenConfig, ensure_data, run_selective_replay_with_regime,
)
from ultimate_trader.regime_filter import RegimeGate

frozen = FrozenConfig()
rcfg = ReplayConfig(warmup_candles=50, taker_fee_percent=0.04,
    slippage_percent=0.02, funding_per_candle_percent=0.001)

candles = ensure_data("BTCUSDT", "15m")
total = len(candles)
print(f"Total candles: {total}", flush=True)

# Reference = last 30 days (the profitable regime: +1.18R EV)
ref = candles[-2880:]
print(f"Reference: {len(ref)} candles ({ref[0].timestamp} -> {ref[-1].timestamp})", flush=True)

t0 = time.time()
gate = RegimeGate()
gate.fit(ref)
print(f"Fit: {time.time()-t0:.0f}s", flush=True)

t0 = time.time()
m2, _, _, stats = run_selective_replay_with_regime(candles, frozen, rcfg, gate)
t1 = time.time()
scores = stats.get("regime_scores", [])
blk = stats.get("regime_blocked", 0)
pct = blk / max(len(scores), 1) * 100
n_after = m2["total_trades"]

print(f"Run: {t1-t0:.0f}s", flush=True)
print(f"RESULTS:", flush=True)
print(f"  +regime: {n_after}t EV {m2['expectancy']:.2f}R PF {m2['profit_factor']:.2f} DD {m2['max_drawdown']:.1f}R", flush=True)
print(f"  Blocked: {blk}/{len(scores)} ({pct:.1f}%) avg_score {sum(scores)/len(scores):.1f}", flush=True)

# Per-period block rates
def period_rate(start_dt, end_dt, label):
    si = next((i for i,c in enumerate(candles) if c.timestamp >= start_dt), 0)
    ei = next((i for i,c in enumerate(candles) if c.timestamp >= end_dt), len(candles))
    ps = scores[si:ei]
    if not ps: return
    b = sum(1 for s in ps if s < 50)
    print(f"  {label}: {len(ps)}c {b}blk ({b/len(ps)*100:.1f}%) score {sum(ps)/len(ps):.1f}", flush=True)

p90 = candles[-8640].timestamp if total >=8640 else candles[0].timestamp
p60 = candles[-5760].timestamp if total >=5760 else candles[0].timestamp
p30 = candles[-2880].timestamp if total >=2880 else candles[0].timestamp
print(f"\nPer-period block rates:", flush=True)
period_rate(candles[0].timestamp, p90, "First 90d  ")
period_rate(p90, p60, "Days 90-120")
period_rate(p60, p30, "Days 120-150")
period_rate(p30, candles[-1].timestamp, "Last 30d REF")

print(f"\n{'='*60}", flush=True)
print("FINAL VERDICT", flush=True)
print(f"{'='*60}", flush=True)
print(f"A+ alone:             190t EV +0.47R PF 1.68 DD 12.3R", flush=True)
print(f"+regime (last-30d ref): {n_after:3d}t EV {m2['expectancy']:.2f}R PF {m2['profit_factor']:.2f} DD {m2['max_drawdown']:.1f}R blocked {pct:.1f}%", flush=True)

if pct >= 5:
    print(f"\nCLASSIFICATION: USEFUL (blocks {pct:.1f}% >= 5%)", flush=True)
else:
    print(f"\nCLASSIFICATION: NOT USEFUL (blocks {pct:.1f}% < 5%)", flush=True)
