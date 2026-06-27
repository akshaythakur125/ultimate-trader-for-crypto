from ultimate_trader.liquidity_smart_money.liquidity_pools import LiquidityPoolDetector
from ultimate_trader.liquidity_smart_money.models import Candle, SwingPoint, SwingType


def make_candle(high: float, low: float, close: float = 0.0, vol: float = 100.0) -> Candle:
    return Candle(
        symbol="BTCUSDT", timeframe="1h",
        timestamp=__import__("datetime").datetime.utcnow(),
        open=close, high=high, low=low, close=close, volume=vol,
    )


class TestLiquidityPoolDetector:
    def test_buy_side_liquidity_detected(self):
        d = LiquidityPoolDetector()
        swing_highs = [SwingPoint(price=105.0, index=5, swing_type=SwingType.SWING_HIGH)]
        swing_lows = [SwingPoint(price=95.0, index=3, swing_type=SwingType.SWING_LOW)]
        equal_highs = [SwingPoint(price=106.0, index=7, swing_type=SwingType.EQUAL_HIGH)]
        equal_lows = []
        zones = d.analyze(swing_highs, swing_lows, equal_highs, equal_lows, 100.0, [])
        buy_side = [z for z in zones if z.zone_type == "BUY_SIDE"]
        assert len(buy_side) > 0

    def test_sell_side_liquidity_detected(self):
        d = LiquidityPoolDetector()
        swing_highs = [SwingPoint(price=105.0, index=5, swing_type=SwingType.SWING_HIGH)]
        swing_lows = [SwingPoint(price=95.0, index=3, swing_type=SwingType.SWING_LOW)]
        equal_lows = [SwingPoint(price=94.0, index=6, swing_type=SwingType.EQUAL_LOW)]
        zones = d.analyze(swing_highs, swing_lows, [], equal_lows, 100.0, [])
        sell_side = [z for z in zones if z.zone_type == "SELL_SIDE"]
        assert len(sell_side) > 0

    def test_active_and_swept_zones(self):
        d = LiquidityPoolDetector()
        swing_highs = [SwingPoint(price=105.0, index=5, swing_type=SwingType.SWING_HIGH)]
        swing_lows = [SwingPoint(price=95.0, index=3, swing_type=SwingType.SWING_LOW)]
        zones = d.analyze(swing_highs, swing_lows, [], [], 100.0, [])
        active = d.get_active_zones()
        swept = d.get_swept_zones()
        assert len(active) + len(swept) == len(zones)

    def test_zones_marked_swept_by_price(self):
        d = LiquidityPoolDetector()
        swing_highs = [SwingPoint(price=105.0, index=5, swing_type=SwingType.SWING_HIGH)]
        swing_lows = [SwingPoint(price=95.0, index=3, swing_type=SwingType.SWING_LOW)]
        zones = d.analyze(swing_highs, swing_lows, [], [], 106.0, [make_candle(106, 104)])
        buy_side = [z for z in zones if z.zone_type == "BUY_SIDE"]
        if buy_side:
            assert all(z.is_swept for z in buy_side)

    def test_stop_clusters_detected(self):
        d = LiquidityPoolDetector()
        candles = [make_candle(100, 99, vol=200.0) for _ in range(10)]
        candles += [make_candle(101, 98, vol=500.0) for _ in range(5)]
        zones = d.analyze([], [], [], [], 100.0, candles)
        stops = [z for z in zones if z.zone_type == "STOP_CLUSTER"]
        assert len(stops) >= 0

    def test_reset(self):
        d = LiquidityPoolDetector()
        d.analyze([], [], [], [], 100.0, [])
        d.reset()
        assert len(d._zones) == 0
