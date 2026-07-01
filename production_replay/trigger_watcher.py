"""Continuous Trigger Watcher — monitors watchlist candidates for trigger confirmation.

Monitors top watchlist setups frequently and confirms/invalidates triggers
using real-time candle data. Runs as --once or --loop --interval N.

Usage:
    python -m production_replay.trigger_watcher --once
    python -m production_replay.trigger_watcher --loop --interval 60
"""

import argparse, json, os, sys, time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.bingx_client import get_all_swap_tickers
from production_replay.bingx_universe import is_crypto_usdt_perp

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
TXT_PATH = os.path.join(RESULTS_DIR, "trigger_watcher_report.txt")
JSON_PATH = os.path.join(RESULTS_DIR, "trigger_watcher_report.json")
EVENTS_PATH = os.path.join(STATE_DIR, "trigger_events.jsonl")
ACTIVE_PATH = os.path.join(STATE_DIR, "trigger_watchlist_active.json")

MAX_WATCHED = 50
MAX_PER_SYMBOL = 2
MAX_PER_SYMBOL_TF_THESIS = 1

# Expiry in minutes per timeframe
EXPIRY_MINUTES = {"5m": 45, "15m": 120, "30m": 240, "1h": 480}

TRIGGER_STATUSES = ["WAITING", "TRIGGER_CONFIRMED", "INVALIDATED", "EXPIRED"]

# Buckets eligible for watching (in priority order)
WATCH_BUCKETS_PRIORITY = [
    "DIAGNOSTIC_EXECUTABLE",
    "NEAR_MISS_PSYCHOLOGY",
    "NEAR_MISS_RR",
    "WATCHLIST_READY",
    "RAW_TRAP_DETECTED",
    "ARBITER_ELIGIBLE",
]

# Priority search keys in near_miss_report.json for candidate lists
CANDIDATE_LIST_KEYS = [
    "top_30_watchlist", "top_watchlist", "watchlist", "candidates",
    "diagnostic_candidates", "thesis_candidates", "validated_candidates",
    "ranked_candidates", "near_miss_candidates", "raw_candidates",
    "all_classified",
]


def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _read_jsonl(path: str) -> list[dict]:
    try:
        with open(path) as f:
            return [json.loads(line) for line in f if line.strip()]
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _append_jsonl(path: str, entry: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def _write_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _normalize_candidate(c: dict) -> dict:
    """Normalize field names so trigger watcher can handle various schemas."""
    norm = dict(c)
    field_map = {
        "tf": "timeframe",
        "pattern": "thesis_type",
        "psych": "psychology_score",
        "tscr": "thesis_score",
        "rr": "current_rr",
        "dir": "direction",
        "p_score": "psychology_score",
        "t_score": "thesis_score",
        "thesis": "thesis_type",
        "entry_price": "entry",
        "stop_loss": "stop",
        "target_price": "target",
    }
    for old, new in field_map.items():
        if old in norm and old != new:
            if new not in norm or not norm.get(new):
                norm[new] = norm[old]
    # Ensure string fields
    for sf in ("symbol", "timeframe", "direction", "thesis_type", "bucket"):
        if sf not in norm:
            norm[sf] = ""
    # Ensure numeric fields
    for nf in ("psychology_score", "thesis_score", "current_rr", "entry", "stop", "target", "rr_2"):
        if nf not in norm:
            norm[nf] = 0
    # Normalize thesis_type from pattern_name if missing
    if not norm.get("thesis_type") and norm.get("pattern_name"):
        norm["thesis_type"] = norm["pattern_name"]
    return norm


def _extract_candidates_from_report(report: dict) -> list[dict]:
    """Extract candidate dicts from near_miss_report.json using multiple strategies."""
    raw_candidates = []

    # Strategy A: check known list keys
    for key in CANDIDATE_LIST_KEYS:
        val = report.get(key)
        if isinstance(val, list) and val:
            if isinstance(val[0], dict):
                raw_candidates.extend(val)

    # Strategy B: inspect all top-level list values for candidate-like dicts
    if not raw_candidates:
        for k, v in report.items():
            if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                sample_keys = set(v[0].keys())
                if sample_keys & {"symbol", "timeframe", "direction"}:
                    raw_candidates.extend(v)

    return raw_candidates


def _is_fresh_near_miss(report: dict) -> bool:
    """Check if near_miss_report.json has fresh content."""
    if not report:
        return False
    count_keys = ["diagnostic_executable_count", "watchlist_ready_count",
                  "near_miss_rr_count", "near_miss_psychology_count",
                  "directional_theses_created"]
    for k in count_keys:
        if report.get(k, 0) > 0:
            return True
    if report.get("all_classified") or report.get("top_30_watchlist"):
        return True
    return False


def _load_stale_jsonl_fallback() -> list[dict]:
    """Load from JSONL as fallback only, filtering stale/rejected entries."""
    entries = _read_jsonl(os.path.join(STATE_DIR, "near_miss_watchlist.jsonl"))
    now_ts = datetime.now().isoformat()
    latest_nm = _read_json(os.path.join(RESULTS_DIR, "near_miss_report.json"))
    nm_ts = latest_nm.get("timestamp", now_ts) if latest_nm else now_ts

    fresh = []
    for e in entries:
        e = _normalize_candidate(e)
        if e.get("bucket") == "REJECTED":
            continue
        if e.get("psychology_score", 0) == 0:
            continue
        rr_val = e.get("current_rr") or e.get("rr_2") or 0
        if rr_val in (0, "N/A", "0"):
            continue
        if e.get("next_step") in ("", "no actionable setup", None):
            continue
        entry_ts = e.get("timestamp", e.get("detection_time", ""))
        if entry_ts and entry_ts < nm_ts:
            continue
        fresh.append(e)
    return fresh


def _load_watchlist_candidates() -> tuple[list[dict], str]:
    """Load and select top watchlist candidates from near_miss_report.json.

    Returns (list of candidates, source_description).
    """
    near_miss = _read_json(os.path.join(RESULTS_DIR, "near_miss_report.json"))
    arbiter = _read_json(os.path.join(RESULTS_DIR, "candidate_arbiter_report.json"))
    arbiter_best = arbiter.get("best_candidate") if arbiter else None

    source = "none"
    raw_candidates = []

    # Priority A: fresh near_miss_report.json
    if _is_fresh_near_miss(near_miss):
        raw_candidates = _extract_candidates_from_report(near_miss)
        source = f"near_miss_report.json ({len(raw_candidates)} raw)"
        # Normalize all candidates
        raw_candidates = [_normalize_candidate(c) for c in raw_candidates]
    else:
        # Priority B: stale JSONL fallback
        raw_candidates = _load_stale_jsonl_fallback()
        source = f"near_miss_watchlist.jsonl (fallback, {len(raw_candidates)} after stale filter)"

    # Filter eligible candidates
    eligible = []
    for c in raw_candidates:
        sym = c.get("symbol", "")
        tf = c.get("timeframe", "")
        bucket = c.get("bucket", "REJECTED")
        direction = c.get("direction", "UNKNOWN")
        thesis_type = c.get("thesis_type", "NONE")
        entry = c.get("entry") or c.get("thesis_ideal_entry") or 0
        stop = c.get("stop") or c.get("thesis_stop") or 0
        target = c.get("target") or c.get("thesis_target") or c.get("target_2") or 0
        psych_score = float(c.get("psychology_score", 0))
        thesis_score = float(c.get("thesis_score", 0) or c.get("trade_thesis_score", 0))
        rr = float(c.get("current_rr") or c.get("rr_2") or 0)

        # Must be crypto USDT perp
        if not is_crypto_usdt_perp(sym):
            continue
        # Must have direction
        if direction not in ("LONG", "SHORT"):
            continue
        # Must have thesis type
        if thesis_type in ("NONE", ""):
            continue
        # Must have valid entry/stop/target
        if not entry or float(entry) <= 0 or not stop or float(stop) <= 0 or not target or float(target) <= 0:
            continue
        # Must have minimum scores (relaxed from Phase 49)
        if psych_score < 30 or thesis_score < 45:
            continue
        # Must be in eligible bucket
        if bucket not in WATCH_BUCKETS_PRIORITY:
            continue
        # Must not be invalidated by trigger watcher
        if c.get("trigger_info", {}).get("trigger_status") == "INVALIDATED":
            continue
        # Must have a valid timeframe
        if tf not in EXPIRY_MINUTES:
            continue

        # Priority rank
        try:
            priority = WATCH_BUCKETS_PRIORITY.index(bucket)
        except ValueError:
            priority = 99

        eligible.append({
            "symbol": sym,
            "timeframe": tf,
            "direction": direction,
            "thesis_type": thesis_type,
            "bucket": bucket,
            "psychology_score": psych_score,
            "thesis_score": thesis_score,
            "rr": rr,
            "entry": float(entry),
            "stop": float(stop),
            "target": float(target),
            "priority": priority,
            "detection_time": c.get("detection_time", c.get("timestamp", datetime.now().isoformat())),
            "raw_anomaly_score": float(c.get("raw_anomaly_score", 0)),
            "pattern_name": c.get("pattern_name", c.get("thesis_type", "N/A")),
        })

    # Sort by priority (lower = better), then by thesis_score descending
    eligible.sort(key=lambda x: (x["priority"], -x["thesis_score"], -x["rr"]))

    # Deduplicate: max 1 per symbol/TF/thesis_type, max 2 per symbol
    selected = []
    seen_st = set()
    seen_symbol_count = {}
    for c in eligible:
        st_key = f"{c['symbol']}|{c['timeframe']}|{c['thesis_type']}"
        if st_key in seen_st:
            continue
        if seen_symbol_count.get(c["symbol"], 0) >= MAX_PER_SYMBOL:
            continue
        seen_st.add(st_key)
        seen_symbol_count[c["symbol"]] = seen_symbol_count.get(c["symbol"], 0) + 1
        selected.append(c)
        if len(selected) >= MAX_WATCHED:
            break

    # Ensure arbiter best candidate is included if not already
    if arbiter_best:
        ab_sym = arbiter_best.get("symbol", "")
        ab_tf = arbiter_best.get("timeframe", "")
        ab_type = arbiter_best.get("thesis_type", "N/A")
        st_key = f"{ab_sym}|{ab_tf}|{ab_type}"
        if st_key not in seen_st and len(selected) < MAX_WATCHED:
            selected.append({
                "symbol": ab_sym,
                "timeframe": ab_tf,
                "direction": arbiter_best.get("direction", "UNKNOWN"),
                "thesis_type": ab_type,
                "bucket": arbiter_best.get("bucket", "ARBITER_ELIGIBLE"),
                "psychology_score": arbiter_best.get("psychology_score", 0),
                "thesis_score": arbiter_best.get("thesis_score", 0),
                "rr": arbiter_best.get("rr", 0),
                "entry": arbiter_best.get("entry", 0),
                "stop": arbiter_best.get("stop", 0),
                "target": arbiter_best.get("target", 0),
                "priority": 0,
                "detection_time": datetime.now().isoformat(),
                "raw_anomaly_score": arbiter_best.get("raw_anomaly_score", 0),
                "pattern_name": ab_type,
            })

    return selected, source


def _parse_candles(raw_data: list) -> list[dict]:
    """Parse BingX klines response into list of candle dicts.

    Handles both list-of-lists format and list-of-dicts format.
    """
    candles = []
    for item in raw_data:
        try:
            if isinstance(item, dict):
                candles.append({
                    "timestamp": int(item.get("time", item.get("timestamp", 0))),
                    "open": float(item["open"]),
                    "high": float(item["high"]),
                    "low": float(item["low"]),
                    "close": float(item["close"]),
                    "volume": float(item.get("volume", 0)),
                })
            elif isinstance(item, (list, tuple)):
                # BingX list format: [time, open, high, low, close, volume, close_time, quote_vol]
                candles.append({
                    "timestamp": int(item[0]),
                    "open": float(item[1]),
                    "high": float(item[2]),
                    "low": float(item[3]),
                    "close": float(item[4]),
                    "volume": float(item[5]) if len(item) > 5 else 0,
                })
        except (ValueError, TypeError, IndexError, KeyError):
            continue
    candles.sort(key=lambda x: x["timestamp"])
    # Remove duplicates by timestamp
    seen_ts = set()
    unique = []
    for c in candles:
        if c["timestamp"] not in seen_ts:
            seen_ts.add(c["timestamp"])
            unique.append(c)
    return unique


def _get_recent_candles(symbol: str, tf: str, limit: int = 120) -> list[dict]:
    """Fetch recent candles for a symbol/timeframe via BingX klines API.

    Returns list of candle dicts parsed via _parse_candles.
    Returns [] on any failure (caller handles gracefully).
    """
    try:
        from production_replay.bingx_client import get_klines, load_credentials
        base = load_credentials()["base_url"]
        # Normalize symbol: BingX API accepts hyphenated format
        api_symbol = symbol if "-" in symbol else symbol
        resp = get_klines(api_symbol, tf, limit, base)
        if not resp.get("success"):
            return []
        data = resp.get("data", {})
        # BingX response wrapper may be nested: {"code":0, "data": [...]}
        # or direct: {"data": [...]}
        raw_data = None
        if isinstance(data, dict):
            if "data" in data:
                raw_data = data["data"]
            elif "code" in data:
                raw_data = data.get("code")
        elif isinstance(data, list):
            raw_data = data
        if not isinstance(raw_data, list):
            return []
        return _parse_candles(raw_data)
    except Exception:
        return []


def _check_trigger(candidate: dict, candles: list) -> dict:
    """Check trigger status for a single candidate against recent candles.

    Returns dict with trigger_status, reason, latest_price, latest_candle_time.
    """
    thesis_type = candidate.get("thesis_type", "NONE")
    direction = candidate.get("direction", "UNKNOWN")
    entry = candidate.get("entry", 0)
    stop = candidate.get("stop", 0)

    if thesis_type == "COMPRESSION":
        return {
            "trigger_status": "WAITING",
            "reason": "Compression setups cannot trigger alone; waiting for breakout failure or sweep",
            "latest_price": None,
            "latest_candle_time": None,
        }

    if not candles or len(candles) < 5:
        return {
            "trigger_status": "WAITING",
            "reason": "Insufficient candle data",
            "latest_price": None,
            "latest_candle_time": None,
        }

    def _price(idx: int, field: str = "close") -> float:
        if idx < 0:
            idx = len(candles) + idx
        if 0 <= idx < len(candles):
            cdl = candles[idx]
            if isinstance(cdl, dict):
                return float(cdl.get(field, 0))
            fields = {"close": 4, "high": 2, "low": 3, "open": 1}
            idx_f = fields.get(field, 4)
            return float(cdl[idx_f]) if isinstance(cdl, (list, tuple)) and len(cdl) > idx_f else 0
        return 0

    latest = candles[-1]
    latest_close = _price(-1, "close")
    latest_high = _price(-1, "high")
    latest_low = _price(-1, "low")
    prev_close = _price(-2, "close") if len(candles) >= 2 else latest_close

    if isinstance(latest, dict):
        latest_time = latest.get("timestamp", latest.get("time", latest.get("open_time", "")))
    else:
        latest_time = latest[0] if isinstance(latest, (list, tuple)) and len(latest) > 0 else ""

    trigger_status = "WAITING"
    reason = ""

    # Use candles before the latest for reference range (allow latest to break through)
    ref_range = candles[:-1] if len(candles) > 1 else candles

    def _ref_price(idx: int, field: str = "close") -> float:
        if idx < 0:
            idx = len(ref_range) + idx
        if 0 <= idx < len(ref_range):
            cdl = ref_range[idx]
            if isinstance(cdl, dict):
                return float(cdl.get(field, 0))
            fields = {"close": 4, "high": 2, "low": 3, "open": 1}
            idx_f = fields.get(field, 4)
            return float(cdl[idx_f]) if isinstance(cdl, (list, tuple)) and len(cdl) > idx_f else 0
        return 0

    if thesis_type == "UPPER_WICK_EXTENSION" and direction == "SHORT":
        wick_high = max(_ref_price(i, "high") for i in range(len(ref_range)))
        wick_mid = (wick_high + max(_ref_price(i, "close") for i in range(len(ref_range)))) / 2
        if latest_close < wick_mid:
            trigger_status = "TRIGGER_CONFIRMED"
            reason = f"Close {latest_close} below wick midpoint {wick_mid:.2f}"
        elif latest_high > wick_high:
            trigger_status = "INVALIDATED"
            reason = f"High {latest_high} above wick high {wick_high}"
        else:
            reason = f"Waiting: close {latest_close} still above wick mid {wick_mid:.2f}"

    elif thesis_type == "LOWER_WICK_EXTENSION" and direction == "LONG":
        wick_low = min(_ref_price(i, "low") for i in range(len(ref_range)))
        wick_mid = (wick_low + min(_ref_price(i, "close") for i in range(len(ref_range)))) / 2
        if latest_close > wick_mid:
            trigger_status = "TRIGGER_CONFIRMED"
            reason = f"Close {latest_close} above wick midpoint {wick_mid:.2f}"
        elif latest_low < wick_low:
            trigger_status = "INVALIDATED"
            reason = f"Low {latest_low} below wick low {wick_low}"
        else:
            reason = f"Waiting: close {latest_close} still below wick mid {wick_mid:.2f}"

    elif thesis_type == "SWEEP_HIGH" and direction == "SHORT":
        sweep_high = max(_ref_price(i, "high") for i in range(len(ref_range)))
        if latest_close < sweep_high:
            trigger_status = "TRIGGER_CONFIRMED"
            reason = f"Close {latest_close} back below swept high {sweep_high}"
        elif latest_high > sweep_high * 1.005:
            trigger_status = "INVALIDATED"
            reason = f"High {latest_high} held above swept high {sweep_high}"
        else:
            reason = f"Waiting: close {latest_close} at/near swept high {sweep_high}"

    elif thesis_type == "SWEEP_LOW" and direction == "LONG":
        sweep_low = min(_ref_price(i, "low") for i in range(len(ref_range)))
        if latest_close > sweep_low:
            trigger_status = "TRIGGER_CONFIRMED"
            reason = f"Close {latest_close} back above swept low {sweep_low}"
        elif latest_low < sweep_low * 0.995:
            trigger_status = "INVALIDATED"
            reason = f"Low {latest_low} held below swept low {sweep_low}"
        else:
            reason = f"Waiting: close {latest_close} at/near swept low {sweep_low}"

    else:
        reason = f"Unknown thesis_type/direction: {thesis_type}/{direction}"

    return {
        "trigger_status": trigger_status,
        "reason": reason,
        "latest_price": latest_close,
        "latest_candle_time": latest_time,
    }


def _check_expiry(candidate: dict, now: datetime) -> tuple[bool, str]:
    """Check if a watched candidate has expired.

    Returns (expired, reason).
    """
    tf = candidate.get("timeframe", "5m")
    expiry_min = EXPIRY_MINUTES.get(tf, 45)
    detection_time_str = candidate.get("detection_time", "")
    if not detection_time_str:
        return False, ""
    try:
        detection_dt = datetime.fromisoformat(detection_time_str)
    except (ValueError, TypeError):
        return False, ""
    age = (now - detection_dt).total_seconds() / 60.0
    if age > expiry_min:
        return True, f"Expired after {age:.0f}m (max {expiry_min}m for {tf})"
    return False, ""


def run_trigger_watcher() -> dict:
    now = datetime.now()
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)

    candidates, source = _load_watchlist_candidates()
    active_watchlist = []
    events = []

    waiting_count = 0
    confirmed_count = 0
    invalidated_count = 0
    expired_count = 0
    candle_attempted = 0
    candle_success = 0
    candle_failed = 0

    ticker_map = {}
    try:
        ticker_result = get_all_swap_tickers()
        if ticker_result["success"]:
            raw = ticker_result.get("data", {})
            items = raw.get("data", raw) if isinstance(raw, dict) else raw
            if isinstance(items, list):
                for t in items:
                    ticker_map[t.get("symbol", "")] = float(t.get("lastPrice", 0))
    except Exception:
        pass

    # Min candles per timeframe
    MIN_CANDLES = {"5m": 20, "15m": 20, "30m": 30, "1h": 30}
    CANDLE_LIMITS = {"5m": 60, "15m": 60, "30m": 120, "1h": 120}

    for c in candidates:
        sym = c["symbol"]
        tf = c["timeframe"]
        min_req = MIN_CANDLES.get(tf, 20)
        fetch_limit = CANDLE_LIMITS.get(tf, 120)

        # Check expiry first
        expired, expiry_reason = _check_expiry(c, now)
        if expired:
            expired_count += 1
            event = {
                **c,
                "trigger_status": "EXPIRED",
                "trigger_condition": "expiry",
                "reason": expiry_reason,
                "latest_price": ticker_map.get(sym),
                "latest_candle_time": None,
                "checked_at": now.isoformat(),
            }
            events.append(event)
            _append_jsonl(EVENTS_PATH, event)
            active_watchlist.append(event)
            continue

        # Fetch candles for this symbol/TF
        candle_attempted += 1
        candles = _get_recent_candles(sym, tf, limit=fetch_limit)
        if candles and len(candles) >= min_req:
            candle_success += 1
        else:
            candle_failed += 1
        if not candles and sym in ticker_map:
            candles = [{"close": ticker_map[sym]}]

        # Check trigger
        trigger_result = _check_trigger(c, candles)
        trigger_status = trigger_result["trigger_status"]

        event = {
            **c,
            "trigger_status": trigger_status,
            "trigger_condition": c.get("thesis_type", "N/A"),
            "reason": trigger_result.get("reason", ""),
            "latest_price": trigger_result.get("latest_price", ticker_map.get(sym)),
            "latest_candle_time": trigger_result.get("latest_candle_time"),
            "checked_at": now.isoformat(),
        }

        if trigger_status == "TRIGGER_CONFIRMED":
            confirmed_count += 1
            _append_jsonl(EVENTS_PATH, event)
        elif trigger_status == "INVALIDATED":
            invalidated_count += 1
            _append_jsonl(EVENTS_PATH, event)
        elif trigger_status == "WAITING":
            waiting_count += 1

        events.append(event)
        active_watchlist.append(event)

    # Save active watchlist
    _write_json(ACTIVE_PATH, {
        "generated_at": now.isoformat(),
        "total_active": len(active_watchlist),
        "waiting": waiting_count,
        "confirmed": confirmed_count,
        "invalidated": invalidated_count,
        "expired": expired_count,
        "candidates": active_watchlist,
    })

    # Find best confirmed candidate
    best_confirmed = None
    for e in events:
        if e["trigger_status"] == "TRIGGER_CONFIRMED":
            if best_confirmed is None or e.get("rr", 0) > best_confirmed.get("rr", 0):
                best_confirmed = e

    # Find best waiting candidate
    best_waiting = None
    for e in events:
        if e["trigger_status"] == "WAITING":
            if best_waiting is None or e.get("rr", 0) > best_waiting.get("rr", 0):
                best_waiting = e

    report = {
        "mode": "trigger_watcher",
        "research_only": True,
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "timestamp": now.isoformat(),
        "candidate_source": source,
        "candidates_watched": len(candidates),
        "candle_fetch_attempted": candle_attempted,
        "candle_fetch_success": candle_success,
        "candle_fetch_failed": candle_failed,
        "active_watchlist_size": len(active_watchlist),
        "waiting_count": waiting_count,
        "confirmed_count": confirmed_count,
        "invalidated_count": invalidated_count,
        "expired_count": expired_count,
        "best_confirmed_candidate": best_confirmed,
        "best_waiting_candidate": best_waiting,
        "latest_trigger_event": events[-1] if events else None,
        "candidates": events,
    }

    _write_text_report(report)
    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2)
    print(f"[JSON] {JSON_PATH}")
    print(f"[TXT]  {TXT_PATH}")
    return report


def _write_text_report(report: dict):
    lines = [
        "=" * 60,
        "  TRIGGER WATCHER REPORT",
        f"  {report['timestamp']}",
        "=" * 60,
        "",
        f"  Source:                 {report.get('candidate_source', 'unknown')}",
        f"  Candidates watched:     {report['candidates_watched']}",
        f"  Active watchlist size:  {report['active_watchlist_size']}",
        f"  Candle fetch attempted: {report.get('candle_fetch_attempted', 0)}",
        f"  Candle fetch succeeded: {report.get('candle_fetch_success', 0)}",
        f"  Candle fetch failed:    {report.get('candle_fetch_failed', 0)}",
        f"  Waiting:                {report['waiting_count']}",
        f"  TRIGGER_CONFIRMED:      {report['confirmed_count']}",
        f"  INVALIDATED:            {report['invalidated_count']}",
        f"  EXPIRED:                {report['expired_count']}",
        "",
    ]

    best = report.get("best_confirmed_candidate")
    if best:
        lines += [
            "  BEST CONFIRMED CANDIDATE:",
            f"    {best['symbol']} {best['timeframe']} {best['direction']}",
            f"    Thesis: {best.get('thesis_type', 'N/A')}  Bucket: {best.get('bucket', 'N/A')}",
            f"    RR: 1:{best.get('rr', 'N/A')}  Score: {best.get('thesis_score', 'N/A')}",
            f"    Psychology: {best.get('psychology_score', 'N/A')}",
            f"    Reason: {best.get('reason', '')}",
            "",
        ]
    else:
        best_waiting = report.get("best_waiting_candidate")
        if best_waiting:
            lines += [
                "  BEST WAITING CANDIDATE:",
                f"    {best_waiting['symbol']} {best_waiting['timeframe']} {best_waiting['direction']}",
                f"    Thesis: {best_waiting.get('thesis_type', 'N/A')}  Bucket: {best_waiting.get('bucket', 'N/A')}",
                f"    RR: 1:{best_waiting.get('rr', 'N/A')}  Score: {best_waiting.get('thesis_score', 'N/A')}",
                f"    Psychology: {best_waiting.get('psychology_score', 'N/A')}",
                f"    Latest Price: {best_waiting.get('latest_price', 'N/A')}",
                f"    Reason: {best_waiting.get('reason', '')}",
                "",
            ]

    # Recent events
    lines += ["  RECENT TRIGGER EVENTS:", ""]
    for e in report.get("candidates", [])[:10]:
        rr_val = e.get('rr', '?')
        rr_str = f"{rr_val}" if not isinstance(rr_val, str) else rr_val
        price_val = e.get('latest_price', '?')
        price_str = f"{price_val:.4f}" if isinstance(price_val, (int, float)) else (str(price_val) if price_val else '?')
        reason_str = str(e.get('reason', ''))[:30]
        lines += [
            f"    {str(e['symbol']):12s} {str(e['timeframe']):4s} {str(e['direction']):5s} "
            f"{str(e.get('trigger_status', '?')):18s} RR:{rr_str:<6s} "
            f"Price:{price_str:<12s} {reason_str}",
        ]
    lines += [
        "",
        "  WARNING: System not approved for live trading.",
        "",
        "=" * 60,
    ]

    with open(TXT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description="Trigger Watcher")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--loop", action="store_true", help="Run in continuous loop")
    parser.add_argument("--interval", type=int, default=60, help="Loop interval in seconds")
    args = parser.parse_args()

    if args.once:
        run_trigger_watcher()
        return 0

    if args.loop:
        print(f"Trigger watcher loop starting (interval={args.interval}s)")
        while True:
            run_trigger_watcher()
            print(f"Sleeping {args.interval}s...")
            time.sleep(args.interval)

    # Default: run once
    run_trigger_watcher()
    return 0


if __name__ == "__main__":
    sys.exit(main())
