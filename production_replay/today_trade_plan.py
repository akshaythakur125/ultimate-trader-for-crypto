"""Daily trade candidate report — decision-support only.

Evaluates whether there is a valid setup today using the
latest dry-forward and accelerated evidence data.

Usage:
    python -m production_replay.today_trade_plan
"""

import json, os, sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.evidence_ledger import read_latest_entry
from production_replay.launch_check import load_config

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
TXT_REPORT = os.path.join(RESULTS_DIR, "today_trade_plan.txt")
JSON_REPORT = os.path.join(RESULTS_DIR, "today_trade_plan.json")
ACCELERATED_PATH = os.path.join(RESULTS_DIR, "accelerated_evidence_report.json")

MIN_TRADES = 100
MIN_DAYS = 30


def _read_accelerated() -> dict | None:
    if not os.path.exists(ACCELERATED_PATH):
        return None
    with open(ACCELERATED_PATH) as f:
        return json.load(f)


def _best_candidate_from_accelerated(acc: dict | None) -> dict | None:
    if not acc:
        return None
    candidates = acc.get("candidates", [])
    completed = [c for c in candidates if c.get("status") == "completed" and c.get("trades", 0) > 0]
    if not completed:
        return None
    completed.sort(key=lambda c: c.get("ev", 0), reverse=True)
    return completed[0]


def grade_setup(candidate: dict | None, trades: int, days: int, ev: float, pf: float, dd: float) -> str:
    if not candidate or trades == 0:
        return "C"
    ev_ok = ev > 0
    pf_ok = pf >= 1.5
    dd_ok = dd < 12.0
    kill_ok = not candidate.get("kill_triggered", False)
    trades_ok = candidate.get("trades", 0) >= 75
    gap = candidate.get("max_consecutive_losses", 99) <= 6
    gate_r = candidate.get("gate_results", {})
    all_6 = all(gate_r.values()) if gate_r else False

    if trades_ok and all_6 and ev_ok and pf_ok and dd_ok and kill_ok:
        return "A"
    if ev_ok and pf_ok and dd_ok and kill_ok and gap:
        return "B"
    return "C"


def _check_safety() -> tuple[bool, bool, bool]:
    """Returns (system_safe, live_disabled, paper_disabled)."""
    config = load_config()
    live_disabled = not config.get("live_trading", True)
    paper_disabled = not config.get("paper_trading", True)
    return True, live_disabled, paper_disabled


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)

    entry = read_latest_entry()
    acc = _read_accelerated()

    system_safe, live_disabled, paper_disabled = _check_safety()

    # Extract evidence from ledger
    if entry:
        trades = entry.get("total_trades", 0)
        days = entry.get("calendar_days", 0)
        ev = entry.get("ev_r", 0)
        pf = entry.get("profit_factor", 0)
        dd = entry.get("max_drawdown_r", 0)
        kill = entry.get("kill_status") == "KILL"
        safety_ok = entry.get("safety_lock_verdict") == "ALL LOCKS ENGAGED"
        launch_ok = entry.get("launch_check_verdict") == "PASS"
    else:
        trades = 0
        days = 0
        ev = 0
        pf = 0
        dd = 0
        kill = False
        safety_ok = True
        launch_ok = True

    # Find best candidate
    best = _best_candidate_from_accelerated(acc)
    best_label = f"{best['symbol']} {best['timeframe']}" if best else "none"
    setup_grade = grade_setup(best, trades, days, ev, pf, dd)

    # Decision rules
    decision = "MANUAL_REVIEW_ONLY"
    reasons = []

    if not safety_ok:
        decision = "WAIT"
        reasons.append("safety lock failed")
    if not launch_ok:
        decision = "WAIT"
        reasons.append("launch check failed")
    if not live_disabled:
        decision = "WAIT"
        reasons.append("live trading not disabled")
    if not paper_disabled:
        decision = "WAIT"
        reasons.append("paper trading not disabled")
    if kill:
        decision = "WAIT"
        reasons.append("kill switch triggered")
    if trades < MIN_TRADES or days < MIN_DAYS:
        if decision != "WAIT":
            decision = "MANUAL_REVIEW_ONLY"
        reasons.append(f"evidence incomplete ({trades}/{MIN_TRADES} trades, {days}/{MIN_DAYS} days)")
    if decision == "MANUAL_REVIEW_ONLY" and not reasons:
        reasons.append("evidence gates not met — trade at your own risk")

    reason_str = "; ".join(reasons) if reasons else "all checks pass"

    # Build report
    report = {
        "mode": "today_trade_plan",
        "research_only": True,
        "timestamp": datetime.now().isoformat(),
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "system_safe": system_safe,
        "live_disabled": live_disabled,
        "paper_disabled": paper_disabled,
        "trade_decision": decision,
        "best_candidate": best_label,
        "setup_quality": setup_grade,
        "evidence": {
            "trades_collected": trades,
            "calendar_days_collected": days,
            "ev_r": ev,
            "profit_factor": pf,
            "max_drawdown_r": dd,
            "kill_switch": "KILL" if kill else "OK",
        },
        "reason": reason_str,
        "disclaimer": "This system is not approved for live trading. Manual trading is at user's own risk.",
    }

    # Write JSON
    with open(JSON_REPORT, "w") as f:
        json.dump(report, f, indent=2)

    # Write text report
    lines = [
        "=" * 60,
        "  TODAY TRADE PLAN — Decision Support Only",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  SYSTEM SAFE:    {'YES' if system_safe else 'NO'}",
        f"  LIVE DISABLED:  {'YES' if live_disabled else 'NO'}",
        f"  PAPER DISABLED: {'YES' if paper_disabled else 'NO'}",
        "",
        f"  TRADE DECISION: {decision}",
        f"  Best candidate: {best_label}",
        f"  Setup quality:  {setup_grade}",
        "",
        "  Evidence Status:",
        f"    Trades:  {trades} / {MIN_TRADES}",
        f"    Days:    {days} / {MIN_DAYS}",
        f"    EV:      {ev:+.3f}R",
        f"    PF:      {pf:.2f}",
        f"    DD:      {dd:.2f}R",
        f"    Kill:    {'KILL' if kill else 'OK'}",
        "",
        f"  Reason: {reason_str}",
        "",
        "  WARNING:",
        "  " + report["disclaimer"],
        "",
        "=" * 60,
    ]

    with open(TXT_REPORT, "w") as f:
        f.write("\n".join(lines) + "\n")

    # Print to console
    print("\n".join(lines))
    print(f"\n[JSON] {JSON_REPORT}")
    print(f"[TXT]  {TXT_REPORT}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
