"""Historical strategy brain — analyzes replay results, computes edge metrics,
produces verdict, and writes structured reports.

Offline research only — never enables live trading.
"""

import json, os, sys
from datetime import datetime, timezone
from statistics import mean
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")

TRADES_LEDGER = os.path.join(STATE_DIR, "historical_replay_trades.jsonl")
PATTERN_MEMORY_LEDGER = os.path.join(STATE_DIR, "historical_pattern_memory.jsonl")
JSON_PATH = os.path.join(RESULTS_DIR, "historical_replay_report.json")
TXT_PATH = os.path.join(RESULTS_DIR, "historical_replay_report.txt")

VERDICT_INSUFFICIENT = "HISTORICAL_INSUFFICIENT_DATA"
VERDICT_NOT_FOUND = "HISTORICAL_EDGE_NOT_FOUND"
VERDICT_WEAK = "HISTORICAL_EDGE_WEAK"
VERDICT_PROMISING = "HISTORICAL_EDGE_PROMISING"
VERDICT_STRONG = "HISTORICAL_EDGE_STRONG_REVIEW"


def _read_ledger(path: str) -> list[dict]:
    try:
        with open(path) as f:
            return [json.loads(l) for l in f if l.strip()]
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _group_and_score(groups: dict) -> dict:
    result = {}
    for key, group in sorted(groups.items()):
        r_vals = [t["r_result"] for t in group]
        avg_r = mean(r_vals) if r_vals else 0.0
        wins = sum(1 for t in group if t.get("is_win"))
        result[key] = {
            "trades": len(group),
            "wins": wins,
            "losses": len(group) - wins,
            "win_rate": round(wins / len(group) * 100, 1) if group else 0.0,
            "avg_r": round(avg_r, 2),
        }
    return result


def _compute_max_drawdown(trades: list[dict]) -> float:
    if not trades:
        return 0.0
    sorted_trades = sorted(trades, key=lambda t: t.get("entry_time", 0))
    running = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in sorted_trades:
        pnl = t.get("r_result", 0) or 0
        running += pnl
        if running > peak:
            peak = running
        dd = peak - running
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 2)


def _compute_max_consecutive_losses(trades: list[dict]) -> int:
    streak = 0
    max_streak = 0
    for t in trades:
        if not t.get("is_win"):
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return max_streak


def analyze_trades(trades: list[dict]) -> dict:
    """Analyze historical replay trades and produce full report."""
    total = len(trades)
    wins = [t for t in trades if t.get("is_win")]
    losses = [t for t in trades if not t.get("is_win")]
    expired = [t for t in trades if t.get("outcome") == "EXPIRED"]
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = round(win_count / total * 100, 1) if total > 0 else 0.0

    r_vals = [t["r_result"] for t in trades]
    avg_r = mean(r_vals) if r_vals else 0.0
    total_r = round(sum(r_vals), 2) if r_vals else 0.0

    max_dd = _compute_drawdown(trades)
    max_consec = _compute_max_consecutive_losses(trades)

    # Groupings
    by_symbol = defaultdict(list)
    by_direction = defaultdict(list)
    by_timeframe = defaultdict(list)
    by_pattern = defaultdict(list)
    by_rr_bucket = defaultdict(list)

    for t in trades:
        by_symbol[t.get("symbol", "?")].append(t)
        by_direction[t.get("direction", "?")].append(t)
        by_timeframe[t.get("timeframe", "?")].append(t)
        by_pattern[t.get("pattern", "unknown")].append(t)
        rr = abs(t.get("r_result", 0))
        if rr < 1:
            by_rr_bucket["0-1"].append(t)
        elif rr < 2:
            by_rr_bucket["1-2"].append(t)
        elif rr < 4:
            by_rr_bucket["2-4"].append(t)
        else:
            by_rr_bucket["4+"].append(t)

    # Split in-sample (70%) / out-of-sample (30%) by time
    sorted_trades = sorted(trades, key=lambda t: t.get("entry_time", 0))
    split_idx = int(len(sorted_trades) * 0.7)
    in_sample = sorted_trades[:split_idx]
    out_of_sample = sorted_trades[split_idx:]

    is_r_vals = [t["r_result"] for t in in_sample]
    oos_r_vals = [t["r_result"] for t in out_of_sample]
    is_avg_r = round(mean(is_r_vals), 2) if is_r_vals else 0.0
    oos_avg_r = round(mean(oos_r_vals), 2) if oos_r_vals else 0.0
    is_win_count = sum(1 for t in in_sample if t.get("is_win"))
    oos_win_count = sum(1 for t in out_of_sample if t.get("is_win"))
    is_win_rate = round(is_win_count / len(in_sample) * 100, 1) if in_sample else 0.0
    oos_win_rate = round(oos_win_count / len(out_of_sample) * 100, 1) if out_of_sample else 0.0

    # Best/worst
    sym_stats = _group_and_score(by_symbol)
    pat_stats = _group_and_score(by_pattern)
    tf_stats = _group_and_score(by_timeframe)
    dir_stats = _group_and_score(by_direction)

    best_symbol = None
    worst_symbol = None
    if sym_stats:
        best_symbol = max(sym_stats, key=lambda s: sym_stats[s]["avg_r"])
        worst_symbol = min(sym_stats, key=lambda s: sym_stats[s]["avg_r"])

    best_pattern = None
    worst_pattern = None
    if pat_stats:
        best_pattern = max(pat_stats, key=lambda p: pat_stats[p]["avg_r"])
        worst_pattern = min(pat_stats, key=lambda p: pat_stats[p]["avg_r"])

    best_timeframe = max(tf_stats, key=lambda t: tf_stats[t]["avg_r"]) if tf_stats else None
    worst_timeframe = min(tf_stats, key=lambda t: tf_stats[t]["avg_r"]) if tf_stats else None

    # Verdict
    verdict = VERDICT_INSUFFICIENT
    recommendation = "Insufficient historical data"

    if total < 100:
        verdict = VERDICT_INSUFFICIENT
        recommendation = f"Only {total} trades (need 100+)"
    elif avg_r <= 0:
        verdict = VERDICT_NOT_FOUND
        recommendation = f"Average R {avg_r} <= 0 — no edge found"
    elif total >= 300 and avg_r > 0.25 and win_rate > 35 and max_dd < 50:
        verdict = VERDICT_STRONG
        recommendation = "Strong historical edge — promote for review"
    elif total >= 100 and avg_r > 0 and win_rate > 35:
        if max_dd > 30:
            verdict = VERDICT_WEAK
            recommendation = f"Edge found but drawdown {max_dd} is high"
        else:
            verdict = VERDICT_PROMISING
            recommendation = "Promising historical edge — continue monitoring"
    elif total >= 100 and avg_r > 0:
        verdict = VERDICT_WEAK
        recommendation = f"Edge weak (win rate {win_rate}% <= 35%)"

    report = {
        "mode": "historical_replay_brain",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "real_order": False,
        "total_trades": total,
        "wins": win_count,
        "losses": loss_count,
        "expired": len(expired),
        "win_rate": win_rate,
        "average_r": avg_r,
        "total_r": total_r,
        "max_drawdown_r": max_dd,
        "max_consecutive_losses": max_consec,
        "in_sample": {
            "trades": len(in_sample),
            "avg_r": is_avg_r,
            "win_rate": is_win_rate,
        },
        "out_of_sample": {
            "trades": len(out_of_sample),
            "avg_r": oos_avg_r,
            "win_rate": oos_win_rate,
        },
        "by_symbol": sym_stats,
        "by_direction": dir_stats,
        "by_timeframe": tf_stats,
        "by_pattern": pat_stats,
        "by_rr_bucket": _group_and_score(by_rr_bucket),
        "best_symbol": {"symbol": best_symbol, **sym_stats[best_symbol]} if best_symbol else None,
        "worst_symbol": {"symbol": worst_symbol, **sym_stats[worst_symbol]} if worst_symbol else None,
        "best_pattern": {"pattern": best_pattern, **pat_stats[best_pattern]} if best_pattern else None,
        "worst_pattern": {"pattern": worst_pattern, **pat_stats[worst_pattern]} if worst_pattern else None,
        "best_timeframe": {"timeframe": best_timeframe, **tf_stats[best_timeframe]} if best_timeframe else None,
        "worst_timeframe": {"timeframe": worst_timeframe, **tf_stats[worst_timeframe]} if worst_timeframe else None,
        "verdict": verdict,
        "recommendation": recommendation,
        "warnings": [],
    }

    # Warnings
    if oos_avg_r <= 0 and is_avg_r > 0:
        report["warnings"].append(
            f"Positive in-sample ({is_avg_r}) but negative out-of-sample ({oos_avg_r}) — likely overfitting"
        )
    if max_dd > 20:
        report["warnings"].append(f"High drawdown ({max_dd} R)")
    if max_consec > 10:
        report["warnings"].append(f"Long consecutive loss streak ({max_consec})")

    return report


def _compute_drawdown(trades: list[dict]) -> float:
    """Compute maximum drawdown in R units."""
    if not trades:
        return 0.0
    sorted_trades = sorted(trades, key=lambda t: t.get("entry_time", 0))
    running = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in sorted_trades:
        pnl = t.get("r_result", 0) or 0
        running += pnl
        if running > peak:
            peak = running
        dd = peak - running
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 2)


def run_historical_brain(trades: list[dict] | None = None) -> dict:
    """Run historical strategy brain analysis."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)

    if trades is None:
        trades = _read_ledger(TRADES_LEDGER)

    report = analyze_trades(trades)

    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2)

    _write_text_report(report)
    _append_to_ledger(report)
    return report


def _write_text_report(report: dict):
    lines = [
        "=" * 60,
        "  HISTORICAL REPLAY BRAIN",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  Total Historical Trades:  {report['total_trades']}",
        f"  Wins:                     {report['wins']}",
        f"  Losses:                   {report['losses']}",
        f"  Expired:                  {report['expired']}",
        f"  Win Rate:                 {report['win_rate']}%",
        f"  Average R:                {report['average_r']}",
        f"  Total R:                  {report['total_r']}",
        f"  Max Drawdown (R):         {report['max_drawdown_r']}",
        f"  Max Consecutive Losses:   {report['max_consecutive_losses']}",
        "",
        "  === WALK-FORWARD SPLIT ===",
        f"  In-sample:       {report['in_sample']['trades']} trades, "
        f"avg R {report['in_sample']['avg_r']}, WR {report['in_sample']['win_rate']}%",
        f"  Out-of-sample:   {report['out_of_sample']['trades']} trades, "
        f"avg R {report['out_of_sample']['avg_r']}, WR {report['out_of_sample']['win_rate']}%",
        "",
    ]

    best_pat = report.get("best_pattern")
    worst_pat = report.get("worst_pattern")
    if best_pat:
        lines.append(f"  Best Pattern:  {best_pat['pattern']} — avg R {best_pat['avg_r']}, WR {best_pat['win_rate']}%")
    if worst_pat:
        lines.append(f"  Worst Pattern: {worst_pat['pattern']} — avg R {worst_pat['avg_r']}, WR {worst_pat['win_rate']}%")

    best_sym = report.get("best_symbol")
    worst_sym = report.get("worst_symbol")
    if best_sym:
        lines.append(f"  Best Symbol:   {best_sym['symbol']} — avg R {best_sym['avg_r']}")
    if worst_sym:
        lines.append(f"  Worst Symbol:  {worst_sym['symbol']} — avg R {worst_sym['avg_r']}")

    best_tf = report.get("best_timeframe")
    worst_tf = report.get("worst_timeframe")
    if best_tf:
        lines.append(f"  Best TF:       {best_tf['timeframe']} — avg R {best_tf['avg_r']}")
    if worst_tf:
        lines.append(f"  Worst TF:      {worst_tf['timeframe']} — avg R {worst_tf['avg_r']}")

    lines += [
        "",
        f"  Verdict:           {report['verdict']}",
        f"  Recommendation:    {report['recommendation']}",
    ]

    if report.get("by_direction"):
        lines += ["", "  PERFORMANCE BY DIRECTION:"]
        for d, s in sorted(report["by_direction"].items()):
            lines.append(f"    {d}: {s['trades']} trades, avg R {s['avg_r']}, WR {s['win_rate']}%")

    if report.get("by_pattern"):
        lines += ["", "  PERFORMANCE BY PATTERN:"]
        for p, s in sorted(report["by_pattern"].items()):
            lines.append(f"    {p}: {s['trades']} trades, avg R {s['avg_r']}, WR {s['win_rate']}%")

    if report.get("warnings"):
        lines += ["", "  WARNINGS:"]
        for w in report["warnings"]:
            lines.append(f"    - {w}")
    else:
        lines += ["", "  WARNINGS: None"]

    lines += [
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
        "total_trades": report["total_trades"],
        "verdict": report["verdict"],
        "avg_r": report["average_r"],
        "win_rate": report["win_rate"],
        "is_avg_r": report["in_sample"]["avg_r"],
        "oos_avg_r": report["out_of_sample"]["avg_r"],
    }
    with open(PATTERN_MEMORY_LEDGER, "a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[LEDGER] {PATTERN_MEMORY_LEDGER}")


def main():
    report = run_historical_brain()
    return 0


if __name__ == "__main__":
    sys.exit(main())
