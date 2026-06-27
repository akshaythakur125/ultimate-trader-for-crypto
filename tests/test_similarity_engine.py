"""Tests for SimilarityEngine."""

import uuid

from ultimate_trader.memory_engine.case_library import CaseLibrary
from ultimate_trader.memory_engine.market_case import ActionTaken, MarketCase, OutcomeLabel
from ultimate_trader.memory_engine.pattern_signature import PatternSignature
from ultimate_trader.memory_engine.similarity_engine import SimilarityEngine


def _make_sig(
    sig_id: str,
    regime: str = "trending",
    liquidity: str = "normal",
    orderflow: str = "neutral",
    volatility: str = "normal",
    trend: str = "bullish",
    features: dict | None = None,
) -> PatternSignature:
    return PatternSignature(
        signature_id=sig_id,
        symbol="BTCUSDT",
        timeframe="1h",
        regime_label=regime,
        liquidity_state=liquidity,
        orderflow_state=orderflow,
        volatility_state=volatility,
        trend_state=trend,
        feature_vector=features or {},
    )


def _make_case(sig: PatternSignature) -> MarketCase:
    return MarketCase(
        case_id=f"CASE-{uuid.uuid4().hex[:8].upper()}",
        timestamp="2024-01-01T00:00:00Z",
        symbol=sig.symbol,
        timeframe=sig.timeframe,
        pattern_signature=sig,
        reasoning_summary="Test",
        decision_bias="LONG",
        action_taken=ActionTaken.TRADE,
    )


class TestSimilarityEngine:
    def setup_method(self):
        self.engine = SimilarityEngine()

    def test_identical_signatures_score_high(self):
        sig_a = _make_sig("SIG-A", regime="trending", liquidity="normal")
        sig_b = _make_sig("SIG-B", regime="trending", liquidity="normal")
        score = self.engine.compute_similarity(sig_a, sig_b)
        assert score > 90.0

    def test_different_signatures_score_low(self):
        sig_a = _make_sig(
            "SIG-A",
            regime="trending",
            liquidity="normal",
            orderflow="aggressive_buying",
            volatility="expanding",
            trend="bullish",
        )
        sig_b = _make_sig(
            "SIG-B",
            regime="ranging",
            liquidity="thin",
            orderflow="neutral",
            volatility="contracting",
            trend="bearish",
        )
        score = self.engine.compute_similarity(sig_a, sig_b)
        assert score < 50.0

    def test_similarity_respects_numeric_features(self):
        sig_a = _make_sig(
            "SIG-A",
            regime="trending",
            features={
                "trend_strength": 80.0,
                "volatility_score": 30.0,
            },
        )
        sig_b = _make_sig(
            "SIG-B",
            regime="trending",
            features={
                "trend_strength": 75.0,
                "volatility_score": 35.0,
            },
        )
        sig_c = _make_sig(
            "SIG-C",
            regime="trending",
            features={
                "trend_strength": 20.0,
                "volatility_score": 90.0,
            },
        )
        score_ab = self.engine.compute_similarity(sig_a, sig_b)
        score_ac = self.engine.compute_similarity(sig_a, sig_c)
        assert score_ab > score_ac

    def test_find_similar_cases_returns_matches(self):
        target_sig = _make_sig("SIG-TARGET", regime="trending")
        similar_sig = _make_sig("SIG-SIM", regime="trending")
        diff_sig = _make_sig(
            "SIG-DIFF",
            regime="ranging",
            liquidity="thin",
            orderflow="aggressive_selling",
            volatility="contracting",
            trend="bearish",
        )

        lib = CaseLibrary()
        lib.add_case(_make_case(similar_sig))
        lib.add_case(_make_case(diff_sig))

        results = self.engine.find_similar_cases(
            target_sig, lib, min_similarity=70.0
        )
        assert len(results) == 1
        assert results[0].similarity_score >= 70.0

    def test_find_similar_cases_limits_results(self):
        target_sig = _make_sig("SIG-TARGET", regime="trending")
        lib = CaseLibrary()
        for i in range(5):
            s = _make_sig(f"SIG-{i}", regime="trending")
            lib.add_case(_make_case(s))

        results = self.engine.find_similar_cases(
            target_sig, lib, min_similarity=70.0, limit=3
        )
        assert len(results) <= 3

    def test_result_has_matched_and_mismatched(self):
        sig_a = _make_sig(
            "SIG-A",
            regime="trending",
            liquidity="normal",
            orderflow="aggressive_buying",
        )
        sig_b = _make_sig(
            "SIG-B",
            regime="trending",
            liquidity="thin",
            orderflow="neutral",
        )
        lib = CaseLibrary()
        lib.add_case(_make_case(sig_b))
        results = self.engine.find_similar_cases(
            sig_a, lib, min_similarity=0.0
        )
        assert len(results) == 1
        assert "regime_label" in results[0].matched_features
        assert len(results[0].mismatched_features) > 0
