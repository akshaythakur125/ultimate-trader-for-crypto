import pytest
from datetime import datetime
from ultimate_trader.selectivity_engine.quality_gate import QualityGate, QualityGateConfig, QualityGateResult
from ultimate_trader.selectivity_engine.candidate_ranker import RankedCandidate


def make_rc(grade="A_PLUS", confluence=70, confidence=0.7, conflict=0.2, reversal=30, risk=20, rr=3.5):
    return RankedCandidate(
        candidate_id="test_1", symbol="BTCUSDT", direction="LONG",
        timestamp=datetime(2025, 6, 1, 10, 0),
        rank_grade=grade, rank_score=80.0,
        confluence_score=confluence, directional_confidence=confidence,
        conflict_score=conflict, reversal_risk_score=reversal,
        risk_score=risk, rr_ratio=rr,
        continuation_score=50, target_realism_score=60,
        stop_quality_score=70, volatility_alignment=60,
    )


class TestQualityGate:
    def test_passes_a_plus(self):
        gate = QualityGate()
        rc = make_rc(grade="A_PLUS")
        result = gate.evaluate(rc)
        assert result.passed

    def test_passes_a(self):
        gate = QualityGate()
        rc = make_rc(grade="A")
        result = gate.evaluate(rc)
        assert result.passed

    def test_rejects_b(self):
        gate = QualityGate()
        rc = make_rc(grade="B")
        result = gate.evaluate(rc)
        assert not result.passed
        assert result.rejection_category == "low_rank"

    def test_rejects_c(self):
        gate = QualityGate()
        rc = make_rc(grade="C")
        result = gate.evaluate(rc)
        assert not result.passed

    def test_rejects_reject(self):
        gate = QualityGate()
        rc = make_rc(grade="REJECT")
        result = gate.evaluate(rc)
        assert not result.passed

    def test_rejects_low_confluence(self):
        gate = QualityGate()
        rc = make_rc(confluence=40)
        result = gate.evaluate(rc)
        assert not result.passed
        assert result.rejection_category == "confluence"

    def test_rejects_low_confidence(self):
        gate = QualityGate()
        rc = make_rc(confidence=0.4)
        result = gate.evaluate(rc)
        assert not result.passed
        assert result.rejection_category == "directional_confidence"

    def test_rejects_high_conflict(self):
        gate = QualityGate()
        rc = make_rc(conflict=0.7)
        result = gate.evaluate(rc)
        assert not result.passed
        assert result.rejection_category == "conflict"

    def test_rejects_high_reversal_risk(self):
        gate = QualityGate()
        rc = make_rc(reversal=70)
        result = gate.evaluate(rc)
        assert not result.passed
        assert result.rejection_category == "reversal_risk"

    def test_rejects_high_risk(self):
        gate = QualityGate()
        rc = make_rc(risk=60)
        result = gate.evaluate(rc)
        assert not result.passed
        assert result.rejection_category == "risk"

    def test_rejects_low_rr(self):
        gate = QualityGate()
        rc = make_rc(rr=2.0)
        result = gate.evaluate(rc)
        assert not result.passed
        assert result.rejection_category == "rr"

    def test_rejects_first_failure_only(self):
        gate = QualityGate()
        rc = make_rc(grade="B", confluence=30, confidence=0.3)
        result = gate.evaluate(rc)
        assert not result.passed
        assert result.rejection_category == "low_rank"

    def test_custom_config(self):
        config = QualityGateConfig(
            min_confluence_score=30, min_directional_confidence=0.3,
            max_conflict_score=0.6, max_reversal_risk_score=60,
            max_risk_score=50, min_rr=1.5,
            allowed_grades={"A_PLUS", "A", "B"},
        )
        gate = QualityGate(config)
        rc = make_rc(grade="B", confluence=35, confidence=0.4, conflict=0.5, reversal=55, risk=45, rr=1.6)
        result = gate.evaluate(rc)
        assert result.passed

    def test_quality_gate_config_defaults(self):
        config = QualityGateConfig()
        assert config.min_confluence_score == 50
        assert config.min_directional_confidence == 0.55
        assert config.max_conflict_score == 0.4
        assert config.min_rr == 3.0
