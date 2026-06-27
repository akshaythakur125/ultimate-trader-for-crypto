import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from ultimate_trader.cognitive_engine.reasoning_chain import ReasoningChain
from ultimate_trader.config.settings import Settings


class FinalRecommendation(str, Enum):
    PROCEED_TO_BACKTEST = "PROCEED_TO_BACKTEST"
    WAIT = "WAIT"
    COLLECT_MORE_DATA = "COLLECT_MORE_DATA"
    REJECT_IDEA = "REJECT_IDEA"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    PAPER_TRADE_ONLY = "PAPER_TRADE_ONLY"
    LIVE_TRADE_BLOCKED = "LIVE_TRADE_BLOCKED"


class TradeReadinessAssessment(BaseModel):
    assessment_id: str
    target_decision_id: str
    ready_for_signal: bool = False
    ready_for_backtest: bool = False
    ready_for_paper_trade: bool = False
    ready_for_live_trade: bool = False
    blocking_reasons: list[str] = Field(default_factory=list)
    readiness_score: float = 0.0
    final_recommendation: FinalRecommendation = FinalRecommendation.WAIT


class TradeReadinessChecker:
    def check(
        self,
        chain: ReasoningChain,
        audit_passed: bool = True,
        settings: Optional[Settings] = None,
    ) -> TradeReadinessAssessment:
        return self.assess(chain, audit_passed, settings)

    def assess(
        self,
        chain: ReasoningChain,
        audit_passed: bool,
        settings: Optional[Settings] = None,
    ) -> TradeReadinessAssessment:
        blocking: list[str] = []
        score = 0.0

        if chain.should_trade:
            score += 20.0
        else:
            blocking.append("Reasoner does not recommend trading")
            score -= 5.0

        if chain.confidence_after >= 60:
            score += 20.0
        elif chain.confidence_after >= 40:
            score += 10.0
        else:
            blocking.append(f"Confidence too low ({chain.confidence_after:.0f})")
            score -= 5.0

        if chain.risk_after <= 50:
            score += 15.0
        elif chain.risk_after <= 70:
            score += 5.0
        else:
            blocking.append(f"Risk too high ({chain.risk_after:.0f})")
            score -= 5.0

        if chain.uncertainty_score <= 40:
            score += 15.0
        elif chain.uncertainty_score <= 60:
            score += 5.0
        else:
            blocking.append(
                f"Uncertainty too high ({chain.uncertainty_score:.0f})"
            )
            score -= 5.0

        if audit_passed:
            score += 10.0
        else:
            blocking.append("Decision audit did not pass")
            score -= 5.0

        if len(chain.contradictions) == 0:
            score += 10.0
        elif len(chain.contradictions) <= 2:
            score += 5.0
        else:
            blocking.append(
                f"Too many contradictions ({len(chain.contradictions)})"
            )
            score -= 5.0

        if not chain.missing_evidence:
            score += 10.0
        elif len(chain.missing_evidence) <= 2:
            score += 5.0
        else:
            blocking.append(
                f"Too much missing evidence ({len(chain.missing_evidence)})"
            )
            score -= 5.0

        score = max(0.0, min(100.0, score))

        live_trading_blocked = True
        if settings and settings.LIVE_TRADING_ENABLED:
            live_trading_blocked = False

        ready_backtest = score >= 40 and not blocking
        ready_paper = score >= 60 and not blocking
        ready_signal = score >= 50 and not blocking
        ready_live = score >= 80 and not blocking and not live_trading_blocked

        if live_trading_blocked:
            blocking.append("Live trading is disabled by safety settings")

        recommendation = self._determine_recommendation(
            score, blocking, ready_signal, ready_backtest, ready_paper, ready_live
        )

        return TradeReadinessAssessment(
            assessment_id=f"TRA-{uuid.uuid4().hex[:8].upper()}",
            target_decision_id=chain.chain_id,
            ready_for_signal=ready_signal,
            ready_for_backtest=ready_backtest,
            ready_for_paper_trade=ready_paper,
            ready_for_live_trade=ready_live,
            blocking_reasons=blocking,
            readiness_score=round(score, 1),
            final_recommendation=recommendation,
        )

    def _determine_recommendation(
        self,
        score: float,
        blocking: list[str],
        ready_signal: bool,
        ready_backtest: bool,
        ready_paper: bool,
        ready_live: bool,
    ) -> FinalRecommendation:
        if ready_live:
            return FinalRecommendation.LIVE_TRADE_BLOCKED
        if ready_paper:
            return FinalRecommendation.PAPER_TRADE_ONLY
        if ready_signal:
            return FinalRecommendation.PROCEED_TO_BACKTEST
        if ready_backtest:
            return FinalRecommendation.PROCEED_TO_BACKTEST
        if "Confidence" in str(blocking):
            return FinalRecommendation.COLLECT_MORE_DATA
        if "Uncertainty" in str(blocking):
            return FinalRecommendation.WAIT
        if "Too many contradictions" in str(blocking):
            return FinalRecommendation.REJECT_IDEA
        if "decision audit" in str(blocking):
            return FinalRecommendation.HUMAN_REVIEW
        if score < 20:
            return FinalRecommendation.REJECT_IDEA
        return FinalRecommendation.WAIT
