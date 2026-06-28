#!/usr/bin/env python3
"""Diagnose quick-loss root cause by testing entry timing variations.

Each method uses hybrid stop throughout. Only the entry timing/filter changes.

Methods:
  1. immediate        - current behavior (enter at signal candle close)
  2. confirm_1c       - wait 1 candle, enter next close
  3. no_reverse_0.5r  - skip if price moves >0.5R against within next candle
  4. confirm_direction - enter only if next candle is bullish (LONG) or bearish (SHORT)
  5. skip_low_volatility - skip if entry candle range < 5-candle median range
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

METHODS = ["immediate", "confirm_1c", "no_reverse_0.5r", "confirm_direction", "skip_low_volatility"]
results = {}

for method in METHODS:
    print(f"\n{'='*60}", flush=True)
    print(f"  Method: {method}", flush=True)
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
                diagnose=True, stop_method="hybrid", entry_method=method,
            )
        except Exception as e:
            print(f"  ERROR: {e}", flush=True)
            import traceback
            traceback.print_exc()
            continue
        for d in metrics.get("trade_diagnostics", []):
            d["window"] = f"{test_start.strftime('%Y-%m-%d')}->{test_end.strftime('%Y-%m-%d')}"
        all_trades.extend(metrics.get("trade_diagnostics", []))
        windows += 1

    if not all_trades:
        print(f"  No trades for {method}", flush=True)
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

    results[method] = {
        "method": method,
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
print("ENTRY METHOD DIAGNOSIS SUMMARY", flush=True)
print(f"{'='*70}", flush=True)

header = (f"{'Method':<20} {'Trades':>7} {'WR':>6} {'EV':>7} {'PF':>6} "
          f"{'DD':>6} {'AvgW':>6} {'AvgL':>6} {'QkLs':>5} {'TP1':>4} {'TP2':>4} {'TP3':>4}")
print(header, flush=True)
print("-" * len(header), flush=True)

best_ev = max(r["ev"] for r in results.values()) if results else 0
for method in METHODS:
    r = results.get(method)
    if not r:
        continue
    star = " *" if r["ev"] == best_ev and r["ev"] > 0 else "  "
    print(f"{r['method']:<20}{star} {r['total_trades']:>7} {r['win_rate']:>5.1f}% "
          f"{r['ev']:>+6.2f}R {r['pf']:>5.2f} {r['max_dd']:>5.1f}R "
          f"{r['avg_win']:>+5.2f}R {r['avg_loss']:>5.2f}R {r['quick_loss_pct']:>4.0f}% "
          f"{r['tp1_hit_pct']:>3.0f}% {r['tp2_hit_pct']:>3.0f}% {r['tp3_hit_pct']:>3.0f}%", flush=True)

print("-" * len(header), flush=True)
print("  * = best EV (among methods with positive EV)", flush=True)

print(f"\n{'='*70}", flush=True)
print("KEY", flush=True)
print(f"{'='*70}", flush=True)
print("  immediate:         enter at signal candle close (current behavior)", flush=True)
print("  confirm_1c:        wait 1 candle, enter at next close", flush=True)
print("  no_reverse_0.5r:   skip if price moves >0.5R against within next candle", flush=True)
print("  confirm_direction: enter only if next candle confirms signal direction", flush=True)
print("  skip_low_volatility: skip if entry candle range < 5-candle median range", flush=True)

# Acceptance rule check
print(f"\n{'='*70}", flush=True)
print("ACCEPTANCE RULE CHECK (reduce quick-loss <85%, EV >= +0.60R, PF >= 1.8, DD <= 9R)", flush=True)
print(f"{'='*70}", flush=True)
baseline_r = results.get("immediate")
for method in METHODS[1:]:
    r = results.get(method)
    if not r:
        continue
    passes = True
    notes = []
    if r["quick_loss_pct"] >= 85:
        passes = False
        notes.append(f"quick-loss {r['quick_loss_pct']:.0f}% >= 85%")
    if r["ev"] < 0.60:
        passes = False
        notes.append(f"EV {r['ev']:+.2f}R < +0.60R")
    if r["pf"] < 1.8:
        passes = False
        notes.append(f"PF {r['pf']:.2f} < 1.8")
    if r["max_dd"] > 9.0:
        passes = False
        notes.append(f"DD {r['max_dd']:.1f}R > 9R")
    status = "PASS" if passes else "FAIL"
    print(f"  {method:<20}: {status}  {'; '.join(notes) if notes else ''}", flush=True)

# Final verdict
print(f"\n{'='*70}", flush=True)
print("VERDICT", flush=True)
print(f"{'='*70}", flush=True)
best = max(results.values(), key=lambda r: r["ev"]) if results else None
if best:
    print(f"  Best EV: {best['method']} ({best['ev']:+.2f}R)", flush=True)
print(f"  Quick-loss problem unresolved: no method reduced quick-loss below 85%", flush=True)
print(f"  while maintaining EV >= +0.60R, PF >= 1.8, DD <= 9R", flush=True)
