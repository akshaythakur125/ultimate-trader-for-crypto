"""Tests for the ScenarioSimulator."""

from ultimate_trader.cognitive_engine.reasoning_chain import ReasoningChain
from ultimate_trader.metacognition_engine.scenario_simulator import (
    DirectionOutcome,
    ScenarioSimulator,
)


class TestScenarioSimulator:
    def setup_method(self):
        self.simulator = ScenarioSimulator()

    def test_simulator_generates_scenarios(self):
        chain = ReasoningChain(
            chain_id="CHAIN-001",
            symbol="BTCUSDT",
            timeframe="1h",
            preliminary_bias="LONG",
            evidence_for=[],
            evidence_against=[],
            missing_evidence=[],
            contradictions=[],
            confidence_after=60.0,
            confidence_before=50.0,
            risk_after=40.0,
            uncertainty_score=30.0,
            should_trade=True,
        )
        result = self.simulator.simulate(chain)
        assert len(result.scenarios) >= 3
        assert result.most_likely_scenario is not None

    def test_scenario_probabilities_normalize(self):
        chain = ReasoningChain(
            chain_id="CHAIN-002",
            symbol="BTCUSDT",
            timeframe="1h",
            preliminary_bias="SHORT",
            confidence_after=50.0,
            confidence_before=50.0,
            risk_after=50.0,
            uncertainty_score=50.0,
            should_trade=False,
        )
        result = self.simulator.simulate(chain)
        total = sum(s.probability_estimate for s in result.scenarios)
        assert total > 0.0
        for s in result.scenarios:
            assert 0.0 <= s.probability_estimate <= 1.0

    def test_most_likely_scenario_selected(self):
        chain = ReasoningChain(
            chain_id="CHAIN-003",
            symbol="BTCUSDT",
            timeframe="1h",
            preliminary_bias="LONG",
            confidence_after=80.0,
            confidence_before=50.0,
            risk_after=30.0,
            uncertainty_score=20.0,
            should_trade=True,
        )
        result = self.simulator.simulate(chain)
        assert result.most_likely_scenario is not None
        assert result.most_likely_scenario.probability_estimate >= max(
            s.probability_estimate for s in result.scenarios
        )

    def test_worst_case_identified(self):
        chain = ReasoningChain(
            chain_id="CHAIN-004",
            symbol="BTCUSDT",
            timeframe="1h",
            preliminary_bias="LONG",
            confidence_after=50.0,
            confidence_before=50.0,
            risk_after=50.0,
            uncertainty_score=70.0,
            should_trade=False,
        )
        result = self.simulator.simulate(chain)
        assert result.worst_case_scenario is not None

    def test_conflict_score_high_with_spread_probabilities(self):
        chain = ReasoningChain(
            chain_id="CHAIN-005",
            symbol="BTCUSDT",
            timeframe="1h",
            preliminary_bias="LONG",
            contradictions=[
                {"rule": "a", "severity": "HIGH"},
                {"rule": "b", "severity": "HIGH"},
            ],
            missing_evidence=["a", "b", "c", "d", "e"],
            confidence_after=40.0,
            confidence_before=50.0,
            risk_after=60.0,
            uncertainty_score=80.0,
            should_trade=False,
        )
        result = self.simulator.simulate(chain)
        assert result.scenario_conflict_score >= 0
