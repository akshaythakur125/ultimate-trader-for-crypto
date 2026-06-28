"""Phase 5 — Daily trade report from forward test results.

Reads forward_test_runner output (JSON) and produces a per-day breakdown
of selected trades, rejected trades, expected RR, stop, target, and outcome.
Exports to CSV for human review.
"""

import csv, json, os
from collections import defaultdict
from datetime import datetime
from typing import Any


def generate_daily_report(
    result_path: str = "phase5_results/forward_test_result.json",
    output_dir: str = "phase5_results",
) -> dict[str, Any]:
    """Produce per-day report from forward test results.

    Args:
        result_path: Path to forward_test_result.json.
        output_dir: Directory for CSV output.

    Returns:
        Dict with per_day entries and summary stats.
    """
    if not os.path.exists(result_path):
        return {"status": "no_data", "reason": f"{result_path} not found"}

    with open(result_path) as f:
        data = json.load(f)

    if data.get("dry_run"):
        return {"status": "dry_run", "reason": "no trades executed"}

    trades = data.get("trade_diagnostics", [])
    if not trades:
        return {"status": "no_trades"}

    # Group trades by calendar day (using signal_time)
    by_day: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        ts = t.get("timestamp", "")
        day = ts[:10] if ts else "unknown"
        by_day[day].append(t)

    daily_rows = []
    day_summaries = []

    for day in sorted(by_day.keys()):
        day_trades = by_day[day]
        winners = [t for t in day_trades if t.get("net_r", 0) > 0]
        losers = [t for t in day_trades if t.get("net_r", 0) <= 0]
        day_pnl = sum(t.get("net_r", 0) for t in day_trades)
        dd_contrib = sum(t.get("net_r", 0) for t in losers)

        summary = {
            "date": day,
            "total_trades": len(day_trades),
            "winners": len(winners),
            "losers": len(losers),
            "win_rate": round(len(winners) / max(len(day_trades), 1) * 100, 1),
            "day_pnl_r": round(day_pnl, 2),
            "dd_contribution_r": round(dd_contrib, 2),
        }
        day_summaries.append(summary)

        for t in day_trades:
            daily_rows.append({
                "date": day,
                "direction": t.get("direction", ""),
                "entry_price": t.get("entry_price", ""),
                "exit_price": t.get("exit_price", ""),
                "net_r": t.get("net_r", ""),
                "exit_reason": t.get("exit_reason", ""),
                "holding_candles": t.get("holding_candles", ""),
                "window": t.get("window", ""),
            })

    csv_path = os.path.join(output_dir, "daily_report.csv")
    if daily_rows:
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=daily_rows[0].keys())
            writer.writeheader()
            writer.writerows(daily_rows)
        print(f"[DAILY REPORT] Wrote {len(daily_rows)} rows to {csv_path}", flush=True)

    summary_path = os.path.join(output_dir, "daily_summary.json")
    with open(summary_path, "w") as f:
        json.dump(day_summaries, f, indent=2, default=str)

    total_trades = len(trades)
    total_winners = sum(1 for t in trades if t.get("net_r", 0) > 0)
    total_pnl = sum(t.get("net_r", 0) for t in trades)

    report = {
        "status": "completed",
        "total_days": len(day_summaries),
        "total_trades": total_trades,
        "overall_win_rate": round(total_winners / max(total_trades, 1) * 100, 1),
        "total_pnl_r": round(total_pnl, 2),
        "day_summaries": day_summaries,
        "csv_path": csv_path if daily_rows else None,
    }
    return report
