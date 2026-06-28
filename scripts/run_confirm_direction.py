#!/usr/bin/env python3
"""Run confirm_direction and skip_low_volatility entry methods."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from datetime import timedelta
from ultimate_trader.historical_replay.models import ReplayConfig
from ultimate_trader.robustness_lab.replay_runner import run_selective_replay_with_regime, ensure_data
from ultimate_trader.robustness_lab.frozen_config import FrozenConfig
from ultimate_trader.regime_filter import RegimeGate

frozen = FrozenConfig()
rcfg = ReplayConfig(warmup_candles=50, taker_fee_percent=0.04, slippage_percent=0.02, funding_per_candle_percent=0.001)
candles = ensure_data("BTCUSDT", "15m", days=365)
end_ts = candles[-1].timestamp
total_days = (candles[-1].timestamp - candles[0].timestamp).days

def format_window(ts):
    return ts.strftime("%Y-%m-%d")

for method in ["confirm_direction", "skip_low_volatility"]:
    all_trades = []
    windows = 0
    for offset in range(0, total_days - 30 - 30, 30):
        test_end = end_ts - timedelta(days=offset)
        test_start = test_end - timedelta(days=30)
        train_start = test_start - timedelta(days=30)
        train_end = test_start
        train_set = [c for c in candles if train_start <= c.timestamp < train_end]
        test_set = [c for c in candles if test_start <= c.timestamp < test_end]
        if len(train_set) < 60 or len(test_set) < 10:
            continue
        gate = RegimeGate()
        gate.fit(train_set)
        try:
            metrics, _, _, _ = run_selective_replay_with_regime(
                test_set, frozen, rcfg, gate, diagnose=True,
                stop_method="hybrid", entry_method=method,
            )
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
            continue
        for d in metrics.get("trade_diagnostics", []):
            d["window"] = format_window(test_start) + "->" + format_window(test_end)
        all_trades.extend(metrics.get("trade_diagnostics", []))
        windows += 1
        print(f"{method}: window {windows} done ({len(all_trades)} trades)", flush=True)
    
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
    
    print(f"\n=== {method} ===")
    print(f"Windows: {windows}, Trades: {total}, W: {len(winners)} L: {len(losers)}")
    print(f"WR: {wr:.1f}% | EV: {ev:+.2f}R | PF: {pf:.2f} | DD: {max_dd:.1f}R")
    print(f"AvgW: {avg_win:+.2f}R | AvgL: {avg_loss:.2f}R")
    print(f"Quick losses: {quick_losses}/{len(losers)} ({quick_loss_pct:.0f}%)")
    print(f"TP1={tp1_pct:.0f}% TP2={tp2_pct:.0f}% TP3={tp3_pct:.0f}%")
