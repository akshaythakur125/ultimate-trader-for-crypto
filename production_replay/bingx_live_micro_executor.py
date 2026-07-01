"""BingX live micro executor with hard kill switch — OFF by default.

Reads Dux pattern, shadow intent, and doctor packet reports.
Places a single BingX market entry with attached stop-loss ONLY when
all gates pass. Execution mode must be live_micro with explicit ACK.

Usage:
    python -m production_replay.bingx_live_micro_executor
"""

import hashlib, hmac, json, os, sys, time
from datetime import datetime, timedelta
from urllib.parse import urlencode

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests

from production_replay.bingx_client import load_credentials, credentials_found
from production_replay.bingx_universe import is_bingx_listed, load_universe

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
TXT_PATH = os.path.join(RESULTS_DIR, "bingx_live_execution.txt")
JSON_PATH = os.path.join(RESULTS_DIR, "bingx_live_execution.json")
LIVE_LEDGER = os.path.join(STATE_DIR, "bingx_live_orders.jsonl")
KILL_SWITCH_FILE = os.path.join(STATE_DIR, "KILL_SWITCH_ON")

SHADOW_MAX_AGE_MINUTES = 15


def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _sign(params: dict[str, str], secret: str) -> str:
    query = urlencode(sorted(params.items()))
    return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()


def _signed_post(endpoint: str, api_key: str, api_secret: str, base_url: str,
                 params: dict) -> dict:
    params["timestamp"] = str(int(time.time() * 1000))
    params["signature"] = _sign(params, api_secret)
    headers = {"X-BX-APIKEY": api_key, "Content-Type": "application/json"}
    url = f"{base_url}{endpoint}"
    try:
        resp = requests.post(url, json=params, headers=headers, timeout=10)
        resp.raise_for_status()
        return {"success": True, "data": resp.json(), "error": None}
    except requests.RequestException as e:
        return {"success": False, "data": None, "error": str(e)}


def _delete_order(endpoint: str, api_key: str, api_secret: str, base_url: str,
                  params: dict) -> dict:
    params["timestamp"] = str(int(time.time() * 1000))
    params["signature"] = _sign(params, api_secret)
    headers = {"X-BX-APIKEY": api_key, "Content-Type": "application/json"}
    url = f"{base_url}{endpoint}"
    try:
        resp = requests.delete(url, json=params, headers=headers, timeout=10)
        resp.raise_for_status()
        return {"success": True, "data": resp.json(), "error": None}
    except requests.RequestException as e:
        return {"success": False, "data": None, "error": str(e)}


def _kill_switch_active() -> bool:
    return os.path.exists(KILL_SWITCH_FILE)


def _run_check(name: str) -> tuple[bool, str]:
    try:
        import subprocess
        r = subprocess.run(
            [sys.executable, "-m", f"production_replay.{name}"],
            capture_output=True, text=True, timeout=30,
        )
        ok = "PASS" in r.stdout and "FAIL" not in r.stdout
        return ok, r.stdout[:200] if not ok else ""
    except Exception as e:
        return False, str(e)


def _get_open_position_count(creds: dict) -> int:
    from production_replay.bingx_client import get_open_positions
    result = get_open_positions(creds)
    if not result["success"]:
        return -1
    data = result["data"]
    positions = []
    if isinstance(data, dict):
        positions = data.get("data", [])
    elif isinstance(data, list):
        positions = data
    if not isinstance(positions, list):
        return -1
    active = [p for p in positions if abs(float(p.get("positionAmt", 0))) > 0]
    return len(active)


def _stale_intent(shadow_json_path: str) -> bool:
    if not os.path.exists(shadow_json_path):
        return True
    mtime = datetime.fromtimestamp(os.path.getmtime(shadow_json_path))
    age = datetime.now() - mtime
    return age > timedelta(minutes=SHADOW_MAX_AGE_MINUTES)


def run_live_micro_executor() -> dict:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)

    reasons = []
    decision = "DO_NOT_EXECUTE"
    order_result = None
    live_armed = False

    # -- Read inputs --
    dux = _read_json(os.path.join(RESULTS_DIR, "dux_pattern_report.json"))
    psych = _read_json(os.path.join(RESULTS_DIR, "psychology_alpha_report.json"))
    doctor = _read_json(os.path.join(RESULTS_DIR, "doctor_daily_packet.json"))
    shadow = _read_json(os.path.join(RESULTS_DIR, "bingx_order_intent.json"))
    creds = load_credentials()

    # -- 1. Environment gates --
    env_ok = True
    exec_mode = os.environ.get("BINGX_EXECUTION_MODE", "").lower()
    if exec_mode != "live_micro":
        reasons.append(f"BINGX_EXECUTION_MODE={exec_mode}, need live_micro")
        env_ok = False
    live_ack = os.environ.get("LIVE_TRADING_ACK", "")
    if live_ack != "I_UNDERSTAND_THIS_CAN_LOSE_MONEY":
        reasons.append("LIVE_TRADING_ACK not set")
        env_ok = False
    if not credentials_found(creds):
        reasons.append("API credentials not found")
        env_ok = False

    # -- 2. Safety gates --
    safety_ok = True
    if env_ok:
        sl_ok, sl_msg = _run_check("safety_lock")
        if not sl_ok:
            reasons.append(f"safety_lock: {sl_msg[:80]}")
            safety_ok = False
        lc_ok, lc_msg = _run_check("launch_check")
        if not lc_ok:
            reasons.append(f"launch_check: {lc_msg[:80]}")
            safety_ok = False
    if not doctor.get("system_safe", False):
        reasons.append("doctor packet says system not safe")
        safety_ok = False

    # -- 3. Strategy gates --
    strategy_ok = True
    dux_decision = "DO_NOT_TRADE"
    if dux.get("mode") == "dux_pattern_engine":
        dux_decision = dux.get("final_decision", "DO_NOT_TRADE")
    elif "dux_pattern_engine" in doctor:
        dux_decision = doctor["dux_pattern_engine"].get("final_decision", "DO_NOT_TRADE")

    if dux_decision not in ("WATCH", "MANUAL_REVIEW_ONLY"):
        reasons.append(f"Dux decision is {dux_decision}")
        strategy_ok = False

    candidate = None
    if dux.get("mode") == "dux_pattern_engine":
        candidate = dux.get("best_candidate")
    else:
        candidate = doctor.get("dux_pattern_engine", {}).get("best_candidate")

    if not candidate:
        reasons.append("no Dux candidate")
        strategy_ok = False
    else:
        symbol = candidate.get("symbol", "")
        direction = candidate.get("direction", "")
        rr_final = candidate.get("rr_2") or 0
        entry = candidate.get("entry") or 0
        stop = candidate.get("stop") or 0
        target = candidate.get("target_2") or 0

        universe = load_universe()["contracts"]
        if not is_bingx_listed(symbol, universe):
            reasons.append(f"{symbol} not BingX-listed")
            strategy_ok = False
        if direction not in ("LONG", "SHORT"):
            reasons.append(f"invalid direction {direction}")
            strategy_ok = False
        if rr_final < 4.0:
            reasons.append(f"RR {rr_final} < 4.0")
            strategy_ok = False
        if entry <= 0:
            reasons.append("invalid entry")
            strategy_ok = False
        if stop <= 0 or stop == entry:
            reasons.append("invalid stop")
            strategy_ok = False
        if target <= 0:
            reasons.append("invalid target")
            strategy_ok = False
    psych_score = None
    if psych:
        pc = psych.get("best_candidate")
        psych_score = pc["psychology_score"] if pc else None
    if psych_score is None or psych_score < 70:
        reasons.append(f"psychology score {psych_score} < 70")
        strategy_ok = False

    if not strategy_ok:
        reasons.append("strategy gates failed")

    # -- 4. Shadow gate --
    shadow_ok = True
    shadow_path = os.path.join(RESULTS_DIR, "bingx_order_intent.json")
    if not os.path.exists(shadow_path):
        reasons.append("shadow intent file missing")
        shadow_ok = False
    elif _stale_intent(shadow_path):
        reasons.append("shadow intent stale (>15 min)")
        shadow_ok = False
    else:
        shadow_dec = shadow.get("decision", "")
        if shadow_dec != "SHADOW_READY":
            reasons.append(f"shadow decision is {shadow_dec}")
            shadow_ok = False
        shadow_intent = shadow.get("shadow_order_intent")
        if not shadow_intent:
            reasons.append("no shadow order intent")
            shadow_ok = False
        elif shadow_intent.get("real_order") is not False:
            reasons.append("shadow intent real_order not false")
            shadow_ok = False

    # -- 5. Risk gates --
    risk_ok = True
    try:
        max_risk = float(os.environ.get("MAX_RISK_PER_TRADE_USDT", "1"))
        max_daily = float(os.environ.get("MAX_DAILY_LOSS_USDT", "2"))
        max_weekly = float(os.environ.get("MAX_WEEKLY_LOSS_USDT", "5"))
        max_positions = int(os.environ.get("MAX_OPEN_POSITIONS", "1"))
        max_leverage = int(os.environ.get("MAX_LEVERAGE", "2"))
    except (ValueError, TypeError):
        reasons.append("invalid risk env vars")
        risk_ok = False
        max_risk = max_daily = max_weekly = 1
        max_positions = max_leverage = 1

    risk_usdt = abs(entry - stop) if candidate else 0
    if risk_usdt > max_risk:
        reasons.append(f"risk {risk_usdt:.2f} > max {max_risk} USDT")
        risk_ok = False
    if max_risk > 1:
        reasons.append(f"MAX_RISK_PER_TRADE_USDT={max_risk} > 1")
        risk_ok = False
    if max_daily > 2:
        reasons.append(f"MAX_DAILY_LOSS_USDT={max_daily} > 2")
        risk_ok = False
    if max_weekly > 5:
        reasons.append(f"MAX_WEEKLY_LOSS_USDT={max_weekly} > 5")
        risk_ok = False
    if max_positions > 1:
        reasons.append(f"MAX_OPEN_POSITIONS={max_positions} > 1")
        risk_ok = False
    if max_leverage > 2:
        reasons.append(f"MAX_LEVERAGE={max_leverage} > 2")
        risk_ok = False

    # -- 6. Account gates --
    account_ok = True
    open_pos_count = 0
    if env_ok:
        open_pos_count = _get_open_position_count(creds)
        if open_pos_count < 0:
            reasons.append("cannot read open positions")
            account_ok = False
        elif open_pos_count > 0:
            reasons.append(f"{open_pos_count} open positions exist (max 1)")
            account_ok = False

    # -- 7. Kill switch --
    kill_active = _kill_switch_active()
    if kill_active:
        reasons.append("kill switch ON")

    # -- Final decision --
    all_gates = env_ok and safety_ok and strategy_ok and shadow_ok and risk_ok and account_ok and not kill_active

    if all_gates and candidate:
        bingx_side = "BUY" if direction == "LONG" else "SELL"
        qty = 1  # micro quantity placeholder

        # Step 1: place market entry
        entry_result = _signed_post(
            "/openApi/swap/v2/trade/order",
            creds["api_key"], creds["api_secret"], creds["base_url"],
            {"symbol": symbol, "side": bingx_side, "type": "MARKET",
             "quantity": str(qty), "positionSide": "BOTH"},
        )

        if not entry_result["success"]:
            reasons.append(f"entry order failed: {entry_result['error']}")
            decision = "DO_NOT_EXECUTE"
        else:
            # Step 2: place stop-loss
            stop_side = "SELL" if direction == "LONG" else "BUY"
            stop_result = _signed_post(
                "/openApi/swap/v2/trade/order",
                creds["api_key"], creds["api_secret"], creds["base_url"],
                {"symbol": symbol, "side": stop_side, "type": "STOP_MARKET",
                 "quantity": str(qty), "stopPrice": str(stop),
                 "positionSide": "BOTH"},
            )

            if not stop_result["success"]:
                # Cancel the entry order
                reasons.append(f"stop-loss placement failed: {stop_result['error']}; cancelling entry")
                cancel_data = entry_result["data"] or {}
                order_id = ""
                if isinstance(cancel_data, dict):
                    order_id = str(cancel_data.get("orderId", ""))
                if order_id:
                    _delete_order(
                        "/openApi/swap/v2/trade/order",
                        creds["api_key"], creds["api_secret"], creds["base_url"],
                        {"symbol": symbol, "orderId": order_id},
                    )
                reasons.append("entry cancelled — stop-loss could not be guaranteed")
                decision = "DO_NOT_EXECUTE"
            else:
                # Step 3: place take-profit
                tp_side = "SELL" if direction == "LONG" else "BUY"
                tp_result = _signed_post(
                    "/openApi/swap/v2/trade/order",
                    creds["api_key"], creds["api_secret"], creds["base_url"],
                    {"symbol": symbol, "side": tp_side, "type": "TAKE_PROFIT_MARKET",
                     "quantity": str(qty), "stopPrice": str(target),
                     "positionSide": "BOTH"},
                )
                if not tp_result["success"]:
                    reasons.append(f"take-profit placement warning: {tp_result['error']}")

                decision = "EXECUTED"
                order_result = {
                    "entry": entry_result["data"],
                    "stop_loss": stop_result["data"],
                    "take_profit": tp_result["data"] if tp_result["success"] else None,
                }
                live_armed = True
    else:
        decision = "DO_NOT_EXECUTE"
        if not reasons:
            reasons.append("gates not passed")

    report = {
        "mode": "bingx_live_micro_executor",
        "research_only": False,
        "live_trading_enabled": True,
        "paper_trading_enabled": False,
        "execution_mode": exec_mode,
        "live_armed": live_armed,
        "timestamp": datetime.now().isoformat(),
        "kill_switch": "ON" if kill_active else "OFF",
        "inputs": {
            "dux_pattern_report": "dux_pattern_report.json",
            "doctor_daily_packet": "doctor_daily_packet.json",
            "bingx_order_intent": "bingx_order_intent.json",
        },
        "environment": {
            "BINGX_EXECUTION_MODE": exec_mode,
            "LIVE_TRADING_ACK": "SET" if live_ack else "NOT_SET",
            "api_key_found": credentials_found(creds),
            "MAX_RISK_PER_TRADE_USDT": max_risk,
            "MAX_DAILY_LOSS_USDT": max_daily,
            "MAX_WEEKLY_LOSS_USDT": max_weekly,
            "MAX_OPEN_POSITIONS": max_positions,
            "MAX_LEVERAGE": max_leverage,
        },
        "gates": {
            "env_gates": env_ok,
            "safety_gates": safety_ok,
            "strategy_gates": strategy_ok,
            "shadow_gate": shadow_ok,
            "risk_gates": risk_ok,
            "account_gates": account_ok,
            "kill_switch": not kill_active,
        },
        "dux_decision": dux_decision,
        "psychology_score": psych_score,
        "shadow_decision": shadow.get("decision", "N/A") if shadow else "N/A",
        "symbol": symbol if candidate else None,
        "direction": direction if candidate else None,
        "rr_final": rr_final if candidate else 0,
        "entry": entry if candidate else None,
        "stop": stop if candidate else None,
        "target": target if candidate else None,
        "risk_usdt": round(risk_usdt, 2),
        "open_position_count": open_pos_count,
        "order_result": order_result,
        "decision": decision,
        "reasons": reasons if reasons else ["all gates passed"],
    }

    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2)

    _write_text_report(report, decision, reasons, order_result)

    # Append to live orders ledger on execution
    if decision == "EXECUTED" and order_result:
        ledger_entry = {
            "timestamp": report["timestamp"],
            "mode": "live_micro",
            "real_order": True,
            "symbol": symbol,
            "side": bingx_side,
            "entry": entry,
            "stop_loss": stop,
            "target": target,
            "rr_final": rr_final,
            "order_result": order_result,
        }
        with open(LIVE_LEDGER, "a") as f:
            f.write(json.dumps(ledger_entry) + "\n")

    return report


def _write_text_report(report: dict, decision: str, reasons: list[str],
                        order_result: dict | None):
    lines = [
        "=" * 60,
        "  BINGX LIVE MICRO EXECUTOR",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  Execution Mode:     {report['execution_mode']}",
        f"  Live Armed:         {'YES' if report['live_armed'] else 'NO'}",
        f"  Kill Switch:        {report['kill_switch']}",
        "",
        f"  Dux Decision:       {report['dux_decision']}",
        f"  Shadow Decision:    {report['shadow_decision']}",
        f"  Symbol:             {report['symbol'] or 'N/A'}",
        f"  Direction:          {report['direction'] or 'N/A'}",
        f"  RR Final:           {report['rr_final']}",
        f"  Risk (USDT):        {report['risk_usdt']:.2f}",
        f"  Open Positions:     {report['open_position_count']}",
        "",
        "  Gates:",
        f"    Env:      {'PASS' if report['gates']['env_gates'] else 'FAIL'}",
        f"    Safety:   {'PASS' if report['gates']['safety_gates'] else 'FAIL'}",
        f"    Strategy: {'PASS' if report['gates']['strategy_gates'] else 'FAIL'}",
        f"    Shadow:   {'PASS' if report['gates']['shadow_gate'] else 'FAIL'}",
        f"    Risk:     {'PASS' if report['gates']['risk_gates'] else 'FAIL'}",
        f"    Account:  {'PASS' if report['gates']['account_gates'] else 'FAIL'}",
        f"    Kill Sw:  {'PASS' if report['gates']['kill_switch'] else 'FAIL'}",
        "",
    ]

    if order_result:
        lines += [
            "  ORDER EXECUTED:",
            f"    Entry:      {order_result.get('entry')}",
            f"    Stop-Loss:  {order_result.get('stop_loss')}",
            f"    Take-Profit: {order_result.get('take_profit')}",
            "",
        ]

    lines += [
        f"  DECISION: {decision}",
        "",
    ]
    for r in reasons:
        lines.append(f"    - {r}")
    lines.append("")

    if decision == "EXECUTED":
        lines += [
            "  WARNING: Real order placed. Monitor positions immediately.",
        ]
    else:
        lines += [
            "  WARNING: No real order placed. All gates must pass.",
        ]

    lines += [
        "",
        "=" * 60,
    ]

    with open(TXT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n[JSON] {JSON_PATH}")
    print(f"[TXT]  {TXT_PATH}")
    if order_result:
        print(f"[LEDGER] {LIVE_LEDGER}")


def main():
    report = run_live_micro_executor()
    return 0


if __name__ == "__main__":
    sys.exit(main())
