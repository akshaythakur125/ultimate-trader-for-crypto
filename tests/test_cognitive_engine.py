"""Tests for the Cognitive Engine — models, observations, hypotheses, reports."""

from datetime import datetime, timezone

from ultimate_trader.cognitive_engine.cognitive_report import (
    CognitiveReport,
    CognitiveReportGenerator,
)
from ultimate_trader.cognitive_engine.decision_context import (
    CognitiveDecisionContext,
    NextBestAction,
)
from ultimate_trader.cognitive_engine.hypothesis_reasoning import (
    AlternativeHypothesis,
    HypothesisDirection,
    HypothesisStatus,
)
from ultimate_trader.cognitive_engine.observation import Observation, ObservationType


class TestObservation:
    def test_observation_created(self):
        obs = Observation(
            observation_id="OBS-001",
            symbol="BTCUSDT",
            timeframe="1h",
            observation_type=ObservationType.PRICE_ACTION,
            description="Price rejected at resistance",
            source="manual",
        )
        assert obs.observation_id == "OBS-001"
        assert obs.reliability_score == 0.5

    def test_observation_with_features(self):
        obs = Observation(
            observation_id="OBS-002",
            symbol="ETHUSDT",
            timeframe="15m",
            observation_type=ObservationType.VOLUME,
            description="Volume spike detected",
            raw_features={"volume": 50000, "avg_volume": 10000},
            source="volume_analyzer",
            reliability_score=0.8,
        )
        assert obs.raw_features["volume"] == 50000
        assert obs.reliability_score == 0.8


class TestAlternativeHypothesis:
    def test_hypothesis_created(self):
        hyp = AlternativeHypothesis(
            hypothesis_id="HYP-COG-001",
            name="Trend Continuation",
            description="Price action suggests trend continues.",
            direction_bias=HypothesisDirection.LONG,
        )
        assert hyp.status == HypothesisStatus.ACTIVE
        assert hyp.confidence_score == 0.0

    def test_hypothesis_rejected(self):
        hyp = AlternativeHypothesis(
            hypothesis_id="HYP-COG-002",
            name="Bad Setup",
            description="No evidence supports this.",
            direction_bias=HypothesisDirection.NO_TRADE,
            status=HypothesisStatus.REJECTED,
        )
        assert hyp.status == HypothesisStatus.REJECTED


class TestCognitiveReport:
    def test_cognitive_report_created(self):
        report = CognitiveReport(
            report_id="CR-001",
            symbol="BTCUSDT",
            timeframe="1h",
            summary="No trade recommended.",
            recommended_next_action="WAIT",
            explanation="Insufficient evidence.",
        )
        assert report.observations_reviewed == 0


class TestCognitiveDecisionContext:
    def test_decision_context_defaults(self):
        ctx = CognitiveDecisionContext(
            symbol="BTCUSDT",
            timeframe="1h",
        )
        assert ctx.next_best_action == NextBestAction.WAIT
        assert ctx.requires_human_review is False

    def test_decision_context_with_hypothesis(self):
        hyp = AlternativeHypothesis(
            hypothesis_id="HYP-001",
            name="Test",
            description="Test hypothesis",
            direction_bias=HypothesisDirection.LONG,
        )
        ctx = CognitiveDecisionContext(
            symbol="ETHUSDT",
            timeframe="15m",
            dominant_hypothesis=hyp,
            next_best_action=NextBestAction.BACKTEST_HYPOTHESIS,
        )
        assert ctx.dominant_hypothesis is not None
        assert ctx.next_best_action == NextBestAction.BACKTEST_HYPOTHESIS
