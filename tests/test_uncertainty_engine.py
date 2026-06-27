"""Tests for the UncertaintyEngine — assessing uncertainty from various factors."""

from ultimate_trader.cognitive_engine.observation import Observation, ObservationType
from ultimate_trader.cognitive_engine.uncertainty_engine import UncertaintyEngine


class TestUncertaintyEngine:
    def setup_method(self):
        self.engine = UncertaintyEngine()

    def test_no_observations_high_uncertainty(self):
        result = self.engine.assess_uncertainty(
            observations=[],
        )
        assert result.score >= 30.0

    def test_missing_data_increases_uncertainty(self):
        obs = Observation(
            observation_id="OBS-001",
            symbol="BTCUSDT",
            timeframe="1h",
            observation_type=ObservationType.PRICE_ACTION,
            description="Price action only",
            source="manual",
        )
        result = self.engine.assess_uncertainty(
            observations=[obs],
        )
        assert result.score > 0

    def test_evidence_contradictions_increase_uncertainty(self):
        contradictions = [
            {"rule": "trend_in_chop_regime", "severity": "HIGH"},
            {"rule": "bullish_price_bearish_flow", "severity": "MEDIUM"},
        ]
        result = self.engine.assess_uncertainty(
            observations=[],
            contradictions=contradictions,
        )
        assert result.score >= 20.0

    def test_missing_evidence_increases_uncertainty(self):
        result = self.engine.assess_uncertainty(
            observations=[],
            missing_evidence=["order_flow", "volume", "liquidity"],
        )
        assert result.score >= 10.0

    def test_regime_unclear_increases_uncertainty(self):
        obs = Observation(
            observation_id="OBS-001",
            symbol="BTCUSDT",
            timeframe="1h",
            observation_type=ObservationType.REGIME,
            description="Market regime is unclear",
            source="manual",
        )
        result = self.engine.assess_uncertainty(
            observations=[obs],
        )
        assert result.score >= 10.0

    def test_volatility_spike_increases_uncertainty(self):
        obs = Observation(
            observation_id="OBS-001",
            symbol="BTCUSDT",
            timeframe="15m",
            observation_type=ObservationType.VOLATILITY,
            description="Volatility spike detected",
            source="manual",
        )
        result = self.engine.assess_uncertainty(
            observations=[obs],
        )
        assert result.score >= 8.0

    def test_thin_liquidity_increases_uncertainty(self):
        obs = Observation(
            observation_id="OBS-001",
            symbol="BTCUSDT",
            timeframe="1h",
            observation_type=ObservationType.LIQUIDITY,
            description="Thin liquidity conditions",
            source="manual",
        )
        result = self.engine.assess_uncertainty(
            observations=[obs],
        )
        assert result.score >= 10.0

    def test_missing_orderflow_increases_uncertainty(self):
        obs = Observation(
            observation_id="OBS-001",
            symbol="BTCUSDT",
            timeframe="1h",
            observation_type=ObservationType.PRICE_ACTION,
            description="Price moving",
            source="manual",
        )
        result = self.engine.assess_uncertainty(
            observations=[obs],
        )
        has_flow_factor = any("order flow" in f.lower() for f in result.factors)
        assert has_flow_factor

    def test_uncertainty_capped_at_100(self):
        contradictions = [
            {"rule": "trend_in_chop_regime", "severity": "HIGH"},
            {"rule": "long_high_manipulation_risk", "severity": "HIGH"},
            {"rule": "high_confidence_missing_evidence", "severity": "MEDIUM"},
        ]
        result = self.engine.assess_uncertainty(
            observations=[],
            contradictions=contradictions,
            missing_evidence=["a", "b", "c", "d", "e"],
        )
        assert result.score <= 100.0

    def test_uncertainty_returns_factors(self):
        obs = Observation(
            observation_id="OBS-001",
            symbol="BTCUSDT",
            timeframe="1h",
            observation_type=ObservationType.PRICE_ACTION,
            description="Price action",
            source="manual",
        )
        result = self.engine.assess_uncertainty(
            observations=[obs],
        )
        assert len(result.factors) > 0
