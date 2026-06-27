from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.cognitive_engine.hypothesis_reasoning import AlternativeHypothesis


class NextBestAction(str, Enum):
    WAIT = "WAIT"
    COLLECT_MORE_DATA = "COLLECT_MORE_DATA"
    BACKTEST_HYPOTHESIS = "BACKTEST_HYPOTHESIS"
    PREPARE_SIGNAL_CANDIDATE = "PREPARE_SIGNAL_CANDIDATE"
    REJECT_TRADE_IDEA = "REJECT_TRADE_IDEA"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class CognitiveDecisionContext(BaseModel):
    symbol: str
    timeframe: str
    market_summary: str = ""
    dominant_hypothesis: Optional[AlternativeHypothesis] = None
    rejected_hypotheses: list[AlternativeHypothesis] = Field(default_factory=list)
    evidence_summary: str = ""
    contradiction_summary: str = ""
    uncertainty_summary: str = ""
    confidence_score: float = 0.0
    risk_score: float = 0.0
    decision_bias: str = "NO_TRADE"
    requires_human_review: bool = False
    next_best_action: NextBestAction = NextBestAction.WAIT
