import uuid
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.cognitive_engine.decision_context import CognitiveDecisionContext
from ultimate_trader.cognitive_engine.reasoning_chain import ReasoningChain
from ultimate_trader.schemas.decision import IntelligenceDecision


class DecisionAudit(BaseModel):
    audit_id: str
    target_decision_id: str
    evidence_quality_score: float = 0.0
    contradiction_score: float = 0.0
    uncertainty_score: float = 0.0
    risk_alignment_score: float = 0.0
    rr_realism_score: float = 0.0
    confidence_justification_score: float = 0.0
    forced_trade_risk_score: float = 0.0
    audit_passed: bool = False
    audit_summary: str = ""
    required_corrections: list[str] = Field(default_factory=list)


class DecisionAuditor:
    def audit(
        self,
        chain: ReasoningChain,
        context: Optional[CognitiveDecisionContext] = None,
    ) -> DecisionAudit:
        audit_id = f"DA-{uuid.uuid4().hex[:8].upper()}"

        evidence_quality = self._score_evidence_quality(chain)
        contradiction = self._score_contradictions(chain)
        uncertainty = chain.uncertainty_score
        risk_align = self._score_risk_alignment(chain)
        rr_realism = self._score_rr_realism(chain)
        conf_just = self._score_confidence_justification(chain)
        forced = self._score_forced_trade_risk(chain)

        corrections: list[str] = []
        if evidence_quality < 50:
            corrections.append("Collect more supporting evidence")
        if contradiction > 60:
            corrections.append("Address high-severity contradictions")
        if uncertainty > 70:
            corrections.append("Reduce uncertainty before proceeding")
        if risk_align < 50:
            corrections.append("Improve risk alignment")
        if rr_realism < 50:
            corrections.append("Review target realism")
        if conf_just < 50:
            corrections.append("Re-evaluate confidence justification")
        if forced > 60:
            corrections.append("Do not force trade — wait for better conditions")

        passed = (
            evidence_quality >= 40
            and contradiction <= 70
            and uncertainty <= 70
            and risk_align >= 40
            and conf_just >= 40
            and forced <= 70
        )

        summary_parts = []
        if passed:
            summary_parts.append("Audit passed")
        else:
            summary_parts.append("Audit flagged issues")
        summary_parts.append(f"Evidence: {evidence_quality:.0f}")
        summary_parts.append(f"Contradictions: {contradiction:.0f}")
        summary_parts.append(f"Uncertainty: {uncertainty:.0f}")
        summary_parts.append(f"Forced trade risk: {forced:.0f}")

        return DecisionAudit(
            audit_id=audit_id,
            target_decision_id=chain.chain_id,
            evidence_quality_score=round(evidence_quality, 1),
            contradiction_score=round(contradiction, 1),
            uncertainty_score=round(uncertainty, 1),
            risk_alignment_score=round(risk_align, 1),
            rr_realism_score=round(rr_realism, 1),
            confidence_justification_score=round(conf_just, 1),
            forced_trade_risk_score=round(forced, 1),
            audit_passed=passed,
            audit_summary=" | ".join(summary_parts),
            required_corrections=corrections,
        )

    def _score_evidence_quality(self, chain: ReasoningChain) -> float:
        score = 50.0
        score += min(len(chain.evidence_for) * 10.0, 30.0)
        score -= len(chain.missing_evidence) * 5.0
        return max(0.0, min(100.0, score))

    def _score_contradictions(self, chain: ReasoningChain) -> float:
        score = 0.0
        for c in chain.contradictions:
            severity = c.get("severity", "LOW")
            if severity == "HIGH":
                score += 25.0
            elif severity == "MEDIUM":
                score += 15.0
            else:
                score += 5.0
        return min(score, 100.0)

    def _score_risk_alignment(self, chain: ReasoningChain) -> float:
        if chain.risk_after == 0:
            return 50.0
        score = 100.0 - chain.risk_after
        return max(0.0, score)

    def _score_rr_realism(self, chain: ReasoningChain) -> float:
        return 50.0

    def _score_confidence_justification(self, chain: ReasoningChain) -> float:
        if len(chain.evidence_for) == 0:
            return 20.0
        ratio = chain.confidence_after / max(len(chain.evidence_for) * 20.0, 1)
        return max(0.0, min(100.0, ratio * 50.0))

    def _score_forced_trade_risk(self, chain: ReasoningChain) -> float:
        score = 0.0
        if chain.should_trade and chain.uncertainty_score > 60:
            score += 35.0
        if chain.should_trade and len(chain.missing_evidence) > 2:
            score += 20.0
        if chain.should_trade and chain.risk_after > 60:
            score += 20.0
        if len(chain.contradictions) > 1 and chain.should_trade:
            score += 15.0
        return min(score, 100.0)
