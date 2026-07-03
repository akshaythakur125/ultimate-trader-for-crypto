"""Legacy paper trade cleanup for Phase 75.

Scans the current paper portfolio and marks invalid legacy trades:
- Missing strategy_family
- Missing promotion_tier
- Unknown family
- OBSERVE_ONLY family
- REJECTED family
- Violating risk/notional caps (LINK-USDT 7350 notional > 800 cap)

Invalid trades are marked PAPER_INVALID_LEGACY_PROMOTION_GATE and removed
from the active portfolio. They are NOT counted as win/loss or evidence.

This module NEVER places real orders, NEVER enables live trading.
"""

import json, os, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
PORTFOLIO_PATH = os.path.join(STATE_DIR, "paper_portfolio.json")
PAPER_LEDGER = os.path.join(STATE_DIR, "paper_trades.jsonl")
TXT_PATH = os.path.join(RESULTS_DIR, "paper_legacy_cleanup_report.txt")
JSON_PATH = os.path.join(RESULTS_DIR, "paper_legacy_cleanup_report.json")

# Risk limits (Phase 75: stricter)
PAPER_CAPITAL_USDT = 400
PAPER_MAX_RISK_PER_TRADE_USDT = 12
PAPER_MAX_PORTFOLIO_NOTIONAL_USDT = 800
PAPER_MAX_NOTIONAL_PER_TRADE_USDT = 100  # 25% of capital
PAPER_MAX_ACTIVE_TRADES = 3  # reduced from 5

# Thesis type to strategy family mapping
THESIS_TYPE_TO_FAMILY = {
    "SWEEP_HIGH": "liquidity_sweep_reversal",
    "SWEEP_LOW": "liquidity_sweep_reversal",
    "UPPER_WICK_EXTENSION": "liquidity_sweep_reversal",
    "LOWER_WICK_EXTENSION": "liquidity_sweep_reversal",
    "COMPRESSION": "compression_breakout",
    "BREAKOUT": "compression_breakout",
    "EMA_PULLBACK": "trend_pullback",
    "TREND_PULLBACK": "trend_pullback",
    "MEAN_REVERSION": "mean_reversion",
    "SHORT_WEAKNESS": "short_weakness",
}

# Promotion tiers that allow paper trading
PAPER_ALLOWED_TIERS = {"PAPER_CANDIDATE", "PAPER_PRIORITY"}


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


def _append_to_ledger(trade: dict):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(PAPER_LEDGER, "a") as f:
        f.write(json.dumps(trade) + "\n")


def _load_promotion_tiers() -> dict[str, str]:
    report = _read_json(os.path.join(RESULTS_DIR, "strategy_promotion_arbiter_report.json"))
    families = report.get("families", {})
    return {name: info.get("tier", "UNKNOWN") for name, info in families.items()}


def resolve_strategy_family(trade: dict) -> str:
    family = trade.get("strategy_family", "")
    if family and family != "unknown":
        return family
    thesis_type = trade.get("thesis_type", "")
    family = THESIS_TYPE_TO_FAMILY.get(thesis_type, "")
    if family:
        return family
    pattern = trade.get("pattern_name", "")
    family = THESIS_TYPE_TO_FAMILY.get(pattern, "")
    if family:
        return family
    return "unknown"


def _check_promotion_gate(family: str, promotion_tiers: dict[str, str]) -> tuple[bool, str, str]:
    if family == "unknown":
        return False, "UNKNOWN", "PAPER_FAMILY_UNKNOWN"
    tier = promotion_tiers.get(family, "UNKNOWN")
    if tier in PAPER_ALLOWED_TIERS:
        return True, tier, ""
    if tier == "REJECTED":
        return False, tier, "PAPER_FAMILY_REJECTED"
    if tier == "OBSERVE_ONLY":
        return False, tier, "PAPER_FAMILY_NOT_PROMOTED"
    return False, tier, "PAPER_FAMILY_NOT_PROMOTED"


def _check_risk_caps(trade: dict) -> tuple[bool, str]:
    notional = float(trade.get("notional", 0) or 0)
    risk = float(trade.get("risk", 0) or 0)
    if notional > PAPER_MAX_NOTIONAL_PER_TRADE_USDT:
        return False, f"notional {notional:.2f} > max {PAPER_MAX_NOTIONAL_PER_TRADE_USDT} USDT"
    if risk > PAPER_MAX_RISK_PER_TRADE_USDT:
        return False, f"risk {risk:.2f} > max {PAPER_MAX_RISK_PER_TRADE_USDT} USDT"
    return True, "valid"


def scan_and_clean_legacy() -> dict:
    """Scan portfolio and clean invalid legacy trades. Returns report."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)

    portfolio = _read_portfolio()
    promotion_tiers = _load_promotion_tiers()

    reasons = []
    invalidated = []
    valid_trades = []

    for trade in portfolio:
        if trade.get("status") != "PAPER_OPEN":
            valid_trades.append(trade)
            continue

        symbol = trade.get("symbol", "?")
        side = trade.get("side", "?")
        family = resolve_strategy_family(trade)

        # Check promotion gate
        allowed, tier, reason_code = _check_promotion_gate(family, promotion_tiers)
        if not allowed:
            trade["status"] = "LEGACY_INVALIDATED"
            trade["exit_reason"] = reason_code
            trade["closed_at"] = datetime.now(timezone.utc).isoformat()
            trade["strategy_family"] = family
            trade["promotion_tier"] = tier
            _append_to_ledger(trade)
            invalidated.append({
                "symbol": symbol,
                "side": side,
                "family": family,
                "tier": tier,
                "reason": reason_code,
            })
            reasons.append(f"legacy invalidated: {symbol} {side} family={family} tier={tier} reason={reason_code}")
            continue

        # Check risk caps
        risk_ok, risk_reason = _check_risk_caps(trade)
        if not risk_ok:
            trade["status"] = "LEGACY_INVALIDATED"
            trade["exit_reason"] = f"RISK_CAP_VIOLATION: {risk_reason}"
            trade["closed_at"] = datetime.now(timezone.utc).isoformat()
            trade["strategy_family"] = family
            trade["promotion_tier"] = tier
            _append_to_ledger(trade)
            invalidated.append({
                "symbol": symbol,
                "side": side,
                "family": family,
                "tier": tier,
                "reason": f"RISK_CAP_VIOLATION: {risk_reason}",
            })
            reasons.append(f"legacy invalidated: {symbol} {side} risk cap violation: {risk_reason}")
            continue

        # Check active trade count limit
        if len(valid_trades) >= PAPER_MAX_ACTIVE_TRADES:
            trade["status"] = "LEGACY_INVALIDATED"
            trade["exit_reason"] = "LEGACY_ACTIVE_COUNT_EXCEEDED"
            trade["closed_at"] = datetime.now(timezone.utc).isoformat()
            trade["strategy_family"] = family
            trade["promotion_tier"] = tier
            _append_to_ledger(trade)
            invalidated.append({
                "symbol": symbol,
                "side": side,
                "family": family,
                "tier": tier,
                "reason": "LEGACY_ACTIVE_COUNT_EXCEEDED",
            })
            reasons.append(f"legacy invalidated: {symbol} {side} active count exceeded")
            continue

        valid_trades.append(trade)

    # Write cleaned portfolio
    _write_portfolio(valid_trades)

    # Build report
    report = {
        "mode": "paper_legacy_cleanup",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "live_trading_enabled": False,
        "real_order": False,
        "portfolio_before": len(portfolio),
        "portfolio_after": len(valid_trades),
        "invalidated_count": len(invalidated),
        "invalidated_trades": invalidated,
        "promotion_tiers": promotion_tiers,
        "reasons": reasons,
        "final_decision": "NO_EDGE_FOUND" if not valid_trades else "PAPER_ONLY",
    }

    # Write JSON report
    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2)

    # Write text report
    _write_text_report(report, valid_trades)

    return report


def _write_text_report(report: dict, valid_trades: list[dict]):
    lines = [
        "=" * 60,
        "  PAPER LEGACY CLEANUP",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  Portfolio Before:  {report['portfolio_before']}",
        f"  Portfolio After:   {report['portfolio_after']}",
        f"  Invalidated:       {report['invalidated_count']}",
        "",
        "  Promotion Tiers:",
    ]
    for family, tier in report.get("promotion_tiers", {}).items():
        marker = " *" if tier in PAPER_ALLOWED_TIERS else ""
        lines.append(f"    {family}: {tier}{marker}")

    if report.get("invalidated_trades"):
        lines += ["", "  Invalidated Trades:"]
        for t in report["invalidated_trades"]:
            lines.append(f"    - {t['symbol']} {t['side']} family={t['family']} tier={t['tier']} reason={t['reason']}")

    if valid_trades:
        lines += ["", "  Valid Active Trades:"]
        for t in valid_trades:
            lines.append(f"    + {t.get('symbol','?')} {t.get('side','?')} family={t.get('strategy_family','?')} notional={t.get('notional',0):.2f} risk={t.get('risk',0):.2f}")

    lines += [
        "",
        f"  Final Decision: {report['final_decision']}",
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


def main():
    report = scan_and_clean_legacy()
    return 0


if __name__ == "__main__":
    sys.exit(main())
