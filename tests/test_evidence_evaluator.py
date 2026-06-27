"""Tests for the EvidenceEvaluator — scoring, separating, and missing detection."""

from ultimate_trader.cognitive_engine.evidence_evaluator import (
    EvidenceEvaluator,
    EvidenceItem,
    EvidenceType,
)
from ultimate_trader.cognitive_engine.hypothesis_reasoning import (
    AlternativeHypothesis,
    HypothesisDirection,
)
from ultimate_trader.cognitive_engine.observation import Observation, ObservationType


class TestEvidenceEvaluator:
    def setup_method(self):
        self.evaluator = EvidenceEvaluator()

    def test_score_evidence_strength_confirmation(self):
        item = EvidenceItem(
            evidence_id="EV-001",
            description="Volume supports directional move",
            evidence_type=EvidenceType.CONFIRMATION,
            strength_score=0.8,
            reliability_score=0.7,
        )
        score = self.evaluator.score_evidence_strength(item)
        assert 0.0 < score <= 1.0
        assert score > 0.5

    def test_score_evidence_strength_contradiction(self):
        item = EvidenceItem(
            evidence_id="EV-002",
            description="Order flow contradicts direction",
            evidence_type=EvidenceType.CONTRADICTION,
            strength_score=0.6,
            reliability_score=0.8,
        )
        score = self.evaluator.score_evidence_strength(item)
        assert score > 0.5

    def test_separate_supporting_and_contradicting(self):
        items = [
            EvidenceItem(
                evidence_id="EV-001",
                description="Supports",
                evidence_type=EvidenceType.CONFIRMATION,
                supports="HYP-001",
                strength_score=0.8,
                reliability_score=0.7,
            ),
            EvidenceItem(
                evidence_id="EV-002",
                description="Contradicts",
                evidence_type=EvidenceType.CONTRADICTION,
                contradicts="HYP-001",
                strength_score=0.6,
                reliability_score=0.5,
            ),
            EvidenceItem(
                evidence_id="EV-003",
                description="Neutral",
                evidence_type=EvidenceType.NEUTRAL,
                strength_score=0.5,
                reliability_score=0.5,
            ),
        ]
        supporting, contradicting = self.evaluator.separate_supporting_contradicting(
            items, "HYP-001"
        )
        assert len(supporting) >= 1
        assert len(contradicting) >= 1

    def test_detect_missing_critical_evidence(self):
        hyp = AlternativeHypothesis(
            hypothesis_id="HYP-001",
            name="Trend Continuation",
            description="Expect trend to continue",
            direction_bias=HypothesisDirection.LONG,
            required_evidence=["volume_confirmation", "order_flow_confirmation"],
        )
        available = [
            EvidenceItem(
                evidence_id="EV-001",
                description="volume_confirmation",
                evidence_type=EvidenceType.CONFIRMATION,
                strength_score=0.8,
                reliability_score=0.7,
            )
        ]
        missing = self.evaluator.detect_missing_critical_evidence(hyp, available)
        assert "order_flow_confirmation" in missing
        assert "volume_confirmation" not in missing

    def test_assess_missing_evidence_for_directional_hypothesis(self):
        hyp = AlternativeHypothesis(
            hypothesis_id="HYP-001",
            name="Trend Continuation",
            description="Expect trend to continue",
            direction_bias=HypothesisDirection.LONG,
        )
        obs = Observation(
            observation_id="OBS-001",
            symbol="BTCUSDT",
            timeframe="1h",
            observation_type=ObservationType.PRICE_ACTION,
            description="Price moving up",
            source="manual",
        )
        missing = self.evaluator.assess_missing_evidence([obs], hyp)
        assert "order_flow_confirmation" in missing
        assert "volume_confirmation" in missing
