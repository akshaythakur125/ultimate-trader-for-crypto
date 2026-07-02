"""Multi-candidate paper watchlist.

Tracks fresh eligible and near-eligible candidates while an active paper
trade is open. Does NOT open a second paper trade. Does NOT enable live
trading. Does NOT place real orders.

This module NEVER places real orders, NEVER sets BINGX_EXECUTION_MODE=live_micro,
and NEVER sets LIVE_TRADING_ACK.
"""

import json, os, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
TXT_PATH = os.path.join(RESULTS_DIR, "paper_candidate_watchlist.txt")
JSON_PATH = os.path.join(RESULTS_DIR, "paper_candidate_watchlist.json")
LEDGER_PATH = os.path.join(STATE_DIR, "paper_candidate_watchlist.jsonl")
PORTFOLIO_PATH = os.path.join(STATE_DIR, "paper_portfolio.json")


def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _candidate_score(c: dict) -> float:
    return float(c.get("thesis_score", 0) or c.get("raw_anomaly_score", 0))


def _eligibility_status(c: dict) -> str:
    ts = c.get("trigger_status", "")
    if ts == "TRIGGER_CONFIRMED":
        if float(c.get("thesis_score", 0) or 0) >= 75 and float(c.get("rr", 0) or 0) >= 4:
            return "SHADOW_ELIGIBLE"
        return "REVIEW_CANDIDATE"
    return ts


def run_paper_candidate_watchlist() -> dict:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)

    trigger_watcher = _read_json(RESULTS_DIR + "/trigger_watcher_report.json")
    arbiter = _read_json(RESULTS_DIR + "/candidate_arbiter_report.json")
    shadow = _read_json(RESULTS_DIR + "/bingx_order_intent.json")
    paper_status = _read_json(RESULTS_DIR + "/paper_execution_status.json")
    paper_outcome = _read_json(RESULTS_DIR + "/paper_outcome_report.json")
    hourly = _read_json(RESULTS_DIR + "/hourly_status.json")

    reasons = []

    # -- Active paper trades from portfolio --
    portfolio = _read_json(PORTFOLIO_PATH) if os.path.exists(PORTFOLIO_PATH) else (paper_status.get("portfolio") if paper_status else None)
    if isinstance(portfolio, dict) and "active_trades" in portfolio:
        portfolio = portfolio["active_trades"]
    if isinstance(portfolio, list):
        active_trades_list = [t for t in portfolio if t.get("status") == "PAPER_OPEN"]
    else:
        active_trades_list = []
    active_symbols = set(t.get("symbol", "") for t in active_trades_list)
    trade_lock_on = len(active_trades_list) > 0

    # -- All candidates from trigger watcher --
    all_candidates: list[dict] = trigger_watcher.get("candidates", []) if trigger_watcher else []
    total_candidates = len(all_candidates)

    # -- Breakdown --
    trigger_confirmed = [c for c in all_candidates if c.get("trigger_status") == "TRIGGER_CONFIRMED"]
    shadow_eligible = [c for c in trigger_confirmed if _eligibility_status(c) == "SHADOW_ELIGIBLE"]
    review_candidates = [c for c in trigger_confirmed if _eligibility_status(c) == "REVIEW_CANDIDATE"]
    rejected = [c for c in all_candidates if c.get("trigger_status") not in ("TRIGGER_CONFIRMED", "WAITING")]

    # -- Top fresh candidates (excluding active symbols) --
    fresh_pool = [c for c in all_candidates if c.get("symbol", "") not in active_symbols]
    fresh_pool.sort(key=_candidate_score, reverse=True)
    top_fresh = fresh_pool[:10]

    # Add eligibility_status and rejection_reason to top fresh
    for c in top_fresh:
        c["eligibility_status"] = _eligibility_status(c)
        if c.get("trigger_status") != "TRIGGER_CONFIRMED":
            c["rejection_reason_display"] = f"{c.get('trigger_status','N/A')}, {c.get('bucket','N/A')}, score={_candidate_score(c)}"
        else:
            c["rejection_reason_display"] = None

    # -- Active trade score --
    def _trade_score(t: dict) -> float:
        return float(t.get("rr", 0) or 0)

    active_scores = [_trade_score(t) for t in active_trades_list]
    active_max_score = max(active_scores) if active_scores else 0

    # -- Best fresh candidate --
    best_fresh = top_fresh[0] if top_fresh else None
    best_fresh_score = _trade_score(best_fresh) if best_fresh else 0
    best_fresh_stronger = bool(
        best_fresh and trade_lock_on and best_fresh_score > active_max_score
    )

    # -- Next action --
    if trade_lock_on:
        if best_fresh_stronger and best_fresh:
            next_action = "WAIT_FOR_CURRENT_TRADE_CLOSE"
            reasons.append(
                f"stronger candidate {best_fresh['symbol']} {best_fresh['direction']} "
                f"(RR:{best_fresh.get('rr','?')}) exists but {len(active_trades_list)} active paper trade(s) lock ON"
            )
        else:
            next_action = "ACTIVE_TRADE_MONITORING"
            syms = ', '.join(t.get('symbol','?') for t in active_trades_list)
            reasons.append(f"{len(active_trades_list)} active paper trade(s): {syms}; trade lock ON")
    elif shadow_eligible or best_fresh:
        next_action = "NEW_CANDIDATE_AVAILABLE"
        label = best_fresh.get("symbol", "?") if best_fresh else "?"
        reasons.append(f"candidate {label} available; no active trade lock")
    else:
        next_action = "NO_VALID_CANDIDATE"
        reasons.append("no valid candidates found")

    report = {
        "mode": "paper_candidate_watchlist",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "real_order": False,
        "active_trade_lock_on": trade_lock_on,
        "active_trades_count": len(active_trades_list),
        "active_trade_symbols": list(active_symbols),
        "active_trades": active_trades_list,
        "candidate_discovery": {
            "total_candidates": total_candidates,
            "trigger_confirmed": len(trigger_confirmed),
            "shadow_eligible": len(shadow_eligible),
            "review_candidates": len(review_candidates),
            "rejected": len(rejected),
        },
        "top_fresh_candidates": top_fresh,
        "candidate_comparison": {
            "active_trades_max_rr": active_max_score,
            "active_trades_count": len(active_trades_list),
            "best_fresh_candidate": {
                "symbol": best_fresh.get("symbol", "") if best_fresh else None,
                "timeframe": best_fresh.get("timeframe", "") if best_fresh else None,
                "direction": best_fresh.get("direction", "") if best_fresh else None,
                "rr": float(best_fresh.get("rr", 0) or 0) if best_fresh else 0,
                "thesis_score": _candidate_score(best_fresh) if best_fresh else 0,
                "trigger_status": best_fresh.get("trigger_status", "") if best_fresh else "",
                "eligibility_status": _eligibility_status(best_fresh) if best_fresh else "",
            } if best_fresh else None,
            "best_fresh_score": best_fresh_score,
            "best_fresh_stronger": best_fresh_stronger,
        },
        "next_action": next_action,
        "reasons": reasons,
    }

    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2)

    _write_text_report(report)
    _append_to_ledger(report)
    return report


def _write_text_report(report: dict):
    lines = [
        "=" * 60,
        "  PAPER CANDIDATE WATCHLIST",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  Trade Lock:         {'ON' if report['active_trade_lock_on'] else 'OFF'}",
        "",
    ]

    trade = report.get("active_trades")
    if trade:
        lines += ["  Active Paper Trades:"]
        for i, t in enumerate(trade, 1):
            lines += [
                f"    [{i}] {t.get('symbol','?')} {t.get('side','?')} "
                f"Entry:{t.get('entry',0)} Stop:{t.get('stop',0)} Target:{t.get('target',0)} "
                f"Status:{t.get('status','?')} P&L:{t.get('unrealized_pnl','?')}",
            ]

    cd = report.get("candidate_discovery", {})
    lines += [
        "",
        "  Candidate Discovery:",
        f"    Total:           {cd.get('total_candidates', 0)}",
        f"    Confirmed:       {cd.get('trigger_confirmed', 0)}",
        f"    Shadow Eligible: {cd.get('shadow_eligible', 0)}",
        f"    Review:          {cd.get('review_candidates', 0)}",
        f"    Rejected:        {cd.get('rejected', 0)}",
        "",
    ]

    cc = report.get("candidate_comparison", {})
    bf = cc.get("best_fresh_candidate")
    if bf:
        lines += [
            "  Best Fresh Candidate:",
            f"    Symbol:   {bf.get('symbol','?')} {bf.get('direction','?')} {bf.get('timeframe','?')}",
            f"    RR:       1:{bf.get('rr','?')}",
            f"    Score:    {bf.get('thesis_score','?')}",
            f"    Status:   {bf.get('eligibility_status','?')}",
            f"    Stronger: {'YES' if cc.get('best_fresh_stronger') else 'NO'} (active trades max RR={cc.get('active_trades_max_rr','?')})",
        ]
    else:
        lines += ["  Best Fresh Candidate: NONE"]

    fresh = report.get("top_fresh_candidates", [])
    if fresh:
        excluded = ', '.join(report.get('active_trade_symbols', [])) or '?'
        lines += [
            "",
            f"  Top {len(fresh)} Fresh Candidates (excluding {excluded}):",
            "    {:<12s} {:<6s} {:<7s} {:<6s} {:<6s} {:<16s} {:<20s}".format(
                "Symbol", "TF", "Side", "RR", "Score", "Status", "Rejection"),
        ]
        for c in fresh:
            rej = (c.get("rejection_reason_display") or "")[:20]
            lines.append("    {:<12s} {:<6s} {:<7s} {:<6s} {:<6s} {:<16s} {:<20s}".format(
                c.get("symbol", "?")[:12],
                c.get("timeframe", ""),
                c.get("direction", "?"),
                str(c.get("rr", "?")),
                str(int(_candidate_score(c))) if _candidate_score(c) else "?",
                (c.get("eligibility_status") or c.get("trigger_status", "?"))[:16],
                rej,
            ))

    lines += [
        "",
        f"  Next Action: {report['next_action']}",
        "",
    ]
    for r in report["reasons"]:
        lines.append(f"    - {r}")
    lines += [
        "",
        "  WARNING: Watchlist only. No real orders placed. No second paper trade opened.",
        "",
        "=" * 60,
    ]

    with open(TXT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n[JSON] {JSON_PATH}")
    print(f"[TXT]  {TXT_PATH}")
    if fresh:
        print(f"[LEDGER] {LEDGER_PATH}")


def _append_to_ledger(report: dict):
    entry = {
        "timestamp": report["timestamp"],
        "active_trade_lock_on": report["active_trade_lock_on"],
        "next_action": report["next_action"],
        "candidate_discovery": report.get("candidate_discovery", {}),
        "best_fresh_symbol": (
            report.get("candidate_comparison", {}).get("best_fresh_candidate", {}).get("symbol")
        ),
        "best_fresh_stronger": report.get("candidate_comparison", {}).get("best_fresh_stronger", False),
        "active_trades_count": report.get("active_trades_count", 0),
    }
    with open(LEDGER_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def main():
    report = run_paper_candidate_watchlist()
    return 0


if __name__ == "__main__":
    sys.exit(main())
