"""Tests for metacognition engine models."""

from ultimate_trader.metacognition_engine.bias_detector import BiasDetection, BiasType
from ultimate_trader.metacognition_engine.scenario_simulator import (
    DirectionOutcome,
    MarketScenario,
    ScenarioSimulationResult,
)
from ultimate_trader.metacognition_engine.self_critique import SelfCritique
from ultimate_trader.metacognition_engine.trade_readiness import (
    FinalRecommendation,
    TradeReadinessAssessment,
)


class TestSelfCritique:
    def test_self_critique_created(self):
        sc = SelfCritique(
            critique_id="SC-001",
            target_decision_id="DEC-001",
        )
        assert sc.should_reduce_confidence is False
        assert sc.should_reject_trade is False

    def test_self_critique_rejection(self):
        sc = SelfCritique(
            critique_id="SC-002",
            target_decision_id="DEC-002",
            strongest_argument_against_trade="High uncertainty and missing evidence",
            should_reject_trade=True,
            critique_summary="Critique recommends rejection",
        )
        assert sc.should_reject_trade is True


class TestBiasDetection:
    def test_bias_detection_created(self):
        bd = BiasDetection(
            bias_report_id="BD-001",
            target_decision_id="DEC-001",
        )
        assert bd.detected_biases == []
        assert bd.confirmation_bias_score == 0.0

    def test_bias_detection_with_biases(self):
        bd = BiasDetection(
            bias_report_id="BD-002",
            target_decision_id="DEC-002",
            detected_biases=[BiasType.OVERCONFIDENCE, BiasType.FORCED_TRADE],
            overconfidence_score=75.0,
            forced_trade_score=80.0,
            bias_summary="Overconfidence and forced trade detected",
            recommended_action="HUMAN_REVIEW",
        )
        assert BiasType.OVERCONFIDENCE in bd.detected_biases
        assert bd.overconfidence_score == 75.0


class TestScenarioSimulation:
    def test_market_scenario_created(self):
        sc = MarketScenario(
            scenario_id="SCN-001",
            name="Bullish Continuation",
            description="Price continues upward.",
            direction_outcome=DirectionOutcome.LONG_CONTINUATION,
            probability_estimate=0.6,
            risk_if_wrong="Loss on reversal",
            invalidation_trigger="Price breaks support",
        )
        assert sc.direction_outcome == DirectionOutcome.LONG_CONTINUATION

    def test_scenario_simulation_result(self):
        result = ScenarioSimulationResult(
            simulation_id="SIM-001",
            target_decision_id="DEC-001",
        )
        assert result.scenario_conflict_score == 0.0


class TestTradeReadiness:
    def test_trade_readiness_created(self):
        tra = TradeReadinessAssessment(
            assessment_id="TRA-001",
            target_decision_id="DEC-001",
        )
        assert tra.ready_for_live_trade is False
        assert tra.final_recommendation == FinalRecommendation.WAIT

    def test_trade_readiness_blocked(self):
        tra = TradeReadinessAssessment(
            assessment_id="TRA-002",
            target_decision_id="DEC-002",
            ready_for_live_trade=False,
            blocking_reasons=["Live trading disabled"],
            final_recommendation=FinalRecommendation.LIVE_TRADE_BLOCKED,
        )
        assert FinalRecommendation.LIVE_TRADE_BLOCKED in FinalRecommendation
