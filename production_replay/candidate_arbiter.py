"""Candidate Arbiter — unified gate between near-miss diagnostic and shadow executor.

Reads near_miss_report.json, psychology_alpha_report.json, dux_pattern_report.json.
Outputs REVIEW_CANDIDATE / SHADOW_ELIGIBLE / DO_NOT_TRADE per candidate.
"""

import json, os, sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.bingx_universe import is_crypto_usdt_perp

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
TXT_PATH = os.path.join(RESULTS_DIR, "candidate_arbiter_report.txt")
JSON_PATH = os.path.join(RESULTS_DIR, "candidate_arbiter_report.json")
REVIEW_PATH = os.path.join(STATE_DIR, "review_candidates.jsonl")

ARBITER_VERDICTS = ["SHADOW_ELIGIBLE", "REVIEW_CANDIDATE", "DO_NOT_TRADE"]


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


def _evaluate_candidate(
    c: dict,
    psych_patterns_map: dict,
    dux_best: dict | None,
) -> dict:
    """Evaluate a single candidate and return arbiter verdict.

    Args:
        c: Candidate dict from near_miss all_classified
        psych_patterns_map: Dict of symbol|tf|pattern_id -> psych pattern
        dux_best: Best candidate from dux_pattern_engine (or None)

    Returns:
        Dict with verdict and reasoning
    """
    symbol = c.get("symbol", "")
    tf = c.get("timeframe", "")
    direction = c.get("direction", "UNKNOWN")
    bucket = c.get("bucket", "REJECTED")
    entry = c.get("entry") or c.get("thesis_ideal_entry") or 0
    stop = c.get("stop") or c.get("thesis_stop") or 0
    target = c.get("target") or c.get("thesis_target") or c.get("target_2") or 0
    rr = c.get("current_rr") or c.get("rr_2") or 0
    thesis_score = c.get("trade_thesis_score", 0)
    trigger_status = c.get("trigger_info", {}).get("trigger_status", "NOT_APPLICABLE")

    reasons = []
    verdict = "DO_NOT_TRADE"

    # Gate 1: crypto filter
    if not is_crypto_usdt_perp(symbol):
        reasons.append(f"{symbol} not crypto USDT perpetual")
        return {"symbol": symbol, "timeframe": tf, "direction": direction,
                "bucket": bucket, "verdict": verdict, "reasons": reasons,
                "rr": rr, "thesis_score": thesis_score, "trigger_status": trigger_status}

    # Gate 2: bucket must be TRIGGER_CONFIRMED or DIAGNOSTIC_EXECUTABLE
    if bucket not in ("TRIGGER_CONFIRMED", "DIAGNOSTIC_EXECUTABLE", "ARBITER_ELIGIBLE"):
        reasons.append(f"bucket {bucket} not eligible for arbiter review")
        return {"symbol": symbol, "timeframe": tf, "direction": direction,
                "bucket": bucket, "verdict": verdict, "reasons": reasons,
                "rr": rr, "thesis_score": thesis_score, "trigger_status": trigger_status}

    # Gate 3: valid direction
    if direction not in ("LONG", "SHORT"):
        reasons.append(f"invalid direction: {direction}")
        return {"symbol": symbol, "timeframe": tf, "direction": direction,
                "bucket": bucket, "verdict": verdict, "reasons": reasons,
                "rr": rr, "thesis_score": thesis_score, "trigger_status": trigger_status}

    # Gate 4: valid entry/stop/target
    if not entry or float(entry) <= 0:
        reasons.append("invalid entry")
    if not stop or float(stop) <= 0:
        reasons.append("invalid stop")
    if not target or float(target) <= 0:
        reasons.append("invalid target")
    if reasons:
        return {"symbol": symbol, "timeframe": tf, "direction": direction,
                "bucket": bucket, "verdict": verdict, "reasons": reasons,
                "rr": rr, "thesis_score": thesis_score, "trigger_status": trigger_status,
                "entry": entry, "stop": stop, "target": target}

    # Gate 5: RR >= 4
    if rr < 4.0:
        reasons.append(f"RR {rr} < 4.0")

    # Gate 6: thesis score >= 70
    if thesis_score < 70:
        reasons.append(f"thesis score {thesis_score} < 70")

    # Gate 7: trigger confirmed or pending
    if trigger_status not in ("TRIGGER_CONFIRMED", "TRIGGER_PENDING"):
        reasons.append(f"trigger status {trigger_status} not actionable")

    # Gate 8: psychology_alpha has data for this symbol/TF
    psych_key = f"{symbol}|{tf}"
    psych_match = any(k.startswith(psych_key) for k in psych_patterns_map)
    if not psych_match:
        reasons.append(f"no psychology_alpha data for {symbol}/{tf}")

    if not reasons:
        # If all gates pass and trigger is confirmed, eligible for shadow
        if trigger_status == "TRIGGER_CONFIRMED" and rr >= 4.0 and thesis_score >= 70:
            verdict = "SHADOW_ELIGIBLE"
            reasons.append("all gates passed; shadow executor may proceed")
        else:
            verdict = "REVIEW_CANDIDATE"
            if trigger_status != "TRIGGER_CONFIRMED":
                reasons.append("trigger not yet confirmed; candidate needs price action validation")
            if rr < 4.0:
                reasons.append("RR below 4.0 threshold")
            if thesis_score < 70:
                reasons.append("thesis score below 70")
    else:
        # Some gates failed, but still might be reviewable if close
        if rr >= 3.0 and thesis_score >= 60:
            verdict = "REVIEW_CANDIDATE"
        else:
            verdict = "DO_NOT_TRADE"

    return {
        "symbol": symbol,
        "timeframe": tf,
        "direction": direction,
        "bucket": bucket,
        "verdict": verdict,
        "reasons": reasons,
        "rr": rr,
        "thesis_score": thesis_score,
        "trigger_status": trigger_status,
        "entry": entry,
        "stop": stop,
        "target": target,
        "thesis_type": c.get("thesis_type", "N/A"),
        "psychology_score": c.get("psychology_score", 0),
        "raw_anomaly_score": c.get("raw_anomaly_score", 0),
        "detection_time": c.get("detection_time", ""),
    }


def run_arbiter() -> dict:
    near_miss = _read_json(os.path.join(RESULTS_DIR, "near_miss_report.json"))
    psych = _read_json(os.path.join(RESULTS_DIR, "psychology_alpha_report.json"))
    dux = _read_json(os.path.join(RESULTS_DIR, "dux_pattern_report.json"))
    trigger_watcher = _read_json(os.path.join(RESULTS_DIR, "trigger_watcher_report.json"))
    trigger_events = _read_jsonl(os.path.join(STATE_DIR, "trigger_events.jsonl"))

    # Build trigger status map from trigger watcher
    trigger_status_map = {}
    for c in trigger_watcher.get("candidates", []):
        key = f"{c.get('symbol', '')}|{c.get('timeframe', '')}|{c.get('direction', '')}|{c.get('thesis_type', '')}"
        trigger_status_map[key] = c.get("trigger_status", "WAITING")

    # Also build from trigger events (later events override)
    for ev in trigger_events:
        key = f"{ev.get('symbol', '')}|{ev.get('timeframe', '')}|{ev.get('direction', '')}|{ev.get('thesis_type', '')}"
        trigger_status_map[key] = ev.get("trigger_status", "WAITING")

    classified = near_miss.get("all_classified", [])
    psych_patterns = psych.get("patterns", []) if psych else []
    dux_best = (dux.get("dux_pattern_engine") or dux).get("best_candidate")

    # Build psych map for quick lookup
    psych_patterns_map = {}
    for pp in psych_patterns:
        key = f"{pp.get('symbol', '')}|{pp.get('timeframe', '')}|{pp.get('pattern_id', '')}"
        psych_patterns_map[key] = pp
        # Also add without pattern_id
        key2 = f"{pp.get('symbol', '')}|{pp.get('timeframe', '')}"
        if key2 not in psych_patterns_map:
            psych_patterns_map[key2] = pp

    candidates_evaluated = []
    shadow_eligible_count = 0
    review_candidate_count = 0
    do_not_trade_count = 0

    for c in classified:
        # Override trigger status from trigger watcher if available
        tw_key = f"{c.get('symbol', '')}|{c.get('timeframe', '')}|{c.get('direction', '')}|{c.get('thesis_type', '')}"
        tw_status = trigger_status_map.get(tw_key)
        if tw_status:
            c["trigger_info"] = c.get("trigger_info", {})
            c["trigger_info"]["trigger_status"] = tw_status
            if tw_status == "TRIGGER_CONFIRMED":
                c["bucket"] = "TRIGGER_CONFIRMED"
            elif tw_status == "INVALIDATED":
                c["bucket"] = "REJECTED"
                c["rejection_reason"] = "Invalidated by trigger watcher"

        result = _evaluate_candidate(c, psych_patterns_map, dux_best)
        candidates_evaluated.append(result)
        if result["verdict"] == "SHADOW_ELIGIBLE":
            shadow_eligible_count += 1
            _append_jsonl(REVIEW_PATH, result)
        elif result["verdict"] == "REVIEW_CANDIDATE":
            review_candidate_count += 1
            _append_jsonl(REVIEW_PATH, result)
        else:
            do_not_trade_count += 1

    # Also check psychology_alpha best_candidate directly
    psych_best = psych.get("best_candidate") if psych else None
    psych_best_verdict = None
    if psych_best:
        pb_symbol = psych_best.get("symbol", "")
        pb_tf = psych_best.get("timeframe", "")
        pb_dir = psych_best.get("direction", "")
        pb_rr = psych_best.get("rr_2", 0)
        pb_psych = psych_best.get("psychology_score", 0)
        if (is_crypto_usdt_perp(pb_symbol) and pb_dir in ("LONG", "SHORT")
                and pb_rr >= 4.0 and pb_psych >= 70):
            psych_best_verdict = "SHADOW_ELIGIBLE"
        else:
            psych_best_verdict = "REVIEW_CANDIDATE"

    report = {
        "mode": "candidate_arbiter",
        "research_only": True,
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "timestamp": datetime.now().isoformat(),
        "inputs": {
            "near_miss_report": "near_miss_report.json",
            "psychology_alpha_report": "psychology_alpha_report.json",
            "dux_pattern_report": "dux_pattern_report.json",
            "trigger_watcher_report": "trigger_watcher_report.json",
            "trigger_events": "trigger_events.jsonl",
        },
        "total_candidates_evaluated": len(candidates_evaluated),
        "shadow_eligible": shadow_eligible_count,
        "review_candidate": review_candidate_count,
        "do_not_trade": do_not_trade_count,
        "trigger_watcher_candidates": len(trigger_watcher.get("candidates", [])) if trigger_watcher else 0,
        "trigger_watcher_best_confirmed": trigger_watcher.get("best_confirmed_candidate") if trigger_watcher else None,
        "psychology_alpha_best_candidate_verdict": psych_best_verdict,
        "has_shadow_eligible_candidates": shadow_eligible_count > 0,
        "best_candidate": next((c for c in candidates_evaluated if c["verdict"] == "SHADOW_ELIGIBLE"), None),
        "candidates": candidates_evaluated,
    }

    _write_text_report(report)
    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2)
    print(f"[JSON] {JSON_PATH}")
    print(f"[TXT]  {TXT_PATH}")
    print(f"[REVIEW] {REVIEW_PATH}")
    return report


def _write_text_report(report: dict):
    lines = [
        "=" * 60,
        "  CANDIDATE ARBITER REPORT",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  Total candidates evaluated:  {report['total_candidates_evaluated']}",
        f"  SHADOW_ELIGIBLE:             {report['shadow_eligible']}",
        f"  REVIEW_CANDIDATE:            {report['review_candidate']}",
        f"  DO_NOT_TRADE:                {report['do_not_trade']}",
        f"  Psych alpha best verdict:    {report['psychology_alpha_best_candidate_verdict']}",
        f"  Trigger watcher candidates: {report.get('trigger_watcher_candidates', 0)}",
        "",
    ]

    best = report.get("best_candidate")
    if best:
        lines += [
            "  BEST SHADOW-ELIGIBLE CANDIDATE:",
            f"    Symbol:           {best['symbol']}",
            f"    Timeframe:        {best['timeframe']}",
            f"    Direction:        {best['direction']}",
            f"    Bucket:           {best['bucket']}",
            f"    Thesis Type:      {best.get('thesis_type', 'N/A')}",
            f"    RR:               1:{best['rr']}",
            f"    Thesis Score:     {best['thesis_score']}",
            f"    Trigger Status:   {best['trigger_status']}",
            f"    Entry:            {best.get('entry', 'N/A')}",
            f"    Stop:             {best.get('stop', 'N/A')}",
            f"    Target:           {best.get('target', 'N/A')}",
            f"    Psychology:       {best.get('psychology_score', 'N/A')}",
            f"    Raw Anomaly:      {best.get('raw_anomaly_score', 'N/A')}",
            "",
        ]

    tw_best = report.get("trigger_watcher_best_confirmed")
    if tw_best:
        lines += [
            "  TRIGGER WATCHER BEST CONFIRMED:",
            f"    {tw_best['symbol']} {tw_best['timeframe']} {tw_best['direction']} "
            f"RR:1:{tw_best.get('rr', '?')} Score:{tw_best.get('thesis_score', '?')}",
            f"    Reason: {tw_best.get('reason', '')}",
            "",
        ]

    # Show review candidates
    review_candidates = [c for c in report["candidates"] if c["verdict"] == "REVIEW_CANDIDATE"]
    if review_candidates:
        lines += [
            f"  REVIEW CANDIDATES ({len(review_candidates)}):",
            "",
        ]
        for rc in review_candidates[:5]:
            lines += [
                f"    {rc['symbol']} {rc['timeframe']} {rc['direction']} "
                f"RR:1:{rc['rr']} Score:{rc['thesis_score']} Trigger:{rc['trigger_status']}",
                f"      Reasons: {'; '.join(rc['reasons'])}",
                "",
            ]

    # Signal integrity section
    lines += [
        "  SIGNAL INTEGRITY:",
        f"    Arbiter candidates:   {report['total_candidates_evaluated']}",
        f"    Shadow eligible:      {report['shadow_eligible']}",
        f"    Review candidates:    {report['review_candidate']}",
        f"    Do not trade:         {report['do_not_trade']}",
        "",
        "  WARNING: System not approved for live trading.",
        "",
        "=" * 60,
    ]

    with open(TXT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def main():
    report = run_arbiter()
    return 0


if __name__ == "__main__":
    sys.exit(main())
