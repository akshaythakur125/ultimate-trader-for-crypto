"""Tests for the CounterfactualReasoner."""

from ultimate_trader.cognitive_engine.evidence_evaluator import EvidenceItem, EvidenceType
from ultimate_trader.cognitive_engine.reasoning_chain import ReasoningChain
from ultimate_trader.metacognition_engine.counterfactual_reasoning import (
    CounterfactualReasoner,
)


class TestCounterfactualReasoner:
    def setup_method(self):
        self.reasoner = CounterfactualReasoner()

    def test_reasoner_returns_questions(self):
        chain = ReasoningChain(
            chain_id="CHAIN-001",
            symbol="BTCUSDT",
            timeframe="1h",
            confidence_after=50.0,
            confidence_before=50.0,
            risk_after=50.0,
            uncertainty_score=50.0,
        )
        result = self.reasoner.reason(chain)
        assert len(result.counterfactual_questions) >= 5

    def test_questions_have_answers(self):
        chain = ReasoningChain(
            chain_id="CHAIN-002",
            symbol="ETHUSDT",
            timeframe="15m",
            confidence_after=60.0,
            confidence_before=40.0,
            risk_after=30.0,
            uncertainty_score=20.0,
            should_trade=True,
        )
        result = self.reasoner.reason(chain)
        for q in result.counterfactual_questions:
            assert len(q.answer) > 0

    def test_key_insight_generated(self):
        chain = ReasoningChain(
            chain_id="CHAIN-003",
            symbol="BTCUSDT",
            timeframe="1h",
            evidence_for=[
                EvidenceItem(
                    evidence_id="EV-001",
                    description="Supporting data",
                    evidence_type=EvidenceType.CONFIRMATION,
                ),
            ],
            evidence_against=[
                EvidenceItem(
                    evidence_id="EV-002",
                    description="Contradicting data",
                    evidence_type=EvidenceType.CONTRADICTION,
                ),
            ],
            missing_evidence=["a", "b"],
            contradictions=[{"rule": "test", "severity": "HIGH"}],
            confidence_after=30.0,
            confidence_before=50.0,
            risk_after=80.0,
            uncertainty_score=85.0,
            should_trade=False,
        )
        result = self.reasoner.reason(chain)
        assert len(result.key_insight) > 0
