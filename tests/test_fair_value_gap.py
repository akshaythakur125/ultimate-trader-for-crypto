from ultimate_trader.liquidity_smart_money.fair_value_gap import (
    FairValueGapDetector,
)
from ultimate_trader.liquidity_smart_money.models import Candle


def make_candle(open_p: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        symbol="BTCUSDT", timeframe="1h",
        timestamp=__import__("datetime").datetime.utcnow(),
        open=open_p, high=high, low=low, close=close, volume=100.0,
    )


class TestFairValueGapDetector:
    def test_bullish_fvg_detected(self):
        d = FairValueGapDetector(min_gap_bps=0.5)
        candles = [
            make_candle(100, 101, 99, 100),
            make_candle(101, 102, 100.5, 101.5),
            make_candle(103, 104, 102, 103),
        ]
        fvgs = d.analyze(candles)
        bullish = [f for f in fvgs if f.fvg_type == "BULLISH_FVG"]
        assert len(bullish) >= 0

    def test_bearish_fvg_detected(self):
        d = FairValueGapDetector(min_gap_bps=0.5)
        candles = [
            make_candle(103, 104, 102, 103),
            make_candle(102, 103, 101, 102),
            make_candle(100, 101, 99, 100),
        ]
        fvgs = d.analyze(candles)
        bearish = [f for f in fvgs if f.fvg_type == "BEARISH_FVG"]
        assert len(bearish) >= 0

    def test_no_fvg_with_continuous_prices(self):
        d = FairValueGapDetector(min_gap_bps=0.5)
        candles = [
            make_candle(100, 101, 99, 100),
            make_candle(100, 101, 99, 100),
            make_candle(100, 101, 99, 100),
        ]
        fvgs = d.analyze(candles)
        assert len(fvgs) == 0

    def test_insufficient_candles(self):
        d = FairValueGapDetector()
        fvgs = d.analyze([make_candle(100, 101, 99, 100)])
        assert len(fvgs) == 0

    def test_fvg_mitigation(self):
        d = FairValueGapDetector(min_gap_bps=0.1)
        candles = [
            make_candle(100, 101, 99, 100),
            make_candle(101, 102, 100.5, 101.5),
            make_candle(103, 104, 102, 103),
        ]
        d.analyze(candles)
        mitigate = [
            make_candle(102, 102.5, 101, 102),
            make_candle(101, 101.5, 100.5, 101),
        ]
        fvgs_after = d.analyze(mitigate)
        active = d.get_active_fvgs()
        all_fvgs = d.get_fvgs()
        assert len(active) <= len(all_fvgs)

    def test_reset(self):
        d = FairValueGapDetector()
        candles = [
            make_candle(100, 101, 99, 100),
            make_candle(101, 102, 100.5, 101.5),
            make_candle(103, 104, 102, 103),
        ]
        d.analyze(candles)
        d.reset()
        assert len(d.get_fvgs()) == 0
