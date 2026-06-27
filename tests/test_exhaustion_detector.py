from ultimate_trader.orderflow_intelligence.exhaustion_detector import (
    ExhaustionDetector,
)
from ultimate_trader.orderflow_intelligence.models import (
    ExhaustionState,
    FlowWindow,
)


def make_window(buy_vol: float = 0.0, sell_vol: float = 0.0, trades: int = 0) -> FlowWindow:
    return FlowWindow(
        symbol="BTCUSDT",
        total_buy_volume=buy_vol,
        total_sell_volume=sell_vol,
        buy_sell_delta=buy_vol - sell_vol,
        trade_count=trades,
    )


class TestExhaustionDetector:
    def test_insufficient_history_returns_no_exhaustion(self):
        d = ExhaustionDetector(history_length=10)
        r = d.analyze(make_window(buy_vol=100.0, sell_vol=50.0, trades=5))
        assert r.exhaustion_detected is False
        assert "Insufficient" in r.exhaustion_reason

    def test_buyer_exhaustion_detected(self):
        d = ExhaustionDetector(volume_fade_threshold=0.5, history_length=10)
        for _ in range(3):
            d.analyze(make_window(buy_vol=100.0, sell_vol=50.0, trades=5))
        r = d.analyze(make_window(buy_vol=30.0, sell_vol=50.0, trades=5))
        assert r.exhaustion_detected is True
        assert r.exhaustion_side == ExhaustionState.BUYER_EXHAUSTION
        assert r.exhaustion_score > 0

    def test_seller_exhaustion_detected(self):
        d = ExhaustionDetector(volume_fade_threshold=0.5, history_length=10)
        for _ in range(3):
            d.analyze(make_window(buy_vol=50.0, sell_vol=100.0, trades=5))
        r = d.analyze(make_window(buy_vol=50.0, sell_vol=20.0, trades=5))
        assert r.exhaustion_detected is True
        assert r.exhaustion_side == ExhaustionState.SELLER_EXHAUSTION

    def test_no_exhaustion_when_volume_stable(self):
        d = ExhaustionDetector(volume_fade_threshold=0.5, history_length=10)
        for _ in range(5):
            d.analyze(make_window(buy_vol=100.0, sell_vol=100.0, trades=5))
        r = d.analyze(make_window(buy_vol=100.0, sell_vol=100.0, trades=5))
        assert r.exhaustion_detected is False

    def test_both_sides_exhausted_returns_indecision(self):
        d = ExhaustionDetector(volume_fade_threshold=0.5, history_length=10)
        for _ in range(3):
            d.analyze(make_window(buy_vol=100.0, sell_vol=100.0, trades=5))
        r = d.analyze(make_window(buy_vol=30.0, sell_vol=30.0, trades=5))
        assert r.exhaustion_detected is True
        assert r.exhaustion_side == ExhaustionState.NO_EXHAUSTION
        assert "Both sides" in r.exhaustion_reason

    def test_reset(self):
        d = ExhaustionDetector()
        d.analyze(make_window(trades=5))
        d.reset()
        assert len(d._history) == 0

    def test_history_capped(self):
        d = ExhaustionDetector(history_length=3)
        for _ in range(10):
            d.analyze(make_window(buy_vol=100.0, sell_vol=50.0, trades=5))
        assert len(d._history) == 3

    def test_buyer_exhaustion_with_zero_first_volume(self):
        d = ExhaustionDetector(volume_fade_threshold=0.5, history_length=10)
        d.analyze(make_window(buy_vol=0.0, sell_vol=50.0, trades=5))
        d.analyze(make_window(buy_vol=0.0, sell_vol=50.0, trades=5))
        r = d.analyze(make_window(buy_vol=0.0, sell_vol=50.0, trades=5))
        assert r.exhaustion_detected is False

    def test_seller_exhaustion_with_zero_first_volume(self):
        d = ExhaustionDetector(volume_fade_threshold=0.5, history_length=10)
        d.analyze(make_window(buy_vol=50.0, sell_vol=0.0, trades=5))
        d.analyze(make_window(buy_vol=50.0, sell_vol=0.0, trades=5))
        r = d.analyze(make_window(buy_vol=50.0, sell_vol=0.0, trades=5))
        assert r.exhaustion_detected is False

    def test_fade_ratio_check_requires_consecutive_decline(self):
        d = ExhaustionDetector(volume_fade_threshold=0.5, history_length=10)
        d.analyze(make_window(buy_vol=100.0, sell_vol=50.0, trades=5))
        d.analyze(make_window(buy_vol=100.0, sell_vol=50.0, trades=5))
        r = d.analyze(make_window(buy_vol=100.0, sell_vol=50.0, trades=5))
        assert r.exhaustion_detected is False

    def test_exhaustion_reason_contains_score(self):
        d = ExhaustionDetector(volume_fade_threshold=0.5, history_length=10)
        for _ in range(3):
            d.analyze(make_window(buy_vol=100.0, sell_vol=50.0, trades=5))
        r = d.analyze(make_window(buy_vol=20.0, sell_vol=50.0, trades=5))
        assert "score=" in r.exhaustion_reason
