"""Phase 5 — Risk report from forward test results.

Computes per-window and cumulative risk metrics:
- Max daily loss (R)
- Max consecutive losses
- Max drawdown (R)
- Risk per trade (stop_dist / entry, in bps)
- Current drawdown status vs RiskGovernor limits

Flags warnings when thresholds are approached.
"""

import json, os
from collections import defaultdict
from typing import Any

# RiskGovernor thresholds (from Phase 3)
DRAWDOWN_LIMIT_R = 8.0
EMERGENCY_STOP_R = 12.0


def generate_risk_report(
    result_path: str = "phase5_results/forward_test_result.json",
    output_dir: str = "phase5_results",
) -> dict[str, Any]:
    """Compute risk metrics from forward test results.

    Args:
        result_path: Path to forward_test_result.json.
        output_dir: Directory for report output.

    Returns:
        Dict with window_risk, cumulative_risk, and warnings.
    """
    if not os.path.exists(result_path):
        return {"status": "no_data", "reason": f"{result_path} not found"}

    with open(result_path) as f:
        data = json.load(f)

    if data.get("dry_run"):
        return {"status": "dry_run"}

    trades = data.get("trade_diagnostics", [])
    window_metrics = data.get("window_metrics", [])

    if not trades:
        return {"status": "no_trades"}

    # Per-window risk
    by_window: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        by_window[t.get("window", "unknown")].append(t)

    window_risk = []
    for w, wt in sorted(by_window.items()):
        tot = len(wt)
        losers = [t for t in wt if t.get("net_r", 0) <= 0]
        winners = [t for t in wt if t.get("net_r", 0) > 0]
        max_loss = min((t.get("net_r", 0) for t in wt), default=0)
        best_win = max((t.get("net_r", 0) for t in wt), default=0)

        cum = 0
        peak = 0
        dd = 0
        for t in wt:
            cum += t.get("net_r", 0)
            peak = max(peak, cum)
            dd = max(dd, peak - cum)

        wr = len(winners) / max(tot, 1) * 100
        pnl = sum(t.get("net_r", 0) for t in wt)

        window_risk.append({
            "window": w,
            "total_trades": tot,
            "win_rate": round(wr, 1),
            "pnl_r": round(pnl, 2),
            "max_drawdown_r": round(dd, 2),
            "max_loss_r": round(max_loss, 2),
            "best_win_r": round(best_win, 2),
            "consecutive_losses": _max_consecutive_losses(wt),
        })

    # Cumulative risk
    all_net = [t.get("net_r", 0) for t in trades]
    cum_pnl = sum(all_net)
    cum_peak = 0
    cum_dd = 0
    running = 0
    for r_val in all_net:
        running += r_val
        cum_peak = max(cum_peak, running)
        cum_dd = max(cum_dd, cum_peak - running)

    cumulative_risk = {
        "total_trades": len(trades),
        "total_pnl_r": round(cum_pnl, 2),
        "max_drawdown_r": round(cum_dd, 2),
        "max_consecutive_losses": _max_consecutive_losses(trades),
        "avg_risk_per_trade_r": round(abs(sum(min(r, 0) for r in all_net)) / max(len(trades), 1), 3),
    }

    # Warnings
    warnings = []
    if cum_dd > DRAWDOWN_LIMIT_R:
        warnings.append(f"DRAWDOWN_WARNING: {cum_dd:.1f}R exceeds {DRAWDOWN_LIMIT_R}R limit")
    if cum_dd > EMERGENCY_STOP_R * 0.8:
        warnings.append(f"EMERGENCY_APPROACHING: {cum_dd:.1f}R is {cum_dd/EMERGENCY_STOP_R*100:.0f}% of {EMERGENCY_STOP_R}R emergency stop")
    if cumulative_risk["max_consecutive_losses"] >= 5:
        warnings.append(f"CONSECUTIVE_LOSS_WARNING: {cumulative_risk['max_consecutive_losses']} consecutive losses")

    report = {
        "status": "completed",
        "window_risk": window_risk,
        "cumulative_risk": cumulative_risk,
        "warnings": warnings,
    }

    path = os.path.join(output_dir, "risk_report.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"[RISK REPORT] Saved to {path}", flush=True)
    for w in warnings:
        print(f"  WARNING: {w}", flush=True)

    return report


def _max_consecutive_losses(trades: list[dict]) -> int:
    max_cl = 0
    current = 0
    for t in trades:
        if t.get("net_r", 0) <= 0:
            current += 1
            max_cl = max(max_cl, current)
        else:
            current = 0
    return max_cl
