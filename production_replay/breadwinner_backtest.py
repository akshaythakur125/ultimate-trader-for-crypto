"""Breadwinner Backtest for Phase 76 — Liquidity Sweep Reversal v2.

Walk-forward backtest of the Liquidity Sweep Reversal v2 strategy.
Tests across 15m and 30m timeframes, multiple RR targets.
Uses 70/30 in-sample/out-of-sample split.

This module NEVER places real orders, NEVER enables live trading.
"""

import json, os, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.breadwinner_strategy_library import (
    _load_candles, detect_liquidity_sweep_v2, simulate_trade,
    _compute_stats, _check_promotion, _max_dd, _max_consec,
    TIMEFRAMES, RR_TARGETS, SPLIT_RATIO, FEE_RATE, MIN_TRADES,
    MIN_OOS_TRADES, MIN_SYMBOLS, MIN_OOS_AVG_R, MIN_OOS_WIN_RATE,
    MIN_PROFIT_FACTOR, MAX_MAX_DD, MAX_CONSEC_LOSSES, BANNED_FIELDS,
)

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
CACHE_DIR = os.path.join(STATE_DIR, "candles_cache")
JSON_PATH = os.path.join(RESULTS_DIR, "breadwinner_strategy_report.json")
TXT_PATH = os.path.join(RESULTS_DIR, "breadwinner_strategy_report.txt")


def _get_symbols() -> list[str]:
    symbols = []
    if os.path.exists(CACHE_DIR):
        for f in os.listdir(CACHE_DIR):
            if f.endswith("_15m.json"):
                sym = f.replace("_15m.json", "")
                symbols.append(sym)
    return sorted(symbols)


def _run_backtest_variant(
    symbols: list[str],
    timeframe: str,
    rr_target: float,
    sweep_lookback: int = 20,
    volume_lookback: int = 20,
    max_holding: int = 48,
) -> dict | None:
    all_trades = []
    seen_keys = set()

    for sym in symbols:
        candles = _load_candles(sym, timeframe)
        if len(candles) < 60:
            continue

        open_until = -1  # no overlapping trades on the same symbol
        for i in range(sweep_lookback + 5, len(candles)):
            if i <= open_until:
                continue
            sig = detect_liquidity_sweep_v2(
                candles, i, sweep_lookback, volume_lookback, max_holding, rr_target
            )
            if sig is None:
                continue

            direction = sig["direction"]
            entry = sig["entry"]
            stop = sig["stop"]
            target = sig["target"]

            sig_key = f"{sym}_{timeframe}_{direction}_{i}"
            if sig_key in seen_keys:
                continue
            seen_keys.add(sig_key)

            result = simulate_trade(candles, i, direction, entry, stop, target, max_holding)
            open_until = result["exit_idx"]
            fee = (entry + result["exit_price"]) * FEE_RATE
            r_after_fees = result["r_result"] - fee / abs(entry - stop) if abs(entry - stop) > 0 else result["r_result"]

            trade = {
                "symbol": sym, "timeframe": timeframe, "direction": direction,
                "pattern": sig["pattern"], "entry_price": entry, "stop": stop,
                "target": target, "exit_price": result["exit_price"],
                "entry_time": int(candles[i].get("timestamp", i)),
                "r_result": result["r_result"],
                "r_after_fees": round(r_after_fees, 4),
                "is_win": result["r_result"] > 0,
                "outcome": result["outcome"],
                "holding": result["holding"],
                "swing_level": sig.get("swing_level", 0),
                "wick_ratio": sig.get("wick_ratio", 0),
                "volume_ratio": sig.get("volume_ratio", 0),
                "range_ratio": sig.get("range_ratio", 0),
            }
            all_trades.append(trade)

    if not all_trades:
        return None

    # Walk-forward split: 70/30 by entry time, so OOS is strictly later in time
    sorted_t = sorted(all_trades, key=lambda t: t.get("entry_time", 0))
    split = int(len(sorted_t) * SPLIT_RATIO)
    is_t = sorted_t[:split]
    oos_t = sorted_t[split:]

    all_stats = _compute_stats(all_trades)
    is_stats = _compute_stats(is_t)
    oos_stats = _compute_stats(oos_t)

    verdict, reasons = _check_promotion(all_stats, is_stats, oos_stats)

    return {
        "timeframe": timeframe,
        "rr_target": rr_target,
        "sweep_lookback": sweep_lookback,
        "volume_lookback": volume_lookback,
        "max_holding": max_holding,
        "total_trades": all_stats["trades"],
        "oos_trades": oos_stats["trades"],
        "win_rate": all_stats["win_rate"],
        "avg_r": all_stats["avg_r"],
        "oos_avg_r": oos_stats["avg_r"],
        "oos_win_rate": oos_stats["win_rate"],
        "profit_factor": all_stats["profit_factor"],
        "max_dd": all_stats["max_dd"],
        "max_consec": all_stats["max_consec"],
        "unique_symbols": len(all_stats["symbols"]),
        "is_avg_r": is_stats["avg_r"],
        "verdict": verdict,
        "reject_reasons": reasons,
    }


def run_breadwinner_backtest() -> dict:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)

    symbols = _get_symbols()
    if not symbols:
        symbols = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]

    variants_tested = 0
    variants_passed = 0
    all_results = []
    best_variant = None

    for tf in TIMEFRAMES:
        for rr in RR_TARGETS:
            result = _run_backtest_variant(symbols, tf, rr)
            if result is None:
                continue
            variants_tested += 1
            all_results.append(result)
            if result["verdict"] in ("PAPER_CANDIDATE", "PAPER_PRIORITY"):
                variants_passed += 1
                if best_variant is None or result["oos_avg_r"] > best_variant.get("oos_avg_r", 0):
                    best_variant = result

    # Determine final verdict
    if best_variant and best_variant.get("verdict") == "PAPER_PRIORITY":
        final_verdict = "PAPER_PRIORITY"
    elif best_variant and best_variant.get("verdict") == "PAPER_CANDIDATE":
        final_verdict = "PAPER_CANDIDATE"
    else:
        final_verdict = "NO_EDGE_FOUND"

    # Analyze best timeframe
    tf_stats = {}
    for r in all_results:
        tf = r["timeframe"]
        if tf not in tf_stats:
            tf_stats[tf] = {"trades": 0, "avg_r": 0}
        tf_stats[tf]["trades"] += r["total_trades"]
        tf_stats[tf]["avg_r"] = max(tf_stats[tf]["avg_r"], r["oos_avg_r"])

    best_tf = max(tf_stats.items(), key=lambda x: x[1]["avg_r"])[0] if tf_stats else "N/A"

    # Analyze best side
    long_trades = []
    short_trades = []
    for r in all_results:
        if r.get("oos_avg_r", 0) > 0:
            if r.get("rr_target", 0) <= 3:
                long_trades.append(r)
            else:
                short_trades.append(r)

    # Top rejected variants
    rejected = [r for r in all_results if r["verdict"] == "REJECTED"]
    top_rejected = sorted(rejected, key=lambda x: x.get("oos_avg_r", 0), reverse=True)[:5]

    report = {
        "mode": "breadwinner_strategy_backtest",
        "strategy": "LIQUIDITY_SWEEP_REVERSAL_V2",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "live_trading_enabled": False,
        "real_order": False,
        "symbols_scanned": len(symbols),
        "variants_tested": variants_tested,
        "variants_passed": variants_passed,
        "best_variant": best_variant,
        "final_verdict": final_verdict,
        "best_timeframe": best_tf,
        "timeframe_stats": tf_stats,
        "promising_variants": [r for r in all_results if r["verdict"] in ("PAPER_CANDIDATE", "PAPER_PRIORITY")],
        "rejected_variants": top_rejected,
        "warnings": [],
    }

    # Leakage check
    for field in BANNED_FIELDS:
        if field in str(all_results).lower():
            report["warnings"].append(f"potential leakage: {field}")

    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2, default=str)

    _write_text_report(report)
    return report


def _write_text_report(report: dict):
    lines = [
        "=" * 60,
        "  BREADWINNER STRATEGY BACKTEST",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  Strategy:           {report['strategy']}",
        f"  Symbols Scanned:    {report['symbols_scanned']}",
        f"  Variants Tested:    {report['variants_tested']}",
        f"  Variants Passed:    {report['variants_passed']}",
        f"  Final Verdict:      {report['final_verdict']}",
        f"  Best Timeframe:     {report['best_timeframe']}",
        "",
    ]

    best = report.get("best_variant")
    if best:
        lines += [
            "  BEST VARIANT:",
            f"    Timeframe:    {best['timeframe']}",
            f"    RR Target:    {best['rr_target']}",
            f"    Total Trades: {best['total_trades']}",
            f"    OOS Trades:   {best['oos_trades']}",
            f"    Win Rate:     {best['win_rate']}%",
            f"    IS Avg R:     {best['is_avg_r']}",
            f"    OOS Avg R:    {best['oos_avg_r']}",
            f"    OOS Win Rate: {best['oos_win_rate']}%",
            f"    Profit Factor:{best['profit_factor']}",
            f"    Max DD:       {best['max_dd']}",
            f"    Max Consec:   {best['max_consec']}",
            f"    Symbols:      {best['unique_symbols']}",
            f"    Verdict:      {best['verdict']}",
            "",
        ]
    else:
        lines += ["  BEST VARIANT: NONE", ""]

    promising = report.get("promising_variants", [])
    if promising:
        lines += [f"  PROMISING VARIANTS ({len(promising)}):", ""]
        for v in sorted(promising, key=lambda x: -x.get("oos_avg_r", 0))[:5]:
            lines.append(
                f"    {v['timeframe']:4s} RR:{v['rr_target']} "
                f"OOS_R:{v['oos_avg_r']:.3f} PF:{v['profit_factor']:.2f} "
                f"Trades:{v['total_trades']} Verdict:{v['verdict']}"
            )

    rejected = report.get("rejected_variants", [])
    if rejected:
        lines += ["", f"  TOP REJECTED VARIANTS ({len(rejected)}):", ""]
        for v in rejected[:3]:
            lines.append(
                f"    {v['timeframe']:4s} RR:{v['rr_target']} "
                f"OOS_R:{v['oos_avg_r']:.3f} Reasons:{'; '.join(v.get('reject_reasons', [])[:2])}"
            )

    lines += [
        "",
        "  WARNING: Paper execution only. No real orders placed.",
        "",
        "=" * 60,
    ]

    with open(TXT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n[JSON] {JSON_PATH}")
    print(f"[TXT]  {TXT_PATH}")


def main():
    report = run_breadwinner_backtest()
    return 0


if __name__ == "__main__":
    sys.exit(main())
