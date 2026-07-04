"""
Phase 80 — CSM Paper Portfolio
Tracks paper positions for cross-sectional momentum strategy.
Market-neutral, equal-weight, rebalanced daily.
"""

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cross_sectional_momentum import get_eligible_symbols, rank_by_momentum, generate_baskets

STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
PORTFOLIO_FILE = os.path.join(STATE_DIR, "csm_paper_portfolio.jsonl")
REPORT_JSON = os.path.join(RESULTS_DIR, "csm_paper_portfolio.json")
REPORT_TXT = os.path.join(RESULTS_DIR, "csm_paper_portfolio.txt")

# Paper account parameters
CAPITAL = 400.0
MAX_GROSS_EXPOSURE = 1.0  # 1x capital
FEE_RATE = 0.0004  # 0.04% per side
SLIPPAGE_RATE = 0.0005  # 0.05% per side

# Default basket size
TOP_N = 5
BOTTOM_N = 5


def _load_portfolio():
    """Load current portfolio from JSONL."""
    if not os.path.exists(PORTFOLIO_FILE):
        return {"positions": [], "cash": CAPITAL, "last_rebalance": None}
    with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]
    if not lines:
        return {"positions": [], "cash": CAPITAL, "last_rebalance": None}
    return json.loads(lines[-1])


def _save_portfolio(portfolio):
    """Append portfolio state to JSONL."""
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(PORTFOLIO_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(portfolio, default=str) + "\n")


def _get_current_price(symbol):
    """Get current price from candle cache."""
    cache_dir = os.path.join(STATE_DIR, "candles_cache")
    path = os.path.join(cache_dir, f"{symbol}_1h.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            candles = json.load(f)
        if candles:
            return candles[-1].get("close")
    except Exception:
        pass
    return None


def rebalance_portfolio(top_n=TOP_N, bottom_n=BOTTOM_N):
    """Rebalance portfolio to new signal.
    Returns new portfolio state.
    """
    portfolio = _load_portfolio()
    now = datetime.now(timezone.utc).isoformat()

    # Get current signal
    eligible = get_eligible_symbols()
    ranked = rank_by_momentum(eligible)
    baskets = generate_baskets(ranked, top_n, bottom_n)

    long_basket = baskets.get("long_basket", [])
    short_basket = baskets.get("short_basket", [])

    if not long_basket or not short_basket:
        print(f"[csm_paper_portfolio] Insufficient symbols for baskets")
        return portfolio

    # Calculate equal weights
    total_positions = len(long_basket) + len(short_basket)
    weight_per_position = MAX_GROSS_EXPOSURE / total_positions

    # Calculate notional per position
    notional_per_position = (CAPITAL * MAX_GROSS_EXPOSURE) / total_positions

    # Build new positions
    new_positions = []

    for s in long_basket:
        symbol = s["symbol"]
        price = _get_current_price(symbol) or s["close"]
        notional = notional_per_position
        quantity = notional / price if price > 0 else 0

        # Apply fee and slippage
        entry_cost = notional * (FEE_RATE + SLIPPAGE_RATE)

        new_positions.append({
            "symbol": symbol,
            "side": "LONG",
            "entry_price": price,
            "current_price": price,
            "quantity": quantity,
            "notional": notional,
            "weight": weight_per_position,
            "entry_cost": entry_cost,
            "unrealized_pnl": 0,
            "entry_time": now,
            "momentum_30d": s["momentum_30d"],
        })

    for s in short_basket:
        symbol = s["symbol"]
        price = _get_current_price(symbol) or s["close"]
        notional = notional_per_position
        quantity = notional / price if price > 0 else 0

        entry_cost = notional * (FEE_RATE + SLIPPAGE_RATE)

        new_positions.append({
            "symbol": symbol,
            "side": "SHORT",
            "entry_price": price,
            "current_price": price,
            "quantity": quantity,
            "notional": notional,
            "weight": weight_per_position,
            "entry_cost": entry_cost,
            "unrealized_pnl": 0,
            "entry_time": now,
            "momentum_30d": s["momentum_30d"],
        })

    # Calculate total exposure
    total_long = sum(p["notional"] for p in new_positions if p["side"] == "LONG")
    total_short = sum(p["notional"] for p in new_positions if p["side"] == "SHORT")

    portfolio = {
        "positions": new_positions,
        "cash": CAPITAL - total_long + total_short,  # simplified
        "total_long_notional": total_long,
        "total_short_notional": total_short,
        "net_exposure": total_long - total_short,
        "gross_exposure": total_long + total_short,
        "num_positions": len(new_positions),
        "last_rebalance": now,
        "live_trading": "NO",
        "real_orders": "NO",
    }

    _save_portfolio(portfolio)
    return portfolio


def update_prices():
    """Update current prices for all positions.
    Returns updated portfolio.
    """
    portfolio = _load_portfolio()
    if not portfolio.get("positions"):
        return portfolio

    total_pnl = 0
    for pos in portfolio["positions"]:
        price = _get_current_price(pos["symbol"])
        if price is not None:
            pos["current_price"] = price
            if pos["side"] == "LONG":
                pos["unrealized_pnl"] = (price - pos["entry_price"]) * pos["quantity"]
            else:
                pos["unrealized_pnl"] = (pos["entry_price"] - price) * pos["quantity"]
            total_pnl += pos["unrealized_pnl"]

    portfolio["total_unrealized_pnl"] = total_pnl
    portfolio["equity"] = CAPITAL + total_pnl

    _save_portfolio(portfolio)
    return portfolio


def get_portfolio_summary():
    """Get current portfolio summary."""
    portfolio = _load_portfolio()
    if not portfolio.get("positions"):
        return {
            "status": "EMPTY",
            "positions": 0,
            "equity": CAPITAL,
            "unrealized_pnl": 0,
            "live_trading": "NO",
        }

    # Update prices
    portfolio = update_prices()

    return {
        "status": "ACTIVE",
        "positions": len(portfolio["positions"]),
        "long_positions": sum(1 for p in portfolio["positions"] if p["side"] == "LONG"),
        "short_positions": sum(1 for p in portfolio["positions"] if p["side"] == "SHORT"),
        "equity": portfolio.get("equity", CAPITAL),
        "unrealized_pnl": portfolio.get("total_unrealized_pnl", 0),
        "total_long_notional": portfolio.get("total_long_notional", 0),
        "total_short_notional": portfolio.get("total_short_notional", 0),
        "last_rebalance": portfolio.get("last_rebalance"),
        "live_trading": "NO",
        "real_orders": "NO",
    }


def run_paper_portfolio(top_n=TOP_N, bottom_n=BOTTOM_N):
    """Run paper portfolio update.
    Returns report dict.
    """
    os.makedirs(RESULTS_DIR, exist_ok=True)

    # Rebalance
    portfolio = rebalance_portfolio(top_n, bottom_n)
    summary = get_portfolio_summary()

    report = {
        "mode": "csm_paper_portfolio",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "capital": CAPITAL,
        "top_n": top_n,
        "bottom_n": bottom_n,
        "portfolio": summary,
        "positions": portfolio.get("positions", []),
        "live_trading": "NO",
        "real_orders": "NO",
    }

    # Write reports
    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    _write_txt_report(report)
    return report


def _write_txt_report(report):
    """Write human-readable TXT report."""
    lines = []
    lines.append("=" * 60)
    lines.append("CSM PAPER PORTFOLIO")
    lines.append(f"  {report['timestamp']}")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"  Capital:           {report['capital']} USDT")
    lines.append(f"  Top N / Bottom N:  {report['top_n']} / {report['bottom_n']}")
    lines.append(f"  Status:            {report['portfolio']['status']}")
    lines.append(f"  Positions:         {report['portfolio']['positions']}")
    lines.append(f"  Equity:            {report['portfolio']['equity']:.2f} USDT")
    lines.append(f"  Unrealized P&L:    {report['portfolio']['unrealized_pnl']:.4f} USDT")
    lines.append(f"  Last Rebalance:    {report['portfolio']['last_rebalance']}")
    lines.append("")

    lines.append("  POSITIONS:")
    for p in report.get("positions", []):
        lines.append(f"    {p['symbol']:15s} {p['side']:5s} "
                     f"entry={p['entry_price']:.6f} "
                     f"current={p['current_price']:.6f} "
                     f"pnl={p['unrealized_pnl']:.4f} "
                     f"mom={p['momentum_30d']:+.4f}")
    lines.append("")

    lines.append("  SAFETY:")
    lines.append(f"    Live Trading: NO")
    lines.append(f"    Real Orders:  NO")
    lines.append(f"    Execution:    read_only")
    lines.append("")
    lines.append("  WARNING: Paper positions only. No real orders placed.")
    lines.append("=" * 60)

    with open(REPORT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    report = run_paper_portfolio()
    print(f"Status: {report['portfolio']['status']}")
    print(f"Positions: {report['portfolio']['positions']}")
    print(f"Equity: {report['portfolio']['equity']:.2f} USDT")
