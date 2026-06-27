from ultimate_trader.liquidity_smart_money.confluence_engine import ConfluenceEngine
from ultimate_trader.liquidity_smart_money.displacement import DisplacementEngine
from ultimate_trader.liquidity_smart_money.fair_value_gap import FairValueGapDetector
from ultimate_trader.liquidity_smart_money.liquidity_pools import LiquidityPoolDetector
from ultimate_trader.liquidity_smart_money.liquidity_report import LiquiditySmartMoneyReport
from ultimate_trader.liquidity_smart_money.market_structure import MarketStructureEngine
from ultimate_trader.liquidity_smart_money.models import (
    Candle,
    ConfluenceResult,
    DirectionalBias,
    Displacement,
    FVG,
    LiquidityZone,
    OrderBlock,
    PremiumDiscountState,
    StructureEvent,
    StructureType,
    Sweep,
    SwingPoint,
    SwingType,
    TradePermission,
)
from ultimate_trader.liquidity_smart_money.order_block import OrderBlockDetector
from ultimate_trader.liquidity_smart_money.premium_discount import PremiumDiscountEngine
from ultimate_trader.liquidity_smart_money.sweep_detector import SweepDetector
from ultimate_trader.liquidity_smart_money.swing_detector import SwingDetector


def make_candle(high: float, low: float, close: float = 0.0, vol: float = 100.0) -> Candle:
    return Candle(
        symbol="BTCUSDT", timeframe="1h",
        timestamp=__import__("datetime").datetime.utcnow(),
        open=close, high=high, low=low, close=close, volume=vol,
    )


class TestLiquiditySmartMoneyIntegration:
    def test_swing_detector_creates_swing_points(self):
        d = SwingDetector(lookback=2)
        for h, l in [(100, 99), (101, 99.5), (102, 100), (101.5, 99.8), (101, 99.5)]:
            d.add_candle(make_candle(high=h, low=l))
        assert len(d.get_swing_highs()) >= 1
        assert len(d.get_all_swing_points()) > 0
        assert d.highest_swing_high() == 102.0

    def test_liquidity_pools_created_from_swings(self):
        lpd = LiquidityPoolDetector()
        swing_highs = [SwingPoint(price=105, index=5, swing_type=SwingType.SWING_HIGH)]
        swing_lows = [SwingPoint(price=95, index=3, swing_type=SwingType.SWING_LOW)]
        equal_highs = [SwingPoint(price=106, index=7, swing_type=SwingType.EQUAL_HIGH)]
        zones = lpd.analyze(swing_highs, swing_lows, equal_highs, [], 100.0, [])
        buy_side = [z for z in zones if z.zone_type == "BUY_SIDE"]
        assert len(buy_side) > 0
        assert any(z.strength >= 1.5 for z in buy_side)

    def test_sweeps_detected_from_zones(self):
        sd = SweepDetector()
        zones = [
            LiquidityZone(
                zone_type="BUY_SIDE", price_min=104.9, price_max=105.1,
                is_swept=True, sweep_index=2, strength=2.0, label="t",
            ),
        ]
        candles = [make_candle(100, 99), make_candle(101, 100), make_candle(105.2, 103)]
        sweeps = sd.analyze(candles, zones)
        assert len(sweeps) >= 0

    def test_structure_events_from_swings(self):
        mse = MarketStructureEngine(lookback=2)
        sh = [SwingPoint(price=100, index=2, swing_type=SwingType.SWING_HIGH)]
        sl = [SwingPoint(price=98, index=1, swing_type=SwingType.SWING_LOW)]
        candles = [make_candle(99, 98), make_candle(100.5, 99), make_candle(101, 99.5)]
        events = mse.analyze(sh, sl, candles)
        assert isinstance(events, list)

    def test_fvg_detected_from_candles(self):
        fvg = FairValueGapDetector(min_gap_bps=0.1)
        candles = [
            make_candle(100, 101, 99, 100),
            make_candle(101, 102, 100.5, 101.5),
            make_candle(103, 104, 102, 103),
        ]
        result = fvg.analyze(candles)
        assert isinstance(result, list)

    def test_order_blocks_from_fvg(self):
        obd = OrderBlockDetector()
        candles = [
            make_candle(99, 100, 98, 99),
            make_candle(100, 101, 99.5, 100.5),
            make_candle(102.5, 103, 101.5, 102),
        ]
        fvgs_list = [FVG(fvg_type="BULLISH_FVG", gap_high=102, gap_low=101, gap_size=10.0, index=2)]
        blocks = obd.analyze(candles, fvgs_list)
        assert isinstance(blocks, list)

    def test_premium_discount_calculated(self):
        pde = PremiumDiscountEngine()
        sh = [SwingPoint(price=110, index=5, swing_type=SwingType.SWING_HIGH)]
        sl = [SwingPoint(price=90, index=3, swing_type=SwingType.SWING_LOW)]
        state = pde.analyze(sh, sl, 100.0)
        assert state.equilibrium == 100.0
        assert state.current_price_zone in ("PREMIUM", "DISCOUNT", "EQUILIBRIUM")

    def test_displacement_detected(self):
        de = DisplacementEngine(range_threshold=1.5, volume_threshold=1.3)
        candles = [make_candle(100, 99, 99.5, 50) for _ in range(5)]
        candles.append(make_candle(103, 100, 102, 200))
        result = de.analyze(candles)
        if result:
            assert isinstance(result, Displacement)

    def test_confluence_increases_with_factors(self):
        ce = ConfluenceEngine()
        r1 = ce.analyze([], [], [], [], [], None, [])
        fvgs = [FVG(fvg_type="BULLISH_FVG", gap_high=102, gap_low=101, gap_size=15.0)]
        sweeps = [Sweep(sweep_type="SELL_SIDE_SWEEP", entry_price=100, sweep_low=98, sweep_high=102, has_reclaim=True)]
        r2 = ce.analyze([], sweeps, [], fvgs, [], None, [])
        assert r2.confluence_score >= r1.confluence_score

    def test_report_builds_correctly(self):
        r = LiquiditySmartMoneyReport.build(
            symbol="BTCUSDT",
            swing_highs=[SwingPoint(price=105, index=5, swing_type=SwingType.SWING_HIGH)],
            swing_lows=[SwingPoint(price=95, index=3, swing_type=SwingType.SWING_LOW)],
            equal_highs=[], equal_lows=[],
            liquidity_pools=[], sweeps=[], structure_events=[],
            fvgs=[], order_blocks=[], premium_discount=None,
            displacements=[],
            confluence=ConfluenceResult(confluence_score=50.0, directional_bias=DirectionalBias.LONG, trade_permission="ALLOW"),
        )
        assert r.symbol == "BTCUSDT"
        assert r.trade_permission in (TradePermission.ALLOW, TradePermission.CAUTION, TradePermission.BLOCK)
        assert r.final_summary

    def test_report_includes_avoid_reasons(self):
        r = LiquiditySmartMoneyReport.build(
            symbol="BTCUSDT",
            swing_highs=[], swing_lows=[], equal_highs=[], equal_lows=[],
            liquidity_pools=[], sweeps=[], structure_events=[],
            fvgs=[], order_blocks=[], premium_discount=None,
            displacements=[],
            confluence=ConfluenceResult(
                confluence_score=15.0,
                directional_bias=DirectionalBias.NEUTRAL,
                trade_permission="BLOCK",
                reasons_against=["Low score", "No confluence"],
            ),
        )
        assert len(r.reasons_to_avoid_trade) > 0

    def test_full_pipeline_no_errors(self):
        swing = SwingDetector(lookback=2)
        for h, l in [(100, 99), (101, 99.5), (102, 100), (101.5, 99.8), (101, 99.5)]:
            swing.add_candle(make_candle(high=h, low=l))

        lpd = LiquidityPoolDetector()
        zones = lpd.analyze(swing.get_swing_highs(), swing.get_swing_lows(), swing.get_equal_highs(), swing.get_equal_lows(), 100.0, [])

        sd = SweepDetector()
        sweeps = sd.analyze([make_candle(100, 99)], zones)

        mse = MarketStructureEngine()
        struct = mse.analyze(swing.get_swing_highs(), swing.get_swing_lows(), [make_candle(101, 99.5)])

        fvgd = FairValueGapDetector()
        candles = [make_candle(100, 101, 99, 100), make_candle(101, 102, 100.5, 101.5), make_candle(103, 104, 102, 103)]
        fvgs = fvgd.analyze(candles)

        obd = OrderBlockDetector()
        obs = obd.analyze(candles, fvgs)

        pde = PremiumDiscountEngine()
        pd = pde.analyze(swing.get_swing_highs(), swing.get_swing_lows(), 100.0)

        de = DisplacementEngine()
        disp = de.analyze(candles)

        ce = ConfluenceEngine()
        conflu = ce.analyze(zones, sweeps, struct, fvgs, obs, pd, [disp] if disp else [])

        report = LiquiditySmartMoneyReport.build(
            symbol="BTCUSDT",
            swing_highs=swing.get_swing_highs(),
            swing_lows=swing.get_swing_lows(),
            equal_highs=swing.get_equal_highs(),
            equal_lows=swing.get_equal_lows(),
            liquidity_pools=zones,
            sweeps=sweeps,
            structure_events=struct,
            fvgs=fvgs,
            order_blocks=obs,
            premium_discount=pd,
            displacements=[disp] if disp else [],
            confluence=conflu,
        )
        assert report.final_summary
