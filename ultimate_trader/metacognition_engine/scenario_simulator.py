import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.cognitive_engine.reasoning_chain import ReasoningChain


class DirectionOutcome(str, Enum):
    LONG_CONTINUATION = "LONG_CONTINUATION"
    SHORT_CONTINUATION = "SHORT_CONTINUATION"
    REVERSAL_UP = "REVERSAL_UP"
    REVERSAL_DOWN = "REVERSAL_DOWN"
    CHOP = "CHOP"
    FAKEOUT = "FAKEOUT"
    NO_TRADE = "NO_TRADE"


class MarketScenario(BaseModel):
    scenario_id: str
    name: str
    description: str
    direction_outcome: DirectionOutcome
    probability_estimate: float = Field(ge=0.0, le=1.0)
    evidence_supporting: list[str] = Field(default_factory=list)
    evidence_against: list[str] = Field(default_factory=list)
    risk_if_wrong: str = ""
    invalidation_trigger: str = ""


class ScenarioSimulationResult(BaseModel):
    simulation_id: str
    target_decision_id: str
    scenarios: list[MarketScenario] = Field(default_factory=list)
    most_likely_scenario: Optional[MarketScenario] = None
    worst_case_scenario: Optional[MarketScenario] = None
    best_case_scenario: Optional[MarketScenario] = None
    probability_weighted_bias: str = "NEUTRAL"
    scenario_conflict_score: float = 0.0
    simulation_summary: str = ""


class ScenarioSimulator:
    def simulate(self, chain: ReasoningChain) -> ScenarioSimulationResult:
        sim_id = f"SIM-{uuid.uuid4().hex[:8].upper()}"
        bias = chain.preliminary_bias

        scenarios = self._generate_scenarios(chain, bias, sim_id)
        normalized = self._normalize_probabilities(scenarios)
        most_likely = max(normalized, key=lambda s: s.probability_estimate)
        worst = self._find_worst_case(normalized, bias)
        best = self._find_best_case(normalized, bias)
        conflict = self._calculate_conflict(normalized)

        return ScenarioSimulationResult(
            simulation_id=sim_id,
            target_decision_id=chain.chain_id,
            scenarios=normalized,
            most_likely_scenario=most_likely,
            worst_case_scenario=worst,
            best_case_scenario=best,
            probability_weighted_bias=self._weighted_bias(normalized),
            scenario_conflict_score=round(conflict, 1),
            simulation_summary=self._build_summary(
                bias, most_likely, worst, conflict
            ),
        )

    def _generate_scenarios(
        self,
        chain: ReasoningChain,
        bias: str,
        sim_id: str = "",
    ) -> list[MarketScenario]:
        ev_count = len(chain.evidence_for)
        missing_count = len(chain.missing_evidence)
        has_contradictions = len(chain.contradictions) > 0
        high_uncertainty = chain.uncertainty_score > 50

        prefix = sim_id[:8] if sim_id else uuid.uuid4().hex[:8]
        base_prob = max(0.1, 0.5 - (missing_count * 0.05) - (0.1 if has_contradictions else 0))

        scenarios = [
            MarketScenario(
                scenario_id=f"SCN-{prefix}_CONT",
                name="Trend Continuation",
                description=f"The current {bias.lower()} bias continues as expected.",
                direction_outcome=DirectionOutcome.LONG_CONTINUATION
                if bias == "LONG"
                else DirectionOutcome.SHORT_CONTINUATION,
                probability_estimate=base_prob,
                evidence_supporting=[
                    e.description for e in chain.evidence_for[:2]
                ],
                evidence_against=[
                    e.description for e in chain.evidence_against[:2]
                ],
                risk_if_wrong="Extended position against the move",
                invalidation_trigger=f"Key support/resistance level breaks in opposite direction",
            ),
            MarketScenario(
                scenario_id=f"SCN-{prefix}_REV",
                name="Reversal",
                description="Price reverses sharply from current direction.",
                direction_outcome=DirectionOutcome.REVERSAL_UP
                if bias == "SHORT"
                else DirectionOutcome.REVERSAL_DOWN,
                probability_estimate=0.25 + (0.1 if has_contradictions else 0) + (0.05 if high_uncertainty else 0),
                evidence_supporting=[],
                evidence_against=[],
                risk_if_wrong="Missing the continuation move",
                invalidation_trigger="Price continues in original direction beyond recent swing point",
            ),
            MarketScenario(
                scenario_id=f"SCN-{prefix}_FAKE",
                name="Fakeout",
                description="The move is a liquidity grab, not a genuine breakout.",
                direction_outcome=DirectionOutcome.FAKEOUT,
                probability_estimate=0.15 + (0.1 if has_contradictions else 0),
                evidence_supporting=[],
                evidence_against=[],
                risk_if_wrong="Wrong direction, trapped in fake move",
                invalidation_trigger="Price reclaims the swept level and continues",
            ),
            MarketScenario(
                scenario_id=f"SCN-{prefix}_CHOP",
                name="Chop / No Trade",
                description="Market becomes directionless and choppy.",
                direction_outcome=DirectionOutcome.CHOP,
                probability_estimate=0.1 + (0.05 if high_uncertainty else 0),
                evidence_supporting=[],
                evidence_against=[],
                risk_if_wrong="Stop loss triggered by noise",
                invalidation_trigger="Price establishes a clear directional range",
            ),
        ]
        return scenarios

    def _normalize_probabilities(
        self, scenarios: list[MarketScenario]
    ) -> list[MarketScenario]:
        total = sum(s.probability_estimate for s in scenarios)
        if total == 0:
            return scenarios
        factor = min(1.0 / total, 10.0)
        for s in scenarios:
            s.probability_estimate = round(s.probability_estimate * factor, 2)
        return scenarios

    def _find_worst_case(
        self,
        scenarios: list[MarketScenario],
        bias: str,
    ) -> Optional[MarketScenario]:
        if bias == "LONG":
            for s in scenarios:
                if s.direction_outcome in (
                    DirectionOutcome.REVERSAL_DOWN,
                    DirectionOutcome.FAKEOUT,
                ):
                    return s
        elif bias == "SHORT":
            for s in scenarios:
                if s.direction_outcome in (
                    DirectionOutcome.REVERSAL_UP,
                    DirectionOutcome.FAKEOUT,
                ):
                    return s
        return scenarios[-1] if scenarios else None

    def _find_best_case(
        self,
        scenarios: list[MarketScenario],
        bias: str,
    ) -> Optional[MarketScenario]:
        if bias == "LONG":
            for s in scenarios:
                if s.direction_outcome == DirectionOutcome.LONG_CONTINUATION:
                    return s
        elif bias == "SHORT":
            for s in scenarios:
                if s.direction_outcome == DirectionOutcome.SHORT_CONTINUATION:
                    return s
        return scenarios[0] if scenarios else None

    def _calculate_conflict(self, scenarios: list[MarketScenario]) -> float:
        if len(scenarios) < 2:
            return 0.0
        probs = [s.probability_estimate for s in scenarios]
        max_prob = max(probs)
        if max_prob < 0.35:
            return 70.0
        if max_prob < 0.5:
            return 40.0
        return 10.0

    def _weighted_bias(self, scenarios: list[MarketScenario]) -> str:
        long_prob = sum(
            s.probability_estimate
            for s in scenarios
            if s.direction_outcome
            in (
                DirectionOutcome.LONG_CONTINUATION,
                DirectionOutcome.REVERSAL_UP,
            )
        )
        short_prob = sum(
            s.probability_estimate
            for s in scenarios
            if s.direction_outcome
            in (
                DirectionOutcome.SHORT_CONTINUATION,
                DirectionOutcome.REVERSAL_DOWN,
            )
        )
        if long_prob > short_prob + 0.1:
            return "LONG"
        if short_prob > long_prob + 0.1:
            return "SHORT"
        return "NEUTRAL"

    def _build_summary(
        self,
        bias: str,
        most_likely: MarketScenario,
        worst: Optional[MarketScenario],
        conflict: float,
    ) -> str:
        parts = [
            f"Most likely: {most_likely.name} ({most_likely.probability_estimate:.0%})"
        ]
        if worst:
            parts.append(f"Worst case: {worst.name}")
        if conflict > 50:
            parts.append("High scenario conflict — outcomes highly uncertain")
        return " | ".join(parts)
