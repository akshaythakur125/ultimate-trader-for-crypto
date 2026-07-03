"""
Phase 79 — Breadwinner Watchtower
Produces top 3 actionable candidates from all edge sources.
Rejects unsafe/unpromoted trades. Scores on quality, RR, liquidity, etc.
"""

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from paper_execution_ledger import _read_portfolio
from derivatives_data_collector import get_oi_funding_summary

RUNTIME_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
DEPLOY_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
CANDIDATES_FILE = os.path.join(RUNTIME_DIR, "derivatives_edge_candidates.jsonl")
TICKER_CACHE = os.path.join(RUNTIME_DIR, "swap_tickers_cache.json")
PROMOTION_REPORT = os.path.join(DEPLOY_DIR, "strategy_promotion_arbiter_report.json")

# Report files
REPORT_JSON = os.path.join(DEPLOY_DIR, "breadwinner_watchtower_report.json")
REPORT_TXT = os.path.join(DEPLOY_DIR, "breadwinner_watchtower_report.txt")

# Safety thresholds
MIN_RR = 2.5
MAX_NOTIONAL = 100.0
MAX_RISK = 2.0
MAX_CANDIDATES = 3
MIN_LIQUIDITY_USD = 100000.0  # 24h volume minimum

# Banning rules
BANNED_FAMILIES = {"REJECTED", "OBSERVE_ONLY"}
PAPER_FAMILIES = {"PAPER_CANDIDATE", "PAPER_PRIORITY"}
STOP_TARGET_FIELDS = {"entry", "stop", "target"}


def load_promotion_tiers():
    """Load promotion tiers from the arbiter report JSON."""
    if not os.path.exists(PROMOTION_REPORT):
        return {}
    try:
        with open(PROMOTION_REPORT, "r", encoding="utf-8") as f:
            data = json.load(f)
        tiers = {}
        families = data.get("families", {})
        for name, info in families.items():
            tiers[name] = info.get("tier", "unknown")
        return tiers
    except Exception:
        return {}


def _load_candidates():
    """Load derivatives edge candidates from JSONL."""
    if not os.path.exists(CANDIDATES_FILE):
        return []
    candidates = []
    with open(CANDIDATES_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                candidates.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return candidates


def _load_ticker(symbol):
    """Load cached ticker for a symbol."""
    if not os.path.exists(TICKER_CACHE):
        return None
    try:
        with open(TICKER_CACHE, "r", encoding="utf-8") as f:
            cache = json.load(f)
        for t in cache:
            if t.get("symbol") == symbol:
                return t
    except Exception:
        pass
    return None


def _score_candidate(candidate, promotion_tiers, portfolio, derivatives_obs):
    """Score a candidate. Returns (score, reasons) or None if rejected."""
    symbol = candidate.get("symbol", "")
    direction = candidate.get("direction", "")
    setup_type = candidate.get("setup_type", "")
    rr = candidate.get("rr", 0)
    entry = candidate.get("entry", 0)
    stop = candidate.get("stop", 0)
    target = candidate.get("target", 0)

    # Determine family from setup_type
    family_map = {
        "LIQUIDATION_PROXY_SWEEP": "liquidity_sweep",
        "MOMENTUM_CONTINUATION_SQU": "trend_pullback",
        "OI_BUILD_COMPRESSION": "compression_breakout",
        "FUNDING_TRAP_REVERSAL": "mean_reversion",
        "OI_PRICE_DIVERGENCE": "mean_reversion",
    }
    family = family_map.get(setup_type, "unknown")
    tier = promotion_tiers.get(family, "unknown")

    reasons = []
    score = 0.0

    # Hard rejections
    if tier in BANNED_FAMILIES:
        return None, [f"REJECTED: family={family} tier={tier}"]
    if tier == "unknown":
        return None, [f"REJECTED: unknown family={family}"]
    if rr < MIN_RR:
        return None, [f"REJECTED: RR={rr:.2f} < {MIN_RR}"]
    if entry <= 0 or stop <= 0 or target <= 0:
        return None, [f"REJECTED: missing stop/target"]
    if entry == stop or entry == target:
        return None, [f"REJECTED: entry=stop or entry=target"]

    # Check notional cap
    notional = abs(entry * 1.0)  # approximate notional
    if notional > MAX_NOTIONAL:
        return None, [f"REJECTED: notional {notional:.1f} > {MAX_NOTIONAL}"]

    # Check risk cap
    risk_per_unit = abs(entry - stop)
    if risk_per_unit > MAX_RISK:
        return None, [f"REJECTED: risk {risk_per_unit:.2f} > {MAX_RISK}"]

    # Check duplicate active trade
    for trade in portfolio.get("trades", []):
        if trade.get("symbol") == symbol and trade.get("side") == direction:
            return None, [f"REJECTED: duplicate active trade {symbol} {direction}"]

    # Score components
    # Setup quality (0-30 points)
    if setup_type == "LIQUIDATION_PROXY_SWEEP":
        score += 30
        reasons.append("Liquidation sweep (best setup)")
    elif setup_type == "MOMENTUM_CONTINUATION_SQU":
        score += 25
        reasons.append("Momentum continuation")
    elif setup_type == "OI_BUILD_COMPRESSION":
        score += 20
        reasons.append("OI compression")
    elif setup_type == "FUNDING_TRAP_REVERSAL":
        score += 15
        reasons.append("Funding trap")
    elif setup_type == "OI_PRICE_DIVERGENCE":
        score += 15
        reasons.append("OI divergence")
    else:
        score += 10
        reasons.append(f"Setup: {setup_type}")

    # RR score (0-25 points)
    rr_score = min(25, (rr - MIN_RR) * 5)
    score += rr_score
    reasons.append(f"RR={rr:.2f} (+{rr_score:.1f})")

    # Liquidity score (0-20 points)
    vol_24h = candidate.get("volume_24h", 0) or 0
    if vol_24h >= MIN_LIQUIDITY_USD:
        liq_score = min(20, vol_24h / 50000)
        score += liq_score
        reasons.append(f"Liquidity OK (+{liq_score:.1f})")
    else:
        score += 5  # minimal liquidity
        reasons.append("Low liquidity (+5)")

    # Volume expansion (0-10 points)
    vol_exp = candidate.get("volume_expansion", 0) or 0
    if vol_exp > 1.5:
        score += 10
        reasons.append("Volume expansion (+10)")
    elif vol_exp > 1.2:
        score += 5
        reasons.append("Volume mild expansion (+5)")

    # Funding trap score (0-10 points)
    funding_score = candidate.get("funding_trap_score", 0) or 0
    if funding_score > 0.5:
        score += 10
        reasons.append("High funding trap (+10)")
    elif funding_score > 0.3:
        score += 5
        reasons.append("Moderate funding trap (+5)")

    # OI compression score (0-10 points)
    oi_score = candidate.get("oi_compression_score", 0) or 0
    if oi_score > 0.7:
        score += 10
        reasons.append("Strong OI compression (+10)")
    elif oi_score > 0.4:
        score += 5
        reasons.append("Moderate OI compression (+5)")

    # Family promotion bonus (0-15 points)
    if tier == "PAPER_PRIORITY":
        score += 15
        reasons.append("PAPER_PRIORITY family (+15)")
    elif tier == "PAPER_CANDIDATE":
        score += 10
        reasons.append("PAPER_CANDIDATE family (+10)")

    # Penalty for already active
    for trade in portfolio.get("trades", []):
        if trade.get("symbol") == symbol:
            score -= 20
            reasons.append("Already active penalty (-20)")
            break

    # Derivatives observation bonus
    oi_fund = get_oi_funding_summary(symbol)
    if oi_fund.get("oi_available") and oi_fund.get("funding_available"):
        score += 5
        reasons.append("Real derivatives data (+5)")
    elif oi_fund.get("oi_available") or oi_fund.get("funding_available"):
        score += 2
        reasons.append("Partial derivatives data (+2)")

    return score, reasons


def run_breadwinner_watchtower():
    """Run the watchtower and produce top candidates.
    Returns dict with verdict, candidates, stats.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Load data
    candidates = _load_candidates()
    portfolio_trades = _read_portfolio()
    promotion_tiers = load_promotion_tiers()
    portfolio = {"trades": [t for t in portfolio_trades if t.get("status") == "PAPER_OPEN"]}
    active_trades = portfolio.get("trades", [])

    # Score all candidates
    scored = []
    for c in candidates:
        score, reasons = _score_candidate(c, promotion_tiers, portfolio, {})
        if score is not None:
            scored.append({
                "score": score,
                "reasons": reasons,
                **c,
            })

    # Sort by score descending
    scored.sort(key=lambda x: x["score"], reverse=True)

    # Take top N
    top_candidates = scored[:MAX_CANDIDATES]

    # Determine final mode
    final_mode = "KEEP_WATCHING"
    if top_candidates and top_candidates[0]["score"] >= 70:
        final_mode = "PAPER_SIGNAL_READY"
    elif top_candidates and top_candidates[0]["score"] >= 50:
        final_mode = "PAPER_EDGE_DEVELOPING"

    # Check if live review criteria met
    # (Would need outcome tracker data - check if exists)
    outcome_file = os.path.join(RUNTIME_DIR, "paper_signal_outcomes.jsonl")
    live_review_ready = False
    if os.path.exists(outcome_file):
        outcomes = []
        with open(outcome_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        outcomes.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        closed = [o for o in outcomes if o.get("status") in ("TARGET_HIT", "STOP_HIT", "EXPIRED")]
        if len(closed) >= 30:
            wins = sum(1 for o in closed if o.get("status") == "TARGET_HIT")
            win_rate = wins / len(closed) if closed else 0
            avg_r = sum(o.get("r_multiple", 0) for o in closed) / len(closed) if closed else 0
            pf = sum(o.get("r_multiple", 0) for o in closed if o.get("r_multiple", 0) > 0) / \
                 abs(sum(o.get("r_multiple", 0) for o in closed if o.get("r_multiple", 0) < 0)) \
                 if any(o.get("r_multiple", 0) < 0 for o in closed) else 999
            max_consec = _max_consecutive_losses(closed)
            if avg_r > 0 and pf > 1.15 and max_consec <= 8:
                live_review_ready = True
                final_mode = "LIVE_REVIEW_READY"

    # Build report
    report = {
        "timestamp": now,
        "final_mode": final_mode,
        "live_review_ready": live_review_ready,
        "active_trades": len(active_trades),
        "total_candidates_scored": len(scored),
        "candidates_rejected": len(candidates) - len(scored),
        "top_candidates": [],
        "safety": {
            "live_trading": "NO",
            "real_orders": "NO",
            "execution_mode": "read_only",
        },
    }

    for c in top_candidates:
        report["top_candidates"].append({
            "symbol": c.get("symbol"),
            "direction": c.get("direction"),
            "entry": c.get("entry"),
            "stop": c.get("stop"),
            "target": c.get("target"),
            "rr": c.get("rr"),
            "risk": abs(c.get("entry", 0) - c.get("stop", 0)),
            "setup_type": c.get("setup_type"),
            "score": round(c.get("score", 0), 2),
            "reasons": c.get("reasons", []),
        })

    # Add stats from outcome tracker if available
    report["stats"] = _get_outcome_stats()

    # Write reports
    os.makedirs(DEPLOY_DIR, exist_ok=True)
    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    _write_txt_report(report)

    return report


def _max_consecutive_losses(closed):
    """Calculate max consecutive losses."""
    max_consec = 0
    current = 0
    for o in closed:
        if o.get("status") == "STOP_HIT" or o.get("r_multiple", 0) < 0:
            current += 1
            max_consec = max(max_consec, current)
        else:
            current = 0
    return max_consec


def _get_outcome_stats():
    """Get stats from paper signal outcomes."""
    outcome_file = os.path.join(RUNTIME_DIR, "paper_signal_outcomes.jsonl")
    if not os.path.exists(outcome_file):
        return {
            "closed_signals": 0,
            "win_rate": 0,
            "avg_r": 0,
            "profit_factor": 0,
            "max_consecutive_losses": 0,
            "best_setup_type": "N/A",
            "worst_setup_type": "N/A",
        }
    outcomes = []
    with open(outcome_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    outcomes.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    closed = [o for o in outcomes if o.get("status") in ("TARGET_HIT", "STOP_HIT", "EXPIRED")]
    if not closed:
        return {
            "closed_signals": 0,
            "win_rate": 0,
            "avg_r": 0,
            "profit_factor": 0,
            "max_consecutive_losses": 0,
            "best_setup_type": "N/A",
            "worst_setup_type": "N/A",
        }

    wins = sum(1 for o in closed if o.get("status") == "TARGET_HIT")
    win_rate = wins / len(closed) if closed else 0
    avg_r = sum(o.get("r_multiple", 0) for o in closed) / len(closed) if closed else 0
    gains = sum(o.get("r_multiple", 0) for o in closed if o.get("r_multiple", 0) > 0)
    losses = abs(sum(o.get("r_multiple", 0) for o in closed if o.get("r_multiple", 0) < 0))
    pf = gains / losses if losses > 0 else 999
    max_consec = _max_consecutive_losses(closed)

    # Best/worst setup type
    setup_r = {}
    for o in closed:
        st = o.get("setup_type", "unknown")
        if st not in setup_r:
            setup_r[st] = []
        setup_r[st].append(o.get("r_multiple", 0))
    best = max(setup_r.items(), key=lambda x: sum(x[1]) / len(x[1]) if x[1] else 0) if setup_r else ("N/A", [])
    worst = min(setup_r.items(), key=lambda x: sum(x[1]) / len(x[1]) if x[1] else 0) if setup_r else ("N/A", [])

    return {
        "closed_signals": len(closed),
        "win_rate": round(win_rate, 4),
        "avg_r": round(avg_r, 4),
        "profit_factor": round(pf, 4),
        "max_consecutive_losses": max_consec,
        "best_setup_type": best[0] if isinstance(best, tuple) else "N/A",
        "worst_setup_type": worst[0] if isinstance(worst, tuple) else "N/A",
    }


def _write_txt_report(report):
    """Write human-readable TXT report."""
    lines = []
    lines.append("=" * 56)
    lines.append("BREADWINNER WATCHTOWER REPORT")
    lines.append(f"  {report['timestamp']}")
    lines.append("=" * 56)
    lines.append("")
    lines.append(f"  FINAL MODE:       {report['final_mode']}")
    lines.append(f"  Live Review Ready: {report['live_review_ready']}")
    lines.append(f"  Active Trades:     {report['active_trades']}")
    lines.append(f"  Candidates Scored: {report['total_candidates_scored']}")
    lines.append(f"  Candidates Rejected: {report['candidates_rejected']}")
    lines.append("")

    top = report.get("top_candidates", [])
    if top:
        lines.append("  TOP CANDIDATES:")
        for i, c in enumerate(top, 1):
            lines.append(f"")
            lines.append(f"  {i}. {c['symbol']} {c['direction']} ({c['setup_type']})")
            lines.append(f"     Score: {c['score']}")
            lines.append(f"     Entry:  {c['entry']}")
            lines.append(f"     Stop:   {c['stop']}")
            lines.append(f"     Target: {c['target']}")
            lines.append(f"     RR:     {c['rr']:.2f}")
            lines.append(f"     Risk:   {c['risk']:.4f} USDT")
            lines.append(f"     Reasons: {'; '.join(c['reasons'])}")
    else:
        lines.append("  TOP CANDIDATES: NONE")
    lines.append("")

    stats = report.get("stats", {})
    lines.append("  OUTCOME TRACKER STATS:")
    lines.append(f"    Closed Signals:      {stats.get('closed_signals', 0)}")
    lines.append(f"    Win Rate:            {stats.get('win_rate', 0):.1%}")
    lines.append(f"    Average R:           {stats.get('avg_r', 0):.4f}")
    lines.append(f"    Profit Factor:       {stats.get('profit_factor', 0):.2f}")
    lines.append(f"    Max Consec Losses:   {stats.get('max_consecutive_losses', 0)}")
    lines.append(f"    Best Setup:          {stats.get('best_setup_type', 'N/A')}")
    lines.append(f"    Worst Setup:         {stats.get('worst_setup_type', 'N/A')}")
    lines.append("")

    safety = report.get("safety", {})
    lines.append("  SAFETY:")
    lines.append(f"    Live Trading:   {safety.get('live_trading', 'NO')}")
    lines.append(f"    Real Orders:    {safety.get('real_orders', 'NO')}")
    lines.append(f"    Execution Mode: {safety.get('execution_mode', 'read_only')}")
    lines.append("")
    lines.append("  WARNING: No real orders placed. Paper/backtest only.")
    lines.append("")

    with open(REPORT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    report = run_breadwinner_watchtower()
    print(f"Watchtower mode: {report['final_mode']}")
    print(f"Candidates scored: {report['total_candidates_scored']}")
    print(f"Top candidates: {len(report.get('top_candidates', []))}")
    for c in report.get("top_candidates", []):
        print(f"  {c['symbol']} {c['direction']} score={c['score']}")
