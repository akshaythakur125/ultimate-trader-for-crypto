from dataclasses import dataclass, field
from typing import Any, Optional


EDGE_CLASSES = [
    "ROBUST_EDGE",
    "REGIME_SPECIFIC_EDGE",
    "PROMISING_BUT_UNPROVEN",
    "UNSTABLE_EDGE",
    "NO_EDGE",
    "OVERFIT_SUSPECTED",
    "INSUFFICIENT_TRADES",
]


@dataclass
class EdgeClassification:
    verdict: str = "INSUFFICIENT_TRADES"
    reason: str = ""
    total_out_of_sample_trades: int = 0
    total_governor_trades: int = 0
    windows_profitable: int = 0
    windows_total: int = 0
    avg_expectancy: float = 0.0
    avg_profit_factor: float = 0.0
    max_drawdown: float = 0.0
    governor_max_drawdown: float = 0.0
    periods_profitable: int = 0
    periods_total: int = 0
    after_governor_ev: float = 0.0
    after_governor_pf: float = 0.0
    after_governor_trades_per_day: float = 0.0
    max_symbol_profit_pct: float = 100.0
    regime_gated_ev: float = 0.0
    regime_gated_pf: float = 0.0
    regime_gated_trades: int = 0
    regime_gated_dd: float = 0.0
    regime_gov_ev: float = 0.0
    regime_gov_pf: float = 0.0
    regime_gov_trades: int = 0
    regime_gov_dd: float = 0.0
    regime_block_pct: float = 0.0

    def governor_verdict(self) -> str:
        if self.total_governor_trades < 50:
            return "INSUFFICIENT_TRADES"
        if self.after_governor_ev <= 0 or self.after_governor_pf <= 1.2:
            return "NO_EDGE"
        if self.after_governor_trades_per_day > 4:
            return "OVERTRADING"
        if self.governor_max_drawdown > 8.0:
            return "DRAWDOWN_TOO_HIGH"
        return "GOOD_RISK_PROFILE"


class EdgeStabilityAnalyzer:
    def classify(
        self,
        multi_period_results: list,
        symbol_results: list,
        timeframe_results: list,
        walk_forward_windows: list,
        total_oos_trades: int,
        after_governor_metrics: Optional[dict] = None,
        governor_walk_forward_windows: Optional[list] = None,
        max_symbol_profit_pct: float = 100.0,
        regime_gated_metrics: Optional[dict] = None,
        regime_governor_metrics: Optional[dict] = None,
    ) -> EdgeClassification:
        ec = EdgeClassification()
        ec.total_out_of_sample_trades = total_oos_trades

        if after_governor_metrics:
            ec.total_governor_trades = after_governor_metrics.get("total_trades", 0)
            ec.after_governor_ev = after_governor_metrics.get("expectancy", 0)
            ec.after_governor_pf = after_governor_metrics.get("profit_factor", 0)
            ec.after_governor_trades_per_day = after_governor_metrics.get("avg_trades_per_day", 0)
        # Compute max symbol profit concentration from symbol results if not provided
        if max_symbol_profit_pct == 100.0 and symbol_results:
            profits = []
            total = 0
            for sr in symbol_results:
                if hasattr(sr, 'data_available') and sr.data_available and hasattr(sr, 'total_trades') and sr.total_trades >= 5:
                    p = sr.expectancy * sr.total_trades
                    profits.append(p)
                    total += p
            if total > 0 and len(profits) >= 2:
                max_symbol_profit_pct = (max(profits) / total) * 100
        ec.max_symbol_profit_pct = max_symbol_profit_pct

        if total_oos_trades < 20:
            ec.verdict = "INSUFFICIENT_TRADES"
            ec.reason = f"Only {total_oos_trades} OOS trades (need >= 20 for any verdict)"
            return ec

        all_evs = []
        all_pfs = []
        all_dds = []
        profitable_periods = 0
        total_periods = 0

        for pr in multi_period_results:
            if pr.total_trades >= 5:
                all_evs.append(pr.expectancy)
                all_pfs.append(pr.profit_factor)
                all_dds.append(pr.max_drawdown)
                total_periods += 1
                if pr.expectancy > 0:
                    profitable_periods += 1

        for sr in symbol_results:
            if sr.data_available and sr.total_trades >= 5:
                all_evs.append(sr.expectancy)
                all_pfs.append(sr.profit_factor)
                all_dds.append(sr.max_drawdown)
                total_periods += 1
                if sr.expectancy > 0:
                    profitable_periods += 1

        for tr in timeframe_results:
            if tr.data_available and tr.total_trades >= 5:
                all_evs.append(tr.expectancy)
                all_pfs.append(tr.profit_factor)
                all_dds.append(tr.max_drawdown)
                total_periods += 1
                if tr.expectancy > 0:
                    profitable_periods += 1

        for w in walk_forward_windows:
            if w.test_trades >= 3:
                all_evs.append(w.test_expectancy)
                all_pfs.append(w.test_profit_factor)

        ec.windows_total = len(walk_forward_windows)
        ec.windows_profitable = sum(1 for w in walk_forward_windows if w.profitable)
        ec.periods_total = total_periods
        ec.periods_profitable = profitable_periods

        if not all_evs:
            ec.verdict = "INSUFFICIENT_TRADES"
            ec.reason = "No evaluable periods"
            return ec

        ec.avg_expectancy = sum(all_evs) / len(all_evs)
        ec.avg_profit_factor = sum(all_pfs) / len(all_pfs) if all_pfs else 0
        ec.max_drawdown = max(all_dds) if all_dds else 0

        if after_governor_metrics:
            ec.governor_max_drawdown = after_governor_metrics.get("max_drawdown", 0)

        if regime_gated_metrics:
            ec.regime_gated_ev = regime_gated_metrics.get("expectancy", 0)
            ec.regime_gated_pf = regime_gated_metrics.get("profit_factor", 0)
            ec.regime_gated_trades = regime_gated_metrics.get("total_trades", 0)
            ec.regime_gated_dd = regime_gated_metrics.get("max_drawdown", 0)

        if regime_governor_metrics:
            ec.regime_gov_ev = regime_governor_metrics.get("expectancy", 0)
            ec.regime_gov_pf = regime_governor_metrics.get("profit_factor", 0)
            ec.regime_gov_trades = regime_governor_metrics.get("total_trades", 0)
            ec.regime_gov_dd = regime_governor_metrics.get("max_drawdown", 0)
            ec.regime_block_pct = regime_governor_metrics.get("regime_block_pct", 0)

        # ---- Minimum evidence rules ----
        wf_profitable_ratio = ec.windows_profitable / max(ec.windows_total, 1)

        # NO_EDGE first — negative EV or PF <= 1.0 overrides all other checks
        if ec.avg_expectancy <= 0 or ec.avg_profit_factor <= 1.0:
            ec.verdict = "NO_EDGE"
            ec.reason = f"Avg EV={ec.avg_expectancy:.2f}R, PF={ec.avg_profit_factor:.2f}"
            return ec

        # ROBUST_EDGE
        if (total_oos_trades >= 200
                and ec.avg_expectancy > 0
                and ec.avg_profit_factor > 1.2
                and wf_profitable_ratio >= 0.7
                and max_symbol_profit_pct <= 50.0):
            if ec.max_drawdown <= 8.0:
                ec.verdict = "ROBUST_EDGE"
                ec.reason = (
                    f"Stable across {total_oos_trades} OOS trades, "
                    f"EV={ec.avg_expectancy:.2f}R, PF={ec.avg_profit_factor:.2f}, "
                    f"DD={ec.max_drawdown:.1f}R, "
                    f"WF profitable={ec.windows_profitable}/{ec.windows_total}, "
                    f"best symbol <=50% of profit"
                )
                return ec

        # REGIME_SPECIFIC_EDGE: A+ alone looks overfit, but regime gate recovers edge
        if ec.regime_gov_trades >= 20 and ec.regime_gov_ev > 0 and ec.regime_gov_pf > 1.2:
            if regime_gated_metrics and regime_gated_metrics.get("total_trades", 0) >= 50:
                ec.verdict = "REGIME_SPECIFIC_EDGE"
                ec.reason = (
                    f"A+ alone overfit ({ec.max_drawdown:.1f}R DD, "
                    f"{ec.windows_profitable}/{ec.windows_total} WF), "
                    f"but regime gate stabilizes: "
                    f"EV={ec.regime_gated_ev:.2f}R, PF={ec.regime_gated_pf:.2f}, "
                    f"DD={ec.regime_gated_dd:.1f}R, "
                    f"gov={ec.regime_gov_trades}t EV={ec.regime_gov_ev:.2f}R, "
                    f"blocked={ec.regime_block_pct:.0f}%"
                )
                return ec

        # Check high drawdown
        if ec.max_drawdown > 8.0 and total_oos_trades >= 50:
            ec.verdict = "OVERFIT_SUSPECTED"
            ec.reason = (
                f"Excessive drawdown ({ec.max_drawdown:.1f}R) across "
                f"{total_oos_trades} OOS trades"
            )
            return ec

        # Check if symbol profit concentration > 50% (only with 2+ data symbols)
        data_symbols = [s for s in symbol_results if s.data_available and s.total_trades >= 5]
        if len(data_symbols) >= 2 and max_symbol_profit_pct > 50.0 and total_oos_trades >= 50:
            ec.verdict = "OVERFIT_SUSPECTED"
            ec.reason = (
                f"Edge concentrated: one symbol contributes "
                f"{max_symbol_profit_pct:.0f}% of total profit"
            )
            return ec

        # PROMISING_BUT_UNPROVEN
        if ec.avg_expectancy > 0 and ec.avg_profit_factor > 1.2:
            if total_oos_trades < 200:
                ec.verdict = "PROMISING_BUT_UNPROVEN"
                ec.reason = (
                    f"Positive EV={ec.avg_expectancy:.2f}R, PF={ec.avg_profit_factor:.2f} "
                    f"but only {total_oos_trades} OOS trades (need >= 200)"
                )
                return ec
            if wf_profitable_ratio < 0.7:
                ec.verdict = "PROMISING_BUT_UNPROVEN"
                ec.reason = (
                    f"Positive EV={ec.avg_expectancy:.2f}R, PF={ec.avg_profit_factor:.2f} "
                    f"but only {ec.windows_profitable}/{ec.windows_total} WF windows profitable"
                )
                return ec
            if ec.max_drawdown > 5.0:
                ec.verdict = "PROMISING_BUT_UNPROVEN"
                ec.reason = (
                    f"Positive EV={ec.avg_expectancy:.2f}R but drawdown "
                    f"{ec.max_drawdown:.1f}R is elevated"
                )
                return ec

        ec.verdict = "UNSTABLE_EDGE"
        ec.reason = (
            f"Mixed results: EV={ec.avg_expectancy:.2f}R, PF={ec.avg_profit_factor:.2f}, "
            f"{profitable_periods}/{total_periods} periods profitable"
        )
        return ec


