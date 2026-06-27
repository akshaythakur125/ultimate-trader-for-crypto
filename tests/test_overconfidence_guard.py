"""Tests for the OverconfidenceGuard."""

from ultimate_trader.cognitive_engine.evidence_evaluator import EvidenceItem, EvidenceType
from ultimate_trader.cognitive_engine.reasoning_chain import ReasoningChain
from ultimate_trader.metacognition_engine.overconfidence_guard import OverconfidenceGuard


class TestOverconfidenceGuard:
    def setup_method(self):
        self.guard = OverconfidenceGuard()

    def test_no_adjustment_when_well_calibrated(self):
        chain = ReasoningChain(
            chain_id="CHAIN-001",
            symbol="BTCUSDT",
            timeframe="1h",
            evidence_for=[
                EvidenceItem(
                    evidence_id="EV-001",
                    description="Strong evidence",
                    evidence_type=EvidenceType.CONFIRMATION,
                    strength_score=0.9,
                    reliability_score=0.9,
                ),
            ],
            evidence_against=[
                EvidenceItem(
                    evidence_id="EV-002",
                    description="Some against",
                    evidence_type=EvidenceType.WARNING,
                    strength_score=0.3,
                    reliability_score=0.5,
                ),
            ],
            contradictions=[],
            confidence_after=60.0,
            confidence_before=50.0,
            uncertainty_score=25.0,
            should_trade=True,
        )
        result = self.guard.evaluate(chain)
        assert result.adjusted_confidence == 60.0
        assert result.reduction_amount == 0.0

    def test_penalty_for_high_uncertainty(self):
        chain = ReasoningChain(
            chain_id="CHAIN-002",
            symbol="BTCUSDT",
            timeframe="1h",
            evidence_for=[EvidenceItem(evidence_id="EV-001", description="E",
                           evidence_type=EvidenceType.CONFIRMATION, strength_score=0.5, reliability_score=0.5)],
            contradictions=[{"rule": "test", "severity": "HIGH"}],
            confidence_after=70.0,
            uncertainty_score=85.0,
            should_trade=True,
        )
        result = self.guard.evaluate(chain)
        assert result.reduction_amount > 0

    def test_never_raises_confidence(self):
        chain = ReasoningChain(
            chain_id="CHAIN-003",
            symbol="BTCUSDT",
            timeframe="1h",
            confidence_after=30.0,
            should_trade=False,
        )
        result = self.guard.evaluate(chain)
        assert result.adjusted_confidence <= 30.0
