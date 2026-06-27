from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.liquidity_smart_money.models import (
    ConfluenceResult,
    DirectionalBias,
    Displacement,
    FVG,
    LiquidityZone,
    OrderBlock,
    PremiumDiscountState,
    StructureEvent,
    Sweep,
    SwingPoint,
    TradePermission,
)


class LiquiditySmartMoneyReport(BaseModel):
    symbol: str
    timeframe: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    swing_highs: list[SwingPoint] = Field(default_factory=list)
    swing_lows: list[SwingPoint] = Field(default_factory=list)
    equal_highs: list[SwingPoint] = Field(default_factory=list)
    equal_lows: list[SwingPoint] = Field(default_factory=list)
    liquidity_pools: list[LiquidityZone] = Field(default_factory=list)
    sweeps: list[Sweep] = Field(default_factory=list)
    structure_events: list[StructureEvent] = Field(default_factory=list)
    fvgs: list[FVG] = Field(default_factory=list)
    order_blocks: list[OrderBlock] = Field(default_factory=list)
    premium_discount_state: Optional[PremiumDiscountState] = None
    displacements: list[Displacement] = Field(default_factory=list)
    confluence: Optional[ConfluenceResult] = None
    directional_bias: DirectionalBias = DirectionalBias.NEUTRAL
    trade_permission: TradePermission = TradePermission.ALLOW
    reasons_to_avoid_trade: list[str] = Field(default_factory=list)
    final_summary: str = ""

    @classmethod
    def build(
        cls,
        symbol: str,
        swing_highs: list[SwingPoint],
        swing_lows: list[SwingPoint],
        equal_highs: list[SwingPoint],
        equal_lows: list[SwingPoint],
        liquidity_pools: list[LiquidityZone],
        sweeps: list[Sweep],
        structure_events: list[StructureEvent],
        fvgs: list[FVG],
        order_blocks: list[OrderBlock],
        premium_discount: Optional[PremiumDiscountState],
        displacements: list[Displacement],
        confluence: ConfluenceResult,
        timeframe: str = "",
    ) -> "LiquiditySmartMoneyReport":
        summary_parts = [
            f"{symbol}: {confluence.trade_permission}",
            f"score={confluence.confluence_score}/100",
            f"bias={confluence.directional_bias.value}",
        ]
        if sweeps:
            summary_parts.append(f"sweeps={len(sweeps)}")
        if structure_events:
            summary_parts.append(f"structures={len(structure_events)}")
        if fvgs:
            count_active = sum(1 for f in fvgs if not f.is_filled and not f.is_mitigated)
            summary_parts.append(f"active_fvgs={count_active}")

        return cls(
            symbol=symbol,
            timeframe=timeframe,
            swing_highs=swing_highs,
            swing_lows=swing_lows,
            equal_highs=equal_highs,
            equal_lows=equal_lows,
            liquidity_pools=liquidity_pools,
            sweeps=sweeps,
            structure_events=structure_events,
            fvgs=fvgs,
            order_blocks=order_blocks,
            premium_discount_state=premium_discount,
            displacements=displacements,
            confluence=confluence,
            directional_bias=confluence.directional_bias,
            trade_permission=TradePermission(confluence.trade_permission),
            reasons_to_avoid_trade=confluence.reasons_against,
            final_summary=" | ".join(summary_parts),
        )
