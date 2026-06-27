from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.validation_lab.performance_metrics import (
    PerformanceMetrics,
    TradeResult,
)


class SensitivityResult(BaseModel):
    scenarios_tested: int = 0
    scenarios_passed: int = 0
    fragile_parameters: list[str] = Field(default_factory=list)
    robustness_score: float = 0.0
    passed: bool = False


class SensitivityAnalysis:
    def analyze(
        self,
        base_trades: list[TradeResult],
    ) -> SensitivityResult:
        base_metrics = PerformanceMetrics.calculate(base_trades)
        total_scenarios = 0
        passed_scenarios = 0
        fragile = []

        scenarios = [
            ("Higher fees (2x)", self._apply_higher_fees, base_trades),
            ("Higher slippage (2x)", self._apply_higher_slippage, base_trades),
            ("Lower win rate (-10%)", self._apply_lower_win_rate, base_trades),
            ("Lower RR (-20%)", self._apply_lower_rr, base_trades),
        ]

        for name, fn, trades in scenarios:
            total_scenarios += 1
            modified = fn(trades)
            modified_metrics = PerformanceMetrics.calculate(modified)
            if modified_metrics.expectancy_r > 0 and modified_metrics.profit_factor > 1.0:
                passed_scenarios += 1
            else:
                fragile.append(name)

        robustness = passed_scenarios / total_scenarios if total_scenarios > 0 else 0.0
        passed = robustness >= 0.75

        return SensitivityResult(
            scenarios_tested=total_scenarios,
            scenarios_passed=passed_scenarios,
            fragile_parameters=fragile,
            robustness_score=round(robustness, 4),
            passed=passed,
        )

    def _apply_higher_fees(self, trades: list[TradeResult]) -> list[TradeResult]:
        result = []
        for t in trades:
            ct = t.model_copy(deep=True)
            ct.fees_r *= 2
            ct.net_r = ct.gross_r - ct.fees_r - ct.slippage_r - ct.funding_r
            result.append(ct)
        return result

    def _apply_higher_slippage(self, trades: list[TradeResult]) -> list[TradeResult]:
        result = []
        for t in trades:
            ct = t.model_copy(deep=True)
            ct.slippage_r *= 2
            ct.net_r = ct.gross_r - ct.fees_r - ct.slippage_r - ct.funding_r
            result.append(ct)
        return result

    def _apply_lower_win_rate(self, trades: list[TradeResult]) -> list[TradeResult]:
        result = []
        wins = [t for t in trades if t.net_r > 0]
        losses = [t for t in trades if t.net_r <= 0]
        num_to_flip = max(1, len(wins) // 10)
        for i, t in enumerate(wins):
            if i < num_to_flip:
                flipped = t.model_copy(deep=True)
                flipped.net_r = -abs(flipped.net_r)
                result.append(flipped)
            else:
                result.append(t.model_copy(deep=True))
        for t in losses:
            result.append(t.model_copy(deep=True))
        return result

    def _apply_lower_rr(self, trades: list[TradeResult]) -> list[TradeResult]:
        result = []
        for t in trades:
            ct = t.model_copy(deep=True)
            if ct.net_r > 0:
                ct.net_r *= 0.8
            result.append(ct)
        return result
