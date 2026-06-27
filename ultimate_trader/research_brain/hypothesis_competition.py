from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.research_brain.hypothesis_generator import (
    DirectionBias,
    ResearchHypothesis,
)


class HypothesisCompetitionResult(BaseModel):
    competition_id: str
    symbol: str
    timeframe: str
    hypotheses_compared: list[ResearchHypothesis] = Field(default_factory=list)
    winning_hypothesis: Optional[ResearchHypothesis] = None
    rejected_hypotheses: list[str] = Field(default_factory=list)
    unresolved_hypotheses: list[str] = Field(default_factory=list)
    no_edge_detected: bool = False
    competition_summary: str = ""


class HypothesisCompetitionEngine:
    def compare(
        self,
        hypotheses: list[ResearchHypothesis],
        symbol: str = "",
        timeframe: str = "",
    ) -> HypothesisCompetitionResult:
        active = [h for h in hypotheses if h.status not in ("FALSIFIED", "REJECTED")]
        no_trade = [h for h in active if h.direction_bias == DirectionBias.NO_TRADE]
        directional = [h for h in active if h.direction_bias != DirectionBias.NO_TRADE]

        if not directional:
            no_trade_h = no_trade[0] if no_trade else None
            return HypothesisCompetitionResult(
                competition_id="HC-001",
                symbol=symbol,
                timeframe=timeframe,
                hypotheses_compared=hypotheses,
                winning_hypothesis=no_trade_h,
                rejected_hypotheses=[],
                no_edge_detected=len(directional) == 0,
                competition_summary="No directional hypotheses survived filtering",
            )

        scored = []
        for h in directional:
            score = self._score_hypothesis(h)
            scored.append((h, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        top_h = scored[0][0]

        rejected = [h.name for h, s in scored if s < 30]
        unresolved = [h.name for h, s in scored if 30 <= s < 50]

        if scored[0][1] < 40:
            return HypothesisCompetitionResult(
                competition_id="HC-002",
                symbol=symbol,
                timeframe=timeframe,
                hypotheses_compared=hypotheses,
                winning_hypothesis=no_trade[0] if no_trade else top_h,
                rejected_hypotheses=[h.name for h, _ in scored],
                no_edge_detected=True,
                competition_summary="No hypothesis scored above minimum threshold",
            )

        top_h.status = "COMPETING"

        return HypothesisCompetitionResult(
            competition_id="HC-003",
            symbol=symbol,
            timeframe=timeframe,
            hypotheses_compared=hypotheses,
            winning_hypothesis=top_h,
            rejected_hypotheses=rejected,
            unresolved_hypotheses=unresolved,
            no_edge_detected=False,
            competition_summary=(
                f"Winner: {top_h.name} (score {scored[0][1]:.0f}). "
                f"{len(rejected)} rejected, {len(unresolved)} unresolved"
            ),
        )

    def _score_hypothesis(self, h: ResearchHypothesis) -> float:
        score = 50.0
        if h.expected_rr > 2.0:
            score += 10.0
        if h.required_evidence:
            score += min(len(h.required_evidence) * 5.0, 15.0)
        if h.invalidating_evidence:
            score += len(h.invalidating_evidence) * 3.0
        if h.expected_failure_modes:
            score -= len(h.expected_failure_modes) * 2.0
        if h.regime_dependency and h.regime_dependency != "any":
            score += 5.0
        return max(0.0, min(100.0, score))
