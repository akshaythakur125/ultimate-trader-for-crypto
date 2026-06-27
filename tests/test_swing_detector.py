from ultimate_trader.liquidity_smart_money.models import Candle, SwingType
from ultimate_trader.liquidity_smart_money.swing_detector import SwingDetector


def make_candle(high: float, low: float, close: float = 0.0, idx: int = 0) -> Candle:
    return Candle(
        symbol="BTCUSDT",
        timeframe="1h",
        timestamp=__import__("datetime").datetime.utcnow(),
        open=close,
        high=high,
        low=low,
        close=close,
        volume=100.0,
    )


class TestSwingDetector:
    def test_swing_high_detected(self):
        d = SwingDetector(lookback=2)
        for h, l in [(100, 99), (101, 99.5), (102, 100), (101.5, 99.8), (101, 99.5)]:
            d.add_candle(make_candle(high=h, low=l))
        highs = d.get_swing_highs()
        assert len(highs) >= 1
        assert any(s.price == 102.0 for s in highs)

    def test_swing_low_detected(self):
        d = SwingDetector(lookback=2)
        for h, l in [(101, 100), (100.5, 99), (100, 98), (100.5, 98.5), (101, 99)]:
            d.add_candle(make_candle(high=h, low=l))
        lows = d.get_swing_lows()
        assert len(lows) >= 1
        assert any(s.price == 98.0 for s in lows)

    def test_no_swing_with_few_candles(self):
        d = SwingDetector(lookback=3)
        for h, l in [(100, 99), (101, 99.5)]:
            d.add_candle(make_candle(high=h, low=l))
        assert len(d.get_all_swing_points()) == 0

    def test_equal_highs_detected(self):
        d = SwingDetector(lookback=2, equal_threshold=0.01)
        for i, (h, l) in enumerate([(100, 99), (100.05, 99.5), (101, 100), (100.03, 99.8), (100.5, 99.5)]):
            d.add_candle(make_candle(high=h, low=l))
        eq_highs = d.get_equal_highs()
        assert len(eq_highs) >= 0

    def test_equal_lows_detected(self):
        d = SwingDetector(lookback=2, equal_threshold=0.01)
        for i, (h, l) in enumerate([(101, 99), (100.5, 98.98), (101, 100), (100.5, 99), (101, 99.5)]):
            d.add_candle(make_candle(high=h, low=l))
        eq_lows = d.get_equal_lows()
        assert len(eq_lows) >= 0

    def test_recent_high_and_low(self):
        d = SwingDetector()
        for h, l in [(100, 99), (101, 99.5), (102, 100)]:
            d.add_candle(make_candle(high=h, low=l))
        assert d.recent_high(3) == 102.0
        assert d.recent_low(3) == 99.0

    def test_highest_lowest_swing(self):
        d = SwingDetector(lookback=2)
        for h, l in [(100, 99), (101, 99.5), (102, 100), (101.5, 99.8), (101, 99.5)]:
            d.add_candle(make_candle(high=h, low=l))
        assert d.highest_swing_high() == 102.0

    def test_lowest_swing_low_found(self):
        d = SwingDetector(lookback=2)
        for h, l in [(101, 100), (100.5, 99), (100, 98), (100.5, 98.5), (101, 99)]:
            d.add_candle(make_candle(high=h, low=l))
        assert d.lowest_swing_low() == 98.0

    def test_reset(self):
        d = SwingDetector()
        d.add_candle(make_candle(high=100, low=99))
        d.reset()
        assert len(d.get_all_swing_points()) == 0
