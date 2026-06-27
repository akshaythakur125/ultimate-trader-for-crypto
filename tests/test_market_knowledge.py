"""Tests for the Market Knowledge Base — loading, categories, and queries."""

from ultimate_trader.market_brain.knowledge_base import (
    KnowledgeBaseQuery,
    MarketKnowledgeBase,
    MarketReasoningContext,
)
from ultimate_trader.market_brain.market_principles import (
    CategoryEnum,
    MarketPrinciple,
    get_all_principles,
)


class TestKnowledgeBaseLoading:
    def setup_method(self):
        self.kb = MarketKnowledgeBase()

    def test_knowledge_base_loads(self):
        assert self.kb.is_loaded is True

    def test_knowledge_base_has_principles(self):
        assert self.kb.principle_count > 0

    def test_knowledge_base_returns_all_principles(self):
        all_principles = self.kb.get_all()
        assert len(all_principles) == self.kb.principle_count

    def test_principle_has_required_fields(self):
        for p in self.kb.get_all():
            assert p.principle_id
            assert p.name
            assert p.category in CategoryEnum
            assert p.description
            assert p.why_it_matters
            assert p.intraday_relevance
            assert p.failure_conditions


class TestKnowledgeBaseCategories:
    def setup_method(self):
        self.kb = MarketKnowledgeBase()

    def test_all_categories_have_principles(self):
        for cat in CategoryEnum:
            principles = self.kb.get_by_category(cat)
            assert len(principles) > 0, f"Category {cat.value} has no principles"

    def test_get_principles_by_category(self):
        auction = self.kb.get_by_category(CategoryEnum.AUCTION_MARKET)
        for p in auction:
            assert p.category == CategoryEnum.AUCTION_MARKET


class TestKnowledgeBaseQueries:
    def setup_method(self):
        self.kb = MarketKnowledgeBase()

    def test_find_principles_by_condition(self):
        results = self.kb.find_principles_by_condition("liquidity")
        assert len(results) > 0

    def test_get_principles_for_keyword(self):
        results = self.kb.get_principles_for_keyword("volume")
        assert len(results) > 0

    def test_get_no_trade_principles(self):
        results = self.kb.get_no_trade_principles()
        assert len(results) > 0
        ids = [p.principle_id for p in results]
        assert "REG-005" in ids

    def test_get_liquidity_manipulation_principles(self):
        results = self.kb.get_liquidity_manipulation_principles()
        assert len(results) > 0

    def test_get_volatility_expansion_principles(self):
        results = self.kb.get_volatility_expansion_principles()
        assert len(results) > 0

    def test_knowledge_base_query_with_keywords(self):
        query = KnowledgeBaseQuery(condition="breakout", keywords=["fakeout", "trap"])
        results = self.kb.query(query)
        assert len(results) > 0

    def test_knowledge_base_query_with_category_filter(self):
        query = KnowledgeBaseQuery(
            condition="volume",
            categories=[CategoryEnum.ORDER_FLOW],
        )
        results = self.kb.query(query)
        for p in results:
            assert p.category == CategoryEnum.ORDER_FLOW


class TestKnowledgeBaseHealth:
    def setup_method(self):
        self.kb = MarketKnowledgeBase()

    def test_health_check_returns_dict(self):
        health = self.kb.health_check()
        assert isinstance(health, dict)

    def test_health_check_all_true(self):
        health = self.kb.health_check()
        all_ok = all(health.values())
        failed = [k for k, v in health.items() if not v]
        assert all_ok, f"Health checks failed: {failed}"

    def test_health_check_has_key_checks(self):
        health = self.kb.health_check()
        expected = [
            "knowledge_base_loaded",
            "has_auction_principles",
            "has_liquidity_principles",
            "has_regime_principles",
            "no_trade_principles_available",
            "liquidity_manipulation_principles_available",
            "volatility_expansion_principles_available",
        ]
        for key in expected:
            assert key in health, f"Missing health check: {key}"
