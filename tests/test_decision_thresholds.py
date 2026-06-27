"""Tests for DecisionThresholds."""

from ultimate_trader.belief_engine.decision_thresholds import DecisionThresholds


class TestDecisionThresholds:
    def setup_method(self):
        self.thresholds = DecisionThresholds()

    def test_accepts_positive_ev(self):
        result = self.thresholds.evaluate(
            expected_value_r=1.5,
            utility_grade="GOOD",
            no_trade_probability=0.1,
            uncertainty_score=40.0,
            estimated_win_probability=0.6,
            required_win_rate=0.33,
        )
        assert result.mathematically_acceptable is True

    def test_rejects_negative_ev(self):
        result = self.thresholds.evaluate(
            expected_value_r=-0.5,
            utility_grade="MARGINAL",
            no_trade_probability=0.1,
            uncertainty_score=40.0,
            estimated_win_probability=0.3,
            required_win_rate=0.5,
        )
        assert result.mathematically_acceptable is False
        assert "Non-positive EV" in str(result.failed_thresholds)

    def test_rejects_dominant_no_trade(self):
        result = self.thresholds.evaluate(
            expected_value_r=1.0,
            utility_grade="GOOD",
            no_trade_probability=0.7,
            uncertainty_score=40.0,
            estimated_win_probability=0.6,
            required_win_rate=0.33,
        )
        assert result.mathematically_acceptable is False

    def test_rejects_high_uncertainty(self):
        result = self.thresholds.evaluate(
            expected_value_r=1.0,
            utility_grade="GOOD",
            no_trade_probability=0.1,
            uncertainty_score=85.0,
            estimated_win_probability=0.6,
            required_win_rate=0.33,
            max_uncertainty=70.0,
        )
        assert result.mathematically_acceptable is False

    def test_passed_thresholds_listed(self):
        result = self.thresholds.evaluate(
            expected_value_r=1.0,
            utility_grade="EXCELLENT",
            no_trade_probability=0.1,
            uncertainty_score=30.0,
            estimated_win_probability=0.6,
            required_win_rate=0.33,
        )
        assert len(result.passed_thresholds) == 5
