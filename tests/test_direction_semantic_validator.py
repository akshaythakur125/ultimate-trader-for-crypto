"""DirectionSemanticValidator: explicit tests for directional bias semantics.

Verifies that confluence engine correctly maps market conditions to
LONG/SHORT/NEUTRAL directional bias per ICT/Smart Money principles.
"""

import pytest
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


def make_sweep(sweep_type: str, has_reclaim: bool = True) -> Sweep:
    return Sweep(
        sweep_type=sweep_type,
        entry_price=100.0,
        sweep_low=98.0 if "SELL" in sweep_type else 102.0,
        sweep_high=102.0 if "BUY" in sweep_type else 98.0,
        has_reclaim=has_reclaim,
    )


def make_structure(stype: StructureType, direction: str = "") -> StructureEvent:
    return StructureEvent(structure_type=stype, direction=direction, price=100.0)


def make_fvg(fvg_type: str, gap_size: float = 10.0) -> FVG:
    return FVG(fvg_type=fvg_type, gap_high=102.0, gap_low=98.0, gap_size=gap_size)


def make_ob(ob_type: str, strength: float = 75.0) -> OrderBlock:
    return OrderBlock(ob_type=ob_type, price_high=101.0, price_low=99.0, strength_score=strength)


def make_pd(zone: str) -> PremiumDiscountState:
    return PremiumDiscountState(
        dealing_range_high=110, dealing_range_low=90, equilibrium=100,
        premium_zone_high=110, premium_zone_low=100,
        discount_zone_high=100, discount_zone_low=90,
        optimal_entry_high=104, optimal_entry_low=106,
        current_price_zone=zone,
    )


def make_displacement(direction: str, dtype: str = "STRONG") -> Displacement:
    return Displacement(is_displaced=True, displacement_type=dtype, direction=direction)


class TestDirectionSemanticValidator:

    # ====== BUY-SIDE SWEEP ======

    def test_buy_side_sweep_no_reclaim_neutral(self):
        """Buy-side sweep without reclaim should NOT be LONG; return NEUTRAL."""
        c = ConfluenceEngine()
        sweeps = [make_sweep("BUY_SIDE_SWEEP", has_reclaim=False)]
        r = c.analyze([], sweeps, [], [], [], None, [])
        assert r.directional_bias == DirectionalBias.NEUTRAL, (
            f"Expected NEUTRAL for buy-side sweep without reclaim, got {r.directional_bias}"
        )

    def test_buy_side_sweep_with_reclaim_short(self):
        """Buy-side sweep with reclaim should signal SHORT (reversal)."""
        c = ConfluenceEngine()
        sweeps = [make_sweep("BUY_SIDE_SWEEP", has_reclaim=True)]
        r = c.analyze([], sweeps, [], [], [], None, [])
        assert r.directional_bias == DirectionalBias.SHORT, (
            f"Expected SHORT for buy-side sweep with reclaim, got {r.directional_bias}"
        )

    # ====== SELL-SIDE SWEEP ======

    def test_sell_side_sweep_no_reclaim_neutral(self):
        """Sell-side sweep without reclaim should NOT be SHORT; return NEUTRAL."""
        c = ConfluenceEngine()
        sweeps = [make_sweep("SELL_SIDE_SWEEP", has_reclaim=False)]
        r = c.analyze([], sweeps, [], [], [], None, [])
        assert r.directional_bias == DirectionalBias.NEUTRAL, (
            f"Expected NEUTRAL for sell-side sweep without reclaim, got {r.directional_bias}"
        )

    def test_sell_side_sweep_with_reclaim_long(self):
        """Sell-side sweep with reclaim should signal LONG (reversal)."""
        c = ConfluenceEngine()
        sweeps = [make_sweep("SELL_SIDE_SWEEP", has_reclaim=True)]
        r = c.analyze([], sweeps, [], [], [], None, [])
        assert r.directional_bias == DirectionalBias.LONG, (
            f"Expected LONG for sell-side sweep with reclaim, got {r.directional_bias}"
        )

    # ====== BULLISH/BEARISH SCENARIOS ======

    def test_bullish_scenario_returns_long(self):
        """Multiple bullish components should yield LONG."""
        c = ConfluenceEngine()
        sweeps = [make_sweep("SELL_SIDE_SWEEP")]
        structure = [make_structure(StructureType.BOS, direction="BULLISH")]
        fvgs = [make_fvg("BULLISH_FVG")]
        r = c.analyze([], sweeps, structure, fvgs, [], None, [])
        assert r.directional_bias == DirectionalBias.LONG, (
            f"Expected LONG for bullish scenario, got {r.directional_bias}"
        )

    def test_bearish_scenario_returns_short(self):
        """Multiple bearish components should yield SHORT."""
        c = ConfluenceEngine()
        sweeps = [make_sweep("BUY_SIDE_SWEEP")]
        structure = [make_structure(StructureType.CHOCH, direction="BEARISH")]
        fvgs = [make_fvg("BEARISH_FVG")]
        r = c.analyze([], sweeps, structure, fvgs, [], None, [])
        assert r.directional_bias == DirectionalBias.SHORT, (
            f"Expected SHORT for bearish scenario, got {r.directional_bias}"
        )

    # ====== CONFLICT HANDLING ======

    def test_conflicting_components_return_neutral(self):
        """Conflicting components (buy-side sweep + bullish structure) should yield NEUTRAL."""
        c = ConfluenceEngine()
        sweeps = [make_sweep("BUY_SIDE_SWEEP")]
        structure = [make_structure(StructureType.BOS, direction="BULLISH")]
        fvgs = [make_fvg("BULLISH_FVG")]
        r = c.analyze([], sweeps, structure, fvgs, [], None, [])
        assert r.directional_bias == DirectionalBias.NEUTRAL, (
            f"Expected NEUTRAL for conflict, got {r.directional_bias}"
        )

    def test_conflicting_components_high_conflict_score(self):
        """Conflicting components should produce high conflict_score."""
        c = ConfluenceEngine()
        sweeps = [make_sweep("BUY_SIDE_SWEEP")]
        structure = [make_structure(StructureType.BOS, direction="BULLISH")]
        r = c.analyze([], sweeps, structure, [], [], None, [])
        assert r.conflict_score >= 0.3, f"Expected conflict_score >= 0.3, got {r.conflict_score}"

    def test_conflicting_components_block_permission(self):
        """High conflict should result in BLOCK permission."""
        c = ConfluenceEngine()
        sweeps = [make_sweep("BUY_SIDE_SWEEP")]
        structure = [make_structure(StructureType.BOS, direction="BULLISH")]
        r = c.analyze([], sweeps, structure, [], [], None, [])
        assert r.trade_permission == TradePermission.BLOCK.value, (
            f"Expected BLOCK for conflict, got {r.trade_permission}"
        )

    def test_unanimous_vote_allows_trade(self):
        """All components voting same direction should ALLOW."""
        c = ConfluenceEngine()
        sweeps = [make_sweep("BUY_SIDE_SWEEP")]
        structure = [make_structure(StructureType.CHOCH, direction="BEARISH")]
        fvgs = [make_fvg("BEARISH_FVG")]
        r = c.analyze([], sweeps, structure, fvgs, [], None, [])
        assert r.directional_bias == DirectionalBias.SHORT
        assert r.conflict_score < 0.3
        assert r.trade_permission != TradePermission.BLOCK.value

    # ====== DISPLACEMENT ======

    def test_displacement_up_long(self):
        """Displacement up should support LONG direction."""
        c = ConfluenceEngine()
        sweeps = [make_sweep("SELL_SIDE_SWEEP")]
        disp = [make_displacement("UP")]
        r = c.analyze([], sweeps, [], [], [], None, disp)
        assert r.directional_bias == DirectionalBias.LONG

    def test_displacement_down_short(self):
        """Displacement down should support SHORT direction."""
        c = ConfluenceEngine()
        sweeps = [make_sweep("BUY_SIDE_SWEEP")]
        disp = [make_displacement("DOWN")]
        r = c.analyze([], sweeps, [], [], [], None, disp)
        assert r.directional_bias == DirectionalBias.SHORT

    # ====== PREMIUM / DISCOUNT ======

    def test_premium_penalizes_long(self):
        """Premium zone should not force SHORT, but contributes to SHORT vote."""
        c = ConfluenceEngine()
        pd = make_pd("PREMIUM")
        r = c.analyze([], [], [], [], [], pd, [])
        assert r.directional_bias in (DirectionalBias.SHORT, DirectionalBias.NEUTRAL)

    def test_discount_penalizes_short(self):
        """Discount zone should not force LONG, but contributes to LONG vote."""
        c = ConfluenceEngine()
        pd = make_pd("DISCOUNT")
        r = c.analyze([], [], [], [], [], pd, [])
        assert r.directional_bias in (DirectionalBias.LONG, DirectionalBias.NEUTRAL)

    # ====== SWEEP + ORDER BLOCK ======

    def test_sell_sweep_plus_bullish_ob_long(self):
        """Sell-side sweep + bullish OB should yield LONG."""
        c = ConfluenceEngine()
        sweeps = [make_sweep("SELL_SIDE_SWEEP")]
        obs = [make_ob("BULLISH_OB")]
        r = c.analyze([], sweeps, [], [], obs, None, [])
        assert r.directional_bias == DirectionalBias.LONG

    def test_buy_sweep_plus_bearish_ob_short(self):
        """Buy-side sweep + bearish OB should yield SHORT."""
        c = ConfluenceEngine()
        sweeps = [make_sweep("BUY_SIDE_SWEEP")]
        obs = [make_ob("BEARISH_OB")]
        r = c.analyze([], sweeps, [], [], obs, None, [])
        assert r.directional_bias == DirectionalBias.SHORT

    # ====== ORDERFLOW / MICROSTRUCTURE ======

    def test_orderflow_buyer_long(self):
        """Buyer aggression orderflow should vote LONG."""
        c = ConfluenceEngine()
        sweeps = [make_sweep("SELL_SIDE_SWEEP")]
        r = c.analyze([], sweeps, [], [], [], None, [], orderflow_bias="BUYER_AGGRESSION")
        assert r.directional_bias == DirectionalBias.LONG

    def test_orderflow_seller_short(self):
        """Seller aggression orderflow should vote SHORT."""
        c = ConfluenceEngine()
        sweeps = [make_sweep("BUY_SIDE_SWEEP")]
        r = c.analyze([], sweeps, [], [], [], None, [], orderflow_bias="SELLER_AGGRESSION")
        assert r.directional_bias == DirectionalBias.SHORT

    def test_microstructure_confirms_direction(self):
        """Microstructure bias should confirm direction."""
        c = ConfluenceEngine()
        sweeps = [make_sweep("SELL_SIDE_SWEEP")]
        r = c.analyze([], sweeps, [], [], [], None, [], microstructure_bias="LONG")
        assert r.directional_bias == DirectionalBias.LONG

    # ====== NEW FIELD PRESENCE ======

    def test_result_has_new_fields(self):
        """ConfluenceResult should have all new diagnostic fields."""
        c = ConfluenceEngine()
        r = c.analyze([], [], [], [], [], None, [])
        assert hasattr(r, "directional_confidence")
        assert hasattr(r, "reversal_risk_score")
        assert hasattr(r, "continuation_score")
        assert hasattr(r, "conflict_score")
        assert hasattr(r, "reason_for_direction")

    def test_buy_sweep_reversal_risk_nonzero(self):
        """Buy-side sweep should produce non-zero reversal risk."""
        c = ConfluenceEngine()
        sweeps = [make_sweep("BUY_SIDE_SWEEP")]
        r = c.analyze([], sweeps, [], [], [], None, [])
        assert r.reversal_risk_score > 0

    def test_bullish_scenario_continuation_nonzero(self):
        """Bullish structure events should produce non-zero continuation score."""
        c = ConfluenceEngine()
        structure = [make_structure(StructureType.BOS, direction="BULLISH")]
        r = c.analyze([], [], structure, [], [], None, [])
        assert r.continuation_score > 0

    # ====== CONFLUENCE DOES NOT APPROVE WITH CONFLICT ======

    def test_no_trade_when_conflicting_liquidity_and_structure(self):
        """Confluence should BLOCK trade when liquidity and structure conflict."""
        c = ConfluenceEngine()
        sweeps = [make_sweep("BUY_SIDE_SWEEP")]
        structure = [make_structure(StructureType.BOS, direction="BULLISH")]
        r = c.analyze([], sweeps, structure, [], [], None, [])
        assert r.trade_permission == TradePermission.BLOCK.value, (
            f"Expected BLOCK for conflicting liquidity/structure, got {r.trade_permission}"
        )

    def test_confluence_no_trade_when_low_score_and_neutral(self):
        """Confluence should not approve when score is low and bias is NEUTRAL."""
        c = ConfluenceEngine()
        r = c.analyze([], [], [], [], [], None, [])
        assert r.trade_permission in (TradePermission.BLOCK.value, TradePermission.CAUTION.value)
