#!/usr/bin/env python3
"""Compare stop methods: baseline, avg5, avg10, avg20, structure, hybrid.

Each method is tested through the same causal walk-forward (30d/30d/30d
with regime gate). No threshold optimization, no new indicators.
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

METHODS = ["baseline", "avg5", "hybrid", "avg5_hybrid"]
results = {}

def compute_tp_hits(trades):
    """Estimate TP1/TP2/TP3 hit rates from exit_reason='TAKE_PROFIT' trades.
       Winners always hit TP1; track avg win to estimate higher TPs."""
    winners = [t for t in trades if t["net_r"] > 0]
    losers = [t for t in trades if t["net_r"] <= 0]
    tp_trades = [t for t in trades if "TAKE_PROFIT" in str(t.get("exit_reason", "")).upper()]
    sl_trades = [t for t in trades if "STOP_LOSS" in str(t.get("exit_reason", "")).upper()]
    # Estimate TP hit distribution from avg win R
    avg_win = sum(t["net_r"] for t in winners) / len(winners) if winners else 0
    tp1_pct = len(winners) / max(len(trades), 1) * 100
    tp2_pct = sum(1 for t in winners if t["net_r"] >= 2.0) / max(len(winners), 1) * 100
    tp3_pct = sum(1 for t in winners if t["net_r"] >= 3.5) / max(len(winners), 1) * 100
    return tp1_pct, tp2_pct, tp3_pct, avg_win

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
                diagnose=True, stop_method=method,
            )
        except Exception as e:
            print(f"  ERROR: {e}", flush=True)
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
    gross = sum(t["net_r"] for t in winners) + sum(t["net_r"] for t in losers)
    pf = abs(sum(t["net_r"] for t in winners) / max(abs(sum(t["net_r"] for t in losers)), 0.001))
    avg_win = sum(t["net_r"] for t in winners) / len(winners) if winners else 0
    avg_loss = sum(t["net_r"] for t in losers) / len(losers) if losers else 0
    max_dd = 0.0
    # Estimate max drawdown as worst cumulative R across trades
    running = 0
    low = 0
    for t in all_trades:
        running += t["net_r"]
        low = min(low, running - sum(t2["net_r"] for t2 in all_trades if t2["window"] == t["window"] and t2["net_r"] < 0))
    # Simple per-window DD estimation
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

    tp1_pct, tp2_pct, tp3_pct, _ = compute_tp_hits(all_trades)

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
print("STOP METHOD COMPARISON SUMMARY", flush=True)
print(f"{'='*70}", flush=True)

header = (f"{'Method':<12} {'Win':>4} {'Trades':>7} {'WR':>6} {'EV':>7} {'PF':>6} "
          f"{'DD':>6} {'AvgW':>6} {'AvgL':>6} {'QkLs':>5} {'TP1':>4} {'TP2':>4} {'TP3':>4}")
print(header, flush=True)
print("-" * len(header), flush=True)

best_ev = max(r["ev"] for r in results.values()) if results else 0
for method in METHODS:
    r = results.get(method)
    if not r:
        continue
    star = " *" if r["ev"] == best_ev and r["ev"] > 0 else "  "
    print(f"{r['method']:<12}{star} {r['total_trades']:>7} {r['win_rate']:>5.1f}% "
          f"{r['ev']:>+6.2f}R {r['pf']:>5.2f} {r['max_dd']:>5.1f}R "
          f"{r['avg_win']:>+5.2f}R {r['avg_loss']:>5.2f}R {r['quick_loss_pct']:>4.0f}% "
          f"{r['tp1_hit_pct']:>3.0f}% {r['tp2_hit_pct']:>3.0f}% {r['tp3_hit_pct']:>3.0f}%", flush=True)

print("-" * len(header), flush=True)
print("  * = best EV (among methods with positive EV)", flush=True)
print(f"\n{'='*70}", flush=True)
print("KEY", flush=True)
print(f"{'='*70}", flush=True)
print("  baseline:     1.5x single-candle range (current)", flush=True)
print("  avg5:         1.5x average of last 5 candle ranges", flush=True)
print("  hybrid:       max(baseline, min(structure, baseline*3.0/2.5))", flush=True)
print("                 RR capped at 2.5 (target scales to maintain >=2.5R)", flush=True)
print("  avg5_hybrid:  same as hybrid but uses 5-candle avg range", flush=True)
print("                 where single-candle range is used", flush=True)

# Verdict
print(f"\n{'='*70}", flush=True)
print("RECOMMENDATION", flush=True)
print(f"{'='*70}", flush=True)
best = max(results.values(), key=lambda r: r["ev"]) if results else None
if best:
    print(f"  Best method: {best['method']} (EV {best['ev']:+.2f}R, WR {best['win_rate']:.0f}%)", flush=True)
    print(f"  vs baseline: EV {results['baseline']['ev']:+.2f}R, WR {results['baseline']['win_rate']:.0f}%", flush=True)
    baseline = results["baseline"]
    ev_change = ((best["ev"] / max(baseline["ev"], 0.001)) - 1) * 100 if baseline["ev"] > 0 else float("inf")
    print(f"  EV change: {ev_change:+.0f}%", flush=True)
    print(f"  Quick loss change: {best['quick_loss_pct']:.0f}% vs {baseline['quick_loss_pct']:.0f}%", flush=True)
