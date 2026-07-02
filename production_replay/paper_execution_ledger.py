"""Paper-trade execution ledger for live-micro rehearsal.

Manages a portfolio of up to 5 simultaneous paper trades. Reads shadow intent
and preflight output, creates virtual paper positions, and monitors simulated
fills, stops, and targets using read-only market API.

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
PORTFOLIO_PATH = os.path.join(STATE_DIR, "paper_portfolio.json")

MAX_PAPER_TRADES = 5


def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _read_portfolio() -> list[dict]:
    try:
        with open(PORTFOLIO_PATH) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _write_portfolio(portfolio: list[dict]):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(PORTFOLIO_PATH, "w") as f:
        json.dump(portfolio, f, indent=2)


def _write_current_paper_trade(trade: dict | None):
    with open(PAPER_TRADE_FILE, "w") as f:
        json.dump(trade or {}, f, indent=2)


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
    can_enter = (side == "LONG" and current_price >= entry) or (side == "SHORT" and current_price <= entry)
    if not can_enter:
        return "PAPER_OPEN", None
    if side == "LONG":
        if current_price <= stop:
            return "PAPER_CLOSED", "STOP_HIT"
        if current_price >= target:
            return "PAPER_CLOSED", "TARGET_HIT"
    else:
        if current_price >= stop:
            return "PAPER_CLOSED", "STOP_HIT"
        if current_price <= target:
            return "PAPER_CLOSED", "TARGET_HIT"
    return "PAPER_OPEN", "ENTRY_FILLED"


def _calculate_pnl(side: str, entry: float, exit_price: float, quantity: float) -> float:
    diff = (exit_price - entry) if side == "LONG" else (entry - exit_price)
    return round(diff * quantity, 4)


def _monitor_trade(trade: dict) -> dict:
    """Monitor a single open trade and return updated trade dict."""
    sym = trade.get("symbol", "")
    eside = trade.get("side", "")
    eentry = float(trade.get("entry", 0))
    estop = float(trade.get("stop", 0))
    etarget = float(trade.get("target", 0))
    eqty = float(trade.get("quantity", 0))
    entry_was_filled = trade.get("entry_fill_check", False)
    entry_fill_price = float(trade["entry_fill_price"]) if trade.get("entry_fill_price") is not None else None
    existing_entry_price = entry_fill_price if entry_was_filled and entry_fill_price else eentry

    current_price = _get_current_price(sym)
    if not current_price or current_price <= 0:
        trade["price_at_last_check"] = current_price or eentry
        return trade

    new_status, hit_reason = _check_hit(eside, eentry, estop, etarget, current_price)
    trade["price_at_last_check"] = current_price

    if not entry_was_filled:
        can_enter_now = hit_reason == "ENTRY_FILLED"
        if not can_enter_now:
            trade["unrealized_pnl"] = 0.0
        else:
            trade["entry_fill_price"] = current_price
            trade["entry_fill_check"] = True
            existing_entry_price = current_price
            new_status, hit_reason = _check_hit(eside, existing_entry_price, estop, etarget, current_price)
            if hit_reason in ("STOP_HIT", "TARGET_HIT"):
                pnl = _calculate_pnl(eside, existing_entry_price, current_price, eqty)
                trade["status"] = new_status
                trade["exit_reason"] = hit_reason
                trade["exit_price"] = current_price
                trade["realized_pnl"] = pnl
                trade["closed_at"] = datetime.now(timezone.utc).isoformat()
                trade["_just_closed"] = True
                return trade
            trade["unrealized_pnl"] = _calculate_pnl(eside, existing_entry_price, current_price, eqty)
        trade["status"] = "PAPER_OPEN"
    else:
        if hit_reason in ("STOP_HIT", "TARGET_HIT"):
            pnl = _calculate_pnl(eside, existing_entry_price, current_price, eqty)
            trade["status"] = new_status
            trade["exit_reason"] = hit_reason
            trade["exit_price"] = current_price
            trade["realized_pnl"] = pnl
            trade["closed_at"] = datetime.now(timezone.utc).isoformat()
            trade["_just_closed"] = True
        else:
            trade["status"] = "PAPER_OPEN"
            trade["unrealized_pnl"] = _calculate_pnl(eside, existing_entry_price, current_price, eqty)

    return trade


def _create_trade_from_data(
    symbol: str, side: str, entry: float, stop: float, target: float,
    quantity: float, notional: float, risk: float, rr: float,
    source: str = "shadow",
) -> dict:
    current_price = _get_current_price(symbol)
    if not current_price or current_price <= 0:
        current_price = entry

    fill_status, _ = _check_hit(side, entry, stop, target, current_price)
    entry_filled = fill_status != "PAPER_OPEN"

    return {
        "symbol": symbol,
        "side": side,
        "entry": entry,
        "stop": stop,
        "target": target,
        "quantity": quantity,
        "notional": round(notional, 2),
        "risk": risk,
        "rr": rr,
        "entry_fill_price": current_price if entry_filled else None,
        "entry_fill_check": entry_filled,
        "status": "PAPER_OPEN",
        "exit_reason": None,
        "exit_price": None,
        "realized_pnl": None,
        "unrealized_pnl": 0.0,
        "price_at_last_check": current_price,
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "closed_at": None,
        "source": source,
    }


def _is_duplicate(symbol: str, side: str, portfolio: list[dict]) -> bool:
    return any(
        t.get("symbol") == symbol and t.get("side") == side and t.get("status") == "PAPER_OPEN"
        for t in portfolio
    )


def run_paper_execution() -> dict:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)

    shadow = _read_json(os.path.join(RESULTS_DIR, "bingx_order_intent.json"))
    preflight = _read_json(os.path.join(RESULTS_DIR, "bingx_live_preflight.json"))
    live = _read_json(os.path.join(RESULTS_DIR, "bingx_live_execution.json"))
    rotation_report = _read_json(os.path.join(RESULTS_DIR, "paper_rotation_report.json"))

    shadow_decision = shadow.get("decision", "") if shadow else ""
    preflight_decision = preflight.get("decision", "") if preflight else ""
    execution_mode = live.get("execution_mode", "read_only") if live else "read_only"
    live_decision = live.get("decision", "") if live else ""

    reasons = []
    status = "PAPER_SKIPPED"
    new_trades_opened = []
    skipped_duplicates = []
    rejected_candidates = []

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

    # -- Extract data from shadow intent --
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

    # -- Read existing portfolio --
    portfolio = _read_portfolio()
    active_before = [t for t in portfolio if t.get("status") == "PAPER_OPEN"]

    # -- Monitor all active trades --
    updated_portfolio = []
    for trade in portfolio:
        if trade.get("status") == "PAPER_OPEN":
            updated = _monitor_trade(trade)
            if updated.get("_just_closed"):
                del updated["_just_closed"]
                _append_to_ledger(updated)
                reasons.append(
                    f"paper trade closed: {updated['symbol']} {updated['side']} "
                    f"{updated.get('exit_reason','?')} at {updated.get('exit_price','?')}, "
                    f"P&L={updated.get('realized_pnl',0)}"
                )
            updated_portfolio.append(updated)
        else:
            updated_portfolio.append(trade)

    # -- Try to add new trade from shadow intent --
    if all_gates and symbol and side and entry > 0 and stop > 0 and target > 0 and quantity > 0:
        if len([t for t in updated_portfolio if t.get("status") == "PAPER_OPEN"]) >= MAX_PAPER_TRADES:
            rejected_candidates.append(f"max {MAX_PAPER_TRADES} paper trades reached, cannot add {symbol} {side}")
            reasons.append(f"portfolio full: {symbol} {side} rejected (max {MAX_PAPER_TRADES})")
        elif _is_duplicate(symbol, side, updated_portfolio):
            skipped_duplicates.append(f"{symbol} {side} already active")
            reasons.append(f"duplicate skipped: {symbol} {side} already in portfolio")
        else:
            new_trade = _create_trade_from_data(symbol, side, entry, stop, target, quantity, notional, risk, rr, source="shadow")
            updated_portfolio.append(new_trade)
            new_trades_opened.append(new_trade)
            _append_to_ledger(new_trade)
            reasons.append(f"paper trade opened: {symbol} {side}, entry={entry}, RR={rr}")
            status = "PAPER_OPEN"

    # -- Try to add trade from rotation report --
    rot_candidate = None
    if rotation_report.get("next_action") == "ROTATE_TO_NEW_PAPER_TRADE":
        rc = rotation_report.get("rotation_candidate")
        if rc and rc.get("symbol") and float(rc.get("entry", 0) or 0) > 0 and float(rc.get("stop", 0) or 0) > 0 and float(rc.get("target", 0) or 0) > 0:
            rot_candidate = rc

    if rot_candidate:
        rot_sym = rot_candidate["symbol"]
        rot_side_raw = rot_candidate.get("direction", "")
        rot_side = "LONG" if rot_side_raw.upper() == "LONG" else "SHORT"
        rot_entry = float(rot_candidate["entry"])
        rot_stop = float(rot_candidate["stop"])
        rot_target = float(rot_candidate["target"])
        rot_rr = float(rot_candidate.get("rr", 0) or 0)

        if len([t for t in updated_portfolio if t.get("status") == "PAPER_OPEN"]) >= MAX_PAPER_TRADES:
            rejected_candidates.append(f"max {MAX_PAPER_TRADES} paper trades reached, cannot add {rot_sym} {rot_side} (rotation)")
            reasons.append(f"portfolio full: {rot_sym} {rot_side} rotation rejected (max {MAX_PAPER_TRADES})")
        elif _is_duplicate(rot_sym, rot_side, updated_portfolio):
            skipped_duplicates.append(f"{rot_sym} {rot_side} already active (rotation)")
            reasons.append(f"duplicate skipped (rotation): {rot_sym} {rot_side} already in portfolio")
        else:
            risk_per_unit = abs(rot_entry - rot_stop)
            rot_qty = round(10.0 / risk_per_unit, 4) if risk_per_unit > 0 else 0.001
            rot_notional = rot_entry * rot_qty
            rot_risk = risk_per_unit * rot_qty

            new_trade = _create_trade_from_data(
                rot_sym, rot_side, rot_entry, rot_stop, rot_target,
                rot_qty, rot_notional, rot_risk, rot_rr, source="rotation",
            )
            updated_portfolio.append(new_trade)
            new_trades_opened.append(new_trade)
            _append_to_ledger(new_trade)
            reasons.append(f"paper trade opened via rotation: {rot_sym} {rot_side}, entry={rot_entry}, RR={rot_rr}")
            status = "PAPER_OPEN"

    # -- Determine overall status --
    active_trades = [t for t in updated_portfolio if t.get("status") == "PAPER_OPEN"]
    if active_trades:
        status = "PAPER_OPEN"
    elif new_trades_opened:
        status = "PAPER_OPEN"
    else:
        status = status or "PAPER_SKIPPED"

    # -- Write portfolio (only active trades) --
    _write_portfolio(active_trades)

    # -- Write primary trade (first active, for backward compat) --
    primary = active_trades[0] if active_trades else (updated_portfolio[-1] if updated_portfolio else None)
    _write_current_paper_trade(primary)

    # -- Build report --
    total_notional = sum(float(t.get("notional", 0) or 0) for t in active_trades)
    total_unrealized = sum(float(t.get("unrealized_pnl", 0) or 0) for t in active_trades)
    total_risk = sum(float(t.get("risk", 0) or 0) for t in active_trades)

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
        "current_paper_trade": primary,
        "portfolio": {
            "active_count": len(active_trades),
            "max_allowed": MAX_PAPER_TRADES,
            "active_trades": active_trades,
            "new_trades_opened": new_trades_opened,
            "skipped_duplicates": skipped_duplicates,
            "rejected_candidates": rejected_candidates,
            "total_notional_exposure": round(total_notional, 2),
            "total_unrealized_pnl": round(total_unrealized, 4),
            "total_risk_usdt": round(total_risk, 4),
        },
    }

    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2)

    _write_text_report(report, status, reasons, active_trades, new_trades_opened, skipped_duplicates, rejected_candidates)
    return report


def _write_text_report(
    report: dict, status: str, reasons: list[str],
    active_trades: list[dict], new_trades: list[dict],
    skipped: list[str], rejected: list[str],
):
    current = report.get("current_paper_trade")
    pf = report.get("portfolio", {})
    lines = [
        "=" * 60,
        "  PAPER EXECUTION LEDGER",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  Status: {status}",
        f"  Active Paper Trades: {pf.get('active_count', 0)} / {pf.get('max_allowed', MAX_PAPER_TRADES)}",
        "",
        "  Gates:",
    ]
    for gk, gv in report.get("gates", {}).items():
        if gk == "all_pass":
            continue
        label = gk.replace("_", " ").title()
        lines.append(f"    {label}: {'PASS' if gv else 'FAIL'}")
    lines.append(f"    Overall: {'PASS' if report['gates']['all_pass'] else 'FAIL'}")

    if active_trades:
        lines += ["", "  Active Paper Trades:"]
        for i, t in enumerate(active_trades, 1):
            lines += [
                f"    [{i}] {t.get('symbol','?')} {t.get('side','?')}",
                f"        Entry: {t.get('entry',0)}  Stop: {t.get('stop',0)}  Target: {t.get('target',0)}",
                f"        Qty: {t.get('quantity',0)}  Notional: {t.get('notional',0)}  RR: 1:{t.get('rr',0)}",
                f"        Entry Fill: {'YES' if t.get('entry_fill_check') else 'NO'}  "
                f"Unrealized P&L: {t.get('unrealized_pnl',0):.2f}",
            ]
        lines += [
            "",
            f"  Total Notional Exposure: {pf.get('total_notional_exposure', 0):.2f} USDT",
            f"  Total Unrealized P&L:    {pf.get('total_unrealized_pnl', 0):.4f} USDT",
            f"  Total Risk:              {pf.get('total_risk_usdt', 0):.4f} USDT",
        ]
    else:
        lines += ["", "  Active Paper Trades: NONE"]

    if new_trades:
        lines += ["", "  New Paper Trades This Run:"]
        for t in new_trades:
            lines.append(f"    + {t.get('symbol','?')} {t.get('side','?')} source={t.get('source','?')}")
    if skipped:
        lines += ["", "  Skipped Duplicates:"]
        for s in skipped:
            lines.append(f"    - {s}")
    if rejected:
        lines += ["", "  Rejected Candidates:"]
        for r in rejected:
            lines.append(f"    - {r}")

    lines += ["", ""]
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
    print(f"[PORTFOLIO] {PORTFOLIO_PATH}")
    if current:
        print(f"[LEDGER] {PAPER_LEDGER}")


def main():
    report = run_paper_execution()
    return 0


if __name__ == "__main__":
    sys.exit(main())
