from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.historical_replay.metrics import ReplayMetrics
from ultimate_trader.historical_replay.models import ReplayConclusion, ReplayTrade
from ultimate_trader.historical_replay.parameter_sweeper import (
    ParameterSweeperReport,
)


class ReplayReport(BaseModel):
    report_id: str
    symbol: str
    timeframe: str
    start_time: datetime
    end_time: datetime
    candles_processed: int = 0
    replay_metrics: Optional[ReplayMetrics] = None
    trades: list[ReplayTrade] = Field(default_factory=list)
    rejected_signals_summary: list[dict] = Field(default_factory=list)
    engine_skip_summary: list[dict] = Field(default_factory=list)
    parameter_sweep_results: Optional[ParameterSweeperReport] = None
    final_conclusion: ReplayConclusion = ReplayConclusion.INSUFFICIENT_DATA
    explanation: str = ""

    @classmethod
    def build(
        cls,
        report_id: str,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime,
        candles_processed: int,
        metrics: ReplayMetrics,
        trades: list[ReplayTrade],
        rejected_summary: list[dict],
        engine_skip_summary: list[dict],
        sweep_report: Optional[ParameterSweeperReport] = None,
    ) -> "ReplayReport":
        conclusion, explanation = cls._determine_conclusion(metrics, sweep_report)

        return cls(
            report_id=report_id,
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
            candles_processed=candles_processed,
            replay_metrics=metrics,
            trades=trades,
            rejected_signals_summary=rejected_summary,
            engine_skip_summary=engine_skip_summary,
            parameter_sweep_results=sweep_report,
            final_conclusion=conclusion,
            explanation=explanation,
        )

    @staticmethod
    def _determine_conclusion(
        metrics: ReplayMetrics,
        sweep_report: Optional[ParameterSweeperReport],
    ) -> tuple[ReplayConclusion, str]:
        if metrics.executed_trades == 0:
            if metrics.total_signals == 0:
                return ReplayConclusion.INSUFFICIENT_DATA, "No signals generated — insufficient market data or all engines skipped"

            return ReplayConclusion.NO_EDGE, "All signals were rejected — no trades executed"

        if metrics.executed_trades < 10:
            return ReplayConclusion.NEEDS_MORE_TESTING, f"Only {metrics.executed_trades} trades executed — need at least 10 for statistical confidence"

        if sweep_report and sweep_report.overfit_warning:
            return ReplayConclusion.NEEDS_MORE_TESTING, f"Overfit risk detected: {sweep_report.overfit_reason}"

        if metrics.expectancy_r > 0 and metrics.profit_factor > 1.2 and metrics.win_rate > 0.2:
            return ReplayConclusion.EDGE_DETECTED, (
                f"Statistical edge detected: expectancy={metrics.expectancy_r:.2f}R, "
                f"profit_factor={metrics.profit_factor:.2f}, "
                f"win_rate={metrics.win_rate:.1%}, "
                f"trades={metrics.executed_trades}"
            )

        if metrics.expectancy_r <= 0:
            return ReplayConclusion.NO_EDGE, f"Negative or zero expectancy ({metrics.expectancy_r:.2f}R) — no edge detected"

        return ReplayConclusion.NO_EDGE, "Failed to meet edge criteria (expectancy>0, profit_factor>1.2, win_rate>20%)"
