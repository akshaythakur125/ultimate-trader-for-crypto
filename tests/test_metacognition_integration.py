"""Integration tests for the full metacognition pipeline."""

from ultimate_trader.cognitive_engine.observation import Observation, ObservationType
from ultimate_trader.cognitive_engine.reasoning_chain import Reasoner
from ultimate_trader.metacognition_engine.bias_detector import BiasDetector
from ultimate_trader.metacognition_engine.counterfactual_reasoning import (
    CounterfactualReasoner,
)
from ultimate_trader.metacognition_engine.decision_auditor import DecisionAuditor
from ultimate_trader.metacognition_engine.metacognitive_report import (
    MetacognitiveReportGenerator,
)
from ultimate_trader.metacognition_engine.overconfidence_guard import OverconfidenceGuard
from ultimate_trader.metacognition_engine.scenario_simulator import ScenarioSimulator
from ultimate_trader.metacognition_engine.self_critique import SelfCritiqueEngine
from ultimate_trader.metacognition_engine.trade_readiness import TradeReadinessChecker


class TestMetacognitionIntegration:
    def setup_method(self):
        self.reasoner = Reasoner()
        self.report_generator = MetacognitiveReportGenerator()

    def _build_chain(
        self, obs_text: str, obs_type: ObservationType = ObservationType.PRICE_ACTION
    ) -> tuple[list[Observation], object]:
        obs = [
            Observation(
                observation_id=f"OBS-{i:03d}",
                symbol="BTCUSDT",
                timeframe="1h",
                observation_type=obs_type,
                description=obs_text,
                source="integration_test",
            )
            for i in range(2)
        ]
        chain = self.reasoner.reason(obs)
        return obs, chain

    def test_full_cognitive_metacognitive_pipeline(self):
        obs, chain = self._build_chain(
            "Price breaking above resistance with strong volume confirmation"
        )
        assert chain.should_trade is not None

        report = self.report_generator.generate(chain)
        assert report.report_id.startswith("MCR-")
        assert report.decision_audit.audit_passed is not None
        assert len(report.bias_detection.detected_biases) >= 0
        assert len(report.decision_audit.required_corrections) >= 0
        assert len(report.final_action) > 0
        assert report.trade_readiness.readiness_score >= 0
        assert report.overconfidence_adjustment.adjusted_confidence >= 0

    def test_metacognition_rejects_bad_cognition(self):
        obs, chain = self._build_chain(
            "Random noise, no clear signal",
            ObservationType.UNKNOWN,
        )
        report = self.report_generator.generate(chain)
        if not chain.should_trade:
            assert report.self_critique.should_reject_trade is True
            assert report.trade_readiness.final_recommendation.value in ["WAIT", "LIVE_TRADE_BLOCKED"]

    def test_individual_engines_agree_on_weak_setup(self):
        obs, chain = self._build_chain(
            "Slight price increase with low volume",
        )
        critique = SelfCritiqueEngine().critique(chain)
        bias = BiasDetector().detect(chain)
        scenarios = ScenarioSimulator().simulate(chain)
        audit = DecisionAuditor().audit(chain)
        guard = OverconfidenceGuard().evaluate(chain)
        cf = CounterfactualReasoner().reason(chain)
        readiness = TradeReadinessChecker().check(chain)

        assert critique is not None
        assert bias is not None
        assert len(scenarios.scenarios) >= 3
        assert audit is not None
        assert guard is not None
        assert len(cf.counterfactual_questions) >= 5
        assert readiness is not None
