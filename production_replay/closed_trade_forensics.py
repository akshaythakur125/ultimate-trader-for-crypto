"""Closed trade forensic brain and pattern memory.

Analyzes every closed paper trade and learns which patterns, symbols,
directions, and market conditions are working or failing.

This phase is purely observational — it does NOT:
- Change live trading status
- Place real orders
- Auto-modify strategy rules

It only observes, scores, and reports.
"""

import json, os, sys
from datetime import datetime, timezone
from statistics import mean
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")

TRADES_LEDGER = os.path.join(STATE_DIR, "paper_trades.jsonl")
PATTERN_MEMORY_LEDGER = os.path.join(STATE_DIR, "pattern_memory.jsonl")
OUTCOME_PATH = os.path.join(RESULTS_DIR, "paper_outcome_report.json")
EVIDENCE_PATH = os.path.join(RESULTS_DIR, "strategy_evidence_report.json")
HOURLY_PATH = os.path.join(RESULTS_DIR, "hourly_status.json")
ROTATION_PATH = os.path.join(RESULTS_DIR, "candidate_rotation_report.json")
JSON_PATH = os.path.join(RESULTS_DIR, "pattern_memory_report.json")
TXT_PATH = os.path.join(RESULTS_DIR, "pattern_memory_report.txt")

VERDICT_INSUFFICIENT = "LEARNING_INSUFFICIENT_DATA"
VERDICT_PROMISING = "PATTERN_PROMISING"
VERDICT_WEAK = "PATTERN_WEAK"
VERDICT_BLOCK = "PATTERN_BLOCK_CANDIDATE"


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


def _compute_holding_hours(opened_at: str | None, closed_at: str | None) -> float | None:
    if not opened_at or not closed_at:
        return None
    try:
        open_dt = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
        close_dt = datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
        return round((close_dt - open_dt).total_seconds() / 3600, 2)
    except (ValueError, TypeError):
        return None


def _stop_quality(stop: float, entry: float) -> str:
    if not stop or not entry:
        return "unknown"
    distance_pct = abs(stop - entry) / entry * 100
    if distance_pct < 0.5:
        return "too_tight"
    if distance_pct > 5:
        return "too_wide"
    return "acceptable"


def _target_quality(target: float, entry: float) -> str:
    if not target or not entry:
        return "unknown"
    distance_pct = abs(target - entry) / entry * 100
    if distance_pct > 20:
        return "too_ambitious"
    return "realistic"


def _exit_reason_clean(reason: str | None) -> str:
    if not reason:
        return "UNKNOWN"
    r = reason.upper()
    if "TARGET" in r:
        return "TARGET_HIT"
    if "STOP" in r:
        return "STOP_HIT"
    if "MANUAL" in r:
        return "MANUAL_CLOSE"
    if "EXPIR" in r:
        return "EXPIRED"
    if "INVALID" in r:
        return "INVALID"
    return reason.upper()


def extract_trade_analyses(trades: list[dict]) -> list[dict]:
    """Extract 20-point forensic analysis for each closed trade."""
    closed = [
        t for t in trades
        if t.get("status") == "PAPER_CLOSED" and t.get("realized_pnl") is not None
    ]
    analyses = []
    for t in closed:
        pnl = float(t.get("realized_pnl", 0) or 0)
        risk = float(t.get("risk", 0) or 0)
        r = _r_multiple(pnl, risk)
        entry = float(t.get("entry", 0) or 0)
        stop = float(t.get("stop", 0) or 0)
        target = float(t.get("target", 0) or 0)
        exit_price = float(t.get("exit_price", 0) or 0)
        direction = t.get("side", "UNKNOWN")

        analysis = {
            "symbol": t.get("symbol", "?"),
            "direction": direction,
            "entry": entry,
            "stop": stop,
            "target": target,
            "exit_price": exit_price,
            "exit_reason": _exit_reason_clean(t.get("exit_reason")),
            "r_result": r,
            "pnl": pnl,
            "rr_at_entry": float(t.get("rr", 0) or 0),
            "thesis_score": t.get("thesis_score"),
            "trigger_source": t.get("source", "unknown"),
            "pattern": t.get("pattern") or t.get("thesis"),
            "timeframe": t.get("timeframe"),
            "holding_hours": _compute_holding_hours(t.get("opened_at"), t.get("closed_at")),
            "max_favorable_excursion": t.get("max_favorable_excursion"),
            "max_adverse_excursion": t.get("max_adverse_excursion"),
            "entry_timing": "unknown",
            "stop_quality": _stop_quality(stop, entry),
            "target_quality": _target_quality(target, entry),
            "win": pnl > 0,
        }
        analyses.append(analysis)
    return analyses


def _group_and_score(groups: dict) -> dict:
    result = {}
    for key, group in sorted(groups.items()):
        r_vals = [a["r_result"] for a in group]
        avg_r = mean(r_vals) if r_vals else 0.0
        wins = sum(1 for a in group if a["win"])
        result[key] = {
            "trades": len(group),
            "wins": wins,
            "losses": len(group) - wins,
            "win_rate": round(wins / len(group) * 100, 1) if group else 0.0,
            "avg_r": round(avg_r, 2),
            "total_pnl": round(sum(a["pnl"] for a in group), 4),
        }
    return result


def _compute_consecutive_streak(analyses: list[dict], win: bool) -> int:
    streak = 0
    for a in analyses:
        if a["win"] == win:
            streak += 1
        else:
            streak = 0
    return streak


def build_pattern_memory(analyses: list[dict]) -> dict:
    """Build pattern memory summaries by symbol, direction, trigger, etc."""
    memory = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "pattern_memory",
        "research_only": True,
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "real_order": False,
        "total_analyzed": len(analyses),
        "by_symbol": {},
        "by_direction": {},
        "by_pattern": {},
        "by_trigger": {},
        "by_rr_bucket": {},
        "by_thesis_score_bucket": {},
        "warnings": [],
        "best_pattern": None,
        "worst_pattern": None,
        "best_symbol": None,
        "worst_symbol": None,
        "learning_verdict": VERDICT_INSUFFICIENT,
        "recommendation": "keep watching",
        "long_short_summary": {},
    }

    if not analyses:
        return memory

    # Group by symbol
    sym_groups = defaultdict(list)
    for a in analyses:
        sym_groups[a["symbol"]].append(a)
    memory["by_symbol"] = _group_and_score(sym_groups)

    # Group by direction
    dir_groups = defaultdict(list)
    for a in analyses:
        dir_groups[a["direction"]].append(a)
    memory["by_direction"] = _group_and_score(dir_groups)

    # Group by pattern
    pat_groups = defaultdict(list)
    for a in analyses:
        pat = a.get("pattern") or "unknown"
        pat_groups[pat].append(a)
    memory["by_pattern"] = _group_and_score(pat_groups)

    # Group by trigger source
    trig_groups = defaultdict(list)
    for a in analyses:
        trig = a.get("trigger_source") or "unknown"
        trig_groups[trig].append(a)
    memory["by_trigger"] = _group_and_score(trig_groups)

    # RR buckets
    rr_buckets = {"0-1": [], "1-2": [], "2-4": [], "4-6": [], "6-10": [], "10+": []}
    for a in analyses:
        rr = float(a.get("rr_at_entry", 0) or 0)
        if rr < 1:
            rr_buckets["0-1"].append(a)
        elif rr < 2:
            rr_buckets["1-2"].append(a)
        elif rr < 4:
            rr_buckets["2-4"].append(a)
        elif rr < 6:
            rr_buckets["4-6"].append(a)
        elif rr < 10:
            rr_buckets["6-10"].append(a)
        else:
            rr_buckets["10+"].append(a)
    memory["by_rr_bucket"] = _group_and_score(rr_buckets)

    # Best/worst by symbol
    sym_stats = memory["by_symbol"]
    if sym_stats:
        best_sym = max(sym_stats, key=lambda s: sym_stats[s]["avg_r"])
        worst_sym = min(sym_stats, key=lambda s: sym_stats[s]["avg_r"])
        memory["best_symbol"] = {"symbol": best_sym, **sym_stats[best_sym]}
        memory["worst_symbol"] = {"symbol": worst_sym, **sym_stats[worst_sym]}

    # Best/worst by pattern
    pat_stats = memory["by_pattern"]
    if pat_stats:
        best_pat = max(pat_stats, key=lambda p: pat_stats[p]["avg_r"])
        worst_pat = min(pat_stats, key=lambda p: pat_stats[p]["avg_r"])
        memory["best_pattern"] = {"pattern": best_pat, **pat_stats[best_pat]}
        memory["worst_pattern"] = {"pattern": worst_pat, **pat_stats[worst_pat]}

    # Long/short summary
    dir_stats = memory["by_direction"]
    long_s = dir_stats.get("LONG", {})
    short_s = dir_stats.get("SHORT", {})
    memory["long_short_summary"] = {
        "long_trades": long_s.get("trades", 0),
        "long_avg_r": long_s.get("avg_r", 0),
        "long_win_rate": long_s.get("win_rate", 0),
        "short_trades": short_s.get("trades", 0),
        "short_avg_r": short_s.get("avg_r", 0),
        "short_win_rate": short_s.get("win_rate", 0),
    }

    # Warnings
    max_consec_losses = _compute_consecutive_streak(analyses, win=False)
    if max_consec_losses >= 10:
        memory["warnings"].append(
            f"repeated loser: {max_consec_losses} consecutive losses"
        )

    max_consec_wins = _compute_consecutive_streak(analyses, win=True)
    if max_consec_wins >= 5:
        memory["warnings"].append(
            f"repeated winner: {max_consec_wins} consecutive wins (possible overfitting)"
        )

    sym_counts = {s: len(g) for s, g in sym_groups.items()}
    for sym, count in sym_counts.items():
        if count > len(analyses) * 0.5 and len(analyses) > 10:
            memory["warnings"].append(
                f"same-symbol bias: {sym} has {count}/{len(analyses)} trades ({count/len(analyses)*100:.0f}%)"
            )

    total_dir = long_s.get("trades", 0) + short_s.get("trades", 0)
    if total_dir > 10:
        long_pct = long_s.get("trades", 0) / total_dir * 100 if total_dir else 0
        short_pct = short_s.get("trades", 0) / total_dir * 100 if total_dir else 0
        if long_pct > 80:
            memory["warnings"].append(
                f"long/short imbalance: {long_pct:.0f}% long, only {short_pct:.0f}% short"
            )
        elif short_pct > 80:
            memory["warnings"].append(
                f"long/short imbalance: {short_pct:.0f}% short, only {long_pct:.0f}% long"
            )

    # Verdict system
    closed_count = len(analyses)
    if closed_count < 10:
        memory["learning_verdict"] = VERDICT_INSUFFICIENT
        memory["recommendation"] = "keep watching"
    else:
        pattern_verdicts = {}
        for pat, stats in pat_stats.items():
            if stats["trades"] >= 10 and stats["avg_r"] < -0.5:
                pattern_verdicts[pat] = VERDICT_BLOCK
            elif stats["trades"] >= 5 and stats["avg_r"] <= 0:
                pattern_verdicts[pat] = VERDICT_WEAK
            elif stats["trades"] >= 5 and stats["avg_r"] > 0:
                pattern_verdicts[pat] = VERDICT_PROMISING

        symbol_verdicts = {}
        for sym, stats in sym_stats.items():
            if stats["trades"] >= 10 and stats["avg_r"] < -0.5:
                symbol_verdicts[sym] = VERDICT_BLOCK
            elif stats["trades"] >= 5 and stats["avg_r"] <= 0:
                symbol_verdicts[sym] = VERDICT_WEAK
            elif stats["trades"] >= 5 and stats["avg_r"] > 0:
                symbol_verdicts[sym] = VERDICT_PROMISING

        memory["pattern_verdicts"] = pattern_verdicts
        memory["symbol_verdicts"] = symbol_verdicts

        block_pat = any(v == VERDICT_BLOCK for v in pattern_verdicts.values())
        weak_pat = any(v == VERDICT_WEAK for v in pattern_verdicts.values())
        prom_pat = any(v == VERDICT_PROMISING for v in pattern_verdicts.values())
        block_sym = any(v == VERDICT_BLOCK for v in symbol_verdicts.values())
        weak_sym = any(v == VERDICT_WEAK for v in symbol_verdicts.values())
        prom_sym = any(v == VERDICT_PROMISING for v in symbol_verdicts.values())

        if block_pat or block_sym:
            memory["learning_verdict"] = VERDICT_BLOCK
            memory["recommendation"] = "block candidate for review"
        elif weak_pat or weak_sym:
            memory["learning_verdict"] = VERDICT_WEAK
            memory["recommendation"] = "reduce priority"
        elif prom_pat or prom_sym:
            memory["learning_verdict"] = VERDICT_PROMISING
            memory["recommendation"] = "promote for review"
        else:
            memory["learning_verdict"] = VERDICT_INSUFFICIENT
            memory["recommendation"] = "keep watching"

    return memory


def run_forensics() -> dict:
    """Main entry point — read data, analyze, write reports."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)

    trades = _read_ledger(TRADES_LEDGER)
    outcome = _read_json(OUTCOME_PATH)
    evidence = _read_json(EVIDENCE_PATH)

    analyses = extract_trade_analyses(trades)
    memory = build_pattern_memory(analyses)

    # Merge thesis performance from evidence report if available
    if evidence and evidence.get("thesis_performance"):
        memory["thesis_performance"] = evidence["thesis_performance"]

    with open(JSON_PATH, "w") as f:
        json.dump(memory, f, indent=2)

    _write_text_report(memory)
    _append_to_ledger(memory)
    return memory


def _write_text_report(memory: dict):
    lines = [
        "=" * 60,
        "  TRADER BRAIN / PATTERN MEMORY",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  Closed Trades Analyzed:  {memory['total_analyzed']}",
        f"  Learning Verdict:        {memory['learning_verdict']}",
        f"  Recommendation:          {memory['recommendation']}",
        "",
    ]

    if memory.get("best_pattern"):
        bp = memory["best_pattern"]
        lines += [
            "  BEST PATTERN:",
            f"    {bp['pattern']}: {bp['trades']} trades, avg R {bp['avg_r']}, "
            f"WR {bp['win_rate']}%, P&L {bp['total_pnl']:.2f} USDT",
            "",
        ]

    if memory.get("worst_pattern"):
        wp = memory["worst_pattern"]
        lines += [
            "  WORST PATTERN:",
            f"    {wp['pattern']}: {wp['trades']} trades, avg R {wp['avg_r']}, "
            f"WR {wp['win_rate']}%, P&L {wp['total_pnl']:.2f} USDT",
            "",
        ]

    if memory.get("best_symbol"):
        bs = memory["best_symbol"]
        lines += [
            "  BEST SYMBOL:",
            f"    {bs['symbol']}: {bs['trades']} trades, avg R {bs['avg_r']}, "
            f"WR {bs['win_rate']}%, P&L {bs['total_pnl']:.2f} USDT",
            "",
        ]

    if memory.get("worst_symbol"):
        ws = memory["worst_symbol"]
        lines += [
            "  WORST SYMBOL:",
            f"    {ws['symbol']}: {ws['trades']} trades, avg R {ws['avg_r']}, "
            f"WR {ws['win_rate']}%, P&L {ws['total_pnl']:.2f} USDT",
            "",
        ]

    ls = memory.get("long_short_summary", {})
    lines += [
        "  LONG vs SHORT EDGE:",
        f"    LONG:  {ls.get('long_trades', 0)} trades, avg R {ls.get('long_avg_r', 0)}, "
        f"WR {ls.get('long_win_rate', 0)}%",
        f"    SHORT: {ls.get('short_trades', 0)} trades, avg R {ls.get('short_avg_r', 0)}, "
        f"WR {ls.get('short_win_rate', 0)}%",
        "",
    ]

    if memory.get("by_trigger"):
        lines += ["  PERFORMANCE BY TRIGGER:"]
        for trig, stats in sorted(memory["by_trigger"].items()):
            lines.append(
                f"    {trig}: {stats['trades']} trades, avg R {stats['avg_r']}, "
                f"WR {stats['win_rate']}%"
            )
        lines += [""]

    if memory.get("by_rr_bucket"):
        lines += ["  PERFORMANCE BY RR BUCKET:"]
        for bucket, stats in sorted(memory["by_rr_bucket"].items()):
            lines.append(
                f"    RR {bucket}: {stats['trades']} trades, avg R {stats['avg_r']}, "
                f"WR {stats['win_rate']}%"
            )
        lines += [""]

    if memory.get("warnings"):
        lines += ["  WARNINGS:"]
        for w in memory["warnings"]:
            lines.append(f"    - {w}")
        lines += [""]

    if not memory.get("warnings") and memory["total_analyzed"] > 0:
        lines += ["  WARNINGS: None", ""]

    lines += [
        "=" * 60,
    ]

    with open(TXT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n[JSON] {JSON_PATH}")
    print(f"[TXT]  {TXT_PATH}")


def _append_to_ledger(memory: dict):
    entry = {
        "timestamp": memory["timestamp"],
        "total_analyzed": memory["total_analyzed"],
        "learning_verdict": memory["learning_verdict"],
        "recommendation": memory["recommendation"],
        "best_pattern": memory.get("best_pattern"),
        "worst_pattern": memory.get("worst_pattern"),
        "best_symbol": memory.get("best_symbol"),
        "worst_symbol": memory.get("worst_symbol"),
        "warning_count": len(memory.get("warnings", [])),
    }
    with open(PATTERN_MEMORY_LEDGER, "a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[LEDGER] {PATTERN_MEMORY_LEDGER}")


def main():
    memory = run_forensics()
    return 0


if __name__ == "__main__":
    sys.exit(main())
