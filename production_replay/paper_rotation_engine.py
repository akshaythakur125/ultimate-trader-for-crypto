"""Auto paper rotation engine.

Selects the next best fresh SHADOW_ELIGIBLE candidate after a paper trade
closes. Does NOT open a second paper trade while one is active. Does NOT
enable live trading. Does NOT place real orders.

This module NEVER places real orders, NEVER sets BINGX_EXECUTION_MODE=live_micro,
and NEVER sets LIVE_TRADING_ACK.
"""

import json, os, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
TXT_PATH = os.path.join(RESULTS_DIR, "paper_rotation_report.txt")
JSON_PATH = os.path.join(RESULTS_DIR, "paper_rotation_report.json")
LEDGER_PATH = os.path.join(STATE_DIR, "paper_rotation_events.jsonl")
PAPER_TRADE_FILE = os.path.join(STATE_DIR, "current_paper_trade.json")
PAPER_LEDGER = os.path.join(STATE_DIR, "paper_trades.jsonl")
PAPER_EXECUTION_PATH = os.path.join(RESULTS_DIR, "paper_execution_status.json")


def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _read_ledger(path: str) -> list[dict]:
    try:
        with open(path) as f:
            return [json.loads(l) for l in f if l.strip()]
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _candidate_score(c: dict) -> float:
    return float(c.get("thesis_score", 0) or c.get("raw_anomaly_score", 0))


def _is_eligible(c: dict) -> bool:
    ts = c.get("trigger_status", "")
    if ts != "TRIGGER_CONFIRMED":
        return False
    rr = float(c.get("rr", 0) or 0)
    if rr < 4:
        return False
    return True


def _eligibility_status(c: dict) -> str:
    ts = c.get("trigger_status", "")
    if ts == "TRIGGER_CONFIRMED":
        if float(c.get("thesis_score", 0) or 0) >= 75 and float(c.get("rr", 0) or 0) >= 4:
            return "SHADOW_ELIGIBLE"
        return "REVIEW_CANDIDATE"
    return ts


def _last_closed_trade_same_symbol_direction(symbol: str, direction: str) -> dict | None:
    trades = _read_ledger(PAPER_LEDGER)
    closed = [t for t in trades if t.get("status") == "PAPER_CLOSED"]
    if not closed:
        return None
    last_closed = closed[-1]
    if (
        last_closed.get("symbol", "") == symbol
        and last_closed.get("side", "").lower() == direction.lower()
    ):
        return last_closed
    return None


def run_paper_rotation_engine() -> dict:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)

    current_trade_data = _read_json(PAPER_TRADE_FILE)
    trigger_watcher = _read_json(RESULTS_DIR + "/trigger_watcher_report.json")

    reasons = []
    active_trade_open = bool(
        current_trade_data
        and current_trade_data.get("status") == "PAPER_OPEN"
    )
    trade_lock_on = active_trade_open
    active_symbol = (current_trade_data or {}).get("symbol", "")
    active_side = (current_trade_data or {}).get("side", "")
    active_rr = float(current_trade_data.get("rr", 0) or 0) if current_trade_data else 0

    all_candidates: list[dict] = trigger_watcher.get("candidates", []) if trigger_watcher else []

    eligible = [c for c in all_candidates if _is_eligible(c)]
    fresh_eligible = [c for c in eligible if c.get("symbol", "") != active_symbol]

    filtered_eligible = []
    for c in fresh_eligible:
        last_closed = _last_closed_trade_same_symbol_direction(
            c.get("symbol", ""), c.get("direction", "")
        )
        if last_closed:
            cand_ts = c.get("timestamp") or c.get("trigger_confirmed_at") or ""
            closed_ts = last_closed.get("closed_at", "")
            if cand_ts and closed_ts and cand_ts > closed_ts:
                filtered_eligible.append(c)
            else:
                reasons.append(
                    f"re-entry blocked: {c['symbol']} {c['direction']} same as last closed trade"
                )
        else:
            filtered_eligible.append(c)

    if not filtered_eligible:
        filtered_eligible = fresh_eligible

    def _sort_key(c: dict) -> tuple:
        is_se = _eligibility_status(c) == "SHADOW_ELIGIBLE"
        return (is_se, _candidate_score(c), float(c.get("rr", 0) or 0))

    filtered_eligible.sort(key=_sort_key, reverse=True)
    best_candidate = filtered_eligible[0] if filtered_eligible else None

    if active_trade_open:
        next_action = "ACTIVE_TRADE_MONITORING"
        reasons.append(
            f"active paper trade {active_symbol} {active_side} open; trade lock ON"
        )
    elif best_candidate:
        best_rr = float(best_candidate.get("rr", 0) or 0)
        if best_rr >= 4:
            next_action = "ROTATE_TO_NEW_PAPER_TRADE"
            reasons.append(
                f"selected {best_candidate['symbol']} {best_candidate['direction']} "
                f"RR:{best_rr} Score:{_candidate_score(best_candidate)} for paper rotation"
            )
        else:
            next_action = "NO_VALID_CANDIDATE"
            reasons.append(
                f"best candidate {best_candidate['symbol']} has RR={best_rr} < 4"
            )
    else:
        next_action = "NO_VALID_CANDIDATE"
        reasons.append("no eligible candidate found for rotation")

    report = {
        "mode": "paper_rotation_engine",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "real_order": False,
        "next_action": next_action,
        "active_trade_lock_on": trade_lock_on,
        "active_trade": {
            "symbol": active_symbol,
            "side": active_side,
            "rr": active_rr,
            "status": current_trade_data.get("status", "") if current_trade_data else "",
        } if current_trade_data else None,
        "rotation_candidate": {
            "symbol": best_candidate.get("symbol", ""),
            "timeframe": best_candidate.get("timeframe", ""),
            "direction": best_candidate.get("direction", ""),
            "rr": float(best_candidate.get("rr", 0) or 0),
            "thesis_score": _candidate_score(best_candidate),
            "trigger_status": best_candidate.get("trigger_status", ""),
            "eligibility_status": _eligibility_status(best_candidate),
            "entry": float(best_candidate.get("entry", 0) or 0),
            "stop": float(best_candidate.get("stop", 0) or 0),
            "target": float(best_candidate.get("target", 0) or 0),
            "bucket": best_candidate.get("bucket", ""),
            "reason": best_candidate.get("reason", ""),
        } if best_candidate else None,
        "candidate_discovery": {
            "total_candidates": len(all_candidates),
            "eligible_candidates": len(eligible),
            "fresh_eligible": len(fresh_eligible),
            "re_entry_blocked": max(0, len(fresh_eligible) - len(filtered_eligible)),
        },
        "reasons": reasons,
    }

    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2)

    _write_text_report(report)
    _append_to_ledger(report)
    return report


def _write_text_report(report: dict):
    lines = [
        "=" * 60,
        "  PAPER ROTATION ENGINE",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  Next Action:       {report['next_action']}",
        f"  Trade Lock:        {'ON' if report['active_trade_lock_on'] else 'OFF'}",
        "",
    ]

    at = report.get("active_trade")
    if at and at.get("symbol"):
        lines += [
            "  Active Paper Trade:",
            f"    Symbol:   {at.get('symbol', 'N/A')} {at.get('side', 'N/A')}",
            f"    RR:       1:{at.get('rr', 0)}",
            f"    Status:   {at.get('status', 'N/A')}",
        ]
    else:
        lines += ["  Active Paper Trade: NONE"]

    cd = report.get("candidate_discovery", {})
    lines += [
        "",
        "  Candidate Discovery:",
        f"    Total:              {cd.get('total_candidates', 0)}",
        f"    Eligible (RR>=4):   {cd.get('eligible_candidates', 0)}",
        f"    Fresh (ex. active): {cd.get('fresh_eligible', 0)}",
        f"    Re-entry blocked:   {cd.get('re_entry_blocked', 0)}",
        "",
    ]

    rc = report.get("rotation_candidate")
    if rc:
        lines += [
            "  Rotation Candidate:",
            f"    Symbol:   {rc.get('symbol','?')} {rc.get('direction','?')} {rc.get('timeframe','?')}",
            f"    RR:       1:{rc.get('rr','?')}",
            f"    Score:    {rc.get('thesis_score','?')}",
            f"    Status:   {rc.get('eligibility_status','?')} ({rc.get('trigger_status','?')})",
            f"    Entry:    {rc.get('entry','?')}  Stop: {rc.get('stop','?')}  Target: {rc.get('target','?')}",
            f"    Reason:   {rc.get('reason','')}",
        ]
    else:
        lines += ["  Rotation Candidate: NONE"]

    lines += [
        "",
        "  Rotation Allowed: " + (
            "YES" if report['next_action'] == "ROTATE_TO_NEW_PAPER_TRADE" else
            "NO (active trade)" if report['next_action'] == "ACTIVE_TRADE_MONITORING" else
            "NO (no candidate)"
        ),
        "",
    ]
    for r in report["reasons"]:
        lines.append(f"    - {r}")
    lines += [
        "",
        "  WARNING: Paper rotation only. No real orders placed. Max one paper trade.",
        "",
        "=" * 60,
    ]

    with open(TXT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n[JSON] {JSON_PATH}")
    print(f"[TXT]  {TXT_PATH}")
    print(f"[LEDGER] {LEDGER_PATH}")


def _append_to_ledger(report: dict):
    entry = {
        "timestamp": report["timestamp"],
        "next_action": report["next_action"],
        "active_trade_lock_on": report["active_trade_lock_on"],
        "rotation_candidate_symbol": (
            report.get("rotation_candidate", {}).get("symbol")
        ) if report.get("rotation_candidate") else None,
        "candidate_discovery": report.get("candidate_discovery", {}),
    }
    with open(LEDGER_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def main():
    report = run_paper_rotation_engine()
    return 0


if __name__ == "__main__":
    sys.exit(main())
