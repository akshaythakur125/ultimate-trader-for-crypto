from ultimate_trader.liquidity_smart_money.confluence_engine import ConfluenceEngine
from ultimate_trader.liquidity_smart_money.models import (
    DirectionalBias,
    Displacement,
    FVG,
    LiquidityZone,
    OrderBlock,
    PremiumDiscountState,
    StructureEvent,
    StructureType,
    Sweep,
    TradePermission,
)


class TestConfluenceEngine:
    def test_low_score_when_no_factors(self):
        c = ConfluenceEngine()
        r = c.analyze([], [], [], [], [], None, [])
        assert r.confluence_score < 30
        assert r.trade_permission != TradePermission.ALLOW.value

    def test_multiple_factors_increase_score(self):
        c = ConfluenceEngine()
        sweeps = [Sweep(sweep_type="SELL_SIDE_SWEEP", entry_price=100, sweep_low=98, sweep_high=102, has_reclaim=True)]
        structure = [StructureEvent(structure_type=StructureType.BOS, direction="BULLISH", price=100)]
        r = c.analyze([], sweeps, structure, [], [], None, [])
        assert r.confluence_score > 0
        assert len(r.reasons_for) > 0

    def test_fvg_adds_confluence(self):
        c = ConfluenceEngine()
        fvgs = [FVG(fvg_type="BULLISH_FVG", gap_high=102, gap_low=101, gap_size=15.0)]
        r = c.analyze([], [], [], fvgs, [], None, [])
        assert r.confluence_score > 0
        assert "FVG" in " ".join(r.reasons_for)

    def test_order_block_adds_confluence(self):
        c = ConfluenceEngine()
        blocks = [OrderBlock(ob_type="BULLISH_OB", price_high=101, price_low=99, strength_score=75.0)]
        r = c.analyze([], [], [], [], blocks, None, [])
        assert r.confluence_score > 0

    def test_premium_discount_short_bias(self):
        c = ConfluenceEngine()
        pd = PremiumDiscountState(
            dealing_range_high=110, dealing_range_low=90, equilibrium=100,
            premium_zone_high=110, premium_zone_low=100,
            discount_zone_high=100, discount_zone_low=90,
            optimal_entry_high=104, optimal_entry_low=106,
            current_price_zone="PREMIUM",
        )
        r = c.analyze([], [], [], [], [], pd, [])
        assert r.confluence_score > 0

    def test_displacement_adds_confluence(self):
        c = ConfluenceEngine()
        displacements = [Displacement(is_displaced=True, displacement_type="STRONG", direction="UP")]
        r = c.analyze([], [], [], [], [], None, displacements)
        assert r.confluence_score > 0

    def test_orderflow_bias_used(self):
        c = ConfluenceEngine()
        r = c.analyze([], [], [], [], [], None, [], orderflow_bias="BUYER_AGGRESSION")
        assert r.confluence_score > 0

    def test_microstructure_bias_used(self):
        c = ConfluenceEngine()
        r = c.analyze([], [], [], [], [], None, [], microstructure_bias="LONG")
        assert r.confluence_score > 0

    def test_risks_collected(self):
        c = ConfluenceEngine()
        sweeps = [Sweep(sweep_type="BUY_SIDE_SWEEP", entry_price=100, sweep_low=98, sweep_high=102, is_failed=True)]
        r = c.analyze([], sweeps, [], [], [], None, [])
        assert len(r.reasons_against) > 0

    def test_block_permission_when_high_risks(self):
        c = ConfluenceEngine()
        sweeps = [Sweep(sweep_type="BUY_SIDE_SWEEP", entry_price=100, sweep_low=98, sweep_high=102, is_failed=True) for _ in range(3)]
        structure = [StructureEvent(structure_type=StructureType.STRUCTURE_FAILURE, direction="NEUTRAL", price=100)]
        r = c.analyze([], sweeps, structure, [], [], None, [])
        assert r.trade_permission in ("CAUTION", "BLOCK")

    def test_confluence_breakdown_has_keys(self):
        c = ConfluenceEngine()
        r = c.analyze([], [], [], [], [], None, [])
        assert isinstance(r.confluence_breakdown, dict)

    def test_reset(self):
        c = ConfluenceEngine()
        c.analyze([], [], [], [], [], None, [])
        c.reset()
        assert c.get_result() is None
