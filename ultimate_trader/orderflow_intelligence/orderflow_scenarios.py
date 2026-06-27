from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.orderflow_intelligence.models import (
    AggressionBias,
    AbsorptionState,
    ExhaustionState,
    FlowWindow,
    TrapRisk,
)


class FlowScenario(BaseModel):
    name: str
    probability_estimate: float = 0.0
    evidence_for: list[str] = Field(default_factory=list)
    evidence_against: list[str] = Field(default_factory=list)
    invalidation_condition: str = ""


class OrderFlowScenarioReport(BaseModel):
    scenarios: list[FlowScenario] = Field(default_factory=list)
    dominant_scenario: Optional[str] = None
    no_edge_probability: float = 0.0
    scenario_summary: str = ""


class OrderFlowScenarioEngine:
    def __init__(self):
        self.SCENARIO_NAMES = [
            "genuine_buyer_accumulation",
            "genuine_seller_distribution",
            "passive_seller_absorption",
            "passive_buyer_absorption",
            "short_squeeze",
            "long_squeeze",
            "exhaustion_reversal",
            "fake_breakout",
            "no_edge_balanced_flow",
        ]

    def analyze(
        self,
        window: FlowWindow,
        aggression: AggressionBias,
        absorption: AbsorptionState,
        exhaustion: ExhaustionState,
        trap_risk: TrapRisk,
    ) -> OrderFlowScenarioReport:
        scenarios = [
            self._scenario_buyer_accumulation(window, aggression, absorption, trap_risk),
            self._scenario_seller_distribution(window, aggression, absorption, trap_risk),
            self._scenario_passive_seller_absorption(window, aggression, absorption, trap_risk),
            self._scenario_passive_buyer_absorption(window, aggression, absorption, trap_risk),
            self._scenario_short_squeeze(window, aggression, absorption, trap_risk),
            self._scenario_long_squeeze(window, aggression, absorption, trap_risk),
            self._scenario_exhaustion_reversal(window, aggression, absorption, exhaustion),
            self._scenario_fake_breakout(window, aggression, trap_risk),
            self._scenario_no_edge(window, aggression, absorption),
        ]
        scenarios = [s for s in scenarios if s is not None]
        scenarios.sort(key=lambda s: s.probability_estimate, reverse=True)

        dominant = scenarios[0] if scenarios else None
        no_edge = next((s for s in scenarios if s.name == "no_edge_balanced_flow"), None)

        return OrderFlowScenarioReport(
            scenarios=scenarios[:5],
            dominant_scenario=dominant.name if dominant else None,
            no_edge_probability=no_edge.probability_estimate if no_edge else 0.0,
            scenario_summary=self._build_summary(scenarios),
        )

    def _build_summary(self, scenarios: list[FlowScenario]) -> str:
        if not scenarios:
            return "No scenarios generated"
        parts = [f"dominant={scenarios[0].name} ({scenarios[0].probability_estimate:.0f}%)"]
        if len(scenarios) > 1:
            parts.append(f"alt={scenarios[1].name} ({scenarios[1].probability_estimate:.0f}%)")
        return " | ".join(parts)

    def _scenario_buyer_accumulation(
        self, window: FlowWindow, aggression: AggressionBias, absorption: AbsorptionState, trap: TrapRisk
    ) -> Optional[FlowScenario]:
        prob = 10.0
        evidence_for = []
        if aggression == AggressionBias.BUYER_AGGRESSION:
            prob += 25
            evidence_for.append("Aggressive buyer dominance")
        if absorption == AbsorptionState.NO_ABSORPTION:
            prob += 15
            evidence_for.append("No absorption detected — price responding to buying")
        if window.large_trade_count > 3:
            prob += 10
            evidence_for.append("Multiple large trades")
        if trap == TrapRisk.SHORT_TRAP_RISK:
            prob += 5
        if prob < 20:
            return None
        return FlowScenario(
            name="genuine_buyer_accumulation",
            probability_estimate=round(min(prob, 95), 1),
            evidence_for=evidence_for,
            evidence_against=["Price may be at resistance"],
            invalidation_condition="Price reverses below accumulation zone",
        )

    def _scenario_seller_distribution(
        self, window: FlowWindow, aggression: AggressionBias, absorption: AbsorptionState, trap: TrapRisk
    ) -> Optional[FlowScenario]:
        prob = 10.0
        evidence_for = []
        if aggression == AggressionBias.SELLER_AGGRESSION:
            prob += 25
            evidence_for.append("Aggressive seller dominance")
        if absorption == AbsorptionState.NO_ABSORPTION:
            prob += 15
            evidence_for.append("No absorption — price responding to selling")
        if window.large_trade_count > 3:
            prob += 10
            evidence_for.append("Multiple large sell trades")
        if trap == TrapRisk.LONG_TRAP_RISK:
            prob += 5
        if prob < 20:
            return None
        return FlowScenario(
            name="genuine_seller_distribution",
            probability_estimate=round(min(prob, 95), 1),
            evidence_for=evidence_for,
            evidence_against=["Price may be at support"],
            invalidation_condition="Price reverses above distribution zone",
        )

    def _scenario_passive_seller_absorption(
        self, window: FlowWindow, aggression: AggressionBias, absorption: AbsorptionState, trap: TrapRisk
    ) -> Optional[FlowScenario]:
        prob = 10.0
        evidence_for = []
        if absorption == AbsorptionState.BUYING_ABSORBED:
            prob += 30
            evidence_for.append("Buying being absorbed by passive sellers")
        if aggression == AggressionBias.BUYER_AGGRESSION:
            prob += 10
            evidence_for.append("Aggressive buying failing to push price")
        if trap == TrapRisk.LONG_TRAP_RISK:
            prob += 10
        if prob < 20:
            return None
        return FlowScenario(
            name="passive_seller_absorption",
            probability_estimate=round(min(prob, 90), 1),
            evidence_for=evidence_for,
            evidence_against=["Buyers may resume pushing price"],
            invalidation_condition="Price breaks above absorption zone with strong delta",
        )

    def _scenario_passive_buyer_absorption(
        self, window: FlowWindow, aggression: AggressionBias, absorption: AbsorptionState, trap: TrapRisk
    ) -> Optional[FlowScenario]:
        prob = 10.0
        evidence_for = []
        if absorption == AbsorptionState.SELLING_ABSORBED:
            prob += 30
            evidence_for.append("Selling being absorbed by passive buyers")
        if aggression == AggressionBias.SELLER_AGGRESSION:
            prob += 10
            evidence_for.append("Aggressive selling failing to push price")
        if trap == TrapRisk.SHORT_TRAP_RISK:
            prob += 10
        if prob < 20:
            return None
        return FlowScenario(
            name="passive_buyer_absorption",
            probability_estimate=round(min(prob, 90), 1),
            evidence_for=evidence_for,
            evidence_against=["Sellers may resume pushing price"],
            invalidation_condition="Price breaks below absorption zone with strong delta",
        )

    def _scenario_short_squeeze(
        self, window: FlowWindow, aggression: AggressionBias, absorption: AbsorptionState, trap: TrapRisk
    ) -> Optional[FlowScenario]:
        prob = 5.0
        evidence_for = []
        if absorption == AbsorptionState.SELLING_ABSORBED and aggression == AggressionBias.SELLER_AGGRESSION:
            prob += 25
            evidence_for.append("Selling absorbed — trapped shorts may cover")
        if window.buy_sell_delta > 0 and window.total_sell_volume > 0:
            prob += 10
        if trap == TrapRisk.SHORT_TRAP_RISK:
            prob += 15
        if prob < 20:
            return None
        return FlowScenario(
            name="short_squeeze",
            probability_estimate=round(min(prob, 85), 1),
            evidence_for=evidence_for,
            evidence_against=["Distribution may continue"],
            invalidation_condition="Price fails to hold above support",
        )

    def _scenario_long_squeeze(
        self, window: FlowWindow, aggression: AggressionBias, absorption: AbsorptionState, trap: TrapRisk
    ) -> Optional[FlowScenario]:
        prob = 5.0
        evidence_for = []
        if absorption == AbsorptionState.BUYING_ABSORBED and aggression == AggressionBias.BUYER_AGGRESSION:
            prob += 25
            evidence_for.append("Buying absorbed — trapped longs may liquidate")
        if window.buy_sell_delta < 0 and window.total_buy_volume > 0:
            prob += 10
        if trap == TrapRisk.LONG_TRAP_RISK:
            prob += 15
        if prob < 20:
            return None
        return FlowScenario(
            name="long_squeeze",
            probability_estimate=round(min(prob, 85), 1),
            evidence_for=evidence_for,
            evidence_against=["Accumulation may continue"],
            invalidation_condition="Price holds above support",
        )

    def _scenario_exhaustion_reversal(
        self, window: FlowWindow, aggression: AggressionBias, absorption: AbsorptionState, exhaustion: ExhaustionState
    ) -> Optional[FlowScenario]:
        prob = 5.0
        evidence_for = []
        if exhaustion == ExhaustionState.BUYER_EXHAUSTION:
            prob += 25
            evidence_for.append("Buyer exhaustion detected — reversal down possible")
        if exhaustion == ExhaustionState.SELLER_EXHAUSTION:
            prob += 25
            evidence_for.append("Seller exhaustion detected — reversal up possible")
        if absorption != AbsorptionState.NO_ABSORPTION:
            prob += 10
        if prob < 20:
            return None
        return FlowScenario(
            name="exhaustion_reversal",
            probability_estimate=round(min(prob, 80), 1),
            evidence_for=evidence_for,
            evidence_against=["Trend may continue despite fading volume"],
            invalidation_condition="Aggression resumes in original direction",
        )

    def _scenario_fake_breakout(
        self, window: FlowWindow, aggression: AggressionBias, trap: TrapRisk
    ) -> Optional[FlowScenario]:
        prob = 5.0
        evidence_for = []
        if trap in (TrapRisk.LONG_TRAP_RISK, TrapRisk.SHORT_TRAP_RISK):
            prob += 25
            evidence_for.append("Trap risk detected")
        if aggression == AggressionBias.BALANCED:
            prob += 10
            evidence_for.append("No clear aggression despite price move")
        if window.large_trade_count <= 1 and window.trade_count > 10:
            prob += 10
            evidence_for.append("Low large-trade participation in move")
        if prob < 20:
            return None
        return FlowScenario(
            name="fake_breakout",
            probability_estimate=round(min(prob, 80), 1),
            evidence_for=evidence_for,
            evidence_against=["Breakout may be genuine"],
            invalidation_condition="Price continues with strong volume and delta expansion",
        )

    def _scenario_no_edge(
        self, window: FlowWindow, aggression: AggressionBias, absorption: AbsorptionState
    ) -> Optional[FlowScenario]:
        prob = 50.0
        evidence_for = []
        if aggression == AggressionBias.BALANCED:
            prob += 20
            evidence_for.append("Balanced aggression")
        if absorption == AbsorptionState.NO_ABSORPTION:
            prob += 10
        if window.trade_count < 5:
            prob += 10
            evidence_for.append("Insufficient trade data")
        return FlowScenario(
            name="no_edge_balanced_flow",
            probability_estimate=round(min(prob, 90), 1),
            evidence_for=evidence_for,
            evidence_against=["Edge may exist in higher timeframe"],
            invalidation_condition="Clear directional aggression emerges",
        )
