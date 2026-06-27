import uuid
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.cognitive_engine.decision_context import CognitiveDecisionContext
from ultimate_trader.cognitive_engine.reasoning_chain import ReasoningChain


class SelfCritique(BaseModel):
    critique_id: str
    target_decision_id: str
    strongest_argument_for_trade: str = ""
    strongest_argument_against_trade: str = ""
    ignored_risks: list[str] = Field(default_factory=list)
    missing_confirmations: list[str] = Field(default_factory=list)
    possible_failure_modes: list[str] = Field(default_factory=list)
    critique_summary: str = ""
    should_reduce_confidence: bool = False
    should_reject_trade: bool = False


class SelfCritiqueEngine:
    def critique(
        self,
        chain: ReasoningChain,
        context: Optional[CognitiveDecisionContext] = None,
    ) -> SelfCritique:
        critique_id = f"SC-{uuid.uuid4().hex[:8].upper()}"

        arguments_for = self._build_argument_for(chain, context)
        arguments_against = self._build_argument_against(chain, context)
        ignored_risks = self._find_ignored_risks(chain, context)
        missing = self._find_missing_confirmations(chain)
        failure_modes = self._build_failure_modes(chain, context)

        should_reduce = chain.uncertainty_score > 60 or len(missing) > 3
        should_reject = (
            chain.reason_not_to_trade is not None
            or chain.uncertainty_score > 80
            or len(chain.contradictions) > 3
        )

        summary_parts = []
        if arguments_for:
            summary_parts.append(f"For: {arguments_for}")
        if arguments_against:
            summary_parts.append(f"Against: {arguments_against}")
        if not should_reject and not should_reduce:
            summary_parts.append("Critique passed — no major concerns.")
        elif should_reject:
            summary_parts.append("Critique recommends rejection.")

        return SelfCritique(
            critique_id=critique_id,
            target_decision_id=chain.chain_id,
            strongest_argument_for_trade=arguments_for,
            strongest_argument_against_trade=arguments_against,
            ignored_risks=ignored_risks,
            missing_confirmations=missing,
            possible_failure_modes=failure_modes,
            critique_summary=" | ".join(summary_parts),
            should_reduce_confidence=should_reduce,
            should_reject_trade=should_reject,
        )

    def _build_argument_for(
        self,
        chain: ReasoningChain,
        context: Optional[CognitiveDecisionContext],
    ) -> str:
        parts = []
        if chain.evidence_for:
            parts.append(f"{len(chain.evidence_for)} supporting evidence item(s)")
        if chain.confidence_after > 60:
            parts.append(f"confidence is {chain.confidence_after:.0f}/100")
        if chain.preliminary_bias != "NO_TRADE":
            parts.append(f"bias is {chain.preliminary_bias}")
        return "; ".join(parts) if parts else "No strong argument for trade."

    def _build_argument_against(
        self,
        chain: ReasoningChain,
        context: Optional[CognitiveDecisionContext],
    ) -> str:
        parts = []
        if chain.reason_not_to_trade:
            parts.append(chain.reason_not_to_trade)
        if chain.contradictions:
            parts.append(f"{len(chain.contradictions)} contradiction(s) detected")
        if chain.uncertainty_score > 50:
            parts.append(f"uncertainty is {chain.uncertainty_score:.0f}/100")
        if chain.missing_evidence:
            parts.append(f"{len(chain.missing_evidence)} missing evidence item(s)")
        return "; ".join(parts) if parts else "No strong argument against."

    def _find_ignored_risks(
        self,
        chain: ReasoningChain,
        context: Optional[CognitiveDecisionContext],
    ) -> list[str]:
        risks: list[str] = []
        high_severity = [
            c for c in chain.contradictions if c.get("severity") == "HIGH"
        ]
        for c in high_severity:
            risks.append(f"High-severity contradiction: {c.get('rule', 'unknown')}")
        if chain.uncertainty_score > 70 and chain.should_trade:
            risks.append("Trading despite very high uncertainty")
        return risks

    def _find_missing_confirmations(self, chain: ReasoningChain) -> list[str]:
        return chain.missing_evidence[:5]

    def _build_failure_modes(
        self,
        chain: ReasoningChain,
        context: Optional[CognitiveDecisionContext],
    ) -> list[str]:
        modes: list[str] = []
        if chain.uncertainty_score > 60:
            modes.append("High uncertainty leads to unpredictable outcome")
        if chain.missing_evidence:
            modes.append(f"Missing key evidence: {', '.join(chain.missing_evidence[:3])}")
        for c in chain.contradictions:
            modes.append(c.get("description", "Contradiction present"))
        if chain.confidence_after < 50:
            modes.append("Low confidence suggests edge is weak or absent")
        return modes[:5]
