"""Tests for the MetacognitiveReportGenerator."""

from ultimate_trader.cognitive_engine.reasoning_chain import ReasoningChain
from ultimate_trader.metacognition_engine.metacognitive_report import (
    MetacognitiveReportGenerator,
)


class TestMetacognitiveReportGenerator:
    def setup_method(self):
        self.generator = MetacognitiveReportGenerator()

    def test_report_generated(self):
        chain = ReasoningChain(
            chain_id="CHAIN-001",
            symbol="BTCUSDT",
            timeframe="1h",
            confidence_after=60.0,
            uncertainty_score=30.0,
            should_trade=True,
        )
        report = self.generator.generate(chain)
        assert report.report_id.startswith("MCR-")

    def test_report_integrates_audits(self):
        chain = ReasoningChain(
            chain_id="CHAIN-002",
            symbol="ETHUSDT",
            timeframe="15m",
            evidence_for=[],
            evidence_against=[],
            missing_evidence=["a", "b", "c", "d", "e"],
            contradictions=[
                {"rule": "a", "severity": "HIGH"},
                {"rule": "b", "severity": "HIGH"},
                {"rule": "c", "severity": "HIGH"},
            ],
            confidence_after=30.0,
            confidence_before=50.0,
            risk_after=80.0,
            uncertainty_score=85.0,
            should_trade=False,
        )
        report = self.generator.generate(chain)
        assert report.decision_audit.audit_passed is False
        assert report.self_critique.should_reject_trade is True
        assert len(report.bias_detection.detected_biases) > 0
        assert len(report.decision_audit.required_corrections) > 0

    def test_report_provides_final_action(self):
        chain = ReasoningChain(
            chain_id="CHAIN-003",
            symbol="BTCUSDT",
            timeframe="1h",
        )
        report = self.generator.generate(chain)
        assert len(report.final_action) > 0

    def test_readiness_scores_present(self):
        chain = ReasoningChain(
            chain_id="CHAIN-004",
            symbol="BTCUSDT",
            timeframe="1h",
            confidence_after=55.0,
            uncertainty_score=45.0,
        )
        report = self.generator.generate(chain)
        assert report.trade_readiness.readiness_score >= 0
        assert report.overconfidence_adjustment.adjusted_confidence >= 0
