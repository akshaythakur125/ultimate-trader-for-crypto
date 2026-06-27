from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.cognitive_engine.observation import Observation, ObservationType


class HypothesisDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"
    NO_TRADE = "NO_TRADE"


class HypothesisStatus(str, Enum):
    ACTIVE = "ACTIVE"
    WEAK = "WEAK"
    REJECTED = "REJECTED"
    NEEDS_MORE_DATA = "NEEDS_MORE_DATA"


class AlternativeHypothesis(BaseModel):
    hypothesis_id: str
    name: str
    description: str
    direction_bias: HypothesisDirection
    required_evidence: list[str] = Field(default_factory=list)
    invalidating_evidence: list[str] = Field(default_factory=list)
    supporting_observations: list[str] = Field(default_factory=list)
    contradicting_observations: list[str] = Field(default_factory=list)
    confidence_score: float = Field(default=0.0, ge=0.0, le=100.0)
    risk_score: float = Field(default=0.0, ge=0.0, le=100.0)
    uncertainty_score: float = Field(default=100.0, ge=0.0, le=100.0)
    status: HypothesisStatus = HypothesisStatus.ACTIVE


_OBSERVATION_TO_HYPOTHESIS: dict[ObservationType, list[dict]] = {
    ObservationType.PRICE_ACTION: [
        {
            "name": "Trend Continuation",
            "description": "Price action suggests the ongoing trend will continue.",
            "direction": HypothesisDirection.LONG,
        },
        {
            "name": "Trend Reversal",
            "description": "Price action suggests the ongoing trend may reverse.",
            "direction": HypothesisDirection.SHORT,
        },
        {
            "name": "Range Bound",
            "description": "Price is expected to remain within a range.",
            "direction": HypothesisDirection.NEUTRAL,
        },
    ],
    ObservationType.VOLUME: [
        {
            "name": "Volume Confirmation",
            "description": "Volume confirms the directional move — trend likely valid.",
            "direction": HypothesisDirection.LONG,
        },
        {
            "name": "Volume Exhaustion",
            "description": "Volume spike with stalled price suggests potential reversal.",
            "direction": HypothesisDirection.SHORT,
        },
    ],
    ObservationType.LIQUIDITY: [
        {
            "name": "Liquidity Sweep Reversal",
            "description": "Sweep of obvious level may precede reversal.",
            "direction": HypothesisDirection.LONG,
        },
        {
            "name": "Breakout Continuation",
            "description": "Liquidity sweep may be a stop run before continuation.",
            "direction": HypothesisDirection.SHORT,
        },
    ],
    ObservationType.ORDER_FLOW: [
        {
            "name": "Order Flow Confirmation",
            "description": "Order flow supports directional movement.",
            "direction": HypothesisDirection.LONG,
        },
        {
            "name": "Order Flow Divergence",
            "description": "Order flow diverges from price — potential reversal.",
            "direction": HypothesisDirection.SHORT,
        },
    ],
    ObservationType.VOLATILITY: [
        {
            "name": "Volatility Expansion Breakout",
            "description": "Compression resolved — directional expansion underway.",
            "direction": HypothesisDirection.LONG,
        },
        {
            "name": "Volatility Spike Reversal",
            "description": "Volatility spike without volume may fade.",
            "direction": HypothesisDirection.SHORT,
        },
    ],
    ObservationType.REGIME: [
        {
            "name": "Regime Supports Trend",
            "description": "Current regime is favorable for trend following.",
            "direction": HypothesisDirection.LONG,
        },
        {
            "name": "Regime Warns No Trade",
            "description": "Current regime is unfavorable — avoid trading.",
            "direction": HypothesisDirection.NO_TRADE,
        },
    ],
}


class HypothesisReasoningEngine:
    def generate_hypotheses(
        self, observations: list[Observation]
    ) -> list[AlternativeHypothesis]:
        hypotheses: list[AlternativeHypothesis] = []
        seen_names: set[str] = set()

        for obs in observations:
            templates = _OBSERVATION_TO_HYPOTHESIS.get(
                obs.observation_type, []
            )
            for tmpl in templates:
                name = tmpl["name"]
                if name not in seen_names:
                    seen_names.add(name)
                    hypotheses.append(
                        AlternativeHypothesis(
                            hypothesis_id=f"HYP-COG-{len(hypotheses)+1:03d}",
                            name=name,
                            description=tmpl["description"],
                            direction_bias=tmpl["direction"],
                            supporting_observations=[obs.observation_id],
                        )
                    )
                else:
                    for h in hypotheses:
                        if h.name == name:
                            h.supporting_observations.append(obs.observation_id)

        if not hypotheses:
            hypotheses.append(
                AlternativeHypothesis(
                    hypothesis_id="HYP-COG-001",
                    name="Insufficient Data",
                    description="Not enough observations to form a hypothesis.",
                    direction_bias=HypothesisDirection.NO_TRADE,
                    status=HypothesisStatus.NEEDS_MORE_DATA,
                )
            )

        return hypotheses
