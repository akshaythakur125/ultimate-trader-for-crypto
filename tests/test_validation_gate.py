from datetime import datetime

import pytest

from ultimate_trader.validation_lab.performance_metrics import (
    Direction,
    PerformanceMetrics,
    TradeResult,
)
from ultimate_trader.validation_lab.validation_gate import (
    ValidationGate,
    ValidationGrade,
)
from ultimate_trader.validation_lab.monte_carlo import MonteCarloResult
from ultimate_trader.validation_lab.out_of_sample import OutOfSampleResult
from ultimate_trader.validation_lab.sensitivity_analysis import SensitivityResult
from ultimate_trader.validation_lab.walk_forward import WalkForwardResult


def make_trades(net_rs: list[float]) -> list[TradeResult]:
    return [
        TradeResult(
            trade_id=f"T{i}",
            hypothesis_id="RH-TEST",
            symbol="BTCUSDT",
            entry_time=datetime(2024, 1, 1),
            direction=Direction.LONG,
            entry_price=100.0,
            gross_r=r,
            net_r=r,
        )
        for i, r in enumerate(net_rs)
    ]


class TestValidationGate:
    def test_rejects_too_few_trades(self):
        gate = ValidationGate()
        metrics = PerformanceMetrics.calculate(make_trades([1.0]))
        result = gate.evaluate(
            metrics=metrics,
            walk_forward_result=WalkForwardResult(passed=True),
            out_of_sample_result=OutOfSampleResult(passed=True),
            monte_carlo_result=MonteCarloResult(passed=True),
            sensitivity_result=SensitivityResult(passed=True),
            minimum_trades=50,
        )
        assert not result.passed
        assert any("Too few trades" in r for r in result.failed_reasons)

    def test_rejects_negative_expectancy(self):
        gate = ValidationGate()
        trades = make_trades([-1.0] * 60)
        metrics = PerformanceMetrics.calculate(trades)
        result = gate.evaluate(
            metrics=metrics,
            walk_forward_result=WalkForwardResult(passed=True),
            out_of_sample_result=OutOfSampleResult(passed=True),
            monte_carlo_result=MonteCarloResult(passed=True),
            sensitivity_result=SensitivityResult(passed=True),
        )
        assert not result.passed
        assert any("Non-positive expectancy" in r for r in result.failed_reasons)

    def test_rejects_excessive_drawdown(self):
        gate = ValidationGate()
        trades = make_trades([5.0, -10.0, 3.0] * 20)
        metrics = PerformanceMetrics.calculate(trades)
        result = gate.evaluate(
            metrics=metrics,
            walk_forward_result=WalkForwardResult(passed=True),
            out_of_sample_result=OutOfSampleResult(passed=True),
            monte_carlo_result=MonteCarloResult(passed=True),
            sensitivity_result=SensitivityResult(passed=True),
        )
        assert "excessive drawdown" in str(result).lower() or not result.passed

    def test_never_allows_live_trading(self):
        gate = ValidationGate()
        trades = make_trades([1.0] * 100)
        metrics = PerformanceMetrics.calculate(trades)
        result = gate.evaluate(
            metrics=metrics,
            walk_forward_result=WalkForwardResult(passed=True),
            out_of_sample_result=OutOfSampleResult(passed=True),
            monte_carlo_result=MonteCarloResult(passed=True, probability_of_ruin=0.001),
            sensitivity_result=SensitivityResult(passed=True, robustness_score=0.9),
        )
        assert not result.eligible_for_live_trading

    def test_valid_hypothesis_passes_all_checks(self):
        gate = ValidationGate()
        trades = make_trades([2.0, -0.5, 1.5, -0.3, 1.0] * 20)
        metrics = PerformanceMetrics.calculate(trades)
        result = gate.evaluate(
            metrics=metrics,
            walk_forward_result=WalkForwardResult(passed=True),
            out_of_sample_result=OutOfSampleResult(passed=True),
            monte_carlo_result=MonteCarloResult(passed=True, probability_of_ruin=0.001),
            sensitivity_result=SensitivityResult(passed=True, robustness_score=0.9),
        )
        assert result.eligible_for_signal_generation

    def test_grade_assigned(self):
        gate = ValidationGate()
        trades = make_trades([-1.0] * 60)
        metrics = PerformanceMetrics.calculate(trades)
        result = gate.evaluate(
            metrics=metrics,
            walk_forward_result=WalkForwardResult(passed=True),
            out_of_sample_result=OutOfSampleResult(passed=True),
            monte_carlo_result=MonteCarloResult(passed=True),
            sensitivity_result=SensitivityResult(passed=True),
        )
        assert isinstance(result.validation_grade, ValidationGrade)
