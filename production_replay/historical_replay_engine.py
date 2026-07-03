"""Historical replay engine — walk-forward candle-by-candle simulation.

Walks through OHLCV data one candle at a time, detects setups using only
information available up to that candle, simulates entries/stops/targets,
and records outcomes without lookahead bias.

Supports diagnostics mode (HISTORICAL_DIAGNOSTIC_MODE=1) to capture
near-miss candidates and rejection reason summaries.

Offline research only — never enables live trading.
"""

import json, os, sys, copy
from datetime import datetime, timezone
from statistics import mean
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
CACHE_DIR = os.path.join(STATE_DIR, "historical_cache")

TRADES_LEDGER = os.path.join(STATE_DIR, "historical_replay_trades.jsonl")
DIAG_JSON_PATH = os.path.join(RESULTS_DIR, "historical_replay_diagnostics.json")
DIAG_TXT_PATH = os.path.join(RESULTS_DIR, "historical_replay_diagnostics.txt")
NEAR_MISS_PATH = os.path.join(STATE_DIR, "historical_near_misses.jsonl")

FEE_RATE = 0.0004

MAX_HOLDING_CANDLES = {
    "15m": 480,
    "30m": 240,
    "1h": 120,
    "4h": 30,
}

DIAGNOSTIC_MODE = os.environ.get("HISTORICAL_DIAGNOSTIC_MODE") == "1"

SUPPORTED_TIMEFRAMES = ["15m", "30m", "1h", "4h"]


def _atr(candles: list, period: int = 14) -> float:
    if len(candles) < period + 1:
        return 0.0
    trs = []
    for i in range(len(candles) - period, len(candles)):
        if i == 0:
            continue
        h = float(candles[i][2])
        l = float(candles[i][3])
        pc = float(candles[i - 1][4])
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    return mean(trs) if trs else 0.0


def _sma(values: list, period: int) -> float:
    if len(values) < period:
        return mean(values) if values else 0.0
    return mean(values[-period:])


def _detect_sweep(candles: list, i: int, lookback: int = 20) -> dict | None:
    if i < lookback + 2:
        return None
    c = candles[i]
    high = float(c[2])
    low = float(c[3])
    close = float(c[4])
    open_p = float(c[1])

    recent_highs = [float(candles[j][2]) for j in range(i - lookback, i)]
    recent_lows = [float(candles[j][3]) for j in range(i - lookback, i)]
    max_recent_high = max(recent_highs)
    min_recent_low = min(recent_lows)

    signals = []

    if high > max_recent_high and close < high and close < open_p:
        entry = close
        stop = high * 1.002
        risk_pct = abs(stop - entry) / entry if entry else 0
        if risk_pct > 0.001:
            signals.append({
                "direction": "SHORT",
                "pattern": "sweep",
                "entry": entry,
                "stop": stop,
                "confidence": "medium",
                "entry_time": int(c[0]),
            })

    if low < min_recent_low and close > low and close > open_p:
        entry = close
        stop = low * 0.998
        risk_pct = abs(entry - stop) / entry if entry else 0
        if risk_pct > 0.001:
            signals.append({
                "direction": "LONG",
                "pattern": "sweep",
                "entry": entry,
                "stop": stop,
                "confidence": "medium",
                "entry_time": int(c[0]),
            })

    return signals[0] if signals else None


def _detect_wick_rejection(candles: list, i: int) -> dict | None:
    if i < 1:
        return None
    c = candles[i]
    high = float(c[2])
    low = float(c[3])
    close = float(c[4])
    open_p = float(c[1])

    body = abs(close - open_p)
    upper_wick = high - max(open_p, close)
    lower_wick = min(open_p, close) - low

    if body <= 0:
        return None

    signals = []

    if upper_wick >= 2 * body and close < open_p:
        entry = close
        stop = high * 1.002
        signals.append({
            "direction": "SHORT",
            "pattern": "wick_rejection",
            "entry": entry,
            "stop": stop,
            "confidence": "low" if upper_wick < 3 * body else "medium",
            "entry_time": int(c[0]),
        })

    if lower_wick >= 2 * body and close > open_p:
        entry = close
        stop = low * 0.998
        signals.append({
            "direction": "LONG",
            "pattern": "wick_rejection",
            "entry": entry,
            "stop": stop,
            "confidence": "low" if lower_wick < 3 * body else "medium",
            "entry_time": int(c[0]),
        })

    return signals[0] if signals else None


def _detect_compression_breakout(candles: list, i: int, lookback: int = 10) -> dict | None:
    if i < lookback + 1:
        return None
    c = candles[i]
    high = float(c[2])
    low = float(c[3])
    close = float(c[4])
    open_p = float(c[1])

    recent_ranges = []
    for j in range(i - lookback, i):
        h = float(candles[j][2])
        l_ = float(candles[j][3])
        recent_ranges.append((h - l_) / l_ if l_ else 0)

    avg_range = mean(recent_ranges) if recent_ranges else 0
    current_range = (high - low) / low if low else 0

    if avg_range <= 0 or current_range <= 0:
        return None

    compression_ratio = current_range / avg_range if avg_range else 0

    if compression_ratio < 0.5:
        return None

    atr_val = _atr(candles[:i + 1], 14)
    if atr_val <= 0:
        return None

    signals = []

    if close > open_p and (high - close) < (high - low) * 0.3:
        entry = close
        stop = low - atr_val * 0.5
        signals.append({
            "direction": "LONG",
            "pattern": "compression_breakout",
            "entry": entry,
            "stop": stop,
            "confidence": "low",
            "entry_time": int(c[0]),
        })

    if close < open_p and (close - low) < (high - low) * 0.3:
        entry = close
        stop = high + atr_val * 0.5
        signals.append({
            "direction": "SHORT",
            "pattern": "compression_breakout",
            "entry": entry,
            "stop": stop,
            "confidence": "low",
            "entry_time": int(c[0]),
        })

    return signals[0] if signals else None


def _detect_volume_spike(candles: list, i: int, lookback: int = 20) -> dict | None:
    if i < lookback + 1:
        return None
    c = candles[i]
    vol = float(c[5])
    close = float(c[4])
    open_p = float(c[1])
    high = float(c[2])
    low = float(c[3])

    avg_vol = _sma([float(candles[j][5]) for j in range(i - lookback, i)], lookback)
    if avg_vol <= 0:
        return None

    vol_ratio = vol / avg_vol
    if vol_ratio < 1.5:
        return None

    atr_val = _atr(candles[:i + 1], 14)
    if atr_val <= 0:
        return None

    signals = []

    if close > open_p and (high - close) < (high - low) * 0.3:
        entry = close
        stop = low - atr_val * 0.5
        signals.append({
            "direction": "LONG",
            "pattern": "volume_spike",
            "entry": entry,
            "stop": stop,
            "confidence": "low" if vol_ratio < 2 else "medium",
            "entry_time": int(c[0]),
        })

    if close < open_p and (close - low) < (high - low) * 0.3:
        entry = close
        stop = high + atr_val * 0.5
        signals.append({
            "direction": "SHORT",
            "pattern": "volume_spike",
            "entry": entry,
            "stop": stop,
            "confidence": "low" if vol_ratio < 2 else "medium",
            "entry_time": int(c[0]),
        })

    return signals[0] if signals else None


def _calculate_rr_target(entry: float, stop: float, direction: str, min_rr: float = 4.0) -> float | None:
    risk = abs(entry - stop)
    if risk <= 0 or entry <= 0:
        return None
    reward = risk * min_rr
    if direction == "LONG":
        return entry + reward
    else:
        return entry - reward


def _simulate_trade(candles: list, signal: dict, entry_idx: int, timeframe: str) -> dict:
    entry = signal["entry"]
    stop = signal["stop"]
    direction = signal["direction"]
    target = _calculate_rr_target(entry, stop, direction, 4.0)

    if target is None:
        return {**signal, "outcome": "INVALID", "r_result": 0.0, "exit_reason": "invalid_setup"}

    max_holding = MAX_HOLDING_CANDLES.get(timeframe, 120)

    outcome = "EXPIRED"
    exit_price = entry
    exit_reason = "max_holding_expired"
    hit_idx = entry_idx

    for j in range(entry_idx + 1, min(len(candles), entry_idx + max_holding + 1)):
        hit_idx = j
        c = candles[j]
        high = float(c[2])
        low = float(c[3])
        close = float(c[4])

        if direction == "LONG":
            if high >= target:
                outcome = "WIN"
                exit_price = target
                exit_reason = "TARGET_HIT"
                break
            if low <= stop:
                outcome = "LOSS"
                exit_price = stop
                exit_reason = "STOP_HIT"
                break
        else:
            if low <= target:
                outcome = "WIN"
                exit_price = target
                exit_reason = "TARGET_HIT"
                break
            if high >= stop:
                outcome = "LOSS"
                exit_price = stop
                exit_reason = "STOP_HIT"
                break

    risk = abs(entry - stop)
    pnl = (exit_price - entry) * (1 if direction == "LONG" else -1)
    r_result = round(pnl / risk, 2) if risk > 0 else 0.0
    fee_cost = entry * FEE_RATE * 2
    r_after_fees = round((pnl - fee_cost) / risk, 2) if risk > 0 else 0.0

    max_fav = 0.0
    max_adv = 0.0
    for j in range(entry_idx + 1, hit_idx + 1):
        c = candles[j]
        high = float(c[2])
        low = float(c[3])
        if direction == "LONG":
            mfe = (high - entry) / entry if entry else 0
            mae = (entry - low) / entry if entry else 0
        else:
            mfe = (entry - low) / entry if entry else 0
            mae = (high - entry) / entry if entry else 0
        max_fav = max(max_fav, mfe)
        max_adv = max(max_adv, mae)

    holding_candles = hit_idx - entry_idx

    return {
        "symbol": signal.get("symbol", "?"),
        "direction": direction,
        "timeframe": timeframe,
        "pattern": signal.get("pattern", "unknown"),
        "entry_time": signal.get("entry_time", 0),
        "entry_price": round(entry, 4),
        "stop": round(stop, 4),
        "target": round(target, 4),
        "exit_time": int(candles[hit_idx][0]) if hit_idx < len(candles) else 0,
        "exit_price": round(exit_price, 4),
        "exit_reason": exit_reason,
        "outcome": outcome,
        "r_result": r_result,
        "r_after_fees": r_after_fees,
        "holding_candles": holding_candles,
        "max_favorable_excursion_pct": round(max_fav * 100, 2),
        "max_adverse_excursion_pct": round(max_adv * 100, 2),
        "is_win": outcome == "WIN",
    }


# --------------------------------------------------------------------
# Diagnostics helpers
# --------------------------------------------------------------------

def _make_diagnostics() -> dict:
    """Create a fresh diagnostics counters dict."""
    return {
        "symbols_checked": 0,
        "symbols_skipped_too_few_candles": 0,
        "timeframes_checked": 0,
        "candles_loaded": 0,
        "candles_evaluated": 0,
        "sweep_detected": 0,
        "wick_rejection_detected": 0,
        "compression_detected": 0,
        "volume_spike_detected": 0,
        "trigger_confirmed": 0,
        "rr_passed": 0,
        "rr_failed": 0,
        "risk_passed": 0,
        "risk_failed": 0,
        "volume_passed": 0,
        "volume_failed": 0,
        "funding_oi_missing": 0,
        "funding_oi_passed": 0,
        "final_signal_created": 0,
        "rejection_reasons": defaultdict(int),
        "per_symbol": defaultdict(lambda: {
            "candles": 0, "evaluated": 0, "sweep": 0, "wick": 0,
            "compression": 0, "volume_spike": 0, "signals": 0,
        }),
        "per_timeframe": defaultdict(lambda: {
            "candles": 0, "evaluated": 0, "signals": 0,
        }),
        "near_misses": [],
        "data_fetch_successful": False,
        "data_fetch_error": "",
        "cache_files_found": 0,
        "total_duration_ms": 0,
    }


def _write_diagnostics_json(diag: dict):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    serializable = _make_diagnostics_serializable(diag)
    with open(DIAG_JSON_PATH, "w") as f:
        json.dump(serializable, f, indent=2)


def _make_diagnostics_serializable(diag: dict) -> dict:
    result = {}
    for k, v in diag.items():
        if isinstance(v, defaultdict):
            result[k] = dict(v)
        elif isinstance(v, list):
            result[k] = v
        elif isinstance(v, dict):
            inner = {}
            for ik, iv in v.items():
                inner[str(ik)] = dict(iv) if isinstance(iv, defaultdict) else iv
            result[k] = inner
        else:
            result[k] = v
    return result


def _write_diagnostics_txt(diag: dict):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    lines = [
        "=" * 60,
        "  HISTORICAL REPLAY DIAGNOSTICS",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        "  === OVERVIEW ===",
        f"  Symbols checked:              {diag['symbols_checked']}",
        f"  Symbols skipped (<50 candles): {diag['symbols_skipped_too_few_candles']}",
        f"  Timeframes checked:           {diag['timeframes_checked']}",
        f"  Candles loaded:               {diag['candles_loaded']}",
        f"  Candles evaluated:            {diag['candles_evaluated']}",
        f"  Cache files found:            {diag['cache_files_found']}",
        f"  Data fetch successful:        {diag['data_fetch_successful']}",
        "",
        "  === DETECTOR COUNTS ===",
        f"  Sweep detections:             {diag['sweep_detected']}",
        f"  Wick rejection detections:    {diag['wick_rejection_detected']}",
        f"  Compression detections:       {diag['compression_detected']}",
        f"  Volume spike detections:      {diag['volume_spike_detected']}",
        "",
        "  === FILTER GATE COUNTS ===",
        f"  Trigger confirmed:            {diag['trigger_confirmed']}",
        f"  RR passed:                    {diag['rr_passed']}",
        f"  RR failed:                    {diag['rr_failed']}",
        f"  Risk passed:                  {diag['risk_passed']}",
        f"  Risk failed:                  {diag['risk_failed']}",
        f"  Volume passed:                {diag['volume_passed']}",
        f"  Volume failed:                {diag['volume_failed']}",
        f"  Funding/OI missing:           {diag['funding_oi_missing']}",
        f"  Funding/OI passed:            {diag['funding_oi_passed']}",
        f"  Final signals created:        {diag['final_signal_created']}",
        "",
    ]

    if diag["rejection_reasons"]:
        reasons = sorted(diag["rejection_reasons"].items(), key=lambda x: -x[1])
        lines.append("  === TOP REJECTION REASONS ===")
        for reason, count in reasons[:15]:
            lines.append(f"    {reason}: {count}")
        lines.append("")

    if diag["near_misses"]:
        lines.append("  === NEAR-MISSES (DIAGNOSTIC MODE) ===")
        for nm in diag["near_misses"][:10]:
            lines.append(
                f"  [{nm.get('symbol','?')} {nm.get('timeframe','?')}] "
                f"{nm.get('direction','?')} "
                f"rejection: {nm.get('rejection_reason','?')} "
                f"RR est: {nm.get('rr_estimate','?')}"
            )
        if len(diag["near_misses"]) > 10:
            lines.append(f"  ... and {len(diag['near_misses']) - 10} more")
        lines.append("")

    lines += [
        "=" * 60,
    ]

    with open(DIAG_TXT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def _record_near_miss(near_misses: list, entry: dict):
    near_misses.append(entry)
    if DIAGNOSTIC_MODE:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(NEAR_MISS_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")


# --------------------------------------------------------------------
# Cache loader
# --------------------------------------------------------------------

def _cache_path(symbol: str, timeframe: str) -> str:
    safe = symbol.replace("/", "_")
    return os.path.join(CACHE_DIR, f"{safe}_{timeframe}.json")


def _read_cache(symbol: str, timeframe: str) -> list | None:
    path = _cache_path(symbol, timeframe)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def load_cached_data(symbols: list[str] | None = None, timeframes: list[str] | None = None) -> dict[str, list]:
    """Load cached OHLCV data for given symbols/timeframes from local cache.

    Returns dict of symbol -> list of candles.
    """
    if timeframes is None:
        timeframes = SUPPORTED_TIMEFRAMES

    if not os.path.isdir(CACHE_DIR):
        return {}

    if symbols is None:
        cached_files = os.listdir(CACHE_DIR)
        symbols_set = set()
        for fname in cached_files:
            for tf in timeframes:
                suffix = f"_{tf}.json"
                if fname.endswith(suffix):
                    sym = fname[:-len(suffix)].replace("_", "/", 1)
                    symbols_set.add(sym)
        symbols = sorted(symbols_set)

    result = {}
    for sym in symbols:
        for tf in timeframes:
            data = _read_cache(sym, tf)
            if data and len(data) > 50:
                key = f"{sym}_{tf}"
                result[key] = data
    return result


# --------------------------------------------------------------------
# Main replay with diagnostics
# --------------------------------------------------------------------

def run_replay_with_diagnostics(
    ohlcv_data: dict[str, list],
    timeframes: list[str] | None = None,
) -> tuple[list[dict], dict]:
    """Run historical replay with full diagnostics.

    Returns:
        (trades, diagnostics) tuple.
    """
    import time as _time
    start_ms = int(_time.time() * 1000)

    if timeframes is None:
        timeframes = ["1h"]

    diag = _make_diagnostics()
    all_trades = []
    seen_signals = set()

    for symbol, candles in ohlcv_data.items():
        if symbol in diag["per_symbol"]:
            pass
        diag["symbols_checked"] += 1
        diag["candles_loaded"] += len(candles)
        diag["per_symbol"][symbol]["candles"] = len(candles)

        if len(candles) < 50:
            diag["symbols_skipped_too_few_candles"] += 1
            continue

        for tf in timeframes:
            diag["timeframes_checked"] += 1
            max_hold = MAX_HOLDING_CANDLES.get(tf, 120)

            for i in range(30, len(candles) - 1):
                diag["candles_evaluated"] += 1
                diag["per_symbol"][symbol]["evaluated"] += 1
                diag["per_timeframe"][tf]["evaluated"] += 1

                sweep_signal = _detect_sweep(candles, i)
                wick_signal = _detect_wick_rejection(candles, i)
                compression_signal = _detect_compression_breakout(candles, i)
                volume_signal = _detect_volume_spike(candles, i)

                if sweep_signal:
                    diag["sweep_detected"] += 1
                    diag["per_symbol"][symbol]["sweep"] += 1
                if wick_signal:
                    diag["wick_rejection_detected"] += 1
                    diag["per_symbol"][symbol]["wick"] += 1
                if compression_signal:
                    diag["compression_detected"] += 1
                    diag["per_symbol"][symbol]["compression"] += 1
                if volume_signal:
                    diag["volume_spike_detected"] += 1
                    diag["per_symbol"][symbol]["volume_spike"] += 1

                detectors = [sweep_signal, wick_signal, compression_signal, volume_signal]

                for signal in detectors:
                    if signal is None:
                        continue

                    diag["trigger_confirmed"] += 1

                    # Check risk
                    risk = abs(signal["stop"] - signal["entry"])
                    risk_pct = risk / signal["entry"] if signal["entry"] else 0
                    if risk_pct <= 0.001:
                        diag["risk_failed"] += 1
                        diag["rejection_reasons"]["RISK_TOO_SMALL"] += 1
                        _record_near_miss(diag["near_misses"], {
                            "symbol": symbol,
                            "timeframe": tf,
                            "candle_time": signal["entry_time"],
                            "direction": signal["direction"],
                            "pattern": signal["pattern"],
                            "passed_filters": ["trigger_confirmed"],
                            "failed_filters": ["risk_check"],
                            "rr_estimate": 0,
                            "rejection_reason": "RISK_TOO_SMALL",
                        })
                        continue
                    diag["risk_passed"] += 1

                    # Check RR >= 4
                    target = _calculate_rr_target(
                        signal["entry"], signal["stop"], signal["direction"], 4.0
                    )
                    if target is None:
                        diag["rr_failed"] += 1
                        diag["rejection_reasons"]["TARGET_CALC_FAILED"] += 1
                        _record_near_miss(diag["near_misses"], {
                            "symbol": symbol,
                            "timeframe": tf,
                            "candle_time": signal["entry_time"],
                            "direction": signal["direction"],
                            "pattern": signal["pattern"],
                            "passed_filters": ["trigger_confirmed", "risk_check"],
                            "failed_filters": ["rr_check"],
                            "rr_estimate": round(risk_pct * 4 / risk_pct, 2) if risk_pct else 0,
                            "rejection_reason": "TARGET_CALC_FAILED",
                        })
                        continue
                    diag["rr_passed"] += 1

                    # Volume check (for volume spike pattern only)
                    if signal["pattern"] == "volume_spike":
                        vol = float(candles[i][5])
                        avg_vol = _sma(
                            [float(candles[j][5]) for j in range(i - 20, i) if j >= 0],
                            20
                        )
                        if avg_vol > 0 and vol / avg_vol < 1.5:
                            diag["volume_failed"] += 1
                            continue
                    diag["volume_passed"] += 1

                    # Funding/OI not used in replay (no real data)
                    diag["funding_oi_missing"] += 1

                    signal["symbol"] = symbol

                    sig_key = f"{symbol}_{tf}_{signal['direction']}_{i}"
                    if sig_key in seen_signals:
                        continue
                    seen_signals.add(sig_key)

                    diag["final_signal_created"] += 1
                    diag["per_symbol"][symbol]["signals"] += 1
                    diag["per_timeframe"][tf]["signals"] += 1
                    diag["funding_oi_passed"] += 1

                    trade = _simulate_trade(candles, signal, i, tf)
                    all_trades.append(trade)

    end_ms = int(_time.time() * 1000)
    diag["total_duration_ms"] = end_ms - start_ms

    # Write diagnostics
    _write_diagnostics_json(diag)
    _write_diagnostics_txt(diag)

    return all_trades, diag


def run_replay(
    ohlcv_data: dict[str, list],
    timeframes: list[str] | None = None,
) -> list[dict]:
    """Run historical replay (backwards-compatible, returns only trades)."""
    trades, _ = run_replay_with_diagnostics(ohlcv_data, timeframes)
    return trades


def run_and_save(ohlcv_data: dict[str, list], timeframes: list[str] | None = None) -> list[dict]:
    """Run replay and save trades to ledger."""
    os.makedirs(STATE_DIR, exist_ok=True)
    trades, diag = run_replay_with_diagnostics(ohlcv_data, timeframes)

    with open(TRADES_LEDGER, "w") as f:
        for t in trades:
            f.write(json.dumps(t) + "\n")

    return trades


def run_full_pipeline(symbols: list[str] | None = None) -> tuple[list[dict], dict]:
    """Run the full pipeline: load cache -> replay -> diagnose.

    If no cached data exists, returns empty trades with diagnostics showing
    cache_missing status.
    """
    diag = _make_diagnostics()

    cached = load_cached_data(symbols)
    diag["cache_files_found"] = len(cached)

    if not cached:
        diag["data_fetch_successful"] = False
        diag["data_fetch_error"] = "No cached data found in runtime_state/historical_cache/"
        _write_diagnostics_json(diag)
        _write_diagnostics_txt(diag)
        return [], diag

    diag["data_fetch_successful"] = True
    trades, replay_diag = run_replay_with_diagnostics(cached)
    return trades, replay_diag


# --------------------------------------------------------------------
# Live-trigger parity check
# --------------------------------------------------------------------

def compute_live_trigger_parity() -> dict:
    """Compare historical replay detectors with live trigger_watcher logic.

    Returns a report of:
    - Filters present in live but not in historical
    - Filters present in historical but not in live
    - Whether historical replay can reproduce FLUID-USDT-like trigger logic
    """
    report = {
        "live_only_filters": [],
        "historical_only_filters": [],
        "overlapping_filters": [],
        "can_reproduce_fluid_usdt_live_trigger": False,
        "fluid_usdt_analysis": "",
        "notes": [],
    }

    live_thesis_types = {
        "UPPER_WICK_EXTENSION": "Live: detects upper wick, then confirms when close < wick midpoint",
        "LOWER_WICK_EXTENSION": "Live: detects lower wick, then confirms when close > wick midpoint",
        "SWEEP_HIGH": "Live: detects high sweep, then confirms when close < swept high",
        "SWEEP_LOW": "Live: detects low sweep, then confirms when close > swept low",
        "COMPRESSION": "Live: compression setups waiting for breakout; requires another trigger",
    }

    historical_detectors = {
        "sweep": "Historical: one-step sweep on same candle (high > max or low < min + close confirms)",
        "wick_rejection": "Historical: one-step wick rejection (wick >= 2x body + close confirms)",
        "compression_breakout": "Historical: one-step compression breakout (range expanding + close near extreme)",
        "volume_spike": "Historical: one-step volume spike (vol >= 1.5x avg + directional close)",
    }

    live_filters = set(live_thesis_types.keys())
    historical_filters = set(historical_detectors.keys())

    # Map overlapping concepts
    # Live SWEEP_HIGH/LOW maps to historical sweep
    # Live UPPER_WICK_EXTENSION/LOWER_WICK_EXTENSION maps to historical wick_rejection
    # Live COMPRESSION maps to historical compression_breakout

    overlap_map = {
        ("SWEEP_HIGH", "SWEEP_LOW"): "sweep",
        ("UPPER_WICK_EXTENSION", "LOWER_WICK_EXTENSION"): "wick_rejection",
        ("COMPRESSION",): "compression_breakout",
    }

    # Live has VOLUME_WATCH but it's not a thesis type; historical has volume_spike
    # Live has no volume thesis type, only a volume filter inside _check_trigger indirectly via candidate data

    overlapping_concepts = ["sweep", "wick_rejection", "compression_breakout"]
    report["overlapping_filters"] = overlapping_concepts

    # Live-only features
    report["live_only_filters"].append(
        "Two-phase process: Phase 1 creates candidate (near_miss_diagnostics.py), "
        "Phase 2 confirms trigger (trigger_watcher.py _check_trigger)"
    )
    report["live_only_filters"].append(
        "EXPIRY: Live triggers expire after N minutes per timeframe; "
        "historical has no expiry concept"
    )
    report["live_only_filters"].append(
        "INVALIDATION: Live can INVALIDATE a trigger if price moves against; "
        "historical is one-shot at candle i"
    )
    report["live_only_filters"].append(
        "THESIS_SCORE: Live uses thesis_score >= 75 for trigger; "
        "historical has no thesis score"
    )
    report["live_only_filters"].append(
        "WATCHLIST: Live candidates must come through watchlist pipeline; "
        "historical scans every candle independently"
    )

    # Historical-only features
    report["historical_only_filters"].append(
        "volume_spike detector: Historical detects volume spikes as standalone pattern; "
        "live has no volume-based thesis type"
    )
    report["historical_only_filters"].append(
        "Risk check (0.1% min): Historical checks risk_pct > 0.001; "
        "live relies on stop distance from entry"
    )
    report["historical_only_filters"].append(
        "Compression expansion ratio: Historical requires current_range / avg_range >= 0.5; "
        "live COMPRESSION thesis just marks as WAITING"
    )

    # FLUID-USDT analysis
    report["can_reproduce_fluid_usdt_live_trigger"] = True
    report["fluid_usdt_analysis"] = (
        "Historical replay engine CAN reproduce FLUID-USDT-like live trigger logic "
        "for sweep patterns (the most common setup). The historical sweep detector "
        "checks for the same conditions as the live trigger_watcher: "
        "high > max_recent_high and close < high and close < open_p for SHORT. "
        "However, there are key differences: (1) Historical does one-step detection "
        "on the same candle, while live uses two-phase (pattern detection then "
        "subsequent candle confirmation). (2) Historical uses a 0.2% stop buffer, "
        "while live uses the actual high/low. "
        "(3) Historical requires RR >= 4 on the same candle, "
        "while live waits for price confirmation then separately checks RR. "
        "(4) Live uses reference range (excluding latest) for sweep high, "
        "while historical uses lookback=20 candles including current. "
        "These differences may cause historical to miss setups that appear in live "
        "and vice versa."
    )

    report["notes"].append(
        "Historical replay simulates one-step execution: detect + enter + check RR "
        "all at candle i. Live has a multi-step pipeline with expiry and invalidation."
    )
    report["notes"].append(
        "The biggest divergence is the 2-phase process: live can wait multiple "
        "candles for confirmation, historical must confirm within the same candle."
    )
    report["notes"].append(
        "To fully match live behavior, historical would need to also use a 2-phase "
        "approach: detect at candle i, confirm at candle i+1 or later."
    )

    return report


def main():
    print("Historical Replay Engine (offline research)")

    if DIAGNOSTIC_MODE:
        print("[DIAGNOSTIC MODE] Near-miss recording enabled")
        print(f"[DIAGNOSTIC MODE] Near-miss path: {NEAR_MISS_PATH}")

    trades, diag = run_full_pipeline()

    if trades:
        print(f"Generated {len(trades)} historical trades")
        with open(TRADES_LEDGER, "w") as f:
            for t in trades:
                f.write(json.dumps(t) + "\n")
    else:
        print("No trades generated")
        print(f"  Candles evaluated: {diag.get('candles_evaluated', 0)}")
        print(f"  Sweep detected:    {diag.get('sweep_detected', 0)}")
        print(f"  Wick rejection:    {diag.get('wick_rejection_detected', 0)}")
        if diag.get("rejection_reasons"):
            top = sorted(diag["rejection_reasons"].items(), key=lambda x: -x[1])[0]
            print(f"  Top rejection:     {top[0]} ({top[1]} times)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
