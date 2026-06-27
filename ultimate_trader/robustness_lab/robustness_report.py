from typing import Any

from ultimate_trader.robustness_lab.frozen_config import config_summary
from ultimate_trader.robustness_lab.edge_stability import EdgeClassification


class RobustnessReport:
    @classmethod
    def generate(
        cls,
        frozen_cfg,
        multi_period_results: list,
        symbol_results: list,
        timeframe_results: list,
        walk_forward_windows: list,
        edge: EdgeClassification,
    ) -> str:
        lines = []
        lines.append("=" * 70)
        lines.append("ROBUSTNESS VALIDATION REPORT")
        lines.append("=" * 70)

        lines.append(f"\nA. Frozen Config\n{'-' * 40}")
        lines.append(config_summary(frozen_cfg))

        lines.append(f"\nB. BTC Multi-Period Results\n{'-' * 40}")
        if not multi_period_results:
            lines.append("  NONE")
        for pr in multi_period_results:
            lines.append(f"  {pr.label} ({pr.start} → {pr.end}): "
                         f"{pr.total_trades}t, WR {pr.win_rate*100:.1f}%, "
                         f"EV {pr.expectancy:.2f}R, PF {pr.profit_factor:.2f}, "
                         f"{pr.avg_trades_per_day:.1f}/d, DD {pr.max_drawdown:.1f}R — {pr.verdict}")

        lines.append(f"\nC. Symbol Robustness\n{'-' * 40}")
        any_symbol = any(sr.data_available for sr in symbol_results)
        if not any_symbol:
            lines.append("  No symbol data available")
        for sr in symbol_results:
            if sr.data_available:
                lines.append(f"  {sr.symbol} {sr.timeframe}: {sr.total_trades}t, "
                             f"WR {sr.win_rate*100:.1f}%, EV {sr.expectancy:.2f}R, "
                             f"PF {sr.profit_factor:.2f}, {sr.avg_trades_per_day:.1f}/d")
            else:
                lines.append(f"  {sr.symbol} {sr.timeframe}: NOT AVAILABLE ({sr.error})")

        lines.append(f"\nD. Timeframe Robustness\n{'-' * 40}")
        any_tf = any(tr.data_available for tr in timeframe_results)
        if not any_tf:
            lines.append("  No timeframe data available")
        for tr in timeframe_results:
            if tr.data_available:
                lines.append(f"  {tr.symbol} {tr.timeframe}: {tr.total_trades}t, "
                             f"WR {tr.win_rate*100:.1f}%, EV {tr.expectancy:.2f}R, "
                             f"PF {tr.profit_factor:.2f}, {tr.avg_trades_per_day:.1f}/d")
            else:
                lines.append(f"  {tr.symbol} {tr.timeframe}: NOT AVAILABLE ({tr.error})")

        lines.append(f"\nE. Walk-Forward Results\n{'-' * 40}")
        if not walk_forward_windows:
            lines.append("  No windows could be formed (insufficient data)")
        else:
            evs = [w.test_expectancy for w in walk_forward_windows]
            profitable = sum(1 for w in walk_forward_windows if w.profitable)
            lines.append(f"  Windows evaluated:  {len(walk_forward_windows)}")
            lines.append(f"  Profitable windows: {profitable}")
            lines.append(f"  Avg expectancy:     {sum(evs)/len(evs):.2f}R")
            lines.append(f"  Worst window:       {min(evs):.2f}R")
            lines.append(f"  Best window:        {max(evs):.2f}R")
            for w in walk_forward_windows:
                lines.append(f"    {w.test_start}→{w.test_end}: {w.test_trades}t, "
                             f"EV {w.test_expectancy:.2f}R, PF {w.test_profit_factor:.2f}, "
                             f"{'PROFITABLE' if w.profitable else 'LOSS'}")

        lines.append(f"\nF. Final Verdict\n{'-' * 40}")
        lines.append(f"  Classification: {edge.verdict}")
        lines.append(f"  Reason:          {edge.reason}")
        lines.append(f"  Total OOS trades: {edge.total_out_of_sample_trades}")
        if edge.windows_total > 0:
            lines.append(f"  WF windows:      {edge.windows_profitable}/{edge.windows_total} profitable")
        if edge.periods_total > 0:
            lines.append(f"  Periods:         {edge.periods_profitable}/{edge.periods_total} profitable")
        lines.append(f"  Avg EV:          {edge.avg_expectancy:.2f}R")
        lines.append(f"  Avg PF:          {edge.avg_profit_factor:.2f}")
        lines.append(f"  Max DD:          {edge.max_drawdown:.1f}R")
        lines.append("=" * 70)

        return "\n".join(lines)
