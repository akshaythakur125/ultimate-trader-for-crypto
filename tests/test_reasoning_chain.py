"""Tests for the ReasoningChain and Reasoner orchestrator."""

from ultimate_trader.cognitive_engine.observation import Observation, ObservationType
from ultimate_trader.cognitive_engine.reasoning_chain import Reasoner, ReasoningChain


class TestReasoningChainModel:
    def test_reasoning_chain_created(self):
        chain = ReasoningChain(
            chain_id="CHAIN-001",
            symbol="BTCUSDT",
            timeframe="1h",
        )
        assert chain.should_trade is False
        assert chain.preliminary_bias == "NO_TRADE"

    def test_reasoning_chain_full(self):
        chain = ReasoningChain(
            chain_id="CHAIN-002",
            symbol="ETHUSDT",
            timeframe="15m",
            confidence_before=50.0,
            confidence_after=70.0,
            risk_before=50.0,
            risk_after=30.0,
            uncertainty_score=25.0,
            preliminary_bias="LONG",
            final_conclusion="Conditions favorable",
            should_trade=True,
        )
        assert chain.should_trade is True


class TestReasoner:
    def setup_method(self):
        self.reasoner = Reasoner()

    def test_reasoner_empty_observations(self):
        chain = self.reasoner.reason([])
        assert chain.should_trade is False
        assert "No observations" in chain.final_conclusion

    def test_reasoner_single_observation(self):
        obs = Observation(
            observation_id="OBS-001",
            symbol="BTCUSDT",
            timeframe="1h",
            observation_type=ObservationType.PRICE_ACTION,
            description="Price rejected at resistance",
            source="manual",
            reliability_score=0.7,
        )
        chain = self.reasoner.reason([obs])
        assert chain.symbol == "BTCUSDT"
        assert len(chain.observations) == 1
        assert len(chain.interpretations) == 1
        assert len(chain.alternative_hypotheses) > 0

    def test_reasoner_multiple_observations(self):
        obs1 = Observation(
            observation_id="OBS-001",
            symbol="BTCUSDT",
            timeframe="1h",
            observation_type=ObservationType.PRICE_ACTION,
            description="Price breaking above resistance with momentum",
            source="manual",
            reliability_score=0.8,
        )
        obs2 = Observation(
            observation_id="OBS-002",
            symbol="BTCUSDT",
            timeframe="1h",
            observation_type=ObservationType.VOLUME,
            description="Volume confirming the breakout",
            source="manual",
            reliability_score=0.7,
        )
        chain = self.reasoner.reason([obs1, obs2])
        assert len(chain.observations) == 2
        assert len(chain.interpretations) == 2
        assert chain.confidence_after >= 0.0
        assert chain.confidence_after <= 100.0

    def test_reasoner_generates_evidence(self):
        obs = Observation(
            observation_id="OBS-001",
            symbol="BTCUSDT",
            timeframe="1h",
            observation_type=ObservationType.LIQUIDITY,
            description="Liquidity sweep detected at support",
            source="manual",
            reliability_score=0.9,
        )
        chain = self.reasoner.reason([obs])
        assert len(chain.evidence_for) > 0 or len(chain.evidence_against) > 0

    def test_reasoner_missing_evidence_detected(self):
        obs = Observation(
            observation_id="OBS-001",
            symbol="BTCUSDT",
            timeframe="1h",
            observation_type=ObservationType.PRICE_ACTION,
            description="Strong bullish price action",
            source="manual",
        )
        chain = self.reasoner.reason([obs])
        assert len(chain.missing_evidence) > 0

    def test_reasoner_uncertainty_assessed(self):
        obs = Observation(
            observation_id="OBS-001",
            symbol="BTCUSDT",
            timeframe="1h",
            observation_type=ObservationType.REGIME,
            description="Regime is unclear — ranging conditions",
            source="manual",
        )
        chain = self.reasoner.reason([obs])
        assert chain.uncertainty_score > 0
