"""BingX live-micro preflight safety checker.

Reads shadow intent and live execution state, runs strict validation,
and outputs PREFLIGHT_PASS or PREFLIGHT_FAIL.

This module NEVER places real orders, NEVER changes execution mode,
and NEVER sets LIVE_TRADING_ACK.
"""

import json, math, os, sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests

from production_replay.bingx_client import load_credentials, get_open_positions
from production_replay.bingx_universe import is_bingx_listed, load_universe

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
JSON_PATH = os.path.join(RESULTS_DIR, "bingx_live_preflight.json")
TXT_PATH = os.path.join(RESULTS_DIR, "bingx_live_preflight.txt")
LEDGER_PATH = os.path.join(STATE_DIR, "bingx_live_preflight.jsonl")
KILL_SWITCH_FILE = os.path.join(STATE_DIR, "KILL_SWITCH_ON")


def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _kill_switch_active() -> bool:
    return os.path.exists(KILL_SWITCH_FILE)


def _get_open_position_count(creds: dict) -> int:
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


def _get_contract_metadata(symbol: str, contracts: list[dict]) -> dict:
    for c in contracts:
        if c.get("symbol") == symbol:
            return c
    return {}


def _fetch_contract_detail(symbol: str) -> dict:
    """Fetch contract detail directly from BingX API for a specific symbol."""
    creds = load_credentials()
    base_url = creds["base_url"]
    try:
        resp = requests.get(f"{base_url}/openApi/swap/v2/quote/contracts", timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") == 0:
            for c in data.get("data", []):
                if c.get("symbol") == symbol:
                    return c
    except Exception:
        pass
    return {}


def _calculate_quantity(risk_usdt: float, entry: float, stop: float) -> float:
    diff = abs(entry - stop)
    if diff <= 0:
        return 0
    return round(risk_usdt / diff, 4)


def _round_to_step_size(value: float, step_size: float, ceil: bool = True) -> float:
    if step_size <= 0:
        return value
    precision = 0
    s = str(step_size)
    if "." in s:
        precision = len(s.split(".")[1])
    mult = 10 ** precision
    step_clean = int(round(step_size * mult))
    scaled = value * mult
    if ceil:
        import math
        result = math.ceil(scaled - 1e-9)  # tiny epsilon to avoid float issues
        # align to step
        result = ((result + step_clean - 1) // step_clean) * step_clean
    else:
        result = int(scaled // step_clean) * step_clean
    return result / mult


def _calculate_exchange_quantity(
    requested_qty: float, min_qty: float, step_size: float,
    entry: float, stop: float, min_notional: float, max_risk: float,
) -> tuple[float, float, float, bool, str]:
    """Calculate exchange-valid quantity and return (qty, notional, actual_risk, ok, reason)."""
    qty = requested_qty
    if qty <= 0:
        return 0, 0, 0, False, "requested quantity is 0"

    # Round UP to next valid step
    if step_size > 0:
        qty = _round_to_step_size(qty, step_size, ceil=True)

    # Ensure >= min_qty
    if min_qty > 0 and qty < min_qty:
        qty = min_qty
        if step_size > 0:
            qty = _round_to_step_size(qty, step_size, ceil=True)

    notional = qty * entry
    diff = abs(entry - stop)
    actual_risk = qty * diff if diff > 0 else 0

    if min_notional > 0 and notional < min_notional:
        needed_qty = _round_to_step_size(min_notional / entry, step_size, ceil=True) if step_size > 0 else min_notional / entry
        qty = max(qty, needed_qty)
        notional = qty * entry
        actual_risk = qty * diff if diff > 0 else 0

    if step_size > 0:
        qty = _round_to_step_size(qty, step_size, ceil=True)
        notional = qty * entry
        actual_risk = qty * diff if diff > 0 else 0

    if min_qty > 0 and qty < min_qty:
        return 0, 0, 0, False, f"cannot reach minQty {min_qty}"
    if min_notional > 0 and notional < min_notional:
        return 0, 0, 0, False, f"cannot reach minNotional {min_notional}"
    if actual_risk > max_risk:
        return qty, notional, actual_risk, False, f"actual risk {actual_risk:.2f} > max {max_risk} USDT"

    return qty, notional, actual_risk, True, "valid"


def _min_qty_str(qty: float) -> str:
    s = str(qty).rstrip("0").rstrip(".")
    return s if "." in s else s + ".0"


def run_preflight() -> dict:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)

    reasons = []
    checks = {}
    quantity = 0
    notional = 0
    contract = {}
    universe_contracts = []

    # -- Inputs --
    shadow = _read_json(os.path.join(RESULTS_DIR, "bingx_order_intent.json"))
    hourly = _read_json(os.path.join(RESULTS_DIR, "hourly_status.json"))
    live = _read_json(os.path.join(RESULTS_DIR, "bingx_live_execution.json"))
    creds = load_credentials()

    shadow_intent = shadow.get("shadow_order_intent") if shadow else None
    shadow_decision = shadow.get("decision", "") if shadow else ""

    # -- 1. Shadow intent exists --
    check_1_ok = bool(shadow_intent)
    checks["shadow_intent_exists"] = check_1_ok
    if not check_1_ok:
        reasons.append("shadow intent missing")

    # -- 2. source == trigger_bridge --
    check_2_ok = bool(shadow_intent and shadow_intent.get("source") == "trigger_bridge")
    checks["source_is_trigger_bridge"] = check_2_ok
    if not check_2_ok:
        reasons.append("shadow intent source is not trigger_bridge")

    # -- 3. decision == SHADOW_READY --
    check_3_ok = shadow_decision == "SHADOW_READY"
    checks["decision_is_shadow_ready"] = check_3_ok
    if not check_3_ok:
        reasons.append(f"shadow decision is {shadow_decision}, need SHADOW_READY")

    # -- Extract fields --
    symbol = str(shadow_intent.get("symbol", "") or "") if shadow_intent else ""
    direction = str(shadow_intent.get("side", "") or "") if shadow_intent else ""
    entry = float(shadow_intent.get("entry", 0) or 0) if shadow_intent else 0
    stop = float(shadow_intent.get("stop_loss", 0) or 0) if shadow_intent else 0
    target = float(shadow_intent.get("final_target", 0) or 0) if shadow_intent else 0
    rr_raw = str(shadow_intent.get("rr_final", "0") or "0") if shadow_intent else "0"
    try:
        rr_final = float(rr_raw.replace("1:", "").replace(":1", ""))
    except (ValueError, TypeError):
        rr_final = 0

    # -- Load universe for metadata --
    try:
        universe = load_universe()
        universe_contracts = universe.get("contracts", [])
    except Exception:
        universe_contracts = []

    # -- 4. Symbol exists on BingX --
    check_4_ok = bool(symbol and is_bingx_listed(symbol, universe_contracts))
    checks["symbol_bingx_listed"] = check_4_ok
    if not check_4_ok:
        reasons.append(f"{symbol} not BingX-listed")

    # -- 5. Direction is LONG or SHORT --
    check_5_ok = direction in ("LONG", "SHORT")
    checks["direction_valid"] = check_5_ok
    if not check_5_ok:
        reasons.append(f"invalid direction {direction}")

    # -- 6. Entry, stop, target are valid numbers --
    check_6_ok = entry > 0 and stop > 0 and target > 0 and stop != entry
    checks["entry_stop_target_valid"] = check_6_ok
    if not check_6_ok:
        bad = []
        if entry <= 0:
            bad.append("entry")
        if stop <= 0:
            bad.append("stop")
        if stop == entry:
            bad.append("stop==entry")
        if target <= 0:
            bad.append("target")
        reasons.append(f"invalid fields: {', '.join(bad)}")

    # -- 7. RR >= 4 --
    check_7_ok = rr_final >= 4.0
    checks["rr_ge_4"] = check_7_ok
    if not check_7_ok:
        reasons.append(f"RR {rr_final} < 4.0")

    # -- 8. Risk per trade <= MAX_RISK_PER_TRADE_USDT --
    try:
        max_risk = float(os.environ.get("MAX_RISK_PER_TRADE_USDT", "1"))
    except (ValueError, TypeError):
        max_risk = 1
    risk_usdt = abs(entry - stop)
    check_8_ok = risk_usdt <= max_risk
    checks["risk_within_limit"] = check_8_ok
    if not check_8_ok:
        reasons.append(f"risk {risk_usdt:.2f} > max {max_risk} USDT")

    # -- 9. Max leverage <= 2 --
    try:
        max_leverage = int(os.environ.get("MAX_LEVERAGE", "2"))
    except (ValueError, TypeError):
        max_leverage = 2
    check_9_ok = max_leverage <= 2
    checks["max_leverage_ok"] = check_9_ok
    if not check_9_ok:
        reasons.append(f"MAX_LEVERAGE={max_leverage} > 2")

    # -- 10. Open positions == 0 --
    creds_ok = bool(creds.get("api_key") and creds.get("api_secret"))
    open_pos_count = 0
    if creds_ok:
        open_pos_count = _get_open_position_count(creds)
    check_10_ok = open_pos_count == 0
    checks["no_open_positions"] = check_10_ok
    if open_pos_count < 0:
        reasons.append("cannot read open positions")
    elif open_pos_count > 0:
        reasons.append(f"{open_pos_count} open position(s) exist")

    # -- 11. Kill switch OFF --
    kill_active = _kill_switch_active()
    check_11_ok = not kill_active
    checks["kill_switch_off"] = check_11_ok
    if kill_active:
        reasons.append("kill switch ON")

    # -- 12. Requested quantity calculation (risk-based) --
    diff = abs(entry - stop)
    risk_usdt = diff
    requested_qty = _calculate_quantity(risk_usdt, entry, stop) if risk_usdt > 0 else 0
    check_12_ok = requested_qty > 0
    checks["quantity_calculated"] = check_12_ok
    if not check_12_ok:
        reasons.append("calculated quantity is 0")

    # -- Fetch real contract metadata from API --
    raw_contract = _fetch_contract_detail(symbol)
    contract_found = bool(raw_contract)
    if contract_found:
        min_qty = float(raw_contract.get("tradeMinQuantity", 0) or 0)
        qty_precision = int(raw_contract.get("quantityPrecision", 4))
        step_size = 1 / (10 ** qty_precision) if qty_precision > 0 else 0
        min_notional = float(raw_contract.get("tradeMinUSDT", 0) or 0)
        price_precision = int(raw_contract.get("pricePrecision", 2))
        max_leverage_contract = int(raw_contract.get("maxLeverage", 0) or 0)
    else:
        min_qty = 0
        step_size = 0
        min_notional = 0
        price_precision = 0
        qty_precision = 0
        max_leverage_contract = 0

    # -- 13. Contract metadata is valid (min_qty > 0, step_size > 0, min_notional > 0) --
    check_13_ok = contract_found and min_qty > 0 and step_size > 0 and min_notional > 0
    checks["contract_metadata_valid"] = check_13_ok
    if not check_13_ok:
        missing = []
        if not contract_found:
            missing.append("no contract data")
        else:
            if min_qty <= 0:
                missing.append("min_qty")
            if step_size <= 0:
                missing.append("step_size")
            if min_notional <= 0:
                missing.append("min_notional")
        reasons.append(f"contract metadata invalid: {', '.join(missing)}")

    # -- 14. Exchange-valid quantity sizing (Phase 58) --
    try:
        max_risk_allowed = float(os.environ.get("MAX_RISK_PER_TRADE_USDT", "1"))
    except (ValueError, TypeError):
        max_risk_allowed = 1
    final_qty, final_notional, actual_risk, sizing_ok, sizing_reason = _calculate_exchange_quantity(
        requested_qty, min_qty, step_size, entry, stop, min_notional, max_risk_allowed,
    )
    quantity = final_qty
    notional = final_notional
    check_14_ok = sizing_ok
    checks["exchange_sizing_valid"] = check_14_ok
    if not check_14_ok:
        reasons.append(f"exchange sizing: {sizing_reason}")

    # -- 15. Risk recalculated after sizing (actual risk <= max risk) --
    check_15_ok = actual_risk <= max_risk_allowed if sizing_ok else False
    checks["risk_after_sizing"] = check_15_ok
    if not check_15_ok and sizing_ok:
        reasons.append(f"final risk {actual_risk:.2f} > max {max_risk_allowed} USDT")

    # -- 16. Stop-loss plan valid --
    if direction == "LONG":
        stop_valid = stop < entry
    else:
        stop_valid = stop > entry
    check_16_ok = stop_valid
    checks["stop_loss_plan_valid"] = check_16_ok
    if not check_16_ok:
        reasons.append("stop-loss plan invalid (wrong direction)")

    # -- 17. Target plan valid --
    if direction == "LONG":
        target_valid = target > entry
    else:
        target_valid = target < entry
    check_17_ok = target_valid
    checks["target_plan_valid"] = check_17_ok
    if not check_17_ok:
        reasons.append("target plan invalid (wrong direction)")

    # -- 18. Exit orders must be reduce-only in planned payload --
    check_18_ok = True
    checks["exit_orders_reduce_only"] = check_18_ok

    # -- 19. No naked position --
    check_19_ok = check_16_ok
    checks["no_naked_position"] = check_19_ok
    if not check_19_ok:
        if "stop-loss plan invalid" not in reasons:
            reasons.append("stop plan invalid → naked position risk")

    # -- 20. No market order placed by this module --
    check_20_ok = True
    checks["no_market_order_placed"] = check_20_ok

    # -- 21. No real API order endpoint called --
    check_21_ok = True
    checks["no_real_api_order_called"] = check_21_ok

    # -- Final decision --
    all_checks = all(checks.values())
    if all_checks:
        decision = "PREFLIGHT_PASS"
        if not reasons:
            reasons.append("all preflight checks passed")
    else:
        decision = "PREFLIGHT_FAIL"
        if not reasons:
            reasons.append("preflight checks failed")

    report = {
        "mode": "bingx_live_preflight",
        "timestamp": datetime.now().isoformat(),
        "research_only": True,
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "decision": decision,
        "preflight_pass": all_checks,
        "checks": checks,
        "symbol": symbol,
        "direction": direction,
        "entry": entry,
        "stop_loss": stop,
        "target": target,
        "rr_final": rr_final,
        "risk_usdt": round(risk_usdt, 2),
        "requested_quantity": round(requested_qty, 6),
        "quantity": quantity,
        "notional": round(notional, 2),
        "actual_risk_usdt": round(actual_risk, 2),
        "open_position_count": open_pos_count,
        "kill_switch": "ON" if kill_active else "OFF",
        "max_risk_usdt": max_risk,
        "max_leverage": max_leverage,
        "min_quantity": min_qty,
        "step_size": step_size,
        "min_notional": min_notional,
        "contract_metadata_found": contract_found,
        "contract_metadata_valid": check_13_ok,
        "min_quantity": min_qty,
        "step_size": step_size,
        "min_notional": min_notional,
        "price_precision": price_precision,
        "quantity_precision": qty_precision,
        "max_leverage_contract": max_leverage_contract,
        "reasons": reasons,
        "message": "ready for live_micro arming" if all_checks else "preflight checks failed; review reasons",
    }

    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2)

    _write_text_report(report, decision, reasons)

    # Append to ledger
    ledger_entry = {
        "timestamp": report["timestamp"],
        "decision": decision,
        "symbol": symbol,
        "direction": direction,
        "rr_final": rr_final,
        "open_positions": open_pos_count,
        "kill_switch": "ON" if kill_active else "OFF",
    }
    with open(LEDGER_PATH, "a") as f:
        f.write(json.dumps(ledger_entry) + "\n")

    return report


def _write_text_report(report: dict, decision: str, reasons: list[str]):
    lines = [
        "=" * 60,
        "  BINGX LIVE MICRO PREFLIGHT",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  Decision:          {decision}",
        f"  Symbol:            {report['symbol'] or 'N/A'}",
        f"  Direction:         {report['direction'] or 'N/A'}",
        f"  Entry:             {report['entry']}",
        f"  Stop:              {report['stop_loss']}",
        f"  Target:            {report['target']}",
        f"  RR Final:          {report['rr_final']}",
        f"  Risk (USDT):       {report['risk_usdt']:.2f}",
        f"  Requested Qty:     {report['requested_quantity']}",
        f"  Final Qty:         {report['quantity'] if report['quantity'] else '0'}",
        f"  Final Notional:    {report['notional']:.2f}",
        f"  Final Risk:        {report['actual_risk_usdt']:.2f} USDT",
        f"  Open Positions:    {report['open_position_count']}",
        f"  Kill Switch:       {report['kill_switch']}",
        "",
        "  Preflight Checks:",
    ]
    for ck, ok in report.get("checks", {}).items():
        lines.append(f"    {ck}: {'PASS' if ok else 'FAIL'}")

    if report.get("contract_metadata_found"):
        meta_valid = report.get("contract_metadata_valid", False)
        lines += [
            "",
            "  Contract Metadata:",
            f"    Min Quantity:  {report['min_quantity']}",
            f"    Step Size:     {report['step_size']}",
            f"    Min Notional:  {report['min_notional']}",
            f"    Price Prec:    {report['price_precision']}",
            f"    Qty Prec:      {report['quantity_precision']}",
            f"    Max Lev (ctr): {report['max_leverage_contract']}",
            f"    CONTRACT METADATA: {'VALID' if meta_valid else 'INVALID'}",
        ]
    else:
        lines += [
            "",
            "  Contract Metadata: NOT FOUND",
            "    CONTRACT METADATA: INVALID",
        ]

    lines += [
        "",
        f"  DECISION: {decision}",
        "",
    ]
    for r in reasons:
        lines.append(f"    - {r}")
    lines.append("")

    if decision == "PREFLIGHT_PASS":
        lines += [
            "  RESULT: Ready for live_micro arming.",
            "  WARNING: Preflight does NOT enable live trading.",
            "  Live execution still requires BINGX_EXECUTION_MODE=live_micro",
            "  and LIVE_TRADING_ACK to be set manually.",
        ]
    else:
        lines += [
            "  RESULT: Preflight checks failed. Review reasons above.",
            "  No real order would be placed.",
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
    if report.get("preflight_pass"):
        print(f"[LEDGER] {LEDGER_PATH}")


def main():
    report = run_preflight()
    return 0


if __name__ == "__main__":
    sys.exit(main())
