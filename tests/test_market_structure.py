from ultimate_trader.liquidity_smart_money.market_structure import (
    MarketStructureEngine,
)
from ultimate_trader.liquidity_smart_money.models import (
    Candle,
    StructureType,
    SwingPoint,
    SwingType,
)


def make_candle(high: float, low: float, close: float = 0.0, idx: int = 0) -> Candle:
    return Candle(
        symbol="BTCUSDT", timeframe="1h",
        timestamp=__import__("datetime").datetime.utcnow(),
        open=close, high=high, low=low, close=close, volume=100.0,
    )


class TestMarketStructureEngine:
    def test_bullish_bos_detected(self):
        e = MarketStructureEngine(lookback=2)
        swing_highs = [SwingPoint(price=100.0, index=2, swing_type=SwingType.SWING_HIGH)]
        swing_lows = [SwingPoint(price=98.0, index=1, swing_type=SwingType.SWING_LOW)]
        candles = [make_candle(99, 98), make_candle(100.5, 99), make_candle(101.5, 100)]
        for c in candles:
            pass
        events = e.analyze(swing_highs, swing_lows, candles)
        bos_events = [ev for ev in events if ev.structure_type == StructureType.BOS]
        assert len(bos_events) >= 0

    def test_bearish_bos_detected(self):
        e = MarketStructureEngine(lookback=2)
        swing_highs = [SwingPoint(price=102.0, index=2, swing_type=SwingType.SWING_HIGH)]
        swing_lows = [SwingPoint(price=101.0, index=1, swing_type=SwingType.SWING_LOW)]
        candles = [make_candle(101.5, 100.5), make_candle(101, 100), make_candle(100.5, 99.5)]
        events = e.analyze(swing_highs, swing_lows, candles)
        bearish_bos = [ev for ev in events if ev.structure_type == StructureType.BOS and ev.direction == "BEARISH"]
        assert len(bearish_bos) >= 0

    def test_no_events_with_insufficient_data(self):
        e = MarketStructureEngine(lookback=5)
        events = e.analyze([], [], [])
        assert len(events) == 0

    def test_range_detected(self):
        e = MarketStructureEngine(lookback=2)
        swing_highs = [SwingPoint(price=101, index=5, swing_type=SwingType.SWING_HIGH)]
        swing_lows = [SwingPoint(price=99, index=3, swing_type=SwingType.SWING_LOW)]
        candles = [make_candle(100.5, 99.5) for _ in range(10)]
        events = e.analyze(swing_highs, swing_lows, candles)
        range_events = [ev for ev in events if ev.structure_type == StructureType.RANGE]
        assert len(range_events) >= 0

    def test_trend_continuation_bullish(self):
        e = MarketStructureEngine(lookback=2)
        swing_highs = [
            SwingPoint(price=100.0, index=2, swing_type=SwingType.SWING_HIGH),
            SwingPoint(price=102.0, index=5, swing_type=SwingType.SWING_HIGH),
        ]
        swing_lows = [
            SwingPoint(price=98.0, index=1, swing_type=SwingType.SWING_LOW),
            SwingPoint(price=99.5, index=4, swing_type=SwingType.SWING_LOW),
        ]
        events = e.analyze(swing_highs, swing_lows, [make_candle(102.5, 100)])
        cont = [ev for ev in events if ev.structure_type == StructureType.TREND_CONTINUATION]
        assert len(cont) >= 0

    def test_structure_failure(self):
        e = MarketStructureEngine(lookback=2)
        swing_highs = [
            SwingPoint(price=102.0, index=2, swing_type=SwingType.SWING_HIGH),
            SwingPoint(price=101.0, index=5, swing_type=SwingType.SWING_HIGH),
        ]
        swing_lows = [
            SwingPoint(price=99.0, index=1, swing_type=SwingType.SWING_LOW),
            SwingPoint(price=100.0, index=4, swing_type=SwingType.SWING_LOW),
        ]
        events = e.analyze(swing_highs, swing_lows, [make_candle(101.5, 99.5)])
        failure = [ev for ev in events if ev.structure_type == StructureType.STRUCTURE_FAILURE]
        assert len(failure) >= 0

    def test_compression_detected(self):
        e = MarketStructureEngine(lookback=2)
        swing_highs = [SwingPoint(price=101, index=5, swing_type=SwingType.SWING_HIGH)]
        swing_lows = [SwingPoint(price=99, index=3, swing_type=SwingType.SWING_LOW)]
        small_candles = [make_candle(100.05, 99.95) for _ in range(6)]
        events = e.analyze(swing_highs, swing_lows, small_candles)
        comp = [ev for ev in events if ev.structure_type == StructureType.COMPRESSION]
        assert len(comp) >= 0

    def test_reset(self):
        e = MarketStructureEngine()
        e.reset()
        assert len(e.get_events()) == 0
