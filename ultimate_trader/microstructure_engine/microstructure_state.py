from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.microstructure_engine.models import (
    AbsorptionSignal,
    ExecutionRisk,
    ImbalanceBias,
    LiquidityVoid,
    OrderBookSnapshot,
    SpoofingSignal,
    SpreadState,
    DepthState,
    TradePermission,
)


class MicrostructureState(BaseModel):
    symbol: str
    spread_state: SpreadState = SpreadState.NORMAL
    depth_state: DepthState = DepthState.NORMAL
    imbalance_bias: ImbalanceBias = ImbalanceBias.NEUTRAL
    liquidity_voids: list[LiquidityVoid] = Field(default_factory=list)
    absorption: AbsorptionSignal = Field(default_factory=lambda: AbsorptionSignal(detected=False))
    spoofing: SpoofingSignal = Field(default_factory=lambda: SpoofingSignal(detected=False))
    execution_risk: ExecutionRisk = ExecutionRisk.LOW
    trade_permission: TradePermission = TradePermission.ALLOW
    reason: str = ""

    def compute(self, snapshot: OrderBookSnapshot) -> "MicrostructureState":
        return self

    def update(
        self,
        spread_state: SpreadState,
        depth_state: DepthState,
        imbalance_bias: ImbalanceBias,
        liquidity_voids: list[LiquidityVoid],
        absorption: AbsorptionSignal,
        spoofing: SpoofingSignal,
        execution_risk: ExecutionRisk,
    ):
        self.spread_state = spread_state
        self.depth_state = depth_state
        self.imbalance_bias = imbalance_bias
        self.liquidity_voids = liquidity_voids
        self.absorption = absorption
        self.spoofing = spoofing
        self.execution_risk = execution_risk
        self.trade_permission = self._determine_permission()
        self.reason = self._build_reason()

    def _determine_permission(self) -> TradePermission:
        if self.spread_state == SpreadState.TRADE_BLOCKING:
            return TradePermission.BLOCK
        if self.execution_risk == ExecutionRisk.CRITICAL:
            return TradePermission.BLOCK
        if self.spoofing.detected and self.spoofing.risk_level.value in ("HIGH", "MEDIUM"):
            return TradePermission.BLOCK
        if self.absorption.detected:
            return TradePermission.BLOCK

        blockers = 0
        if self.spread_state == SpreadState.WIDE:
            blockers += 1
        if self.execution_risk == ExecutionRisk.HIGH:
            blockers += 1
        if self.depth_state in (DepthState.THIN, DepthState.CRITICAL):
            blockers += 1
        if len(self.liquidity_voids) > 2:
            blockers += 1
        if self.spoofing.detected:
            blockers += 1

        if blockers >= 2:
            return TradePermission.CAUTION

        return TradePermission.ALLOW

    def _build_reason(self) -> str:
        reasons = []
        if self.spread_state != SpreadState.NORMAL:
            reasons.append(f"spread={self.spread_state.value}")
        if self.depth_state != DepthState.NORMAL:
            reasons.append(f"depth={self.depth_state.value}")
        if self.imbalance_bias != ImbalanceBias.NEUTRAL:
            reasons.append(f"bias={self.imbalance_bias.value}")
        if self.liquidity_voids:
            reasons.append(f"voids={len(self.liquidity_voids)}")
        if self.absorption.detected:
            reasons.append(f"absorption={self.absorption.absorption_type}")
        if self.spoofing.detected:
            reasons.append(f"spoofing={self.spoofing.risk_level.value}")
        reasons.append(f"risk={self.execution_risk.value}")
        return " | ".join(reasons)
