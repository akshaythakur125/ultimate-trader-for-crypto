"""Phase 5 — Kill-switch monitor for forward/paper trading.

Continuously monitors trailing performance metrics and triggers a kill if
critical thresholds are breached. Designed to be called at the end of each
trading day or after each trade batch.

Kill conditions:
1. DD exceeds EMERGENCY_STOP (12.0R) — immediate kill.
2. PF < 1.2 over trailing 25 trades.
3. WR < 35% over trailing 25 trades.
4. 3 consecutive max-loss days (daily loss exceeds max daily loss threshold).

Kill = halt all execution, log report, no further trades allowed until
manual review.
"""

import json, os
from datetime import datetime
from typing import Any

EMERGENCY_STOP_R = 12.0
TRAILING_WINDOW = 25
MIN_PF = 1.2
MIN_WR = 35.0
MAX_CONSECUTIVE_BAD_DAYS = 3
MAX_DAILY_LOSS_R = 4.0


def check_kill_switch(
    trades: list[dict[str, Any]] | None = None,
    result_path: str | None = None,
    output_dir: str = "phase5_results",
) -> dict[str, Any]:
    """Evaluate kill-switch conditions on trade data.

    Args:
        trades: List of trade diagnostic dicts (with net_r, timestamp, etc).
        result_path: Alternative to trades; loads from JSON file.
        output_dir: Directory for kill-switch report.

    Returns:
        Dict with kill_triggered (bool), reasons, and per-condition status.
    """
    if trades is None and result_path:
        if os.path.exists(result_path):
            with open(result_path) as f:
                data = json.load(f)
            trades = data.get("trade_diagnostics", [])
        else:
            return {"kill_triggered": False, "reason": "no data"}

    if not trades:
        return {"kill_triggered": False, "reason": "no trades to evaluate"}

    conditions = {}
    kill_reasons = []

    # Condition 1: Cumulative DD
    cum = 0
    peak = 0
    dd = 0
    for t in trades:
        r_val = t.get("net_r", 0)
        cum += r_val
        peak = max(peak, cum)
        dd = max(dd, peak - cum)

    conditions["max_drawdown"] = {
        "value": round(dd, 2),
        "threshold": EMERGENCY_STOP_R,
        "triggered": dd >= EMERGENCY_STOP_R,
    }
    if dd >= EMERGENCY_STOP_R:
        kill_reasons.append(f"DD {dd:.1f}R >= {EMERGENCY_STOP_R}R emergency stop")

    # Condition 2: Trailing PF
    trailing = trades[-TRAILING_WINDOW:] if len(trades) >= TRAILING_WINDOW else trades
    trailing_winners = [t for t in trailing if t.get("net_r", 0) > 0]
    trailing_losers = [t for t in trailing if t.get("net_r", 0) <= 0]
    gross_win = sum(t.get("net_r", 0) for t in trailing_winners)
    gross_loss = abs(sum(t.get("net_r", 0) for t in trailing_losers))
    pf = gross_win / max(gross_loss, 0.001)
    trailing_wr = len(trailing_winners) / max(len(trailing), 1) * 100

    conditions["trailing_pf"] = {
        "value": round(pf, 2),
        "threshold": MIN_PF,
        "window": len(trailing),
        "triggered": pf < MIN_PF,
    }
    if pf < MIN_PF:
        kill_reasons.append(f"PF {pf:.2f} < {MIN_PF} over trailing {len(trailing)} trades")

    # Condition 3: Trailing WR
    conditions["trailing_wr"] = {
        "value": round(trailing_wr, 1),
        "threshold": MIN_WR,
        "window": len(trailing),
        "triggered": trailing_wr < MIN_WR,
    }
    if trailing_wr < MIN_WR:
        kill_reasons.append(f"WR {trailing_wr:.1f}% < {MIN_WR}% over trailing {len(trailing)} trades")

    # Condition 4: Consecutive bad days
    # Group by calendar day, check days with loss > MAX_DAILY_LOSS_R
    from collections import defaultdict
    by_day: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        ts = t.get("timestamp", "")
        day = ts[:10] if ts else "unknown"
        by_day[day].append(t)

    bad_days = 0
    max_bad_in_row = 0
    for day in sorted(by_day.keys()):
        day_pnl = sum(t.get("net_r", 0) for t in by_day[day])
        if day_pnl < -MAX_DAILY_LOSS_R:
            bad_days += 1
            max_bad_in_row = max(max_bad_in_row, bad_days)
        else:
            bad_days = 0

    conditions["consecutive_bad_days"] = {
        "value": max_bad_in_row,
        "threshold": MAX_CONSECUTIVE_BAD_DAYS,
        "triggered": max_bad_in_row >= MAX_CONSECUTIVE_BAD_DAYS,
    }
    if max_bad_in_row >= MAX_CONSECUTIVE_BAD_DAYS:
        kill_reasons.append(f"{max_bad_in_row} consecutive bad days (daily loss > {MAX_DAILY_LOSS_R}R)")

    kill_triggered = len(kill_reasons) > 0

    report = {
        "kill_triggered": kill_triggered,
        "timestamp": datetime.now().isoformat(),
        "conditions": conditions,
        "kill_reasons": kill_reasons,
        "total_trades_evaluated": len(trades),
    }

    if kill_triggered:
        print("[KILL SWITCH] *** KILL TRIGGERED ***", flush=True)
        for r in kill_reasons:
            print(f"  KILL: {r}", flush=True)
    else:
        print("[KILL SWITCH] All conditions nominal.", flush=True)

    path = os.path.join(output_dir, "kill_switch_report.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    return report
