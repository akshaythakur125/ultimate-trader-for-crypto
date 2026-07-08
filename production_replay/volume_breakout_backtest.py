"""Volume breakout backtest for BB Bounce strategy.

Tests TWO volume breakout approaches:
  A) Volume on SIGNAL candle (band touch candle)
  B) Volume on ENTRY candle (next candle open)
  C) Volume on EITHER candle

Compares against baseline (no volume filter).
"""
import json, math, os, sys, time
from datetime import datetime, timezone
from statistics import mean, median

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.breadwinner_strategy_library import (
    detect_bb_bounce, _avg_volume, simulate_trade, _compute_stats, _max_dd, _max_consec,
)

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state", "candles_cache")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")

PERIOD = 15; STD_MULT = 3.5; RR_TARGET = 10.0; TIMEFRAME = "1h"
VOLUME_THRESHOLDS = [0, 1.0, 1.5, 2.0, 3.0]
WALK_FORWARD_SPLIT = 0.7


def get_symbols() -> list[str]:
    symbols = []
    if os.path.exists(CACHE_DIR):
        for f in sorted(os.listdir(CACHE_DIR)):
            if f.endswith("_1h.json"):
                symbols.append(f.replace("_1h.json", ""))
    return symbols


def backtest_bb(min_volume_ratio: float) -> dict:
    """Baseline backtest (no volume filter)."""
    symbols = get_symbols()
    all_trades = []
    for sym in symbols:
        path = os.path.join(CACHE_DIR, f"{sym}_1h.json")
        try:
            with open(path) as f: candles = json.load(f)
        except Exception: continue
        if not isinstance(candles, list) or len(candles) < 100: continue
        seen = set()
        for idx in range(PERIOD + 10, len(candles) - 2):
            sig = detect_bb_bounce(candles, idx, period=PERIOD, std_mult=STD_MULT,
                                   rr_target=RR_TARGET, max_holding=0, min_entry_volume_ratio=min_volume_ratio)
            if not sig: continue
            entry_idx = idx + 1
            if entry_idx >= len(candles): continue
            dir_key = (sym, sig["direction"], round(sig["entry"], 6))
            if dir_key in seen: continue
            seen.add(dir_key)
            result = simulate_trade(candles, entry_idx, sig["direction"],
                                    sig["entry"], sig["stop"], sig["target"], max_holding=9999)
            result["symbol"] = sym
            result["timeframe"] = TIMEFRAME
            result["direction"] = sig["direction"]
            result["entry"] = sig["entry"]
            result["volume_ratio_signal"] = sig.get("volume_ratio", 0)
            # Entry candle volume ratio
            if entry_idx < len(candles):
                entry_vol = float(candles[entry_idx].get("volume", 0))
                avg_vol = _avg_volume(candles, entry_idx, 20)
                result["volume_ratio_entry"] = entry_vol / avg_vol if avg_vol > 0 else 0
            else:
                result["volume_ratio_entry"] = 0
            all_trades.append(result)

    split_idx = int(len(all_trades) * WALK_FORWARD_SPLIT)
    is_trades = all_trades[:split_idx]
    oos_trades = all_trades[split_idx:]
    stats = _compute_stats(all_trades)
    oos_stats = _compute_stats(oos_trades)

    return {
        "total_trades": stats["trades"],
        "oos_trades": oos_stats["trades"],
        "win_rate": stats["win_rate"],
        "oos_win_rate": oos_stats["win_rate"],
        "avg_r": stats["avg_r"],
        "oos_avg_r": oos_stats["avg_r"],
        "total_r": round(sum(t.get("r_result", 0) for t in all_trades), 2),
        "profit_factor": stats["profit_factor"],
        "max_dd": stats["max_dd"],
        "max_consec": stats["max_consec"],
        "symbols": len(stats["symbols"]),
    }


def backtest_bb_entry_volume(volume_threshold: float) -> dict:
    """Volume breakout on ENTRY candle (not signal candle)."""
    symbols = get_symbols()
    all_trades = []
    for sym in symbols:
        path = os.path.join(CACHE_DIR, f"{sym}_1h.json")
        try:
            with open(path) as f: candles = json.load(f)
        except Exception: continue
        if not isinstance(candles, list) or len(candles) < 100: continue
        seen = set()
        for idx in range(PERIOD + 10, len(candles) - 2):
            # Always detect with NO volume filter first
            sig = detect_bb_bounce(candles, idx, period=PERIOD, std_mult=STD_MULT,
                                   rr_target=RR_TARGET, max_holding=0, min_entry_volume_ratio=0.0)
            if not sig: continue
            entry_idx = idx + 1
            if entry_idx >= len(candles): continue
            # Volume check on ENTRY candle
            entry_vol = float(candles[entry_idx].get("volume", 0))
            avg_vol = _avg_volume(candles, entry_idx, 20)
            vol_ratio = entry_vol / avg_vol if avg_vol > 0 else 0
            if vol_ratio < volume_threshold: continue
            dir_key = (sym, sig["direction"], round(sig["entry"], 6))
            if dir_key in seen: continue
            seen.add(dir_key)
            result = simulate_trade(candles, entry_idx, sig["direction"],
                                    sig["entry"], sig["stop"], sig["target"], max_holding=9999)
            result["symbol"] = sym
            result["timeframe"] = TIMEFRAME
            result["direction"] = sig["direction"]
            result["entry"] = sig["entry"]
            all_trades.append(result)

    split_idx = int(len(all_trades) * WALK_FORWARD_SPLIT)
    is_trades = all_trades[:split_idx]
    oos_trades = all_trades[split_idx:]
    stats = _compute_stats(all_trades)
    oos_stats = _compute_stats(oos_trades)

    return {
        "total_trades": stats["trades"],
        "oos_trades": oos_stats["trades"],
        "win_rate": stats["win_rate"],
        "oos_win_rate": oos_stats["win_rate"],
        "avg_r": stats["avg_r"],
        "oos_avg_r": oos_stats["avg_r"],
        "total_r": round(sum(t.get("r_result", 0) for t in all_trades), 2),
        "profit_factor": stats["profit_factor"],
        "max_dd": stats["max_dd"],
        "max_consec": stats["max_consec"],
        "symbols": len(stats["symbols"]),
    }


def backtest_bb_either_volume(volume_threshold: float) -> dict:
    """Volume breakout on EITHER signal candle OR entry candle."""
    symbols = get_symbols()
    all_trades = []
    for sym in symbols:
        path = os.path.join(CACHE_DIR, f"{sym}_1h.json")
        try:
            with open(path) as f: candles = json.load(f)
        except Exception: continue
        if not isinstance(candles, list) or len(candles) < 100: continue
        seen = set()
        for idx in range(PERIOD + 10, len(candles) - 2):
            sig = detect_bb_bounce(candles, idx, period=PERIOD, std_mult=STD_MULT,
                                   rr_target=RR_TARGET, max_holding=0, min_entry_volume_ratio=0.0)
            if not sig: continue
            entry_idx = idx + 1
            if entry_idx >= len(candles): continue
            # Check volume on signal candle
            sig_vol = float(candles[idx].get("volume", 0))
            sig_avg = _avg_volume(candles, idx, 20)
            sig_ratio = sig_vol / sig_avg if sig_avg > 0 else 0
            # Check volume on entry candle
            entry_vol = float(candles[entry_idx].get("volume", 0))
            entry_avg = _avg_volume(candles, entry_idx, 20)
            entry_ratio = entry_vol / entry_avg if entry_avg > 0 else 0
            # Either must exceed threshold
            if sig_ratio < volume_threshold and entry_ratio < volume_threshold: continue
            dir_key = (sym, sig["direction"], round(sig["entry"], 6))
            if dir_key in seen: continue
            seen.add(dir_key)
            result = simulate_trade(candles, entry_idx, sig["direction"],
                                    sig["entry"], sig["stop"], sig["target"], max_holding=9999)
            result["symbol"] = sym
            result["timeframe"] = TIMEFRAME
            result["direction"] = sig["direction"]
            all_trades.append(result)

    split_idx = int(len(all_trades) * WALK_FORWARD_SPLIT)
    is_trades = all_trades[:split_idx]
    oos_trades = all_trades[split_idx:]
    stats = _compute_stats(all_trades)
    oos_stats = _compute_stats(oos_trades)

    return {
        "total_trades": stats["trades"],
        "oos_trades": oos_stats["trades"],
        "win_rate": stats["win_rate"],
        "oos_win_rate": oos_stats["win_rate"],
        "avg_r": stats["avg_r"],
        "oos_avg_r": oos_stats["avg_r"],
        "total_r": round(sum(t.get("r_result", 0) for t in all_trades), 2),
        "profit_factor": stats["profit_factor"],
        "max_dd": stats["max_dd"],
        "max_consec": stats["max_consec"],
        "symbols": len(stats["symbols"]),
    }


def main():
    print("=" * 70)
    print("  BB BOUNCE — VOLUME BREAKOUT DEEP BACKTEST")
    print("  Config: p=%d s=%.1f rr=%.1f %s" % (PERIOD, STD_MULT, RR_TARGET, TIMEFRAME))
    print("=" * 70)
    print("\n  Testing 3 approaches across %d thresholds..." % len(VOLUME_THRESHOLDS))

    methods = [
        ("Signal candle volume", backtest_bb),
        ("Entry candle volume", backtest_bb_entry_volume),
        ("Either candle volume", backtest_bb_either_volume),
    ]

    all_results = {}
    for method_name, method_fn in methods:
        print("\n  --- %s ---" % method_name)
        results = []
        t0 = time.time()
        for threshold in VOLUME_THRESHOLDS:
            label = "No filter" if threshold == 0 else ">= %.1fx" % threshold
            t1 = time.time()
            r = method_fn(threshold)
            elapsed = time.time() - t1
            results.append(r)
            print("    %-14s Trades:%5d  WR:%5.1f%%  Avg R:%7.4f  OOS R:%7.4f  PF:%.2f  DD:%.1f [%.1fs]" % (
                label, r["total_trades"], r["win_rate"], r["avg_r"], r["oos_avg_r"],
                r["profit_factor"], r["max_dd"], elapsed))
        all_results[method_name] = results
        print("    Elapsed: %.1fs" % (time.time() - t0))

    # Summary
    print("\n" + "=" * 70)
    print("  COMPARISON: BEST OOS AVG R PER METHOD")
    print("=" * 70)
    baseline = all_results[list(all_results.keys())[0]][0]
    print("  %-24s %6s %6s %8s %8s %6s" % (
        "Method", "Trades", "WR%", "Avg R", "OOS R", "vs Base"))
    print("  " + "-" * 70)
    print("  %-24s %6d %5.1f%% %8.4f %8.4f %s" % (
        "BASELINE (no filter)", baseline["total_trades"], baseline["win_rate"],
        baseline["avg_r"], baseline["oos_avg_r"], "---"))

    for method_name, results in all_results.items():
        best_oos = max(results, key=lambda r: r["oos_avg_r"])
        change = ((best_oos["oos_avg_r"] - baseline["oos_avg_r"]) / abs(baseline["oos_avg_r"]) * 100)
        print("  %-24s %6d %5.1f%% %8.4f %8.4f %+.1f%%" % (
            "BEST: " + method_name, best_oos["total_trades"], best_oos["win_rate"],
            best_oos["avg_r"], best_oos["oos_avg_r"], change))

    print("\n  CONCLUSION:")
    best_all = "no filter (baseline)"
    for method_name, results in all_results.items():
        best_oos = max(results, key=lambda r: r["oos_avg_r"])
        if best_oos["oos_avg_r"] > baseline["oos_avg_r"]:
            best_all = "%s at threshold" % method_name

    if best_all == "no filter (baseline)":
        print("  Volume breakout does NOT improve BB bounce performance.")
        print("  The no-filter baseline remains optimal.")
    else:
        print("  Best approach: %s" % best_all)

    # Save
    out = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": "p=%d s=%.1f rr=%.1f" % (PERIOD, STD_MULT, RR_TARGET),
        "baseline": {"avg_r": baseline["avg_r"], "oos_avg_r": baseline["oos_avg_r"], "win_rate": baseline["win_rate"], "trades": baseline["total_trades"]},
        "results": all_results,
    }
    path = os.path.join(RESULTS_DIR, "volume_breakout_backtest.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print("\n  Saved to %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
