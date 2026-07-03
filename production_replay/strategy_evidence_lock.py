"""Strategy evidence lock — paper performance dashboard and live-readiness gate.

Collects all paper trading evidence, computes performance metrics, detects
risk/sizing/duplicate anomalies, and outputs a verdict on whether the strategy
has sufficient evidence to consider live review.

Hard rules:
- Do NOT enable live trading.
- Do NOT set BINGX_EXECUTION_MODE.
- Do NOT set LIVE_TRADING_ACK.
- Do NOT place real orders.
- Never output any live-granted or go-live wording.
"""

import json, os, subprocess, sys
from datetime import datetime, timezone
from statistics import mean

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
TXT_PATH = os.path.join(RESULTS_DIR, "strategy_evidence_report.txt")
JSON_PATH = os.path.join(RESULTS_DIR, "strategy_evidence_report.json")
LEDGER_PATH = os.path.join(STATE_DIR, "strategy_evidence_ledger.jsonl")

PAPER_TRADES_LEDGER = os.path.join(STATE_DIR, "paper_trades.jsonl")
PAPER_STATUS_PATH = os.path.join(RESULTS_DIR, "paper_execution_status.json")
PAPER_OUTCOME_PATH = os.path.join(RESULTS_DIR, "paper_outcome_report.json")
HOURLY_PATH = os.path.join(RESULTS_DIR, "hourly_status.json")
DOCTOR_PATH = os.path.join(RESULTS_DIR, "doctor_daily_packet.json")
ROTATION_PATH = os.path.join(RESULTS_DIR, "candidate_rotation_report.json")

PAPER_CAPITAL_USDT = 400
PAPER_MAX_RISK_PER_TRADE_USDT = 12
PAPER_MAX_PORTFOLIO_NOTIONAL_USDT = 800
PAPER_MAX_ACTIVE_TRADES = 5

# Verdicts
EVIDENCE_INCOMPLETE = "EVIDENCE_INCOMPLETE"
STRATEGY_BLOCKED = "STRATEGY_BLOCKED"
LIVE_REVIEW_READY = "LIVE_REVIEW_READY"
LIVE_REVIEW_STRONG = "LIVE_REVIEW_STRONG"


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


def _r_multiple(pnl: float, risk: float) -> float:
    if risk <= 0:
        return 0.0
    return round(pnl / risk, 2)


def _compute_max_drawdown(closed: list[dict]) -> float:
    """Compute max drawdown from cumulative P&L curve."""
    if not closed:
        return 0.0
    sorted_trades = sorted(closed, key=lambda t: t.get("closed_at", "") or t.get("opened_at", ""))
    running = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in sorted_trades:
        pnl = float(t.get("realized_pnl", 0) or 0)
        running += pnl
        if running > peak:
            peak = running
        dd = peak - running
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 2)


def _detect_anomalies(paper_trades: list[dict], outcome: dict) -> list[str]:
    """Detect risk sizing, notional, preflight, shadow-readiness, duplicate warnings."""
    warnings = []

    closed = [t for t in paper_trades if t.get("status") == "PAPER_CLOSED" and t.get("realized_pnl") is not None]
    open_trades = [t for t in paper_trades if t.get("status") == "PAPER_OPEN"]

    # Risk sizing mismatch
    for t in paper_trades:
        risk = float(t.get("risk", 0) or 0)
        if risk > PAPER_MAX_RISK_PER_TRADE_USDT * 1.05:
            warnings.append(f"risk sizing mismatch: {t.get('symbol','?')} {t.get('side','?')} risk {risk:.2f} > max {PAPER_MAX_RISK_PER_TRADE_USDT} USDT")
            break

    # Notional violation
    for t in paper_trades:
        notional = float(t.get("notional", 0) or 0)
        if notional > PAPER_MAX_PORTFOLIO_NOTIONAL_USDT:
            warnings.append(f"notional violation: {t.get('symbol','?')} {t.get('side','?')} notional {notional:.2f} > max portfolio {PAPER_MAX_PORTFOLIO_NOTIONAL_USDT} USDT")
            break

    # Same-symbol bias (repeated symbol in closed trades)
    sym_counts: dict[str, int] = {}
    for t in closed:
        sym = t.get("symbol", "?")
        sym_counts[sym] = sym_counts.get(sym, 0) + 1
    for sym, count in sym_counts.items():
        if count > len(closed) * 0.5 and len(closed) > 5:
            warnings.append(f"repeated-symbol bias: {sym} appears {count}/{len(closed)} closed trades ({count/len(closed)*100:.0f}%)")
            break

    # Same-coin overexposure (multiple open trades on same coin)
    open_syms: dict[str, int] = {}
    for t in open_trades:
        sym = t.get("symbol", "?")
        open_syms[sym] = open_syms.get(sym, 0) + 1
    for sym, count in open_syms.items():
        if count > 1:
            warnings.append(f"same-coin overexposure: {sym} has {count} concurrent open trades")
            break

    # Duplicate paper trades (same symbol+side opened multiple times without close)
    pairs: dict[str, int] = {}
    for t in paper_trades:
        key = f"{t.get('symbol','?')}_{t.get('side','?')}"
        pairs[key] = pairs.get(key, 0) + 1
    for key, count in pairs.items():
        if count > len(paper_trades) * 0.3 and len(paper_trades) > 10:
            warnings.append(f"duplicate paper trade warning: {key} appears {count}/{len(paper_trades)} entries")
            break

    # Preflight pass check (from outcome or hourly data)
    agg = outcome.get("agg_stats", {})
    if agg.get("total_closed", 0) > 0 and agg.get("average_r", 0) <= 0 and agg.get("total_closed", 0) >= 10:
        warnings.append("negative average R — strategy may lack edge")

    return warnings if warnings else ["none"]


def _long_vs_short(closed: list[dict]) -> dict:
    longs = [t for t in closed if t.get("side", "").upper() == "LONG"]
    shorts = [t for t in closed if t.get("side", "").upper() == "SHORT"]
    result = {}
    for label, group in [("long", longs), ("short", shorts)]:
        if group:
            pnls = [float(t.get("realized_pnl", 0) or 0) for t in group]
            r_vals = [_r_multiple(float(t.get("realized_pnl", 0) or 0), float(t.get("risk", 0) or 0)) for t in group]
            wins = sum(1 for p in pnls if p > 0)
            result[label] = {
                "trades": len(group),
                "wins": wins,
                "losses": len(group) - wins,
                "win_rate": round(wins / len(group) * 100, 1),
                "total_pnl": round(sum(pnls), 4),
                "avg_r": round(mean(r_vals), 2) if r_vals else 0.0,
            }
        else:
            result[label] = {"trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "total_pnl": 0.0, "avg_r": 0.0}
    return result


def _symbol_performance(closed: list[dict]) -> list[dict]:
    syms: dict[str, list[float]] = {}
    for t in closed:
        sym = t.get("symbol", "?")
        pnl = float(t.get("realized_pnl", 0) or 0)
        if sym not in syms:
            syms[sym] = []
        syms[sym].append(pnl)
    perf = []
    for sym, pnls in sorted(syms.items()):
        wins = sum(1 for p in pnls if p > 0)
        perf.append({
            "symbol": sym,
            "trades": len(pnls),
            "wins": wins,
            "losses": len(pnls) - wins,
            "total_pnl": round(sum(pnls), 4),
        })
    return perf


def run_strategy_evidence_lock() -> dict:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)

    paper_trades = _read_ledger(PAPER_TRADES_LEDGER)
    paper_status = _read_json(PAPER_STATUS_PATH)
    outcome = _read_json(PAPER_OUTCOME_PATH)
    hourly = _read_json(HOURLY_PATH)
    doctor = _read_json(DOCTOR_PATH)
    rotation = _read_json(ROTATION_PATH)
    historical = _read_json(os.path.join(RESULTS_DIR, "historical_replay_report.json"))
    if not historical:
        try:
            subprocess.run(
                [sys.executable, "-m", "production_replay.historical_strategy_brain"],
                capture_output=True, text=True, timeout=30,
            )
            historical = _read_json(os.path.join(RESULTS_DIR, "historical_replay_report.json"))
        except Exception:
            pass

    agg = outcome.get("agg_stats", {}) if outcome else {}
    total_trades = len(paper_trades)
    open_trades_list = [t for t in paper_trades if t.get("status") == "PAPER_OPEN"]
    closed = [t for t in paper_trades if t.get("status") == "PAPER_CLOSED" and t.get("realized_pnl") is not None]
    closed_count = len(closed)

    wins = [t for t in closed if float(t.get("realized_pnl", 0) or 0) > 0]
    losses = [t for t in closed if float(t.get("realized_pnl", 0) or 0) <= 0]
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = round(win_count / closed_count * 100, 1) if closed_count > 0 else 0.0

    r_values = []
    for t in closed:
        risk = float(t.get("risk", 0) or 0)
        pnl = float(t.get("realized_pnl", 0) or 0)
        r_values.append(_r_multiple(pnl, risk))
    avg_r = round(mean(r_values), 2) if r_values else 0.0
    total_r = round(sum(r_values), 2) if r_values else 0.0

    winner_r = []
    for t in wins:
        risk = float(t.get("risk", 0) or 0)
        pnl = float(t.get("realized_pnl", 0) or 0)
        winner_r.append(_r_multiple(pnl, risk))
    avg_winner_r = round(mean(winner_r), 2) if winner_r else 0.0

    loser_r = []
    for t in losses:
        risk = float(t.get("risk", 0) or 0)
        pnl = float(t.get("realized_pnl", 0) or 0)
        loser_r.append(_r_multiple(pnl, risk))
    avg_loser_r = round(mean(loser_r), 2) if loser_r else 0.0

    total_pnl = round(sum(float(t.get("realized_pnl", 0) or 0) for t in closed), 4)

    max_dd = _compute_max_drawdown(closed)
    consec_losses = 0
    max_consec_losses = 0
    for t in closed:
        if float(t.get("realized_pnl", 0) or 0) <= 0:
            consec_losses += 1
            max_consec_losses = max(max_consec_losses, consec_losses)
        else:
            consec_losses = 0

    long_short = _long_vs_short(closed)
    symbol_perf = _symbol_performance(closed)

    anomalies = _detect_anomalies(paper_trades, outcome)
    has_anomaly = any(w != "none" for w in anomalies)

    # Pattern/thesis performance (if available in paper_trades)
    thesis_groups: dict[str, list[float]] = {}
    for t in closed:
        thesis = t.get("thesis", "") or t.get("pattern", "") or t.get("reason", "") or "unknown"
        pnl = float(t.get("realized_pnl", 0) or 0)
        if thesis not in thesis_groups:
            thesis_groups[thesis] = []
        thesis_groups[thesis].append(pnl)
    thesis_perf = []
    for thesis, pnls in sorted(thesis_groups.items()):
        if len(pnls) >= 2:
            thesis_perf.append({
                "thesis": thesis,
                "trades": len(pnls),
                "total_pnl": round(sum(pnls), 4),
            })

    # Evidence verdict
    verdict = EVIDENCE_INCOMPLETE
    verdict_reason = ""

    if closed_count < 30:
        verdict = EVIDENCE_INCOMPLETE
        verdict_reason = f"only {closed_count} closed trades (need 30)"
    elif avg_r <= 0:
        verdict = STRATEGY_BLOCKED
        verdict_reason = f"average R {avg_r} <= 0 — strategy not profitable"
    elif closed_count >= 100 and avg_r > 0 and win_rate > 45 and max_dd < 50:
        verdict = LIVE_REVIEW_STRONG
        verdict_reason = f"strong evidence: {closed_count} closed trades, avg R {avg_r}, win rate {win_rate}%, max DD {max_dd} USDT"
    elif closed_count >= 30 and avg_r > 0 and win_rate > 45:
        verdict = LIVE_REVIEW_READY
        verdict_reason = f"meets minimum: {closed_count} closed trades, avg R {avg_r}, win rate {win_rate}%"
    else:
        verdict = STRATEGY_BLOCKED
        verdict_reason = f"win rate {win_rate}% <= 45% or avg R {avg_r} <= 0"

    if has_anomaly and verdict in (LIVE_REVIEW_READY, LIVE_REVIEW_STRONG):
        verdict_reason += " (anomalies detected — manual review required)"
        verdict = LIVE_REVIEW_READY

    live_allowed = False
    live_reason = (
        "evidence incomplete" if verdict == EVIDENCE_INCOMPLETE
        else "strategy blocked" if verdict == STRATEGY_BLOCKED
        else "review ready — manual review required" if verdict == LIVE_REVIEW_READY
        else "strong evidence — manual review required"
    )

    report = {
        "mode": "strategy_evidence_lock",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "real_order": False,
        "evidence_verdict": verdict,
        "verdict_reason": verdict_reason,
        "live_allowed": live_allowed,
        "live_reason": live_reason,
        "total_paper_trades": total_trades,
        "open_trades": len(open_trades_list),
        "closed_trades": closed_count,
        "wins": win_count,
        "losses": loss_count,
        "win_rate": win_rate,
        "average_r": avg_r,
        "total_r": total_r,
        "total_simulated_pnl": total_pnl,
        "max_drawdown_usdt": max_dd,
        "max_consecutive_losses": max_consec_losses,
        "average_winner_r": avg_winner_r,
        "average_loser_r": avg_loser_r,
        "long_short": long_short,
        "symbol_performance": symbol_perf,
        "thesis_performance": thesis_perf,
        "anomalies": anomalies,
        "has_anomaly": has_anomaly,
        "historical_replay": {
            "total_trades": historical.get("total_trades", 0) if historical else 0,
            "verdict": historical.get("verdict", "HISTORICAL_INSUFFICIENT_DATA") if historical else "HISTORICAL_INSUFFICIENT_DATA",
            "average_r": historical.get("average_r", 0) if historical else 0,
            "win_rate": historical.get("win_rate", 0) if historical else 0,
            "in_sample_avg_r": historical.get("in_sample", {}).get("avg_r", 0) if historical else 0,
            "out_of_sample_avg_r": historical.get("out_of_sample", {}).get("avg_r", 0) if historical else 0,
            "recommendation": historical.get("recommendation", "N/A") if historical else "N/A",
        },
        "required_before_real_trading": [
            "minimum 30 closed paper trades",
            "positive average R",
            "no risk mismatch",
            "no same-symbol illusion",
            "no duplicate paper trades",
            "no sizing bug",
        ],
        "historical_edge_miner": _read_json(os.path.join(RESULTS_DIR, "historical_edge_miner_report.json")),
    }

    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2)

    _write_text_report(report)
    _append_to_ledger(report)
    return report


def _write_text_report(report: dict):
    lines = [
        "=" * 60,
        "  STRATEGY EVIDENCE LOCK — PAPER PERFORMANCE DASHBOARD",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  Evidence Verdict:     {report['evidence_verdict']}",
        f"  Reason:               {report['verdict_reason']}",
        "",
        "  === PERFORMANCE SUMMARY ===",
        f"  Total Paper Trades:   {report['total_paper_trades']}",
        f"  Open Trades:          {report['open_trades']}",
        f"  Closed Trades:        {report['closed_trades']}",
        f"  Wins:                 {report['wins']}",
        f"  Losses:               {report['losses']}",
        f"  Win Rate:             {report['win_rate']}%",
        f"  Average R:            {report['average_r']}",
        f"  Total R:              {report['total_r']}",
        f"  Total Simulated P&L:  {report['total_simulated_pnl']:.2f} USDT",
        f"  Max Drawdown:         {report['max_drawdown_usdt']:.2f} USDT",
        f"  Max Consec Losses:    {report['max_consecutive_losses']}",
        f"  Avg Winner R:         {report['average_winner_r']}",
        f"  Avg Loser R:          {report['average_loser_r']}",
        "",
        "  === LONG vs SHORT ===",
    ]

    ls = report["long_short"]
    for label in ("long", "short"):
        d = ls.get(label, {})
        lines.append(
            f"    {label.title()}: {d.get('trades',0)} trades, {d.get('wins',0)}W/{d.get('losses',0)}L "
            f"({d.get('win_rate',0)}%), P&L {d.get('total_pnl',0):.2f} USDT, avg R {d.get('avg_r',0)}"
        )

    perf = report.get("symbol_performance", [])
    if perf:
        lines += ["", "  === SYMBOL PERFORMANCE ==="]
        for s in perf[:10]:
            lines.append(
                f"    {s['symbol']}: {s['trades']} trades, {s['wins']}W/{s['losses']}L, "
                f"P&L {s['total_pnl']:.2f} USDT"
            )

    thesis_p = report.get("thesis_performance", [])
    if thesis_p:
        lines += ["", "  === PATTERN / THESIS PERFORMANCE ==="]
        for tp in thesis_p[:8]:
            lines.append(
                f"    {tp['thesis'][:40]}: {tp['trades']} trades, P&L {tp['total_pnl']:.2f} USDT"
            )

    lines += [
        "",
        "  === ANOMALIES / WARNINGS ===",
    ]
    for a in report["anomalies"]:
        lines.append(f"    - {a}")
    if report["has_anomaly"]:
        lines.append("  *** Anomalies detected — manual review required ***")

    hr = report.get("historical_replay", {})
    if hr and hr.get("total_trades", 0) > 0:
        lines += [
            "",
            "  === HISTORICAL REPLAY BRAIN ===",
            f"  Historical Trades:         {hr['total_trades']}",
            f"  Historical Verdict:        {hr.get('verdict', 'N/A')}",
            f"  Avg R (in-sample):         {hr.get('in_sample_avg_r', 0)}",
            f"  Avg R (out-of-sample):     {hr.get('out_of_sample_avg_r', 0)}",
            f"  Win Rate:                  {hr.get('win_rate', 0)}%",
            f"  Recommendation:            {hr.get('recommendation', 'N/A')}",
        ]

    em = report.get("historical_edge_miner", {})
    if em and em.get("total_groups_analyzed", 0) > 0:
        top = em.get("top_accepted", [])
        best_candidate = top[0]["group"] if top else "NONE"
        best_oos = top[0]["out_of_sample"]["avg_r"] if top else "N/A"
        best_n = top[0]["trades"] if top else "N/A"
        overfit_count = len(em.get("overfit_groups", []))
        lines += [
            "",
            "  === HISTORICAL EDGE MINER ===",
            f"  Best candidate group:      {best_candidate}",
            f"  OOS Avg R:                 {best_oos}",
            f"  Sample size:               {best_n}",
            f"  Overfit status:            {'OVERFIT' if overfit_count > 0 else 'PASS'}",
            f"  Verdict:                   {em.get('overall_verdict', 'N/A')}",
            f"  Live allowed:              NO",
            "",
        ]

    lines += [
        "",
        "  " + "=" * 56,
        "  EVIDENCE LOCK:",
        f"    Live trading allowed: {'NO' if not report['live_allowed'] else 'MANUAL REVIEW REQUIRED'}",
        f"    Reason: {report['live_reason']}",
        "",
        "  Required before real trading:",
    ]
    for req in report["required_before_real_trading"]:
        lines.append(f"    - {req}")
    lines += [
        "",
        "  WARNING: This is an evidence-collection system. Real trading is BLOCKED.",
        "  No real orders placed. No BINGX_EXECUTION_MODE set. LIVE_TRADING_ACK not set.",
        "",
        "=" * 60,
    ]

    with open(TXT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n[JSON] {JSON_PATH}")
    print(f"[TXT]  {TXT_PATH}")


def _append_to_ledger(report: dict):
    entry = {
        "timestamp": report["timestamp"],
        "evidence_verdict": report["evidence_verdict"],
        "closed_trades": report["closed_trades"],
        "win_rate": report["win_rate"],
        "average_r": report["average_r"],
        "total_simulated_pnl": report["total_simulated_pnl"],
        "max_drawdown_usdt": report["max_drawdown_usdt"],
        "live_allowed": report["live_allowed"],
        "has_anomaly": report["has_anomaly"],
    }
    with open(LEDGER_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[LEDGER] {LEDGER_PATH}")


def main():
    report = run_strategy_evidence_lock()
    return 0


if __name__ == "__main__":
    sys.exit(main())
