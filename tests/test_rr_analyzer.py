import pytest

from ultimate_trader.signal_engine.rr_analyzer import RRAnalyzer


class TestRRAnalyzer:
    def test_rejects_rr_below_3(self):
        analyzer = RRAnalyzer()
        result = analyzer.analyze(100.0, 99.0, 102.0)
        assert result.meets_minimum_rr is False
        assert "REJECTED" in result.rr_summary

    def test_accepts_rr_at_3(self):
        analyzer = RRAnalyzer()
        result = analyzer.analyze(100.0, 99.0, 103.0)
        assert result.meets_minimum_rr is True

    def test_prefers_rr_at_5(self):
        analyzer = RRAnalyzer()
        result = analyzer.analyze(100.0, 99.0, 105.0)
        assert result.meets_preferred_rr is True

    def test_rr_between_min_and_pref(self):
        analyzer = RRAnalyzer()
        result = analyzer.analyze(100.0, 99.0, 104.0)
        assert result.meets_minimum_rr is True
        assert result.meets_preferred_rr is False

    def test_zero_risk_returns_zero_rr(self):
        analyzer = RRAnalyzer()
        result = analyzer.analyze(100.0, 100.0, 105.0)
        assert result.rr_ratio == 0.0
        assert result.meets_minimum_rr is False

    def test_meets_minimum_helper(self):
        analyzer = RRAnalyzer()
        assert analyzer.meets_minimum(3.0) is True
        assert analyzer.meets_minimum(2.9) is False
