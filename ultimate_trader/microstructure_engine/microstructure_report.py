from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.microstructure_engine.microstructure_state import (
    MicrostructureState,
)
from ultimate_trader.microstructure_engine.models import (
    AbsorptionSignal,
    ExecutionRisk,
    ImbalanceBias,
    OrderBookSnapshot,
    SpoofingSignal,
    SpreadState,
    DepthState,
    TradePermission,
)


class MicrostructureReport(BaseModel):
    report_id: str
    symbol: str
    order_book_condition: str = ""
    liquidity_quality: str = ""
    execution_risk: ExecutionRisk = ExecutionRisk.LOW
    directional_bias: ImbalanceBias = ImbalanceBias.NEUTRAL
    reasons_to_avoid: list[str] = Field(default_factory=list)
    permission: TradePermission = TradePermission.ALLOW
    summary: str = ""

    @classmethod
    def from_state(
        cls,
        report_id: str,
        symbol: str,
        state: MicrostructureState,
    ) -> "MicrostructureReport":
        reasons = cls._collect_reasons(state)
        condition = cls._describe_book_condition(state)
        liquidity = cls._describe_liquidity(state)
        summary = cls._build_summary(symbol, state)

        return cls(
            report_id=report_id,
            symbol=symbol,
            order_book_condition=condition,
            liquidity_quality=liquidity,
            execution_risk=state.execution_risk,
            directional_bias=state.imbalance_bias,
            reasons_to_avoid=reasons,
            permission=state.trade_permission,
            summary=summary,
        )

    @staticmethod
    def _collect_reasons(state: MicrostructureState) -> list[str]:
        reasons = []
        if state.spread_state == SpreadState.TRADE_BLOCKING:
            reasons.append("Spread is trade-blocking wide")
        elif state.spread_state == SpreadState.WIDE:
            reasons.append("Spread is wider than normal")
        elif state.spread_state == SpreadState.UNSTABLE:
            reasons.append("Spread is unstable")
        if state.depth_state in (DepthState.THIN, DepthState.CRITICAL):
            reasons.append("Order book depth is thin or critical")
        if state.depth_state == DepthState.IMBALANCED:
            reasons.append("Order book is heavily imbalanced")
        if state.liquidity_voids:
            reasons.append(f"{len(state.liquidity_voids)} liquidity voids detected")
        if state.absorption.detected:
            reasons.append(f"Order absorption: {state.absorption.description}")
        if state.spoofing.detected:
            reasons.append(f"Spoofing risk: {state.spoofing.reason}")
        if state.execution_risk in (ExecutionRisk.HIGH, ExecutionRisk.CRITICAL):
            reasons.append(f"Execution risk is {state.execution_risk.value}")
        return reasons

    @staticmethod
    def _describe_book_condition(state: MicrostructureState) -> str:
        parts = [f"spread={state.spread_state.value}"]
        parts.append(f"depth={state.depth_state.value}")
        parts.append(f"bias={state.imbalance_bias.value}")
        if state.absorption.detected:
            parts.append("ABSORPTION")
        if state.spoofing.detected:
            parts.append("SPOOFING")
        return " | ".join(parts)

    @staticmethod
    def _describe_liquidity(state: MicrostructureState) -> str:
        liquidity_parts = []
        if state.depth_state == DepthState.NORMAL:
            liquidity_parts.append("adequate")
        else:
            liquidity_parts.append(state.depth_state.value.lower())
        if state.liquidity_voids:
            liquidity_parts.append(f"{len(state.liquidity_voids)} voids")
        if state.execution_risk != ExecutionRisk.LOW:
            liquidity_parts.append(f"risk={state.execution_risk.value}")
        return " | ".join(liquidity_parts) if liquidity_parts else "unknown"

    @staticmethod
    def _build_summary(symbol: str, state: MicrostructureState) -> str:
        if state.trade_permission == TradePermission.BLOCK:
            return (
                f"{symbol}: TRADE BLOCKED — "
                f"{'spread blocking' if state.spread_state == SpreadState.TRADE_BLOCKING else ''}"
                f"{'absorption detected' if state.absorption.detected else ''}"
                f"{'spoofing risk' if state.spoofing.detected else ''}"
                f"{'critical execution risk' if state.execution_risk == ExecutionRisk.CRITICAL else ''}"
            )
        if state.trade_permission == TradePermission.CAUTION:
            return (
                f"{symbol}: CAUTION — {len(state.liquidity_voids)} voids, "
                f"depth={state.depth_state.value}, risk={state.execution_risk.value}"
            )
        return (
            f"{symbol}: ALLOW — spread={state.spread_state.value}, "
            f"depth={state.depth_state.value}, bias={state.imbalance_bias.value}"
        )
