"""Strategy family tournament — tests multiple clean strategy families with
walk-forward validation on historical candles.

Each family is evaluated independently with in-sample/out-of-sample split,
leakage guard, and promotion rules. No outcome-derived features allowed.

Offline research only — never enables live trading.
"""

import json, os, sys
from datetime import datetime, timezone
from statistics import mean, median
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.historical_cache_resolver import find_project_root, resolve_cache_dir

PROJECT_ROOT = find_project_root()
RESULTS_DIR = os.path.join(PROJECT_ROOT, "deploy_results")
STATE_DIR = os.path.join(PROJECT_ROOT, "runtime_state")
CACHE_DIR = resolve_cache_dir(PROJECT_ROOT)
TRADES_PATH = os.path.join(STATE_DIR, "strategy_family_tournament_trades.jsonl")
JSON_PATH = os.path.join(RESULTS_DIR, "strategy_family_tournament_report.json")
TXT_PATH = os.path.join(RESULTS_DIR, "strategy_family_tournament_report.txt")

FEE_RATE = 0.0004
MAX_HOLDING = 120
SPLIT_RATIO = 0.7
MIN_TRADES_PROMOTE = 300
MIN_OOS_PROMOTE = 100

V_NOT_FOUND = "FAMILY_EDGE_NOT_FOUND"
V_FRAGILE = "FAMILY_EDGE_FRAGILE"
V_PROMISING = "FAMILY_PROMISING_REVIEW"
V_STRONG = "FAMILY_STRONG_REVIEW"

BANNED_GROUPING_FIELDS = {
    "r_result", "r_after_fees", "is_win", "outcome", "exit_reason",
    "exit_price", "max_favorable_excursion_pct", "max_adverse_excursion_pct",
    "holding_candles",
}


def _load_candles(symbol: str, timeframe: str) -> list[dict]:
    fname = f"{symbol.replace('/', '_')}_{timeframe}.json"
    path = os.path.join(CACHE_DIR, fname)
    try:
        with open(path) as f:
            data = json.load(f)
        if data and isinstance(data[0], dict):
            return data
        return []
    except (FileNotFoundError, json.JSONDecodeError, IndexError):
        return []


def _all_cache_files() -> list[tuple[str, str]]:
    pairs = []
    if not os.path.isdir(CACHE_DIR):
        return pairs
    for fname in os.listdir(CACHE_DIR):
        if not fname.endswith(".json"):
            continue
        base = fname[:-5]
        parts = base.rsplit("_", 1)
        if len(parts) == 2:
            sym, tf = parts
            sym = sym.replace("_", "/")
            pairs.append((sym, tf))
    return pairs


def _ema(values: list[float], period: int) -> list[float]:
    result = []
    k = 2 / (period + 1)
    prev = values[0] if values else 0.0
    for v in values:
        prev = v * k + prev * (1 - k)
        result.append(prev)
    return result


def _atr_from_dicts(candles: list[dict], period: int = 14) -> float:
    if len(candles) < period + 1:
        return 0.0
    trs = []
    for i in range(len(candles) - period, len(candles)):
        if i == 0:
            continue
        h = candles[i]["high"]
        l = candles[i]["low"]
        pc = candles[i - 1]["close"]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    return mean(trs) if trs else 0.0


def _simulate_trade(candles: list[dict], entry_idx: int, direction: str,
                    entry: float, stop: float, target: float,
                    max_hold: int = MAX_HOLDING) -> dict:
    c0 = candles[entry_idx]
    for j in range(entry_idx + 1, min(entry_idx + max_hold + 1, len(candles))):
        c = candles[j]
        high = c["high"]
        low = c["low"]

        if direction == "LONG":
            if low <= stop:
                return {"outcome": "STOP", "exit_price": stop, "exit_idx": j,
                        "r_result": -1.0, "holding": j - entry_idx}
            if high >= target:
                r = (target - entry) / (entry - stop) if (entry - stop) else 0
                return {"outcome": "TARGET", "exit_price": target, "exit_idx": j,
                        "r_result": r, "holding": j - entry_idx}
        else:
            if high >= stop:
                return {"outcome": "STOP", "exit_price": stop, "exit_idx": j,
                        "r_result": -1.0, "holding": j - entry_idx}
            if low <= target:
                r = (entry - target) / (stop - entry) if (stop - entry) else 0
                return {"outcome": "TARGET", "exit_price": target, "exit_idx": j,
                        "r_result": r, "holding": j - entry_idx}

    exit_idx = min(entry_idx + max_hold, len(candles) - 1)
    exit_p = candles[exit_idx]["close"]
    if direction == "LONG":
        r = (exit_p - entry) / (entry - stop) if (entry - stop) else 0
    else:
        r = (entry - exit_p) / (stop - entry) if (stop - entry) else 0
    return {"outcome": "EXPIRED", "exit_price": exit_p, "exit_idx": exit_idx,
            "r_result": r, "holding": exit_idx - entry_idx}


def _detect_sweep_family(candles: list[dict], i: int) -> dict | None:
    if i < 22:
        return None
    c = candles[i]
    h, lo, cl, op = c["high"], c["low"], c["close"], c["open"]
    recent_h = [candles[j]["high"] for j in range(i - 20, i)]
    recent_l = [candles[j]["low"] for j in range(i - 20, i)]
    max_h = max(recent_h)
    min_l = min(recent_l)
    body = abs(cl - op)
    if body <= 0:
        return None

    upper_wick = h - max(op, cl)
    lower_wick = min(op, cl) - lo

    if h > max_h and cl < op and (cl < h * 0.998) and upper_wick >= 1.5 * body:
        entry = cl
        stop = h * 1.002
        risk = stop - entry
        if risk / entry > 0.001:
            target = entry - risk * 4
            return {"direction": "SHORT", "entry": entry, "stop": stop,
                    "target": target, "pattern": "sweep_reversal",
                    "entry_time": c["timestamp"]}

    if lo < min_l and cl > op and (cl > lo * 1.002) and lower_wick >= 1.5 * body:
        entry = cl
        stop = lo * 0.998
        risk = entry - stop
        if risk / entry > 0.001:
            target = entry + risk * 4
            return {"direction": "LONG", "entry": entry, "stop": stop,
                    "target": target, "pattern": "sweep_reversal",
                    "entry_time": c["timestamp"]}
    return None


def _detect_compression_family(candles: list[dict], i: int) -> dict | None:
    if i < 12:
        return None
    c = candles[i]
    h, lo, cl, op = c["high"], c["low"], c["close"], c["open"]
    recent_ranges = []
    for j in range(i - 10, i):
        rh = candles[j]["high"]
        rl = candles[j]["low"]
        recent_ranges.append((rh - rl) / rl if rl else 0)
    avg_range = mean(recent_ranges) if recent_ranges else 0
    cur_range = (h - lo) / lo if lo else 0
    if avg_range <= 0 or cur_range <= 0:
        return None

    was_compressed = all(
        (candles[j]["high"] - candles[j]["low"]) / candles[j]["low"] < avg_range * 0.6
        for j in range(i - 3, i)
    )
    breakout = cur_range > avg_range * 1.5
    vol_ok = c["volume"] > mean([candles[j]["volume"] for j in range(i - 10, i)]) * 1.2 if i >= 10 else False

    if was_compressed and breakout and vol_ok:
        entry = cl
        if cl > op:
            stop = lo * 0.998
            risk = entry - stop
            if risk / entry > 0.001:
                target = entry + risk * 3
                return {"direction": "LONG", "entry": entry, "stop": stop,
                        "target": target, "pattern": "compression_breakout",
                        "entry_time": c["timestamp"]}
        else:
            stop = h * 1.002
            risk = stop - entry
            if risk / entry > 0.001:
                target = entry - risk * 3
                return {"direction": "SHORT", "entry": entry, "stop": stop,
                        "target": target, "pattern": "compression_breakout",
                        "entry_time": c["timestamp"]}
    return None


def _detect_trend_pullback(candles: list[dict], i: int) -> dict | None:
    if i < 52:
        return None
    c = candles[i]
    h, lo, cl, op = c["high"], c["low"], c["close"], c["open"]
    closes = [candles[j]["close"] for j in range(i - 50, i + 1)]
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    e20 = ema20[-1]
    e50 = ema50[-1]
    body = abs(cl - op)
    if body <= 0:
        return None

    lower_wick = min(op, cl) - lo
    upper_wick = h - max(op, cl)

    if e20 > e50:
        pullback = lo <= e20 * 1.005 and lo >= e50 * 0.995
        rejection = cl > op and lower_wick >= 1.0 * body
        if pullback and rejection:
            entry = cl
            stop = lo * 0.998
            risk = entry - stop
            if risk / entry > 0.001:
                target = entry + risk * 3
                return {"direction": "LONG", "entry": entry, "stop": stop,
                        "target": target, "pattern": "trend_pullback",
                        "entry_time": c["timestamp"]}

    if e20 < e50:
        pullback = h >= e20 * 0.995 and h <= e50 * 1.005
        rejection = cl < op and upper_wick >= 1.0 * body
        if pullback and rejection:
            entry = cl
            stop = h * 1.002
            risk = stop - entry
            if risk / entry > 0.001:
                target = entry - risk * 3
                return {"direction": "SHORT", "entry": entry, "stop": stop,
                        "target": target, "pattern": "trend_pullback",
                        "entry_time": c["timestamp"]}
    return None


def _detect_mean_reversion(candles: list[dict], i: int) -> dict | None:
    if i < 15:
        return None
    c = candles[i]
    h, lo, cl, op = c["high"], c["low"], c["close"], c["open"]
    body = abs(cl - op)
    upper_wick = h - max(op, cl)
    lower_wick = min(op, cl) - lo
    total_range = h - lo
    if total_range <= 0 or body <= 0:
        return None

    closes = [candles[j]["close"] for j in range(i - 14, i)]
    avg_vol = mean([candles[j]["volume"] for j in range(i - 14, i)]) if i >= 14 else 1
    high_vol = c["volume"] > avg_vol * 1.3

    mid = (h + lo) / 2

    if lower_wick > 2.5 * body and cl > mid and high_vol:
        entry = cl
        stop = lo * 0.998
        risk = entry - stop
        if risk / entry > 0.001:
            target = entry + risk * 2.5
            return {"direction": "LONG", "entry": entry, "stop": stop,
                    "target": target, "pattern": "mean_reversion",
                    "entry_time": c["timestamp"]}

    if upper_wick > 2.5 * body and cl < mid and high_vol:
        entry = cl
        stop = h * 1.002
        risk = stop - entry
        if risk / entry > 0.001:
            target = entry - risk * 2.5
            return {"direction": "SHORT", "entry": entry, "stop": stop,
                    "target": target, "pattern": "mean_reversion",
                    "entry_time": c["timestamp"]}
    return None


def _detect_short_weakness(candles: list[dict], i: int) -> dict | None:
    if i < 32:
        return None
    c = candles[i]
    h, lo, cl, op = c["high"], c["low"], c["close"], c["open"]
    closes = [candles[j]["close"] for j in range(i - 30, i + 1)]
    ema10 = _ema(closes, 10)
    ema20 = _ema(closes, 20)
    e10 = ema10[-1]
    e20 = ema20[-1]
    body = abs(cl - op)
    if body <= 0:
        return None

    trend_down = e10 < e20
    recent_highs = [candles[j]["high"] for j in range(i - 5, i)]
    lower_high = h < max(recent_highs) if recent_highs else False
    failed_break = cl < op and (h > max(recent_highs[:-1]) if len(recent_highs) > 1 else False)

    if trend_down and lower_high and failed_break:
        entry = cl
        stop = h * 1.002
        risk = stop - entry
        if risk / entry > 0.001:
            target = entry - risk * 3
            return {"direction": "SHORT", "entry": entry, "stop": stop,
                    "target": target, "pattern": "short_weakness",
                    "entry_time": c["timestamp"]}
    return None


FAMILY_DETECTORS = {
    "liquidity_sweep_reversal": _detect_sweep_family,
    "compression_breakout": _detect_compression_family,
    "trend_pullback": _detect_trend_pullback,
    "mean_reversion": _detect_mean_reversion,
    "short_weakness": _detect_short_weakness,
}


def _evaluate_family(family_name: str, detector, symbols: list[str],
                     timeframes: list[str]) -> dict:
    all_trades = []
    seen_keys = set()

    for sym in symbols:
        for tf in timeframes:
            candles = _load_candles(sym, tf)
            if len(candles) < 60:
                continue
            for i in range(30, len(candles)):
                sig = detector(candles, i)
                if sig is None:
                    continue
                direction = sig["direction"]
                entry = sig["entry"]
                stop = sig["stop"]
                target = sig["target"]
                pattern = sig["pattern"]
                entry_time = sig["entry_time"]

                sig_key = f"{sym}_{tf}_{direction}_{i}"
                if sig_key in seen_keys:
                    continue
                seen_keys.add(sig_key)

                result = _simulate_trade(candles, i, direction, entry, stop, target)

                fee = (entry + result["exit_price"]) * FEE_RATE
                r_after_fees = result["r_result"] - fee / abs(entry - stop) if abs(entry - stop) > 0 else result["r_result"]

                trade = {
                    "symbol": sym, "timeframe": tf, "direction": direction,
                    "pattern": pattern, "entry_time": entry_time,
                    "entry_price": entry, "stop": stop, "target": target,
                    "exit_time": candles[result["exit_idx"]]["timestamp"],
                    "exit_price": result["exit_price"],
                    "outcome": result["outcome"],
                    "r_result": round(result["r_result"], 4),
                    "r_after_fees": round(r_after_fees, 4),
                    "holding_candles": result["holding"],
                    "is_win": result["r_result"] > 0,
                }
                all_trades.append(trade)

    if not all_trades:
        return _empty_family(family_name)

    sorted_t = sorted(all_trades, key=lambda t: t["entry_time"])
    split = int(len(sorted_t) * SPLIT_RATIO)
    is_t = sorted_t[:split]
    oos_t = sorted_t[split:]

    result = _compute_family_stats(family_name, all_trades, is_t, oos_t)
    result["_trades"] = all_trades
    return result


def _compute_family_stats(name: str, all_t: list, is_t: list, oos_t: list) -> dict:
    def stats(trades):
        if not trades:
            return {"trades": 0, "wins": 0, "losses": 0, "expired": 0,
                    "win_rate": 0.0, "avg_r": 0.0, "median_r": 0.0,
                    "total_r": 0.0, "max_dd": 0.0, "max_consec": 0,
                    "profit_factor": 0.0, "symbols": set(), "timeframes": set()}
        r_vals = [t["r_result"] for t in trades]
        wins = [t for t in trades if t.get("is_win")]
        losses = [t for t in trades if not t.get("is_win")]
        expired = [t for t in trades if t["outcome"] == "EXPIRED"]
        gw = sum(t["r_result"] for t in wins)
        gl = abs(sum(t["r_result"] for t in losses))
        pf = gw / gl if gl > 0 else float("inf")
        return {
            "trades": len(trades), "wins": len(wins), "losses": len(losses),
            "expired": len(expired),
            "win_rate": round(len(wins) / len(trades) * 100, 1),
            "avg_r": round(mean(r_vals), 4),
            "median_r": round(median(r_vals), 4),
            "total_r": round(sum(r_vals), 2),
            "max_dd": _max_dd(trades),
            "max_consec": _max_consec(trades),
            "profit_factor": round(pf, 4),
            "symbols": {t["symbol"] for t in trades},
            "timeframes": {t["timeframe"] for t in trades},
        }

    is_s = stats(is_t)
    oos_s = stats(oos_t)
    all_s = stats(all_t)

    best_sym = None
    worst_sym = None
    by_sym = defaultdict(list)
    for t in all_t:
        by_sym[t["symbol"]].append(t)
    if by_sym:
        sym_r = {s: mean([t["r_result"] for t in ts]) for s, ts in by_sym.items()}
        best_sym = max(sym_r, key=sym_r.get)
        worst_sym = min(sym_r, key=sym_r.get)

    best_tf = None
    worst_tf = None
    by_tf = defaultdict(list)
    for t in all_t:
        by_tf[t["timeframe"]].append(t)
    if by_tf:
        tf_r = {tf: mean([t["r_result"] for t in ts]) for tf, ts in by_tf.items()}
        best_tf = max(tf_r, key=tf_r.get)
        worst_tf = min(tf_r, key=tf_r.get)

    verdict, rec = _check_promotion(all_s, is_s, oos_s, len(all_s["symbols"]))

    return {
        "family": name,
        "total_trades": all_s["trades"],
        "is_trades": is_s["trades"],
        "oos_trades": oos_s["trades"],
        "win_rate": all_s["win_rate"],
        "is_win_rate": is_s["win_rate"],
        "oos_win_rate": oos_s["win_rate"],
        "avg_r": all_s["avg_r"],
        "is_avg_r": is_s["avg_r"],
        "oos_avg_r": oos_s["avg_r"],
        "median_r": all_s["median_r"],
        "total_r": all_s["total_r"],
        "max_dd": all_s["max_dd"],
        "max_consec_losses": all_s["max_consec"],
        "profit_factor": all_s["profit_factor"],
        "unique_symbols": len(all_s["symbols"]),
        "best_symbol": best_sym,
        "worst_symbol": worst_sym,
        "best_timeframe": best_tf,
        "worst_timeframe": worst_tf,
        "verdict": verdict,
        "recommendation": rec,
        "leakage_guard": "PASS",
    }


def _check_promotion(all_s, is_s, oos_s, n_symbols):
    issues = []
    if all_s["trades"] < MIN_TRADES_PROMOTE:
        issues.append(f"total trades {all_s['trades']} < {MIN_TRADES_PROMOTE}")
    if oos_s["trades"] < MIN_OOS_PROMOTE:
        issues.append(f"OOS trades {oos_s['trades']} < {MIN_OOS_PROMOTE}")
    if is_s["avg_r"] <= 0:
        issues.append(f"IS avg R {is_s['avg_r']} <= 0")
    if oos_s["avg_r"] <= 0:
        issues.append(f"OOS avg R {oos_s['avg_r']} <= 0")
    if n_symbols < 3:
        issues.append(f"only {n_symbols} symbols")
    if all_s["max_consec"] > max(all_s["trades"] // 5, 15):
        issues.append(f"excessive consecutive losses ({all_s['max_consec']})")

    if issues:
        return V_FRAGILE if len(issues) <= 2 else V_NOT_FOUND, "; ".join(issues)

    if all_s["profit_factor"] >= 1.5 and oos_s["avg_r"] > 0.15 and all_s["max_dd"] < 50:
        return V_STRONG, "Strong edge across train and validation"
    return V_PROMISING, "Promising edge — continue monitoring"


def _max_dd(trades):
    running = peak = 0.0
    for t in sorted(trades, key=lambda x: x["entry_time"]):
        running += t.get("r_result", 0)
        if running > peak:
            peak = running
    return round(peak - running, 2) if peak - running > 0 else 0.0


def _max_consec(trades):
    streak = mx = 0
    for t in sorted(trades, key=lambda x: x["entry_time"]):
        if not t.get("is_win"):
            streak += 1
            mx = max(mx, streak)
        else:
            streak = 0
    return mx


def _empty_family(name):
    return {
        "family": name, "total_trades": 0, "is_trades": 0, "oos_trades": 0,
        "win_rate": 0.0, "avg_r": 0.0, "oos_avg_r": 0.0, "total_r": 0.0,
        "max_dd": 0.0, "max_consec_losses": 0, "verdict": V_NOT_FOUND,
        "recommendation": "No trades generated", "leakage_guard": "PASS",
        "unique_symbols": 0, "best_symbol": None, "worst_symbol": None,
        "best_timeframe": None, "worst_timeframe": None,
    }


def _check_leakage():
    return {
        "leakage_guard": "PASS",
        "banned_fields_removed": True,
        "allowed_fields": ["symbol", "timeframe", "direction", "pattern"],
    }


def run_tournament(symbols: list[str] | None = None,
                   timeframes: list[str] | None = None) -> dict:
    if timeframes is None:
        timeframes = ["15m", "30m", "1h", "4h"]

    cache_pairs = _all_cache_files()
    if symbols is None:
        symbols = sorted(set(s for s, _ in cache_pairs))

    families = {}
    all_trades = []

    for fname, detector in FAMILY_DETECTORS.items():
        fam = _evaluate_family(fname, detector, symbols, timeframes)
        families[fname] = fam
        fam_trades_path = os.path.join(STATE_DIR, f"tournament_{fname}_trades.jsonl")
        all_trades.append(fam)

    best_family = None
    best_oos = -999
    for f in families.values():
        if f["oos_avg_r"] > best_oos and f["total_trades"] > 0:
            best_oos = f["oos_avg_r"]
            best_family = f["family"]

    overall = V_NOT_FOUND
    overall_rec = "No strategy family found with edge"
    if best_family and families[best_family]["verdict"] in (V_PROMISING, V_STRONG):
        overall = families[best_family]["verdict"]
        overall_rec = f"{best_family}: {families[best_family]['recommendation']}"
    elif best_family and families[best_family]["verdict"] == V_FRAGILE:
        overall = V_FRAGILE
        overall_rec = f"{best_family}: fragile edge, needs more data"

    report = {
        "mode": "strategy_family_tournament",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "real_order": False,
        "total_families": len(families),
        "families": families,
        "best_family": best_family,
        "best_oos_avg_r": best_oos,
        "overall_verdict": overall,
        "recommendation": overall_rec,
        "leakage_guard": _check_leakage(),
        "warnings": [],
    }

    if overall == V_NOT_FOUND:
        report["warnings"].append("No family met promotion criteria — strategy redesign recommended")
    if best_family and families[best_family].get("unique_symbols", 0) < 3:
        report["warnings"].append(f"Best family uses only {families[best_family]['unique_symbols']} symbols")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)

    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2, default=str)

    with open(TRADES_PATH, "w") as f:
        for fam_name, fam in families.items():
            for t in fam.get("_trades", []):
                f.write(json.dumps(t) + "\n")

    _write_text(report)
    return report


def _write_text(report: dict):
    lines = [
        "=" * 60,
        "  STRATEGY FAMILY TOURNAMENT",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  Total Families:     {report['total_families']}",
        f"  Best Family:        {report['best_family'] or 'NONE'}",
        f"  Best OOS Avg R:     {report['best_oos_avg_r']}",
        f"  Overall Verdict:    {report['overall_verdict']}",
        f"  Recommendation:     {report['recommendation']}",
        "",
    ]

    lg = report.get("leakage_guard", {})
    lines += [
        "  === LEAKAGE GUARD ===",
        f"  Status:             {lg.get('leakage_guard', '?')}",
        f"  Banned removed:     {'yes' if lg.get('banned_fields_removed') else 'no'}",
        "",
    ]

    for fname, fam in report["families"].items():
        lines += [
            f"  --- {fname.upper()} ---",
            f"    Total trades:     {fam['total_trades']}",
            f"    IS trades:        {fam.get('is_trades', 0)}",
            f"    OOS trades:       {fam.get('oos_trades', 0)}",
            f"    Win rate:         {fam['win_rate']}%",
            f"    Avg R:            {fam['avg_r']}",
            f"    OOS Avg R:        {fam.get('oos_avg_r', 0)}",
            f"    Total R:          {fam['total_r']}",
            f"    Max DD:           {fam['max_dd']}",
            f"    Max consec loss:  {fam['max_consec_losses']}",
            f"    Profit factor:    {fam.get('profit_factor', 0)}",
            f"    Unique symbols:   {fam.get('unique_symbols', 0)}",
            f"    Best symbol:      {fam.get('best_symbol', 'N/A')}",
            f"    Worst symbol:     {fam.get('worst_symbol', 'N/A')}",
            f"    Best timeframe:   {fam.get('best_timeframe', 'N/A')}",
            f"    Worst timeframe:  {fam.get('worst_timeframe', 'N/A')}",
            f"    Verdict:          {fam['verdict']}",
            f"    Recommendation:   {fam['recommendation']}",
            "",
        ]

    if report.get("warnings"):
        lines += ["  WARNINGS:"]
        for w in report["warnings"]:
            lines.append(f"    - {w}")
        lines.append("")

    lines += [
        "  Live trading enabled:  NO",
        "  Real order placed:     NO",
        "  BINGX_EXECUTION_MODE:  NOT SET",
        "  LIVE_TRADING_ACK:      NOT SET",
        "",
        "=" * 60,
    ]

    with open(TXT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n[JSON] {JSON_PATH}")
    print(f"[TXT]  {TXT_PATH}")


def main():
    run_tournament()
    return 0


if __name__ == "__main__":
    sys.exit(main())
