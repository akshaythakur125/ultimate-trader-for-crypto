import uuid
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.research_brain.hypothesis_generator import (
    ResearchHypothesis,
)


class PredictivePowerScore(BaseModel):
    predictive_power_score: float
    score_id: str
    hypothesis_id: str
    reasoning: str = ""
    confidence: str = "medium"


class PredictivePowerScorer:
    def score(self, hypothesis: ResearchHypothesis) -> PredictivePowerScore:
        score = 50.0
        reasoning = []

        if hypothesis.expected_market_behavior:
            score += 15.0
            reasoning.append("Specific market behavior predicted")

        if hypothesis.required_evidence:
            score += min(len(hypothesis.required_evidence) * 5.0, 15.0)
            reasoning.append(
                f"{len(hypothesis.required_evidence)} required evidence items defined"
            )

        if hypothesis.invalidating_evidence:
            score += 10.0
            reasoning.append("Falsifiable via defined invalidating evidence")

        if hypothesis.expected_failure_modes:
            score += 5.0
            reasoning.append(f"{len(hypothesis.expected_failure_modes)} failure modes considered")

        if hypothesis.expected_rr > 0:
            score += 5.0
            reasoning.append(f"Expected RR: {hypothesis.expected_rr}")

        if hypothesis.regime_dependency and hypothesis.regime_dependency != "any":
            score += 5.0
            reasoning.append("Tied to specific market regime")

        confidence = "high" if score >= 80 else "medium" if score >= 50 else "low"

        return PredictivePowerScore(
            predictive_power_score=min(100.0, max(0.0, score)),
            score_id=f"PPS-{uuid.uuid4().hex[:8].upper()}",
            hypothesis_id=hypothesis.research_id,
            reasoning="; ".join(reasoning),
            confidence=confidence,
        )
