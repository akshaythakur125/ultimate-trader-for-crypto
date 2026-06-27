"""Tests for RiskAdjustedUtilityEngine."""

from ultimate_trader.belief_engine.risk_adjusted_utility import (
    RiskAdjustedUtilityEngine,
    UtilityGrade,
)


class TestRiskAdjustedUtilityEngine:
    def setup_method(self):
        self.engine = RiskAdjustedUtilityEngine()

    def test_high_uncertainty_penalizes(self):
        low_uncertainty = self.engine.calculate(
            raw_expected_value_r=1.0, uncertainty_score=10.0
        )
        high_uncertainty = self.engine.calculate(
            raw_expected_value_r=1.0, uncertainty_score=90.0
        )
        assert low_uncertainty.final_utility_score > high_uncertainty.final_utility_score

    def test_high_drawdown_penalizes(self):
        low_dd = self.engine.calculate(
            raw_expected_value_r=1.0, drawdown_risk=10.0
        )
        high_dd = self.engine.calculate(
            raw_expected_value_r=1.0, drawdown_risk=90.0
        )
        assert low_dd.final_utility_score > high_dd.final_utility_score

    def test_contradiction_penalizes(self):
        no_contra = self.engine.calculate(
            raw_expected_value_r=1.0, contradiction_score=0.0
        )
        high_contra = self.engine.calculate(
            raw_expected_value_r=1.0, contradiction_score=80.0
        )
        assert no_contra.final_utility_score > high_contra.final_utility_score

    def test_excellent_grade_for_high_ev(self):
        result = self.engine.calculate(raw_expected_value_r=2.0, uncertainty_score=10.0)
        assert result.utility_grade == UtilityGrade.EXCELLENT

    def test_no_trade_grade_when_no_trade_dominant(self):
        result = self.engine.calculate(
            raw_expected_value_r=0.5,
            no_trade_probability=0.8,
            uncertainty_score=50.0,
        )
        assert result.utility_grade == UtilityGrade.NO_TRADE

    def test_bad_grade_for_negative_ev(self):
        result = self.engine.calculate(
            raw_expected_value_r=-0.3,
            uncertainty_score=50.0,
        )
        assert result.utility_grade in (UtilityGrade.BAD, UtilityGrade.NO_TRADE)
