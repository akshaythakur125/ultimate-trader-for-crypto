"""Candidate rotation and active paper trade lock report.

Reads trigger watcher, arbiter, shadow intent, paper execution, outcome,
and hourly status. Reports whether the active paper trade is blocking new
candidates and what the next action should be.

This module NEVER places real orders, NEVER sets BINGX_EXECUTION_MODE=live_micro,
and NEVER sets LIVE_TRADING_ACK.
"""

import json, os, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
TXT_PATH = os.path.join(RESULTS_DIR, "candidate_rotation_report.txt")
JSON_PATH = os.path.join(RESULTS_DIR, "candidate_rotation_report.json")
LEDGER_PATH = os.path.join(STATE_DIR, "candidate_rotation.jsonl")


def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _get_best_eligible_candidate(trigger_watcher: dict, arbiter: dict) -> dict | None:
    best = None
    # Check arbiter best first
    arb_best = arbiter.get("best_candidate") if arbiter else None
    if arb_best:
        return arb_best
    # Fall back to trigger watcher best confirmed
    tw_best = trigger_watcher.get("best_confirmed_candidate") if trigger_watcher else None
    if tw_best:
        return tw_best
    return None


def _get_best_rejected_candidate(trigger_watcher: dict) -> dict | None:
    if not trigger_watcher:
        return None
    # Look through all candidates for a rejected/not-confirmed one with highest score
    candidates = trigger_watcher.get("candidates", [])
    if not candidates:
        return None
    candidates = [c for c in candidates if c.get("trigger_status") != "TRIGGER_CONFIRMED"]
    if not candidates:
        return None
    # Pick highest thesis_score or raw_anomaly_score
    def sort_key(c):
        return float(c.get("thesis_score", 0) or c.get("raw_anomaly_score", 0))
    candidates.sort(key=sort_key, reverse=True)
    best_rej = candidates[0]
    trigger_status = best_rej.get("trigger_status", "N/A")
    bucket = best_rej.get("bucket", "N/A")
    reason_parts = [trigger_status, bucket]
    if trigger_status != "TRIGGER_CONFIRMED":
        reason_parts.append(f"score={sort_key(best_rej)}")
    best_rej["rejection_reason_display"] = ", ".join(reason_parts)
    return best_rej


def run_candidate_rotation_report() -> dict:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)

    trigger_watcher = _read_json(RESULTS_DIR + "/trigger_watcher_report.json")
    arbiter = _read_json(RESULTS_DIR + "/candidate_arbiter_report.json")
    shadow = _read_json(RESULTS_DIR + "/bingx_order_intent.json")
    paper_status = _read_json(RESULTS_DIR + "/paper_execution_status.json")
    paper_outcome = _read_json(RESULTS_DIR + "/paper_outcome_report.json")
    hourly = _read_json(RESULTS_DIR + "/hourly_status.json")

    reasons = []

    # -- Active paper trades from portfolio --
    portfolio = _read_json(os.path.join(STATE_DIR, "paper_portfolio.json"))
    if isinstance(portfolio, list):
        active_trades_list = [t for t in portfolio if t.get("status") == "PAPER_OPEN"]
    else:
        active_trades_list = []
    trade_lock_on = len(active_trades_list) > 0

    # -- Total candidates scanned --
    tw_candidates = trigger_watcher.get("candidates", []) if trigger_watcher else []
    total_candidates = len(tw_candidates)

    # -- Trigger confirmed count --
    trigger_confirmed = trigger_watcher.get("confirmed_count", 0) if trigger_watcher else 0

    # -- Shadow eligible count --
    shadow_eligible = arbiter.get("shadow_eligible", 0) if arbiter else 0

    # -- Best new eligible candidate --
    best_eligible = _get_best_eligible_candidate(trigger_watcher, arbiter)

    # -- Best rejected candidate --
    best_rejected = _get_best_rejected_candidate(trigger_watcher)

    # -- Determine next action --
    if trade_lock_on:
        syms = ', '.join(t.get('symbol','?') for t in active_trades_list)
        next_action = "ACTIVE_TRADE_MONITORING"
        reasons.append(f"{len(active_trades_list)} active paper trade(s): {syms}; trade lock ON")
    elif best_eligible:
        next_action = "NEW_CANDIDATE_AVAILABLE"
        reasons.append(
            f"candidate {best_eligible.get('symbol','?')} {best_eligible.get('direction','?')} "
            f"RR:{best_eligible.get('rr','?')} Score:{best_eligible.get('thesis_score','?')} available"
        )
    elif trigger_confirmed > 0:
        next_action = "WAIT_FOR_CURRENT_TRADE_CLOSE"
        reasons.append(f"{trigger_confirmed} confirmed candidates but none shadow-eligible yet")
    else:
        next_action = "NO_VALID_CANDIDATE"
        reasons.append("no valid candidates found across watchlist")

    report = {
        "mode": "candidate_rotation_report",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "real_order": False,
        "active_trade_lock_on": trade_lock_on,
        "active_trades": active_trades_list,
        "active_trades_count": len(active_trades_list),
        "total_candidates_scanned": total_candidates,
        "trigger_confirmed_count": trigger_confirmed,
        "shadow_eligible_count": shadow_eligible,
        "best_eligible_candidate": best_eligible,
        "best_rejected_candidate": best_rejected,
        "next_action": next_action,
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
        "  CANDIDATE ROTATION REPORT",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  Active Trade Lock:   {'ON' if report['active_trade_lock_on'] else 'OFF'}",
        "",
    ]

    trade = report.get("active_trade")
    if trade:
        lines += [
            "  Active Paper Trade:",
            f"    Symbol:        {trade.get('symbol', 'N/A')}",
            f"    Side:          {trade.get('side', 'N/A')}",
            f"    Entry:         {trade.get('entry', 0)}",
            f"    Stop:          {trade.get('stop', 0)}",
            f"    Target:        {trade.get('target', 0)}",
            f"    Status:        {trade.get('status', 'N/A')}",
            f"    Current Price: {trade.get('price_at_last_check', 'N/A')}",
            f"    Unrealized P&L:{trade.get('unrealized_pnl', 'N/A')}",
        ]
    else:
        lines += ["  Active Paper Trade: NONE", ""]

    lines += [
        "",
        "  Scan Stats:",
        f"    Total Candidates:    {report['total_candidates_scanned']}",
        f"    Trigger Confirmed:   {report['trigger_confirmed_count']}",
        f"    Shadow Eligible:     {report['shadow_eligible_count']}",
        "",
    ]

    eligible = report.get("best_eligible_candidate")
    if eligible:
        lines += [
            "  Best Eligible Candidate:",
            f"    Symbol:    {eligible.get('symbol', 'N/A')} {eligible.get('direction', 'N/A')}",
            f"    Entry:     {eligible.get('entry', 'N/A')}",
            f"    Stop:      {eligible.get('stop', 'N/A')}",
            f"    Target:    {eligible.get('target', 'N/A')}",
            f"    RR:        1:{eligible.get('rr', 'N/A')}",
            f"    Score:     {eligible.get('thesis_score', 'N/A')}",
        ]
    else:
        lines += ["  Best Eligible Candidate: NONE", ""]

    rejected = report.get("best_rejected_candidate")
    if rejected:
        lines += [
            "  Best Rejected Candidate:",
            f"    Symbol:   {rejected.get('symbol', 'N/A')} {rejected.get('direction', 'N/A')}",
            f"    Reason:   {rejected.get('rejection_reason_display', 'N/A')}",
        ]
    else:
        lines += ["  Best Rejected Candidate: NONE", ""]

    lines += [
        "",
        f"  Next Action: {report['next_action']}",
        "",
    ]
    for r in report["reasons"]:
        lines.append(f"    - {r}")
    lines += [
        "",
        "  WARNING: Rotation report only. No real orders placed.",
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
        "active_trade_lock_on": report["active_trade_lock_on"],
        "total_candidates_scanned": report["total_candidates_scanned"],
        "trigger_confirmed_count": report["trigger_confirmed_count"],
        "shadow_eligible_count": report["shadow_eligible_count"],
        "next_action": report["next_action"],
    }
    with open(LEDGER_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def main():
    report = run_candidate_rotation_report()
    return 0


if __name__ == "__main__":
    sys.exit(main())
