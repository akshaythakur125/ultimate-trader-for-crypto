"""Near-Miss Diagnostic and Watchlist Intelligence.

Reads Dux pattern results and psychology alpha output, classifies every
symbol/timeframe into diagnostic buckets, and produces a near-miss report.
Includes independent raw market anomaly scoring.

Usage:
    python -m production_replay.near_miss_diagnostics
"""

import json, math, os, sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
TXT_PATH = os.path.join(RESULTS_DIR, "near_miss_report.txt")
JSON_PATH = os.path.join(RESULTS_DIR, "near_miss_report.json")
WATCHLIST_PATH = os.path.join(STATE_DIR, "near_miss_watchlist.jsonl")
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state", "candles_cache")

RR_MIN = 4.0
PSYCH_WATCH_MIN = 70
PSYCH_ELITE_MIN = 85
NEAR_MISS_PSYCH_MIN = 50
NEAR_MISS_RR_MIN = 2.0
RAW_ANOMALY_WATCH_MIN = 70
RAW_ANOMALY_NEAR_MISS_MIN = 50
RAW_ANOMALY_OBSERVE_MIN = 30

BUCKETS = [
    "EXECUTABLE_CANDIDATE",
    "WATCHLIST_READY",
    "NEAR_MISS_RR",
    "NEAR_MISS_PSYCHOLOGY",
    "RAW_TRAP_DETECTED",
    "REJECTED",
]

REJECTION_REASONS = [
    "RR_TOO_POOR",
    "PSYCHOLOGY_TOO_WEAK",
    "NO_CLEAR_TRAP",
    "ENTRY_TOO_LATE",
    "STOP_TOO_WIDE",
    "TARGET_TOO_CLOSE",
    "TARGET_UNREALISTIC",
    "STRUCTURE_NOT_CONFIRMED",
    "LIQUIDITY_TOO_POOR",
    "DATA_MISSING",
    "API_ERROR",
    "TIMEOUT_SKIPPED",
    "NO_CANDIDATE",
]

RAW_ANOMALY_CATEGORIES = [
    "VOLUME_ANOMALY",
    "VOLATILITY_EXPANSION",
    "COMPRESSION",
    "WICK_REJECTION",
    "SWEEP",
    "EXTENSION",
    "RELATIVE_MOMENTUM",
]

LIFECYCLE_STAGES = [
    "EARLY_FORMING",
    "COMPRESSION_BUILDING",
    "TRIGGER_NEAR",
    "TRIGGERED_BUT_UNCONFIRMED",
    "CONFIRMED_BUT_RR_POOR",
    "EXECUTABLE",
    "LATE_CHASE",
    "DEAD_SETUP",
]

ANOMALY_LABELS = {
    "volume_anomaly": "volume anomaly",
    "volatility_expansion": "volatility expansion",
    "extension": "parabolic extension",
    "wick_rejection": "wick rejection",
    "sweep": "range sweep",
    "compression": "compression",
    "relative_momentum": "relative strength",
}


def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _read_jsonl(path: str) -> list[dict]:
    records = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return records


def _compute_rr(entry: float, stop: float, target: float) -> float:
    risk = abs(entry - stop)
    if risk <= 0:
        return 0.0
    return round(abs(target - entry) / risk, 2)


def _load_cached_candles(symbol: str, tf: str) -> list[dict]:
    """Load candles for anomaly scoring. Tries memory cache first, then API."""
    cache_key = f"{symbol}_{tf}".replace("-", "_")
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path) as f:
                return json.load(f)
        except Exception:
            pass
    try:
        from production_replay.bingx_client import get_klines, load_credentials
        base = load_credentials()["base_url"]
        resp = get_klines(symbol, tf, 100, base)
        if resp["success"]:
            data = resp.get("data", {})
            if isinstance(data, dict) and data.get("code") == 0:
                raw = data.get("data", [])
                candles = []
                for r in raw:
                    try:
                        candles.append({
                            "timestamp": str(r.get("time", "")),
                            "open": float(r["open"]),
                            "high": float(r["high"]),
                            "low": float(r["low"]),
                            "close": float(r["close"]),
                            "volume": float(r.get("volume", 0)),
                        })
                    except (KeyError, ValueError, TypeError):
                        continue
                if candles:
                    os.makedirs(CACHE_DIR, exist_ok=True)
                    try:
                        with open(cache_path, "w") as f:
                            json.dump(candles, f)
                    except Exception:
                        pass
                    return candles
    except Exception:
        pass
    return []


# --- Raw Anomaly Scoring ---

def _volatility_expansion_score(candles: list[dict]) -> tuple[int, str]:
    if len(candles) < 20:
        return (0, "")
    recent = candles[-5:]
    prior = candles[-20:-5]
    recent_ranges = [abs(c["high"] - c["low"]) for c in recent]
    prior_ranges = [abs(c["high"] - c["low"]) for c in prior]
    avg_recent = sum(recent_ranges) / len(recent_ranges)
    avg_prior = sum(prior_ranges) / len(prior_ranges)
    if avg_prior <= 0:
        return (0, "")
    ratio = avg_recent / avg_prior
    if ratio >= 2.5:
        return (min(25, int(ratio * 8)), "volatility_expansion")
    if ratio >= 1.8:
        return (min(18, int(ratio * 6)), "volatility_expansion")
    if ratio >= 1.4:
        return (10, "volatility_expansion")
    return (0, "")


def _volume_anomaly_score(candles: list[dict]) -> tuple[int, str]:
    if len(candles) < 20:
        return (0, "")
    recent = candles[-5:]
    prior = candles[-20:-5]
    recent_vol = sum(c["volume"] for c in recent) / len(recent)
    avg_vol = sum(c["volume"] for c in prior) / len(prior)
    if avg_vol <= 0:
        return (0, "")
    ratio = recent_vol / avg_vol
    if ratio >= 3.0:
        return (min(25, int(ratio * 7)), "volume_anomaly")
    if ratio >= 2.0:
        return (min(18, int(ratio * 6)), "volume_anomaly")
    if ratio >= 1.5:
        return (12, "volume_anomaly")
    if ratio <= 0.3:
        return (8, "volume_anomaly")
    return (0, "")


def _extension_score(candles: list[dict]) -> tuple[int, str]:
    if len(candles) < 15:
        return (0, "")
    closes = [c["close"] for c in candles[-15:]]
    ema20 = sum(closes) / len(closes)
    last = candles[-1]
    mid = (last["high"] + last["low"]) / 2
    if ema20 <= 0:
        return (0, "")
    pct = abs(mid - ema20) / ema20 * 100
    cons_up = 0
    cons_down = 0
    for i in range(1, min(8, len(closes))):
        if closes[-i] > closes[-i - 1]:
            cons_up += 1
        elif closes[-i] < closes[-i - 1]:
            cons_down += 1
    score = 0
    if pct >= 5.0:
        score = 20
    elif pct >= 3.0:
        score = 15
    elif pct >= 1.5:
        score = 8
    if cons_up >= 5 or cons_down >= 5:
        score += 5
    if score > 0:
        return (min(20, score), "extension")
    return (0, "")


def _wick_rejection_score(candles: list[dict]) -> tuple[int, str]:
    if len(candles) < 5:
        return (0, "")
    last = candles[-1]
    total_range = last["high"] - last["low"]
    if total_range <= 0:
        return (0, "")
    body = abs(last["close"] - last["open"])
    upper_wick = last["high"] - max(last["open"], last["close"])
    lower_wick = min(last["open"], last["close"]) - last["low"]
    upper_pct = upper_wick / total_range * 100
    lower_pct = lower_wick / total_range * 100
    score = 0
    label = ""
    if upper_pct >= 60 and body > 0:
        score = min(20, int(upper_pct / 3))
        label = "wick_rejection"
    elif lower_pct >= 60 and body > 0:
        score = min(20, int(lower_pct / 3))
        label = "wick_rejection"
    elif upper_pct >= 40:
        score = 8
        label = "wick_rejection"
    elif lower_pct >= 40:
        score = 8
        label = "wick_rejection"
    if score > 0 and total_range > 0:
        score = min(score, 20)
    return (score, label)


def _sweep_score(candles: list[dict]) -> tuple[int, str]:
    if len(candles) < 15:
        return (0, "")
    window = candles[-15:-1]
    if not window:
        return (0, "")
    range_high = max(c["high"] for c in window)
    range_low = min(c["low"] for c in window)
    last = candles[-1]
    score = 0
    label = ""
    if last["high"] > range_high and last["close"] < range_high:
        score = 18
        label = "sweep"
    elif last["low"] < range_low and last["close"] > range_low:
        score = 18
        label = "sweep"
    elif last["high"] > range_high:
        score = 8
        label = "sweep"
    elif last["low"] < range_low:
        score = 8
        label = "sweep"
    return (score, label)


def _compression_score(candles: list[dict]) -> tuple[int, str]:
    if len(candles) < 20:
        return (0, "")
    recent = candles[-10:]
    prior = candles[-20:-10]
    recent_ranges = [abs(c["high"] - c["low"]) for c in recent]
    prior_ranges = [abs(c["high"] - c["low"]) for c in prior]
    avg_recent = sum(recent_ranges) / len(recent_ranges)
    avg_prior = sum(prior_ranges) / len(prior_ranges)
    if avg_prior <= 0:
        return (0, "")
    ratio = avg_recent / avg_prior
    if ratio <= 0.4:
        return (18, "compression")
    if ratio <= 0.6:
        return (12, "compression")
    if ratio <= 0.8:
        return (7, "compression")
    return (0, "")


def _relative_momentum_score(candles: list[dict], symbol: str) -> tuple[int, str]:
    return (0, "")


def _compute_raw_anomaly_score(symbol: str, timeframe: str) -> dict:
    candles = _load_cached_candles(symbol, timeframe)
    if len(candles) < 20:
        return {"raw_anomaly_score": 0, "anomalies": [], "top_anomaly": ""}

    scores = []
    anomalies = []

    vola_score, vola_label = _volatility_expansion_score(candles)
    if vola_score > 0:
        scores.append(vola_score)
        anomalies.append(vola_label)

    vol_score, vol_label = _volume_anomaly_score(candles)
    if vol_score > 0:
        scores.append(vol_score)
        anomalies.append(vol_label)

    ext_score, ext_label = _extension_score(candles)
    if ext_score > 0:
        scores.append(ext_score)
        anomalies.append(ext_label)

    wick_score, wick_label = _wick_rejection_score(candles)
    if wick_score > 0:
        scores.append(wick_score)
        anomalies.append(wick_label)

    sweep_score_val, sweep_label = _sweep_score(candles)
    if sweep_score_val > 0:
        scores.append(sweep_score_val)
        anomalies.append(sweep_label)

    comp_score, comp_label = _compression_score(candles)
    if comp_score > 0:
        scores.append(comp_score)
        anomalies.append(comp_label)

    rel_score, rel_label = _relative_momentum_score(candles, symbol)
    if rel_score > 0:
        scores.append(rel_score)
        anomalies.append(rel_label)

    total = sum(scores) if scores else 0
    total = min(total, 100)
    top = max(anomalies, key=lambda a: ANOMALY_LABELS.get(a, a)) if anomalies else ""

    return {
        "raw_anomaly_score": total,
        "anomalies": anomalies,
        "top_anomaly": top,
        "volatility_expansion": vola_score,
        "volume_anomaly": vol_score,
        "extension": ext_score,
        "wick_rejection": wick_score,
        "sweep": sweep_score_val,
        "compression": comp_score,
        "relative_momentum": rel_score,
    }


def _classify_bucket(pattern: dict, psych: dict | None, raw_anomaly: dict | None = None) -> str:
    rr = pattern.get("rr_2") or 0
    psych_score = psych.get("psychology_score", 0) if psych else 0
    rejected = pattern.get("rejected", True)
    has_trap = pattern.get("pattern_id", "") != "" and pattern.get("direction", "UNKNOWN") != "UNKNOWN"
    raw_score = raw_anomaly.get("raw_anomaly_score", 0) if raw_anomaly else 0

    if not rejected and rr >= RR_MIN and psych_score >= PSYCH_ELITE_MIN:
        return "EXECUTABLE_CANDIDATE"
    if not rejected and rr >= RR_MIN and psych_score >= PSYCH_WATCH_MIN:
        return "EXECUTABLE_CANDIDATE"
    if not rejected and rr >= RR_MIN and NEAR_MISS_PSYCH_MIN <= psych_score < PSYCH_WATCH_MIN:
        return "NEAR_MISS_PSYCHOLOGY"
    if not rejected and rr >= RR_MIN and psych_score >= NEAR_MISS_PSYCH_MIN:
        return "WATCHLIST_READY"
    if has_trap and NEAR_MISS_RR_MIN <= rr < RR_MIN and psych_score >= PSYCH_WATCH_MIN:
        return "NEAR_MISS_RR"
    if raw_score >= RAW_ANOMALY_WATCH_MIN:
        return "WATCHLIST_READY"
    if raw_score >= RAW_ANOMALY_NEAR_MISS_MIN:
        return "RAW_TRAP_DETECTED"
    if has_trap:
        return "RAW_TRAP_DETECTED"
    if raw_score >= RAW_ANOMALY_OBSERVE_MIN:
        return "REJECTED"
    return "REJECTED"


def _actionability_score(candidate: dict) -> int:
    score = 0
    bucket = candidate.get("bucket", "REJECTED")
    bucket_ranks = {"EXECUTABLE_CANDIDATE": 100, "WATCHLIST_READY": 80,
                    "NEAR_MISS_RR": 60, "NEAR_MISS_PSYCHOLOGY": 50,
                    "RAW_TRAP_DETECTED": 30, "REJECTED": 0}
    score += bucket_ranks.get(bucket, 0)
    psych = candidate.get("psychology_score", 0) or 0
    score += psych
    raw_anomaly = candidate.get("raw_anomaly_score", 0) or 0
    score += raw_anomaly
    rr = candidate.get("rr_value", 0) or 0
    if rr >= 1:
        score += int(rr * 5)
    return score


def _is_valid_watchlist_entry(candidate: dict) -> bool:
    bucket = candidate.get("bucket", "REJECTED")
    if bucket == "REJECTED" and candidate.get("raw_anomaly_score", 0) < RAW_ANOMALY_OBSERVE_MIN:
        return False
    if candidate.get("psychology_score", 0) == 0 and candidate.get("raw_anomaly_score", 0) == 0:
        return False
    rr_raw = candidate.get("current_rr", "N/A")
    rr_val = candidate.get("rr_value", 0)
    if rr_raw in ("N/A", None, "") and rr_val == 0 and candidate.get("raw_anomaly_score", 0) < RAW_ANOMALY_OBSERVE_MIN:
        return False
    if candidate.get("direction", "UNKNOWN") == "UNKNOWN" and candidate.get("raw_anomaly_score", 0) < RAW_ANOMALY_OBSERVE_MIN:
        return False
    if candidate.get("lifecycle") == "DEAD_SETUP" and candidate.get("raw_anomaly_score", 0) < RAW_ANOMALY_OBSERVE_MIN:
        return False
    if candidate.get("next_step", "") in ("no actionable setup", "") and candidate.get("raw_anomaly_score", 0) < RAW_ANOMALY_OBSERVE_MIN:
        return False
    return True


def _classify_lifecycle(pattern: dict, bucket: str, psych: dict | None, raw_anomaly: dict | None = None) -> str:
    rr = pattern.get("rr_2") or 0
    if bucket == "EXECUTABLE_CANDIDATE":
        return "EXECUTABLE"
    if bucket == "WATCHLIST_READY":
        return "CONFIRMED_BUT_RR_POOR" if rr < RR_MIN else "TRIGGERED_BUT_UNCONFIRMED"
    if bucket == "NEAR_MISS_RR":
        return "CONFIRMED_BUT_RR_POOR"
    if bucket == "NEAR_MISS_PSYCHOLOGY":
        return "TRIGGERED_BUT_UNCONFIRMED"
    if bucket == "RAW_TRAP_DETECTED":
        raw = raw_anomaly or {}
        if raw.get("volatility_expansion", 0) > 0 or pattern.get("vol_expansion") is True:
            return "TRIGGER_NEAR"
        if raw.get("compression", 0) > 0:
            return "COMPRESSION_BUILDING"
        if raw.get("sweep", 0) > 0:
            return "TRIGGER_NEAR"
        if raw.get("wick_rejection", 0) > 0:
            return "TRIGGERED_BUT_UNCONFIRMED"
        return "COMPRESSION_BUILDING"
    if pattern.get("pattern_id", ""):
        return "DEAD_SETUP"
    return "DEAD_SETUP"


def _assign_rejection_reason(pattern: dict, bucket: str, psych: dict | None, raw_anomaly: dict | None = None) -> str:
    rr = pattern.get("rr_2") or 0
    psych_score = psych.get("psychology_score", 0) if psych else 0
    raw = raw_anomaly or {}
    if pattern.get("pattern_id", "") == "" or pattern.get("direction", "UNKNOWN") == "UNKNOWN":
        for cat in RAW_ANOMALY_CATEGORIES:
            if raw.get(cat.lower(), 0) > 0:
                return cat
        return "NO_CLEAR_TRAP"
    if rr < NEAR_MISS_RR_MIN:
        return "RR_TOO_POOR"
    if NEAR_MISS_RR_MIN <= rr < RR_MIN and psych_score >= PSYCH_WATCH_MIN:
        return "RR_TOO_POOR"
    if rr >= RR_MIN and psych_score < NEAR_MISS_PSYCH_MIN:
        return "PSYCHOLOGY_TOO_WEAK"
    if bucket == "RAW_TRAP_DETECTED":
        return "STRUCTURE_NOT_CONFIRMED"
    return "NO_CANDIDATE"


def _compute_alternative_entries(pattern: dict) -> list[dict]:
    entry = pattern.get("entry", 0)
    stop = pattern.get("stop", 0)
    target = pattern.get("target_2", 0)
    direction = pattern.get("direction", "LONG")
    rr = pattern.get("rr_2") or 0
    plans = []

    risk = abs(entry - stop)
    if risk <= 0 or entry <= 0 or stop <= 0:
        return [{"plan": "none", "reason": "invalid parameters"}]

    current_rr = _compute_rr(entry, stop, target) if target else 0
    plans.append({
        "plan": "current_market_entry",
        "entry": entry, "stop": stop, "target": target,
        "rr": current_rr,
        "feasibility": "ready" if current_rr >= RR_MIN else "needs improvement",
        "trigger_condition": "execute now" if current_rr >= RR_MIN else "wait for better entry",
    })

    if direction == "LONG":
        pullback_entry = round(entry * 0.985, 2)
    else:
        pullback_entry = round(entry * 1.015, 2)
    new_risk = abs(pullback_entry - stop)
    if new_risk > 0:
        pullback_target = round(pullback_entry + new_risk * RR_MIN, 2) if direction == "LONG" else round(pullback_entry - new_risk * RR_MIN, 2)
        pullback_rr = _compute_rr(pullback_entry, stop, pullback_target)
        plans.append({
            "plan": "pullback_retest_entry", "entry": pullback_entry,
            "stop": stop, "target": pullback_target, "rr": pullback_rr,
            "feasibility": "possible" if pullback_rr >= RR_MIN else "unlikely",
            "trigger_condition": "wait for pullback to entry level",
        })

    if direction == "SHORT":
        better_entry = round(pattern.get("pump_high", entry * 1.02), 2)
    else:
        better_entry = round(pattern.get("flush_low", entry * 0.98), 2)
    risk2 = abs(better_entry - stop)
    if risk2 > 0 and better_entry != entry:
        target2 = round(better_entry + risk2 * RR_MIN, 2) if direction == "LONG" else round(better_entry - risk2 * RR_MIN, 2)
        rr2 = _compute_rr(better_entry, stop, target2)
        plans.append({
            "plan": "breakout_failure_confirmation", "entry": better_entry,
            "stop": stop, "target": target2, "rr": rr2,
            "feasibility": "possible" if rr2 >= RR_MIN else "unlikely",
            "trigger_condition": "wait for breakout failure confirmation candle",
        })

    if direction == "LONG":
        reclaim_entry = round(stop * 1.01, 2) if stop < entry else round(entry * 1.005, 2)
    else:
        reclaim_entry = round(stop * 0.99, 2) if stop > entry else round(entry * 0.995, 2)
    risk3 = abs(reclaim_entry - stop)
    if risk3 > 0:
        target3 = round(reclaim_entry + risk3 * RR_MIN, 2) if direction == "LONG" else round(reclaim_entry - risk3 * RR_MIN, 2)
        rr3 = _compute_rr(reclaim_entry, stop, target3)
        plans.append({
            "plan": "reclaim_confirmation_entry", "entry": reclaim_entry,
            "stop": stop, "target": target3, "rr": rr3,
            "feasibility": "possible" if rr3 >= RR_MIN else "unlikely",
            "trigger_condition": "wait for reclaim confirmation candle",
        })

    return plans


def _determine_next_step(bucket: str, pattern: dict, lifecycle: str, raw_anomaly: dict | None = None) -> str:
    if bucket == "WATCHLIST_READY":
        if lifecycle == "CONFIRMED_BUT_RR_POOR":
            return "wait for pullback to improve RR"
        return "wait for entry trigger confirmation"
    if bucket == "NEAR_MISS_RR":
        if pattern.get("direction", "LONG") == "LONG":
            return "wait for pullback to lower entry for RR >= 4"
        return "wait for retest to lower entry for RR >= 4"
    if bucket == "NEAR_MISS_PSYCHOLOGY":
        return "wait for stronger psychological evidence"
    if bucket == "RAW_TRAP_DETECTED":
        raw = raw_anomaly or {}
        if raw.get("compression", 0) > 0:
            return "watch compression breakout/failure"
        if raw.get("sweep", 0) > 0:
            return "wait for failed retest below swept high"
        if raw.get("wick_rejection", 0) > 0:
            return "wait for reclaim above breakdown level"
        if raw.get("volatility_expansion", 0) > 0:
            return "avoid if next candle expands against thesis"
        pid = pattern.get("pattern_id", "")
        if "breakout" in pid:
            return "wait for failed retest of breakout level"
        if "pump" in pid or "bounce" in pid:
            return "wait for lower high after pump"
        if "panic" in pid or "flush" in pid:
            return "wait for reclaim above breakdown level"
        if "compression" in pid:
            return "wait for volatility expansion"
        return "wait for formation completion"
    if bucket == "EXECUTABLE_CANDIDATE":
        return "setup fully formed, ready for execution review"
    if pattern.get("entry", 0) and pattern.get("reject_reason", "").startswith("entry"):
        return "avoid because entry is already late"
    return "no actionable setup"


def _required_entry_for_rr4(pattern: dict) -> float:
    entry = pattern.get("entry", 0)
    stop = pattern.get("stop", 0)
    direction = pattern.get("direction", "LONG")
    risk = abs(entry - stop)
    if risk <= 0:
        return 0.0
    if direction == "LONG":
        return round(stop + risk * RR_MIN / 2, 2)
    return round(stop - risk * RR_MIN / 2, 2)


def run_diagnostics() -> dict:
    dux = _read_json(os.path.join(RESULTS_DIR, "dux_pattern_report.json"))
    psych = _read_json(os.path.join(RESULTS_DIR, "psychology_alpha_report.json"))
    universe = _read_json(os.path.join(RESULTS_DIR, "bingx_universe.json"))

    patterns = dux.get("patterns", [])
    psych_patterns = psych.get("patterns", []) if psych else []
    psych_map = {}
    for pp in psych_patterns:
        key = f"{pp.get('symbol', '')}|{pp.get('timeframe', '')}|{pp.get('pattern_id', '')}"
        psych_map[key] = pp

    scan_symbols = dux.get("dux_scan_universe_size", universe.get("scan_universe_size", 0))
    total_contracts = dux.get("total_raw_contracts", universe.get("total_raw_contracts", 0))
    st_scanned = dux.get("symbol_timeframes_scanned", 0)

    rejection_counts = {r: 0 for r in REJECTION_REASONS}
    raw_anomaly_counts = {r: 0 for r in RAW_ANOMALY_CATEGORIES}
    lifecycle_counts = {l: 0 for l in LIFECYCLE_STAGES}
    bucket_counts = {b: 0 for b in BUCKETS}

    classified = []
    raw_anomaly_cache = {}

    for p in patterns:
        sym = p.get("symbol", "")
        tf = p.get("timeframe", "")
        key = f"{sym}|{tf}|{p.get('pattern_id', '')}"
        psych_data = psych_map.get(key)

        cache_key = f"{sym}|{tf}"
        if cache_key not in raw_anomaly_cache:
            raw_anomaly_cache[cache_key] = _compute_raw_anomaly_score(sym, tf)
        raw_data = raw_anomaly_cache[cache_key]

        bucket = _classify_bucket(p, psych_data, raw_data)
        lifecycle = _classify_lifecycle(p, bucket, psych_data, raw_data)
        rejection = _assign_rejection_reason(p, bucket, psych_data, raw_data)

        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        rejection_counts[rejection] = rejection_counts.get(rejection, 0) + 1
        lifecycle_counts[lifecycle] = lifecycle_counts.get(lifecycle, 0) + 1

        for cat in RAW_ANOMALY_CATEGORIES:
            if raw_data.get(cat.lower(), 0) > 0:
                raw_anomaly_counts[cat] = raw_anomaly_counts.get(cat, 0) + 1

        psych_score = psych_data.get("psychology_score", 0) if psych_data else 0
        scores = psych_data.get("scores", {}) if psych_data else {}
        trap_score = scores.get("trap_quality", 0)
        vol_score = scores.get("volume_momentum", 0)
        struct_score = scores.get("structure", 0)
        liq_score = scores.get("liquidity", 0)
        thesis = psych_data.get("psychology_thesis", "") if psych_data else ""
        rr_raw = p.get("rr_2")
        rr_str = f"{rr_raw}" if rr_raw else "N/A"
        rr_val = float(rr_raw) if rr_raw else 0.0

        entry_plans = _compute_alternative_entries(p)
        required_entry = _required_entry_for_rr4(p)
        next_step = _determine_next_step(bucket, p, lifecycle, raw_data)

        classified.append({
            "symbol": sym, "timeframe": tf,
            "pattern_id": p.get("pattern_id", ""),
            "pattern_name": p.get("pattern_name", ""),
            "direction": p.get("direction", "UNKNOWN"),
            "entry": p.get("entry"), "stop": p.get("stop"),
            "target": p.get("target_2"),
            "current_rr": rr_str, "rr_value": rr_val,
            "psychology_score": psych_score,
            "trap_score": trap_score, "volume_score": vol_score,
            "structure_score": struct_score, "liquidity_score": liq_score,
            "psychology_thesis": thesis,
            "bucket": bucket, "lifecycle": lifecycle,
            "rejection_reason": rejection, "next_step": next_step,
            "required_entry_for_rr4": required_entry,
            "alternative_entries": entry_plans,
            "raw_anomaly_score": raw_data["raw_anomaly_score"],
            "anomalies": raw_data["anomalies"],
            "top_anomaly": raw_data["top_anomaly"],
            "volatility_expansion": raw_data["volatility_expansion"],
            "volume_anomaly": raw_data["volume_anomaly"],
            "extension": raw_data["extension"],
            "wick_rejection": raw_data["wick_rejection"],
            "sweep": raw_data["sweep"],
            "compression": raw_data["compression"],
            "relative_momentum": raw_data["relative_momentum"],
        })

    # Sort by actionability score descending
    classified.sort(key=lambda x: _actionability_score(x), reverse=True)

    # Build watchlist: filter valid entries, max 3 per symbol, max 30 total
    watchlist = []
    symbol_count = {}
    for c in classified:
        if not _is_valid_watchlist_entry(c):
            continue
        sym = c.get("symbol", "")
        if symbol_count.get(sym, 0) >= 3:
            continue
        c["rank"] = len(watchlist) + 1
        watchlist.append(c)
        symbol_count[sym] = symbol_count.get(sym, 0) + 1
        if len(watchlist) >= 30:
            break

    top_rejection = max(rejection_counts, key=rejection_counts.get) if rejection_counts else "NONE"
    best_watchlist = None
    for c in classified:
        if c["bucket"] in ("WATCHLIST_READY", "NEAR_MISS_RR", "NEAR_MISS_PSYCHOLOGY", "EXECUTABLE_CANDIDATE"):
            best_watchlist = c
            break
    if not best_watchlist:
        for c in classified:
            if c["raw_anomaly_score"] >= RAW_ANOMALY_WATCH_MIN:
                best_watchlist = c
                break

    formal_traps = bucket_counts.get("EXECUTABLE_CANDIDATE", 0) + bucket_counts.get("WATCHLIST_READY", 0) + bucket_counts.get("NEAR_MISS_RR", 0) + bucket_counts.get("NEAR_MISS_PSYCHOLOGY", 0) + bucket_counts.get("RAW_TRAP_DETECTED", 0)
    total_raw_anomalies = sum(raw_anomaly_counts.values())
    observe_count = sum(1 for c in classified if c["raw_anomaly_score"] >= RAW_ANOMALY_OBSERVE_MIN and c["raw_anomaly_score"] < RAW_ANOMALY_NEAR_MISS_MIN and c["bucket"] == "REJECTED")
    dead_setup_count = lifecycle_counts.get("DEAD_SETUP", 0)

    report = {
        "mode": "near_miss_diagnostics",
        "research_only": True,
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "timestamp": datetime.now().isoformat(),
        "total_raw_contracts": total_contracts,
        "scan_symbols": scan_symbols,
        "symbol_timeframes_scanned": st_scanned,
        "total_patterns_analyzed": len(patterns),
        "formal_dux_traps_detected": formal_traps,
        "raw_anomalies_detected": total_raw_anomalies,
        "bucket_counts": bucket_counts,
        "rejection_reason_counts": rejection_counts,
        "raw_anomaly_counts": raw_anomaly_counts,
        "lifecycle_counts": lifecycle_counts,
        "top_rejection_reason": top_rejection,
        "executable_candidate_count": bucket_counts.get("EXECUTABLE_CANDIDATE", 0),
        "watchlist_ready_count": bucket_counts.get("WATCHLIST_READY", 0),
        "near_miss_rr_count": bucket_counts.get("NEAR_MISS_RR", 0),
        "near_miss_psychology_count": bucket_counts.get("NEAR_MISS_PSYCHOLOGY", 0),
        "raw_trap_detected_count": bucket_counts.get("RAW_TRAP_DETECTED", 0),
        "observe_only_count": observe_count,
        "dead_setup_count": dead_setup_count,
        "best_watchlist_candidate": best_watchlist,
        "top_30_watchlist": watchlist,
        "all_classified": classified,
    }

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2)

    _write_watchlist_jsonl(watchlist)
    _write_text_report(report, watchlist, best_watchlist, top_rejection, raw_anomaly_counts)
    return report


def _write_watchlist_jsonl(watchlist: list[dict]):
    os.makedirs(STATE_DIR, exist_ok=True)
    try:
        existing = _read_jsonl(WATCHLIST_PATH)
    except Exception:
        existing = []
    seen_keys = set()
    for e in existing:
        seen_keys.add(f"{e.get('symbol', '')}|{e.get('timeframe', '')}")
    with open(WATCHLIST_PATH, "a") as f:
        for c in watchlist:
            key = f"{c.get('symbol', '')}|{c.get('timeframe', '')}"
            if key not in seen_keys:
                entry = {
                    "timestamp": datetime.now().isoformat(),
                    "rank": watchlist.index(c) + 1,
                    "symbol": c["symbol"], "timeframe": c["timeframe"],
                    "pattern_name": c.get("pattern_name", ""),
                    "direction": c.get("direction", ""),
                    "bucket": c["bucket"],
                    "psychology_score": c.get("psychology_score"),
                    "current_rr": c.get("current_rr", "N/A"),
                    "required_entry_for_rr4": c.get("required_entry_for_rr4"),
                    "next_step": c.get("next_step", ""),
                    "raw_anomaly_score": c.get("raw_anomaly_score", 0),
                    "top_anomaly": c.get("top_anomaly", ""),
                }
                f.write(json.dumps(entry) + "\n")
                seen_keys.add(key)


def _write_text_report(report: dict, watchlist: list[dict],
                        best_watchlist: dict | None, top_rejection: str,
                        raw_anomaly_counts: dict):
    lines = [
        "=" * 60,
        "  NEAR-MISS DIAGNOSTIC REPORT",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  BingX contracts:        {report['total_raw_contracts']}",
        f"  Scan symbols:           {report['scan_symbols']}",
        f"  Symbol-timeframes:      {report['symbol_timeframes_scanned']}",
        f"  Total patterns analyzed: {report['total_patterns_analyzed']}",
        f"  Formal Dux traps:       {report['formal_dux_traps_detected']}",
        f"  Raw anomalies:          {report['raw_anomalies_detected']}",
        "",
        "  BUCKET BREAKDOWN:",
        f"    EXECUTABLE_CANDIDATE:    {report['executable_candidate_count']}",
        f"    WATCHLIST_READY:         {report['watchlist_ready_count']}",
        f"    NEAR_MISS_RR:            {report['near_miss_rr_count']}",
        f"    NEAR_MISS_PSYCHOLOGY:    {report['near_miss_psychology_count']}",
        f"    RAW_TRAP_DETECTED:       {report['raw_trap_detected_count']}",
        f"    OBSERVE_ONLY:            {report.get('observe_only_count', 0)}",
        f"    DEAD_SETUP:              {report.get('dead_setup_count', 0)}",
        "",
        "  REJECTION REASON COUNTS:",
    ]
    for reason, count in sorted(report.get("rejection_reason_counts", {}).items(),
                                  key=lambda x: -x[1]):
        if count > 0:
            lines.append(f"    {reason}: {count}")
    lines += [
        f"  Top rejection reason: {top_rejection}",
        "",
        "  RAW ANOMALY OBSERVATIONS:",
    ]
    for cat, count in sorted(raw_anomaly_counts.items(), key=lambda x: -x[1]):
        if count > 0:
            lines.append(f"    {cat}: {count}")
    lines.append("")

    if best_watchlist:
        lines += [
            "  BEST WATCHLIST CANDIDATE:",
            f"    {best_watchlist.get('pattern_name', 'N/A')} on {best_watchlist['symbol']} {best_watchlist['timeframe']}",
            f"    Direction: {best_watchlist.get('direction', 'N/A')}  Bucket: {best_watchlist['bucket']}",
            f"    Psychology Score: {best_watchlist.get('psychology_score', 'N/A')}",
            f"    Raw Anomaly Score: {best_watchlist.get('raw_anomaly_score', 0)}",
            f"    Top Anomaly: {best_watchlist.get('top_anomaly', 'N/A')}",
            f"    Current RR: 1:{best_watchlist.get('current_rr', 'N/A')}",
            f"    What must happen next: {best_watchlist.get('next_step', '')}",
            "",
        ]

    if watchlist:
        lines += [
            "  TOP 30 REAL WATCHLIST:",
            "",
            "  {:<3s} {:<16s} {:<6s} {:<24s} {:<4s} {:<18s} {:<5s} {:<6s} {:s}".format(
                "Rk", "Symbol", "TF", "Pattern", "Dir", "Bucket", "Psych", "RR", "Anomaly"),
            "  " + "-" * 110,
        ]
        for c in watchlist:
            d = c.get("direction", "N/A")[:4] if c.get("direction") else "N/A"
            psych = str(c.get("psychology_score", "N/A")) if c.get("psychology_score") is not None else "N/A"
            rr = str(c.get("current_rr", "N/A")) if c.get("current_rr") else "N/A"
            top_a = c.get("top_anomaly", "")[:12] if c.get("top_anomaly") else "N/A"
            lines.append("  {:<3d} {:<16s} {:<6s} {:<24s} {:<4s} {:<18s} {:<5s} {:<6s} {:s}".format(
                c["rank"], c["symbol"], c["timeframe"], c.get("pattern_name", "")[:24],
                d, c["bucket"], psych, rr, top_a))
        lines.append("")
    else:
        lines += [
            "  TOP 30 REAL WATCHLIST: NONE",
            "  Reason: no anomaly above threshold",
            "",
        ]

    lines += [
        "  WARNING: This system is not approved for live trading.",
        "",
        "=" * 60,
    ]

    with open(TXT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n[JSON] {JSON_PATH}")
    print(f"[TXT]  {TXT_PATH}")
    print(f"[WATCHLIST] {WATCHLIST_PATH}")


def main():
    report = run_diagnostics()
    return 0


if __name__ == "__main__":
    sys.exit(main())
