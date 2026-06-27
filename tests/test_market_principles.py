"""Tests for all market principle definitions — quality, completeness, categories."""

import re

from ultimate_trader.market_brain.market_principles import (
    BEHAVIORAL_PRINCIPLES,
    LIQUIDITY_PRINCIPLES,
    MANIPULATION_PRINCIPLES,
    ORDERFLOW_PRINCIPLES,
    PROBABILITY_PRINCIPLES,
    REGIME_PRINCIPLES,
    RISK_PRINCIPLES,
    AUCTION_PRINCIPLES,
    VOLATILITY_PRINCIPLES,
    CategoryEnum,
    MarketPrinciple,
    get_all_principles,
    get_all_categories,
)


class TestPrincipleCollections:
    def test_all_collections_have_data(self):
        assert len(AUCTION_PRINCIPLES) > 0
        assert len(LIQUIDITY_PRINCIPLES) > 0
        assert len(ORDERFLOW_PRINCIPLES) > 0
        assert len(VOLATILITY_PRINCIPLES) > 0
        assert len(REGIME_PRINCIPLES) > 0
        assert len(MANIPULATION_PRINCIPLES) > 0
        assert len(BEHAVIORAL_PRINCIPLES) > 0
        assert len(PROBABILITY_PRINCIPLES) > 0
        assert len(RISK_PRINCIPLES) > 0

    def test_get_all_principles_aggregates_all(self):
        total = (
            len(AUCTION_PRINCIPLES)
            + len(LIQUIDITY_PRINCIPLES)
            + len(ORDERFLOW_PRINCIPLES)
            + len(VOLATILITY_PRINCIPLES)
            + len(REGIME_PRINCIPLES)
            + len(MANIPULATION_PRINCIPLES)
            + len(BEHAVIORAL_PRINCIPLES)
            + len(PROBABILITY_PRINCIPLES)
            + len(RISK_PRINCIPLES)
        )
        assert len(get_all_principles()) == total

    def test_all_categories_represented(self):
        all_principles = get_all_principles()
        categories_in_principles = {p.category for p in all_principles}
        for cat in get_all_categories():
            assert cat in categories_in_principles, f"Missing: {cat}"


class TestPrincipleQuality:
    def test_all_principles_have_unique_ids(self):
        all_principles = get_all_principles()
        ids = [p.principle_id for p in all_principles]
        assert len(ids) == len(set(ids)), "Duplicate principle IDs found"

    def test_all_principles_have_non_empty_fields(self):
        for p in get_all_principles():
            assert p.name, f"Empty name: {p.principle_id}"
            assert p.description, f"Empty description: {p.principle_id}"
            assert p.why_it_matters, f"Empty why_it_matters: {p.principle_id}"
            assert p.intraday_relevance, f"Empty intraday_relevance: {p.principle_id}"
            assert p.failure_conditions, f"Empty failure_conditions: {p.principle_id}"

    def test_principle_id_format(self):
        pattern = re.compile(r"^[A-Z]{2,5}-\d{3}$")
        for p in get_all_principles():
            assert pattern.match(
                p.principle_id
            ), f"Invalid ID format: {p.principle_id}"

    def test_principle_id_prefix_matches_category(self):
        prefix_map = {
            "AMT": CategoryEnum.AUCTION_MARKET,
            "LIQ": CategoryEnum.LIQUIDITY,
            "OF": CategoryEnum.ORDER_FLOW,
            "VOL": CategoryEnum.VOLATILITY,
            "REG": CategoryEnum.REGIME,
            "MAN": CategoryEnum.MANIPULATION,
            "BEH": CategoryEnum.BEHAVIORAL,
            "PROB": CategoryEnum.PROBABILITY,
            "RISK": CategoryEnum.RISK,
        }
        for p in get_all_principles():
            prefix = p.principle_id.split("-")[0]
            expected_category = prefix_map.get(prefix)
            assert (
                expected_category == p.category
            ), f"ID {p.principle_id} has prefix {prefix} but category {p.category}"


class TestSpecificPrinciples:
    def test_no_trade_principle_exists(self):
        ids = [p.principle_id for p in REGIME_PRINCIPLES]
        assert "REG-005" in ids

    def test_liquidity_sweep_principle_exists(self):
        ids = [p.principle_id for p in LIQUIDITY_PRINCIPLES]
        assert "LIQ-002" in ids

    def test_compression_expansion_principle_exists(self):
        ids = [p.principle_id for p in VOLATILITY_PRINCIPLES]
        assert "VOL-001" in ids

    def test_all_principles_have_related_observations(self):
        for p in get_all_principles():
            assert len(p.related_observations) > 0, f"Missing observations: {p.principle_id}"
