"""Breadwinner Fast Tournament Engine for Phase 77.

Automated strategy tournament testing multiple proven public trading archetypes.
Ranks only statistically useful strategies using walk-forward validation.

Strategy families:
A. liquidity_sweep_reversal
B. mean_reversion_extreme
C. breakout_retest
D. trend_pullback
E. funding_trap_proxy

This module NEVER places real orders, NEVER enables live trading.
"""

import json, math, os, sys
from datetime import datetime, timezone
from statistics import mean, median

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
CACHE_DIR = os.path.join(STATE_DIR, "candles_cache")
JSON_PATH = os.path.join(RESULTS_DIR, "breadwinner_fast_tournament_report.json")
TXT_PATH = os.path.join(RESULTS_DIR, "breadwinner_fast_tournament_report.txt")
CANDIDATES_PATH = os.path.join(STATE_DIR, "breadwinner_fast_tournament_candidates.jsonl")

SPLIT_RATIO = 0.7
FEE_RATE = 0.0004
BANNED_FIELDS = {"r_result", "r_after_fees", "is_win", "outcome",
                 "exit_reason", "exit_price", "max_favorable_excursion_pct",
                 "max_adverse_excursion_pct", "holding_candles"}


def _load_candles(symbol: str, timeframe: str) -> list[dict]:
    path = os.path.join(CACHE_DIR, f"{symbol}_{timeframe}.json")
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _get_symbols_for_timeframe(timeframe: str) -> list[str]:
    symbols = []
    if os.path.exists(CACHE_DIR):
        for f in os.listdir(CACHE_DIR):
            if f.endswith(f"_{timeframe}.json"):
                sym = f.replace(f"_{timeframe}.json", "")
                symbols.append(sym)
    return sorted(symbols)


def _ema(data: list[float], period: int) -> float:
    if len(data) < period:
        return mean(data) if data else 0
    k = 2 / (period + 1)
    ema_val = mean(data[:period])
    for val in data[period:]:
        ema_val = val * k + ema_val * (1 - k)
    return ema_val


def _avg_range(candles: list[dict], idx: int, lookback: int) -> float:
    if idx < lookback:
        return 0
    ranges = [float(candles[j].get("high", 0)) - float(candles[j].get("low", 0))
              for j in range(idx - lookback, idx)]
    return mean(ranges) if ranges else 0


def _avg_volume(candles: list[dict], idx: int, lookback: int) -> float:
    if idx < lookback:
        return 0
    vols = [float(candles[j].get("volume", 0)) for j in range(idx - lookback, idx)]
    return mean(vols) if vols else 0


def _simulate_trade(candles: list[dict], entry_idx: int, direction: str,
                    entry: float, stop: float, target: float,
                    max_holding: int = 120) -> dict:
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
                return {"r_result": round((target - entry) / risk, 4), "outcome": "TARGET_HIT", "exit_idx": i, "exit_price": target, "holding": i - entry_idx}
        else:
            if high >= stop:
                return {"r_result": -1.0, "outcome": "STOP_HIT", "exit_idx": i, "exit_price": stop, "holding": i - entry_idx}
            if low <= target:
                return {"r_result": round((entry - target) / risk, 4), "outcome": "TARGET_HIT", "exit_idx": i, "exit_price": target, "holding": i - entry_idx}
    last_idx = min(entry_idx + max_holding, len(candles) - 1)
    close = float(candles[last_idx].get("close", entry))
    r = ((close - entry) / risk) if direction == "LONG" else ((entry - close) / risk)
    return {"r_result": round(r, 4), "outcome": "EXPIRED", "exit_idx": last_idx, "exit_price": close, "holding": last_idx - entry_idx}


# --- STRATEGY FAMILY DETECTORS ---

def detect_liquidity_sweep(candles: list[dict], i: int, lookback: int = 20,
                           rr_target: float = 3.0) -> dict | None:
    if i < lookback + 2:
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
        if lower_wick >= 1.0 * body:
            risk = abs(cl - low * 0.998)
            if risk / cl > 0.001:
                return {"direction": "LONG", "entry": cl, "stop": low * 0.998,
                        "target": cl + risk * rr_target, "pattern": "liquidity_sweep"}
    if high > max_high and cl < op and cl < high * 0.998:
        upper_wick = high - max(op, cl)
        if upper_wick >= 1.0 * body:
            risk = abs(high * 1.002 - cl)
            if risk / cl > 0.001:
                return {"direction": "SHORT", "entry": cl, "stop": high * 1.002,
                        "target": cl - risk * rr_target, "pattern": "liquidity_sweep"}
    return None


def detect_mean_reversion_extreme(candles: list[dict], i: int,
                                  rr_target: float = 2.5) -> dict | None:
    if i < 30:
        return None
    c = candles[i]
    high = float(c.get("high", 0))
    low = float(c.get("low", 0))
    op = float(c.get("open", 0))
    cl = float(c.get("close", 0))
    body = abs(cl - op)
    if body <= 0:
        return None
    closes = [float(candles[j].get("close", 0)) for j in range(i - 20, i)]
    ema20 = _ema(closes, 20)
    deviation = abs(cl - ema20) / ema20 if ema20 > 0 else 0
    if deviation < 0.02:
        return None
    lower_wick = min(op, cl) - low
    upper_wick = high - max(op, cl)
    if lower_wick > 2.0 * body and cl > (high + low) / 2 and deviation > 0.02:
        risk = abs(cl - low * 0.998)
        if risk / cl > 0.001:
            return {"direction": "LONG", "entry": cl, "stop": low * 0.998,
                    "target": cl + risk * rr_target, "pattern": "mean_reversion_extreme"}
    if upper_wick > 2.0 * body and cl < (high + low) / 2 and deviation > 0.02:
        risk = abs(high * 1.002 - cl)
        if risk / cl > 0.001:
            return {"direction": "SHORT", "entry": cl, "stop": high * 1.002,
                    "target": cl - risk * rr_target, "pattern": "mean_reversion_extreme"}
    return None


def detect_breakout_retest(candles: list[dict], i: int,
                           rr_target: float = 3.0) -> dict | None:
    if i < 30:
        return None
    c = candles[i]
    high = float(c.get("high", 0))
    low = float(c.get("low", 0))
    op = float(c.get("open", 0))
    cl = float(c.get("close", 0))
    rng = high - low
    body = abs(cl - op)
    if body <= 0 or rng <= 0:
        return None
    avg_rng = _avg_range(candles, i, 20)
    if avg_rng <= 0:
        return None
    is_compressed = all(
        (float(candles[j].get("high", 0)) - float(candles[j].get("low", 0))) < 0.7 * avg_rng
        for j in range(i - 3, i)
    )
    is_breakout = rng > 1.3 * avg_rng
    if not (is_compressed and is_breakout):
        return None
    if i < 5:
        return None
    prev_high = max(float(candles[j].get("high", 0)) for j in range(i - 5, i))
    prev_low = min(float(candles[j].get("low", 0)) for j in range(i - 5, i))
    if cl > op and cl > prev_high:
        risk = abs(cl - prev_high * 0.998)
        if risk / cl > 0.001:
            return {"direction": "LONG", "entry": cl, "stop": prev_high * 0.998,
                    "target": cl + risk * rr_target, "pattern": "breakout_retest"}
    if cl < op and cl < prev_low:
        risk = abs(prev_low * 1.002 - cl)
        if risk / cl > 0.001:
            return {"direction": "SHORT", "entry": cl, "stop": prev_low * 1.002,
                    "target": cl - risk * rr_target, "pattern": "breakout_retest"}
    return None


def detect_trend_pullback(candles: list[dict], i: int,
                          rr_target: float = 2.5) -> dict | None:
    if i < 52:
        return None
    c = candles[i]
    cl = float(c.get("close", 0))
    op = float(c.get("open", 0))
    high = float(c.get("high", 0))
    low = float(c.get("low", 0))
    body = abs(cl - op)
    if body <= 0:
        return None
    closes = [float(candles[j].get("close", 0)) for j in range(i - 50, i + 1)]
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    if ema20 > ema50:
        lower_wick = min(op, cl) - low
        if low >= ema20 * 0.995 and low <= ema50 * 1.005 and cl > op and lower_wick >= body:
            risk = abs(cl - low * 0.998)
            if risk / cl > 0.001:
                return {"direction": "LONG", "entry": cl, "stop": low * 0.998,
                        "target": cl + risk * rr_target, "pattern": "trend_pullback"}
    if ema20 < ema50:
        upper_wick = high - max(op, cl)
        if high <= ema20 * 1.005 and high >= ema50 * 0.995 and cl < op and upper_wick >= body:
            risk = abs(high * 1.002 - cl)
            if risk / cl > 0.001:
                return {"direction": "SHORT", "entry": cl, "stop": high * 1.002,
                        "target": cl - risk * rr_target, "pattern": "trend_pullback"}
    return None


def detect_funding_trap_proxy(candles: list[dict], i: int,
                              rr_target: float = 3.0) -> dict | None:
    if i < 20:
        return None
    c = candles[i]
    high = float(c.get("high", 0))
    low = float(c.get("low", 0))
    op = float(c.get("open", 0))
    cl = float(c.get("close", 0))
    body = abs(cl - op)
    rng = high - low
    if body <= 0 or rng <= 0:
        return None
    recent_closes = [float(candles[j].get("close", 0)) for j in range(i - 10, i)]
    momentum = (cl - recent_closes[0]) / recent_closes[0] if recent_closes[0] > 0 else 0
    if abs(momentum) < 0.01:
        return None
    lower_wick = min(op, cl) - low
    upper_wick = high - max(op, cl)
    avg_rng = _avg_range(candles, i, 15)
    if avg_rng <= 0:
        return None
    if momentum > 0.01 and upper_wick > 1.5 * body and rng > avg_rng:
        risk = abs(high * 1.002 - cl)
        if risk / cl > 0.001:
            return {"direction": "SHORT", "entry": cl, "stop": high * 1.002,
                    "target": cl - risk * rr_target, "pattern": "funding_trap_proxy"}
    if momentum < -0.01 and lower_wick > 1.5 * body and rng > avg_rng:
        risk = abs(cl - low * 0.998)
        if risk / cl > 0.001:
            return {"direction": "LONG", "entry": cl, "stop": low * 0.998,
                    "target": cl + risk * rr_target, "pattern": "funding_trap_proxy"}
    return None


# --- FAMILY CONFIGURATIONS ---

FAMILY_CONFIGS = {
    "liquidity_sweep_reversal": {
        "detector": detect_liquidity_sweep,
        "timeframes": ["5m", "15m", "30m", "1h"],
        "rr_targets": [1.5, 2.0, 2.5, 3.0, 4.0],
        "lookbacks": [10, 20, 40, 80],
    },
    "mean_reversion_extreme": {
        "detector": detect_mean_reversion_extreme,
        "timeframes": ["5m", "15m", "30m"],
        "rr_targets": [1.5, 2.0, 2.5, 3.0],
        "lookbacks": [20],
    },
    "breakout_retest": {
        "detector": detect_breakout_retest,
        "timeframes": ["15m", "30m", "1h"],
        "rr_targets": [2.0, 2.5, 3.0, 4.0],
        "lookbacks": [20],
    },
    "trend_pullback": {
        "detector": detect_trend_pullback,
        "timeframes": ["15m", "30m", "1h"],
        "rr_targets": [1.5, 2.0, 2.5, 3.0],
        "lookbacks": [50],
    },
    "funding_trap_proxy": {
        "detector": detect_funding_trap_proxy,
        "timeframes": ["15m", "30m"],
        "rr_targets": [2.0, 3.0, 4.0],
        "lookbacks": [15],
    },
}


# --- STATS AND PROMOTION ---

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
        "timeframes": {t["timeframe"] for t in trades},
    }


def _check_promotion(stats: dict, is_stats: dict, oos_stats: dict) -> tuple[str, list[str]]:
    reasons = []
    reject = False
    if stats["trades"] < 300:
        reasons.append(f"total trades {stats['trades']} < 300")
        reject = True
    if oos_stats["trades"] < 100:
        reasons.append(f"OOS trades {oos_stats['trades']} < 100")
        reject = True
    if len(stats["symbols"]) < 50:
        reasons.append(f"symbols {len(stats['symbols'])} < 50")
        reject = True
    if oos_stats["avg_r"] <= 0:
        reasons.append(f"OOS avg R {oos_stats['avg_r']} <= 0")
        reject = True
    if stats["profit_factor"] <= 1.10:
        reasons.append(f"PF {stats['profit_factor']} <= 1.10")
        reject = True
    if stats["max_consec"] > 15:
        reasons.append(f"max consec {stats['max_consec']} > 15")
        reject = True
    if is_stats["avg_r"] > 0 and oos_stats["avg_r"] <= 0:
        reasons.append("overfit: IS positive but OOS negative")
        reject = True
    if reject:
        return ("OBSERVE_ONLY" if len(reasons) <= 2 else "REJECTED"), reasons
    if (oos_stats["avg_r"] >= 0.10 and oos_stats["win_rate"] >= 32.0 and
            stats["profit_factor"] >= 1.15 and stats["max_consec"] <= 12 and
            len(stats["symbols"]) >= 50):
        return "PAPER_PRIORITY", reasons
    return "PAPER_CANDIDATE", reasons


# --- MAIN TOURNAMENT ---

def _run_variant(family: str, detector, symbols: list[str], timeframe: str,
                 rr_target: float, lookback: int) -> dict | None:
    all_trades = []
    seen_keys = set()
    for sym in symbols:
        candles = _load_candles(sym, timeframe)
        if len(candles) < 60:
            continue
        max_idx = len(candles) - 1
        for i in range(lookback + 5, max_idx):
            if family == "liquidity_sweep_reversal":
                sig = detector(candles, i, lookback, rr_target)
            else:
                sig = detector(candles, i, rr_target)
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
            result = _simulate_trade(candles, i, direction, entry, stop, target, 48)
            fee = (entry + result["exit_price"]) * FEE_RATE
            r_after_fees = result["r_result"] - fee / abs(entry - stop) if abs(entry - stop) > 0 else result["r_result"]
            trade = {
                "symbol": sym, "timeframe": timeframe, "direction": direction,
                "pattern": sig["pattern"], "entry_price": entry, "stop": stop,
                "target": target, "exit_price": result["exit_price"],
                "r_result": result["r_result"], "r_after_fees": round(r_after_fees, 4),
                "is_win": result["r_result"] > 0,
            }
            all_trades.append(trade)
    if not all_trades:
        return None
    sorted_t = sorted(all_trades, key=lambda t: t.get("entry_price", 0))
    split = int(len(sorted_t) * SPLIT_RATIO)
    is_t = sorted_t[:split]
    oos_t = sorted_t[split:]
    all_stats = _compute_stats(all_trades)
    is_stats = _compute_stats(is_t)
    oos_stats = _compute_stats(oos_t)
    verdict, reasons = _check_promotion(all_stats, is_stats, oos_stats)
    return {
        "family": family, "timeframe": timeframe, "rr_target": rr_target,
        "lookback": lookback,
        "total_trades": all_stats["trades"], "oos_trades": oos_stats["trades"],
        "win_rate": all_stats["win_rate"], "avg_r": all_stats["avg_r"],
        "is_avg_r": is_stats["avg_r"], "oos_avg_r": oos_stats["avg_r"],
        "oos_win_rate": oos_stats["win_rate"],
        "profit_factor": all_stats["profit_factor"],
        "max_dd": all_stats["max_dd"], "max_consec": all_stats["max_consec"],
        "unique_symbols": len(all_stats["symbols"]),
        "verdict": verdict, "reject_reasons": reasons,
    }


def run_breadwinner_fast_tournament() -> dict:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)
    variants_tested = 0
    variants_passed = 0
    all_results = []
    best_variant = None
    for family_name, config in FAMILY_CONFIGS.items():
        detector = config["detector"]
        for tf in config["timeframes"]:
            symbols = _get_symbols_for_timeframe(tf)
            if not symbols:
                continue
            for rr in config["rr_targets"]:
                for lb in config["lookbacks"]:
                    result = _run_variant(family_name, detector, symbols, tf, rr, lb)
                    if result is None:
                        continue
                    variants_tested += 1
                    all_results.append(result)
                    if result["verdict"] in ("PAPER_CANDIDATE", "PAPER_PRIORITY"):
                        variants_passed += 1
                        if best_variant is None or result["oos_avg_r"] > best_variant.get("oos_avg_r", 0):
                            best_variant = result
    if best_variant and best_variant.get("verdict") == "PAPER_PRIORITY":
        final_decision = "PAPER_PRIORITY_FOUND"
    elif best_variant and best_variant.get("verdict") == "PAPER_CANDIDATE":
        final_decision = "PAPER_CANDIDATE_FOUND"
    else:
        final_decision = "NO_EDGE_FOUND"
    top_by_oos = sorted([r for r in all_results if r["oos_avg_r"] > 0],
                        key=lambda x: -x["oos_avg_r"])[:20]
    top_by_pf = sorted([r for r in all_results if r["profit_factor"] > 1.0],
                       key=lambda x: -x["profit_factor"])[:20]
    family_stats = {}
    for r in all_results:
        fam = r["family"]
        if fam not in family_stats:
            family_stats[fam] = {"trades": 0, "best_oos_r": 0}
        family_stats[fam]["trades"] += r["total_trades"]
        family_stats[fam]["best_oos_r"] = max(family_stats[fam]["best_oos_r"], r["oos_avg_r"])
    best_family = max(family_stats.items(), key=lambda x: x[1]["best_oos_r"])[0] if family_stats else "N/A"
    tf_stats = {}
    for r in all_results:
        tf = r["timeframe"]
        if tf not in tf_stats:
            tf_stats[tf] = {"trades": 0, "best_oos_r": 0}
        tf_stats[tf]["trades"] += r["total_trades"]
        tf_stats[tf]["best_oos_r"] = max(tf_stats[tf]["best_oos_r"], r["oos_avg_r"])
    best_tf = max(tf_stats.items(), key=lambda x: x[1]["best_oos_r"])[0] if tf_stats else "N/A"
    rr_stats = {}
    for r in all_results:
        rr = r["rr_target"]
        if rr not in rr_stats:
            rr_stats[rr] = {"trades": 0, "best_oos_r": 0}
        rr_stats[rr]["trades"] += r["total_trades"]
        rr_stats[rr]["best_oos_r"] = max(rr_stats[rr]["best_oos_r"], r["oos_avg_r"])
    best_rr = max(rr_stats.items(), key=lambda x: x[1]["best_oos_r"])[0] if rr_stats else "N/A"
    rejected_variants = [r for r in all_results if r["verdict"] == "REJECTED"]
    with open(CANDIDATES_PATH, "w") as f:
        for r in all_results:
            if r["verdict"] in ("PAPER_CANDIDATE", "PAPER_PRIORITY"):
                f.write(json.dumps(r) + "\n")
    report = {
        "mode": "breadwinner_fast_tournament",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "live_trading_enabled": False,
        "real_order": False,
        "variants_tested": variants_tested,
        "variants_passed": variants_passed,
        "best_variant": best_variant,
        "final_decision": final_decision,
        "best_family": best_family,
        "best_timeframe": best_tf,
        "best_rr": best_rr,
        "top_by_oos_avg_r": top_by_oos,
        "top_by_profit_factor": top_by_pf,
        "family_stats": family_stats,
        "timeframe_stats": tf_stats,
        "rejected_count": len(rejected_variants),
        "warnings": [],
    }
    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2, default=str)
    _write_text_report(report)
    return report


def _write_text_report(report: dict):
    lines = [
        "=" * 60,
        "  BREADWINNER FAST TOURNAMENT",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  Variants Tested:    {report['variants_tested']}",
        f"  Variants Passed:    {report['variants_passed']}",
        f"  Final Decision:     {report['final_decision']}",
        f"  Best Family:        {report['best_family']}",
        f"  Best Timeframe:     {report['best_timeframe']}",
        f"  Best RR:            {report['best_rr']}",
        "",
    ]
    best = report.get("best_variant")
    if best:
        lines += [
            "  BEST VARIANT:",
            f"    Family:       {best['family']}",
            f"    Timeframe:    {best['timeframe']}",
            f"    RR Target:    {best['rr_target']}",
            f"    Total Trades: {best['total_trades']}",
            f"    OOS Trades:   {best['oos_trades']}",
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
    top_oos = report.get("top_by_oos_avg_r", [])
    if top_oos:
        lines += [f"  TOP 20 BY OOS AVG R ({len(top_oos)}):", ""]
        for v in top_oos[:10]:
            lines.append(
                f"    {v['family'][:20]:20s} {v['timeframe']:4s} RR:{v['rr_target']} "
                f"OOS_R:{v['oos_avg_r']:.3f} PF:{v['profit_factor']:.2f} "
                f"Trades:{v['total_trades']} {v['verdict']}"
            )
    lines += [
        "",
        f"  Rejected Variants: {report['rejected_count']}",
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
    print(f"[CANDIDATES] {CANDIDATES_PATH}")


def main():
    report = run_breadwinner_fast_tournament()
    return 0


if __name__ == "__main__":
    sys.exit(main())
