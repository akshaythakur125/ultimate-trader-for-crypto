from pydantic import BaseModel, Field

from ultimate_trader.cognitive_engine.reasoning_chain import ReasoningChain


class OverconfidenceAdjustment(BaseModel):
    original_confidence: float = 50.0
    adjusted_confidence: float = 50.0
    reduction_amount: float = 0.0
    reasons: list[str] = Field(default_factory=list)


class OverconfidenceGuard:
    def evaluate(self, chain: ReasoningChain) -> OverconfidenceAdjustment:
        original = chain.confidence_after
        reduction = 0.0
        reasons: list[str] = []

        if chain.confidence_after > 60 and len(chain.evidence_for) <= 2:
            reduction += 15.0
            reasons.append(
                "High confidence with minimal supporting evidence"
            )

        if len(chain.contradictions) > 0:
            reduction += min(len(chain.contradictions) * 8.0, 20.0)
            reasons.append(
                f"{len(chain.contradictions)} contradiction(s) present"
            )

        if chain.uncertainty_score > 60:
            reduction += 10.0
            reasons.append("High uncertainty reduces confidence justification")

        if chain.missing_evidence:
            reduction += min(len(chain.missing_evidence) * 3.0, 10.0)
            reasons.append("Missing evidence weakens confidence")

        adjusted = max(0.0, original - reduction)
        adjusted = min(100.0, adjusted)

        return OverconfidenceAdjustment(
            original_confidence=original,
            adjusted_confidence=adjusted,
            reduction_amount=round(reduction, 1),
            reasons=reasons,
        )
