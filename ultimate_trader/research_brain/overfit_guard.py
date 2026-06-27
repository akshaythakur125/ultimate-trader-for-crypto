from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.research_brain.hypothesis_generator import (
    ResearchHypothesis,
)


class OverfitAssessment(BaseModel):
    overfit_score: float
    risk_level: str  # low, medium, high
    flags: list[str] = Field(default_factory=list)
    recommendation: str = ""


class OverfitGuard:
    def assess(self, hypothesis: ResearchHypothesis) -> OverfitAssessment:
        score = 0.0
        flags = []

        if not hypothesis.invalidating_evidence:
            score += 25.0
            flags.append("No invalidating evidence - cannot be disproven")

        if not hypothesis.required_evidence:
            score += 20.0
            flags.append("No required evidence - too vague to falsify")

        if hypothesis.expected_rr > 5.0 and not hypothesis.supporting_evidence:
            score += 15.0
            flags.append("Unsupported high expected RR")

        if hypothesis.expected_rr > 10.0:
            score += 20.0
            flags.append("Extreme expected RR without justification")

        if not hypothesis.expected_failure_modes:
            score += 15.0
            flags.append("No failure modes considered")

        if hypothesis.regime_dependency == "any":
            score += 5.0
            flags.append("No regime specificity")

        if score >= 60:
            risk = "high"
            recommendation = "Reject or significantly revise this hypothesis"
        elif score >= 30:
            risk = "medium"
            recommendation = "Gather more evidence before committing capital"
        else:
            risk = "low"
            recommendation = "Hypothesis appears reasonably structured"

        return OverfitAssessment(
            overfit_score=min(100.0, score),
            risk_level=risk,
            flags=flags,
            recommendation=recommendation,
        )
