"""Tests for PatternSignature model."""

from ultimate_trader.memory_engine.pattern_signature import PatternSignature


class TestPatternSignature:
    def test_signature_created(self):
        sig = PatternSignature(
            signature_id="SIG-001",
            symbol="BTCUSDT",
            timeframe="1h",
            regime_label="trending",
            liquidity_state="normal",
            orderflow_state="aggressive_buying",
            volatility_state="expanding",
            trend_state="bullish",
        )
        assert sig.signature_id == "SIG-001"
        assert sig.regime_label == "trending"

    def test_signature_with_all_fields(self):
        sig = PatternSignature(
            signature_id="SIG-002",
            symbol="ETHUSDT",
            timeframe="15m",
            regime_label="ranging",
            liquidity_state="thin",
            orderflow_state="neutral",
            volatility_state="contracting",
            trend_state="bearish",
            funding_state="neutral",
            open_interest_state="rising",
            manipulation_risk_state="elevated",
            compression_state="high",
            feature_vector={
                "trend_strength": 75.0,
                "volatility_score": 30.0,
                "compression_score": 85.0,
                "liquidity_score": 20.0,
            },
        )
        assert sig.funding_state == "neutral"
        assert sig.feature_vector["trend_strength"] == 75.0

    def test_signature_defaults(self):
        sig = PatternSignature(
            signature_id="SIG-003",
            symbol="BTCUSDT",
            timeframe="1h",
            regime_label="volatile",
            liquidity_state="normal",
            orderflow_state="neutral",
            volatility_state="expanding",
            trend_state="mixed",
        )
        assert sig.funding_state is None
        assert sig.feature_vector == {}
