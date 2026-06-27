"""Tests for the TradeReadinessChecker."""

from ultimate_trader.cognitive_engine.reasoning_chain import ReasoningChain
from ultimate_trader.metacognition_engine.trade_readiness import (
    FinalRecommendation,
    TradeReadinessChecker,
)


class TestTradeReadinessChecker:
    def setup_method(self):
        self.checker = TradeReadinessChecker()

    def test_live_trade_blocked_by_default(self):
        chain = ReasoningChain(
            chain_id="CHAIN-001",
            symbol="BTCUSDT",
            timeframe="1h",
            confidence_after=80.0,
            uncertainty_score=20.0,
            should_trade=True,
        )
        assessment = self.checker.check(chain)
        assert assessment.ready_for_live_trade is False
        assert assessment.final_recommendation == FinalRecommendation.PAPER_TRADE_ONLY

    def test_assessment_includes_blocking_reasons(self):
        chain = ReasoningChain(
            chain_id="CHAIN-002",
            symbol="ETHUSDT",
            timeframe="15m",
            confidence_after=50.0,
            uncertainty_score=50.0,
            should_trade=False,
        )
        assessment = self.checker.check(chain)
        assert len(assessment.blocking_reasons) > 0

    def test_recommends_wait_when_not_ready(self):
        chain = ReasoningChain(
            chain_id="CHAIN-003",
            symbol="BTCUSDT",
            timeframe="1h",
            should_trade=False,
        )
        assessment = self.checker.check(chain)
        assert assessment.final_recommendation == FinalRecommendation.WAIT

    def test_next_action_suggested(self):
        chain = ReasoningChain(
            chain_id="CHAIN-004",
            symbol="BTCUSDT",
            timeframe="1h",
        )
        assessment = self.checker.check(chain)
        assert len(assessment.final_recommendation.value) > 0
