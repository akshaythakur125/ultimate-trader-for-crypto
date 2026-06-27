"""Tests specific to the TradingHypothesis schema and its lifecycle."""

import uuid

import pytest
from pydantic import ValidationError

from ultimate_trader.core.constants import HypothesisStatus
from ultimate_trader.schemas.hypothesis import EvidenceBundle, TradingHypothesis


def make_valid_hypothesis(**overrides) -> dict:
    data = {
        "hypothesis_id": f"HYP-{uuid.uuid4().hex[:8].upper()}",
        "name": "Valid Test Hypothesis",
        "description": "A hypothesis for testing.",
        "edge_theory": "Edge based on momentum continuation after liquidity sweep.",
        "expected_market_regime": "trending",
        "required_liquidity_condition": "liquidity_sweep_detected",
        "required_orderflow_condition": "aggressive_buying_confirmed",
        "expected_holding_time_hours": 6.0,
        "minimum_rr": 3.0,
        "preferred_rr": 5.0,
        "entry_logic_description": "Enter on retest of swept level with confirmation.",
        "invalidation_logic_description": "Invalidate if price closes below sweep level.",
        "expected_failure_conditions": "Market becomes choppy or volume drops.",
    }
    data.update(overrides)
    return data


class TestTradingHypothesisContract:
    def test_valid_hypothesis_created(self):
        data = make_valid_hypothesis()
        hyp = TradingHypothesis(**data)
        assert hyp.status == HypothesisStatus.DRAFT
        assert hyp.rejection_reason is None

    def test_hypothesis_rejected_with_reason(self):
        data = make_valid_hypothesis(
            status=HypothesisStatus.REJECTED,
            rejection_reason="Insufficient backtest evidence.",
        )
        hyp = TradingHypothesis(**data)
        assert hyp.status == HypothesisStatus.REJECTED
        assert hyp.rejection_reason == "Insufficient backtest evidence."

    def test_hypothesis_id_required(self):
        data = make_valid_hypothesis()
        del data["hypothesis_id"]
        with pytest.raises(ValidationError):
            TradingHypothesis(**data)

    def test_negative_rr_rejected(self):
        data = make_valid_hypothesis(minimum_rr=-1.0)
        with pytest.raises(ValidationError):
            TradingHypothesis(**data)

    def test_evidence_bundle_contract(self):
        eb = EvidenceBundle()
        assert eb.evidence_for == []
        assert eb.evidence_against == []
        assert eb.missing_evidence == []
        assert eb.uncertainty_notes == []

    def test_evidence_bundle_with_data(self):
        eb = EvidenceBundle(
            evidence_for=["Volume increasing", "Trend strong"],
            evidence_against=["RSI divergence"],
            missing_evidence=["Order book data"],
            uncertainty_notes=["Weekend low volume"],
        )
        assert len(eb.evidence_for) == 2
        assert "RSI divergence" in eb.evidence_against
