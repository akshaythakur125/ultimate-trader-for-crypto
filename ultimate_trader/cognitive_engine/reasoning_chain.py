import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.cognitive_engine.confidence_updater import ConfidenceUpdater
from ultimate_trader.cognitive_engine.contradiction_detector import (
    ContradictionDetector,
)
from ultimate_trader.cognitive_engine.evidence_evaluator import (
    EvidenceEvaluator,
    EvidenceItem,
)
from ultimate_trader.cognitive_engine.hypothesis_reasoning import (
    AlternativeHypothesis,
    HypothesisDirection,
    HypothesisReasoningEngine,
    HypothesisStatus,
)
from ultimate_trader.cognitive_engine.interpretation import (
    InterpretationEngine,
    MarketInterpretation,
)
from ultimate_trader.cognitive_engine.observation import Observation
from ultimate_trader.cognitive_engine.uncertainty_engine import UncertaintyEngine
from ultimate_trader.market_brain.knowledge_base import MarketKnowledgeBase


class ReasoningChain(BaseModel):
    chain_id: str
    symbol: str
    timeframe: str
    observations: list[Observation] = Field(default_factory=list)
    interpretations: list[MarketInterpretation] = Field(default_factory=list)
    alternative_hypotheses: list[AlternativeHypothesis] = Field(default_factory=list)
    evidence_for: list[EvidenceItem] = Field(default_factory=list)
    evidence_against: list[EvidenceItem] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    contradictions: list[dict] = Field(default_factory=list)
    confidence_before: float = 50.0
    confidence_after: float = 50.0
    risk_before: float = 50.0
    risk_after: float = 50.0
    uncertainty_score: float = 50.0
    preliminary_bias: str = "NO_TRADE"
    final_conclusion: str = ""
    should_trade: bool = False
    reason_not_to_trade: Optional[str] = None


class Reasoner:
    def __init__(
        self,
        kb: Optional[MarketKnowledgeBase] = None,
    ) -> None:
        self.kb = kb
        self.interpretation_engine = InterpretationEngine(kb)
        self.hypothesis_engine = HypothesisReasoningEngine()
        self.evidence_evaluator = EvidenceEvaluator()
        self.contradiction_detector = ContradictionDetector(kb)
        self.uncertainty_engine = UncertaintyEngine()
        self.confidence_updater = ConfidenceUpdater()

    def reason(self, observations: list[Observation]) -> ReasoningChain:
        if not observations:
            return self._empty_chain()

        symbol = observations[0].symbol
        timeframe = observations[0].timeframe

        interpretations = self.interpretation_engine.interpret_batch(observations)

        hypotheses = self.hypothesis_engine.generate_hypotheses(observations)

        all_evidence: list[EvidenceItem] = []
        for h in hypotheses:
            items = self.evidence_evaluator.build_evidence_items(observations, h)
            all_evidence.extend(items)

        evidence_for: list[EvidenceItem] = []
        evidence_against: list[EvidenceItem] = []
        for h in hypotheses:
            ef, ea = self.evidence_evaluator.separate_supporting_contradicting(
                all_evidence, h.hypothesis_id
            )
            evidence_for.extend(ef)
            evidence_against.extend(ea)

        all_missing: list[str] = []
        for h in hypotheses:
            missing = self.evidence_evaluator.assess_missing_evidence(observations, h)
            all_missing.extend(missing)

        contradictions = self.contradiction_detector.detect_all(
            observations, hypotheses
        )

        uncertainty_result = self.uncertainty_engine.assess_uncertainty(
            observations=observations,
            contradictions=contradictions,
            missing_evidence=all_missing,
        )

        confidence_before = 50.0
        risk_before = 50.0

        update = self.confidence_updater.update(
            supporting_count=len(evidence_for),
            contradicting_count=len(evidence_against),
            missing_evidence_count=len(all_missing),
            uncertainty_score=uncertainty_result.score,
            warning_count=len(contradictions),
        )

        best_hypothesis = self._select_best_hypothesis(hypotheses, update)

        bias = (
            best_hypothesis.direction_bias.value
            if best_hypothesis
            else HypothesisDirection.NO_TRADE.value
        )

        should_trade, reason_not_to = self._decide_tradeability(
            update, contradictions, best_hypothesis
        )

        conclusion = self._build_conclusion(
            bias, update, contradictions, all_missing, reason_not_to
        )

        return ReasoningChain(
            chain_id=f"CHAIN-{uuid.uuid4().hex[:8].upper()}",
            symbol=symbol,
            timeframe=timeframe,
            observations=observations,
            interpretations=interpretations,
            alternative_hypotheses=hypotheses,
            evidence_for=evidence_for,
            evidence_against=evidence_against,
            missing_evidence=list(set(all_missing)),
            contradictions=contradictions,
            confidence_before=confidence_before,
            confidence_after=update.confidence,
            risk_before=risk_before,
            risk_after=update.risk,
            uncertainty_score=update.uncertainty,
            preliminary_bias=bias,
            final_conclusion=conclusion,
            should_trade=should_trade,
            reason_not_to_trade=reason_not_to,
        )

    def _empty_chain(self) -> ReasoningChain:
        return ReasoningChain(
            chain_id=f"CHAIN-{uuid.uuid4().hex[:8].upper()}",
            symbol="",
            timeframe="",
            final_conclusion="No observations provided.",
            should_trade=False,
            reason_not_to_trade="No data to reason about.",
        )

    def _select_best_hypothesis(
        self,
        hypotheses: list[AlternativeHypothesis],
        update: object,
    ) -> Optional[AlternativeHypothesis]:
        if not hypotheses:
            return None
        return max(
            hypotheses,
            key=lambda h: (
                h.confidence_score if h.status != HypothesisStatus.REJECTED else -1
            ),
        )

    def _decide_tradeability(
        self,
        update: object,
        contradictions: list[dict],
        best_hypothesis: Optional[AlternativeHypothesis],
    ) -> tuple[bool, Optional[str]]:
        reasons: list[str] = []

        if best_hypothesis is None:
            reasons.append("No viable hypothesis")

        elif best_hypothesis.direction_bias == HypothesisDirection.NO_TRADE:
            reasons.append("Best hypothesis recommends no trade")

        elif best_hypothesis.status == HypothesisStatus.REJECTED:
            reasons.append("All hypotheses rejected")

        if update.confidence < 60.0:
            reasons.append(f"Confidence too low ({update.confidence:.0f})")

        if update.risk > 60.0:
            reasons.append(f"Risk too high ({update.risk:.0f})")

        high_severity = [c for c in contradictions if c.get("severity") == "HIGH"]
        if high_severity:
            reasons.append(f"High-severity contradictions: {len(high_severity)}")

        if reasons:
            return False, "; ".join(reasons)

        if best_hypothesis and best_hypothesis.direction_bias in (
            HypothesisDirection.LONG,
            HypothesisDirection.SHORT,
        ):
            return True, None

        return False, "No clear directional bias"

    def _build_conclusion(
        self,
        bias: str,
        update: object,
        contradictions: list[dict],
        missing: list[str],
        reason_not_to: Optional[str],
    ) -> str:
        parts = [f"Directional bias: {bias}."]
        parts.append(
            f"Confidence: {update.confidence:.0f} | "
            f"Risk: {update.risk:.0f} | "
            f"Uncertainty: {update.uncertainty:.0f}"
        )
        if contradictions:
            parts.append(f"Contradictions detected: {len(contradictions)}.")
        if missing:
            parts.append(f"Missing evidence: {len(missing)} item(s).")
        if reason_not_to:
            parts.append(f"Reason not to trade: {reason_not_to}")
        else:
            parts.append("Trade conditions appear favorable.")
        return " ".join(parts)
