import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.cognitive_engine.reasoning_chain import ReasoningChain


class BiasType(str, Enum):
    CONFIRMATION_BIAS = "CONFIRMATION_BIAS"
    OVERCONFIDENCE = "OVERCONFIDENCE"
    RECENCY_BIAS = "RECENCY_BIAS"
    FORCED_TRADE = "FORCED_TRADE"
    REVENGE_TRADING = "REVENGE_TRADING"
    CROWD_FOLLOWING = "CROWD_FOLLOWING"
    ANCHORING = "ANCHORING"
    NONE = "NONE"


class BiasDetection(BaseModel):
    bias_report_id: str
    target_decision_id: str
    detected_biases: list[BiasType] = Field(default_factory=list)
    confirmation_bias_score: float = 0.0
    overconfidence_score: float = 0.0
    recency_bias_score: float = 0.0
    forced_trade_score: float = 0.0
    revenge_trade_risk_score: float = 0.0
    crowd_following_risk_score: float = 0.0
    bias_summary: str = ""
    recommended_action: str = ""


class BiasDetector:
    def detect(self, chain: ReasoningChain) -> BiasDetection:
        detected: list[BiasType] = []

        confirm_bias = self._score_confirmation_bias(chain)
        overconf = self._score_overconfidence(chain)
        forced = self._score_forced_trade(chain)
        recency = self._score_recency_bias(chain)
        revenge = self._score_revenge_trade(chain)
        crowd = self._score_crowd_following(chain)
        anchor = self._score_anchoring(chain)

        for bias_type, score in [
            (BiasType.CONFIRMATION_BIAS, confirm_bias),
            (BiasType.OVERCONFIDENCE, overconf),
            (BiasType.FORCED_TRADE, forced),
            (BiasType.RECENCY_BIAS, recency),
            (BiasType.REVENGE_TRADING, revenge),
            (BiasType.CROWD_FOLLOWING, crowd),
            (BiasType.ANCHORING, anchor),
        ]:
            if score > 50:
                detected.append(bias_type)

        if not detected:
            detected.append(BiasType.NONE)

        summary = self._build_summary(detected, chain)
        action = self._recommend_action(detected, chain)

        return BiasDetection(
            bias_report_id=f"BD-{uuid.uuid4().hex[:8].upper()}",
            target_decision_id=chain.chain_id,
            detected_biases=detected,
            confirmation_bias_score=round(confirm_bias, 1),
            overconfidence_score=round(overconf, 1),
            recency_bias_score=round(recency, 1),
            forced_trade_score=round(forced, 1),
            revenge_trade_risk_score=round(revenge, 1),
            crowd_following_risk_score=round(crowd, 1),
            bias_summary=summary,
            recommended_action=action,
        )

    def _score_confirmation_bias(self, chain: ReasoningChain) -> float:
        score = 0.0
        if len(chain.evidence_for) > 0 and len(chain.evidence_against) == 0:
            score += 40.0
        if len(chain.evidence_for) > len(chain.evidence_against) * 3:
            score += 20.0
        if chain.should_trade and len(chain.contradictions) > 0:
            score += 15.0
        return min(score, 100.0)

    def _score_overconfidence(self, chain: ReasoningChain) -> float:
        score = 0.0
        if chain.confidence_after > 70 and len(chain.evidence_for) <= 2:
            score += 40.0
        if chain.confidence_after > 60 and chain.uncertainty_score > 50:
            score += 25.0
        if chain.confidence_after > chain.confidence_before + 30:
            score += 20.0
        return min(score, 100.0)

    def _score_forced_trade(self, chain: ReasoningChain) -> float:
        score = 0.0
        if chain.should_trade and chain.uncertainty_score > 60:
            score += 40.0
        if chain.should_trade and len(chain.missing_evidence) > 3:
            score += 20.0
        if chain.should_trade and chain.risk_after > 60:
            score += 20.0
        return min(score, 100.0)

    def _score_recency_bias(self, chain: ReasoningChain) -> float:
        return 0.0

    def _score_revenge_trade(self, chain: ReasoningChain) -> float:
        return 0.0

    def _score_crowd_following(self, chain: ReasoningChain) -> float:
        return 0.0

    def _score_anchoring(self, chain: ReasoningChain) -> float:
        return 0.0

    def _build_summary(
        self,
        detected: list[BiasType],
        chain: ReasoningChain,
    ) -> str:
        if BiasType.NONE in detected and len(detected) == 1:
            return "No significant biases detected."
        bias_names = [b.value for b in detected if b != BiasType.NONE]
        return f"Detected biases: {', '.join(bias_names)}. Review recommended."

    def _recommend_action(
        self,
        detected: list[BiasType],
        chain: ReasoningChain,
    ) -> str:
        if BiasType.FORCED_TRADE in detected:
            return "REJECT_OR_REDUCE — forced trade risk detected"
        if BiasType.OVERCONFIDENCE in detected:
            return "REDUCE_CONFIDENCE — confidence exceeds evidence"
        if BiasType.CONFIRMATION_BIAS in detected:
            return "SEEK_CONTRARY_EVIDENCE — actively look for counterarguments"
        if len(detected) > 1 and BiasType.NONE not in detected:
            return "HUMAN_REVIEW — multiple biases detected"
        return "NO_ACTION_NEEDED"
