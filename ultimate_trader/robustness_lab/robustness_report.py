from typing import Any, Optional

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
        dataset_quality_lines: Optional[list[str]] = None,
        governor_walk_forward_windows: Optional[list] = None,
        after_governor_metrics: Optional[dict] = None,
        regime_gated_metrics: Optional[dict] = None,
        regime_governor_metrics: Optional[dict] = None,
        regime_walk_forward_windows: Optional[list] = None,
        regime_governor_walk_forward_windows: Optional[list] = None,
    ) -> str:
        lines = []
        lines.append("=" * 70)
        lines.append("ROBUSTNESS VALIDATION REPORT")
        lines.append("=" * 70)

        lines.append(f"\nA. Frozen Config\n{'-' * 40}")
        lines.append(config_summary(frozen_cfg))

        if dataset_quality_lines:
            lines.append(f"\nA2. Dataset Quality\n{'-' * 40}")
            lines.extend(dataset_quality_lines)

        lines.append(f"\nB. BTC Multi-Period Results\n{'-' * 40}")
        if not multi_period_results:
            lines.append("  NONE")
        for pr in multi_period_results:
            lines.append(f"  {pr.label} ({pr.start} -> {pr.end}): "
                         f"{pr.total_trades}t, WR {pr.win_rate*100:.1f}%, "
                         f"EV {pr.expectancy:.2f}R, PF {pr.profit_factor:.2f}, "
                         f"{pr.avg_trades_per_day:.1f}/d, DD {pr.max_drawdown:.1f}R - {pr.verdict}")

        lines.append(f"\nC. Symbol Robustness\n{'-' * 40}")
        any_symbol = any(sr.data_available for sr in symbol_results)
        if not any_symbol:
            lines.append("  No symbol data available")
        for sr in symbol_results:
            if sr.data_available:
                lines.append(f"  {sr.symbol} {sr.timeframe}: {sr.total_trades}t, "
                             f"WR {sr.win_rate*100:.1f}%, EV {sr.expectancy:.2f}R, "
                             f"PF {sr.profit_factor:.2f}, {sr.avg_trades_per_day:.1f}/d, "
                             f"DD {sr.max_drawdown:.1f}R")
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
                             f"PF {tr.profit_factor:.2f}, {tr.avg_trades_per_day:.1f}/d, "
                             f"DD {tr.max_drawdown:.1f}R")
            else:
                lines.append(f"  {tr.symbol} {tr.timeframe}: NOT AVAILABLE ({tr.error})")

        lines.append(f"\nE. Walk-Forward (A+ selectivity only)\n{'-' * 40}")
        if not walk_forward_windows:
            lines.append("  No windows could be formed (insufficient data)")
        else:
            evs = [w.test_expectancy for w in walk_forward_windows]
            profitable = sum(1 for w in walk_forward_windows if w.profitable)
            lines.append(f"  Windows evaluated:  {len(walk_forward_windows)}")
            lines.append(f"  Profitable windows: {profitable}/{len(walk_forward_windows)}")
            lines.append(f"  Avg expectancy:     {sum(evs)/len(evs):.2f}R")
            lines.append(f"  Worst window:       {min(evs):.2f}R")
            lines.append(f"  Best window:        {max(evs):.2f}R")
            if walk_forward_windows:
                avg_dd = sum(w.test_max_drawdown for w in walk_forward_windows) / len(walk_forward_windows)
                lines.append(f"  Avg max drawdown:   {avg_dd:.1f}R")
            std = (sum((e - sum(evs)/len(evs))**2 for e in evs) / len(evs))**0.5 if len(evs) > 1 else 0
            stability = max(0, 100 - std * 50)
            lines.append(f"  Stability score:    {stability:.0f}%")
            lines.append(f"  Best window:        {max(evs):.2f}R")

        lines.append(f"\nE2. Walk-Forward (A+ + risk governor)\n{'-' * 40}")
        if not governor_walk_forward_windows:
            lines.append("  No governor windows evaluated")
        else:
            evs = [w.test_expectancy for w in governor_walk_forward_windows]
            profitable = sum(1 for w in governor_walk_forward_windows if w.profitable)
            blocked = sum(w.blocked_signals for w in governor_walk_forward_windows)
            lines.append(f"  Windows evaluated:  {len(governor_walk_forward_windows)}")
            lines.append(f"  Profitable windows: {profitable}/{len(governor_walk_forward_windows)}")
            lines.append(f"  Avg expectancy:     {sum(evs)/len(evs):.2f}R")
            lines.append(f"  Worst window:       {min(evs):.2f}R")
            lines.append(f"  Best window:        {max(evs):.2f}R")
            if governor_walk_forward_windows:
                avg_dd = sum(w.test_max_drawdown for w in governor_walk_forward_windows) / len(governor_walk_forward_windows)
                lines.append(f"  Avg max drawdown:   {avg_dd:.1f}R")
            lines.append(f"  Total blocked:      {blocked}")

        lines.append(f"\nE3. Walk-Forward (A+ + regime gate)\n{'-' * 40}")
        if not regime_walk_forward_windows:
            lines.append("  No regime windows evaluated")
        else:
            evs = [w.test_expectancy for w in regime_walk_forward_windows]
            profitable = sum(1 for w in regime_walk_forward_windows if w.profitable)
            blocked = sum(w.regime_blocked for w in regime_walk_forward_windows)
            lines.append(f"  Windows evaluated:  {len(regime_walk_forward_windows)}")
            lines.append(f"  Profitable windows: {profitable}/{len(regime_walk_forward_windows)}")
            lines.append(f"  Avg expectancy:     {sum(evs)/len(evs):.2f}R")
            lines.append(f"  Worst window:       {min(evs):.2f}R")
            lines.append(f"  Best window:        {max(evs):.2f}R")
            if regime_walk_forward_windows:
                avg_dd = sum(w.test_max_drawdown for w in regime_walk_forward_windows) / len(regime_walk_forward_windows)
                lines.append(f"  Avg max drawdown:   {avg_dd:.1f}R")
            lines.append(f"  Regime blocked:     {blocked}")

        lines.append(f"\nE4. Walk-Forward (A+ + regime + governor)\n{'-' * 40}")
        if not regime_governor_walk_forward_windows:
            lines.append("  No regime+gov windows evaluated")
        else:
            evs = [w.test_expectancy for w in regime_governor_walk_forward_windows]
            profitable = sum(1 for w in regime_governor_walk_forward_windows if w.profitable)
            blocked = sum(w.regime_blocked for w in regime_governor_walk_forward_windows)
            lines.append(f"  Windows evaluated:  {len(regime_governor_walk_forward_windows)}")
            lines.append(f"  Profitable windows: {profitable}/{len(regime_governor_walk_forward_windows)}")
            lines.append(f"  Avg expectancy:     {sum(evs)/len(evs):.2f}R")
            lines.append(f"  Worst window:       {min(evs):.2f}R")
            lines.append(f"  Best window:        {max(evs):.2f}R")
            if regime_governor_walk_forward_windows:
                avg_dd = sum(w.test_max_drawdown for w in regime_governor_walk_forward_windows) / len(regime_governor_walk_forward_windows)
                lines.append(f"  Avg max drawdown:   {avg_dd:.1f}R")
            lines.append(f"  Regime blocked:     {blocked}")

        lines.append(f"\nF. A+ Selectivity Final Verdict\n{'-' * 40}")
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
        if edge.max_symbol_profit_pct < 100:
            lines.append(f"  Max symbol profit: {edge.max_symbol_profit_pct:.0f}%")

        lines.append(f"\nG. A+ + Risk Governor Verdict\n{'-' * 40}")
        gov_verdict = edge.governor_verdict()
        lines.append(f"  Classification: {gov_verdict}")
        lines.append(f"  Trades after gov:  {edge.total_governor_trades}")
        lines.append(f"  EV after gov:      {edge.after_governor_ev:.2f}R")
        lines.append(f"  PF after gov:      {edge.after_governor_pf:.2f}")
        lines.append(f"  Max DD after gov:  {edge.governor_max_drawdown:.1f}R")
        lines.append(f"  Trades/day:        {edge.after_governor_trades_per_day:.1f}")

        lines.append(f"\nG2. Regime Gate Results (Full Dataset)\n{'-' * 40}")
        if regime_gated_metrics:
            lines.append(f"  Trades after gate: {edge.regime_gated_trades}")
            lines.append(f"  EV after gate:     {edge.regime_gated_ev:.2f}R")
            lines.append(f"  PF after gate:     {edge.regime_gated_pf:.2f}")
            lines.append(f"  Max DD after gate: {edge.regime_gated_dd:.1f}R")
        if regime_governor_metrics:
            lines.append(f"  Trades after both: {edge.regime_gov_trades}")
            lines.append(f"  EV after both:     {edge.regime_gov_ev:.2f}R")
            lines.append(f"  PF after both:     {edge.regime_gov_pf:.2f}")
            lines.append(f"  Max DD after both: {edge.regime_gov_dd:.1f}R")
            lines.append(f"  Regime blocked %:  {edge.regime_block_pct:.1f}%")

        lines.append(f"\nH. Evidence Summary\n{'-' * 40}")
        if edge.total_out_of_sample_trades >= 200:
            lines.append("  OOS evidence:     SUFFICIENT (200+ trades)")
        else:
            lines.append(f"  OOS evidence:     INSUFFICIENT ({edge.total_out_of_sample_trades}/200)")
        if edge.total_governor_trades >= 50:
            lines.append("  Governor evidence: SUFFICIENT (50+ trades)")
        else:
            lines.append(f"  Governor evidence: INSUFFICIENT ({edge.total_governor_trades}/50)")
        if edge.regime_gov_trades >= 20:
            lines.append("  Regime+gov evidence: SUFFICIENT (20+ trades)")
        else:
            lines.append(f"  Regime+gov evidence: INSUFFICIENT ({edge.regime_gov_trades}/20)")
        if edge.avg_profit_factor > 1.2:
            lines.append(f"  Profit factor:    PASS ({edge.avg_profit_factor:.2f} > 1.2)")
        else:
            lines.append(f"  Profit factor:    FAIL ({edge.avg_profit_factor:.2f} <= 1.2)")
        if edge.windows_total > 0:
            wf_ratio = edge.windows_profitable / edge.windows_total
            if wf_ratio >= 0.7:
                lines.append(f"  WF profitability: PASS ({edge.windows_profitable}/{edge.windows_total} >= 70%)")
            else:
                lines.append(f"  WF profitability: FAIL ({edge.windows_profitable}/{edge.windows_total} < 70%)")
        lines.append("=" * 70)

        return "\n".join(lines)
