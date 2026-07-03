"""Historical edge miner — mines trade dataset for sub-strategies with statistical edge.

Analyzes historical replay trades across many dimensions to identify whether any
statistically meaningful sub-strategy has genuine predictive edge, with overfit
protection via in-sample/out-of-sample split and multiple rejection criteria.

Offline research only — never enables live trading.
"""

import json, os, sys
from datetime import datetime, timezone
from statistics import mean, median
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.historical_cache_resolver import find_project_root

PROJECT_ROOT = find_project_root()
RESULTS_DIR = os.path.join(PROJECT_ROOT, "deploy_results")
STATE_DIR = os.path.join(PROJECT_ROOT, "runtime_state")

TRADES_LEDGER = os.path.join(STATE_DIR, "historical_replay_trades.jsonl")
PATTERN_MEMORY_LEDGER = os.path.join(STATE_DIR, "historical_pattern_memory.jsonl")
REPLAY_REPORT_PATH = os.path.join(RESULTS_DIR, "historical_replay_report.json")
JSON_PATH = os.path.join(RESULTS_DIR, "historical_edge_miner_report.json")
TXT_PATH = os.path.join(RESULTS_DIR, "historical_edge_miner_report.txt")
CANDIDATES_PATH = os.path.join(STATE_DIR, "historical_edge_candidates.jsonl")

MIN_TRADES_PER_GROUP = 100
MIN_OOS_TRADES = 30
MIN_SYMBOLS_PER_GROUP = 3
MIN_WIN_RATE = 20.0
MIN_AVG_R = 0.0

BANNED_GROUPING_FIELDS = {
    "r_result", "r_after_fees", "is_win", "outcome", "exit_reason",
    "exit_price", "max_favorable_excursion_pct", "max_adverse_excursion_pct",
    "holding_candles",
}

V_EDGE_NOT_FOUND = "EDGE_NOT_FOUND"
V_EDGE_FRAGILE = "EDGE_FRAGILE"
V_EDGE_PROMISING = "EDGE_PROMISING_REVIEW"
V_EDGE_STRONG = "EDGE_STRONG_REVIEW"


def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _read_trades(path: str = TRADES_LEDGER) -> list[dict]:
    try:
        with open(path) as f:
            return [json.loads(l) for l in f if l.strip()]
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _compute_max_drawdown(trades: list[dict]) -> float:
    sorted_t = sorted(trades, key=lambda t: t.get("entry_time", 0))
    running = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in sorted_t:
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
    for t in sorted(trades, key=lambda t: t.get("entry_time", 0)):
        if not t.get("is_win"):
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return max_streak


def _compute_profit_factor(trades: list[dict]) -> float:
    gross_win = sum(t.get("r_result", 0) for t in trades if t.get("is_win"))
    gross_loss = abs(sum(t.get("r_result", 0) for t in trades if not t.get("is_win")))
    if gross_loss == 0:
        return float("inf")
    return round(gross_win / gross_loss, 4)


def _compute_stability(trades: list[dict]) -> float:
    if len(trades) < 20:
        return 0.0
    r_vals = [t.get("r_result", 0) for t in sorted(trades, key=lambda t: t.get("entry_time", 0))]
    half = len(r_vals) // 2
    first_half_avg = mean(r_vals[:half]) if r_vals[:half] else 0.0
    second_half_avg = mean(r_vals[half:]) if r_vals[half:] else 0.0
    if abs(first_half_avg) < 0.001:
        return 0.0
    ratio = second_half_avg / first_half_avg if abs(first_half_avg) > 0.001 else 0.0
    return round(min(ratio, 1.0) if ratio > 0 else ratio, 4)


def _in_sample_out_of_sample(trades: list[dict]) -> tuple:
    sorted_t = sorted(trades, key=lambda t: t.get("entry_time", 0))
    split = int(len(sorted_t) * 0.7)
    is_t = sorted_t[:split]
    oos_t = sorted_t[split:]
    is_r = [t["r_result"] for t in is_t]
    oos_r = [t["r_result"] for t in oos_t]
    return {
        "trades": len(is_t),
        "avg_r": round(mean(is_r), 4) if is_r else 0.0,
        "win_rate": round(sum(1 for t in is_t if t.get("is_win")) / len(is_t) * 100, 1) if is_t else 0.0,
    }, {
        "trades": len(oos_t),
        "avg_r": round(mean(oos_r), 4) if oos_r else 0.0,
        "win_rate": round(sum(1 for t in oos_t if t.get("is_win")) / len(oos_t) * 100, 1) if oos_t else 0.0,
    }


def _unique_symbols(trades: list[dict]) -> set:
    return {t.get("symbol", "?") for t in trades}


def analyze_group(trades: list[dict], group_label: str) -> dict:
    total = len(trades)
    wins = [t for t in trades if t.get("is_win")]
    losses = [t for t in trades if not t.get("is_win")]
    expired = [t for t in trades if t.get("outcome") == "EXPIRED"]
    r_vals = [t["r_result"] for t in trades]
    is_stats, oos_stats = _in_sample_out_of_sample(trades)
    symbols = _unique_symbols(trades)

    result = {
        "group": group_label,
        "trades": total,
        "wins": len(wins),
        "losses": len(losses),
        "expired": len(expired),
        "win_rate": round(len(wins) / total * 100, 1) if total > 0 else 0.0,
        "avg_r": round(mean(r_vals), 4) if r_vals else 0.0,
        "median_r": round(median(r_vals), 4) if r_vals else 0.0,
        "total_r": round(sum(r_vals), 2) if r_vals else 0.0,
        "max_drawdown": _compute_max_drawdown(trades),
        "max_consecutive_losses": _compute_max_consecutive_losses(trades),
        "profit_factor": _compute_profit_factor(trades),
        "in_sample": is_stats,
        "out_of_sample": oos_stats,
        "stability": _compute_stability(trades),
        "unique_symbols": len(symbols),
        "symbols": sorted(symbols),
    }
    return result


def _check_overfit(grp: dict) -> dict:
    issues = []
    verdict = V_EDGE_NOT_FOUND
    recommendation = "No edge found or group too small"

    if grp["trades"] < MIN_TRADES_PER_GROUP:
        issues.append(f"insufficient trades ({grp['trades']} < {MIN_TRADES_PER_GROUP})")
    if grp["out_of_sample"]["trades"] < MIN_OOS_TRADES:
        issues.append(f"insufficient out-of-sample trades ({grp['out_of_sample']['trades']} < {MIN_OOS_TRADES})")
    if grp["in_sample"]["avg_r"] <= 0:
        issues.append(f"in-sample avg R {grp['in_sample']['avg_r']} <= 0")
    if grp["out_of_sample"]["avg_r"] <= 0:
        issues.append(f"out-of-sample avg R {grp['out_of_sample']['avg_r']} <= 0")
    if grp["avg_r"] <= 0:
        issues.append(f"overall avg R {grp['avg_r']} <= 0")
    if grp["win_rate"] < MIN_WIN_RATE:
        issues.append(f"win rate {grp['win_rate']}% < {MIN_WIN_RATE}%")
    if grp["unique_symbols"] < MIN_SYMBOLS_PER_GROUP:
        issues.append(f"only {grp['unique_symbols']} symbol(s), less than {MIN_SYMBOLS_PER_GROUP}")
    if grp["max_consecutive_losses"] > max(grp["trades"] // 5, 15):
        issues.append(f"excessive consecutive losses ({grp['max_consecutive_losses']})")

    if issues:
        verdict = V_EDGE_FRAGILE if len(issues) <= 2 else V_EDGE_NOT_FOUND
        recommendation = "; ".join(issues)
        return verdict, recommendation, issues

    # Passed all checks
    if grp["stability"] >= 0.7 and grp["profit_factor"] >= 1.5 and grp["out_of_sample"]["avg_r"] > 0.1:
        verdict = V_EDGE_STRONG
        recommendation = "Strong edge across train and validation with good stability"
    elif grp["avg_r"] > 0:
        verdict = V_EDGE_PROMISING
        recommendation = "Promising edge — continue monitoring"
    else:
        verdict = V_EDGE_FRAGILE
        recommendation = "Edge found but borderline metrics"

    return verdict, recommendation, issues


def _check_leakage(groups: list[dict]) -> dict:
    """Verify no grouping uses outcome-derived fields."""
    used_fields = set()
    for grp in groups:
        label = grp.get("group", "")
        field = label.split(":")[0] if ":" in label else ""
        if "+" in field:
            for part in field.split("+"):
                used_fields.add(part)
        else:
            used_fields.add(field)

    leaked = used_fields & BANNED_GROUPING_FIELDS
    return {
        "leakage_guard": "PASS" if not leaked else "FAIL",
        "banned_fields_removed": len(leaked) == 0,
        "banned_fields_found": sorted(leaked),
        "allowed_fields": sorted(used_fields - BANNED_GROUPING_FIELDS),
    }


def run_edge_miner() -> dict:
    trades = _read_trades()
    if not trades:
        return _empty_report("No trades found in ledger")

    # Group by each dimension
    groups = []

    # 1. symbol
    by_symbol = defaultdict(list)
    for t in trades:
        by_symbol[t.get("symbol", "?")].append(t)
    for sym, st in by_symbol.items():
        groups.append(analyze_group(st, f"symbol:{sym}"))

    # 2. timeframe
    by_tf = defaultdict(list)
    for t in trades:
        by_tf[t.get("timeframe", "?")].append(t)
    for tf, st in by_tf.items():
        groups.append(analyze_group(st, f"timeframe:{tf}"))

    # 3. direction
    by_dir = defaultdict(list)
    for t in trades:
        by_dir[t.get("direction", "?")].append(t)
    for d, st in by_dir.items():
        groups.append(analyze_group(st, f"direction:{d}"))

    # 4. pattern
    by_pat = defaultdict(list)
    for t in trades:
        by_pat[t.get("pattern", "unknown")].append(t)
    for p, st in by_pat.items():
        groups.append(analyze_group(st, f"pattern:{p}"))

    # 5. pattern + direction
    by_pd = defaultdict(list)
    for t in trades:
        by_pd[f"{t.get('pattern', '?')}+{t.get('direction', '?')}"].append(t)
    for pd, st in by_pd.items():
        groups.append(analyze_group(st, f"pattern+direction:{pd}"))

    # 6. pattern + timeframe
    by_pt = defaultdict(list)
    for t in trades:
        by_pt[f"{t.get('pattern', '?')}+{t.get('timeframe', '?')}"].append(t)
    for pt, st in by_pt.items():
        groups.append(analyze_group(st, f"pattern+timeframe:{pt}"))

    # 7. symbol + timeframe
    by_st = defaultdict(list)
    for t in trades:
        by_st[f"{t.get('symbol', '?')}+{t.get('timeframe', '?')}"].append(t)
    for st_key, st_trades in by_st.items():
        groups.append(analyze_group(st_trades, f"symbol+timeframe:{st_key}"))

    # 8. symbol + direction
    by_sd = defaultdict(list)
    for t in trades:
        by_sd[f"{t.get('symbol', '?')}+{t.get('direction', '?')}"].append(t)
    for sd, st in by_sd.items():
        groups.append(analyze_group(st, f"symbol+direction:{sd}"))

    # Run overfit check on each group
    accepted = []
    rejected = []

    for grp in groups:
        verdict, recommendation, issues = _check_overfit(grp)
        grp["verdict"] = verdict
        grp["recommendation"] = recommendation
        grp["issues"] = issues

        if verdict in (V_EDGE_PROMISING, V_EDGE_STRONG):
            accepted.append(grp)
        else:
            rejected.append(grp)

    # Sort groups
    accepted.sort(key=lambda g: g["out_of_sample"]["avg_r"], reverse=True)
    rejected.sort(key=lambda g: g["out_of_sample"]["avg_r"], reverse=True)

    # Overall verdict
    overall_verdict = V_EDGE_NOT_FOUND
    overall_recommendation = "No subgroup with statistically meaningful edge found"
    if accepted:
        best = accepted[0]
        if best["out_of_sample"]["avg_r"] > 0.15 and best["stability"] >= 0.6:
            overall_verdict = V_EDGE_PROMISING
            overall_recommendation = f"Possible niche edge in {best['group']}, review manually"
            if best["verdict"] == V_EDGE_STRONG:
                overall_verdict = V_EDGE_STRONG
                overall_recommendation = f"Strong subgroup edge in {best['group']}"
        else:
            overall_verdict = V_EDGE_FRAGILE
            overall_recommendation = f"Fragile edge in {best['group']}, needs more data"

    # Overfitting detection
    overfit_groups = []
    for grp in groups:
        if grp["in_sample"]["avg_r"] > 0 and grp["out_of_sample"]["avg_r"] <= 0:
            overfit_groups.append(grp)
    overfit_groups.sort(key=lambda g: -g["in_sample"]["avg_r"])

    report = {
        "mode": "historical_edge_miner",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "real_order": False,
        "total_trades_analyzed": len(trades),
        "total_groups_analyzed": len(groups),
        "accepted_groups": len(accepted),
        "rejected_groups": len(rejected),
        "overall_verdict": overall_verdict,
        "recommendation": overall_recommendation,
        "top_accepted": [g for g in accepted[:20]],
        "top_rejected": [g for g in rejected[:20]],
        "overfit_groups": [g for g in overfit_groups[:20]],
        "leakage_guard": _check_leakage(groups),
        "warnings": [],
    }

    if not accepted and not rejected:
        report["warnings"].append("No groups met minimum analysis criteria")
    if len(overfit_groups) > len(groups) * 0.3:
        report["warnings"].append(f"High overfit ratio: {len(overfit_groups)}/{len(groups)} groups fail OOS")
    if accepted and accepted[0]["out_of_sample"]["avg_r"] < 0.05:
        report["warnings"].append("Best accepted group has marginal OOS edge")
    if overall_verdict == V_EDGE_NOT_FOUND:
        report["warnings"].append("Strategy family should be redesigned — no edge found at any granularity")

    # Save
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2, default=str)
    _write_text_report(report)
    _save_candidates(accepted)
    return report


def _empty_report(reason: str) -> dict:
    report = {
        "mode": "historical_edge_miner",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "real_order": False,
        "total_trades_analyzed": 0,
        "total_groups_analyzed": 0,
        "accepted_groups": 0,
        "rejected_groups": 0,
        "overall_verdict": V_EDGE_NOT_FOUND,
        "recommendation": reason,
        "top_accepted": [],
        "top_rejected": [],
        "overfit_groups": [],
        "warnings": [reason],
    }
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2)
    _write_text_report(report)
    return report


def _write_text_report(report: dict):
    lines = [
        "=" * 60,
        "  HISTORICAL EDGE MINER",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  Total Trades Analyzed:  {report['total_trades_analyzed']}",
        f"  Total Groups Analyzed:  {report['total_groups_analyzed']}",
        f"  Accepted Groups:        {report['accepted_groups']}",
        f"  Rejected Groups:        {report['rejected_groups']}",
        "",
        f"  Overall Verdict:        {report['overall_verdict']}",
        f"  Recommendation:         {report['recommendation']}",
        "",
    ]

    lg = report.get("leakage_guard", {})
    if lg:
        lines += [
            "  === LEAKAGE GUARD ===",
            f"  Status:                 {lg.get('leakage_guard', '?')}",
            f"  Banned fields removed:  {'yes' if lg.get('banned_fields_removed') else 'no'}",
            f"  Allowed fields:         {', '.join(lg.get('allowed_fields', []))}",
        ]
        if lg.get("banned_fields_found"):
            lines.append(f"  BANNED FOUND:           {', '.join(lg['banned_fields_found'])}")
        lines.append("")

    if report["top_accepted"]:
        lines += ["", "  TOP 20 POSITIVE GROUPS (by OOS avg R):", ""]
        for i, g in enumerate(report["top_accepted"], 1):
            lines.append(
                f"  {i:2d}. {g['group']:45s} | "
                f"N={g['trades']:5d} | IS R={g['in_sample']['avg_r']:+.4f} | "
                f"OOS R={g['out_of_sample']['avg_r']:+.4f} | "
                f"WR={g['win_rate']:5.1f}% | "
                f"V={g['verdict']}"
            )
        lines.append("")

    if report["top_rejected"]:
        lines += ["", "  TOP 20 REJECTED GROUPS (by OOS avg R):", ""]
        for i, g in enumerate(report["top_rejected"], 1):
            lines.append(
                f"  {i:2d}. {g['group']:45s} | "
                f"N={g['trades']:5d} | IS R={g['in_sample']['avg_r']:+.4f} | "
                f"OOS R={g['out_of_sample']['avg_r']:+.4f} | "
                f"V={g['verdict']:30s} | "
                f"Issues: {g.get('recommendation', '?')[:60]}"
            )
        lines.append("")

    if report["overfit_groups"]:
        lines += ["", "  GROUPS THAT OVERFIT (positive IS, negative OOS):", ""]
        for i, g in enumerate(report["overfit_groups"], 1):
            lines.append(
                f"  {i:2d}. {g['group']:45s} | "
                f"IS R={g['in_sample']['avg_r']:+.4f} | "
                f"OOS R={g['out_of_sample']['avg_r']:+.4f}"
            )
        lines.append("")

    if report.get("warnings"):
        lines += ["", "  WARNINGS:"]
        for w in report["warnings"]:
            lines.append(f"    - {w}")
        lines.append("")

    lines += [
        "",
        "  Live trading enabled:  NO",
        "  Real order placed:     NO",
        "  BINGX_EXECUTION_MODE:  NOT SET",
        "  LIVE_TRADING_ACK:      NOT SET",
        "",
        "=" * 60,
    ]

    with open(TXT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n[JSON] {JSON_PATH}")
    print(f"[TXT]  {TXT_PATH}")


def _save_candidates(accepted: list[dict]):
    with open(CANDIDATES_PATH, "w") as f:
        for c in accepted:
            f.write(json.dumps(c, default=str) + "\n")


def main():
    report = run_edge_miner()
    return 0


if __name__ == "__main__":
    sys.exit(main())
