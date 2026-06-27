"""Tests for the BiasDetector."""

from ultimate_trader.cognitive_engine.evidence_evaluator import EvidenceItem, EvidenceType
from ultimate_trader.cognitive_engine.reasoning_chain import ReasoningChain
from ultimate_trader.metacognition_engine.bias_detector import BiasDetector, BiasType


class TestBiasDetector:
    def setup_method(self):
        self.detector = BiasDetector()

    def test_no_bias_detected_when_balanced(self):
        chain = ReasoningChain(
            chain_id="CHAIN-001",
            symbol="BTCUSDT",
            timeframe="1h",
            evidence_for=[],
            evidence_against=[],
            contradictions=[],
            confidence_after=50.0,
            confidence_before=50.0,
            uncertainty_score=30.0,
            should_trade=False,
        )
        result = self.detector.detect(chain)
        assert BiasType.NONE in result.detected_biases

    def test_confirmation_bias_detected(self):
        chain = ReasoningChain(
            chain_id="CHAIN-002",
            symbol="BTCUSDT",
            timeframe="1h",
            evidence_for=[
                EvidenceItem(
                    evidence_id="EV-001",
                    description="Supports",
                    evidence_type=EvidenceType.CONFIRMATION,
                    strength_score=0.8,
                    reliability_score=0.7,
                ),
                EvidenceItem(
                    evidence_id="EV-002",
                    description="Also supports",
                    evidence_type=EvidenceType.CONFIRMATION,
                    strength_score=0.7,
                    reliability_score=0.6,
                ),
            ],
            evidence_against=[],
            contradictions=[{"rule": "test", "severity": "LOW"}],
            confidence_after=70.0,
            confidence_before=50.0,
            uncertainty_score=30.0,
            should_trade=True,
        )
        result = self.detector.detect(chain)
        assert result.confirmation_bias_score > 50

    def test_overconfidence_detected(self):
        chain = ReasoningChain(
            chain_id="CHAIN-003",
            symbol="BTCUSDT",
            timeframe="1h",
            evidence_for=[
                EvidenceItem(
                    evidence_id="EV-001",
                    description="Single evidence",
                    evidence_type=EvidenceType.CONFIRMATION,
                    strength_score=0.5,
                    reliability_score=0.5,
                ),
            ],
            evidence_against=[],
            contradictions=[],
            confidence_after=85.0,
            confidence_before=50.0,
            uncertainty_score=30.0,
            should_trade=True,
        )
        result = self.detector.detect(chain)
        assert result.overconfidence_score > 50

    def test_forced_trade_detected(self):
        chain = ReasoningChain(
            chain_id="CHAIN-004",
            symbol="BTCUSDT",
            timeframe="1h",
            evidence_for=[],
            evidence_against=[],
            missing_evidence=["a", "b", "c", "d"],
            contradictions=[],
            confidence_after=50.0,
            confidence_before=50.0,
            uncertainty_score=70.0,
            risk_after=70.0,
            should_trade=True,
        )
        result = self.detector.detect(chain)
        assert result.forced_trade_score > 50

    def test_detection_returns_recommendation(self):
        chain = ReasoningChain(
            chain_id="CHAIN-005",
            symbol="BTCUSDT",
            timeframe="1h",
            evidence_for=[],
            evidence_against=[],
            contradictions=[],
            confidence_after=50.0,
            confidence_before=50.0,
            uncertainty_score=50.0,
            should_trade=False,
        )
        result = self.detector.detect(chain)
        assert len(result.recommended_action) > 0
