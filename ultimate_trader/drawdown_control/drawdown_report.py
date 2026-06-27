from typing import Any

from ultimate_trader.drawdown_control.risk_governor import RiskGovernorConfig


class DrawdownReport:
    @classmethod
    def generate(
        cls,
        before_metrics: dict[str, Any],
        after_metrics: dict[str, Any],
        governor_stats: dict[str, int],
        attribution_results: list,
        largest_drawdown_episode: dict,
        loss_cluster_info: dict,
        final_verdict: str,
    ) -> str:
        lines = []
        lines.append("=" * 70)
        lines.append("DRAWDOWN CONTROL VALIDATION REPORT")
        lines.append("=" * 70)

        lines.append(f"\nA. Before Risk Governor\n{'-' * 50}")
        lines.append(f"  Trades:          {before_metrics.get('total_trades', 0)}")
        lines.append(f"  Win rate:        {before_metrics.get('win_rate', 0)*100:.1f}%")
        lines.append(f"  Expectancy:      {before_metrics.get('expectancy', 0):.2f}R")
        lines.append(f"  Profit factor:   {before_metrics.get('profit_factor', 0):.2f}")
        lines.append(f"  Max drawdown:    {before_metrics.get('max_drawdown', 0):.1f}R")
        lines.append(f"  Avg trades/day:  {before_metrics.get('avg_trades_per_day', 0):.1f}")

        lines.append(f"\nB. After Risk Governor\n{'-' * 50}")
        lines.append(f"  Trades:              {after_metrics.get('total_trades', 0)}")
        lines.append(f"  Win rate:            {after_metrics.get('win_rate', 0)*100:.1f}%")
        lines.append(f"  Expectancy:          {after_metrics.get('expectancy', 0):.2f}R")
        lines.append(f"  Profit factor:       {after_metrics.get('profit_factor', 0):.2f}")
        lines.append(f"  Max drawdown:        {after_metrics.get('max_drawdown', 0):.1f}R")
        lines.append(f"  Avg trades/day:      {after_metrics.get('avg_trades_per_day', 0):.1f}")

        lines.append(f"\nC. Governor Blocking Stats\n{'-' * 50}")
        total_blocked = sum(governor_stats.values())
        lines.append(f"  Total blocked:       {total_blocked}")
        lines.append(f"  Daily loss limit:    {governor_stats.get('daily_loss', 0)}")
        lines.append(f"  Weekly loss limit:   {governor_stats.get('weekly_loss', 0)}")
        lines.append(f"  Drawdown mode:       {governor_stats.get('drawdown_mode', 0)}")
        lines.append(f"  Rolling perf:        {governor_stats.get('rolling_perf', 0)}")
        lines.append(f"  Consecutive losses:  {governor_stats.get('consecutive_losses', 0)}")

        lines.append(f"\nD. Drawdown Attribution\n{'-' * 50}")
        if largest_drawdown_episode:
            ep = largest_drawdown_episode
            lines.append(f"  Largest DD episode:")
            lines.append(f"    Depth:     {ep.get('depth_r', 0):.1f}R")
            lines.append(f"    Period:    {ep.get('start', '')} -> {ep.get('end', '')}")
            lines.append(f"    Trades:    {ep.get('num_trades', 0)}")
            lines.append(f"    Win rate:  {ep.get('win_rate', 0)*100:.1f}%")
            lines.append(f"    Cause:     {ep.get('cause', '')}")
            lines.append(f"    Top losses: {ep.get('top_losing_trades', [])}")

        if loss_cluster_info:
            lines.append(f"\n  Loss cluster summary:")
            lines.append(f"    Max consecutive losses: {loss_cluster_info.get('max_consecutive_losses', 0)}")
            lines.append(f"    Severe clusters:        {len(loss_cluster_info.get('severe_clusters', []))}")
            wd = loss_cluster_info.get('daily_loss_summary', {})
            lines.append(f"    Worst loss day:         {wd.get('worst_day', '')} ({wd.get('worst_day_loss_r', 0):.1f}R)")
            sym_summ = loss_cluster_info.get('symbol_loss_summary', {})
            worst_sym = max(sym_summ.items(), key=lambda x: x[1]['total_loss_r']) if sym_summ else None
            if worst_sym:
                lines.append(f"    Worst symbol:           {worst_sym[0]} ({worst_sym[1]['total_loss_r']:.1f}R across {worst_sym[1]['loss_trades']} losses)")

        lines.append(f"\nE. Attribution by Symbol/Timeframe\n{'-' * 50}")
        for r in attribution_results:
            lines.append(f"  {r.symbol} {r.timeframe}: {r.trades}t, WR {r.win_rate*100:.1f}%, "
                         f"EV {r.expectancy:.2f}R, PF {r.profit_factor:.2f}, "
                         f"DD {r.max_drawdown:.1f}R, profit {r.contribution_to_profit:.0f}%, "
                         f"dd_contrib {r.contribution_to_drawdown:.0f}% - {r.reliability}")

        lines.append(f"\nF. Final Verdict\n{'-' * 50}")
        lines.append(f"  {final_verdict}")

        improvement_pct = 0
        if before_metrics.get('max_drawdown', 0) > 0:
            improvement_pct = (1 - after_metrics.get('max_drawdown', 0) / before_metrics.get('max_drawdown', 0)) * 100
        lines.append(f"\n  DD reduction:     {improvement_pct:.0f}%")
        lines.append(f"  EV after:         {after_metrics.get('expectancy', 0):.2f}R")
        lines.append(f"  PF after:         {after_metrics.get('profit_factor', 0):.2f}")
        lines.append(f"  Avg trades/day:   {after_metrics.get('avg_trades_per_day', 0):.1f}")
        lines.append("=" * 70)

        return "\n".join(lines)
