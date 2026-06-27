"""Tests for the SelfCritiqueEngine."""

from ultimate_trader.cognitive_engine.observation import Observation, ObservationType
from ultimate_trader.cognitive_engine.reasoning_chain import Reasoner, ReasoningChain
from ultimate_trader.metacognition_engine.self_critique import SelfCritiqueEngine


class TestSelfCritiqueEngine:
    def setup_method(self):
        self.reasoner = Reasoner()
        self.engine = SelfCritiqueEngine()

    def _make_chain(self, observations: list[Observation]) -> ReasoningChain:
        return self.reasoner.reason(observations)

    def test_critique_accepts_good_decision(self):
        obs = Observation(
            observation_id="OBS-001",
            symbol="BTCUSDT",
            timeframe="1h",
            observation_type=ObservationType.PRICE_ACTION,
            description="Price breaking above resistance with strong momentum",
            source="manual",
            reliability_score=0.9,
        )
        chain = self._make_chain([obs])
        critique = self.engine.critique(chain)
        assert critique.critique_id.startswith("SC-")

    def test_critique_identifies_rejection_warranted(self):
        chain = ReasoningChain(
            chain_id="CHAIN-001",
            symbol="BTCUSDT",
            timeframe="1h",
            uncertainty_score=85.0,
            should_trade=False,
            reason_not_to_trade="High uncertainty and missing evidence",
        )
        critique = self.engine.critique(chain)
        assert critique.should_reject_trade is True
        assert "rejection" in critique.critique_summary.lower()

    def test_critique_identifies_ignored_risks(self):
        chain = ReasoningChain(
            chain_id="CHAIN-002",
            symbol="BTCUSDT",
            timeframe="1h",
            uncertainty_score=75.0,
            should_trade=True,
            contradictions=[{"rule": "test_rule", "severity": "HIGH"}],
        )
        critique = self.engine.critique(chain)
        assert len(critique.ignored_risks) > 0

    def test_critique_summary_non_empty(self):
        obs = Observation(
            observation_id="OBS-001",
            symbol="ETHUSDT",
            timeframe="15m",
            observation_type=ObservationType.VOLUME,
            description="Volume spike with price rejection",
            source="manual",
        )
        chain = self._make_chain([obs])
        critique = self.engine.critique(chain)
        assert len(critique.critique_summary) > 0
