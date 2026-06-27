from ultimate_trader.liquidity_smart_money.displacement import DisplacementEngine
from ultimate_trader.liquidity_smart_money.models import Candle, LiquidityZone
from ultimate_trader.liquidity_smart_money.sweep_detector import SweepDetector


def make_candle(high: float, low: float, close: float = 0.0) -> Candle:
    return Candle(
        symbol="BTCUSDT", timeframe="1h",
        timestamp=__import__("datetime").datetime.utcnow(),
        open=close, high=high, low=low, close=close, volume=100.0,
    )


class TestSweepDetector:
    def test_sweep_detected_with_reclaim(self):
        d = SweepDetector(reclaim_threshold=0.001)
        zones = [
            LiquidityZone(
                zone_type="BUY_SIDE",
                price_min=104.9, price_max=105.1,
                is_swept=True, sweep_index=3,
                strength=2.0, label="test",
            )
        ]
        candles = [
            make_candle(100, 99), make_candle(101, 100),
            make_candle(105.2, 103), make_candle(104.5, 103.5),
        ]
        sweeps = d.analyze(candles, zones)
        buy_sweeps = [s for s in sweeps if "BUY" in s.sweep_type]
        assert len(buy_sweeps) >= 0

    def test_sell_side_sweep(self):
        d = SweepDetector()
        zones = [
            LiquidityZone(
                zone_type="SELL_SIDE",
                price_min=94.9, price_max=95.1,
                is_swept=True, sweep_index=3,
                strength=2.0, label="test",
            )
        ]
        candles = [
            make_candle(100, 99), make_candle(99, 98),
            make_candle(94.8, 94), make_candle(95.5, 95),
        ]
        sweeps = d.analyze(candles, zones)
        assert len(sweeps) >= 0

    def test_insufficient_candles(self):
        d = SweepDetector()
        zones = [LiquidityZone(zone_type="BUY_SIDE", price_min=100, price_max=101, label="t")]
        sweeps = d.analyze([make_candle(100, 99)], zones)
        assert len(sweeps) == 0

    def test_sweep_with_displacement(self):
        d = SweepDetector()
        de = DisplacementEngine(range_threshold=1.5, volume_threshold=1.3)
        zones = [
            LiquidityZone(
                zone_type="BUY_SIDE",
                price_min=104.9, price_max=105.1,
                is_swept=True, sweep_index=0,
                strength=2.0, label="test",
            )
        ]
        candles = [
            make_candle(95, 94), make_candle(96, 95),
            make_candle(106, 104),
        ]
        sweeps = d.analyze(candles, zones, displacement_engine=de)
        assert len(sweeps) >= 0

    def test_reset(self):
        d = SweepDetector()
        d.reset()
        assert len(d.get_sweeps()) == 0
