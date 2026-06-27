from dataclasses import dataclass, field
from typing import Any, Optional


EDGE_CLASSES = [
    "ROBUST_EDGE",
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
    windows_profitable: int = 0
    windows_total: int = 0
    avg_expectancy: float = 0.0
    avg_profit_factor: float = 0.0
    max_drawdown: float = 0.0
    periods_profitable: int = 0
    periods_total: int = 0


class EdgeStabilityAnalyzer:
    def classify(
        self,
        multi_period_results: list,
        symbol_results: list,
        timeframe_results: list,
        walk_forward_windows: list,
        total_oos_trades: int,
    ) -> EdgeClassification:
        ec = EdgeClassification()

        if total_oos_trades < 20:
            ec.verdict = "INSUFFICIENT_TRADES"
            ec.reason = f"Only {total_oos_trades} out-of-sample trades (need ≥ 20)"
            ec.total_out_of_sample_trades = total_oos_trades
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

        ec.total_out_of_sample_trades = total_oos_trades
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

        if total_oos_trades < 100:
            if ec.avg_expectancy > 0 and ec.avg_profit_factor > 1.0:
                ec.verdict = "PROMISING_BUT_UNPROVEN"
                ec.reason = f"Only {total_oos_trades} OOS trades — promising EV={ec.avg_expectancy:.2f}R but sample too small for robust conclusion"
                return ec
            ec.verdict = "INSUFFICIENT_TRADES"
            ec.reason = f"Only {total_oos_trades} OOS trades, negative or flat EV"
            return ec

        if ec.avg_expectancy <= 0 or ec.avg_profit_factor <= 1.0:
            ec.verdict = "NO_EDGE"
            ec.reason = f"Avg EV={ec.avg_expectancy:.2f}R, PF={ec.avg_profit_factor:.2f} — no edge detected"
            return ec

        profitable_ratio = profitable_periods / max(total_periods, 1)
        wf_profitable_ratio = ec.windows_profitable / max(ec.windows_total, 1)

        if ec.max_drawdown > 5.0:
            ec.verdict = "OVERFIT_SUSPECTED"
            ec.reason = f"Excessive drawdown ({ec.max_drawdown:.1f}R) across tests"
            return ec

        if ec.avg_expectancy > 0.5 and ec.avg_profit_factor > 2.0 and profitable_ratio >= 0.6 and wf_profitable_ratio >= 0.5:
            ec.verdict = "ROBUST_EDGE"
            ec.reason = f"Stable positive results: EV={ec.avg_expectancy:.2f}R, PF={ec.avg_profit_factor:.2f}, {profitable_periods}/{total_periods} periods profitable, {ec.windows_profitable}/{ec.windows_total} WF windows profitable"
            return ec

        if profitable_ratio >= 0.4 or wf_profitable_ratio >= 0.4:
            ec.verdict = "PROMISING_BUT_UNPROVEN"
            ec.reason = f"Partial positive: EV={ec.avg_expectancy:.2f}R, PF={ec.avg_profit_factor:.2f}, {profitable_periods}/{total_periods} periods, {ec.windows_profitable}/{ec.windows_total} WF windows"
            return ec

        ec.verdict = "UNSTABLE_EDGE"
        ec.reason = f"Mixed results: EV={ec.avg_expectancy:.2f}R but most periods/windows not profitable"
        return ec
