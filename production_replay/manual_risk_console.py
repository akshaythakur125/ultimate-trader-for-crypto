"""Manual risk console — converts today_trade_plan into a safe doctor-mode risk plan.

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


def main():
    parser = argparse.ArgumentParser(description="Manual risk console — decision-support only")
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
        best_candidate = trade_plan.get("best_candidate", "none")
        setup_quality = trade_plan.get("setup_quality", "C")
        system_safe = trade_plan.get("system_safe", False)
        live_disabled = trade_plan.get("live_disabled", False)
        paper_disabled = trade_plan.get("paper_disabled", False)
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
        system_safe = entry.get("safety_lock_verdict") == "ALL LOCKS ENGAGED"
        live_disabled = not entry.get("live_trading_enabled", True)
        paper_disabled = not entry.get("paper_trading_enabled", True)
    else:
        trades = 0; days = 0; ev_r = 0; pf = 0; dd = 0
        kill = False; decision = "WAIT"
        best_candidate = "none"; setup_quality = "C"
        system_safe = True; live_disabled = True; paper_disabled = True

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
    if decision == "MANUAL_REVIEW_ONLY" and risk_instruction != "DO_NOT_TRADE":
        if trades < MIN_TRADES or days < MIN_DAYS:
            risk_instruction = "MANUAL_REVIEW_ONLY"
            reasons.append(f"evidence incomplete ({trades}/{MIN_TRADES} trades, {days}/{MIN_DAYS} days)")
        else:
            risk_instruction = "MANUAL_REVIEW_ONLY"
            reasons.append("evidence gates met but not approved for live trading")
    if not reasons:
        reasons.append("all checks pass")

    reason_str = "; ".join(reasons) if reasons else "unknown"

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
        "best_candidate": best_candidate,
        "setup_quality": setup_quality,
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
        "  MANUAL RISK PLAN — Decision Support Only",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  SYSTEM SAFE:    {'YES' if system_safe else 'NO'}",
        f"  LIVE DISABLED:  {'YES' if live_disabled else 'NO'}",
        f"  PAPER DISABLED: {'YES' if paper_disabled else 'NO'}",
        "",
        f"  Trade decision:   {decision}",
        f"  RISK INSTRUCTION: {risk_instruction}",
        f"  Best candidate:   {best_candidate}",
        f"  Setup quality:    {setup_quality}",
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
