"""Paper trade outcome validator — validates paper trades and produces live-readiness verdict.

Reads paper trade ledger and current state, fetches live price via read-only API,
evaluates open trades, aggregates stats from closed trades, and outputs verdict.

This module NEVER places real orders, NEVER sets BINGX_EXECUTION_MODE=live_micro,
and NEVER sets LIVE_TRADING_ACK.
"""

import json, os, sys
from datetime import datetime, timezone
from statistics import mean

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.bingx_client import get_swap_ticker

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
TXT_PATH = os.path.join(RESULTS_DIR, "paper_outcome_report.txt")
JSON_PATH = os.path.join(RESULTS_DIR, "paper_outcome_report.json")
OUTCOME_LEDGER = os.path.join(STATE_DIR, "paper_outcomes.jsonl")
PAPER_TRADE_FILE = os.path.join(STATE_DIR, "current_paper_trade.json")
PORTFOLIO_PATH = os.path.join(STATE_DIR, "paper_portfolio.json")
PAPER_LEDGER = os.path.join(STATE_DIR, "paper_trades.jsonl")
PAPER_STATUS_PATH = os.path.join(RESULTS_DIR, "paper_execution_status.json")

MIN_CLOSED_TRADES_FOR_LIVE_REVIEW = 5


def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _read_ledger(path: str) -> list[dict]:
    try:
        with open(path) as f:
            return [json.loads(l) for l in f if l.strip()]
    except (FileNotFoundError, json.JSONDecodeError):
        return []


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


def _evaluate_trade(
    side: str, entry: float, stop: float, target: float, current_price: float, entry_fill_price: float | None = None,
) -> tuple[str, str | None, float]:
    """Evaluate a trade at a given price.
    Returns (status, hit_reason, exit_price).
    """
    effective_entry = entry_fill_price if entry_fill_price and entry_fill_price > 0 else entry
    if side == "LONG":
        if current_price <= stop:
            return "PAPER_CLOSED", "STOP_HIT", current_price
        if current_price >= target:
            return "PAPER_CLOSED", "TARGET_HIT", current_price
        if current_price >= effective_entry:
            return "PAPER_OPEN", "ENTRY_FILLED", current_price
    else:  # SHORT
        if current_price >= stop:
            return "PAPER_CLOSED", "STOP_HIT", current_price
        if current_price <= target:
            return "PAPER_CLOSED", "TARGET_HIT", current_price
        if current_price <= effective_entry:
            return "PAPER_OPEN", "ENTRY_FILLED", current_price
    return "PAPER_OPEN", None, current_price


def _calculate_pnl(side: str, entry: float, exit_price: float, quantity: float) -> float:
    diff = (exit_price - entry) if side == "LONG" else (entry - exit_price)
    return round(diff * quantity, 4)


def _r_multiple(pnl: float, risk: float) -> float:
    if risk <= 0:
        return 0.0
    return round(pnl / risk, 2)


def _aggregate_closed_trades(trades: list[dict]) -> dict:
    closed = [t for t in trades if t.get("status") == "PAPER_CLOSED" and t.get("realized_pnl") is not None]
    if not closed:
        return {
            "total_closed": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "average_r": 0.0,
            "max_loss": 0.0,
            "consecutive_losses": 0,
        }

    wins = [t for t in closed if t["realized_pnl"] > 0]
    losses = [t for t in closed if t["realized_pnl"] <= 0]
    total_pnl = sum(t["realized_pnl"] for t in closed)
    r_values = []
    for t in closed:
        risk = float(t.get("risk", 0) or 0)
        r = _r_multiple(t["realized_pnl"], risk)
        r_values.append(r)
    max_loss = min((t["realized_pnl"] for t in closed), default=0.0)
    cons = 0
    max_cons = 0
    for t in closed:
        if t["realized_pnl"] <= 0:
            cons += 1
            max_cons = max(max_cons, cons)
        else:
            cons = 0

    return {
        "total_closed": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else 0.0,
        "total_pnl": round(total_pnl, 4),
        "average_r": round(mean(r_values), 2) if r_values else 0.0,
        "max_loss": round(max_loss, 4),
        "consecutive_losses": max_cons,
    }


def _determine_verdict(stats: dict, current_status: str, hit_reason: str | None = None) -> str:
    if current_status == "PAPER_OPEN":
        return "PAPER_OPEN_MONITORING"
    if current_status == "PAPER_CLOSED":
        if hit_reason == "TARGET_HIT":
            return "PAPER_CLOSED_TARGET"
        if hit_reason == "STOP_HIT":
            return "PAPER_CLOSED_STOP"
        return "PAPER_CLOSED"
    if current_status in ("PAPER_SKIPPED", "NO_PAPER_TRADE"):
        if stats["total_closed"] >= MIN_CLOSED_TRADES_FOR_LIVE_REVIEW and stats["average_r"] > 0 and stats["win_rate"] > 50:
            return "LIVE_REVIEW_READY"
        if stats["total_closed"] >= MIN_CLOSED_TRADES_FOR_LIVE_REVIEW:
            return "LIVE_BLOCKED"
        return "LIVE_BLOCKED"
    return "LIVE_BLOCKED"


def run_paper_outcome_validator() -> dict:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)

    paper_trades = _read_ledger(PAPER_LEDGER)
    paper_status = _read_json(PAPER_STATUS_PATH)
    current_trade_data = paper_status.get("current_paper_trade") if paper_status else None

    verdict = "LIVE_BLOCKED"
    reasons = []
    outcome_report = {
        "mode": "paper_outcome_validator",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "real_order": False,
        "total_paper_trades": len(paper_trades),
        "current_trade": None,
        "agg_stats": _aggregate_closed_trades(paper_trades),
        "verdict": verdict,
        "reasons": [],
    }

    if not paper_trades:
        verdict = "NO_PAPER_TRADE"
        reasons.append("no paper trades recorded")
        outcome_report["verdict"] = verdict
        outcome_report["reasons"] = reasons
        _write_outputs(outcome_report)
        return outcome_report

    # Evaluate all active trades from portfolio
    portfolio = _read_json(PORTFOLIO_PATH)
    if isinstance(portfolio, list):
        active_trades_list = [t for t in portfolio if t.get("status") == "PAPER_OPEN"]
    else:
        active_trades_list = []

    evaluated_trades = []
    total_unrealized = 0.0
    primary_trade = None
    for t in active_trades_list:
        sym = t.get("symbol", "")
        side = t.get("side", "")
        entry = float(t.get("entry", 0))
        stop = float(t.get("stop", 0))
        target = float(t.get("target", 0))
        qty = float(t.get("quantity", 0))
        risk = float(t.get("risk", 0))
        entry_fill_price = t.get("entry_fill_price")

        current_price = _get_current_price(sym)

        if current_price and current_price > 0:
            new_status, hit_reason, exit_price = _evaluate_trade(
                side, entry, stop, target, current_price,
                entry_fill_price=float(entry_fill_price) if entry_fill_price is not None else None,
            )
            exit_entry = float(entry_fill_price) if entry_fill_price is not None and float(entry_fill_price) > 0 else entry
            pnl = _calculate_pnl(side, exit_entry, exit_price, qty) if hit_reason in ("STOP_HIT", "TARGET_HIT") else None
            r_val = _r_multiple(pnl, risk) if pnl is not None else None
            if pnl is None:
                total_unrealized += _calculate_pnl(side, exit_entry, current_price, qty)

            evaluated = {
                "symbol": sym,
                "side": side,
                "entry": entry,
                "stop": stop,
                "target": target,
                "quantity": qty,
                "risk_usdt": risk,
                "entry_fill_price": float(entry_fill_price) if entry_fill_price is not None else entry,
                "current_price": current_price,
                "status": new_status,
                "hit_reason": hit_reason,
                "realized_pnl": pnl,
                "r_multiple": r_val,
                "time_open_hours": round(
                    (datetime.now(timezone.utc) - datetime.fromisoformat(
                        t.get("opened_at", datetime.now(timezone.utc).isoformat())
                    )).total_seconds() / 3600, 2
                ),
            }
        else:
            evaluated = {
                "symbol": sym,
                "side": side,
                "entry": entry,
                "stop": stop,
                "target": target,
                "quantity": qty,
                "risk_usdt": risk,
                "current_price": None,
                "status": "PAPER_OPEN",
                "hit_reason": None,
                "realized_pnl": None,
                "r_multiple": None,
                "time_open_hours": None,
            }

        evaluated_trades.append(evaluated)
        if primary_trade is None:
            primary_trade = evaluated

    if len(evaluated_trades) > 0:
        reasons.append(f"{len(evaluated_trades)} active paper trade(s) in portfolio")
        outcome_report["active_trades"] = evaluated_trades
        outcome_report["total_unrealized_pnl"] = round(total_unrealized, 4)
        outcome_report["current_trade"] = primary_trade
    else:
        # Fall back to legacy single-trade check
        current_trade_data = paper_status.get("current_paper_trade") if paper_status else None
        if current_trade_data and current_trade_data.get("status") == "PAPER_OPEN":
            sym = current_trade_data.get("symbol", "")
            side = current_trade_data.get("side", "")
            entry = float(current_trade_data.get("entry", 0))
            stop = float(current_trade_data.get("stop", 0))
            target = float(current_trade_data.get("target", 0))
            qty = float(current_trade_data.get("quantity", 0))
            risk = float(current_trade_data.get("risk", 0))
            entry_fill_price = current_trade_data.get("entry_fill_price")
            current_price = _get_current_price(sym) if sym else None
            if current_price and current_price > 0:
                new_status, hit_reason, exit_price = _evaluate_trade(
                    side, entry, stop, target, current_price,
                    entry_fill_price=float(entry_fill_price) if entry_fill_price is not None else None,
                )
                exit_entry = float(entry_fill_price) if entry_fill_price is not None and float(entry_fill_price) > 0 else entry
                pnl = _calculate_pnl(side, exit_entry, exit_price, qty) if hit_reason in ("STOP_HIT", "TARGET_HIT") else None
                r_val = _r_multiple(pnl, risk) if pnl is not None else None
                primary_trade = {
                    "symbol": sym, "side": side, "entry": entry, "stop": stop,
                    "target": target, "quantity": qty, "risk_usdt": risk,
                    "entry_fill_price": float(entry_fill_price) if entry_fill_price is not None else entry,
                    "current_price": current_price, "status": new_status,
                    "hit_reason": hit_reason, "realized_pnl": pnl, "r_multiple": r_val,
                    "time_open_hours": round(
                        (datetime.now(timezone.utc) - datetime.fromisoformat(
                            current_trade_data.get("opened_at", datetime.now(timezone.utc).isoformat())
                        )).total_seconds() / 3600, 2
                    ),
                }
                evaluated_trades.append(primary_trade)
                outcome_report["active_trades"] = evaluated_trades
                outcome_report["current_trade"] = primary_trade
                reasons.append(f"current trade {sym} {side}: {hit_reason or 'PAPER_OPEN'}")
            else:
                reasons.append(f"cannot fetch price for {sym}")
        elif current_trade_data and current_trade_data.get("status") == "PAPER_CLOSED":
            reasons.append(f"last trade closed: {current_trade_data.get('exit_reason', '?')}")
            outcome_report["current_trade"] = {
                "symbol": current_trade_data.get("symbol", ""),
                "side": current_trade_data.get("side", ""),
                "entry": current_trade_data.get("entry", 0),
                "stop": current_trade_data.get("stop", 0),
                "target": current_trade_data.get("target", 0),
                "quantity": current_trade_data.get("quantity", 0),
                "risk_usdt": current_trade_data.get("risk", 0),
                "current_price": current_trade_data.get("price_at_last_check"),
                "status": "PAPER_CLOSED",
                "hit_reason": current_trade_data.get("exit_reason"),
                "realized_pnl": current_trade_data.get("realized_pnl"),
                "exit_price": current_trade_data.get("exit_price"),
                "r_multiple": _r_multiple(
                    float(current_trade_data.get("realized_pnl", 0)),
                    float(current_trade_data.get("risk", 0)),
                ) if current_trade_data.get("realized_pnl") is not None else None,
            }
        else:
            reasons.append("no current paper trade to evaluate")

    agg = outcome_report["agg_stats"]
    if agg["total_closed"] > 0:
        reasons.append(f"{agg['wins']}W/{agg['losses']}L ({agg['win_rate']}% win rate), total P&L={agg['total_pnl']}, avg R={agg['average_r']}")

    # Determine verdict
    if evaluated_trades:
        any_open = any(t.get("status") == "PAPER_OPEN" for t in evaluated_trades)
        current_status = "PAPER_OPEN" if any_open else "PAPER_CLOSED"
    else:
        current_status = primary_trade.get("status", "N/A") if primary_trade else "NO_PAPER_TRADE"
    verdict = _determine_verdict(agg, current_status, hit_reason=(
        primary_trade.get("hit_reason") if primary_trade else None
    ))
    outcome_report["verdict"] = verdict
    outcome_report["reasons"] = reasons
    outcome_report["active_trade_count"] = len(evaluated_trades)

    _write_outputs(outcome_report)
    return outcome_report


def _write_outputs(report: dict):
    lines = [
        "=" * 60,
        "  PAPER TRADE OUTCOME VALIDATOR",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  Total Paper Trades: {report['total_paper_trades']}",
        f"  Verdict:            {report['verdict']}",
        "",
    ]

    agg = report["agg_stats"]
    lines += [
        "  Aggregate Stats:",
        f"    Closed Trades:         {agg['total_closed']}",
        f"    Wins:                  {agg['wins']}",
        f"    Losses:                {agg['losses']}",
        f"    Win Rate:              {agg['win_rate']}%",
        f"    Total P&L:             {agg['total_pnl']:.2f} USDT",
        f"    Average R:             {agg['average_r']}",
        f"    Max Loss:              {agg['max_loss']:.2f} USDT",
        f"    Consecutive Losses:    {agg['consecutive_losses']}",
        "",
    ]

    ct = report.get("current_trade")
    active_trades = report.get("active_trades", [])
    if active_trades:
        lines += [
            f"  Active Trades: {len(active_trades)}",
        ]
        for i, t in enumerate(active_trades, 1):
            hit = t.get("hit_reason") or "PAPER_OPEN"
            lines += [
                f"    [{i}] {t.get('symbol','?')} {t.get('side','?')} "
                f"Entry:{t.get('entry',0)} Stop:{t.get('stop',0)} Target:{t.get('target',0)} "
                f"Status:{t.get('status','?')} {hit}",
            ]
            if t.get("current_price"):
                lines.append(f"          Price:{t['current_price']} "
                             f"P&L:{t.get('realized_pnl') or t.get('current_price','?')}"
                             f" R:{t.get('r_multiple','?')} "
                             f"Open:{t.get('time_open_hours','?')}h")
        total_upnl = report.get("total_unrealized_pnl", 0)
        if total_upnl:
            lines.append(f"    Total Unrealized P&L: {total_upnl:.4f} USDT")
        lines.append("")
    elif ct:
        hit = ct.get("hit_reason") or "PAPER_OPEN"
        lines += [
            "  Current Trade:",
            f"    Symbol:        {ct.get('symbol', 'N/A')}",
            f"    Side:          {ct.get('side', 'N/A')}",
            f"    Entry:         {ct.get('entry', 0)}",
            f"    Stop:          {ct.get('stop', 0)}",
            f"    Target:        {ct.get('target', 0)}",
            f"    Quantity:      {ct.get('quantity', 0)}",
            f"    Risk:          {ct.get('risk_usdt', 0)} USDT",
            f"    Status:        {ct.get('status', 'N/A')}",
            f"    Hit Reason:    {hit}",
            f"    Current Price: {ct.get('current_price', 'N/A')}",
        ]
        if ct.get("time_open_hours") is not None:
            lines.append(f"    Time Open:      {ct['time_open_hours']}h")
        if ct.get("realized_pnl") is not None:
            lines.append(f"    Realized P&L:   {ct['realized_pnl']:.2f} USDT")
        if ct.get("r_multiple") is not None:
            lines.append(f"    R Multiple:     {ct['r_multiple']}")
        lines.append("")

    lines += [
        "  Live-Readiness Verdict:",
        f"    {report['verdict']}",
        "",
    ]

    for r in report["reasons"]:
        lines.append(f"    - {r}")
    lines += [
        "",
        "  WARNING: Paper outcome validation only. No real orders placed.",
        "",
        "=" * 60,
    ]

    with open(TXT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2)
    print("\n".join(lines))
    print(f"\n[JSON] {JSON_PATH}")
    print(f"[TXT]  {TXT_PATH}")

    # Append to outcome ledger
    ledger_entry = {
        "timestamp": report["timestamp"],
        "verdict": report["verdict"],
        "total_paper_trades": report["total_paper_trades"],
        "agg_stats": report["agg_stats"],
    }
    with open(OUTCOME_LEDGER, "a") as f:
        f.write(json.dumps(ledger_entry) + "\n")
    print(f"[LEDGER] {OUTCOME_LEDGER}")


def main():
    report = run_paper_outcome_validator()
    return 0


if __name__ == "__main__":
    sys.exit(main())
