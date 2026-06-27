from ultimate_trader.orderflow_intelligence.delta_divergence import (
    DeltaDivergenceDetector,
)
from ultimate_trader.orderflow_intelligence.models import (
    DeltaDivergenceType,
    FlowWindow,
)


def make_window(cumulative_delta: float = 0.0) -> FlowWindow:
    return FlowWindow(symbol="BTCUSDT", cumulative_delta=cumulative_delta)


class TestDeltaDivergence:
    def test_insufficient_history(self):
        d = DeltaDivergenceDetector(history_length=10)
        r = d.analyze(make_window(cumulative_delta=10.0), 100.0)
        assert r.divergence_detected is False
        assert "Insufficient" in r.interpretation

    def test_bullish_divergence(self):
        d = DeltaDivergenceDetector(history_length=10)
        d.analyze(make_window(cumulative_delta=10.0), 100.0)
        d.analyze(make_window(cumulative_delta=12.0), 99.0)
        r = d.analyze(make_window(cumulative_delta=15.0), 98.0)
        assert r.divergence_detected is True
        assert r.divergence_type == DeltaDivergenceType.BULLISH_DIVERGENCE
        assert "bullish" in r.interpretation

    def test_bearish_divergence(self):
        d = DeltaDivergenceDetector(history_length=10)
        d.analyze(make_window(cumulative_delta=10.0), 100.0)
        d.analyze(make_window(cumulative_delta=8.0), 101.0)
        r = d.analyze(make_window(cumulative_delta=5.0), 102.0)
        assert r.divergence_detected is True
        assert r.divergence_type == DeltaDivergenceType.BEARISH_DIVERGENCE
        assert "bearish" in r.interpretation

    def test_no_divergence(self):
        d = DeltaDivergenceDetector(history_length=10)
        d.analyze(make_window(cumulative_delta=10.0), 100.0)
        d.analyze(make_window(cumulative_delta=12.0), 101.0)
        r = d.analyze(make_window(cumulative_delta=14.0), 102.0)
        assert r.divergence_detected is False

    def test_conflicting_signals(self):
        d = DeltaDivergenceDetector(history_length=10)
        d.analyze(make_window(cumulative_delta=10.0), 100.0)
        d.analyze(make_window(cumulative_delta=12.0), 99.0)
        r = d.analyze(make_window(cumulative_delta=8.0), 98.0)
        assert r.divergence_detected is False

    def test_divergence_strength_weak(self):
        d = DeltaDivergenceDetector(history_length=10)
        d.analyze(make_window(cumulative_delta=10.0), 100.0)
        d.analyze(make_window(cumulative_delta=10.5), 99.0)
        r = d.analyze(make_window(cumulative_delta=11.0), 98.0)
        assert r.divergence_detected is True
        assert r.divergence_strength == "weak"

    def test_divergence_strength_strong(self):
        d = DeltaDivergenceDetector(history_length=10)
        d.analyze(make_window(cumulative_delta=10.0), 100.0)
        d.analyze(make_window(cumulative_delta=20.0), 99.0)
        r = d.analyze(make_window(cumulative_delta=30.0), 98.0)
        assert r.divergence_detected is True
        assert r.divergence_strength == "strong"

    def test_reset(self):
        d = DeltaDivergenceDetector()
        d.analyze(make_window(cumulative_delta=10.0), 100.0)
        d.reset()
        assert len(d._price_history) == 0
        assert len(d._delta_history) == 0

    def test_history_capped(self):
        d = DeltaDivergenceDetector(history_length=3)
        for i in range(10):
            d.analyze(make_window(cumulative_delta=float(i)), 100.0 + float(i))
        assert len(d._price_history) == 3
        assert len(d._delta_history) == 3

    def test_exactly_two_windows_is_insufficient(self):
        d = DeltaDivergenceDetector(history_length=10)
        d.analyze(make_window(cumulative_delta=10.0), 100.0)
        r = d.analyze(make_window(cumulative_delta=12.0), 99.0)
        assert r.divergence_detected is False

    def test_bullish_interpretation_text(self):
        d = DeltaDivergenceDetector(history_length=10)
        d.analyze(make_window(cumulative_delta=10.0), 100.0)
        d.analyze(make_window(cumulative_delta=12.0), 99.0)
        r = d.analyze(make_window(cumulative_delta=15.0), 98.0)
        assert "lower lows" in r.interpretation
        assert "higher lows" in r.interpretation

    def test_bearish_interpretation_text(self):
        d = DeltaDivergenceDetector(history_length=10)
        d.analyze(make_window(cumulative_delta=10.0), 100.0)
        d.analyze(make_window(cumulative_delta=8.0), 101.0)
        r = d.analyze(make_window(cumulative_delta=5.0), 102.0)
        assert "higher highs" in r.interpretation
        assert "lower highs" in r.interpretation
