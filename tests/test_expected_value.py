"""Tests for ExpectedValueCalculator."""

from ultimate_trader.belief_engine.expected_value import ExpectedValueCalculator


class TestExpectedValueCalculator:
    def setup_method(self):
        self.calc = ExpectedValueCalculator()

    def test_positive_ev(self):
        result = self.calc.calculate(
            probability_of_win=0.6,
            average_win_r=3.0,
            probability_of_loss=0.4,
            average_loss_r=1.0,
        )
        assert result.is_positive_ev is True
        assert result.expected_value_r > 0
        assert result.expected_value_r == 1.4

    def test_negative_ev(self):
        result = self.calc.calculate(
            probability_of_win=0.3,
            average_win_r=1.0,
            probability_of_loss=0.7,
            average_loss_r=2.0,
        )
        assert result.is_positive_ev is False
        assert result.expected_value_r < 0

    def test_breakeven_win_rate(self):
        result = self.calc.calculate(
            probability_of_win=0.5,
            average_win_r=2.0,
            probability_of_loss=0.5,
            average_loss_r=1.0,
        )
        assert abs(result.required_win_rate_for_breakeven - 1.0 / 3.0) < 0.001

    def test_margin_of_safety_positive(self):
        result = self.calc.calculate(
            probability_of_win=0.6,
            average_win_r=3.0,
            probability_of_loss=0.4,
            average_loss_r=1.0,
        )
        assert result.margin_of_safety > 0

    def test_zero_probability(self):
        result = self.calc.calculate(
            probability_of_win=0,
            average_win_r=3.0,
            probability_of_loss=0,
            average_loss_r=1.0,
        )
        assert result.is_positive_ev is False

    def test_calculate_from_beliefs(self):
        result = self.calc.calculate_from_beliefs(
            probability_of_win=0.5,
            average_win_r=2.0,
            probability_of_no_trade=0.2,
            average_loss_r=1.0,
        )
        assert result.is_positive_ev is True
