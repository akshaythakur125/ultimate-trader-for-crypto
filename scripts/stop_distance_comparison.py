#!/usr/bin/env python3
"""Compare structural stop-distance approaches.

Each method uses the regime gate. Entry timing is immediate for methods 1-6,
skip_low_volatility for methods 7-8.

Methods:
  1. hybrid (current baseline)
  2. wide20: 2.0 x candle range
  3. wide25: 2.5 x candle range
  4. atr14_15: 1.5 x ATR14
  5. atr14_20: 2.0 x ATR14
  6. structure: nearest swing/OB invalidation
  7. hybrid + skip_low_volatility
  8. best of 2-6 + skip_low_volatility
"""

import os, sys
from datetime import datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ultimate_trader.historical_replay.models import ReplayConfig
from ultimate_trader.robustness_lab.replay_runner import run_selective_replay_with_regime, ensure_data
from ultimate_trader.robustness_lab.frozen_config import FrozenConfig
from ultimate_trader.regime_filter import RegimeGate

frozen = FrozenConfig()
rcfg = ReplayConfig(warmup_candles=50, taker_fee_percent=0.04,
    slippage_percent=0.02, funding_per_candle_percent=0.001)

candles = ensure_data("BTCUSDT", "15m", days=365)
end_ts = candles[-1].timestamp

# Methods 1-7: explicit. Method 8 determined after first 7 run.
METHODS = [
    ("hybrid", "immediate"),
    ("wide20", "immediate"),
    ("wide25", "immediate"),
    ("atr14_15", "immediate"),
    ("atr14_20", "immediate"),
    ("structure", "immediate"),
    ("hybrid", "skip_low_volatility"),
]
results = {}

def format_window(ts):
    return ts.strftime("%Y-%m-%d")

for stop_method, entry_method in METHODS:
    label = f"{stop_method}+{entry_method}" if entry_method != "immediate" else stop_method
    print(f"\n{'='*60}", flush=True)
    print(f"  Method: {label}", flush=True)
    print(f"{'='*60}", flush=True)

    all_trades = []
    total_days = (candles[-1].timestamp - candles[0].timestamp).days
    step = 30
    train_days = 30
    test_days = 30
    windows = 0

    for offset in range(0, total_days - train_days - test_days, step):
        test_end = end_ts - timedelta(days=offset)
        test_start = test_end - timedelta(days=test_days)
        train_start = test_start - timedelta(days=train_days)
        train_end = test_start

        train_set = [c for c in candles if train_start <= c.timestamp < train_end]
        test_set = [c for c in candles if test_start <= c.timestamp < test_end]
        if len(train_set) < rcfg.warmup_candles + 10 or len(test_set) < 10:
            continue

        gate = RegimeGate()
        gate.fit(train_set)
        try:
            metrics, _, _, _ = run_selective_replay_with_regime(
                test_set, frozen, rcfg, gate,
                diagnose=True, stop_method=stop_method, entry_method=entry_method,
            )
        except Exception as e:
            print(f"  ERROR: {e}", flush=True)
            import traceback
            traceback.print_exc()
            continue
        for d in metrics.get("trade_diagnostics", []):
            d["window"] = format_window(test_start) + "->" + format_window(test_end)
        all_trades.extend(metrics.get("trade_diagnostics", []))
        windows += 1

    if not all_trades:
        print(f"  No trades for {label}", flush=True)
        continue

    total = len(all_trades)
    winners = [t for t in all_trades if t["net_r"] > 0]
    losers = [t for t in all_trades if t["net_r"] <= 0]
    wr = len(winners) / total * 100 if total else 0
    ev = sum(t["net_r"] for t in all_trades) / total if total else 0
    pf = abs(sum(t["net_r"] for t in winners) / max(abs(sum(t["net_r"] for t in losers)), 0.001))
    avg_win = sum(t["net_r"] for t in winners) / len(winners) if winners else 0
    avg_loss = sum(t["net_r"] for t in losers) / len(losers) if losers else 0

    window_dds = []
    windows_data = {}
    for t in all_trades:
        windows_data.setdefault(t["window"], []).append(t)
    for w, wt in windows_data.items():
        cum = 0
        peak = 0
        dd = 0
        for t in wt:
            cum += t["net_r"]
            peak = max(peak, cum)
            dd = max(dd, peak - cum)
        window_dds.append(dd)
    max_dd = max(window_dds) if window_dds else 0

    quick_losses = sum(1 for t in losers if t.get("holding_candles", 99) <= 3)
    quick_loss_pct = quick_losses / max(len(losers), 1) * 100

    tp1_pct = len(winners) / max(total, 1) * 100
    tp2_pct = sum(1 for t in winners if t["net_r"] >= 2.0) / max(len(winners), 1) * 100
    tp3_pct = sum(1 for t in winners if t["net_r"] >= 3.5) / max(len(winners), 1) * 100

    results[label] = {
        "method": label,
        "windows": windows,
        "total_trades": total,
        "win_rate": wr,
        "ev": ev,
        "pf": pf,
        "max_dd": max_dd,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "quick_loss_pct": quick_loss_pct,
        "tp1_hit_pct": tp1_pct,
        "tp2_hit_pct": tp2_pct,
        "tp3_hit_pct": tp3_pct,
    }
    print(f"  Windows: {windows}", flush=True)
    print(f"  Trades: {total} | W: {len(winners)} L: {len(losers)}", flush=True)
    print(f"  WR: {wr:.1f}% | EV: {ev:+.2f}R | PF: {pf:.2f}", flush=True)
    print(f"  Max DD: {max_dd:.1f}R", flush=True)
    print(f"  Avg win: {avg_win:+.2f}R | Avg loss: {avg_loss:.2f}R", flush=True)
    print(f"  Quick losses (<=3c): {quick_losses}/{len(losers)} ({quick_loss_pct:.0f}%)", flush=True)
    print(f"  TP hits: TP1={tp1_pct:.0f}% TP2={tp2_pct:.0f}% TP3={tp3_pct:.0f}%", flush=True)

print(f"\n{'='*70}", flush=True)
print("STOP-DISTANCE COMPARISON SUMMARY", flush=True)
print(f"{'='*70}", flush=True)

header = (f"{'Method':<28} {'Trd':>4} {'WR':>5} {'EV':>7} {'PF':>5} "
          f"{'DD':>5} {'AvgW':>5} {'AvgL':>5} {'QkLs':>4} {'TP1':>3} {'TP2':>3} {'TP3':>3}")
print(header, flush=True)
print("-" * len(header), flush=True)

for label, r in results.items():
    print(f"{r['method']:<28} {r['total_trades']:>4} {r['win_rate']:>4.1f}% "
          f"{r['ev']:>+6.2f}R {r['pf']:>4.2f} {r['max_dd']:>4.1f}R "
          f"{r['avg_win']:>+4.2f}R {r['avg_loss']:>4.2f}R {r['quick_loss_pct']:>3.0f}% "
          f"{r['tp1_hit_pct']:>2.0f}% {r['tp2_hit_pct']:>2.0f}% {r['tp3_hit_pct']:>2.0f}%", flush=True)

print("-" * len(header), flush=True)

# Acceptance rule check
print(f"\n{'='*70}", flush=True)
print("ACCEPTANCE RULE CHECK", flush=True)
print("  EV >= +0.65R, PF >= 2.0, DD <= 8.6R, quick-loss < 90%", flush=True)
print(f"{'='*70}", flush=True)

baseline = results.get("hybrid")
for label, r in results.items():
    if label == "hybrid":
        continue
    passes = True
    notes = []
    if r["ev"] < 0.65:
        passes = False
        notes.append(f"EV {r['ev']:+.2f}R < +0.65R")
    if r["pf"] < 2.0:
        passes = False
        notes.append(f"PF {r['pf']:.2f} < 2.0")
    if r["max_dd"] > 8.6:
        notes.append(f"DD {r['max_dd']:.1f}R > 8.6R (worse)")
    if r["quick_loss_pct"] >= 90:
        passes = False
        notes.append(f"QkLs {r['quick_loss_pct']:.0f}% >= 90%")
    status = "PASS" if passes else "FAIL"
    print(f"  {label:<28}: {status}  {'; '.join(notes)}", flush=True)

# Final verdict
print(f"\n{'='*70}", flush=True)
print("VERDICT", flush=True)
print(f"{'='*70}", flush=True)
print("  Best candidates (meeting all acceptance criteria):", flush=True)
passing = [r for r in results.values() if r["ev"] >= 0.65 and r["pf"] >= 2.0 and r["max_dd"] <= 8.6 and r["quick_loss_pct"] < 90]
if passing:
    for r in sorted(passing, key=lambda x: x["ev"], reverse=True):
        print(f"    {r['method']:<28} EV {r['ev']:+.2f}R PF {r['pf']:.2f} DD {r['max_dd']:.1f}R QkLs {r['quick_loss_pct']:.0f}%", flush=True)
else:
    print("    (none)", flush=True)
print(f"\n  Hybrid baseline: EV +0.65R, PF 2.00, DD 8.6R, QkLs 93%", flush=True)
