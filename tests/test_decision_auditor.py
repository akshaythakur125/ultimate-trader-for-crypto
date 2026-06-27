"""Tests for the DecisionAuditor."""

from ultimate_trader.cognitive_engine.evidence_evaluator import EvidenceItem, EvidenceType
from ultimate_trader.cognitive_engine.reasoning_chain import ReasoningChain
from ultimate_trader.metacognition_engine.decision_auditor import DecisionAuditor


class TestDecisionAuditor:
    def setup_method(self):
        self.auditor = DecisionAuditor()

    def _make_evidence(self, eid: str, etype: EvidenceType = EvidenceType.CONFIRMATION) -> EvidenceItem:
        return EvidenceItem(
            evidence_id=eid,
            description=f"Evidence {eid}",
            evidence_type=etype,
        )

    def test_audit_passes_for_good_decision(self):
        chain = ReasoningChain(
            chain_id="CHAIN-001",
            symbol="BTCUSDT",
            timeframe="1h",
            evidence_for=[self._make_evidence("EV-1"), self._make_evidence("EV-2"), self._make_evidence("EV-3")],
            evidence_against=[],
            missing_evidence=[],
            contradictions=[],
            confidence_after=70.0,
            confidence_before=50.0,
            risk_after=30.0,
            uncertainty_score=20.0,
            should_trade=True,
        )
        audit = self.auditor.audit(chain)
        assert audit.audit_passed is True

    def test_audit_fails_for_poor_decision(self):
        chain = ReasoningChain(
            chain_id="CHAIN-002",
            symbol="BTCUSDT",
            timeframe="1h",
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
        audit = self.auditor.audit(chain)
        assert audit.audit_passed is False

    def test_audit_provides_corrections(self):
        chain = ReasoningChain(
            chain_id="CHAIN-003",
            symbol="BTCUSDT",
            timeframe="1h",
            evidence_for=[],
            evidence_against=[],
            missing_evidence=["a", "b", "c"],
            contradictions=[
                {"rule": "a", "severity": "HIGH"},
            ],
            confidence_after=30.0,
            confidence_before=50.0,
            risk_after=70.0,
            uncertainty_score=80.0,
            should_trade=False,
        )
        audit = self.auditor.audit(chain)
        assert len(audit.required_corrections) > 0

    def test_audit_scores_in_range(self):
        chain = ReasoningChain(
            chain_id="CHAIN-004",
            symbol="BTCUSDT",
            timeframe="1h",
            evidence_for=[self._make_evidence("EV-1"), self._make_evidence("EV-2")],
            evidence_against=[self._make_evidence("EV-3", EvidenceType.CONTRADICTION)],
            missing_evidence=["a"],
            contradictions=[{"rule": "a", "severity": "MEDIUM"}],
            confidence_after=55.0,
            confidence_before=50.0,
            risk_after=50.0,
            uncertainty_score=40.0,
            should_trade=False,
        )
        audit = self.auditor.audit(chain)
        for score in [
            audit.evidence_quality_score,
            audit.contradiction_score,
            audit.uncertainty_score,
            audit.risk_alignment_score,
            audit.confidence_justification_score,
            audit.forced_trade_risk_score,
        ]:
            assert 0.0 <= score <= 100.0
