"""Auto paper rotation engine.

Selects the next best fresh SHADOW_ELIGIBLE candidate when paper portfolio
has available slots (fewer than MAX_PAPER_TRADES active trades). Does NOT
enable live trading. Does NOT place real orders.

This module NEVER places real orders, NEVER sets BINGX_EXECUTION_MODE=live_micro,
and NEVER sets LIVE_TRADING_ACK.
"""

import json, os, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
TXT_PATH = os.path.join(RESULTS_DIR, "paper_rotation_report.txt")
JSON_PATH = os.path.join(RESULTS_DIR, "paper_rotation_report.json")
LEDGER_PATH = os.path.join(STATE_DIR, "paper_rotation_events.jsonl")
PORTFOLIO_PATH = os.path.join(STATE_DIR, "paper_portfolio.json")
PAPER_LEDGER = os.path.join(STATE_DIR, "paper_trades.jsonl")

# Paper portfolio risk/capital config — MUST match paper_execution_ledger exactly
PAPER_CAPITAL_USDT = 400
PAPER_MAX_RISK_PER_TRADE_USDT = 2       # 0.5% of capital
PAPER_MAX_LEVERAGE = 2
PAPER_MAX_PORTFOLIO_NOTIONAL_USDT = 200  # 50% of capital
PAPER_MAX_ACTIVE_TRADES = 3
PAPER_MAX_NOTIONAL_PER_TRADE_USDT = 100  # 25% of capital
MAX_PAPER_TRADES = PAPER_MAX_ACTIVE_TRADES

# Thesis type to strategy family mapping (mirrored from paper_execution_ledger)
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
    "BB_BOUNCE": "bb_bounce_v1",
}

PAPER_ALLOWED_TIERS = {"PAPER_CANDIDATE", "PAPER_PRIORITY"}

# Pre-validated BB family always allowed (extensively backtested)
BB_RSI_TRUSTED_FAMILIES = {"bb_bounce_v1"}


def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _load_promotion_tiers() -> dict[str, str]:
    """Load strategy family promotion tiers from arbiter report.
    Returns dict of family_name -> tier.
    """
    report = _read_json(os.path.join(RESULTS_DIR, "strategy_promotion_arbiter_report.json"))
    families = report.get("families", {})
    return {name: info.get("tier", "UNKNOWN") for name, info in families.items()}


def resolve_strategy_family(candidate: dict) -> str:
    """Resolve strategy family from candidate's thesis_type, pattern, or direct family field."""
    family = candidate.get("strategy_family", "")
    if family and family != "unknown":
        return family
    thesis_type = candidate.get("thesis_type", "")
    family = THESIS_TYPE_TO_FAMILY.get(thesis_type, "")
    if family:
        return family
    pattern = candidate.get("pattern_name", "")
    family = THESIS_TYPE_TO_FAMILY.get(pattern, "")
    if family:
        return family
    return "unknown"


def _check_promotion_gate(family: str, promotion_tiers: dict[str, str]) -> tuple[bool, str, str]:
    """Check if a strategy family is allowed for paper trading.
    Returns (allowed, tier, reason_code).
    """
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


def _read_ledger(path: str) -> list[dict]:
    try:
        with open(path) as f:
            return [json.loads(l) for l in f if l.strip()]
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _candidate_score(c: dict) -> float:
    return float(c.get("thesis_score", 0) or c.get("raw_anomaly_score", 0))


def _is_eligible(c: dict) -> bool:
    ts = c.get("trigger_status", "")
    if ts != "TRIGGER_CONFIRMED":
        return False
    family = c.get("strategy_family", "")
    rr = float(c.get("rr", 0) or 0)
    if family in BB_RSI_TRUSTED_FAMILIES:
        if rr < 3.0:
            return False
        return True
    if rr < 4:
        return False
    return True


def _eligibility_status(c: dict) -> str:
    ts = c.get("trigger_status", "")
    family = c.get("strategy_family", "")
    min_rr = 3.0 if family in BB_RSI_TRUSTED_FAMILIES else 4.0
    if ts == "TRIGGER_CONFIRMED":
        if float(c.get("thesis_score", 0) or 0) >= 75 and float(c.get("rr", 0) or 0) >= min_rr:
            return "SHADOW_ELIGIBLE"
        return "REVIEW_CANDIDATE"
    return ts


def _last_closed_trade_same_symbol_direction(symbol: str, direction: str) -> dict | None:
    trades = _read_ledger(PAPER_LEDGER)
    closed = [t for t in trades if t.get("status") == "PAPER_CLOSED"]
    if not closed:
        return None
    for t in reversed(closed):
        if t.get("symbol", "") == symbol and t.get("side", "").lower() == direction.lower():
            return t
    return None


def _passes_capital_gate(c: dict, portfolio: list[dict]) -> tuple[bool, str]:
    """Check if candidate fits within risk and notional caps."""
    entry = float(c.get("entry", 0) or 0)
    stop = float(c.get("stop", 0) or 0)
    if entry <= 0 or stop <= 0:
        return False, "missing entry or stop"

    risk_per_unit = abs(entry - stop)
    if risk_per_unit <= 0:
        return False, "stop equals entry (zero risk distance)"

    qty_from_risk = PAPER_MAX_RISK_PER_TRADE_USDT / risk_per_unit
    qty_from_notional = PAPER_MAX_NOTIONAL_PER_TRADE_USDT / entry
    qty = min(qty_from_risk, qty_from_notional)
    estimated_notional = entry * qty
    estimated_risk = risk_per_unit * qty

    active_trades = [t for t in portfolio if t.get("status") == "PAPER_OPEN"]
    if len(active_trades) >= PAPER_MAX_ACTIVE_TRADES:
        return False, f"max {PAPER_MAX_ACTIVE_TRADES} active trades reached"

    total_open_notional = sum(float(t.get("notional", 0) or 0) for t in active_trades)
    if total_open_notional + estimated_notional > PAPER_MAX_PORTFOLIO_NOTIONAL_USDT:
        return False, f"portfolio notional {total_open_notional + estimated_notional:.2f} > max {PAPER_MAX_PORTFOLIO_NOTIONAL_USDT} USDT"

    return True, "passes capital gates"


def run_paper_rotation_engine() -> dict:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)

    portfolio = _read_json(PORTFOLIO_PATH)
    if not isinstance(portfolio, list):
        portfolio = []
    trigger_watcher = _read_json(RESULTS_DIR + "/trigger_watcher_report.json")

    reasons = []
    active_trades = [t for t in portfolio if t.get("status") == "PAPER_OPEN"]
    trade_lock_on = len(active_trades) >= MAX_PAPER_TRADES
    active_symbols = set(t.get("symbol", "") for t in active_trades)
    active_entries = [(t.get("symbol", ""), t.get("side", "")) for t in active_trades]
    available_slots = max(0, MAX_PAPER_TRADES - len(active_trades))

    # Load promotion tiers for gate checks
    promotion_tiers = _load_promotion_tiers()

    # Load BB candidates
    bb_candidates_path = os.path.join(RESULTS_DIR, "bb_candidates.json")
    bb_data = _read_json(bb_candidates_path)
    bb_candidates: list[dict] = bb_data.get("candidates", []) if bb_data else []

    all_candidates: list[dict] = (trigger_watcher.get("candidates", []) if trigger_watcher else []) + bb_candidates

    eligible = [c for c in all_candidates if _is_eligible(c)]
    fresh_eligible = [c for c in eligible if c.get("symbol", "") not in active_symbols]

    # Promotion gate filter
    promotion_filtered = []
    for c in fresh_eligible:
        family = resolve_strategy_family(c)
        # BB/RSI trusted families bypass promotion gate
        if family in BB_RSI_TRUSTED_FAMILIES:
            allowed, tier, reason_code = True, "PAPER_PRIORITY", ""
            c["strategy_family"] = family
            c["promotion_tier"] = tier
            promotion_filtered.append(c)
            continue
        allowed, tier, reason_code = _check_promotion_gate(family, promotion_tiers)
        if allowed:
            c["strategy_family"] = family
            c["promotion_tier"] = tier
            promotion_filtered.append(c)
        else:
            reasons.append(f"promotion gate blocked: {c.get('symbol','')} {c.get('direction','')} family={family} tier={tier} reason={reason_code}")

    capital_filtered = []
    for c in promotion_filtered:
        ok, reason = _passes_capital_gate(c, portfolio)
        if ok:
            capital_filtered.append(c)
        else:
            reasons.append(f"capital gate blocked: {c.get('symbol','')} {c.get('direction','')} — {reason}")

    filtered_eligible = []
    for c in capital_filtered:
        last_closed = _last_closed_trade_same_symbol_direction(
            c.get("symbol", ""), c.get("direction", "")
        )
        if last_closed:
            cand_ts = c.get("timestamp") or c.get("trigger_confirmed_at") or ""
            closed_ts = last_closed.get("closed_at", "")
            if cand_ts and closed_ts and cand_ts > closed_ts:
                filtered_eligible.append(c)
            else:
                reasons.append(
                    f"re-entry blocked: {c['symbol']} {c['direction']} same as last closed trade"
                )
        else:
            filtered_eligible.append(c)

    if not filtered_eligible:
        filtered_eligible = fresh_eligible

    def _sort_key(c: dict) -> tuple:
        is_se = _eligibility_status(c) == "SHADOW_ELIGIBLE"
        return (is_se, _candidate_score(c), float(c.get("rr", 0) or 0))

    filtered_eligible.sort(key=_sort_key, reverse=True)
    best_candidate = filtered_eligible[0] if filtered_eligible else None

    if trade_lock_on:
        next_action = "PORTFOLIO_FULL"
        syms = ', '.join(t.get('symbol','?') for t in active_trades)
        reasons.append(
            f"{len(active_trades)} active paper trade(s): {syms}; portfolio full ({MAX_PAPER_TRADES}/{MAX_PAPER_TRADES})"
        )
    elif best_candidate:
        best_rr = float(best_candidate.get("rr", 0) or 0)
        best_family = best_candidate.get("strategy_family", "")
        min_rr = 3.0 if best_family in BB_RSI_TRUSTED_FAMILIES else 4.0
        if best_rr >= min_rr:
            next_action = "ROTATE_TO_NEW_PAPER_TRADE"
            reasons.append(
                f"selected {best_candidate['symbol']} {best_candidate['direction']} "
                f"RR:{best_rr} Score:{_candidate_score(best_candidate)} for paper rotation"
            )
        else:
            next_action = "NO_VALID_CANDIDATE"
            reasons.append(
                f"best candidate {best_candidate['symbol']} has RR={best_rr} < 4"
            )
    else:
        next_action = "NO_VALID_CANDIDATE"
        reasons.append("no eligible candidate found for rotation")

    risk_config = {
        "capital_usdt": PAPER_CAPITAL_USDT,
        "max_risk_per_trade_usdt": PAPER_MAX_RISK_PER_TRADE_USDT,
        "max_notional_per_trade_usdt": PAPER_MAX_NOTIONAL_PER_TRADE_USDT,
        "max_leverage": PAPER_MAX_LEVERAGE,
        "max_portfolio_notional_usdt": PAPER_MAX_PORTFOLIO_NOTIONAL_USDT,
        "max_active_trades": PAPER_MAX_ACTIVE_TRADES,
    }

    report = {
        "mode": "paper_rotation_engine",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "real_order": False,
        "next_action": next_action,
        "active_trade_lock_on": trade_lock_on,
        "active_trades_count": len(active_trades),
        "available_slots": available_slots,
        "max_paper_trades": MAX_PAPER_TRADES,
        "risk_config": risk_config,
        "active_trades": active_trades,
        "rotation_candidate": {
            "symbol": best_candidate.get("symbol", ""),
            "timeframe": best_candidate.get("timeframe", ""),
            "direction": best_candidate.get("direction", ""),
            "rr": float(best_candidate.get("rr", 0) or 0),
            "thesis_score": _candidate_score(best_candidate),
            "trigger_status": best_candidate.get("trigger_status", ""),
            "eligibility_status": _eligibility_status(best_candidate),
            "entry": float(best_candidate.get("entry", 0) or 0),
            "stop": float(best_candidate.get("stop", 0) or 0),
            "target": float(best_candidate.get("target", 0) or 0),
            "bucket": best_candidate.get("bucket", ""),
            "reason": best_candidate.get("reason", ""),
            "strategy_family": best_candidate.get("strategy_family", "unknown"),
            "promotion_tier": best_candidate.get("promotion_tier", "UNKNOWN"),
        } if best_candidate else None,
        "candidate_discovery": {
            "total_candidates": len(all_candidates),
            "trigger_watcher_candidates": len(trigger_watcher.get("candidates", []) if trigger_watcher else []),
            "bb_candidates": len(bb_candidates),
            "eligible_candidates": len(eligible),
            "fresh_eligible": len(fresh_eligible),
            "promotion_filtered": len(promotion_filtered),
            "re_entry_blocked": max(0, len(promotion_filtered) - len(filtered_eligible)),
        },
        "promotion_gate": {
            "families": promotion_tiers,
            "allowed_tiers": list(PAPER_ALLOWED_TIERS),
        },
        "reasons": reasons,
    }

    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2)

    _write_text_report(report)
    _append_to_ledger(report)
    return report


def _write_text_report(report: dict):
    promo = report.get("promotion_gate", {})
    lines = [
        "=" * 60,
        "  PAPER ROTATION ENGINE",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  Next Action:       {report['next_action']}",
        f"  Trade Lock:        {'ON' if report['active_trade_lock_on'] else 'OFF'}",
        f"  Portfolio:         {report['active_trades_count']} / {report['max_paper_trades']} active",
        f"  Available Slots:   {report['available_slots']}",
        "",
        "  Promotion Gate:",
        f"    Allowed Tiers:   {', '.join(promo.get('allowed_tiers', []))}",
    ]
    for family, tier in promo.get("families", {}).items():
        marker = " *" if tier in PAPER_ALLOWED_TIERS else ""
        lines.append(f"    {family}: {tier}{marker}")

    lines += [
        "",
        "  Paper Risk Config (Risk vs Notional Model):",
        f"    Capital:                {report['risk_config']['capital_usdt']} USDT",
        f"    Max Risk / Trade:       {report['risk_config']['max_risk_per_trade_usdt']} USDT",
        f"    Max Notional / Trade:   {PAPER_MAX_NOTIONAL_PER_TRADE_USDT} USDT (25% capital)",
        f"    Max Portfolio Notional: {report['risk_config']['max_portfolio_notional_usdt']} USDT (50% capital)",
        f"    Max Leverage:           {report['risk_config']['max_leverage']}x",
        f"    Max Active Trades:      {report['risk_config']['max_active_trades']}",
        "",
    ]

    at = report.get("active_trades")
    if at:
        lines += [
            f"  Active Paper Trades: {len(at)}",
        ]
        for i, t in enumerate(at, 1):
            lines += [
                f"    [{i}] {t.get('symbol','?')} {t.get('side','?')} "
                f"RR:1:{t.get('rr',0)} Status:{t.get('status','?')}",
            ]
    else:
        lines += ["  Active Paper Trades: 0"]

    cd = report.get("candidate_discovery", {})
    lines += [
        "",
        "  Candidate Discovery:",
        f"    Total:              {cd.get('total_candidates', 0)}",
        f"    Eligible (RR>=4):   {cd.get('eligible_candidates', 0)}",
        f"    Fresh (ex. active): {cd.get('fresh_eligible', 0)}",
        f"    Promotion filtered: {cd.get('promotion_filtered', 0)}",
        f"    Re-entry blocked:   {cd.get('re_entry_blocked', 0)}",
        "",
    ]

    rc = report.get("rotation_candidate")
    if rc:
        lines += [
            "  Rotation Candidate:",
            f"    Symbol:   {rc.get('symbol','?')} {rc.get('direction','?')} {rc.get('timeframe','?')}",
            f"    RR:       1:{rc.get('rr','?')}",
            f"    Score:    {rc.get('thesis_score','?')}",
            f"    Status:   {rc.get('eligibility_status','?')} ({rc.get('trigger_status','?')})",
            f"    Entry:    {rc.get('entry','?')}  Stop: {rc.get('stop','?')}  Target: {rc.get('target','?')}",
            f"    Family:   {rc.get('strategy_family','?')}",
            f"    Tier:     {rc.get('promotion_tier','?')}",
            f"    Reason:   {rc.get('reason','')}",
        ]
    else:
        lines += ["  Rotation Candidate: NONE"]

    lines += [
        "",
        "  Rotation Allowed: " + (
            "YES" if report['next_action'] == "ROTATE_TO_NEW_PAPER_TRADE" else
            "NO (portfolio full)" if report['next_action'] in ("PORTFOLIO_FULL", "ACTIVE_TRADE_MONITORING") else
            "NO (no candidate)"
        ),
        "",
    ]
    for r in report["reasons"]:
        lines.append(f"    - {r}")
    lines += [
        "",
        f"  WARNING: Paper rotation only. No real orders placed. Max {PAPER_MAX_ACTIVE_TRADES} paper trades.",
        "",
        "=" * 60,
    ]

    with open(TXT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n[JSON] {JSON_PATH}")
    print(f"[TXT]  {TXT_PATH}")
    print(f"[LEDGER] {LEDGER_PATH}")


def _append_to_ledger(report: dict):
    entry = {
        "timestamp": report["timestamp"],
        "next_action": report["next_action"],
        "active_trade_lock_on": report["active_trade_lock_on"],
        "rotation_candidate_symbol": (
            report.get("rotation_candidate", {}).get("symbol")
        ) if report.get("rotation_candidate") else None,
        "candidate_discovery": report.get("candidate_discovery", {}),
    }
    with open(LEDGER_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def main():
    report = run_paper_rotation_engine()
    return 0


if __name__ == "__main__":
    sys.exit(main())
