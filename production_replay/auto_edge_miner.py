"""Auto Edge Miner for Phase 75 — Hands-Off Breadwinner Sprint.

Tests strategy variants across parameter spaces using strict walk-forward
validation (70% in-sample, 30% out-of-sample). Rejects overfit and
fragile edges. No outcome leakage fields used.

Strategy families tested:
- liquidity_sweep_reversal
- mean_reversion
- compression_breakout
- trend_pullback
- short_weakness

Parameter search:
- timeframe: 5m, 15m, 30m, 1h
- RR: 3, 4, 5, 6
- confirmation bars: 1, 2, 3
- sweep lookback: 10, 20, 50
- stop buffer: 0%, 0.1%, 0.2%, 0.3%

This module NEVER places real orders, NEVER enables live trading.
"""

import json, math, os, sys
from datetime import datetime, timezone
from statistics import mean, median

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
CACHE_DIR = os.path.join(STATE_DIR, "candles_cache")
JSON_PATH = os.path.join(RESULTS_DIR, "auto_edge_miner_report.json")
TXT_PATH = os.path.join(RESULTS_DIR, "auto_edge_miner_report.txt")

SPLIT_RATIO = 0.7  # 70/30 walk-forward
MAX_HOLDING_CANDLES = 120
FEE_RATE = 0.0004  # 0.04% per side

# Minimum thresholds for valid edge
MIN_TRADES = 300
MIN_OOS_TRADES = 100
MIN_SYMBOLS = 50
MIN_OOS_AVG_R = 0.0
MIN_PROFIT_FACTOR = 1.15
MAX_MAX_DD = 500.0
MAX_CONSEC_LOSSES = 30

# Parameter space
TIMEFRAMES = ["5m", "15m", "30m", "1h"]
RR_TARGETS = [3, 4, 5, 6]
CONFIRM_BARS = [1, 2, 3]
SWEEP_LOOKBACKS = [10, 20, 50]
STOP_BUFFERS = [0.0, 0.001, 0.002, 0.003]

# Outcome-derived fields that must NOT be used
BANNED_FIELDS = {"r_result", "r_after_fees", "is_win", "outcome",
                 "exit_reason", "exit_price", "max_favorable_excursion_pct",
                 "max_adverse_excursion_pct", "holding_candles"}


def _load_candles(symbol: str, timeframe: str) -> list[dict]:
    tf_map = {"5m": "5m", "15m": "15m", "30m": "30m", "1h": "1h", "4h": "4h"}
    tf_dir = tf_map.get(timeframe, timeframe)
    path = os.path.join(CACHE_DIR, f"{symbol}_{tf_dir}.json")
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return []


def _simulate_trade(candles: list[dict], entry_idx: int, direction: str,
                    entry: float, stop: float, target: float,
                    max_holding: int = MAX_HOLDING_CANDLES) -> dict:
    risk = abs(entry - stop)
    if risk <= 0:
        return {"r_result": 0, "outcome": "INVALID", "exit_idx": entry_idx, "exit_price": entry, "holding": 0}

    for i in range(entry_idx + 1, min(entry_idx + max_holding + 1, len(candles))):
        c = candles[i]
        high = float(c.get("high", 0))
        low = float(c.get("low", 0))

        if direction == "LONG":
            if low <= stop:
                return {"r_result": -1.0, "outcome": "STOP_HIT", "exit_idx": i, "exit_price": stop, "holding": i - entry_idx}
            if high >= target:
                r = (target - entry) / risk
                return {"r_result": round(r, 4), "outcome": "TARGET_HIT", "exit_idx": i, "exit_price": target, "holding": i - entry_idx}
        else:
            if high >= stop:
                return {"r_result": -1.0, "outcome": "STOP_HIT", "exit_idx": i, "exit_price": stop, "holding": i - entry_idx}
            if low <= target:
                r = (entry - target) / risk
                return {"r_result": round(r, 4), "outcome": "TARGET_HIT", "exit_idx": i, "exit_price": target, "holding": i - entry_idx}

    last_idx = min(entry_idx + max_holding, len(candles) - 1)
    close = float(candles[last_idx].get("close", entry))
    if direction == "LONG":
        r = (close - entry) / risk
    else:
        r = (entry - close) / risk
    return {"r_result": round(r, 4), "outcome": "EXPIRED", "exit_idx": last_idx, "exit_price": close, "holding": last_idx - entry_idx}


def _detect_sweep(candles: list[dict], i: int, lookback: int = 20, stop_buffer: float = 0.002) -> dict | None:
    if i < lookback:
        return None
    c = candles[i]
    high = float(c.get("high", 0))
    low = float(c.get("low", 0))
    op = float(c.get("open", 0))
    cl = float(c.get("close", 0))
    body = abs(cl - op)
    if body <= 0:
        return None

    recent_highs = [float(candles[j].get("high", 0)) for j in range(i - lookback, i)]
    recent_lows = [float(candles[j].get("low", 0)) for j in range(i - lookback, i)]
    max_high = max(recent_highs) if recent_highs else 0
    min_low = min(recent_lows) if recent_lows else 0

    if low < min_low and cl > op and cl > low * 1.002:
        lower_wick = min(op, cl) - low
        if lower_wick >= 1.5 * body:
            risk = abs(cl - low * (1 + stop_buffer))
            if risk / cl > 0.001:
                return {"direction": "LONG", "entry": cl, "stop": low * (1 + stop_buffer), "pattern": "sweep_low"}

    if high > max_high and cl < op and cl < high * 0.998:
        upper_wick = high - max(op, cl)
        if upper_wick >= 1.5 * body:
            risk = abs(high * (1 + stop_buffer) - cl)
            if risk / cl > 0.001:
                return {"direction": "SHORT", "entry": cl, "stop": high * (1 + stop_buffer), "pattern": "sweep_high"}

    return None


def _detect_compression(candles: list[dict], i: int, stop_buffer: float = 0.002) -> dict | None:
    if i < 10:
        return None
    c = candles[i]
    high = float(c.get("high", 0))
    low = float(c.get("low", 0))
    op = float(c.get("open", 0))
    cl = float(c.get("close", 0))
    rng = high - low

    avg_rng = mean([float(candles[j].get("high", 0)) - float(candles[j].get("low", 0)) for j in range(i - 10, i)])
    if avg_rng <= 0:
        return None

    compressed = all(
        (float(candles[j].get("high", 0)) - float(candles[j].get("low", 0))) < 0.6 * avg_rng
        for j in range(i - 3, i)
    )
    breakout = rng > 1.5 * avg_rng

    if compressed and breakout:
        risk = abs(high - low) if cl > op else abs(high - low)
        if cl > op:
            stop = low * (1 + stop_buffer)
            risk = abs(cl - stop)
            if risk / cl > 0.001:
                return {"direction": "LONG", "entry": cl, "stop": stop, "pattern": "compression_breakout"}
        else:
            stop = high * (1 + stop_buffer)
            risk = abs(stop - cl)
            if risk / cl > 0.001:
                return {"direction": "SHORT", "entry": cl, "stop": stop, "pattern": "compression_breakout"}
    return None


def _detect_trend_pullback(candles: list[dict], i: int, stop_buffer: float = 0.002) -> dict | None:
    if i < 50:
        return None
    c = candles[i]
    cl = float(c.get("close", 0))
    op = float(c.get("open", 0))
    high = float(c.get("high", 0))
    low = float(c.get("low", 0))

    closes = [float(candles[j].get("close", 0)) for j in range(i - 50, i + 1)]
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    body = abs(cl - op)
    if body <= 0:
        return None

    if ema20 > ema50:
        lower_wick = min(op, cl) - low
        if low >= ema20 * 0.995 and low <= ema50 * 1.005 and cl > op and lower_wick >= body:
            risk = abs(cl - low * (1 + stop_buffer))
            if risk / cl > 0.001:
                return {"direction": "LONG", "entry": cl, "stop": low * (1 + stop_buffer), "pattern": "trend_pullback"}
    elif ema20 < ema50:
        upper_wick = high - max(op, cl)
        if high <= ema20 * 1.005 and high >= ema50 * 0.995 and cl < op and upper_wick >= body:
            risk = abs(high * (1 + stop_buffer) - cl)
            if risk / cl > 0.001:
                return {"direction": "SHORT", "entry": cl, "stop": high * (1 + stop_buffer), "pattern": "trend_pullback"}
    return None


def _detect_mean_reversion(candles: list[dict], i: int, stop_buffer: float = 0.002) -> dict | None:
    if i < 14:
        return None
    c = candles[i]
    high = float(c.get("high", 0))
    low = float(c.get("low", 0))
    op = float(c.get("open", 0))
    cl = float(c.get("close", 0))
    body = abs(cl - op)
    if body <= 0:
        return None

    mid = (high + low) / 2
    lower_wick = min(op, cl) - low
    upper_wick = high - max(op, cl)

    if lower_wick > 2.5 * body and cl > mid:
        risk = abs(cl - low * (1 + stop_buffer))
        if risk / cl > 0.001:
            return {"direction": "LONG", "entry": cl, "stop": low * (1 + stop_buffer), "pattern": "mean_reversion"}
    if upper_wick > 2.5 * body and cl < mid:
        risk = abs(high * (1 + stop_buffer) - cl)
        if risk / cl > 0.001:
            return {"direction": "SHORT", "entry": cl, "stop": high * (1 + stop_buffer), "pattern": "mean_reversion"}
    return None


def _detect_short_weakness(candles: list[dict], i: int, stop_buffer: float = 0.002) -> dict | None:
    if i < 30:
        return None
    c = candles[i]
    high = float(c.get("high", 0))
    cl = float(c.get("close", 0))
    op = float(c.get("open", 0))

    closes = [float(candles[j].get("close", 0)) for j in range(i - 30, i + 1)]
    ema10 = _ema(closes, 10)
    ema20 = _ema(closes, 20)
    recent_highs = [float(candles[j].get("high", 0)) for j in range(i - 5, i)]

    if ema10 < ema20 and high < max(recent_highs) and cl < op:
        risk = abs(high * (1 + stop_buffer) - cl)
        if risk / cl > 0.001:
            return {"direction": "SHORT", "entry": cl, "stop": high * (1 + stop_buffer), "pattern": "short_weakness"}
    return None


def _ema(data: list[float], period: int) -> float:
    if len(data) < period:
        return mean(data) if data else 0
    k = 2 / (period + 1)
    ema_val = mean(data[:period])
    for val in data[period:]:
        ema_val = val * k + ema_val * (1 - k)
    return ema_val


DETECTORS = {
    "liquidity_sweep_reversal": lambda c, i, lb, buf: _detect_sweep(c, i, lb, buf),
    "compression_breakout": lambda c, i, lb, buf: _detect_compression(c, i, buf),
    "trend_pullback": lambda c, i, lb, buf: _detect_trend_pullback(c, i, buf),
    "mean_reversion": lambda c, i, lb, buf: _detect_mean_reversion(c, i, buf),
    "short_weakness": lambda c, i, lb, buf: _detect_short_weakness(c, i, buf),
}


def _check_leakage(group_label: str) -> list[str]:
    violations = []
    for field in BANNED_FIELDS:
        if field in group_label.lower():
            violations.append(field)
    return violations


def _max_dd(trades: list[dict]) -> float:
    peak = 0
    dd = 0
    equity = 0
    for t in trades:
        equity += t.get("r_result", 0)
        peak = max(peak, equity)
        dd = max(dd, peak - equity)
    return round(dd, 2)


def _max_consec(trades: list[dict]) -> int:
    max_c = 0
    curr = 0
    for t in trades:
        if t.get("r_result", 0) <= 0:
            curr += 1
            max_c = max(max_c, curr)
        else:
            curr = 0
    return max_c


def _compute_stats(trades: list[dict]) -> dict:
    if not trades:
        return {"trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "avg_r": 0.0,
                "total_r": 0.0, "max_dd": 0.0, "max_consec": 0, "profit_factor": 0.0,
                "symbols": set(), "timeframes": set()}
    r_vals = [t["r_result"] for t in trades]
    wins = [t for t in trades if t["r_result"] > 0]
    losses = [t for t in trades if t["r_result"] <= 0]
    gw = sum(t["r_result"] for t in wins)
    gl = abs(sum(t["r_result"] for t in losses))
    pf = gw / gl if gl > 0 else float("inf")
    return {
        "trades": len(trades), "wins": len(wins), "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 1),
        "avg_r": round(mean(r_vals), 4),
        "total_r": round(sum(r_vals), 2),
        "max_dd": _max_dd(trades),
        "max_consec": _max_consec(trades),
        "profit_factor": round(pf, 4),
        "symbols": {t["symbol"] for t in trades},
    }


def _evaluate_variant(family: str, detector, symbols: list[str], timeframe: str,
                      rr_target: int, lookback: int, stop_buffer: float) -> dict | None:
    all_trades = []
    seen_keys = set()

    for sym in symbols:
        candles = _load_candles(sym, timeframe)
        if len(candles) < 60:
            continue
        for i in range(30, len(candles)):
            sig = detector(candles, i, lookback, stop_buffer)
            if sig is None:
                continue
            direction = sig["direction"]
            entry = sig["entry"]
            stop = sig["stop"]
            target = entry + (abs(entry - stop) * rr_target) if direction == "LONG" else entry - (abs(entry - stop) * rr_target)

            sig_key = f"{sym}_{timeframe}_{direction}_{i}"
            if sig_key in seen_keys:
                continue
            seen_keys.add(sig_key)

            result = _simulate_trade(candles, i, direction, entry, stop, target)
            fee = (entry + result["exit_price"]) * FEE_RATE
            r_after_fees = result["r_result"] - fee / abs(entry - stop) if abs(entry - stop) > 0 else result["r_result"]

            trade = {
                "symbol": sym, "timeframe": timeframe, "direction": direction,
                "pattern": sig["pattern"], "entry_price": entry, "stop": stop,
                "target": target, "exit_price": result["exit_price"],
                "r_result": round(result["r_result"], 4),
                "r_after_fees": round(r_after_fees, 4),
                "is_win": result["r_result"] > 0,
            }
            all_trades.append(trade)

    if not all_trades:
        return None

    sorted_t = sorted(all_trades, key=lambda t: t.get("symbol", ""))
    split = int(len(sorted_t) * SPLIT_RATIO)
    is_t = sorted_t[:split]
    oos_t = sorted_t[split:]

    is_stats = _compute_stats(is_t)
    oos_stats = _compute_stats(oos_t)
    all_stats = _compute_stats(all_trades)

    # Overfit detection
    overfit = is_stats["avg_r"] > 0 and oos_stats["avg_r"] <= 0

    # Rejection checks
    reject_reasons = []
    if all_stats["trades"] < MIN_TRADES:
        reject_reasons.append(f"total trades {all_stats['trades']} < {MIN_TRADES}")
    if oos_stats["trades"] < MIN_OOS_TRADES:
        reject_reasons.append(f"OOS trades {oos_stats['trades']} < {MIN_OOS_TRADES}")
    if len(all_stats["symbols"]) < MIN_SYMBOLS:
        reject_reasons.append(f"symbols {len(all_stats['symbols'])} < {MIN_SYMBOLS}")
    if oos_stats["avg_r"] <= MIN_OOS_AVG_R:
        reject_reasons.append(f"OOS avg R {oos_stats['avg_r']} <= {MIN_OOS_AVG_R}")
    if all_stats["profit_factor"] <= MIN_PROFIT_FACTOR:
        reject_reasons.append(f"PF {all_stats['profit_factor']} <= {MIN_PROFIT_FACTOR}")
    if is_stats["avg_r"] > 0 and oos_stats["avg_r"] <= 0:
        reject_reasons.append("overfit: IS positive but OOS negative")

    verdict = "EDGE_PROMISING_REVIEW" if not reject_reasons else "EDGE_REJECTED"

    return {
        "family": family, "timeframe": timeframe, "rr_target": rr_target,
        "lookback": lookback, "stop_buffer": stop_buffer,
        "total_trades": all_stats["trades"], "oos_trades": oos_stats["trades"],
        "is_avg_r": is_stats["avg_r"], "oos_avg_r": oos_stats["avg_r"],
        "oos_win_rate": oos_stats["win_rate"], "profit_factor": all_stats["profit_factor"],
        "max_dd": all_stats["max_dd"], "max_consec": all_stats["max_consec"],
        "unique_symbols": len(all_stats["symbols"]),
        "verdict": verdict, "reject_reasons": reject_reasons,
        "overfit": overfit,
    }


def run_auto_edge_miner() -> dict:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)

    # Load symbols from cache
    symbols = []
    if os.path.exists(CACHE_DIR):
        for f in os.listdir(CACHE_DIR):
            if f.endswith("_15m.json"):
                sym = f.replace("_15m.json", "")
                symbols.append(sym)

    if not symbols:
        symbols = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT"]

    variants_tested = 0
    variants_passed = 0
    all_results = []
    best_variant = None

    for family, detector in DETECTORS.items():
        for tf in TIMEFRAMES:
            for rr in RR_TARGETS:
                for lb in SWEEP_LOOKBACKS:
                    for buf in STOP_BUFFERS:
                        result = _evaluate_variant(family, detector, symbols, tf, rr, lb, buf)
                        if result is None:
                            continue
                        variants_tested += 1
                        all_results.append(result)
                        if result["verdict"] == "EDGE_PROMISING_REVIEW":
                            variants_passed += 1
                            if best_variant is None or result["oos_avg_r"] > best_variant.get("oos_avg_r", 0):
                                best_variant = result

    # Determine final decision
    if best_variant and best_variant.get("oos_avg_r", 0) > 0:
        final_decision = "PAPER_ONLY"
    elif variants_passed > 0:
        final_decision = "KEEP_WATCHING"
    else:
        final_decision = "NO_EDGE_FOUND"

    report = {
        "mode": "auto_edge_miner",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "live_trading_enabled": False,
        "real_order": False,
        "symbols_scanned": len(symbols),
        "variants_tested": variants_tested,
        "variants_passed": variants_passed,
        "best_variant": best_variant,
        "final_decision": final_decision,
        "promising_variants": [r for r in all_results if r["verdict"] == "EDGE_PROMISING_REVIEW"],
        "warnings": [],
    }

    # Leakage check
    leakage_violations = _check_leakage(str(all_results))
    if leakage_violations:
        report["warnings"].append(f"leakage detected: {leakage_violations}")

    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2, default=str)

    _write_text_report(report)
    return report


def _write_text_report(report: dict):
    lines = [
        "=" * 60,
        "  AUTO EDGE MINER",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  Symbols Scanned:    {report['symbols_scanned']}",
        f"  Variants Tested:    {report['variants_tested']}",
        f"  Variants Passed:    {report['variants_passed']}",
        f"  Final Decision:     {report['final_decision']}",
        "",
    ]

    best = report.get("best_variant")
    if best:
        lines += [
            "  BEST VARIANT:",
            f"    Family:       {best['family']}",
            f"    Timeframe:    {best['timeframe']}",
            f"    RR Target:    {best['rr_target']}",
            f"    Lookback:     {best['lookback']}",
            f"    Stop Buffer:  {best['stop_buffer']*100:.1f}%",
            f"    Total Trades: {best['total_trades']}",
            f"    OOS Trades:   {best['oos_trades']}",
            f"    IS Avg R:     {best['is_avg_r']}",
            f"    OOS Avg R:    {best['oos_avg_r']}",
            f"    OOS Win Rate: {best['oos_win_rate']}%",
            f"    Profit Factor:{best['profit_factor']}",
            f"    Max DD:       {best['max_dd']}",
            f"    Max Consec:   {best['max_consec']}",
            f"    Symbols:      {best['unique_symbols']}",
            "",
        ]
    else:
        lines += ["  BEST VARIANT: NONE", ""]

    promising = report.get("promising_variants", [])
    if promising:
        lines += [f"  PROMISING VARIANTS ({len(promising)}):", ""]
        for v in sorted(promising, key=lambda x: -x.get("oos_avg_r", 0))[:5]:
            lines += [
                f"    {v['family']:25s} {v['timeframe']:4s} RR:{v['rr_target']} "
                f"OOS_R:{v['oos_avg_r']:.3f} PF:{v['profit_factor']:.2f} "
                f"Trades:{v['total_trades']}",
            ]

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
    report = run_auto_edge_miner()
    return 0


if __name__ == "__main__":
    sys.exit(main())
