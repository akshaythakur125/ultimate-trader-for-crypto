"""Dux-style pattern playbook engine — BingX-only, RR >= 4 gate.

Detects Steven Dux-inspired crowd-trap patterns on BingX USDT perpetuals.
This is a scanner/statistics/decision-support engine only.

Usage:
    python -m production_replay.dux_pattern_engine
"""

import csv, json, math, os, sys, time
from datetime import datetime
from typing import Any, Callable

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.bingx_universe import load_universe, build_scan_universe, build_adaptive_universe, get_memecoin_symbols, get_major_symbols, is_crypto_usdt_perp
from production_replay.bingx_client import get_klines, load_credentials
from production_replay.setup_compute import compute_atr, load_candles

PARTIAL_PATH = os.path.join(os.path.join(os.path.dirname(__file__), ".."), "runtime_state", "dux_partial.json")

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
TXT_REPORT = os.path.join(RESULTS_DIR, "dux_pattern_report.txt")
JSON_REPORT = os.path.join(RESULTS_DIR, "dux_pattern_report.json")

TIMEFRAMES = ["15m", "30m", "1h"]
TIMEFRAMES_TOP = ["5m", "15m", "30m", "1h"]
TOP_N_5M = 30
RR_MIN = 4.0
MIN_STAT_TRADES = 30
MIN_STAT_EV_R = 0.30
MIN_STAT_PF = 1.5
MAX_STAT_DD_R = 10.0
MAX_STAT_CONSEC = 6
MIN_STAT_AVG_RR = 4.0
LOOKAHEAD = 96  # candles to look forward for target/stop


def _load_klines_from_api(symbol: str, tf: str) -> list[dict]:
    try:
        base = load_credentials()["base_url"]
        resp = get_klines(symbol.replace("-USDT", "-USDT"), tf, 500, base)
        if not resp["success"]:
            return []
        data = resp["data"]
        if not isinstance(data, dict) or data.get("code") != 0:
            return []
        raw = data.get("data", [])
        candles = []
        for r in raw:
            try:
                candles.append({
                    "timestamp": str(r.get("time", "")),
                    "open": float(r["open"]), "high": float(r["high"]),
                    "low": float(r["low"]), "close": float(r["close"]),
                    "volume": float(r.get("volume", 0)),
                })
            except (KeyError, ValueError, TypeError):
                continue
        return candles
    except Exception:
        return []


def _load_candles(symbol: str, tf: str) -> list[dict]:
    bingx_sym = symbol.replace("-USDT", "USDT")
    try:
        candles = load_candles(bingx_sym, tf)
        if candles:
            return candles
    except Exception:
        pass
    return _load_klines_from_api(symbol, tf)


def _simulate_trade_outcome(
    candles: list[dict], idx: int, direction: str, entry: float, stop: float,
    target2: float, lookahead: int = LOOKAHEAD,
) -> tuple[float, float, float, float]:
    risk = abs(entry - stop)
    if risk <= 0 or idx >= len(candles) - 1:
        return (0.0, 0.0, 0.0, 0.0)
    rr_1_target = entry + risk * 1.0 if direction == "LONG" else entry - risk * 1.0
    rr_2_target = target2
    for j in range(idx + 1, min(idx + lookahead + 1, len(candles))):
        c = candles[j]
        if direction == "LONG":
            if c["low"] <= stop:
                return (-1.0, 1.0, c["timestamp"], stop)
            if c["high"] >= rr_2_target:
                realized_rr = abs(rr_2_target - entry) / max(risk, 1e-10)
                return (realized_rr, realized_rr, c["timestamp"], rr_2_target)
            if c["high"] >= rr_1_target:
                return (1.0, 1.0, c["timestamp"], rr_1_target)
        else:
            if c["high"] >= stop:
                return (-1.0, 1.0, c["timestamp"], stop)
            if c["low"] <= rr_2_target:
                realized_rr = abs(rr_2_target - entry) / max(risk, 1e-10)
                return (realized_rr, realized_rr, c["timestamp"], rr_2_target)
            if c["low"] <= rr_1_target:
                return (1.0, 1.0, c["timestamp"], rr_1_target)
    return (0.0, 0.0, None, None)


def _compute_rr(entry: float, stop: float, target: float) -> float:
    risk = abs(entry - stop)
    if risk <= 0:
        return 0.0
    return round(abs(target - entry) / risk, 2)


def _compute_setup(symbol: str, tf: str, direction: str, entry: float, stop_price: float,
                   atr_val: float, pump_high: float = 0, flush_low: float = 0) -> dict:
    risk = abs(entry - stop_price)
    if risk <= 0 or atr_val <= 0:
        return {"rr_1": None, "rr_2": None, "entry": entry, "stop": stop_price,
                "target_1": None, "target_2": None, "rejected": True, "reason": "invalid risk"}
    target_2_dist = risk * RR_MIN
    if direction == "LONG":
        target_1 = round(entry + risk * 1.0, 2)
        target_2 = round(entry + target_2_dist, 2)
    else:
        target_1 = round(entry - risk * 1.0, 2)
        target_2 = round(entry - target_2_dist, 2)
    rr_1 = round(abs(target_1 - entry) / risk, 2)
    rr_2 = round(abs(target_2 - entry) / risk, 2)
    if rr_2 < RR_MIN:
        return {"rr_1": rr_1, "rr_2": rr_2, "entry": entry, "stop": stop_price,
                "target_1": target_1, "target_2": target_2,
                "rejected": True, "reason": f"RR {rr_2} < {RR_MIN}"}
    return {"rr_1": rr_1, "rr_2": rr_2, "entry": entry, "stop": stop_price,
            "target_1": target_1, "target_2": target_2,
            "rejected": False, "reason": ""}


def _backtest_pattern(
    candles: list[dict], pattern_id: str, direction: str,
    detect_fn: Callable,
) -> tuple[list[dict], dict]:
    signals = []
    step = max(1, len(candles) // 200)
    for i in range(50, len(candles) - 10, step):
        for j in range(i, min(i + step, len(candles) - 10)):
            result = detect_fn(candles, j)
            if result and result.get("detected"):
                entry = result["entry"]
                stop_price = result["stop"]
                atr_val = result.get("atr", compute_atr(candles[j - 14:j + 1]))
                setup = _compute_setup("", "", direction, entry, stop_price, atr_val)
                if not setup["rejected"]:
                    outcome, rr_real, ts, exit_price = _simulate_trade_outcome(
                        candles, j, direction, entry, stop_price, setup["target_2"],
                    )
                    signals.append({
                        "outcome_r": outcome, "rr_realized": rr_real,
                        "entry": entry, "stop": stop_price,
                        "t1": setup["target_1"], "t2": setup["target_2"],
                        "rr_1": setup["rr_1"], "rr_2": setup["rr_2"],
                        "timestamp": ts, "exit_price": exit_price,
                    })
                break
    stats = _compute_stats(signals)
    return signals, stats


def _compute_stats(signals: list[dict]) -> dict:
    n = len(signals)
    if n == 0:
        return {"trades": 0, "win_rate": 0.0, "ev_r": 0.0, "profit_factor": 0.0,
                "max_drawdown_r": 0.0, "max_consecutive_losses": 0, "avg_rr": 0.0,
                "median_r": 0.0, "recent_30d_ev_r": 0.0}
    wins = [s for s in signals if s["outcome_r"] > 0]
    losses = [s for s in signals if s["outcome_r"] < 0]
    ev_r = sum(s["outcome_r"] for s in signals) / n
    wr = len(wins) / n
    gp = sum(s["outcome_r"] for s in wins)
    gl = abs(sum(s["outcome_r"] for s in losses)) if losses else 1e-10
    pf = gp / gl
    avg_rr = sum(s["rr_realized"] for s in signals) / n
    sorted_r = sorted(s["outcome_r"] for s in signals)
    median_r = sorted_r[n // 2] if n > 0 else 0.0
    consec = 0
    max_consec = 0
    for s in signals:
        if s["outcome_r"] < 0:
            consec += 1
            max_consec = max(max_consec, consec)
        else:
            consec = 0
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for s in signals:
        equity += s["outcome_r"]
        if equity > peak:
            peak = equity
        max_dd = max(max_dd, peak - equity)
    recent = signals[-max(n // 3, 1):]
    recent_ev = sum(s["outcome_r"] for s in recent) / len(recent)
    return {
        "trades": n, "win_rate": round(wr, 4), "ev_r": round(ev_r, 4),
        "profit_factor": round(pf, 4), "max_drawdown_r": round(max_dd, 2),
        "max_consecutive_losses": max_consec, "avg_rr": round(avg_rr, 4),
        "median_r": round(median_r, 4), "recent_30d_ev_r": round(recent_ev, 4),
    }


def _stat_verdict(stats: dict) -> str:
    if stats["trades"] == 0:
        return "REJECT"
    if stats["trades"] >= MIN_STAT_TRADES and stats["ev_r"] > MIN_STAT_EV_R and \
       stats["profit_factor"] >= MIN_STAT_PF and stats["max_drawdown_r"] <= MAX_STAT_DD_R and \
       stats["max_consecutive_losses"] <= MAX_STAT_CONSEC and stats["avg_rr"] >= MIN_STAT_AVG_RR and \
       stats["recent_30d_ev_r"] > 0:
        return "PASS"
    if stats["trades"] >= 10 and stats["ev_r"] > 0:
        return "WATCH"
    return "REJECT"


def _detect_pump_fade(candles: list[dict], idx: int) -> dict | None:
    n = len(candles)
    if idx < 25 or idx >= n - 5:
        return None
    lookback = 20
    window = candles[max(0, idx - lookback):idx + 1]
    if len(window) < 15:
        return None
    start_close = window[0]["close"]
    end_close = window[-1]["close"]
    pump_pct = (end_close - start_close) / start_close * 100 if start_close > 0 else 0
    if pump_pct < 3.0:
        return None
    vol_start = sum(c["volume"] for c in window[:5])
    vol_end = sum(c["volume"] for c in window[-5:])
    vol_expansion = vol_end > vol_start * 1.3 if vol_start > 0 else False
    if not vol_expansion:
        return None
    last = candles[idx]
    body = abs(last["close"] - last["open"])
    wick = last["high"] - max(last["open"], last["close"]) if last["close"] > last["open"] else \
           min(last["open"], last["close"]) - last["low"]
    total_range = last["high"] - last["low"]
    wick_pct = wick / total_range * 100 if total_range > 0 else 0
    if wick_pct < 40:
        closes_after = [candles[j]["close"] for j in range(idx + 1, min(idx + 4, n))]
        if not closes_after or closes_after[-1] > last["close"]:
            return None
    pump_high = max(c["high"] for c in window)
    atr_val = compute_atr(candles[max(0, idx - 14):idx + 1])
    entry = round(last["close"], 2)
    stop = round(pump_high + atr_val * 0.5, 2)
    return {"detected": True, "direction": "SHORT", "entry": entry, "stop": stop,
            "atr": atr_val, "pump_pct": round(pump_pct, 1), "wick_pct": round(wick_pct, 1),
            "vol_expansion": vol_expansion, "pump_high": pump_high,
            "reason": f"pump {pump_pct:.1f}% wick {wick_pct:.0f}%"}


def _detect_failed_breakout(candles: list[dict], idx: int) -> dict | None:
    n = len(candles)
    if idx < 25 or idx >= n - 5:
        return None
    lookback = 15
    window = candles[max(0, idx - lookback):idx + 1]
    if len(window) < 12:
        return None
    range_high = max(c["high"] for c in window[:-1])
    range_low = min(c["low"] for c in window[:-1])
    rng = range_high - range_low
    if rng <= 0:
        return None
    last = candles[idx]
    direction = None
    if last["high"] > range_high and last["close"] < range_high:
        direction = "SHORT"
    elif last["low"] < range_low and last["close"] > range_low:
        direction = "LONG"
    if direction is None:
        return None
    atr_val = compute_atr(candles[max(0, idx - 14):idx + 1])
    entry = round(last["close"], 2)
    stop = round(range_high + atr_val * 0.5, 2) if direction == "SHORT" else \
           round(range_low - atr_val * 0.5, 2)
    return {"detected": True, "direction": direction, "entry": entry, "stop": stop,
            "atr": atr_val, "range_high": range_high, "range_low": range_low,
            "reason": f"failed {direction} breakout"}


def _detect_first_breakdown(candles: list[dict], idx: int) -> dict | None:
    n = len(candles)
    if idx < 30 or idx >= n - 5:
        return None
    pump_window = candles[max(0, idx - 20):idx - 5]
    if len(pump_window) < 10:
        return None
    pump_start = pump_window[0]["close"]
    pump_end = pump_window[-1]["close"]
    pump_pct = (pump_end - pump_start) / pump_start * 100 if pump_start > 0 else 0
    if pump_pct < 3.0:
        return None
    low_before = min(c["low"] for c in pump_window)
    low_now = min(c["low"] for c in candles[idx - 5:idx + 1])
    if low_now >= low_before:
        return None
    recent = candles[idx - 5:idx + 1]
    bounce_high = max(c["high"] for c in recent)
    atr_val = compute_atr(candles[max(0, idx - 14):idx + 1])
    entry = round(candles[idx]["close"], 2)
    stop = round(bounce_high + atr_val * 0.5, 2)
    return {"detected": True, "direction": "SHORT", "entry": entry, "stop": stop,
            "atr": atr_val, "pump_pct": round(pump_pct, 1),
            "reason": "first breakdown after pump"}


def _detect_panic_flush(candles: list[dict], idx: int) -> dict | None:
    n = len(candles)
    if idx < 20 or idx >= n - 5:
        return None
    last = candles[idx]
    body = abs(last["close"] - last["open"])
    total_range = last["high"] - last["low"]
    lower_wick = min(last["open"], last["close"]) - last["low"]
    wick_pct = lower_wick / total_range * 100 if total_range > 0 else 0
    if wick_pct < 50:
        return None
    breakdown_level = min(last["open"], last["close"]) + body * 0.3
    if last["close"] <= breakdown_level:
        return None
    range_before = candles[max(0, idx - 10):idx]
    range_high = max(c["high"] for c in range_before) if range_before else last["high"]
    atr_val = compute_atr(candles[max(0, idx - 14):idx + 1])
    entry = round(last["close"], 2)
    stop = round(last["low"] - atr_val * 0.3, 2)
    return {"detected": True, "direction": "LONG", "entry": entry, "stop": stop,
            "atr": atr_val, "flush_low": last["low"], "wick_pct": round(wick_pct, 1),
            "reason": f"panic flush wick {wick_pct:.0f}%"}


def _detect_weak_bounce(candles: list[dict], idx: int) -> dict | None:
    n = len(candles)
    if idx < 30 or idx >= n - 5:
        return None
    pump_window = candles[max(0, idx - 25):idx - 10]
    if len(pump_window) < 8:
        return None
    pump_high = max(c["high"] for c in pump_window)
    last = candles[idx]
    if last["close"] > pump_high * 0.8:
        return None
    recent = candles[idx - 5:idx + 1]
    bounce_high = max(c["high"] for c in recent)
    vol_before = sum(c["volume"] for c in pump_window[-5:]) if len(pump_window) >= 5 else 1
    vol_now = sum(c["volume"] for c in recent)
    weak_volume = vol_now < vol_before * 0.7
    if not weak_volume:
        return None
    atr_val = compute_atr(candles[max(0, idx - 14):idx + 1])
    entry = round(last["close"], 2)
    stop = round(bounce_high + atr_val * 0.5, 2)
    return {"detected": True, "direction": "SHORT", "entry": entry, "stop": stop,
            "atr": atr_val, "bounce_high": bounce_high,
            "reason": "weak bounce after pump crack"}


def _detect_crowd_trap(candles: list[dict], idx: int) -> dict | None:
    n = len(candles)
    if idx < 25 or idx >= n - 5:
        return None
    window = candles[max(0, idx - 20):idx + 1]
    if len(window) < 15:
        return None
    closes = [c["close"] for c in window]
    avg = sum(closes) / len(closes)
    last = candles[idx]
    stdev = math.sqrt(sum((c - avg) ** 2 for c in closes) / len(closes)) if len(closes) > 1 else 0
    if stdev <= 0:
        return None
    z = (last["close"] - avg) / stdev
    direction = None
    if z > 1.5:
        direction = "SHORT"
    elif z < -1.5:
        direction = "LONG"
    if direction is None:
        return None
    atr_val = compute_atr(candles[max(0, idx - 14):idx + 1])
    entry = round(last["close"], 2)
    range_high = max(c["high"] for c in window)
    range_low = min(c["low"] for c in window)
    stop = round(range_high + atr_val * 0.5, 2) if direction == "SHORT" else \
           round(range_low - atr_val * 0.5, 2)
    return {"detected": True, "direction": direction, "entry": entry, "stop": stop,
            "atr": atr_val, "funding_evidence": "UNKNOWN",
            "oi_evidence": "UNKNOWN", "z_score": round(z, 2),
            "reason": f"crowd trap z={z:.1f}"}


PATTERN_DETECTORS = [
    ("parabolic_pump_fade", "Parabolic Pump Fade", "SHORT", _detect_pump_fade),
    ("failed_breakout_trap", "Failed Breakout Trap", None, _detect_failed_breakout),
    ("first_breakdown_after_pump", "First Breakdown After Pump", "SHORT", _detect_first_breakdown),
    ("panic_flush_reclaim", "Panic Flush Reclaim", "LONG", _detect_panic_flush),
    ("weak_bounce_short", "Weak Bounce Short", "SHORT", _detect_weak_bounce),
    ("crowd_trap", "Funding/OI Crowd Trap", None, _detect_crowd_trap),
]


def scan_symbol(symbol: str, tf: str) -> list[dict]:
    try:
        candles = _load_candles(symbol, tf)
        if len(candles) < 50:
            return []
        results = []
        for pid, pname, default_dir, detect_fn in PATTERN_DETECTORS:
            atr_val = compute_atr(candles[-20:])
            if atr_val <= 0:
                continue
            direction = default_dir
            result = detect_fn(candles, len(candles) - 1)
            if result and result.get("detected"):
                direction = result["direction"]
                setup = _compute_setup(symbol, tf, direction, result["entry"], result["stop"], atr_val)
                stats_signals, stats = _backtest_pattern(candles, pid, direction, detect_fn)
                verdict = _stat_verdict(stats)
                results.append({
                    "symbol": symbol, "timeframe": tf,
                    "pattern_id": pid, "pattern_name": pname,
                    "direction": direction,
                    "entry": setup["entry"], "stop": setup["stop"],
                    "target_1": setup["target_1"], "target_2": setup["target_2"],
                    "rr_1": setup["rr_1"], "rr_2": setup["rr_2"],
                    "rr_gate": "PASS" if not setup["rejected"] else "FAIL",
                    "setup_quality": "A" if (not setup["rejected"] and stats["ev_r"] > MIN_STAT_EV_R) else "B" if not setup["rejected"] else "REJECT",
                    "rejected": setup["rejected"],
                    "reject_reason": setup.get("reason", ""),
                    "pump_pct": result.get("pump_pct"),
                    "wick_pct": result.get("wick_pct"),
                    "vol_expansion": result.get("vol_expansion"),
                    "funding_evidence": result.get("funding_evidence", "UNKNOWN"),
                    "oi_evidence": result.get("oi_evidence", "UNKNOWN"),
                    "stats": stats,
                    "verdict": verdict,
                })
            else:
                results.append({
                    "symbol": symbol, "timeframe": tf,
                    "pattern_id": pid, "pattern_name": pname,
                    "direction": "UNKNOWN", "rejected": True,
                    "reject_reason": "pattern not detected",
                    "rr_gate": "FAIL",
                    "setup_quality": "REJECT",
                    "stats": _compute_stats([]),
                    "verdict": "REJECT",
                })
        return results
    except Exception:
        return []


def _get_timeframes_for_symbol(symbol: str, adaptive: dict) -> list[str]:
    """Return tier-specific timeframes for a symbol."""
    for tier_key in ("tier_a", "tier_b", "tier_c"):
        tier = adaptive.get(tier_key, {})
        if symbol in tier.get("symbols", []):
            return tier.get("timeframes", ["30m", "1h"])
    return ["30m", "1h"]


def run_dux_engine() -> dict:
    print("=" * 60)
    print("  DUX PATTERN PLAYBOOK ENGINE")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    start_ts = time.time()
    universe_result = load_universe()
    contracts = universe_result["contracts"]
    source = universe_result["source"]
    print(f"\n  BingX universe loaded: {'YES' if source == 'api' else 'NO (fallback)'}")
    print(f"  Source: {source}")
    print(f"  Total raw contracts: {universe_result.get('total_raw', 0)}")
    print(f"  Active USDT perps:   {universe_result.get('active_usdt', len(contracts))}")

    adaptive = build_adaptive_universe(contracts)
    tier_a = adaptive.get("tier_a", {})
    tier_b = adaptive.get("tier_b", {})
    tier_c = adaptive.get("tier_c", {})
    scan_symbols = adaptive["symbols"]
    total_symbols = len(scan_symbols)
    memecoins = adaptive["memecoins"]
    majors = adaptive["majors"]

    print(f"  Adaptive scan universe: {total_symbols} symbols")
    print(f"    Tier A (5m/15m/30m/1h): {tier_a.get('size', 0)}")
    print(f"    Tier B (15m/30m/1h):    {tier_b.get('size', 0)}")
    print(f"    Tier C (30m/1h):         {tier_c.get('size', 0)}")
    print(f"  Memecoin candidates: {len(memecoins)}")
    print(f"  Major controls:      {len(majors)}")
    print(f"  Scanning {total_symbols} symbols...")

    all_results = []
    skipped_symbols = []
    failed_symbols = []
    scanned_st = 0
    total_st = 0
    api_errors = 0
    MAX_API_ERRORS = 50
    MAX_RUNTIME_SECONDS = 600

    os.makedirs(os.path.dirname(PARTIAL_PATH), exist_ok=True)

    for i, sym in enumerate(scan_symbols):
        if time.time() - start_ts > MAX_RUNTIME_SECONDS:
            print(f"\n  [guard] Runtime limit {MAX_RUNTIME_SECONDS}s reached, saving partial scan at symbol {i}/{total_symbols}")
            break
        if api_errors >= MAX_API_ERRORS:
            print(f"\n  [guard] API error limit {MAX_API_ERRORS} reached, stopping scan")
            break

        if not is_crypto_usdt_perp(sym):
            continue
        tfs = _get_timeframes_for_symbol(sym, adaptive)
        symbol_had_results = False
        symbol_had_error = False
        for tf in tfs:
            total_st += 1
            try:
                results = scan_symbol(sym, tf)
                if results:
                    scanned_st += 1
                    all_results.extend(results)
                    symbol_had_results = True
            except Exception:
                api_errors += 1
                symbol_had_error = True
                continue
        if symbol_had_error:
            failed_symbols.append(sym)
        elif not symbol_had_results:
            skipped_symbols.append(sym)

        if (i + 1) % 25 == 0 or i == total_symbols - 1:
            elapsed = time.time() - start_ts
            print(f"  [scan] {i + 1}/{total_symbols} symbols, {scanned_st}/{total_st} sym-tf, "
                  f"{len(all_results)} patterns, {len(failed_symbols)} failed, {elapsed:.0f}s")

        # Save partial every 50 symbols
        if (i + 1) % 50 == 0:
            partial = {
                "mode": "dux_partial",
                "timestamp": datetime.now().isoformat(),
                "symbols_attempted": i + 1,
                "total_symbols": total_symbols,
                "symbol_timeframes_scanned": scanned_st,
                "total_patterns_scanned": len(all_results),
                "failed_symbols": failed_symbols,
                "skipped_symbols": skipped_symbols,
                "scan_duration_seconds": int(time.time() - start_ts),
            }
            try:
                with open(PARTIAL_PATH, "w") as f:
                    json.dump(partial, f, indent=2)
            except Exception:
                pass

    scan_duration = int(time.time() - start_ts)
    print(f"\n  Scan complete: {total_symbols} symbols, {scanned_st} sym-tf, "
          f"{len(all_results)} patterns, {len(failed_symbols)} failed, {scan_duration}s")

    passing = [r for r in all_results if not r["rejected"] and r["verdict"] in ("PASS", "WATCH")]
    rr_pass = [r for r in all_results if not r["rejected"]]
    best_candidate = None
    if passing:
        passing.sort(key=lambda r: r.get("rr_2") or 0, reverse=True)
        best_candidate = passing[0]
    elif rr_pass:
        rr_pass.sort(key=lambda r: r.get("rr_2") or 0, reverse=True)
        best_candidate = rr_pass[0]

    # Final decision
    if not rr_pass:
        final_decision = "DO_NOT_TRADE"
        reason = f"no candidate passes RR >= 4 gate ({len(all_results)} patterns scanned)"
    elif best_candidate and best_candidate["verdict"] == "PASS":
        final_decision = "MANUAL_REVIEW_ONLY"
        reason = f"best: {best_candidate['pattern_name']} {best_candidate['symbol']} RR {best_candidate['rr_2']}"
    elif best_candidate:
        final_decision = "WATCH"
        reason = f"best: {best_candidate['pattern_name']} {best_candidate['symbol']} RR {best_candidate['rr_2']}, stats insufficient"
    else:
        final_decision = "DO_NOT_TRADE"
        reason = "no viable candidate"

    report = {
        "mode": "dux_pattern_engine", "research_only": True,
        "live_trading_enabled": False, "paper_trading_enabled": False,
        "timestamp": datetime.now().isoformat(),
        "bingx_universe_loaded": source == "api",
        "bingx_universe_source": source,
        "total_raw_contracts": universe_result.get("total_raw", 0),
        "active_usdt_perps": universe_result.get("active_usdt", len(contracts)),
        "dux_scan_universe_size": total_symbols,
        "symbols_scanned": total_symbols,
        "symbol_timeframes_scanned": scanned_st,
        "symbol_timeframes_attempted": total_st,
        "total_patterns_scanned": len(all_results),
        "memecoin_candidates": len(memecoins),
        "major_controls": len(majors),
        "tier_a_size": tier_a.get("size", 0),
        "tier_b_size": tier_b.get("size", 0),
        "tier_c_size": tier_c.get("size", 0),
        "failed_symbols": failed_symbols,
        "failed_symbol_count": len(failed_symbols),
        "skipped_symbols": skipped_symbols,
        "skipped_symbol_count": len(skipped_symbols),
        "api_error_count": api_errors,
        "scan_duration_seconds": scan_duration,
        "rr_gate_pass": len(rr_pass),
        "stats_pass": len(passing),
        "best_candidate": {
            k: best_candidate[k] for k in ("symbol", "timeframe", "pattern_name",
                "direction", "entry", "stop", "target_1", "target_2",
                "rr_1", "rr_2", "stats", "verdict")
        } if best_candidate else None,
        "final_decision": final_decision,
        "reason": reason,
        "top_five": [
            {k: r[k] for k in ("symbol", "timeframe", "pattern_name", "direction",
                               "rr_1", "rr_2", "verdict")}
            for r in sorted(all_results, key=lambda r: r.get("rr_2") or 0, reverse=True)[:5]
            if not r["rejected"]
        ],
        "patterns": all_results,
    }

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(JSON_REPORT, "w") as f:
        json.dump(report, f, indent=2)

    # Remove partial file on success
    try:
        if os.path.exists(PARTIAL_PATH):
            os.remove(PARTIAL_PATH)
    except Exception:
        pass

    _write_text_report(report, all_results, best_candidate, final_decision, reason)
    return report


def _write_text_report(report: dict, results: list, best: dict | None,
                        decision: str, reason: str):
    lines = [
        "=" * 60,
        "  DUX PATTERN PLAYBOOK ENGINE — REPORT",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  BingX universe loaded: {'YES' if report['bingx_universe_loaded'] else 'NO'}",
        f"  Total raw contracts:   {report['total_raw_contracts']}",
        f"  Active USDT perps:     {report['active_usdt_perps']}",
        f"  Scan universe:         {report['dux_scan_universe_size']}",
        f"  Tier A (5m/15m/30m/1h): {report.get('tier_a_size', 0)}",
        f"  Tier B (15m/30m/1h):    {report.get('tier_b_size', 0)}",
        f"  Tier C (30m/1h):         {report.get('tier_c_size', 0)}",
        f"  Memecoin candidates:   {report['memecoin_candidates']}",
        f"  Major controls:        {report['major_controls']}",
        "",
        f"  Symbol-timeframes attempted: {report.get('symbol_timeframes_attempted', 0)}",
        f"  Symbol-timeframes completed:  {report['symbol_timeframes_scanned']}",
        f"  Total patterns scanned:       {report['total_patterns_scanned']}",
        f"  Failed symbols:               {report.get('failed_symbol_count', 0)}",
        f"  Skipped symbols:              {report.get('skipped_symbol_count', 0)}",
        f"  API errors:                   {report.get('api_error_count', 0)}",
        f"  Scan duration (seconds):      {report.get('scan_duration_seconds', 0)}",
        f"  RR >= 4 gate PASS:            {report['rr_gate_pass']}",
        f"  Stats PASS:                   {report['stats_pass']}",
        "",
    ]

    if best:
        lines += [
            "  BEST CANDIDATE:",
            f"    Pattern:  {best['pattern_name']} on {best['symbol']} {best['timeframe']}",
            f"    Direction: {best['direction']}",
            f"    Entry:    {best['entry']}  Stop: {best['stop']}",
            f"    Target 1: {best['target_1']}  (RR 1:{best['rr_1']})",
            f"    Target 2: {best['target_2']}  (RR 1:{best['rr_2']})",
            f"    Stats:    {best['stats']['trades']} trades, EV {best['stats']['ev_r']}R, PF {best['stats']['profit_factor']}",
            f"    Verdict:  {best['verdict']}",
            "",
        ]
    else:
        lines += ["  BEST CANDIDATE: NONE", ""]

    # Top candidates table
    top5 = report.get("top_five", [])
    if top5:
        lines += ["  TOP CANDIDATES (RR gate PASS):", ""]
        lines.append("  {:<15s} {:<6s} {:<25s} {:<7s} {:<6s} {:<6s} {:<8s}".format(
            "Symbol", "TF", "Pattern", "Dir", "RR T1", "RR T2", "Verdict"))
        lines.append("  " + "-" * 73)
        for r in top5:
            lines.append("  {:<15s} {:<6s} {:<25s} {:<7s} {:<6s} {:<6s} {:<8s}".format(
                r["symbol"], r["timeframe"], r["pattern_name"][:25],
                r["direction"], str(r["rr_1"] or "N/A"), str(r["rr_2"] or "N/A"),
                r["verdict"]))
        lines.append("")

    lines += [
        f"  FINAL DECISION: {decision}",
        f"  REASON: {reason}",
        "",
        "  WARNING: This system is not approved for live trading.",
        "  Manual trading is at user's own risk.",
        "",
        "=" * 60,
    ]

    with open(TXT_REPORT, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n[JSON] {JSON_REPORT}")
    print(f"[TXT]  {TXT_REPORT}")


def main():
    report = run_dux_engine()
    return 0


if __name__ == "__main__":
    sys.exit(main())
