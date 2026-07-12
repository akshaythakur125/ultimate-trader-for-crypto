"""Breadwinner Daily Report for Phase 75 — Hands-Off Breadwinner Sprint.

Combines:
- Legacy paper cleanup results
- Auto edge miner results
- Promotion arbiter tiers
- Paper execution status

Outputs:
- deploy_results/breadwinner_daily_report.json
- deploy_results/breadwinner_daily_report.txt

Final decision:
- NO_EDGE_FOUND: No statistically valid edge found
- PAPER_ONLY: Valid edge found, paper trading allowed
- KEEP_WATCHING: Some edge found but not yet validated

This module NEVER places real orders, NEVER enables live trading.
"""

import json, os, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
JSON_PATH = os.path.join(RESULTS_DIR, "breadwinner_daily_report.json")
TXT_PATH = os.path.join(RESULTS_DIR, "breadwinner_daily_report.txt")


def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def run_breadwinner_daily() -> dict:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)

    # Run legacy cleanup
    from production_replay.paper_legacy_cleanup import scan_and_clean_legacy
    cleanup_report = scan_and_clean_legacy()

    # Run auto edge miner
    from production_replay.auto_edge_miner import run_auto_edge_miner
    edge_report = run_auto_edge_miner()

    # Read promotion arbiter
    promotion_report = _read_json(os.path.join(RESULTS_DIR, "strategy_promotion_arbiter_report.json"))

    # Read paper execution
    paper_report = _read_json(os.path.join(RESULTS_DIR, "paper_execution_status.json"))

    # Read breadwinner strategy backtest
    strategy_report = _read_json(os.path.join(RESULTS_DIR, "breadwinner_strategy_report.json"))

    # Read breadwinner fast tournament
    tournament_report = _read_json(os.path.join(RESULTS_DIR, "breadwinner_fast_tournament_report.json"))

    # Read derivatives edge layer
    derivatives_report = _read_json(os.path.join(RESULTS_DIR, "derivatives_edge_report.json"))

    # Read breadwinner watchtower (Phase 79)
    watchtower_report = _read_json(os.path.join(RESULTS_DIR, "breadwinner_watchtower_report.json"))

    # Read paper signal outcome tracker (Phase 79)
    signal_report = _read_json(os.path.join(RESULTS_DIR, "paper_signal_outcome_report.json"))

    # Determine final decision
    edge_decision = edge_report.get("final_decision", "NO_EDGE_FOUND")
    strategy_verdict = strategy_report.get("final_verdict", "NO_EDGE_FOUND")
    tournament_verdict = tournament_report.get("final_decision", "NO_EDGE_FOUND")
    derivatives_verdict = derivatives_report.get("final_decision", "NO_EDGE_FOUND")
    watchtower_verdict = watchtower_report.get("final_mode", "KEEP_WATCHING") if watchtower_report else "KEEP_WATCHING"
    cleanup_invalidated = cleanup_report.get("invalidated_count", 0)

    # Use best verdict across all sources
    verdict_priority = {"PAPER_PRIORITY_FOUND": 4, "PAPER_PRIORITY": 4,
                        "BACKTESTABLE_EDGE_FOUND": 3, "PAPER_CANDIDATE_FOUND": 3, "PAPER_CANDIDATE": 3,
                        "PAPER_WATCHLIST_ONLY": 2,
                        "PAPER_SIGNAL_READY": 5, "LIVE_REVIEW_READY": 6,
                        "NO_EDGE_FOUND": 0, "KEEP_WATCHING": 1}
    best_verdict = "NO_EDGE_FOUND"
    for v in [edge_decision, strategy_verdict, tournament_verdict, derivatives_verdict, watchtower_verdict]:
        if verdict_priority.get(v, 0) > verdict_priority.get(best_verdict, 0):
            best_verdict = v

    # Promotion tiers
    promotion_tiers = {}
    families = promotion_report.get("families", {})
    for name, info in families.items():
        promotion_tiers[name] = {
            "tier": info.get("tier", "UNKNOWN"),
            "oos_avg_r": info.get("oos_avg_r", 0),
            "total_trades": info.get("total_trades", 0),
        }

    # Best valid family
    best_family = None
    for name, info in families.items():
        if info.get("tier") in ("PAPER_CANDIDATE", "PAPER_PRIORITY"):
            if best_family is None or info.get("oos_avg_r", 0) > best_family.get("oos_avg_r", 0):
                best_family = {"family": name, **info}

    # Active paper trades
    portfolio_path = os.path.join(STATE_DIR, "paper_portfolio.json")
    try:
        with open(portfolio_path) as f:
            portfolio = json.load(f)
        active_trades = [t for t in portfolio if t.get("status") == "PAPER_OPEN"]
    except (FileNotFoundError, json.JSONDecodeError):
        active_trades = []

    report = {
        "mode": "breadwinner_daily_report",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "live_trading_enabled": False,
        "real_order": False,
        "final_decision": best_verdict,
        "edge_miner": {
            "symbols_scanned": edge_report.get("symbols_scanned", 0),
            "variants_tested": edge_report.get("variants_tested", 0),
            "variants_passed": edge_report.get("variants_passed", 0),
            "best_variant": edge_report.get("best_variant"),
            "final_decision": edge_decision,
        },
        "strategy_backtest": {
            "strategy": strategy_report.get("strategy", "N/A"),
            "final_verdict": strategy_verdict,
            "best_variant": strategy_report.get("best_variant"),
            "best_timeframe": strategy_report.get("best_timeframe"),
            "variants_tested": strategy_report.get("variants_tested", 0),
            "variants_passed": strategy_report.get("variants_passed", 0),
        },
        "fast_tournament": {
            "final_decision": tournament_verdict,
            "best_variant": tournament_report.get("best_variant"),
            "best_family": tournament_report.get("best_family"),
            "best_timeframe": tournament_report.get("best_timeframe"),
            "variants_tested": tournament_report.get("variants_tested", 0),
            "variants_passed": tournament_report.get("variants_passed", 0),
        },
        "derivatives_edge": {
            "final_decision": derivatives_verdict,
            "best_backtest": derivatives_report.get("best_backtest"),
            "live_observation": derivatives_report.get("live_observation", {}),
        },
        "watchtower": {
            "final_mode": watchtower_verdict,
            "candidates_scored": watchtower_report.get("total_candidates_scored", 0) if watchtower_report else 0,
            "top_candidates": watchtower_report.get("top_candidates", []) if watchtower_report else [],
            "live_review_ready": watchtower_report.get("live_review_ready", False) if watchtower_report else False,
        },
        "signal_outcomes": {
            "closed_signals": signal_report.get("closed_signals", 0) if signal_report else 0,
            "win_rate": signal_report.get("win_rate", 0) if signal_report else 0,
            "avg_r": signal_report.get("avg_r", 0) if signal_report else 0,
            "profit_factor": signal_report.get("profit_factor", 0) if signal_report else 0,
            "max_consecutive_losses": signal_report.get("max_consecutive_losses", 0) if signal_report else 0,
            "live_review_ready": signal_report.get("live_review_ready", False) if signal_report else False,
        },
        "legacy_cleanup": {
            "invalidated_count": cleanup_invalidated,
            "invalidated_trades": cleanup_report.get("invalidated_trades", []),
        },
        "promotion_tiers": promotion_tiers,
        "best_valid_family": best_family,
        "active_paper_trades": len(active_trades),
        "portfolio_summary": {
            "active_count": len(active_trades),
            "total_notional": sum(float(t.get("notional", 0) or 0) for t in active_trades),
            "total_risk": sum(float(t.get("risk", 0) or 0) for t in active_trades),
        },
        "live_trading": {
            "enabled": False,
            "reason": "evidence lock blocks live trading until forward paper trades prove edge",
        },
        "warnings": edge_report.get("warnings", []),
    }

    # Write reports
    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2, default=str)

    _write_text_report(report)
    return report


def _write_text_report(report: dict):
    lines = [
        "=" * 60,
        "  BREADWINNER DAILY REPORT",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  Final Decision:     {report['final_decision']}",
        f"  Live Trading:       {'ENABLED' if report['live_trading']['enabled'] else 'BLOCKED'}",
        f"  Real Orders:        NO",
        "",
        "  Edge Miner:",
        f"    Symbols Scanned:    {report['edge_miner']['symbols_scanned']}",
        f"    Variants Tested:    {report['edge_miner']['variants_tested']}",
        f"    Variants Passed:    {report['edge_miner']['variants_passed']}",
    ]

    best = report["edge_miner"].get("best_variant")
    if best:
        lines += [
            "",
            "  Best Variant:",
            f"    Family:       {best['family']}",
            f"    Timeframe:    {best['timeframe']}",
            f"    RR Target:    {best['rr_target']}",
            f"    OOS Avg R:    {best['oos_avg_r']}",
            f"    OOS Win Rate: {best['oos_win_rate']}%",
            f"    Profit Factor:{best['profit_factor']}",
            f"    Max DD:       {best['max_dd']}",
            f"    Symbols:      {best['unique_symbols']}",
        ]

    lines += [
        "",
        "  Legacy Cleanup:",
        f"    Invalidated:   {report['legacy_cleanup']['invalidated_count']}",
    ]
    for t in report["legacy_cleanup"].get("invalidated_trades", []):
        lines.append(f"      - {t['symbol']} {t['side']} reason={t['reason']}")

    lines += [
        "",
        "  Promotion Tiers:",
    ]
    for family, info in report.get("promotion_tiers", {}).items():
        tier = info.get("tier", "UNKNOWN")
        marker = " *" if tier in ("PAPER_CANDIDATE", "PAPER_PRIORITY") else ""
        lines.append(f"    {family}: {tier}{marker}")

    lines += [
        "",
        "  Active Paper Trades:",
        f"    Count:        {report['active_paper_trades']}",
        f"    Total Notional:{report['portfolio_summary']['total_notional']:.2f} USDT",
        f"    Total Risk:   {report['portfolio_summary']['total_risk']:.2f} USDT",
        "",
    ]

    # Phase 79: Watchtower section
    wt = report.get("watchtower", {})
    if wt.get("top_candidates"):
        lines += [
            "  BREADWINNER WATCHTOWER:",
            f"    Final Mode:          {wt.get('final_mode', 'N/A')}",
            f"    Candidates Scored:   {wt.get('candidates_scored', 0)}",
            f"    Top Candidates:      {len(wt.get('top_candidates', []))}",
        ]
        for i, c in enumerate(wt.get("top_candidates", [])[:3], 1):
            lines.append(
                f"    {i}. {c.get('symbol','?')} {c.get('direction','?')} "
                f"RR:{c.get('rr',0):.1f} Score:{c.get('score',0):.1f} "
                f"{c.get('setup_type','?')}"
            )
        lines += [""]
    else:
        lines += [
            "  BREADWINNER WATCHTOWER:",
            f"    Final Mode:          {wt.get('final_mode', 'KEEP_WATCHING')}",
            f"    Top Candidates:      NONE",
            "",
        ]

    # Phase 79: Signal outcomes section
    so = report.get("signal_outcomes", {})
    if so.get("closed_signals", 0) > 0:
        lines += [
            "  PAPER SIGNAL OUTCOMES:",
            f"    Closed Signals:      {so.get('closed_signals', 0)}",
            f"    Win Rate:            {so.get('win_rate', 0):.1%}",
            f"    Average R:           {so.get('avg_r', 0):.4f}",
            f"    Profit Factor:       {so.get('profit_factor', 0):.2f}",
            f"    Max Consec Losses:   {so.get('max_consecutive_losses', 0)}",
            f"    Live Review Ready:   {'YES' if so.get('live_review_ready') else 'NO'}",
            "",
        ]

    lines += [
        f"  Live Trading: {report['live_trading']['reason']}",
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
    report = run_breadwinner_daily()
    return 0


if __name__ == "__main__":
    sys.exit(main())
