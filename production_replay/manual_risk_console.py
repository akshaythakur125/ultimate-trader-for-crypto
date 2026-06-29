"""Manual risk console -- converts today_trade_plan into a safe doctor-mode risk plan.

Reads setup levels from today_trade_plan and calculates position sizing.

Usage:
    python -m production_replay.manual_risk_console
    python -m production_replay.manual_risk_console --capital 50 --risk-per-trade 2
"""

import argparse, json, os, sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.evidence_ledger import read_latest_entry

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
TRADE_PLAN_PATH = os.path.join(RESULTS_DIR, "today_trade_plan.json")
TXT_REPORT = os.path.join(RESULTS_DIR, "manual_risk_plan.txt")
JSON_REPORT = os.path.join(RESULTS_DIR, "manual_risk_plan.json")

MIN_TRADES = 100
MIN_DAYS = 30


def _read_trade_plan() -> dict | None:
    if not os.path.exists(TRADE_PLAN_PATH):
        return None
    with open(TRADE_PLAN_PATH) as f:
        return json.load(f)


def _calc_position_size(entry: float | None, stop: float | None, risk_usdt: float) -> dict:
    if entry is None or stop is None or entry == stop or risk_usdt <= 0:
        return {"position_size": None, "risk_distance": None,
                "max_loss_if_hit": None,
                "warning": "cannot calculate position size -- entry or stop missing"}
    risk_dist = abs(entry - stop)
    if risk_dist <= 0:
        return {"position_size": None, "risk_distance": None,
                "max_loss_if_hit": None,
                "warning": "risk distance is zero or negative"}
    size = risk_usdt / risk_dist
    return {"position_size": round(size, 6), "risk_distance": round(risk_dist, 2),
            "max_loss_if_hit": round(risk_usdt, 2),
            "warning": None}


def main():
    parser = argparse.ArgumentParser(description="Manual risk console -- decision-support only")
    parser.add_argument("--capital", type=float, default=20.0, help="Capital in USDT (default: 20)")
    parser.add_argument("--risk-per-trade", type=float, default=1.0, help="Max risk per trade in USDT (default: 1)")
    parser.add_argument("--max-daily-loss", type=float, default=2.0, help="Max daily loss in USDT (default: 2)")
    parser.add_argument("--max-weekly-loss", type=float, default=5.0, help="Max weekly loss in USDT (default: 5)")
    args, _ = parser.parse_known_args()

    os.makedirs(RESULTS_DIR, exist_ok=True)

    trade_plan = _read_trade_plan()
    entry = read_latest_entry()

    # Extract evidence
    if trade_plan:
        ev = trade_plan.get("evidence", {})
        trades = ev.get("trades_collected", 0)
        days = ev.get("calendar_days_collected", 0)
        ev_r = ev.get("ev_r", 0)
        pf = ev.get("profit_factor", 0)
        dd = ev.get("max_drawdown_r", 0)
        kill = ev.get("kill_switch") == "KILL"
        decision = trade_plan.get("trade_decision", "WAIT")
        best_candidate = trade_plan.get("selected_candidate") or trade_plan.get("best_candidate", "none")
        setup_quality = "N/A"
        direction = "UNKNOWN"
        levels = trade_plan.get("selected_levels", {})
        system_safe = trade_plan.get("system_safe", False)
        live_disabled = trade_plan.get("live_disabled", False)
        paper_disabled = trade_plan.get("paper_disabled", False)
        rr_gate = "FAIL"
        rr_gate_reason = "no passing candidate"
        candidates = trade_plan.get("candidates", [])
        for c in candidates:
            if c.get("verdict") == "CANDIDATE":
                rr_gate = "PASS"
                rr_gate_reason = "OK"
                setup_quality = c.get("quality", "C")
                direction = c.get("direction", "UNKNOWN")
                break
    elif entry:
        trades = entry.get("total_trades", 0)
        days = entry.get("calendar_days", 0)
        ev_r = entry.get("ev_r", 0)
        pf = entry.get("profit_factor", 0)
        dd = entry.get("max_drawdown_r", 0)
        kill = entry.get("kill_status") == "KILL"
        decision = "WAIT"
        best_candidate = "none"
        setup_quality = "C"
        direction = "UNKNOWN"
        levels = {}
        system_safe = entry.get("safety_lock_verdict") == "ALL LOCKS ENGAGED"
        live_disabled = not entry.get("live_trading_enabled", True)
        paper_disabled = not entry.get("paper_trading_enabled", True)
    else:
        trades = 0; days = 0; ev_r = 0; pf = 0; dd = 0
        kill = False; decision = "WAIT"
        best_candidate = "none"; setup_quality = "C"
        direction = "UNKNOWN"; levels = {}
        system_safe = True; live_disabled = True; paper_disabled = True

    # Read setup levels
    entry_price = levels.get("entry_zone") if isinstance(levels, dict) else None
    stop_price = levels.get("stop") if isinstance(levels, dict) else None
    t1_price = levels.get("target_1") if isinstance(levels, dict) else None
    t2_price = levels.get("target_2") if isinstance(levels, dict) else None

    # Calculate position size
    pos = _calc_position_size(entry_price, stop_price, args.risk_per_trade)

    # RR gate from today_trade_plan
    rr_gate_pass = rr_gate == "PASS" if trade_plan else False

    # Decision rules
    risk_instruction = "MANUAL_REVIEW_ONLY"
    reasons = []

    if not system_safe:
        risk_instruction = "DO_NOT_TRADE"
        reasons.append("system unsafe")
    if not live_disabled:
        risk_instruction = "DO_NOT_TRADE"
        reasons.append("live trading enabled")
    if not paper_disabled:
        risk_instruction = "DO_NOT_TRADE"
        reasons.append("paper trading enabled")
    if kill:
        risk_instruction = "DO_NOT_TRADE"
        reasons.append("kill switch triggered")
    if decision == "WAIT":
        risk_instruction = "DO_NOT_TRADE"
        reasons.append("trade plan says WAIT")
    if not rr_gate_pass:
        if risk_instruction != "DO_NOT_TRADE":
            risk_instruction = "WAIT"
        reasons.append(rr_gate_reason)
    if direction == "UNKNOWN" and risk_instruction != "DO_NOT_TRADE":
        risk_instruction = "WAIT"
        reasons.append("direction UNKNOWN")
    if decision == "MANUAL_REVIEW_ONLY" and risk_instruction not in ("DO_NOT_TRADE", "WAIT"):
        if trades < MIN_TRADES or days < MIN_DAYS:
            risk_instruction = "MANUAL_REVIEW_ONLY"
            reasons.append(f"evidence incomplete ({trades}/{MIN_TRADES} trades, {days}/{MIN_DAYS} days)")
        else:
            risk_instruction = "MANUAL_REVIEW_ONLY"
            reasons.append("evidence gates met but not approved for live trading")
    if not reasons:
        reasons.append("all checks pass")

    reason_str = "; ".join(reasons) if reasons else "unknown"

    # Format levels for report
    entry_str = f"{entry_price:.2f}" if entry_price is not None else "N/A"
    stop_str = f"{stop_price:.2f}" if stop_price is not None else "N/A"
    t1_str = f"{t1_price:.2f}" if t1_price is not None else "N/A"
    t2_str = f"{t2_price:.2f}" if t2_price is not None else "N/A"
    pos_str = f"{pos['position_size']:.6f}" if pos["position_size"] is not None else "N/A"
    risk_dist_str = f"{pos['risk_distance']:.2f}" if pos["risk_distance"] is not None else "N/A"
    loss_str = f"{pos['max_loss_if_hit']:.2f}" if pos["max_loss_if_hit"] is not None else "N/A"

    report = {
        "mode": "manual_risk_plan",
        "research_only": True,
        "timestamp": datetime.now().isoformat(),
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "system_safe": system_safe,
        "live_disabled": live_disabled,
        "paper_disabled": paper_disabled,
        "trade_decision": decision,
        "risk_instruction": risk_instruction,
        "direction": direction,
        "best_candidate": best_candidate,
        "setup_quality": setup_quality,
        "rr_gate": "PASS" if rr_gate_pass else "FAIL",
        "rr_gate_reason": rr_gate_reason,
        "setup_levels": {
            "entry_zone": entry_price, "stop": stop_price,
            "target_1": t1_price, "target_2": t2_price,
        },
        "position_sizing": pos,
        "evidence": {
            "trades_collected": trades,
            "calendar_days_collected": days,
            "ev_r": ev_r,
            "profit_factor": pf,
            "max_drawdown_r": dd,
            "kill_switch": "KILL" if kill else "OK",
        },
        "risk_parameters": {
            "capital_usdt": args.capital,
            "max_risk_per_trade_usdt": args.risk_per_trade,
            "max_daily_loss_usdt": args.max_daily_loss,
            "max_weekly_loss_usdt": args.max_weekly_loss,
        },
        "reason": reason_str,
        "disclaimer": "This system is not approved for live trading. Manual trading is at user's own risk.",
    }

    with open(JSON_REPORT, "w") as f:
        json.dump(report, f, indent=2)

    lines = [
        "=" * 60,
        "  MANUAL RISK PLAN -- Decision Support Only",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  SYSTEM SAFE:    {'YES' if system_safe else 'NO'}",
        f"  LIVE DISABLED:  {'YES' if live_disabled else 'NO'}",
        f"  PAPER DISABLED: {'YES' if paper_disabled else 'NO'}",
        "",
        f"  Trade decision:   {decision}",
        f"  RISK INSTRUCTION: {risk_instruction}",
        f"  Direction:        {direction}",
        f"  Best candidate:   {best_candidate}",
        f"  Setup quality:    {setup_quality}",
        f"  RR Gate:          {'PASS' if rr_gate_pass else 'FAIL'} ({rr_gate_reason})",
        "",
        "  Setup Levels:",
        f"    Entry zone:     {entry_str}",
        f"    Stop/Invalid:   {stop_str}",
        f"    Target 1:       {t1_str}",
        f"    Target 2:       {t2_str}",
        "",
        "  Position Sizing:",
        f"    Risk distance:      {risk_dist_str}",
        f"    Estimated position: {pos_str} units",
        f"    Max loss if hit:    {loss_str} USDT",
    ]
    if pos.get("warning"):
        lines.append(f"    Warning:            {pos['warning']}")

    lines += [
        "",
        "  Evidence Status:",
        f"    Trades:  {trades} / {MIN_TRADES}",
        f"    Days:    {days} / {MIN_DAYS}",
        f"    EV:      {ev_r:+.3f}R",
        f"    PF:      {pf:.2f}",
        f"    DD:      {dd:.2f}R",
        f"    Kill:    {'KILL' if kill else 'OK'}",
        "",
        "  Risk Parameters (manual):",
        f"    Capital (USDT):         {args.capital:.1f}",
        f"    Max risk per trade:      {args.risk_per_trade:.1f} USDT",
        f"    Max daily loss:          {args.max_daily_loss:.1f} USDT",
        f"    Max weekly loss:         {args.max_weekly_loss:.1f} USDT",
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

    print("\n".join(lines))
    print(f"\n[JSON] {JSON_REPORT}")
    print(f"[TXT]  {TXT_REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
