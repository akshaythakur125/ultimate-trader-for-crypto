from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.cognitive_engine.observation import Observation, ObservationType
from ultimate_trader.market_brain.knowledge_base import MarketKnowledgeBase


class MarketInterpretation(BaseModel):
    interpretation_id: str
    symbol: str
    timeframe: str
    interpretation_summary: str
    possible_meanings: list[str] = Field(default_factory=list)
    most_likely_meaning: str = ""
    confidence_score: float = Field(default=50.0, ge=0.0, le=100.0)
    uncertainty_score: float = Field(default=50.0, ge=0.0, le=100.0)
    related_market_principles: list[str] = Field(default_factory=list)


_OBSERVATION_INTERPRETATIONS: dict[ObservationType, list[str]] = {
    ObservationType.PRICE_ACTION: [
        "Price may be trending",
        "Price may be ranging",
        "Price may be rejecting a key level",
        "Price may be breaking out",
    ],
    ObservationType.VOLUME: [
        "Volume confirms participation",
        "Volume is declining — move may be weak",
        "Volume spike may indicate climax",
        "Volume expansion supports the move",
    ],
    ObservationType.LIQUIDITY: [
        "Liquidity sweep may have occurred",
        "Stop cluster likely present",
        "Thin liquidity increases fakeout risk",
        "Liquidity grab may have trapped traders",
    ],
    ObservationType.ORDER_FLOW: [
        "Aggressive buying detected",
        "Aggressive selling detected",
        "Order flow confirms direction",
        "Order flow diverges from price",
    ],
    ObservationType.VOLATILITY: [
        "Volatility is compressing — expansion likely",
        "Volatility is expanding — wider stops needed",
        "Volatility spike may be a liquidity event",
        "Low volatility with rising volume may signal preparation",
    ],
    ObservationType.FUNDING: [
        "Funding is extreme — crowded positioning",
        "Funding is neutral — no crowding signal",
        "Funding flipping direction may signal sentiment shift",
    ],
    ObservationType.OPEN_INTEREST: [
        "OI rising with price — trend supported",
        "OI declining — trend may be exhausting",
        "OI rising in compression — expansion building",
    ],
    ObservationType.REGIME: [
        "Market appears to be trending",
        "Market appears to be ranging or choppy",
        "Market regime is unclear",
        "Manipulation risk is elevated",
    ],
    ObservationType.SENTIMENT: [
        "Sentiment is extreme — contrarian opportunity",
        "Sentiment is neutral — no signal",
        "Retail positioning is extreme",
    ],
    ObservationType.RISK: [
        "Risk level is elevated",
        "Risk level is acceptable",
        "Daily drawdown limits approaching",
    ],
    ObservationType.UNKNOWN: [
        "Observation type not recognized",
        "Insufficient data to interpret",
    ],
}


class InterpretationEngine:
    def __init__(self, kb: MarketKnowledgeBase | None = None) -> None:
        self.kb = kb

    def interpret(self, observation: Observation) -> MarketInterpretation:
        possibilities = _OBSERVATION_INTERPRETATIONS.get(
            observation.observation_type,
            _OBSERVATION_INTERPRETATIONS[ObservationType.UNKNOWN],
        )

        related_principles: list[str] = []
        if self.kb:
            results = self.kb.find_principles_by_condition(
                observation.observation_type.value.lower()
            )
            related_principles = [p.principle_id for p in results]

        return MarketInterpretation(
            interpretation_id=f"INT-{observation.observation_id}",
            symbol=observation.symbol,
            timeframe=observation.timeframe,
            interpretation_summary=f"Observation of type {observation.observation_type.value}: {observation.description}",
            possible_meanings=possibilities,
            most_likely_meaning=possibilities[0] if possibilities else "Unknown",
            confidence_score=observation.reliability_score * 100,
            uncertainty_score=(1.0 - observation.reliability_score) * 100,
            related_market_principles=related_principles,
        )

    def interpret_batch(
        self, observations: list[Observation]
    ) -> list[MarketInterpretation]:
        return [self.interpret(o) for o in observations]
