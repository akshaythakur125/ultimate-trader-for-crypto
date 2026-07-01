"""Continuous live position monitor — tracks open positions every 15 seconds.

Usage:
    python -m production_replay.bingx_position_monitor [--once]

Flags:
    --once    Run a single check and exit (for integration tests)
    (default) Run continuously every MONITOR_INTERVAL_SECONDS (default 15)
"""

import json, os, sys, time, argparse
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.bingx_client import load_credentials, get_open_positions
from production_replay.trade_state_machine import TradeStateMachine, STATE_FILE as TSM_FILE
from production_replay.risk_ledger import RiskLedger, LEDGER_PATH as RISK_LEDGER_PATH

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
TXT_PATH = os.path.join(RESULTS_DIR, "position_monitor_status.txt")
JSON_PATH = os.path.join(RESULTS_DIR, "position_monitor_status.json")
EVENTS_FILE = os.path.join(STATE_DIR, "position_monitor_events.jsonl")
KILL_SWITCH_FILE = os.path.join(STATE_DIR, "KILL_SWITCH_ON")

DEFAULT_INTERVAL = 15
MIN_INTERVAL = 10
MAX_RETRIES = 3


def _kill_active() -> bool:
    return os.path.exists(KILL_SWITCH_FILE)


def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _append_event(event: dict):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(EVENTS_FILE, "a") as f:
        f.write(json.dumps(event) + "\n")


def _check_position(creds: dict) -> dict:
    result = get_open_positions(creds)
    if not result["success"]:
        return {"position_found": False, "error": result.get("error", "API error")}

    data = result["data"]
    positions = []
    if isinstance(data, dict):
        positions = data.get("data", [])
    elif isinstance(data, list):
        positions = data

    if not isinstance(positions, list):
        return {"position_found": False, "error": "unexpected data format"}

    active = [p for p in positions if abs(float(p.get("positionAmt", 0))) > 0]
    if not active:
        return {"position_found": False, "open_positions": 0}

    p = active[0]
    return {
        "position_found": True,
        "open_positions": len(active),
        "symbol": p.get("symbol", ""),
        "position_amt": float(p.get("positionAmt", 0)),
        "entry_price": float(p.get("entryPrice", 0)),
        "mark_price": float(p.get("markPrice", 0)),
        "unrealized_pnl": float(p.get("unrealizedProfit", 0)),
        "liquidation_price": float(p.get("liquidationPrice", 0)),
        "leverage": float(p.get("leverage", 1)),
    }


def run_monitor_check() -> dict:
    creds = load_credentials()
    tsm = TradeStateMachine.load()
    risk = RiskLedger()
    live_report = _read_json(os.path.join(RESULTS_DIR, "bingx_live_execution.json"))

    pos_info = _check_position(creds)
    kill_active = _kill_active()
    expected_symbol = (live_report.get("symbol") if live_report else None)

    events = []
    warnings = []
    r_multiple = None
    risk_per_unit = 0.0
    stop_verified = False
    dist_to_stop_pct = 0.0
    dist_to_target_pct = 0.0

    # 1. Position exists check
    if not pos_info.get("position_found"):
        if tsm.is_active():
            events.append("position_closed_unexpectedly")
            warnings.append("CRITICAL: position closed unexpectedly")
            _append_event({
                "timestamp": datetime.now().isoformat(),
                "type": "CRITICAL",
                "message": "position closed unexpectedly while state was active",
            })
    else:
        sym = pos_info.get("symbol", "")
        amt = pos_info.get("position_amt", 0)
        entry = pos_info.get("entry_price", 0)
        mark = pos_info.get("mark_price", 0)
        upnl = pos_info.get("unrealized_pnl", 0)

        # 2. Symbol matches expected
        if expected_symbol and sym != expected_symbol:
            warnings.append(f"symbol mismatch: {sym} != expected {expected_symbol}")

        # 3. Entry price reasonable
        if entry <= 0:
            warnings.append("invalid entry price")

        # 4. Unrealized PnL tracking
        r_multiple = 0.0
        risk_per_unit = 0.0
        if live_report:
            be = live_report.get("entry") or 0
            bs = live_report.get("stop") or 0
            risk_range = abs(be - bs)
            if risk_range > 0 and entry > 0:
                if amt > 0:  # LONG
                    r_multiple = round((mark - entry) / risk_range, 2)
                else:  # SHORT
                    r_multiple = round((entry - mark) / risk_range, 2)
                risk_per_unit = risk_range

        # 5. Stop loss check (we can't verify exchange stop orders from positions endpoint)
        #    Would need open orders endpoint; mark as assumption
        stop_verified = False  # best-effort; would need get_open_orders API

        # 6. Distance to stop/target
        dist_to_stop_pct = 0.0
        dist_to_target_pct = 0.0
        if live_report:
            stop_price = live_report.get("stop") or 0
            target_price = live_report.get("target") or 0
            if stop_price > 0 and entry > 0:
                dist_to_stop_pct = abs(mark - stop_price) / entry * 100
            if target_price > 0 and entry > 0:
                dist_to_target_pct = abs(mark - target_price) / entry * 100

        # 7. Kill switch
        if kill_active:
            warnings.append("kill switch ON - consider closing position")
            events.append("kill_switch_active")

        # 8. Daily/weekly loss
        if risk.today_pnl <= -2.0:
            warnings.append(f"daily loss limit hit ({risk.today_pnl} USDT)")
            events.append("daily_loss_limit_hit")
        if risk.week_pnl <= -5.0:
            warnings.append(f"weekly loss limit hit ({risk.week_pnl} USDT)")
            events.append("weekly_loss_limit_hit")

        # 9. R multiple thresholds
        if r_multiple >= 1.0:
            events.append("target_1_reached")
        if r_multiple >= 2.0:
            events.append("target_2_reached")

        # 10. Abnormal slippage (rough: mark vs entry divergence > 5%)
        if entry > 0:
            slippage_pct = abs(mark - entry) / entry * 100
            if slippage_pct > 5:
                warnings.append(f"abnormal slippage: {slippage_pct:.1f}%")

        # Update trade state machine
        if tsm.state == "ENTRY_FILLED":
            tsm.transition("PROTECTION_PENDING", "entry filled, protection pending")
        elif tsm.state == "PROTECTION_PENDING":
            tsm.transition("PROTECTED", "stop-loss placed")

        if r_multiple >= 1.0 and tsm.state == "MONITORING":
            tsm.transition("BREAKEVEN_MOVED", f"R multiple {r_multiple} reached")

    if not pos_info.get("position_found") and pos_info.get("error"):
        warnings.append(f"API error: {pos_info['error']}")
        events.append("api_error")

    status = {
        "mode": "position_monitor",
        "timestamp": datetime.now().isoformat(),
        "position_found": pos_info.get("position_found", False),
        "open_positions": pos_info.get("open_positions", 0),
        "symbol": pos_info.get("symbol"),
        "position_amt": pos_info.get("position_amt"),
        "entry_price": pos_info.get("entry_price"),
        "mark_price": pos_info.get("mark_price"),
        "unrealized_pnl_usdt": round(pos_info.get("unrealized_pnl", 0), 2),
        "liquidation_price": pos_info.get("liquidation_price"),
        "leverage": pos_info.get("leverage"),
        "r_multiple": r_multiple if pos_info.get("position_found") else None,
        "risk_per_unit": round(risk_per_unit, 2) if pos_info.get("position_found") else None,
        "stop_verified": stop_verified,
        "distance_to_stop_pct": round(dist_to_stop_pct, 2) if pos_info.get("position_found") else None,
        "distance_to_target_pct": round(dist_to_target_pct, 2) if pos_info.get("position_found") else None,
        "trade_state": tsm.state,
        "kill_switch": "ON" if kill_active else "OFF",
        "daily_pnl_usdt": risk.today_pnl,
        "weekly_pnl_usdt": risk.week_pnl,
        "consecutive_losses": risk.consecutive_losses,
        "can_open_new_trade": tsm.can_open_new_trade() and risk.can_trade,
        "warnings": warnings,
        "events": events,
        "emergency_status": "CRITICAL" if any("CRITICAL" in w for w in warnings) else
                             "WARNING" if warnings else "OK",
    }

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(JSON_PATH, "w") as f:
        json.dump(status, f, indent=2)

    _write_text_report(status, warnings, tsm.state)
    return status


def _write_text_report(status: dict, warnings: list[str], state: str):
    lines = [
        "=" * 60,
        "  POSITION MONITOR",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  Position Found:    {'YES' if status['position_found'] else 'NO'}",
        f"  Symbol:            {status['symbol'] or 'N/A'}",
        f"  Open Positions:    {status['open_positions']}",
        f"  Trade State:       {state}",
        "",
    ]
    if status.get("position_found"):
        lines += [
            f"  Entry Price:       {status['entry_price']}",
            f"  Mark Price:        {status['mark_price']}",
            f"  Unrealized PnL:    {status['unrealized_pnl_usdt']} USDT",
            f"  R Multiple:        {status['r_multiple']}",
            f"  Distance to Stop:  {status['distance_to_stop_pct']}%",
            f"  Distance to Tgt:   {status['distance_to_target_pct']}%",
            f"  Stop Verified:     {'YES' if status['stop_verified'] else 'NO'}",
            f"  Liquidation:       {status['liquidation_price']}",
            f"  Leverage:          {status['leverage']}x",
            "",
        ]

    lines += [
        f"  Daily PnL:         {status['daily_pnl_usdt']} USDT",
        f"  Weekly PnL:        {status['weekly_pnl_usdt']} USDT",
        f"  Consec Losses:     {status['consecutive_losses']}",
        f"  Kill Switch:       {status['kill_switch']}",
        f"  Can Open New:      {'YES' if status['can_open_new_trade'] else 'NO'}",
        f"  Emergency Status:  {status['emergency_status']}",
        "",
    ]
    if warnings:
        lines.append("  WARNINGS:")
        for w in warnings:
            lines.append(f"    - {w}")
        lines.append("")

    lines += [
        "=" * 60,
    ]

    with open(TXT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description="BingX Position Monitor")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    args = parser.parse_args()

    interval = int(os.environ.get("MONITOR_INTERVAL_SECONDS", str(DEFAULT_INTERVAL)))
    if interval < MIN_INTERVAL:
        interval = MIN_INTERVAL

    run_monitor_check()

    if args.once:
        return 0

    # Continuous monitoring loop
    while True:
        time.sleep(interval)
        status = run_monitor_check()
        if status.get("emergency_status") == "CRITICAL":
            print("[CRITICAL] Emergency situation detected!")
            _append_event({"timestamp": datetime.now().isoformat(),
                          "type": "CRITICAL_LOOP", "message": "emergency in monitor loop"})
        tsm = TradeStateMachine.load()
        if tsm.is_terminal() or tsm.state == "IDLE":
            print("[MONITOR] Position closed, exiting monitor loop")
            break

    return 0


if __name__ == "__main__":
    sys.exit(main())
