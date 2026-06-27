from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.orderflow_intelligence.absorption_intelligence import (
    AbsorptionAnalysisResult,
)
from ultimate_trader.orderflow_intelligence.aggression_analyzer import (
    AggressionAnalysisResult,
)
from ultimate_trader.orderflow_intelligence.delta_divergence import (
    DeltaDivergenceResult,
)
from ultimate_trader.orderflow_intelligence.exhaustion_detector import (
    ExhaustionResult,
)
from ultimate_trader.orderflow_intelligence.flow_momentum import (
    FlowMomentumResult,
)
from ultimate_trader.orderflow_intelligence.iceberg_detector import (
    IcebergDetectionResult,
)
from ultimate_trader.orderflow_intelligence.models import OrderFlowState, TrapRisk
from ultimate_trader.orderflow_intelligence.orderflow_scenarios import (
    OrderFlowScenarioReport,
)
from ultimate_trader.orderflow_intelligence.trap_detector import (
    TrapDetectionResult,
)


class TradePermission(str, Enum):
    ALLOW = "ALLOW"
    CAUTION = "CAUTION"
    BLOCK = "BLOCK"


class InstitutionalOrderFlowReport(BaseModel):
    symbol: str
    timestamp: str = ""
    aggression_analysis: Optional[AggressionAnalysisResult] = None
    absorption_analysis: Optional[AbsorptionAnalysisResult] = None
    exhaustion_analysis: Optional[ExhaustionResult] = None
    iceberg_detection: Optional[IcebergDetectionResult] = None
    delta_divergence: Optional[DeltaDivergenceResult] = None
    flow_momentum: Optional[FlowMomentumResult] = None
    trap_detection: Optional[TrapDetectionResult] = None
    scenario_report: Optional[OrderFlowScenarioReport] = None
    orderflow_state: Optional[OrderFlowState] = None
    trade_permission: TradePermission = TradePermission.ALLOW
    final_summary: str = ""
    reasons_to_avoid_trade: list[str] = Field(default_factory=list)
    reasons_supporting_trade: list[str] = Field(default_factory=list)

    @classmethod
    def build(
        cls,
        symbol: str,
        aggression: AggressionAnalysisResult,
        absorption: AbsorptionAnalysisResult,
        exhaustion: ExhaustionResult,
        iceberg: IcebergDetectionResult,
        divergence: DeltaDivergenceResult,
        momentum: FlowMomentumResult,
        trap: TrapDetectionResult,
        scenarios: OrderFlowScenarioReport,
        state: OrderFlowState,
    ) -> "InstitutionalOrderFlowReport":
        reasons_avoid = cls._collect_avoid_reasons(
            aggression, absorption, exhaustion, iceberg, divergence, trap, scenarios
        )
        reasons_support = cls._collect_support_reasons(
            aggression, absorption, exhaustion, iceberg, divergence, trap, scenarios
        )
        permission = cls._determine_permission(trap, absorption, state)
        summary = cls._build_summary(symbol, permission, scenarios, trap)

        return cls(
            symbol=symbol,
            aggression_analysis=aggression,
            absorption_analysis=absorption,
            exhaustion_analysis=exhaustion,
            iceberg_detection=iceberg,
            delta_divergence=divergence,
            flow_momentum=momentum,
            trap_detection=trap,
            scenario_report=scenarios,
            orderflow_state=state,
            trade_permission=permission,
            final_summary=summary,
            reasons_to_avoid_trade=reasons_avoid,
            reasons_supporting_trade=reasons_support,
        )

    @staticmethod
    def _collect_avoid_reasons(
        aggression: AggressionAnalysisResult,
        absorption: AbsorptionAnalysisResult,
        exhaustion: ExhaustionResult,
        iceberg: IcebergDetectionResult,
        divergence: DeltaDivergenceResult,
        trap: TrapDetectionResult,
        scenarios: OrderFlowScenarioReport,
    ) -> list[str]:
        reasons = []
        if absorption.absorption_detected:
            reasons.append(f"Order absorption: {absorption.absorption_summary}")
        if exhaustion.exhaustion_detected:
            reasons.append(f"Exhaustion: {exhaustion.exhaustion_reason}")
        if trap.trap_detected:
            reasons.append(f"Trap risk: {trap.trap_reason}")
        if divergence.divergence_detected:
            reasons.append(f"Divergence: {divergence.interpretation}")
        if scenarios.dominant_scenario == "fake_breakout":
            reasons.append("Fake breakout scenario dominant")
        if iceberg.iceberg_suspected.value in ("HIGH", "MODERATE"):
            reasons.append(f"Iceberg suspicion: {iceberg.explanation}")
        return reasons

    @staticmethod
    def _collect_support_reasons(
        aggression: AggressionAnalysisResult,
        absorption: AbsorptionAnalysisResult,
        exhaustion: ExhaustionResult,
        iceberg: IcebergDetectionResult,
        divergence: DeltaDivergenceResult,
        trap: TrapDetectionResult,
        scenarios: OrderFlowScenarioReport,
    ) -> list[str]:
        reasons = []
        if aggression.aggression_bias.value in ("BUYER_AGGRESSION", "SELLER_AGGRESSION"):
            reasons.append(f"Clear aggression bias: {aggression.aggression_bias.value}")
        if scenarios.dominant_scenario in ("genuine_buyer_accumulation", "genuine_seller_distribution"):
            reasons.append(f"Genuine flow scenario: {scenarios.dominant_scenario}")
        return reasons

    @staticmethod
    def _determine_permission(
        trap: TrapDetectionResult,
        absorption: AbsorptionAnalysisResult,
        state: OrderFlowState,
    ) -> TradePermission:
        if trap.trap_detected and trap.recommended_action.value == "BLOCK_TRADE":
            return TradePermission.BLOCK
        if trap.trap_score > 70:
            return TradePermission.BLOCK
        if absorption.absorption_detected and absorption.absorption_score > 80:
            return TradePermission.CAUTION
        if state.warning_flags:
            return TradePermission.CAUTION
        return TradePermission.ALLOW

    @staticmethod
    def _build_summary(
        symbol: str, permission: TradePermission, scenarios: OrderFlowScenarioReport, trap: TrapDetectionResult
    ) -> str:
        parts = [f"{symbol}: {permission.value}"]
        if scenarios.dominant_scenario:
            parts.append(f"scenario={scenarios.dominant_scenario}")
        if trap.trap_detected:
            parts.append(f"trap={trap.trap_type.value}")
        return " | ".join(parts)
