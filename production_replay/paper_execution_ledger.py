"""Paper-trade execution ledger for live-micro rehearsal.

Manages a portfolio of up to 5 simultaneous paper trades with configurable
capital and risk limits. Reads shadow intent and rotation output, creates
virtual paper positions with exchange-compliant sizing, and monitors simulated
fills, stops, and targets using read-only market API.

This module NEVER places real orders, NEVER sets BINGX_EXECUTION_MODE=live_micro,
and NEVER sets LIVE_TRADING_ACK.
"""

import json, math, os, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests

from production_replay.bingx_client import get_swap_ticker, load_credentials

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
TXT_PATH = os.path.join(RESULTS_DIR, "paper_execution_status.txt")
JSON_PATH = os.path.join(RESULTS_DIR, "paper_execution_status.json")
PAPER_LEDGER = os.path.join(STATE_DIR, "paper_trades.jsonl")
PAPER_TRADE_FILE = os.path.join(STATE_DIR, "current_paper_trade.json")
PORTFOLIO_PATH = os.path.join(STATE_DIR, "paper_portfolio.json")

MAX_PAPER_TRADES = 5

# Paper portfolio risk/capital config (hard flat caps)
PAPER_CAPITAL_USDT = 400
PAPER_MAX_RISK_PCT = 0.03
PAPER_MAX_RISK_PER_TRADE_USDT = 12
PAPER_MAX_NOTIONAL_PER_TRADE_USDT = 200
PAPER_MAX_ACTIVE_TRADES = 5
PAPER_MAX_TOTAL_PORTFOLIO_RISK_USDT = 12

# Rejection reason codes
REASON_PORTFOLIO_FULL = "PAPER_MAX_OPEN_TRADES_REACHED"
REASON_DUPLICATE = "PAPER_DUPLICATE_SYMBOL_SIDE"
REASON_RISK_TOO_HIGH = "PAPER_RISK_TOO_HIGH"
REASON_PORTFOLIO_RISK_TOO_HIGH = "PAPER_PORTFOLIO_RISK_TOO_HIGH"
REASON_NOTIONAL_TOO_HIGH_FOR_CAPITAL = "NOTIONAL_TOO_HIGH_FOR_CAPITAL"
REASON_EXCHANGE_MIN_SIZE = "PAPER_EXCHANGE_MIN_SIZE_TOO_LARGE"


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
        result = math.ceil(scaled - 1e-9)
        result = ((result + step_clean - 1) // step_clean) * step_clean
    else:
        result = int(scaled // step_clean) * step_clean
    return result / mult


def _calculate_exchange_quantity(
    requested_qty: float, min_qty: float, step_size: float,
    entry: float, stop: float, min_notional: float, max_risk: float,
) -> tuple[float, float, float, bool, str]:
    qty = requested_qty
    if qty <= 0:
        return 0, 0, 0, False, "requested quantity is 0"
    if step_size > 0:
        qty = _round_to_step_size(qty, step_size, ceil=True)
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


def _fetch_paper_contract_metadata(symbol: str) -> dict:
    creds = load_credentials()
    base_url = creds.get("base_url", "https://api.bingx.com")
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


def _paper_exchange_sizing(symbol: str, entry: float, stop: float) -> dict:
    """Calculate exchange-compliant size for a paper trade using hard capital caps."""
    risk_per_unit = abs(entry - stop)
    target_risk = PAPER_MAX_RISK_PER_TRADE_USDT
    if risk_per_unit <= 0:
        return {"quantity": 0, "notional": 0, "risk": 0, "ok": False, "reason": "stop equals entry"}
    raw_qty = target_risk / risk_per_unit

    raw_contract = _fetch_paper_contract_metadata(symbol)
    if raw_contract:
        min_qty = float(raw_contract.get("tradeMinQuantity", 0) or 0)
        qty_precision = int(raw_contract.get("quantityPrecision", 4))
        step_size = 1 / (10 ** qty_precision) if qty_precision > 0 else 0
        min_notional = float(raw_contract.get("tradeMinUSDT", 0) or 0)
    else:
        min_qty = 0
        step_size = 0
        min_notional = 0

    final_qty, final_notional, actual_risk, sizing_ok, sizing_reason = _calculate_exchange_quantity(
        raw_qty, min_qty, step_size, entry, stop, min_notional, target_risk,
    )

    return {
        "quantity": final_qty,
        "notional": final_notional,
        "risk": actual_risk,
        "ok": sizing_ok,
        "reason": sizing_reason,
        "min_qty": min_qty,
        "step_size": step_size,
        "min_notional": min_notional,
    }


def _paper_risk_check(symbol: str, side: str, entry: float, stop: float, target: float, portfolio: list[dict]) -> dict:
    """Run all paper risk/capital checks using hard capital caps. Returns result dict with ok + reason_code."""
    active_trades = [t for t in portfolio if t.get("status") == "PAPER_OPEN"]
    sizing = _paper_exchange_sizing(symbol, entry, stop)

    if not sizing["ok"]:
        return {"ok": False, "reason_code": REASON_EXCHANGE_MIN_SIZE, "reason": f"exchange sizing failed: {sizing['reason']}", "sizing": sizing}

    final_risk = sizing["risk"]
    final_notional = sizing["notional"]
    final_qty = sizing["quantity"]

    max_risk_per_trade = PAPER_MAX_RISK_PER_TRADE_USDT
    max_portfolio_risk = PAPER_MAX_TOTAL_PORTFOLIO_RISK_USDT
    max_notional_per_trade = PAPER_MAX_NOTIONAL_PER_TRADE_USDT

    if len(active_trades) >= PAPER_MAX_ACTIVE_TRADES:
        return {"ok": False, "reason_code": REASON_PORTFOLIO_FULL, "reason": f"max {PAPER_MAX_ACTIVE_TRADES} open trades reached", "sizing": sizing}

    if final_risk > max_risk_per_trade:
        return {"ok": False, "reason_code": REASON_RISK_TOO_HIGH, "reason": f"risk {final_risk:.2f} > max per trade {max_risk_per_trade:.2f} USDT", "sizing": sizing}

    total_open_risk = sum(float(t.get("risk", 0) or 0) for t in active_trades)
    if total_open_risk + final_risk > max_portfolio_risk:
        return {"ok": False, "reason_code": REASON_PORTFOLIO_RISK_TOO_HIGH, "reason": f"total risk {total_open_risk + final_risk:.2f} > max portfolio {max_portfolio_risk:.2f} USDT", "sizing": sizing}

    if final_notional > max_notional_per_trade:
        return {"ok": False, "reason_code": REASON_NOTIONAL_TOO_HIGH_FOR_CAPITAL, "reason": f"notional {final_notional:.2f} > max {max_notional_per_trade:.2f} USDT for capital {PAPER_CAPITAL_USDT}", "sizing": sizing}

    return {"ok": True, "reason_code": None, "reason": None, "sizing": sizing}


def _monitor_trade(trade: dict) -> dict:
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

    # -- Helper to attempt adding a trade with risk checks --
    def _attempt_add_trade(sym: str, sd: str, en: float, st: float, tg: float, src: str, rr_val: float):
        nonlocal status
        if _is_duplicate(sym, sd, updated_portfolio):
            skipped_duplicates.append(f"{sym} {sd} already active ({src})")
            reasons.append(f"duplicate skipped ({src}): {sym} {sd} already in portfolio")
            return

        risk_result = _paper_risk_check(sym, sd, en, st, tg, updated_portfolio)
        sizin = risk_result.get("sizing", {})
        if not risk_result["ok"]:
            rc = risk_result["reason_code"]
            entry_str = f"entry={en} stop={st} qty={sizin.get('quantity',0)} notional={sizin.get('notional',0)} risk={sizin.get('risk',0)}"
            rejected_candidates.append(f"[{rc}] {sym} {sd} {entry_str} — {risk_result['reason']}")
            reasons.append(f"risk check failed ({rc}): {sym} {sd} — {risk_result['reason']}")
            return

        final_qty = sizin["quantity"]
        final_notional = sizin["notional"]
        final_risk = sizin["risk"]

        new_trade = _create_trade_from_data(
            sym, sd, en, st, tg, final_qty, final_notional, final_risk, rr_val, source=src,
        )
        updated_portfolio.append(new_trade)
        new_trades_opened.append({"symbol": sym, "side": sd, "source": src, "quantity": final_qty, "notional": final_notional, "risk": final_risk})
        _append_to_ledger(new_trade)
        reasons.append(f"paper trade opened: {sym} {sd}, entry={en}, RR={rr_val}, qty={final_qty}, notional={final_notional:.2f}, risk={final_risk:.2f}")
        status = "PAPER_OPEN"

    # -- Try to add new trade from shadow intent --
    if all_gates and symbol and side and entry > 0 and stop > 0 and target > 0 and quantity > 0:
        _attempt_add_trade(symbol, side, entry, stop, target, "shadow", rr)

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
        _attempt_add_trade(rot_sym, rot_side, rot_entry, rot_stop, rot_target, "rotation", rot_rr)

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

    paper_config = {
        "capital_usdt": PAPER_CAPITAL_USDT,
        "max_risk_per_trade_pct": PAPER_MAX_RISK_PCT,
        "max_risk_per_trade_usdt": PAPER_MAX_RISK_PER_TRADE_USDT,
        "max_notional_per_trade_usdt": PAPER_MAX_NOTIONAL_PER_TRADE_USDT,
        "max_active_trades": PAPER_MAX_ACTIVE_TRADES,
        "max_total_portfolio_risk_usdt": PAPER_MAX_TOTAL_PORTFOLIO_RISK_USDT,
    }

    total_risk_pct = round(total_risk / PAPER_CAPITAL_USDT * 100.0, 2) if PAPER_CAPITAL_USDT > 0 else 0

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
        "paper_config": paper_config,
        "current_paper_trade": primary,
        "portfolio": {
            "active_count": len(active_trades),
            "max_allowed": MAX_PAPER_TRADES,
            "available_slots": max(0, MAX_PAPER_TRADES - len(active_trades)),
            "active_trades": active_trades,
            "new_trades_opened": new_trades_opened,
            "skipped_duplicates": skipped_duplicates,
            "rejected_candidates": rejected_candidates,
            "total_notional_exposure": round(total_notional, 2),
            "total_unrealized_pnl": round(total_unrealized, 4),
            "total_risk_usdt": round(total_risk, 4),
            "total_risk_pct": round(total_risk / PAPER_CAPITAL_USDT * 100.0, 2) if PAPER_CAPITAL_USDT > 0 else 0,
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
    pc = report.get("paper_config", {})
    lines = [
        "=" * 60,
        "  PAPER EXECUTION LEDGER",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  Status: {status}",
        f"  Active Paper Trades: {pf.get('active_count', 0)} / {pf.get('max_allowed', MAX_PAPER_TRADES)}",
        "",
        "  Paper Config (Hard Capital Caps):",
        f"    Capital:              {pc.get('capital_usdt', '?')} USDT",
        f"    Max Risk / Trade:     {pc.get('max_risk_per_trade_usdt', '?')} USDT (3.0%)",
        f"    Max Portfolio Risk:   {pc.get('max_total_portfolio_risk_usdt', '?')} USDT",
        f"    Max Notional / Trade: {pc.get('max_notional_per_trade_usdt', '?')} USDT",
        f"    Max Active Trades:    {pc.get('max_active_trades', '?')}",
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
                f"        Risk: {t.get('risk',0):.2f} USDT",
                f"        Entry Fill: {'YES' if t.get('entry_fill_check') else 'NO'}  "
                f"Unrealized P&L: {t.get('unrealized_pnl',0):.2f}",
            ]
        lines += [
            "",
            f"  Total Notional Exposure: {pf.get('total_notional_exposure', 0):.2f} USDT",
            f"  Total Open Risk:         {pf.get('total_risk_usdt', 0):.2f} USDT ({pf.get('total_risk_pct', 0)}% of capital)",
            f"  Total Unrealized P&L:    {pf.get('total_unrealized_pnl', 0):.4f} USDT",
        ]
    else:
        lines += ["", "  Active Paper Trades: NONE"]

    if new_trades:
        lines += ["", "  New Paper Trades This Run:"]
        for t in new_trades:
            lines.append(f"    + {t.get('symbol','?')} {t.get('side','?')} source={t.get('source','?')} qty={t.get('quantity',0)} notional={t.get('notional',0):.2f} risk={t.get('risk',0):.2f}")
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
