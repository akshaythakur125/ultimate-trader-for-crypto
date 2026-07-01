"""Psychology Memory & Self-Learning Evidence Engine.

Records every scan snapshot, tracks forward outcomes, and builds
evidence about which psychology patterns actually work.

Usage:
    python -m production_replay.psychology_memory
"""

import json, os, sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.bingx_client import get_klines, load_credentials

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
TXT_PATH = os.path.join(RESULTS_DIR, "psychology_memory_report.txt")
JSON_PATH = os.path.join(RESULTS_DIR, "psychology_memory_report.json")
SCAN_MEMORY_FILE = os.path.join(STATE_DIR, "psychology_scan_memory.jsonl")
OUTCOMES_FILE = os.path.join(STATE_DIR, "psychology_outcomes.jsonl")

LOOKAHEAD_HOURS = [1, 4, 12, 24]
MIN_SAMPLE_INSUFFICIENT = 20
MIN_SAMPLE_WEAK = 50
MIN_SAMPLE_USABLE = 100


def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _load_jsonl(path: str) -> list[dict]:
    try:
        with open(path) as f:
            return [json.loads(l) for l in f if l.strip()]
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _append_jsonl(path: str, entry: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def _record_scan_snapshot(psych: dict):
    top = psych.get("top_ranked", [])[:200]
    best = psych.get("best_candidate")
    ts = datetime.now().isoformat()

    # Also load near-miss watchlist candidates for memory
    nm_path = os.path.join(RESULTS_DIR, "near_miss_report.json")
    try:
        with open(nm_path) as f:
            nm_report = json.load(f)
        nm_watchlist = nm_report.get("top_30_watchlist", [])[:50]
    except (FileNotFoundError, json.JSONDecodeError, Exception):
        nm_watchlist = []

    records = []
    for c in top:
        records.append({
            "snapshot_ts": ts,
            "symbol": c["symbol"],
            "timeframe": c["timeframe"],
            "direction": c["direction"],
            "pattern_name": c["pattern_name"],
            "psychology_thesis": c.get("psychology_thesis", ""),
            "entry": c.get("entry"),
            "stop": c.get("stop"),
            "target_2": c.get("target_2"),
            "rr_2": c.get("rr_2"),
            "psychology_score": c.get("psychology_score", 0),
            "scores": c.get("scores", {}),
            "verdict": c.get("verdict", "REJECT"),
            "reject_reason": c.get("reject_reason", ""),
            "liquidity_warning": c.get("liquidity_warning", "ok"),
            "execution_warning": c.get("execution_warning", "none"),
            "price_at_scan": c.get("entry"),
            "outcome_evaluated": False,
        })
    # Add near-miss watchlist records (bucket-filtered)
    seen_syms = set()
    for c in nm_watchlist:
        key = (c.get("symbol", ""), c.get("timeframe", ""), c.get("pattern_name", ""))
        if key in seen_syms:
            continue
        seen_syms.add(key)
        records.append({
            "snapshot_ts": ts,
            "symbol": c.get("symbol", ""),
            "timeframe": c.get("timeframe", ""),
            "direction": c.get("direction", ""),
            "pattern_name": c.get("pattern_name", ""),
            "psychology_thesis": c.get("psychology_thesis", ""),
            "entry": c.get("entry"),
            "stop": c.get("stop"),
            "target_2": c.get("target", c.get("target_2")),
            "rr_2": float(c.get("current_rr", 0)) if c.get("current_rr", "N/A") != "N/A" else None,
            "psychology_score": c.get("psychology_score", 0),
            "scores": {},
            "verdict": c.get("bucket", "NEAR_MISS"),
            "reject_reason": c.get("rejection_reason", ""),
            "liquidity_warning": "ok",
            "execution_warning": "none",
            "price_at_scan": c.get("entry"),
            "outcome_evaluated": False,
            "bucket": c.get("bucket", "NEAR_MISS"),
            "next_step": c.get("next_step", ""),
        })
    # Cap total records
    records = records[:200]

    if best and best not in records:
        records.append({
            "snapshot_ts": ts,
            "symbol": best["symbol"],
            "timeframe": best["timeframe"],
            "direction": best["direction"],
            "pattern_name": best["pattern_name"],
            "psychology_thesis": best.get("psychology_thesis", ""),
            "entry": best.get("entry"),
            "stop": best.get("stop"),
            "target_2": best.get("target_2"),
            "rr_2": best.get("rr_2"),
            "psychology_score": best.get("psychology_score", 0),
            "scores": best.get("scores", {}),
            "verdict": best.get("verdict", "REJECT"),
            "reject_reason": best.get("reject_reason", ""),
            "liquidity_warning": "ok",
            "execution_warning": "none",
            "price_at_scan": best.get("entry"),
            "outcome_evaluated": False,
        })

    for r in records:
        _append_jsonl(SCAN_MEMORY_FILE, r)
    return len(records)


def _simulate_outcome(candles: list[dict], entry: float, stop: float, target: float,
                      direction: str, max_lookahead: int) -> dict:
    if not candles or len(candles) < 2:
        return {"simulated_outcome": "UNKNOWN_DATA", "max_r": 0.0, "min_r": 0.0,
                "entry_touched": False, "stop_hit": False, "target_1_hit": False,
                "final_target_hit": False, "reason": "insufficient candles"}

    risk = abs(entry - stop)
    if risk <= 0:
        return {"simulated_outcome": "UNKNOWN_DATA", "max_r": 0.0, "min_r": 0.0,
                "entry_touched": False, "stop_hit": False, "target_1_hit": False,
                "final_target_hit": False, "reason": "zero risk"}

    target_1 = entry + (entry - stop) * 1.0 if direction == "LONG" else entry - (stop - entry) * 1.0
    lookahead = min(max_lookahead, len(candles))
    max_fav = 0.0
    max_adv = 0.0
    stop_hit = False
    target_1_hit = False
    final_hit = False
    entry_touched = False
    best_r = 0.0
    worst_r = 0.0

    for i in range(lookahead):
        c = candles[i]
        high = c["high"]
        low = c["low"]

        if direction == "LONG":
            if low <= stop:
                stop_hit = True
            if high >= target_1:
                target_1_hit = True
            if high >= target:
                final_hit = True
            fav = (high - entry) / risk if high > entry else 0.0
            adv = (entry - low) / risk if low < entry else 0.0
        else:
            if high >= stop:
                stop_hit = True
            if low <= target_1:
                target_1_hit = True
            if low <= target:
                final_hit = True
            fav = (entry - low) / risk if low < entry else 0.0
            adv = (high - entry) / risk if high > entry else 0.0

        max_fav = max(max_fav, fav)
        max_adv = max(max_adv, adv)
        if fav > best_r:
            best_r = fav
        worst_r = min(worst_r, -adv)

        if low <= entry <= high or low >= entry >= high:
            entry_touched = True

    if stop_hit and not final_hit:
        outcome = "STOP_FIRST"
    elif final_hit:
        outcome = "TARGET_FIRST"
    elif target_1_hit and not final_hit:
        outcome = "PARTIAL_ONLY"
    elif not entry_touched:
        outcome = "NO_ENTRY"
    else:
        outcome = "EXPIRED"

    return {
        "simulated_outcome": outcome,
        "max_r": round(max_fav, 2),
        "min_r": round(-max_adv, 2),
        "entry_touched": entry_touched,
        "stop_hit": stop_hit,
        "target_1_hit": target_1_hit,
        "final_target_hit": final_hit,
        "best_r": round(best_r, 2),
        "worst_r": round(worst_r, 2),
        "reason": "",
    }


def _evaluate_pending_outcomes(memory: list[dict], outcomes_existing: set) -> tuple[int, int]:
    pending = [r for r in memory if not r.get("outcome_evaluated", False)]
    evaluated = 0
    skipped = 0

    for record in pending:
        sym = record["symbol"]
        tf = record["timeframe"]
        entry = record.get("entry")
        stop = record.get("stop")
        target = record.get("target_2")
        direction = record.get("direction")

        if not entry or not stop or not target or not direction:
            record["outcome_evaluated"] = True
            _append_jsonl(OUTCOMES_FILE, {**record, "simulated_outcome": "INVALID",
                           "reason": "missing entry/stop/target"})
            skipped += 1
            continue

        try:
            base = load_credentials()["base_url"]
            klines = get_klines(sym.replace("-USDT", "-USDT"), tf, 500, base)
            if not klines["success"]:
                skipped += 1
                continue
            data = klines["data"]
            if isinstance(data, dict) and data.get("code") == 0:
                raw = data.get("data", [])
            elif isinstance(data, list):
                raw = data
            else:
                skipped += 1
                continue

            candles = []
            for r in raw:
                try:
                    candles.append({
                        "timestamp": r[0],
                        "open": float(r[1]), "high": float(r[2]),
                        "low": float(r[3]), "close": float(r[4]),
                        "volume": float(r[5]),
                    })
                except (IndexError, ValueError, TypeError):
                    continue

            future = []
            scan_ts_str = record.get("snapshot_ts", "")
            try:
                scan_dt = datetime.fromisoformat(scan_ts_str)
                for c in candles:
                    c_dt = datetime.fromtimestamp(c["timestamp"] / 1000)
                    if c_dt > scan_dt:
                        future.append(c)
            except (ValueError, TypeError):
                future = candles[len(candles) // 2:]

            if len(future) < 2:
                skipped += 1
                continue

            max_candles_needed = 0
            if tf == "5m":
                max_candles_needed = 24 * 12
            elif tf == "15m":
                max_candles_needed = 24 * 4
            elif tf == "30m":
                max_candles_needed = 24 * 2
            else:
                max_candles_needed = 24

            outcome = _simulate_outcome(future[:max_candles_needed], entry, stop, target, direction, len(future))
            _append_jsonl(OUTCOMES_FILE, {**record, **outcome, "outcome_evaluated": True})
            evaluated += 1

        except Exception:
            skipped += 1

    return evaluated, skipped


def _sample_label(n: int) -> str:
    if n < MIN_SAMPLE_INSUFFICIENT:
        return "INSUFFICIENT_EVIDENCE"
    if n < MIN_SAMPLE_WEAK:
        return "WEAK_EVIDENCE"
    if n < MIN_SAMPLE_USABLE:
        return "USABLE_EVIDENCE"
    return "STRONG_EVIDENCE"


def _compute_statistics(outcomes: list[dict]) -> dict:
    stats = {
        "total_outcomes": len(outcomes),
        "overall_target_first_rate": 0.0,
        "overall_stop_first_rate": 0.0,
        "overall_avg_max_r": 0.0,
        "overall_avg_min_r": 0.0,
        "grouped_by_pattern": {},
        "grouped_by_direction": {},
        "grouped_by_timeframe": {},
        "grouped_by_score_band": {},
        "grouped_by_symbol": {},
        "best_pattern": None,
        "worst_pattern": None,
        "best_timeframe": None,
        "worst_timeframe": None,
        "best_score_band": None,
        "dangerous_symbols": [],
        "reliable_symbols": [],
        "sample_labels": {},
    }

    if not outcomes:
        return stats

    tf_count = 0
    stop_count = 0
    total_max_r = 0
    total_min_r = 0
    nz = 0

    groups = {
        "pattern": {},
        "direction": {},
        "timeframe": {},
        "score_band": {},
        "symbol": {},
    }

    for o in outcomes:
        outcome = o.get("simulated_outcome", "UNKNOWN_DATA")
        max_r = o.get("max_r", 0) or 0
        min_r = o.get("min_r", 0) or 0

        if outcome == "TARGET_FIRST":
            tf_count += 1
        elif outcome == "STOP_FIRST":
            stop_count += 1

        total_max_r += max_r
        total_min_r += min_r
        nz += 1

        pid = o.get("pattern_name", "unknown")
        direction = o.get("direction", "UNKNOWN")
        tf = o.get("timeframe", "?")
        score = o.get("psychology_score", 0)
        sym = o.get("symbol", "?")

        for gkey, gval in [("pattern", pid), ("direction", direction),
                           ("timeframe", tf),
                           ("score_band", _band_label(score)),
                           ("symbol", sym)]:
            if gval not in groups[gkey]:
                groups[gkey][gval] = {"n": 0, "tf": 0, "stop": 0,
                                       "sum_max_r": 0.0, "sum_min_r": 0.0}
            grp = groups[gkey][gval]
            grp["n"] += 1
            if outcome == "TARGET_FIRST":
                grp["tf"] += 1
            elif outcome == "STOP_FIRST":
                grp["stop"] += 1
            grp["sum_max_r"] += max_r
            grp["sum_min_r"] += min_r

    stats["overall_target_first_rate"] = round(tf_count / nz, 4) if nz else 0
    stats["overall_stop_first_rate"] = round(stop_count / nz, 4) if nz else 0
    stats["overall_avg_max_r"] = round(total_max_r / nz, 4) if nz else 0
    stats["overall_avg_min_r"] = round(total_min_r / nz, 4) if nz else 0

    def _summarize_group(g: dict) -> list:
        result = []
        for name, d in sorted(g.items(), key=lambda x: x[1]["n"], reverse=True):
            n = d["n"]
            tf_r = d["tf"] / n if n else 0
            result.append({
                "name": name,
                "sample_size": n,
                "sample_label": _sample_label(n),
                "target_first_rate": round(tf_r, 4),
                "stop_first_rate": round(d["stop"] / n, 4) if n else 0,
                "avg_max_r": round(d["sum_max_r"] / n, 4) if n else 0,
                "avg_min_r": round(d["sum_min_r"] / n, 4) if n else 0,
            })
        return result

    stats["grouped_by_pattern"] = list(_summarize_group(groups["pattern"]))
    stats["grouped_by_direction"] = list(_summarize_group(groups["direction"]))
    stats["grouped_by_timeframe"] = list(_summarize_group(groups["timeframe"]))
    stats["grouped_by_score_band"] = list(_summarize_group(groups["score_band"]))
    stats["grouped_by_symbol"] = list(_summarize_group(groups["symbol"]))

    for g in stats["grouped_by_pattern"]:
        key = "best" if g["target_first_rate"] > 0.5 and g["sample_label"] != "INSUFFICIENT_EVIDENCE" else None
        if key == "best":
            stats["best_pattern"] = g
        if g["target_first_rate"] < 0.3 and g["sample_size"] >= MIN_SAMPLE_INSUFFICIENT:
            stats["worst_pattern"] = g

    for g in stats["grouped_by_timeframe"]:
        if g["sample_size"] >= MIN_SAMPLE_INSUFFICIENT:
            if stats["best_timeframe"] is None or g["target_first_rate"] > stats["best_timeframe"]["target_first_rate"]:
                stats["best_timeframe"] = g
            if stats["worst_timeframe"] is None or g["target_first_rate"] < stats["worst_timeframe"]["target_first_rate"]:
                stats["worst_timeframe"] = g

    for g in stats["grouped_by_score_band"]:
        if g["sample_size"] >= MIN_SAMPLE_INSUFFICIENT:
            if stats["best_score_band"] is None or g["target_first_rate"] > stats["best_score_band"]["target_first_rate"]:
                stats["best_score_band"] = g

    for g in stats["grouped_by_symbol"]:
        if g["stop_first_rate"] > 0.6 and g["sample_size"] >= MIN_SAMPLE_INSUFFICIENT:
            stats["dangerous_symbols"].append(g["name"])
        if g["target_first_rate"] > 0.5 and g["sample_size"] >= MIN_SAMPLE_WEAK:
            stats["reliable_symbols"].append(g["name"])

    stats["sample_labels"] = {
        "INSUFFICIENT_EVIDENCE": MIN_SAMPLE_INSUFFICIENT,
        "WEAK_EVIDENCE": MIN_SAMPLE_WEAK,
        "USABLE_EVIDENCE": MIN_SAMPLE_USABLE,
        "STRONG_EVIDENCE": 100,
    }

    return stats


def _band_label(score: int) -> str:
    if score >= 85:
        return "85-100"
    if score >= 80:
        return "80-84"
    if score >= 70:
        return "70-79"
    if score >= 60:
        return "60-69"
    return "50-59"


def _historical_edge_from_memory(stats: dict, pattern_id: str, direction: str,
                                  timeframe: str, psych_score_val: int, symbol: str) -> int:
    edge = 0
    best_pattern = stats.get("best_pattern")
    worst_pattern = stats.get("worst_pattern")

    if best_pattern:
        bp_name = best_pattern.get("name", "")
        if pattern_id == bp_name and best_pattern.get("sample_label", "") != "INSUFFICIENT_EVIDENCE":
            edge += 2

    if worst_pattern:
        wp_name = worst_pattern.get("name", "")
        if pattern_id == wp_name:
            edge -= 1

    for g in list(stats.get("grouped_by_symbol", [])):
        if g.get("name") == symbol:
            lbl = g.get("sample_label", "INSUFFICIENT_EVIDENCE")
            if lbl != "INSUFFICIENT_EVIDENCE":
                if g.get("target_first_rate", 0) > 0.5:
                    edge += 1
                if g.get("stop_first_rate", 0) > 0.5:
                    edge -= 1
            break

    for g in list(stats.get("grouped_by_timeframe", [])):
        if g.get("name") == timeframe:
            lbl = g.get("sample_label", "INSUFFICIENT_EVIDENCE")
            if lbl != "INSUFFICIENT_EVIDENCE":
                if g.get("target_first_rate", 0) > 0.5:
                    edge += 1
                if g.get("stop_first_rate", 0) > 0.5:
                    edge -= 1
            break

    band = _band_label(psych_score_val)
    for g in list(stats.get("grouped_by_score_band", [])):
        if g.get("name") == band:
            lbl = g.get("sample_label", "INSUFFICIENT_EVIDENCE")
            if lbl != "INSUFFICIENT_EVIDENCE":
                if g.get("target_first_rate", 0) > 0.5:
                    edge += 1
                if g.get("stop_first_rate", 0) > 0.5:
                    edge -= 1
            break

    return max(0, min(5, edge))


def run_psychology_memory() -> dict:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)

    psych = _read_json(os.path.join(RESULTS_DIR, "psychology_alpha_report.json"))
    memory = _load_jsonl(SCAN_MEMORY_FILE)
    outcomes = _load_jsonl(OUTCOMES_FILE)
    existing_outcome_keys = set()

    stored = _record_scan_snapshot(psych)
    prior_count = len(memory)

    memory = _load_jsonl(SCAN_MEMORY_FILE)
    evaluated, skipped = _evaluate_pending_outcomes(memory, existing_outcome_keys)
    outcomes = _load_jsonl(OUTCOMES_FILE)

    stats = _compute_statistics(outcomes)

    report = {
        "mode": "psychology_memory",
        "research_only": True,
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "timestamp": datetime.now().isoformat(),
        "total_scan_records_stored": len(memory),
        "new_records_this_run": stored,
        "total_outcomes_evaluated": len(outcomes),
        "outcomes_evaluated_this_run": evaluated,
        "pending_outcomes": max(0, len(memory) - len(outcomes)),
        "statistics": stats,
        "historical_edge_summary": {
            "best_pattern": stats.get("best_pattern"),
            "worst_pattern": stats.get("worst_pattern"),
            "best_timeframe": stats.get("best_timeframe"),
            "worst_timeframe": stats.get("worst_timeframe"),
            "best_score_band": stats.get("best_score_band"),
            "dangerous_symbols": stats.get("dangerous_symbols", []),
            "reliable_symbols": stats.get("reliable_symbols", []),
            "overall_target_first_rate": stats.get("overall_target_first_rate", 0),
            "overall_avg_max_r": stats.get("overall_avg_max_r", 0),
        },
        "minimum_sample_rules": {
            "insufficient": MIN_SAMPLE_INSUFFICIENT,
            "weak": MIN_SAMPLE_WEAK,
            "usable": MIN_SAMPLE_USABLE,
        },
    }

    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2)

    _write_text_report(report, stats)
    return report


def _write_text_report(report: dict, stats: dict):
    lines = [
        "=" * 60,
        "  PSYCHOLOGY MEMORY & EVIDENCE ENGINE",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  Total scan records stored:  {report['total_scan_records_stored']}",
        f"  New records this run:       {report['new_records_this_run']}",
        f"  Total outcomes evaluated:   {report['total_outcomes_evaluated']}",
        f"  Outcomes this run:          {report['outcomes_evaluated_this_run']}",
        f"  Pending outcomes:           {report['pending_outcomes']}",
        "",
    ]

    lines += ["  HISTORICAL EDGE SUMMARY:", ""]
    hes = report.get("historical_edge_summary", {})
    if hes.get("best_pattern"):
        lines += [f"    Best pattern:  {hes['best_pattern']['name']} "
                  f"(TF rate: {hes['best_pattern']['target_first_rate']:.2f}, "
                  f"n={hes['best_pattern']['sample_size']})"]
    if hes.get("worst_pattern"):
        lines += [f"    Worst pattern: {hes['worst_pattern']['name']} "
                  f"(TF rate: {hes['worst_pattern']['target_first_rate']:.2f}, "
                  f"n={hes['worst_pattern']['sample_size']})"]
    if hes.get("best_timeframe"):
        lines += [f"    Best TF:       {hes['best_timeframe']['name']} "
                  f"(TF rate: {hes['best_timeframe']['target_first_rate']:.2f})"]
    if hes.get("worst_timeframe"):
        lines += [f"    Worst TF:      {hes['worst_timeframe']['name']} "
                  f"(TF rate: {hes['worst_timeframe']['target_first_rate']:.2f})"]
    if hes.get("best_score_band"):
        lines += [f"    Best score:    {hes['best_score_band']['name']} "
                  f"(TF rate: {hes['best_score_band']['target_first_rate']:.2f})"]
    if hes.get("dangerous_symbols"):
        lines += [f"    Dangerous syms: {', '.join(hes['dangerous_symbols'][:10])}"]
    if hes.get("reliable_symbols"):
        lines += [f"    Reliable syms:  {', '.join(hes['reliable_symbols'][:10])}"]
    lines += [
        f"    Overall TF rate: {hes.get('overall_target_first_rate', 0):.4f}",
        f"    Overall avg max R: {hes.get('overall_avg_max_r', 0):.4f}",
        "",
    ]

    lines += [
        "  EVIDENCE BY PATTERN:",
        "    {:<30s} {:<6s} {:<12s} {:<10s} {:<10s} {:<8s} {:<8s}".format(
            "Pattern", "N", "Label", "TF Rate", "Stop Rate", "Avg R", "Avg Min"),
        "    " + "-" * 86,
    ]
    pattern_list = list(stats.get("grouped_by_pattern", []))
    for g in pattern_list[:10]:
        lines.append("    {:<30s} {:<6d} {:<12s} {:<10s} {:<10s} {:<8s} {:<8s}".format(
            g["name"][:30], g["sample_size"], g["sample_label"],
            str(g["target_first_rate"]), str(g["stop_first_rate"]),
            str(g["avg_max_r"]), str(g["avg_min_r"])))
    lines.append("")

    lines += [
        "  EVIDENCE BY SCORE BAND:",
        "    {:<12s} {:<6s} {:<12s} {:<10s} {:<10s}".format(
            "Score Band", "N", "Label", "TF Rate", "Stop Rate"),
        "    " + "-" * 50,
    ]
    for g in list(stats.get("grouped_by_score_band", [])):
        lines.append("    {:<12s} {:<6d} {:<12s} {:<10s} {:<10s}".format(
            g["name"], g["sample_size"], g["sample_label"],
            str(g["target_first_rate"]), str(g["stop_first_rate"])))
    lines.append("")

    lines += [
        "  EVIDENCE BY TIMEFRAME:",
        "    {:<8s} {:<6s} {:<12s} {:<10s} {:<10s}".format(
            "TF", "N", "Label", "TF Rate", "Stop Rate"),
        "    " + "-" * 46,
    ]
    for g in list(stats.get("grouped_by_timeframe", [])):
        lines.append("    {:<8s} {:<6d} {:<12s} {:<10s} {:<10s}".format(
            g["name"], g["sample_size"], g["sample_label"],
            str(g["target_first_rate"]), str(g["stop_first_rate"])))
    lines.append("")

    lines += [
        "  WARNING: Not approved for live trading.",
        "",
        "=" * 60,
    ]

    with open(TXT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n[JSON] {JSON_PATH}")
    print(f"[TXT]  {TXT_PATH}")


def get_historical_edge(pattern_id: str, direction: str, timeframe: str,
                         score: int, symbol: str) -> int:
    """Public API for psychology_alpha to get historical edge from memory."""
    try:
        report = _read_json(os.path.join(RESULTS_DIR, "psychology_memory_report.json"))
        stats = report.get("statistics", {})
        return _historical_edge_from_memory(stats, pattern_id, direction, timeframe, score, symbol)
    except Exception:
        return 0


def main():
    report = run_psychology_memory()
    return 0


if __name__ == "__main__":
    sys.exit(main())
