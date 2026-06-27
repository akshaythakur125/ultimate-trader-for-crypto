from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.validation_lab.monte_carlo import MonteCarloResult
from ultimate_trader.validation_lab.out_of_sample import OutOfSampleResult
from ultimate_trader.validation_lab.performance_metrics import (
    PerformanceMetrics,
)
from ultimate_trader.validation_lab.sensitivity_analysis import (
    SensitivityResult,
)
from ultimate_trader.validation_lab.walk_forward import WalkForwardResult


class ValidationGrade(str, Enum):
    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    MARGINAL = "MARGINAL"
    FAILED = "FAILED"


class ValidationGateResult(BaseModel):
    passed: bool = False
    failed_reasons: list[str] = Field(default_factory=list)
    passed_checks: list[str] = Field(default_factory=list)
    validation_grade: ValidationGrade = ValidationGrade.FAILED
    eligible_for_signal_generation: bool = False
    eligible_for_paper_trading: bool = False
    eligible_for_live_trading: bool = False


class ValidationGate:
    MAX_DAILY_DRAWDOWN_PCT = 15.0

    def evaluate(
        self,
        metrics: PerformanceMetrics,
        walk_forward_result: WalkForwardResult,
        out_of_sample_result: OutOfSampleResult,
        monte_carlo_result: MonteCarloResult,
        sensitivity_result: SensitivityResult,
        minimum_trades: int = 50,
    ) -> ValidationGateResult:
        passed = True
        failed_reasons = []
        passed_checks = []
        grade = ValidationGrade.EXCELLENT

        if metrics.total_trades < minimum_trades:
            passed = False
            failed_reasons.append(
                f"Too few trades ({metrics.total_trades} < {minimum_trades})"
            )

        if metrics.total_trades >= minimum_trades:
            passed_checks.append(f"Minimum trades met ({metrics.total_trades} >= {minimum_trades})")

        if metrics.expectancy_r <= 0:
            passed = False
            failed_reasons.append(f"Non-positive expectancy ({metrics.expectancy_r})")
        else:
            passed_checks.append(f"Positive expectancy ({metrics.expectancy_r})")

        if metrics.profit_factor <= 1.2:
            passed = False
            failed_reasons.append(f"Profit factor too low ({metrics.profit_factor} <= 1.2)")
        else:
            passed_checks.append(f"Profit factor above 1.2 ({metrics.profit_factor})")

        if metrics.max_daily_drawdown_percent > self.MAX_DAILY_DRAWDOWN_PCT:
            passed = False
            failed_reasons.append(
                f"Excessive daily drawdown ({metrics.max_daily_drawdown_percent}% > {self.MAX_DAILY_DRAWDOWN_PCT}%)"
            )
        else:
            passed_checks.append("Daily drawdown within limits")

        if not walk_forward_result.passed:
            passed = False
            failed_reasons.append("Walk-forward validation failed")
        else:
            passed_checks.append("Walk-forward validation passed")

        if not out_of_sample_result.passed:
            passed = False
            failed_reasons.append("Out-of-sample validation failed")
        else:
            passed_checks.append("Out-of-sample validation passed")

        if not monte_carlo_result.passed:
            passed = False
            failed_reasons.append(f"Monte Carlo simulation failed (ruin prob: {monte_carlo_result.probability_of_ruin})")
        else:
            passed_checks.append("Monte Carlo simulation passed")

        if not sensitivity_result.passed:
            passed = False
            failed_reasons.append(
                f"Sensitivity analysis failed ({sensitivity_result.scenarios_passed}/{sensitivity_result.scenarios_tested} passed)"
            )
        else:
            passed_checks.append("Sensitivity analysis passed")

        if passed:
            if monte_carlo_result.probability_of_ruin < 0.01:
                grade = ValidationGrade.EXCELLENT
            elif sensitivity_result.robustness_score >= 0.9:
                grade = ValidationGrade.GOOD
            else:
                grade = ValidationGrade.GOOD
        elif len(failed_reasons) <= 2 and metrics.expectancy_r > 0:
            grade = ValidationGrade.MARGINAL
        else:
            grade = ValidationGrade.FAILED

        return ValidationGateResult(
            passed=passed,
            failed_reasons=failed_reasons,
            passed_checks=passed_checks,
            validation_grade=grade,
            eligible_for_signal_generation=passed,
            eligible_for_paper_trading=passed and grade in (ValidationGrade.GOOD, ValidationGrade.EXCELLENT),
            eligible_for_live_trading=False,
        )
