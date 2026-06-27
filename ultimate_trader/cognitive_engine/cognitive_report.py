import uuid
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.cognitive_engine.decision_context import (
    CognitiveDecisionContext,
    NextBestAction,
)
from ultimate_trader.cognitive_engine.hypothesis_reasoning import AlternativeHypothesis
from ultimate_trader.cognitive_engine.reasoning_chain import ReasoningChain


class CognitiveReport(BaseModel):
    report_id: str
    symbol: str
    timeframe: str
    summary: str = ""
    observations_reviewed: int = 0
    hypotheses_considered: int = 0
    strongest_hypothesis: Optional[AlternativeHypothesis] = None
    rejected_hypotheses: list[AlternativeHypothesis] = Field(default_factory=list)
    key_confirmations: list[str] = Field(default_factory=list)
    key_contradictions: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    confidence_score: float = 0.0
    risk_score: float = 0.0
    uncertainty_score: float = 0.0
    recommended_next_action: str = "WAIT"
    explanation: str = ""


class CognitiveReportGenerator:
    def generate(
        self,
        chain: ReasoningChain,
        context: CognitiveDecisionContext,
    ) -> CognitiveReport:
        rejected = [
            h
            for h in chain.alternative_hypotheses
            if h.status.value in ("REJECTED",)
        ]

        confirmations = [
            e.description
            for e in chain.evidence_for
        ]

        contradiction_descriptions = [
            c.get("description", c.get("rule", "unknown"))
            for c in chain.contradictions
        ]

        summary_parts = [
            f"Reviewed {len(chain.observations)} observations across "
            f"{len(chain.alternative_hypotheses)} hypotheses."
        ]
        if chain.should_trade:
            summary_parts.append(
                f"Conditions favor {chain.preliminary_bias} bias."
            )
        else:
            summary_parts.append("Conditions do not favor trading.")
            if chain.reason_not_to_trade:
                summary_parts.append(f"Reason: {chain.reason_not_to_trade}")

        explanation = (
            f"Confidence: {chain.confidence_after:.0f}/100, "
            f"Risk: {chain.risk_after:.0f}/100, "
            f"Uncertainty: {chain.uncertainty_score:.0f}/100. "
        )
        if chain.contradictions:
            explanation += (
                f"Contradictions: {len(chain.contradictions)} detected. "
            )
        if chain.missing_evidence:
            explanation += (
                f"Missing evidence: {len(chain.missing_evidence)} item(s). "
            )

        return CognitiveReport(
            report_id=f"CR-{uuid.uuid4().hex[:8].upper()}",
            symbol=chain.symbol,
            timeframe=chain.timeframe,
            summary=" ".join(summary_parts),
            observations_reviewed=len(chain.observations),
            hypotheses_considered=len(chain.alternative_hypotheses),
            strongest_hypothesis=context.dominant_hypothesis,
            rejected_hypotheses=rejected,
            key_confirmations=confirmations,
            key_contradictions=contradiction_descriptions,
            missing_evidence=chain.missing_evidence,
            confidence_score=chain.confidence_after,
            risk_score=chain.risk_after,
            uncertainty_score=chain.uncertainty_score,
            recommended_next_action=context.next_best_action.value,
            explanation=explanation,
        )
