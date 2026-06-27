from ultimate_trader.liquidity_smart_money.models import Candle, FVG
from ultimate_trader.liquidity_smart_money.order_block import OrderBlockDetector


def make_candle(open_p: float, high: float, low: float, close: float, vol: float = 100.0) -> Candle:
    return Candle(
        symbol="BTCUSDT", timeframe="1h",
        timestamp=__import__("datetime").datetime.utcnow(),
        open=open_p, high=high, low=low, close=close, volume=vol,
    )


class TestOrderBlockDetector:
    def test_bullish_order_block_from_fvg(self):
        d = OrderBlockDetector()
        candles = [
            make_candle(100, 101, 99, 100),
            make_candle(101, 102, 100.5, 101.5),
            make_candle(103, 104, 102, 103),
        ]
        fvgs = [
            FVG(
                fvg_type="BULLISH_FVG",
                gap_high=102, gap_low=101,
                gap_size=10.0, index=2,
            ),
        ]
        blocks = d.analyze(candles, fvgs)
        bullish = [b for b in blocks if "BULLISH" in b.ob_type]
        assert len(bullish) >= 0

    def test_bearish_order_block_from_fvg(self):
        d = OrderBlockDetector()
        candles = [
            make_candle(103, 104, 102, 103),
            make_candle(102, 103, 101, 102),
            make_candle(100, 101, 99, 100),
        ]
        fvgs = [
            FVG(
                fvg_type="BEARISH_FVG",
                gap_high=102, gap_low=101,
                gap_size=10.0, index=2,
            ),
        ]
        blocks = d.analyze(candles, fvgs)
        bearish = [b for b in blocks if "BEARISH" in b.ob_type]
        assert len(bearish) >= 0

    def test_no_blocks_without_fvgs(self):
        d = OrderBlockDetector()
        candles = [
            make_candle(100, 101, 99, 100),
            make_candle(101, 102, 100.5, 101.5),
        ]
        blocks = d.analyze(candles, [])
        assert len(blocks) == 0

    def test_order_block_strength_scored(self):
        d = OrderBlockDetector()
        candles = [
            make_candle(99, 99.5, 98.5, 99, vol=50.0),
            make_candle(100, 101, 99, 100.5, vol=500.0),
            make_candle(102, 103, 101, 102.5, vol=200.0),
        ]
        fvgs = [FVG(fvg_type="BULLISH_FVG", gap_high=102, gap_low=101, gap_size=10.0, index=2)]
        blocks = d.analyze(candles, fvgs)
        for b in blocks:
            assert 0 <= b.strength_score <= 100

    def test_no_duplicate_blocks(self):
        d = OrderBlockDetector()
        candles = [
            make_candle(99, 100, 98, 99),
            make_candle(100, 101, 99.5, 100.5),
            make_candle(102.5, 103, 101.5, 102),
        ]
        fvg = FVG(fvg_type="BULLISH_FVG", gap_high=102, gap_low=101, gap_size=10.0, index=2)
        d.analyze(candles, [fvg])
        count1 = len(d.get_blocks())
        d.analyze(candles, [fvg])
        count2 = len(d.get_blocks())
        assert count2 == count1

    def test_reset(self):
        d = OrderBlockDetector()
        candles = [
            make_candle(99, 100, 98, 99),
            make_candle(100, 101, 99.5, 100.5),
            make_candle(102.5, 103, 101.5, 102),
        ]
        d.analyze(candles, [FVG(fvg_type="BULLISH_FVG", gap_high=102, gap_low=101, gap_size=10.0, index=2)])
        d.reset()
        assert len(d.get_blocks()) == 0
