from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.validation_lab.performance_metrics import (
    PerformanceMetrics,
    TradeResult,
)


class WalkForwardWindowResult(BaseModel):
    window: int
    passed: bool
    expectancy_r: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0


class WalkForwardResult(BaseModel):
    windows_tested: int = 0
    windows_passed: int = 0
    windows_failed: int = 0
    consistency_score: float = 0.0
    performance_decay_detected: bool = False
    passed: bool = False
    window_results: list[WalkForwardWindowResult] = Field(default_factory=list)


class WalkForwardValidator:
    MIN_WINDOWS = 2

    def evaluate(
        self,
        window_trades: list[list[TradeResult]],
    ) -> WalkForwardResult:
        if len(window_trades) < self.MIN_WINDOWS:
            return WalkForwardResult(passed=False)

        window_results = []
        for i, trades in enumerate(window_trades):
            metrics = PerformanceMetrics.calculate(trades)
            passed = metrics.expectancy_r > 0 and metrics.profit_factor > 1.0
            window_results.append(WalkForwardWindowResult(
                window=i + 1,
                passed=passed,
                expectancy_r=metrics.expectancy_r,
                win_rate=metrics.win_rate,
                profit_factor=metrics.profit_factor,
            ))

        windows_passed = sum(1 for w in window_results if w.passed)
        windows_failed = len(window_results) - windows_passed
        consistency = windows_passed / len(window_results) if window_results else 0.0

        decay_detected = False
        if len(window_results) >= 2:
            first_half = window_results[:len(window_results) // 2]
            second_half = window_results[len(window_results) // 2:]
            avg_first = sum(w.expectancy_r for w in first_half) / len(first_half)
            avg_second = sum(w.expectancy_r for w in second_half) / len(second_half)
            if avg_second < avg_first * 0.7:
                decay_detected = True

        overall_pass = consistency >= 0.6 and not decay_detected

        return WalkForwardResult(
            windows_tested=len(window_results),
            windows_passed=windows_passed,
            windows_failed=windows_failed,
            consistency_score=round(consistency, 4),
            performance_decay_detected=decay_detected,
            passed=overall_pass,
            window_results=window_results,
        )
