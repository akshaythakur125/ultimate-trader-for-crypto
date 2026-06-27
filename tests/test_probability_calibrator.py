"""Tests for ProbabilityCalibrator."""

from ultimate_trader.belief_engine.probability_calibrator import ProbabilityCalibrator


class TestProbabilityCalibrator:
    def setup_method(self):
        self.calibrator = ProbabilityCalibrator()

    def test_insufficient_memory_reduces_certainty(self):
        result = self.calibrator.calibrate(
            raw_probability=0.8,
            similar_cases_count=3,
            min_sample=10,
        )
        assert result.calibrated_probability < 0.8
        assert result.sufficient_sample_size is False

    def test_pulls_overconfident_toward_historical_win_rate(self):
        result = self.calibrator.calibrate(
            raw_probability=0.9,
            historical_win_rate=0.5,
            similar_cases_count=20,
        )
        assert result.calibrated_probability < 0.9

    def test_reduces_for_negative_expectancy(self):
        result = self.calibrator.calibrate(
            raw_probability=0.6,
            historical_expectancy=-0.5,
            similar_cases_count=20,
        )
        assert result.calibrated_probability < 0.6

    def test_reduces_for_high_memory_warning(self):
        result = self.calibrator.calibrate(
            raw_probability=0.6,
            memory_warning_score=80.0,
            similar_cases_count=20,
        )
        assert result.calibrated_probability < 0.6

    def test_increases_for_strong_memory_support(self):
        result = self.calibrator.calibrate(
            raw_probability=0.5,
            memory_support_score=85.0,
            similar_cases_count=20,
        )
        assert result.calibrated_probability > 0.5

    def test_output_stays_in_bounds(self):
        for raw in [0.001, 0.5, 0.999]:
            result = self.calibrator.calibrate(
                raw_probability=raw,
                historical_win_rate=0.3,
                similar_cases_count=100,
            )
            assert 0.01 <= result.calibrated_probability <= 0.99

    def test_no_adjustment_with_no_data(self):
        result = self.calibrator.calibrate(
            raw_probability=0.5, similar_cases_count=10, min_sample=0
        )
        assert abs(result.calibration_adjustment) < 0.001
