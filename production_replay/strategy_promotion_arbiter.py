"""Strategy promotion arbiter — classifies strategy families into promotion tiers.

Separates raw best OOS family from statistically eligible families and
paper-test eligible families. No live trading ever enabled in this module.

Offline research only — never enables live trading.
"""

import json, os, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.historical_cache_resolver import find_project_root

PROJECT_ROOT = find_project_root()
RESULTS_DIR = os.path.join(PROJECT_ROOT, "deploy_results")
STATE_DIR = os.path.join(PROJECT_ROOT, "runtime_state")

TOURNAMENT_PATH = os.path.join(RESULTS_DIR, "strategy_family_tournament_report.json")
EDGE_MINER_PATH = os.path.join(RESULTS_DIR, "historical_edge_miner_report.json")
JSON_PATH = os.path.join(RESULTS_DIR, "strategy_promotion_arbiter_report.json")
TXT_PATH = os.path.join(RESULTS_DIR, "strategy_promotion_arbiter_report.txt")
DECISIONS_PATH = os.path.join(STATE_DIR, "strategy_promotion_decisions.jsonl")

TIER_REJECTED = "REJECTED"
TIER_OBSERVE = "OBSERVE_ONLY"
TIER_PAPER_CANDIDATE = "PAPER_CANDIDATE"
TIER_PAPER_PRIORITY = "PAPER_PRIORITY"
TIER_LIVE_BLOCKED = "LIVE_BLOCKED"

MIN_TRADES_OBSERVE = 300
MIN_OOS_OBSERVE = 100
MIN_SYMBOLS_OBSERVE = 3

MIN_OOS_AVG_R_CANDIDATE = 0.0
MIN_OOS_WIN_RATE_CANDIDATE = 30.0
MIN_PROFIT_FACTOR_CANDIDATE = 1.0
MIN_SYMBOLS_CANDIDATE = 50
MAX_DD_CANDIDATE = 60.0
MAX_CONSEC_CANDIDATE = 40

MIN_OOS_AVG_R_PRIORITY = 0.10
MIN_OOS_TRADES_PRIORITY = 200


def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _classify_family(fam: dict) -> dict:
    """Classify a single family into promotion tier with reasons."""
    tier = TIER_REJECTED
    reasons = []

    total = fam.get("total_trades", 0)
    oos_trades = fam.get("oos_trades", 0)
    is_avg_r = fam.get("is_avg_r", 0)
    oos_avg_r = fam.get("oos_avg_r", 0)
    oos_win_rate = fam.get("oos_win_rate", 0)
    profit_factor = fam.get("profit_factor", 0)
    max_dd = fam.get("max_dd", 0)
    max_consec = fam.get("max_consec_losses", 0)
    unique_symbols = fam.get("unique_symbols", 0)
    leakage = fam.get("leakage_guard", "UNKNOWN")

    if leakage != "PASS":
        reasons.append(f"leakage guard {leakage}")
        return tier, reasons

    if total < MIN_TRADES_OBSERVE:
        reasons.append(f"total trades {total} < {MIN_TRADES_OBSERVE}")
        return tier, reasons

    if oos_trades < MIN_OOS_OBSERVE:
        reasons.append(f"OOS trades {oos_trades} < {MIN_OOS_OBSERVE}")
        return tier, reasons

    if unique_symbols < MIN_SYMBOLS_OBSERVE:
        reasons.append(f"unique symbols {unique_symbols} < {MIN_SYMBOLS_OBSERVE}")
        return tier, reasons

    tier = TIER_OBSERVE

    if is_avg_r <= 0:
        reasons.append(f"IS avg R {is_avg_r} <= 0")
        return tier, reasons

    if oos_avg_r <= MIN_OOS_AVG_R_CANDIDATE:
        reasons.append(f"OOS avg R {oos_avg_r} <= {MIN_OOS_AVG_R_CANDIDATE}")
        return tier, reasons

    if oos_win_rate < MIN_OOS_WIN_RATE_CANDIDATE:
        reasons.append(f"OOS win rate {oos_win_rate}% < {MIN_OOS_WIN_RATE_CANDIDATE}%")
        return tier, reasons

    if profit_factor < MIN_PROFIT_FACTOR_CANDIDATE:
        reasons.append(f"profit factor {profit_factor} < {MIN_PROFIT_FACTOR_CANDIDATE}")
        return tier, reasons

    if max_dd > MAX_DD_CANDIDATE:
        reasons.append(f"max drawdown {max_dd} > {MAX_DD_CANDIDATE}")
        return tier, reasons

    if max_consec > MAX_CONSEC_CANDIDATE:
        reasons.append(f"max consecutive losses {max_consec} > {MAX_CONSEC_CANDIDATE}")
        return tier, reasons

    if unique_symbols < MIN_SYMBOLS_CANDIDATE:
        reasons.append(f"unique symbols {unique_symbols} < {MIN_SYMBOLS_CANDIDATE} for PAPER_CANDIDATE")
        return tier, reasons

    tier = TIER_PAPER_CANDIDATE

    if oos_avg_r < MIN_OOS_AVG_R_PRIORITY:
        reasons.append(f"OOS avg R {oos_avg_r} < {MIN_OOS_AVG_R_PRIORITY} for PRIORITY")
        return tier, reasons

    if oos_trades < MIN_OOS_TRADES_PRIORITY:
        reasons.append(f"OOS trades {oos_trades} < {MIN_OOS_TRADES_PRIORITY} for PRIORITY")
        return tier, reasons

    tier = TIER_PAPER_PRIORITY
    return tier, reasons


def run_arbiter() -> dict:
    """Run promotion arbiter on tournament results."""
    tournament = _read_json(TOURNAMENT_PATH)
    edge_miner = _read_json(EDGE_MINER_PATH)

    families = tournament.get("families", {})
    raw_best = tournament.get("best_family")
    raw_best_oos = tournament.get("best_oos_avg_r", 0)

    classified = {}
    eligible_best = None
    eligible_best_oos = -999
    paper_candidate_best = None
    paper_candidate_oos = -999

    for fname, fam in families.items():
        tier, reasons = _classify_family(fam)
        classified[fname] = {
            "tier": tier,
            "reasons": reasons,
            "total_trades": fam.get("total_trades", 0),
            "oos_trades": fam.get("oos_trades", 0),
            "is_avg_r": fam.get("is_avg_r", 0),
            "oos_avg_r": fam.get("oos_avg_r", 0),
            "oos_win_rate": fam.get("oos_win_rate", 0),
            "profit_factor": fam.get("profit_factor", 0),
            "max_dd": fam.get("max_dd", 0),
            "max_consec_losses": fam.get("max_consec_losses", 0),
            "unique_symbols": fam.get("unique_symbols", 0),
            "verdict": fam.get("verdict", "N/A"),
        }

        if tier not in (TIER_REJECTED,) and fam.get("oos_avg_r", 0) > eligible_best_oos:
            eligible_best = fname
            eligible_best_oos = fam.get("oos_avg_r", 0)

        if tier in (TIER_PAPER_CANDIDATE, TIER_PAPER_PRIORITY) and fam.get("oos_avg_r", 0) > paper_candidate_oos:
            paper_candidate_best = fname
            paper_candidate_oos = fam.get("oos_avg_r", 0)

    tier_counts = {}
    for c in classified.values():
        t = c["tier"]
        tier_counts[t] = tier_counts.get(t, 0) + 1

    report = {
        "mode": "strategy_promotion_arbiter",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "real_order": False,
        "raw_best_oos_family": raw_best,
        "raw_best_oos_avg_r": raw_best_oos,
        "eligible_best_family": eligible_best,
        "eligible_best_oos_avg_r": eligible_best_oos if eligible_best else None,
        "paper_candidate_family": paper_candidate_best,
        "paper_candidate_oos_avg_r": paper_candidate_oos if paper_candidate_best else None,
        "tier_counts": tier_counts,
        "families": classified,
        "warnings": [],
    }

    if not eligible_best:
        report["warnings"].append("No family meets eligibility for OBSERVE_ONLY or higher")
    if not paper_candidate_best:
        report["warnings"].append("No family qualifies as PAPER_CANDIDATE")
    if raw_best and raw_best != eligible_best:
        report["warnings"].append(
            f"Raw best OOS family ({raw_best}) differs from eligible best ({eligible_best or 'NONE'})"
        )

    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)

    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2, default=str)

    _write_text(report)
    _write_decisions(classified)
    return report


def _write_text(report: dict):
    lines = [
        "=" * 60,
        "  STRATEGY PROMOTION ARBITER",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  Raw Best OOS Family:     {report['raw_best_oos_family'] or 'NONE'} (OOS R={report['raw_best_oos_avg_r']})",
        f"  Eligible Best Family:    {report['eligible_best_family'] or 'NONE'} (OOS R={report['eligible_best_oos_avg_r'] or 'N/A'})",
        f"  Paper Candidate Family:  {report['paper_candidate_family'] or 'NONE'} (OOS R={report['paper_candidate_oos_avg_r'] or 'N/A'})",
        "",
        "  TIER COUNTS:",
    ]
    for tier, count in sorted(report["tier_counts"].items()):
        lines.append(f"    {tier}: {count}")

    lines += ["", "  FAMILY CLASSIFICATIONS:"]
    for fname, c in report["families"].items():
        lines.append(f"    {fname}: {c['tier']}")
        if c["reasons"]:
            for r in c["reasons"]:
                lines.append(f"      - {r}")
        lines.append(
            f"      trades={c['total_trades']} oos_trades={c['oos_trades']} "
            f"is_r={c['is_avg_r']} oos_r={c['oos_avg_r']} "
            f"wr={c['oos_win_rate']}% pf={c['profit_factor']} "
            f"dd={c['max_dd']} consec={c['max_consec_losses']} "
            f"symbols={c['unique_symbols']}"
        )

    if report.get("warnings"):
        lines += ["", "  WARNINGS:"]
        for w in report["warnings"]:
            lines.append(f"    - {w}")

    lines += [
        "",
        "  === SAFETY ===",
        "  Live Trading Enabled: NO",
        "  Real Order Placed: NO",
        "  BINGX_EXECUTION_MODE: NOT SET or read_only",
        "  LIVE_TRADING_ACK: NOT SET",
        "  Final Action: EVIDENCE_BLOCKED",
        "",
        "=" * 60,
    ]

    with open(TXT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n[JSON] {JSON_PATH}")
    print(f"[TXT]  {TXT_PATH}")


def _write_decisions(classified: dict):
    with open(DECISIONS_PATH, "w") as f:
        for fname, c in classified.items():
            entry = {
                "family": fname,
                "tier": c["tier"],
                "reasons": c["reasons"],
                "oos_avg_r": c["oos_avg_r"],
                "total_trades": c["total_trades"],
            }
            f.write(json.dumps(entry) + "\n")


def main():
    run_arbiter()
    return 0


if __name__ == "__main__":
    sys.exit(main())
