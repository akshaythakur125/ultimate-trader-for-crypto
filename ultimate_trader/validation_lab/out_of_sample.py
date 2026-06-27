from pydantic import BaseModel

from ultimate_trader.validation_lab.performance_metrics import (
    PerformanceMetrics,
    TradeResult,
)


class OutOfSampleResult(BaseModel):
    validation_expectancy: float = 0.0
    oos_expectancy: float = 0.0
    degradation_detected: bool = False
    oos_expectancy_positive: bool = False
    oos_drawdown_excessive: bool = False
    passed: bool = False


class OutOfSampleValidator:
    MAX_DRAWDOWN_R = 10.0

    def evaluate(
        self,
        validation_trades: list[TradeResult],
        out_of_sample_trades: list[TradeResult],
    ) -> OutOfSampleResult:
        val_metrics = PerformanceMetrics.calculate(validation_trades)
        oos_metrics = PerformanceMetrics.calculate(out_of_sample_trades)

        degradation = False
        if val_metrics.expectancy_r > 0 and oos_metrics.expectancy_r < 0:
            degradation = True
        if val_metrics.expectancy_r > 0 and oos_metrics.expectancy_r < val_metrics.expectancy_r * 0.5:
            degradation = True

        oos_positive = oos_metrics.expectancy_r > 0
        oos_dd_excessive = oos_metrics.max_drawdown_r > self.MAX_DRAWDOWN_R

        passed = oos_positive and not oos_dd_excessive and not degradation

        return OutOfSampleResult(
            validation_expectancy=round(val_metrics.expectancy_r, 4),
            oos_expectancy=round(oos_metrics.expectancy_r, 4),
            degradation_detected=degradation,
            oos_expectancy_positive=oos_positive,
            oos_drawdown_excessive=oos_dd_excessive,
            passed=passed,
        )
