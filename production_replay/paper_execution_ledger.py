"""Paper-trade execution ledger for live-micro rehearsal.

Reads shadow intent and preflight output, creates virtual paper positions,
and monitors simulated fills, stops, and targets using read-only market API.

This module NEVER places real orders, NEVER sets BINGX_EXECUTION_MODE=live_micro,
and NEVER sets LIVE_TRADING_ACK.
"""

import json, os, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.bingx_client import get_swap_ticker

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
TXT_PATH = os.path.join(RESULTS_DIR, "paper_execution_status.txt")
JSON_PATH = os.path.join(RESULTS_DIR, "paper_execution_status.json")
PAPER_LEDGER = os.path.join(STATE_DIR, "paper_trades.jsonl")
PAPER_TRADE_FILE = os.path.join(STATE_DIR, "current_paper_trade.json")


def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _read_current_paper_trade() -> dict | None:
    trade = _read_json(PAPER_TRADE_FILE)
    return trade if trade and trade.get("status") not in (None, "") else None


def _write_current_paper_trade(trade: dict):
    with open(PAPER_TRADE_FILE, "w") as f:
        json.dump(trade, f, indent=2)


def _append_to_ledger(trade: dict):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(PAPER_LEDGER, "a") as f:
        f.write(json.dumps(trade) + "\n")


def _get_current_price(symbol: str) -> float | None:
    result = get_swap_ticker(symbol)
    if result["success"]:
        data = result["data"]
        if isinstance(data, dict):
            inner = data.get("data", data)
            if isinstance(inner, dict):
                return float(inner.get("lastPrice", 0) or inner.get("price", 0))
            if isinstance(inner, list) and len(inner) > 0:
                return float(inner[0].get("lastPrice", 0) or inner[0].get("price", 0))
    return None


def _check_hit(side: str, entry: float, stop: float, target: float, current_price: float) -> tuple[str, str | None]:
    """Check whether price would have filled entry, hit stop, or hit target.
    Returns (status, hit_reason) where:
      - PAPER_OPEN + ENTRY_FILLED: entry fillable at current price
      - PAPER_CLOSED + STOP_HIT: stop loss would be triggered
      - PAPER_CLOSED + TARGET_HIT: target would be reached
      - PAPER_OPEN + None: watching, no event yet
    """
    can_enter = (side == "LONG" and current_price >= entry) or (side == "SHORT" and current_price <= entry)

    if not can_enter:
        return "PAPER_OPEN", None

    # Entry is fillable; check if stop or target is also hit
    if side == "LONG":
        if current_price <= stop:
            return "PAPER_CLOSED", "STOP_HIT"
        if current_price >= target:
            return "PAPER_CLOSED", "TARGET_HIT"
    else:  # SHORT
        if current_price >= stop:
            return "PAPER_CLOSED", "STOP_HIT"
        if current_price <= target:
            return "PAPER_CLOSED", "TARGET_HIT"

    return "PAPER_OPEN", "ENTRY_FILLED"


def _calculate_pnl(side: str, entry: float, exit_price: float, quantity: float, reason: str | None) -> float:
    diff = (exit_price - entry) if side == "LONG" else (entry - exit_price)
    return round(diff * quantity, 4)


def run_paper_execution() -> dict:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)

    shadow = _read_json(os.path.join(RESULTS_DIR, "bingx_order_intent.json"))
    preflight = _read_json(os.path.join(RESULTS_DIR, "bingx_live_preflight.json"))
    live = _read_json(os.path.join(RESULTS_DIR, "bingx_live_execution.json"))

    shadow_decision = shadow.get("decision", "") if shadow else ""
    preflight_decision = preflight.get("decision", "") if preflight else ""
    execution_mode = live.get("execution_mode", "read_only") if live else "read_only"
    live_decision = live.get("decision", "") if live else ""

    reasons = []
    status = "PAPER_SKIPPED"

    # -- Gates --
    gate_shadow_ready = shadow_decision == "SHADOW_READY"
    gate_preflight_pass = preflight_decision == "PREFLIGHT_PASS"
    gate_safe_mode = not execution_mode or execution_mode in ("read_only", "shadow_only")
    gate_no_real_order = live_decision != "EXECUTED"

    all_gates = gate_shadow_ready and gate_preflight_pass and gate_safe_mode and gate_no_real_order

    if not gate_shadow_ready:
        reasons.append(f"shadow decision is {shadow_decision}, need SHADOW_READY")
    if not gate_preflight_pass:
        reasons.append(f"preflight decision is {preflight_decision}, need PREFLIGHT_PASS")
    if not gate_safe_mode:
        reasons.append(f"execution mode is {execution_mode}, cannot run paper when live_micro is active")
    if not gate_no_real_order:
        reasons.append("real order was already placed; paper rehearsal skipped")

    # -- Extract data --
    shadow_intent = shadow.get("shadow_order_intent") if shadow else None
    symbol = str(shadow_intent.get("symbol", "")) if shadow_intent else ""
    side = str(shadow_intent.get("side", "") or shadow_intent.get("direction", "")) if shadow_intent else ""
    entry = float(shadow_intent.get("entry", 0)) if shadow_intent else 0
    stop = float(shadow_intent.get("stop_loss", 0)) if shadow_intent else 0
    target = float(shadow_intent.get("final_target", 0)) if shadow_intent else 0
    quantity = float(preflight.get("quantity", 0)) if preflight else 0
    notional = float(preflight.get("notional", 0)) if preflight else 0
    risk = float(preflight.get("actual_risk_usdt", 0)) if preflight else 0
    rr = float(shadow_intent.get("rr_final", 0)) if shadow_intent else 0

    if all_gates and symbol and side and entry > 0 and stop > 0 and target > 0 and quantity > 0:
        # Check if there is an existing paper trade to monitor
        existing = _read_current_paper_trade()

        if existing:
            # Monitor existing trade
            sym = existing.get("symbol", symbol)
            eside = existing.get("side", side)
            eentry = float(existing.get("entry", entry))
            estop = float(existing.get("stop", stop))
            etarget = float(existing.get("target", target))
            eqty = float(existing.get("quantity", quantity))
            enotional = float(existing.get("notional", notional))
            entry_was_filled = existing.get("entry_fill_check", False)
            entry_fill_price = float(existing["entry_fill_price"]) if existing.get("entry_fill_price") is not None else None
            existing_entry_price = entry_fill_price if entry_was_filled and entry_fill_price else eentry

            current_price = _get_current_price(sym)
            if current_price and current_price > 0:
                new_status, hit_reason = _check_hit(eside, eentry, estop, etarget, current_price)

                if not entry_was_filled:
                    # Entry not yet filled
                    can_enter_now = hit_reason == "ENTRY_FILLED"
                    if not can_enter_now:
                        existing["price_at_last_check"] = current_price
                        existing["unrealized_pnl"] = 0.0
                        _write_current_paper_trade(existing)
                        reasons.append(f"paper trade open: {sym} {eside}, waiting for entry at {eentry}, current={current_price}")
                        status = "PAPER_OPEN"
                    else:
                        # Entry just filled
                        existing["entry_fill_price"] = current_price
                        existing["entry_fill_check"] = True
                        existing_entry_price = current_price
                        new_status, hit_reason = _check_hit(eside, existing_entry_price, estop, etarget, current_price)
                        reasons.append(f"entry filled at {current_price}")
                        # Now process stop/target check below
                        if hit_reason in ("STOP_HIT", "TARGET_HIT"):
                            exit_price = current_price
                            pnl = _calculate_pnl(eside, existing_entry_price, exit_price, eqty, hit_reason)
                            existing["status"] = new_status
                            existing["exit_reason"] = hit_reason
                            existing["exit_price"] = exit_price
                            existing["realized_pnl"] = pnl
                            existing["closed_at"] = datetime.now(timezone.utc).isoformat()
                            existing["price_at_last_check"] = current_price
                            _write_current_paper_trade(existing)
                            _append_to_ledger(existing)
                            reasons.append(f"paper trade closed: {sym} {hit_reason} at {exit_price}, P&L={pnl}")
                            status = new_status
                        else:
                            existing["status"] = "PAPER_OPEN"
                            existing["price_at_last_check"] = current_price
                            existing["unrealized_pnl"] = _calculate_pnl(eside, existing_entry_price, current_price, eqty, None)
                            _write_current_paper_trade(existing)
                            reasons.append(f"paper trade open: {sym} {eside}, current={current_price}")
                            status = "PAPER_OPEN"
                else:
                    # Entry was already filled — check stop/target
                    if hit_reason in ("STOP_HIT", "TARGET_HIT"):
                        exit_price = current_price
                        pnl = _calculate_pnl(eside, existing_entry_price, exit_price, eqty, hit_reason)
                        existing["status"] = new_status
                        existing["exit_reason"] = hit_reason
                        existing["exit_price"] = exit_price
                        existing["realized_pnl"] = pnl
                        existing["closed_at"] = datetime.now(timezone.utc).isoformat()
                        existing["price_at_last_check"] = current_price
                        _write_current_paper_trade(existing)
                        _append_to_ledger(existing)
                        reasons.append(f"paper trade closed: {sym} {hit_reason} at {exit_price}, P&L={pnl}")
                        status = new_status
                    else:
                        existing["status"] = "PAPER_OPEN"
                        existing["price_at_last_check"] = current_price
                        existing["unrealized_pnl"] = _calculate_pnl(eside, existing_entry_price, current_price, eqty, None)
                        _write_current_paper_trade(existing)
                        reasons.append(f"paper trade open: {sym} {eside}, current={current_price}")
                        status = "PAPER_OPEN"
            else:
                reasons.append(f"cannot fetch price for existing paper trade {sym}")
                status = existing.get("status", "PAPER_OPEN")
        else:
            # Open new paper trade
            current_price = _get_current_price(symbol)
            if current_price and current_price > 0:
                entry_fill_price = current_price
                entry_filled = False
                # Check if entry would be filled at current price
                fill_status, _ = _check_hit(side, entry, stop, target, current_price)
                if fill_status == "PAPER_OPEN":
                    entry_filled = True
                else:
                    reasons.append(f"entry not fillable at current price {current_price} (entry={entry})")

                paper_trade = {
                    "symbol": symbol,
                    "side": side,
                    "entry": entry,
                    "stop": stop,
                    "target": target,
                    "quantity": quantity,
                    "notional": round(notional, 2),
                    "risk": risk,
                    "rr": rr,
                    "entry_fill_price": entry_fill_price if entry_filled else None,
                    "entry_fill_check": entry_filled,
                    "status": "PAPER_OPEN" if entry_filled else "PAPER_SKIPPED",
                    "exit_reason": None,
                    "exit_price": None,
                    "realized_pnl": None,
                    "unrealized_pnl": 0.0,
                    "price_at_last_check": current_price,
                    "opened_at": datetime.now(timezone.utc).isoformat(),
                    "closed_at": None,
                }
                if not entry_filled:
                    reasons.append(f"paper trade opened (waiting for entry fill)")
                    paper_trade["status"] = "PAPER_OPEN"
                    status = "PAPER_OPEN"
                else:
                    reasons.append(f"paper trade opened: {symbol} {side}, entry fill={entry_fill_price}")
                    status = "PAPER_OPEN"
                _write_current_paper_trade(paper_trade)
                _append_to_ledger(paper_trade)
            else:
                reasons.append(f"cannot fetch current price for {symbol}")
                status = "PAPER_SKIPPED"
    else:
        if not all_gates:
            status = "PAPER_SKIPPED"
            if not reasons:
                reasons.append("paper execution gates not met")
        elif not symbol:
            reasons.append("no symbol in shadow intent")
            status = "PAPER_SKIPPED"
        elif not side:
            reasons.append("no side in shadow intent")
            status = "PAPER_SKIPPED"
        elif quantity <= 0:
            reasons.append("quantity is 0 or missing")
            status = "PAPER_SKIPPED"
        else:
            reasons.append(f"invalid trade parameters: symbol={symbol} side={side} entry={entry} stop={stop} target={target} qty={quantity}")
            status = "PAPER_SKIPPED"

    # Phase 63: Check rotation report for auto-rotation candidate
    if not existing and status == "PAPER_SKIPPED":
        rotation_report = _read_json(os.path.join(RESULTS_DIR, "paper_rotation_report.json"))
        if rotation_report.get("next_action") == "ROTATE_TO_NEW_PAPER_TRADE":
            rc = rotation_report.get("rotation_candidate")
            if rc and rc.get("symbol") and float(rc.get("entry", 0) or 0) > 0 and float(rc.get("stop", 0) or 0) > 0 and float(rc.get("target", 0) or 0) > 0:
                sym = rc["symbol"]
                side_raw = rc.get("direction", "")
                side = "LONG" if side_raw.upper() == "LONG" else "SHORT"
                entry = float(rc["entry"])
                stop = float(rc["stop"])
                target = float(rc["target"])
                rr = float(rc.get("rr", 0) or 0)

                risk_per_unit = abs(entry - stop)
                qty = round(10.0 / risk_per_unit, 4) if risk_per_unit > 0 else 0.001
                notional = entry * qty
                actual_risk = risk_per_unit * qty

                current_price = _get_current_price(sym)
                if not current_price or current_price <= 0:
                    current_price = entry

                paper_trade = {
                    "symbol": sym,
                    "side": side,
                    "entry": entry,
                    "stop": stop,
                    "target": target,
                    "quantity": qty,
                    "notional": round(notional, 2),
                    "risk": round(actual_risk, 4),
                    "rr": rr,
                    "entry_fill_price": current_price,
                    "entry_fill_check": True,
                    "status": "PAPER_OPEN",
                    "exit_reason": None,
                    "exit_price": None,
                    "realized_pnl": None,
                    "unrealized_pnl": 0.0,
                    "price_at_last_check": current_price,
                    "opened_at": datetime.now(timezone.utc).isoformat(),
                    "closed_at": None,
                    "source": "rotation",
                }
                _write_current_paper_trade(paper_trade)
                _append_to_ledger(paper_trade)
                reasons.append(f"paper trade opened via rotation: {sym} {side}, entry={entry}, RR={rr}")
                status = "PAPER_OPEN"

    report = {
        "mode": "paper_execution_ledger",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "real_order": False,
        "status": status,
        "reasons": reasons,
        "gates": {
            "shadow_ready": gate_shadow_ready,
            "preflight_pass": gate_preflight_pass,
            "safe_mode": gate_safe_mode,
            "no_real_order": gate_no_real_order,
            "all_pass": all_gates,
        },
        "current_paper_trade": _read_current_paper_trade(),
    }

    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2)

    _write_text_report(report, status, reasons)
    return report


def _write_text_report(report: dict, status: str, reasons: list[str]):
    current = report.get("current_paper_trade")
    lines = [
        "=" * 60,
        "  PAPER EXECUTION LEDGER",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  Status: {status}",
        "",
        "  Gates:",
    ]
    for gk, gv in report.get("gates", {}).items():
        if gk == "all_pass":
            continue
        label = gk.replace("_", " ").title()
        lines.append(f"    {label}: {'PASS' if gv else 'FAIL'}")
    lines.append(f"    Overall: {'PASS' if report['gates']['all_pass'] else 'FAIL'}")

    if current:
        lines += [
            "",
            "  Current Paper Trade:",
            f"    Symbol:     {current.get('symbol', 'N/A')}",
            f"    Side:       {current.get('side', 'N/A')}",
            f"    Entry:      {current.get('entry', 0)}",
            f"    Stop:       {current.get('stop', 0)}",
            f"    Target:     {current.get('target', 0)}",
            f"    Quantity:   {current.get('quantity', 0)}",
            f"    Notional:   {current.get('notional', 0)}",
            f"    Risk:       {current.get('risk', 0)} USDT",
            f"    RR:         1:{current.get('rr', 0)}",
            f"    Status:     {current.get('status', 'N/A')}",
            f"    Entry Fill: {'YES at ' + str(current.get('entry_fill_price', '')) if current.get('entry_fill_check') else 'NO'}",
        ]
        if current.get("unrealized_pnl") is not None:
            lines.append(f"    Unrealized P&L: {current['unrealized_pnl']:.2f} USDT")
        if current.get("realized_pnl") is not None:
            lines.append(f"    Realized P&L:   {current['realized_pnl']:.2f} USDT")
        if current.get("exit_reason"):
            lines.append(f"    Exit Reason:    {current['exit_reason']}")
        if current.get("exit_price"):
            lines.append(f"    Exit Price:     {current['exit_price']}")
        if current.get("price_at_last_check"):
            lines.append(f"    Current Price:  {current['price_at_last_check']}")
    else:
        lines += ["", "  Current Paper Trade: NONE"]

    lines += [
        "",
    ]
    for r in reasons:
        lines.append(f"    - {r}")
    lines += [
        "",
        "  WARNING: Paper execution only. No real orders placed.",
        "",
        "=" * 60,
    ]

    with open(TXT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n[JSON] {JSON_PATH}")
    print(f"[TXT]  {TXT_PATH}")
    if current:
        print(f"[LEDGER] {PAPER_LEDGER}")


def main():
    report = run_paper_execution()
    return 0


if __name__ == "__main__":
    sys.exit(main())
