"""Evidence tracker — monitors dry-forward evidence for paper/live unlock gates.

Tracks:
- total valid dry-forward trades
- unique trade count
- calendar days logged
- latest PF, WR, DD, EV
- Gate A (>=100 trades) status
- Gate B (>=30 calendar days) status
- paper/live unlock block status
"""

import json, os, time
from datetime import date, datetime
from pathlib import Path
from typing import Any

TRACKER_FILE = "deploy_results/.evidence_tracker.json"
REPORT_PATH = "deploy_results/dry_forward_report.json"
MIN_TRADES_GATE = 100
MIN_DAYS_GATE = 30
PAPER_PF = 1.5
PAPER_WR = 35.0
PAPER_DD = 12.0


def load_report() -> dict:
    if not os.path.exists(REPORT_PATH):
        return {}
    with open(REPORT_PATH) as f:
        return json.load(f)


def load_tracker() -> dict:
    if not os.path.exists(TRACKER_FILE):
        return {"run_dates": [], "total_trades_logged": 0, "last_report_verdict": None}
    with open(TRACKER_FILE) as f:
        return json.load(f)


def save_tracker(data: dict):
    os.makedirs(os.path.dirname(TRACKER_FILE), exist_ok=True)
    with open(TRACKER_FILE, "w") as f:
        json.dump(data, f, indent=2)


def track_evidence(report: dict | None = None) -> dict[str, Any]:
    if report is None:
        report = load_report()
    tracker = load_tracker()

    today = date.today().isoformat()
    run_dates = tracker.get("run_dates", [])
    if today not in run_dates:
        run_dates.append(today)

    total_trades = report.get("total_trades", 0) if report else 0
    total_wr = report.get("total_wr", 0) if report else 0
    total_ev = report.get("total_ev", 0) if report else 0
    total_pf = report.get("total_pf", 0) if report else 0
    total_dd = report.get("total_dd_r", 99) if report else 99
    kill_triggered = report.get("kill_triggered", False) if report else False
    verdict = report.get("verdict", "NO_REPORT") if report else "NO_REPORT"
    paper_enabled = report.get("paper_trading_enabled", True) if report else True
    live_enabled = report.get("live_trading_enabled", True) if report else True

    save_tracker({
        "run_dates": run_dates,
        "total_trades_logged": total_trades,
        "last_report_verdict": verdict,
        "last_updated": datetime.now().isoformat(),
    })

    calendar_days = len(set(run_dates))
    gate_a = total_trades >= MIN_TRADES_GATE
    gate_b = calendar_days >= MIN_DAYS_GATE
    pf_ok = total_pf >= PAPER_PF
    wr_ok = total_wr >= PAPER_WR
    dd_ok = total_dd < PAPER_DD
    ev_ok = total_ev > 0
    kill_ok = not kill_triggered
    paper_blocked = not (gate_a and gate_b and pf_ok and wr_ok and dd_ok and ev_ok and kill_ok)
    live_blocked = True

    return {
        "timestamp": datetime.now().isoformat(),
        "total_trades": total_trades,
        "calendar_days_logged": calendar_days,
        "run_dates": sorted(run_dates),
        "latest_wr": total_wr,
        "latest_ev": total_ev,
        "latest_pf": total_pf,
        "latest_dd": total_dd,
        "kill_triggered": kill_triggered,
        "verdict": verdict,
        "gates": {
            "gate_a_trades_ge_100": {"pass": gate_a, "detail": f"{total_trades} >= {MIN_TRADES_GATE}" if gate_a else f"{total_trades} < {MIN_TRADES_GATE}"},
            "gate_b_days_ge_30": {"pass": gate_b, "detail": f"{calendar_days} >= {MIN_DAYS_GATE}" if gate_b else f"{calendar_days} < {MIN_DAYS_GATE}"},
            "pf_ge_1.5": {"pass": pf_ok, "detail": f"PF {total_pf:.2f}" + (" >= 1.5" if pf_ok else " < 1.5")},
            "wr_ge_35": {"pass": wr_ok, "detail": f"WR {total_wr:.1f}%" + (" >= 35%" if wr_ok else " < 35%")},
            "dd_lt_12R": {"pass": dd_ok, "detail": f"DD {total_dd:.2f}R" + (" < 12.0R" if dd_ok else " >= 12.0R")},
            "ev_gt_0": {"pass": ev_ok, "detail": f"EV {total_ev:+.3f}R" + (" > 0" if ev_ok else " <= 0")},
            "kill_not_triggered": {"pass": kill_ok, "detail": "OK" if kill_ok else "KILL"},
        },
        "paper_unlock_blocked": paper_blocked,
        "live_unlock_blocked": live_blocked,
        "paper_unlock_reason": _blocked_reason(gate_a, gate_b, pf_ok, wr_ok, dd_ok, ev_ok, kill_ok, calendar_days, total_trades) if paper_blocked else "all gates pass",
        "live_unlock_reason": "eligible_for_live_trading hard-coded to False in validation_gate.py",
        "paper_trading_enabled": paper_enabled,
        "live_trading_enabled": live_enabled,
    }


def _blocked_reason(gate_a: bool, gate_b: bool, pf_ok: bool, wr_ok: bool,
                    dd_ok: bool, ev_ok: bool, kill_ok: bool,
                    calendar_days: int, total_trades: int) -> str:
    fails = []
    if not gate_a:
        fails.append(f"Gate A: {total_trades} trades < 100")
    if not gate_b:
        fails.append(f"Gate B: {calendar_days} days < 30")
    if not pf_ok:
        fails.append("PF < 1.5")
    if not wr_ok:
        fails.append("WR < 35%")
    if not dd_ok:
        fails.append("DD >= 12.0R")
    if not ev_ok:
        fails.append("EV <= 0")
    if not kill_ok:
        fails.append("kill switch triggered")
    return "; ".join(fails) if fails else "unknown"


def print_evidence_summary(evidence: dict):
    print("=" * 72)
    print("  EVIDENCE TRACKER")
    print("=" * 72)
    print(f"  Total trades:       {evidence['total_trades']}")
    print(f"  Calendar days:      {evidence['calendar_days_logged']}")
    print(f"  Latest WR:          {evidence['latest_wr']:.1f}%")
    print(f"  Latest EV:          {evidence['latest_ev']:+.3f}R")
    print(f"  Latest PF:          {evidence['latest_pf']:.2f}")
    print(f"  Latest DD:          {evidence['latest_dd']:.2f}R")
    print(f"  Kill switch:        {'KILL' if evidence['kill_triggered'] else 'OK'}")
    print(f"  Verdict:            {evidence['verdict']}")
    print()
    print("  GATES")
    for name, g in evidence["gates"].items():
        print(f"  {'PASS' if g['pass'] else 'FAIL':6s} | {name:<25s} {g['detail']}")
    print()
    print(f"  Paper unlock:       {'BLOCKED' if evidence['paper_unlock_blocked'] else 'UNLOCKED'}")
    print(f"  Reason:             {evidence['paper_unlock_reason']}")
    print(f"  Live unlock:        {'BLOCKED' if evidence['live_unlock_blocked'] else 'UNLOCKED'}")
    print(f"  Reason:             {evidence['live_unlock_reason']}")
    print(f"  Paper trading:      {'ENABLED' if evidence['paper_trading_enabled'] else 'DISABLED'}")
    print(f"  Live trading:       {'ENABLED' if evidence['live_trading_enabled'] else 'DISABLED'}")
    print("=" * 72)


if __name__ == "__main__":
    evidence = track_evidence()
    print_evidence_summary(evidence)
