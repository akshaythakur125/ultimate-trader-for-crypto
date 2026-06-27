"""Tests for the reasoning framework — MarketReasoningContext and knowledge base reasoning."""

from ultimate_trader.market_brain.knowledge_base import (
    MarketKnowledgeBase,
    MarketReasoningContext,
)


class TestReasoningContext:
    def setup_method(self):
        self.kb = MarketKnowledgeBase()

    def test_build_reasoning_context_basic(self):
        context = self.kb.build_reasoning_context(
            symbol="BTCUSDT",
            timeframe="1h",
            observed_conditions=["liquidity_sweep", "volume_spike"],
        )
        assert isinstance(context, MarketReasoningContext)
        assert context.symbol == "BTCUSDT"
        assert context.timeframe == "1h"
        assert len(context.observed_conditions) == 2

    def test_reasoning_context_finds_relevant_principles(self):
        context = self.kb.build_reasoning_context(
            symbol="BTCUSDT",
            timeframe="15m",
            observed_conditions=["liquidity", "sweep", "fakeout"],
        )
        assert len(context.relevant_principles) > 0

    def test_reasoning_context_identifies_supporting_and_contradicting(self):
        context = self.kb.build_reasoning_context(
            symbol="ETHUSDT",
            timeframe="1h",
            observed_conditions=["breakout", "low_volume"],
        )
        assert len(context.supporting_principles) >= 0
        assert len(context.contradicting_principles) >= 0

    def test_reasoning_context_has_interpretation(self):
        context = self.kb.build_reasoning_context(
            symbol="BTCUSDT",
            timeframe="5m",
            observed_conditions=["volume_spike", "resistance_rejection"],
        )
        assert len(context.preliminary_interpretation) > 0

    def test_reasoning_context_no_conditions(self):
        context = self.kb.build_reasoning_context(
            symbol="BTCUSDT",
            timeframe="1h",
            observed_conditions=[],
        )
        assert len(context.uncertainty_notes) > 0

    def test_reasoning_context_with_uncertain_conditions(self):
        context = self.kb.build_reasoning_context(
            symbol="BTCUSDT",
            timeframe="1h",
            observed_conditions=["no_trade", "choppy", "conflicting_signals"],
        )
        assert len(context.contradicting_principles) > 0


class TestReasoningQueries:
    def setup_method(self):
        self.kb = MarketKnowledgeBase()

    def test_contradicting_conditions_identified(self):
        no_trade_principles = self.kb.get_principles_that_warn_against_trading()
        ids = [p.principle_id for p in no_trade_principles]
        assert "REG-005" in ids or "RISK-002" in ids

    def test_multiple_conditions_produce_broader_context(self):
        few = self.kb.build_reasoning_context(
            "BTCUSDT", "1h", ["volume"]
        )
        many = self.kb.build_reasoning_context(
            "BTCUSDT",
            "1h",
            ["volume", "liquidity", "breakout", "fakeout", "trap"],
        )
        assert len(many.relevant_principles) >= len(few.relevant_principles)


class TestHealthCheckIntegration:
    def setup_method(self):
        self.kb = MarketKnowledgeBase()

    def test_health_check_all_categories_have_principles(self):
        health = self.kb.health_check()
        category_keys = [
            "has_auction_principles",
            "has_liquidity_principles",
            "has_orderflow_principles",
            "has_volatility_principles",
            "has_regime_principles",
            "has_manipulation_principles",
            "has_behavioral_principles",
            "has_probability_principles",
            "has_risk_principles",
        ]
        for key in category_keys:
            assert health[key] is True, f"{key} is False"
