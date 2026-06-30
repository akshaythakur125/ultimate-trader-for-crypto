"""Hourly alert and final status system.

Reads doctor packet, Dux report, shadow/live execution outputs
and produces a clean one-page status with a final action.

Usage:
    python -m production_replay.hourly_alert
"""

import json, os, sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.bingx_client import load_credentials

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
TXT_PATH = os.path.join(RESULTS_DIR, "hourly_status.txt")
JSON_PATH = os.path.join(RESULTS_DIR, "hourly_status.json")
ALERT_LEDGER = os.path.join(STATE_DIR, "hourly_alerts.jsonl")
KILL_SWITCH_FILE = os.path.join(STATE_DIR, "KILL_SWITCH_ON")


def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _kill_switch_active() -> bool:
    return os.path.exists(KILL_SWITCH_FILE)


def _determine_final_action(
    dux_decision: str,
    rr_gate_pass: int,
    shadow_decision: str,
    live_decision: str,
    live_armed: bool,
    execution_mode: str,
) -> tuple[str, str]:
    # Rule 1: DO_NOT_TRADE -> DO_NOTHING
    if dux_decision == "DO_NOT_TRADE":
        return "DO_NOTHING", "Dux says DO_NOT_TRADE; no action needed"

    # Rule 2: RR >= 4 candidate exists but stats not enough (WATCH)
    if rr_gate_pass > 0 and dux_decision == "WATCH":
        return "REVIEW_NOW", f"RR >= 4 candidate exists ({rr_gate_pass}); manual review recommended"

    # Rule 4: live blocked (check before shadow ready)
    if shadow_decision == "SHADOW_READY" and (not live_armed or execution_mode != "live_micro"):
        return "LIVE_BLOCKED", "Shadow ready but live execution blocked (read_only mode)"

    # Rule 3: shadow ready and live armed
    if shadow_decision == "SHADOW_READY":
        return "SHADOW_READY", "Shadow order intent ready for execution"

    # Fallback
    if live_decision == "DO_NOT_EXECUTE":
        return "DO_NOTHING", "All gates not met; no action"
    return "DO_NOTHING", "No actionable signal"


def run_hourly_alert() -> dict:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)

    doctor = _read_json(os.path.join(RESULTS_DIR, "doctor_daily_packet.json"))
    dux = _read_json(os.path.join(RESULTS_DIR, "dux_pattern_report.json"))
    shadow = _read_json(os.path.join(RESULTS_DIR, "bingx_order_intent.json"))
    live = _read_json(os.path.join(RESULTS_DIR, "bingx_live_execution.json"))

    ts = datetime.now().isoformat()

    # Extract fields
    dux_decision = dux.get("final_decision", "DO_NOT_TRADE") if dux else "DO_NOT_TRADE"
    dux_scan_size = dux.get("dux_scan_universe_size", dux.get("symbols_scanned", 0))
    st_scanned = dux.get("symbol_timeframes_scanned", 0)
    rr_pass = dux.get("rr_gate_pass", 0)
    total_contracts = dux.get("total_raw_contracts", dux.get("total_contracts", 0))
    best = dux.get("best_candidate")

    shadow_decision = shadow.get("decision", "N/A") if shadow else "N/A"
    live_decision = live.get("decision", "N/A") if live else "N/A"
    live_armed = live.get("live_armed", False) if live else False
    execution_mode = live.get("execution_mode", "read_only") if live else "read_only"
    open_positions = live.get("open_position_count", 0) if live else 0
    kill_active = _kill_switch_active()
    creds = load_credentials()
    api_ok = bool(creds.get("api_key") and creds.get("api_secret"))

    final_action, action_reason = _determine_final_action(
        dux_decision, rr_pass, shadow_decision,
        live_decision, live_armed, execution_mode,
    )

    report = {
        "mode": "hourly_alert",
        "timestamp": ts,
        "research_only": True,
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "bingx_contracts_discovered": total_contracts,
        "dux_scan_symbols": dux_scan_size,
        "symbol_timeframes_scanned": st_scanned,
        "rr_gate_pass_candidates": rr_pass,
        "best_candidate": {
            "symbol": best["symbol"],
            "timeframe": best["timeframe"],
            "pattern_name": best["pattern_name"],
            "direction": best["direction"],
            "rr_2": best["rr_2"],
            "verdict": best["verdict"],
        } if best else None,
        "dux_decision": dux_decision,
        "shadow_decision": shadow_decision,
        "live_decision": live_decision,
        "execution_mode": execution_mode,
        "live_armed": live_armed,
        "open_positions": open_positions,
        "api_credentials_found": api_ok,
        "kill_switch": "ON" if kill_active else "OFF",
        "final_action": final_action,
        "action_reason": action_reason,
    }

    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2)

    # Append to alert ledger
    alert_entry = {
        "timestamp": ts,
        "final_action": final_action,
        "dux_decision": dux_decision,
        "shadow_decision": shadow_decision,
        "rr_gate_pass": rr_pass,
        "kill_switch": "ON" if kill_active else "OFF",
    }
    with open(ALERT_LEDGER, "a") as f:
        f.write(json.dumps(alert_entry) + "\n")

    _write_text_report(report, final_action, action_reason)
    return report


def _write_text_report(report: dict, action: str, reason: str):
    best = report.get("best_candidate")
    lines = [
        "=" * 60,
        "  HOURLY FINAL STATUS",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  BingX contracts discovered: {report['bingx_contracts_discovered']}",
        f"  Dux scan symbols:           {report['dux_scan_symbols']}",
        f"  Symbol-timeframes scanned:  {report['symbol_timeframes_scanned']}",
        f"  RR >= 4 candidates:         {report['rr_gate_pass_candidates']}",
        "",
    ]
    if best:
        lines += [
            "  BEST CANDIDATE:",
            f"    {best['pattern_name']} on {best['symbol']} {best['timeframe']}",
            f"    Direction: {best['direction']}  RR: 1:{best['rr_2']}",
            f"    Verdict:   {best['verdict']}",
            "",
        ]
    else:
        lines += ["  BEST CANDIDATE: NONE", ""]

    lines += [
        f"  Dux Decision:       {report['dux_decision']}",
        f"  Shadow Decision:    {report['shadow_decision']}",
        f"  Live Decision:      {report['live_decision']}",
        f"  Execution Mode:     {report['execution_mode']}",
        f"  Live Armed:         {'YES' if report['live_armed'] else 'NO'}",
        f"  Open Positions:     {report['open_positions']}",
        f"  API Credentials:    {'FOUND' if report['api_credentials_found'] else 'NOT FOUND'}",
        f"  Kill Switch:        {report['kill_switch']}",
        "",
        f"  FINAL ACTION: {action}",
        f"  REASON: {reason}",
        "",
        "  WARNING: This system is not approved for live trading.",
        "",
        "  Useful files:",
        "    deploy_results/hourly_status.txt",
        "    deploy_results/doctor_daily_packet.txt",
        "    deploy_results/bingx_live_execution.txt",
        "",
        "=" * 60,
    ]

    with open(TXT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n[JSON] {JSON_PATH}")
    print(f"[TXT]  {TXT_PATH}")
    print(f"[LEDGER] {ALERT_LEDGER}")


def main():
    report = run_hourly_alert()
    return 0


if __name__ == "__main__":
    sys.exit(main())
