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
    _run_module("production_replay.strategy_tournament")
    _run_module("production_replay.dux_pattern_engine")
    _run_module("production_replay.bingx_shadow_executor")
    _run_module("production_replay.bingx_live_micro_executor")

    trade_plan = _read_json(os.path.join(RESULTS_DIR, "today_trade_plan.json"))
    risk_plan = _read_json(os.path.join(RESULTS_DIR, "manual_risk_plan.json"))
    tournament = _read_json(os.path.join(RESULTS_DIR, "strategy_tournament_report.json"))
    dux = _read_json(os.path.join(RESULTS_DIR, "dux_pattern_report.json"))
    shadow = _read_json(os.path.join(RESULTS_DIR, "bingx_order_intent.json"))
    live = _read_json(os.path.join(RESULTS_DIR, "bingx_live_execution.json"))
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

    # Candidate table (never empty — show placeholder if no rows)
    cand_lines = []
    if not candidates:
        cand_lines.append("    {:<18s} {:<10s} {:<8s} {:<8s} {:<9s} {:<8s} {:<10s} {:<20s}".format(
            "(no configs)", "", "", "", "", "", "", ""))
    for c in candidates:
        reason = c.get("reason", "")
        cand_lines.append("    {:<18s} {:<10s} {:<8s} {:<8s} {:<9s} {:<8s} {:<10s} {:<20s}".format(
            c["label"], c["direction"], c["rr_t1"], c["rr_t2"],
            c["quality"], c["rr_gate"], c["verdict"], reason[:20]))

    # Tournament section
    tournament_lines = []
    if tournament:
        top_strat = tournament.get("top_strategy")
        if top_strat:
            tournament_lines = [
                "",
                "  TOURNAMENT TOP STRATEGY:",
                f"    {top_strat['display_name']} on {top_strat['config_label']}",
                f"    EV: {top_strat['ev_r']}R  PF: {top_strat['pf']}  WR: {top_strat['win_rate']:.1%}",
                f"    Verdict: {top_strat['verdict']}",
            ]
        else:
            tournament_lines = ["", "  TOURNAMENT: No passing strategy", ""]
        tournament_lines += [
            f"    PASS: {tournament['passing']}  WATCH: {tournament['watching']}  "
            f"REJECT: {tournament['rejected']}  SKIP: {tournament['skipped']}",
        ]

    # Dux pattern engine section
    dux_lines = []
    if dux:
        best_dux = dux.get("best_candidate")
        if best_dux:
            dux_lines = [
                "",
                "  DUX-STYLE PATTERN ENGINE:",
                f"    {best_dux['pattern_name']} on {best_dux['symbol']} {best_dux['timeframe']}",
                f"    Direction: {best_dux['direction']}  RR: 1:{best_dux['rr_2']}",
                f"    Stats: {best_dux['stats']['trades']} trades, EV {best_dux['stats']['ev_r']}R",
                f"    Verdict: {best_dux['verdict']}",
            ]
        else:
            dux_lines = ["", "  DUX PATTERN ENGINE: No candidate passes RR >= 4 gate", ""]
        dux_lines += [
            f"    RR >= 4 gate PASS: {dux['rr_gate_pass']}  "
            f"Stats PASS: {dux['stats_pass']}",
            f"    Dux decision: {dux['final_decision']}",
        ]

    # BingX shadow execution section
    shadow_lines = []
    if shadow:
        shadow_decision = shadow.get("decision", "N/A")
        has_intent = shadow.get("shadow_order_intent") is not None
        shadow_lines = [
            "",
            "  BINGX SHADOW EXECUTION:",
            f"    Shadow Intent: {'GENERATED' if has_intent else 'NOT_GENERATED'}",
            f"    Shadow Decision: {shadow_decision}",
        ]
        shr_reasons = shadow.get("reasons", [])
        if shr_reasons:
            shadow_lines.append(f"    Reason: {'; '.join(shr_reasons)}")
    else:
        shadow_lines = ["", "  BINGX SHADOW EXECUTION: MISSING (no report)", ""]

    # BingX live micro execution section
    live_lines = []
    if live:
        lmode = live.get("execution_mode", "?")
        larmed = live.get("live_armed", False)
        lks = live.get("kill_switch", "OFF")
        ldec = live.get("decision", "?")
        lrisk = live.get("risk_usdt", 0)
        ldaily = live.get("environment", {}).get("MAX_DAILY_LOSS_USDT", 0)
        lreasons = live.get("reasons", [])
        live_lines = [
            "",
            "  BINGX LIVE MICRO EXECUTION:",
            f"    Live Executor Available: {'YES' if lmode == 'live_micro' else 'NO'}",
            f"    Live Armed: {'YES' if larmed else 'NO'}",
            f"    Kill Switch: {lks}",
            f"    Max Risk/Trade: {lrisk} USDT",
            f"    Max Daily Loss: {ldaily} USDT",
            f"    Latest Decision: {ldec}",
            f"    Latest Reason: {'; '.join(lreasons[:3])}" if lreasons else "    Latest Reason: N/A",
        ]
    else:
        live_lines = ["", "  BINGX LIVE MICRO EXECUTION: MISSING (no report)", ""]

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
        "    {:<18s} {:<10s} {:<8s} {:<8s} {:<9s} {:<8s} {:<10s} {:<20s}".format(
            "Config", "Direction", "RR T1", "RR T2", "Quality", "RR Gate", "Verdict", "Reason"),
        "    " + "-" * 88,
    ]
    lines += cand_lines
    lines += [
        "    " + "-" * 88,
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
    lines += tournament_lines
    lines += dux_lines
    lines += shadow_lines
    lines += live_lines

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
        "strategy_tournament": {
            "top_strategy": tournament.get("top_strategy") if tournament else None,
            "passing": tournament.get("passing", 0) if tournament else 0,
            "watching": tournament.get("watching", 0) if tournament else 0,
            "rejected": tournament.get("rejected", 0) if tournament else 0,
            "skipped": tournament.get("skipped", 0) if tournament else 0,
        } if tournament else None,
        "dux_pattern_engine": {
            "best_candidate": dux.get("best_candidate") if dux else None,
            "rr_gate_pass": dux.get("rr_gate_pass", 0) if dux else 0,
            "stats_pass": dux.get("stats_pass", 0) if dux else 0,
            "final_decision": dux.get("final_decision", "N/A") if dux else None,
        } if dux else None,
        "bingx_shadow_execution": {
            "shadow_intent": "GENERATED" if shadow and shadow.get("shadow_order_intent") else "NOT_GENERATED",
            "shadow_decision": shadow.get("decision", "N/A") if shadow else None,
            "reason": "; ".join(shadow.get("reasons", ["no shadow report"])) if shadow else None,
        } if shadow else None,
        "bingx_live_micro_execution": {
            "executor_available": live.get("execution_mode") == "live_micro" if live else False,
            "live_armed": live.get("live_armed", False) if live else False,
            "kill_switch": live.get("kill_switch", "OFF") if live else None,
            "max_risk_per_trade_usdt": live.get("risk_usdt", 0) if live else None,
            "max_daily_loss_usdt": live.get("environment", {}).get("MAX_DAILY_LOSS_USDT") if live else None,
            "latest_decision": live.get("decision") if live else None,
            "latest_reason": "; ".join(live.get("reasons", [])) if live else None,
        } if live else None,
    }

    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2)

    print("\n".join(lines))
    print(f"\n[JSON] {JSON_PATH}")
    print(f"[TXT]  {TXT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
