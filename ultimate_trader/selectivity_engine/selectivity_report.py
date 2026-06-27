from collections import defaultdict
from datetime import datetime
from typing import Any, Optional

from ultimate_trader.selectivity_engine.rejection_reason_analyzer import RejectionStats


class SelectivityReport:
    @classmethod
    def generate(
        cls,
        baseline: dict[str, Any],
        selective: dict[str, Any],
        rejection_stats: RejectionStats,
        daily_breakdown: dict[str, int],
        label: str = "Selective Replay",
    ) -> str:
        lines = []
        lines.append("=" * 70)
        lines.append(f"SELECTIVITY REPORT — {label}")
        lines.append("=" * 70)

        lines.append("\n--- Baseline Replay ---")
        for k, v in baseline.items():
            if isinstance(v, float):
                lines.append(f"  {k}: {v:.2f}")
            else:
                lines.append(f"  {k}: {v}")

        lines.append(f"\n--- Selective Replay ---")
        for k, v in selective.items():
            if isinstance(v, float):
                lines.append(f"  {k}: {v:.2f}")
            else:
                lines.append(f"  {k}: {v}")

        lines.append(f"\n--- Daily Trades ---")
        days_with_0 = sum(1 for c in daily_breakdown.values() if c == 0)
        days_with_1_2 = sum(1 for c in daily_breakdown.values() if 1 <= c <= 2)
        days_with_3_4 = sum(1 for c in daily_breakdown.values() if 3 <= c <= 4)
        days_above_4 = sum(1 for c in daily_breakdown.values() if c > 4)
        lines.append(f"  Days with 0 trades:       {days_with_0}")
        lines.append(f"  Days with 1-2 trades:     {days_with_1_2}")
        lines.append(f"  Days with 3-4 trades:     {days_with_3_4}")
        lines.append(f"  Days above 4 trades:      {days_above_4}")

        lines.append(f"\n--- Rejected Candidates ---")
        lines.append(f"  Low rank:           {rejection_stats.low_rank}")
        lines.append(f"  Confluence:         {rejection_stats.confluence}")
        lines.append(f"  Directional conf:   {rejection_stats.directional_confidence}")
        lines.append(f"  Conflict:           {rejection_stats.conflict}")
        lines.append(f"  Reversal risk:      {rejection_stats.reversal_risk}")
        lines.append(f"  Risk:               {rejection_stats.risk}")
        lines.append(f"  RR:                 {rejection_stats.rr}")
        lines.append(f"  Overtrading:        {rejection_stats.overtrading}")
        lines.append(f"  Cooldown:           {rejection_stats.cooldown}")

        lines.append(f"\n--- Improvement ---")
        base_trades = baseline.get("total_trades", 0)
        sel_trades = selective.get("total_trades", 0)
        reduction = ((base_trades - sel_trades) / base_trades * 100) if base_trades > 0 else 0
        lines.append(f"  Trade reduction:    {reduction:.1f}%")
        lines.append(f"  Baseline trades:    {base_trades}")
        lines.append(f"  Selective trades:   {sel_trades}")

        base_ev = baseline.get("expectancy", 0)
        sel_ev = selective.get("expectancy", 0)
        if sel_ev > base_ev:
            lines.append(f"  Expectancy change:  {base_ev:.2f}R -> {sel_ev:.2f}R (IMPROVED)")
        else:
            lines.append(f"  Expectancy change:  {base_ev:.2f}R -> {sel_ev:.2f}R (NOT IMPROVED)")

        base_pf = baseline.get("profit_factor", 0)
        sel_pf = selective.get("profit_factor", 0)
        if sel_pf > base_pf:
            lines.append(f"  Profit factor:      {base_pf:.2f} -> {sel_pf:.2f} (IMPROVED)")
        else:
            lines.append(f"  Profit factor:      {base_pf:.2f} -> {sel_pf:.2f} (NOT IMPROVED)")

        lines.append(f"\n--- Final Verdict ---")
        sel_avg_day = selective.get("avg_trades_per_day", 99)
        if sel_avg_day <= 4 and selective.get("expectancy", 0) > 0 and selective.get("profit_factor", 0) > 1.2:
            lines.append("  EDGE DETECTED — selectivity improves quality")
        elif sel_avg_day <= 4 and selective.get("expectancy", 0) > 0:
            lines.append("  WEAK EDGE — selectivity limits trades but EV is marginal")
        elif sel_avg_day <= 4:
            lines.append("  NO_EDGE — selectivity limits trades but system still negative expectancy")
        else:
            lines.append("  NO_EDGE — overtrading persists after selectivity")

        lines.append("=" * 70)
        return "\n".join(lines)
