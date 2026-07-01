"""Near-Miss Diagnostic and Watchlist Intelligence.

Reads Dux pattern results and psychology alpha output, classifies every
symbol/timeframe into diagnostic buckets, and produces a near-miss report.

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

RR_MIN = 4.0
PSYCH_WATCH_MIN = 70
PSYCH_ELITE_MIN = 85
NEAR_MISS_PSYCH_MIN = 50
NEAR_MISS_RR_MIN = 2.0

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


def _classify_bucket(pattern: dict, psych: dict | None) -> str:
    rr = pattern.get("rr_2") or 0
    psych_score = psych.get("psychology_score", 0) if psych else 0
    rejected = pattern.get("rejected", True)
    has_trap = pattern.get("pattern_id", "") != "" and pattern.get("direction", "UNKNOWN") != "UNKNOWN"

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
    if has_trap:
        return "RAW_TRAP_DETECTED"
    return "REJECTED"


def _classify_lifecycle(pattern: dict, bucket: str, psych: dict | None) -> str:
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
        if pattern.get("vol_expansion") is True:
            return "TRIGGER_NEAR"
        return "COMPRESSION_BUILDING"
    pid = pattern.get("pattern_id", "")
    if pid and pid != "unknown":
        return "DEAD_SETUP"
    return "DEAD_SETUP"


def _assign_rejection_reason(pattern: dict, bucket: str, psych: dict | None) -> str:
    rr = pattern.get("rr_2") or 0
    psych_score = psych.get("psychology_score", 0) if psych else 0
    if pattern.get("pattern_id", "") == "" or pattern.get("direction", "UNKNOWN") == "UNKNOWN":
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

    # 1. Current market entry
    current_rr = _compute_rr(entry, stop, target) if target else 0
    plans.append({
        "plan": "current_market_entry",
        "entry": entry,
        "stop": stop,
        "target": target,
        "rr": current_rr,
        "feasibility": "ready" if current_rr >= RR_MIN else "needs improvement",
        "trigger_condition": "execute now" if current_rr >= RR_MIN else "wait for better entry",
    })

    # 2. Pullback/retest entry
    if direction == "LONG":
        pullback_entry = round(entry * 0.985, 2)
        new_risk = abs(pullback_entry - stop)
        if new_risk > 0:
            pullback_target = round(pullback_entry + new_risk * RR_MIN, 2)
            pullback_rr = _compute_rr(pullback_entry, stop, pullback_target)
            plans.append({
                "plan": "pullback_retest_entry",
                "entry": pullback_entry,
                "stop": stop,
                "target": pullback_target,
                "rr": pullback_rr,
                "feasibility": "possible" if pullback_rr >= RR_MIN else "unlikely",
                "trigger_condition": "wait for pullback to entry level",
            })
    else:
        pullback_entry = round(entry * 1.015, 2)
        new_risk = abs(pullback_entry - stop)
        if new_risk > 0:
            pullback_target = round(pullback_entry - new_risk * RR_MIN, 2)
            pullback_rr = _compute_rr(pullback_entry, stop, pullback_target)
            plans.append({
                "plan": "pullback_retest_entry",
                "entry": pullback_entry,
                "stop": stop,
                "target": pullback_target,
                "rr": pullback_rr,
                "feasibility": "possible" if pullback_rr >= RR_MIN else "unlikely",
                "trigger_condition": "wait for pullback to entry level",
            })

    # 3. Breakout failure confirmation
    if direction == "SHORT":
        better_entry = round(pattern.get("pump_high", entry * 1.02), 2)
    else:
        better_entry = round(pattern.get("flush_low", entry * 0.98), 2)
    risk2 = abs(better_entry - stop)
    if risk2 > 0 and better_entry != entry:
        target2 = round(better_entry + risk2 * RR_MIN, 2) if direction == "LONG" else round(better_entry - risk2 * RR_MIN, 2)
        rr2 = _compute_rr(better_entry, stop, target2)
        plans.append({
            "plan": "breakout_failure_confirmation",
            "entry": better_entry,
            "stop": stop,
            "target": target2,
            "rr": rr2,
            "feasibility": "possible" if rr2 >= RR_MIN else "unlikely",
            "trigger_condition": "wait for breakout failure confirmation candle",
        })

    # 4. Reclaim confirmation
    if direction == "LONG":
        reclaim_entry = round(stop * 1.01, 2) if stop < entry else round(entry * 1.005, 2)
    else:
        reclaim_entry = round(stop * 0.99, 2) if stop > entry else round(entry * 0.995, 2)
    risk3 = abs(reclaim_entry - stop)
    if risk3 > 0:
        target3 = round(reclaim_entry + risk3 * RR_MIN, 2) if direction == "LONG" else round(reclaim_entry - risk3 * RR_MIN, 2)
        rr3 = _compute_rr(reclaim_entry, stop, target3)
        plans.append({
            "plan": "reclaim_confirmation_entry",
            "entry": reclaim_entry,
            "stop": stop,
            "target": target3,
            "rr": rr3,
            "feasibility": "possible" if rr3 >= RR_MIN else "unlikely",
            "trigger_condition": "wait for reclaim confirmation candle",
        })

    return plans


def _determine_next_step(bucket: str, pattern: dict, lifecycle: str) -> str:
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


def _price_for_rr(entry: float, stop: float, target_rr: float, direction: str) -> float:
    risk = abs(entry - stop)
    if risk <= 0:
        return 0.0
    if direction == "LONG":
        return round(stop + risk * (target_rr + 0.01), 2)
    return round(stop - risk * (target_rr + 0.01), 2)


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

    buckets = {b: [] for b in BUCKETS}
    rejection_counts = {r: 0 for r in REJECTION_REASONS}
    lifecycle_counts = {l: 0 for l in LIFECYCLE_STAGES}
    bucket_counts = {b: 0 for b in BUCKETS}

    classified = []

    for p in patterns:
        key = f"{p.get('symbol', '')}|{p.get('timeframe', '')}|{p.get('pattern_id', '')}"
        psych_data = psych_map.get(key)
        bucket = _classify_bucket(p, psych_data)
        lifecycle = _classify_lifecycle(p, bucket, psych_data)
        rejection = _assign_rejection_reason(p, bucket, psych_data)

        buckets.setdefault(bucket, []).append(p)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        rejection_counts[rejection] = rejection_counts.get(rejection, 0) + 1
        lifecycle_counts[lifecycle] = lifecycle_counts.get(lifecycle, 0) + 1

        entry_plans = _compute_alternative_entries(p)
        required_entry = _required_entry_for_rr4(p)
        next_step = _determine_next_step(bucket, p, lifecycle)

        psych_score = psych_data.get("psychology_score", 0) if psych_data else 0
        scores = psych_data.get("scores", {}) if psych_data else {}
        trap_score = scores.get("trap_quality", 0)
        vol_score = scores.get("volume_momentum", 0)
        struct_score = scores.get("structure", 0)
        liq_score = scores.get("liquidity", 0)
        thesis = psych_data.get("psychology_thesis", "") if psych_data else ""
        rr_str = f"{p.get('rr_2', 'N/A')}" if p.get('rr_2') else "N/A"

        classified.append({
            "symbol": p.get("symbol", ""),
            "timeframe": p.get("timeframe", ""),
            "pattern_id": p.get("pattern_id", ""),
            "pattern_name": p.get("pattern_name", ""),
            "direction": p.get("direction", "UNKNOWN"),
            "entry": p.get("entry"),
            "stop": p.get("stop"),
            "target": p.get("target_2"),
            "current_rr": rr_str,
            "psychology_score": psych_score,
            "trap_score": trap_score,
            "volume_score": vol_score,
            "structure_score": struct_score,
            "liquidity_score": liq_score,
            "psychology_thesis": thesis,
            "bucket": bucket,
            "lifecycle": lifecycle,
            "rejection_reason": rejection,
            "next_step": next_step,
            "required_entry_for_rr4": required_entry,
            "alternative_entries": entry_plans,
        })

    classified.sort(key=lambda x: (
        {"EXECUTABLE_CANDIDATE": 0, "WATCHLIST_READY": 1, "NEAR_MISS_RR": 2,
         "NEAR_MISS_PSYCHOLOGY": 3, "RAW_TRAP_DETECTED": 4, "REJECTED": 5}.get(x["bucket"], 99),
        -(x.get("psychology_score", 0) if x.get("psychology_score") else 0),
    ))

    watchlist = []
    for i, c in enumerate(classified[:30]):
        c["rank"] = i + 1
        watchlist.append(c)

    top_rejection = max(rejection_counts, key=rejection_counts.get) if rejection_counts else "NONE"
    best_watchlist = None
    for c in classified:
        if c["bucket"] in ("WATCHLIST_READY", "NEAR_MISS_RR", "NEAR_MISS_PSYCHOLOGY"):
            best_watchlist = c
            break

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
        "bucket_counts": bucket_counts,
        "rejection_reason_counts": rejection_counts,
        "lifecycle_counts": lifecycle_counts,
        "top_rejection_reason": top_rejection,
        "executable_candidate_count": bucket_counts.get("EXECUTABLE_CANDIDATE", 0),
        "watchlist_ready_count": bucket_counts.get("WATCHLIST_READY", 0),
        "near_miss_rr_count": bucket_counts.get("NEAR_MISS_RR", 0),
        "near_miss_psychology_count": bucket_counts.get("NEAR_MISS_PSYCHOLOGY", 0),
        "raw_trap_detected_count": bucket_counts.get("RAW_TRAP_DETECTED", 0),
        "best_watchlist_candidate": best_watchlist,
        "top_30_watchlist": watchlist,
        "all_classified": classified,
    }

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2)

    _write_watchlist_jsonl(watchlist)
    _write_text_report(report, watchlist, best_watchlist, top_rejection)
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
                    "symbol": c["symbol"],
                    "timeframe": c["timeframe"],
                    "pattern_name": c.get("pattern_name", ""),
                    "direction": c.get("direction", ""),
                    "bucket": c["bucket"],
                    "psychology_score": c.get("psychology_score"),
                    "current_rr": c.get("current_rr", "N/A"),
                    "required_entry_for_rr4": c.get("required_entry_for_rr4"),
                    "next_step": c.get("next_step", ""),
                }
                f.write(json.dumps(entry) + "\n")
                seen_keys.add(key)


def _write_text_report(report: dict, watchlist: list[dict],
                        best_watchlist: dict | None, top_rejection: str):
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
        "",
        "  BUCKET BREAKDOWN:",
        f"    EXECUTABLE_CANDIDATE:    {report['executable_candidate_count']}",
        f"    WATCHLIST_READY:         {report['watchlist_ready_count']}",
        f"    NEAR_MISS_RR:            {report['near_miss_rr_count']}",
        f"    NEAR_MISS_PSYCHOLOGY:    {report['near_miss_psychology_count']}",
        f"    RAW_TRAP_DETECTED:       {report['raw_trap_detected_count']}",
        f"    REJECTED:                {report['bucket_counts'].get('REJECTED', 0)}",
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
        "  LIFECYCLE BREAKDOWN:",
    ]
    for stage, count in sorted(report.get("lifecycle_counts", {}).items(),
                                key=lambda x: -x[1]):
        if count > 0:
            lines.append(f"    {stage}: {count}")
    lines.append("")

    if best_watchlist:
        lines += [
            "  BEST WATCHLIST CANDIDATE:",
            f"    {best_watchlist['pattern_name']} on {best_watchlist['symbol']} {best_watchlist['timeframe']}",
            f"    Direction: {best_watchlist['direction']}  Bucket: {best_watchlist['bucket']}",
            f"    Psychology Score: {best_watchlist.get('psychology_score', 'N/A')}",
            f"    Current RR: 1:{best_watchlist.get('current_rr', 'N/A')}",
            f"    What must happen next: {best_watchlist.get('next_step', '')}",
            "",
        ]

    lines += [
        "  TOP 30 WATCHLIST:",
        "",
        "  {:<3s} {:<16s} {:<6s} {:<24s} {:<4s} {:<18s} {:<5s} {:<6s} {:s}".format(
            "Rk", "Symbol", "TF", "Pattern", "Dir", "Bucket", "Psych", "RR", "Next Step"),
        "  " + "-" * 110,
    ]
    for c in watchlist:
        d = c["direction"][:4] if c.get("direction") else "N/A"
        psych = str(c.get("psychology_score", "N/A")) if c.get("psychology_score") is not None else "N/A"
        rr = str(c.get("current_rr", "N/A")) if c.get("current_rr") else "N/A"
        ns = c.get("next_step", "")[:40]
        lines.append("  {:<3d} {:<16s} {:<6s} {:<24s} {:<4s} {:<18s} {:<5s} {:<6s} {:s}".format(
            c["rank"], c["symbol"], c["timeframe"], c.get("pattern_name", "")[:24],
            d, c["bucket"], psych, rr, ns))
    lines += [
        "",
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
