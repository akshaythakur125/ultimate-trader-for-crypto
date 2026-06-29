"""Final doctor daily packet — one-command combined status.

Runs (or reads outputs from) healthcheck, today_trade_plan,
and manual_risk_console, then produces a single short doctor-friendly
report with multi-candidate scanner results.

Usage:
    python -m production_replay.doctor_daily_packet
"""

import json, os, subprocess, sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
LEDGER_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
LEDGER_FILE = os.environ.get("EVIDENCE_LEDGER_PATH") or os.path.join(LEDGER_DIR, "evidence_ledger.jsonl")
TXT_PATH = os.path.join(RESULTS_DIR, "doctor_daily_packet.txt")
JSON_PATH = os.path.join(RESULTS_DIR, "doctor_daily_packet.json")

MIN_TRADES = 100
MIN_DAYS = 30


def _read_json(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _read_ledger_latest() -> dict | None:
    if not os.path.exists(LEDGER_FILE):
        return None
    with open(LEDGER_FILE) as f:
        lines = [l.strip() for l in f if l.strip()]
    if not lines:
        return None
    return json.loads(lines[-1])


def _run_module(name: str) -> bool:
    try:
        result = subprocess.run(
            [sys.executable, "-m", name],
            capture_output=True, text=True, timeout=60,
        )
        return result.returncode == 0
    except Exception:
        return False


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)

    _run_module("production_replay.healthcheck")
    _run_module("production_replay.today_trade_plan")
    _run_module("production_replay.manual_risk_console")

    trade_plan = _read_json(os.path.join(RESULTS_DIR, "today_trade_plan.json"))
    risk_plan = _read_json(os.path.join(RESULTS_DIR, "manual_risk_plan.json"))
    entry = _read_ledger_latest()

    if entry:
        trades = entry.get("total_trades", 0)
        days = entry.get("calendar_days", 0)
        safety_ok = entry.get("safety_lock_verdict") == "ALL LOCKS ENGAGED"
        launch_ok = entry.get("launch_check_verdict") == "PASS"
        kill = entry.get("kill_status") == "KILL"
        live_ok = not entry.get("live_trading_enabled", False)
        paper_ok = not entry.get("paper_trading_enabled", False)
    else:
        trades = 0; days = 0
        safety_ok = True; launch_ok = True
        kill = False; live_ok = True; paper_ok = True

    system_safe = safety_ok and launch_ok

    # Read candidates from trade plan
    candidates = []
    selected_label = None
    selected_levels = {}
    if trade_plan:
        candidates = trade_plan.get("candidates", [])
        selected_label = trade_plan.get("selected_candidate")
        selected_levels = trade_plan.get("selected_levels", {})

    if risk_plan:
        pos_sizing = risk_plan.get("position_sizing", {})
    else:
        pos_sizing = {"position_size": None, "risk_distance": None, "max_loss_if_hit": None, "warning": None}

    # Decision
    decision = "MANUAL_REVIEW_ONLY"
    reasons = []

    if not safety_ok:
        decision = "DO_NOT_TRADE"
        reasons.append("safety lock failed")
    if not launch_ok:
        decision = "DO_NOT_TRADE"
        reasons.append("launch check failed")
    if not live_ok:
        decision = "DO_NOT_TRADE"
        reasons.append("live trading not disabled")
    if not paper_ok:
        decision = "DO_NOT_TRADE"
        reasons.append("paper trading not disabled")
    if kill:
        decision = "DO_NOT_TRADE"
        reasons.append("kill switch triggered")
    if trade_plan and trade_plan.get("trade_decision") == "WAIT" and decision != "DO_NOT_TRADE":
        decision = "DO_NOT_TRADE"
        reasons.append("trade plan says WAIT")
    if selected_label is None:
        if decision != "DO_NOT_TRADE":
            decision = "DO_NOT_TRADE"
        reasons.append("no candidate passes RR gate")
    if trades < MIN_TRADES or days < MIN_DAYS:
        if decision not in ("DO_NOT_TRADE",):
            decision = "MANUAL_REVIEW_ONLY"
        reasons.append(f"evidence incomplete ({trades}/{MIN_TRADES} trades, {days}/{MIN_DAYS} days)")
    if decision == "MANUAL_REVIEW_ONLY" and not any("evidence" in r for r in reasons):
        reasons.append("evidence gates not met")
    if not reasons:
        reasons.append("all checks pass")

    # Format levels for selected candidate
    entry_str = f"{selected_levels.get('entry_zone'):.2f}" if selected_levels.get("entry_zone") is not None else "N/A"
    stop_str = f"{selected_levels.get('stop'):.2f}" if selected_levels.get("stop") is not None else "N/A"
    t1_str = f"{selected_levels.get('target_1'):.2f}" if selected_levels.get("target_1") is not None else "N/A"
    t2_str = f"{selected_levels.get('target_2'):.2f}" if selected_levels.get("target_2") is not None else "N/A"
    rr_1 = selected_levels.get("rr_1")
    rr_2 = selected_levels.get("rr_2")
    rr1_str = f"1:{rr_1:.2f}" if rr_1 is not None else "N/A"
    rr2_str = f"1:{rr_2:.2f}" if rr_2 is not None else "N/A"

    pos_str = f"{pos_sizing.get('position_size'):.6f}" if pos_sizing.get("position_size") is not None else "N/A"
    loss_str = f"{pos_sizing.get('max_loss_if_hit'):.2f}" if pos_sizing.get("max_loss_if_hit") is not None else "N/A"

    # Candidate table
    cand_lines = []
    for c in candidates:
        cand_lines.append("    {:<18s} {:<10s} {:<8s} {:<8s} {:<9s} {:<8s} {:<10s}".format(
            c["label"], c["direction"], c["rr_t1"], c["rr_t2"], c["quality"], c["rr_gate"], c["verdict"]))

    sel_line = f"  TOP CANDIDATE: {selected_label}" if selected_label else "  TOP CANDIDATE: NONE"

    lines = [
        "=" * 60,
        "  DOCTOR DAILY PACKET",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  SYSTEM SAFE:    {'YES' if system_safe else 'NO'}",
        f"  LIVE DISABLED:  {'YES' if live_ok else 'NO'}",
        f"  PAPER DISABLED: {'YES' if paper_ok else 'NO'}",
        "",
        f"  EVIDENCE:       {trades}/{MIN_TRADES} trades, {days}/{MIN_DAYS} days",
        "",
        "  Candidate Table:",
        "    {:<18s} {:<10s} {:<8s} {:<8s} {:<9s} {:<8s} {:<10s}".format(
            "Config", "Direction", "RR T1", "RR T2", "Quality", "RR Gate", "Verdict"),
        "    " + "-" * 70,
    ]
    lines += cand_lines
    lines += [
        "    " + "-" * 70,
        "",
        sel_line,
    ]
    if selected_label:
        lines += [
            "  SETUP LEVELS (selected):",
            f"    ENTRY:     {entry_str}",
            f"    STOP:      {stop_str}",
            f"    TARGET 1:  {t1_str}  (RR {rr1_str})",
            f"    TARGET 2:  {t2_str}  (RR {rr2_str})",
            "",
            "  RISK:",
            f"    POSITION SIZE: {pos_str}",
            f"    MAX LOSS IF STOP HIT: {loss_str} USDT",
        ]
    lines += [
        "",
        f"  FINAL DECISION: {decision}",
        f"  REASON: {'; '.join(reasons)}",
        "",
        "  WARNING: This system is not approved for live trading.",
        "  Manual trading is at user's own risk.",
        "",
        "=" * 60,
    ]

    with open(TXT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")

    report = {
        "mode": "doctor_daily_packet",
        "research_only": True,
        "timestamp": datetime.now().isoformat(),
        "system_safe": system_safe,
        "live_disabled": live_ok,
        "paper_disabled": paper_ok,
        "evidence": {
            "trades": trades,
            "days": days,
        },
        "candidates": candidates,
        "selected_candidate": selected_label,
        "selected_levels": selected_levels,
        "position_sizing": {
            "position_size": pos_sizing.get("position_size"),
            "risk_distance": pos_sizing.get("risk_distance"),
            "max_loss_if_hit": pos_sizing.get("max_loss_if_hit"),
        },
        "final_decision": decision,
        "reason": "; ".join(reasons),
        "disclaimer": "This system is not approved for live trading. Manual trading is at user's own risk.",
    }

    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2)

    print("\n".join(lines))
    print(f"\n[JSON] {JSON_PATH}")
    print(f"[TXT]  {TXT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
