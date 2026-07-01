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
    "ARBITER_ELIGIBLE",
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


def _load_watchlist_candidates() -> list[dict]:
    """Load and select top watchlist candidates from near_miss_report.json.

    Returns list of candidates to monitor, prioritized and deduplicated.
    """
    near_miss = _read_json(os.path.join(RESULTS_DIR, "near_miss_report.json"))
    classified = near_miss.get("all_classified", [])
    arbiter = _read_json(os.path.join(RESULTS_DIR, "candidate_arbiter_report.json"))
    arbiter_best = arbiter.get("best_candidate") if arbiter else None

    # Filter eligible candidates
    eligible = []
    for c in classified:
        sym = c.get("symbol", "")
        tf = c.get("timeframe", "")
        bucket = c.get("bucket", "REJECTED")
        direction = c.get("direction", "UNKNOWN")
        thesis_type = c.get("thesis_type", "NONE")
        entry = c.get("entry") or c.get("thesis_ideal_entry") or 0
        stop = c.get("stop") or c.get("thesis_stop") or 0
        target = c.get("target") or c.get("thesis_target") or c.get("target_2") or 0
        psych_score = c.get("psychology_score", 0)
        thesis_score = c.get("trade_thesis_score", 0)
        rr = c.get("current_rr") or c.get("rr_2") or 0

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
        # Must have minimum scores
        if psych_score < 50 or thesis_score < 50:
            continue
        # Must be in eligible bucket
        if bucket not in WATCH_BUCKETS_PRIORITY:
            continue
        # Must not be invalidated
        if c.get("rejection_reason") or c.get("trigger_info", {}).get("trigger_status") == "INVALIDATED":
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
            "detection_time": c.get("detection_time", datetime.now().isoformat()),
            "raw_anomaly_score": c.get("raw_anomaly_score", 0),
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

    return selected


def _get_recent_candles(symbol: str, tf: str, limit: int = 20) -> list:
    """Fetch recent candles for a symbol/timeframe.

    Tries API first, falls back to cached data.
    Returns list of candle dicts with at least 'close' and 'high'/'low' fields.
    """
    try:
        from production_replay.bingx_client import get_cached_candles
        candles = get_cached_candles(symbol, tf, limit=limit)
        if candles and len(candles) >= 5:
            return candles
    except Exception:
        pass
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

    candidates = _load_watchlist_candidates()
    active_watchlist = []
    events = []

    waiting_count = 0
    confirmed_count = 0
    invalidated_count = 0
    expired_count = 0

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

    for c in candidates:
        sym = c["symbol"]
        tf = c["timeframe"]

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
        candles = _get_recent_candles(sym, tf, limit=20)
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
        "candidates_watched": len(candidates),
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
        f"  Candidates watched:     {report['candidates_watched']}",
        f"  Active watchlist size:  {report['active_watchlist_size']}",
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
                f"    Reason: {best_waiting.get('reason', '')}",
                "",
            ]

    # Recent events
    lines += ["  RECENT TRIGGER EVENTS:", ""]
    for e in report.get("candidates", [])[:10]:
        lines += [
            f"    {e['symbol']:12s} {e['timeframe']:4s} {e['direction']:5s} "
            f"{e.get('trigger_status', '?'):18s} RR:{e.get('rr', '?'):<6s} "
            f"Price:{e.get('latest_price', '?'):<10s}",
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
